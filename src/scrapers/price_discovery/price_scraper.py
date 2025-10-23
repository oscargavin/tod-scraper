"""
Price Discovery Scraper
Searches for products and extracts prices from top search results.

This scraper:
1. Searches DuckDuckGo for "{product-name} buy online UK"
2. Extracts top 8 search result links (in search rank order)
3. Opens each link with Playwright (full stealth mode)
4. Extracts price using regex (£XXX pattern)
5. Returns product-price mappings
"""

import os
import re
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from playwright.async_api import async_playwright, Page
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Constants
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
MAX_LINKS_TO_SCRAPE = 8  # Number of top search results to scrape


# Price regex patterns (£XXX, £X,XXX.XX, etc.)
PRICE_PATTERNS = [
    r'£\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # £299, £1,299.99
    r'GBP\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',  # GBP 299
    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*GBP',  # 299 GBP
]


def calculate_price_target(prices: List[float]) -> Optional[float]:
    """
    Calculate target price using hybrid median + mode approach.

    Strategy:
    1. Calculate median of all prices (robust baseline)
    2. Remove extreme outliers (>2x or <0.5x median)
    3. Recalculate median on cleaned data
    4. Try to find mode with clustering on cleaned data
    5. If no clear mode → use cleaned median

    Args:
        prices: List of price floats

    Returns:
        Target price or None if not enough data
    """
    if len(prices) < 2:
        return None

    # Step 1: Calculate initial median
    from statistics import median
    initial_median = median(prices)

    # Step 2: Remove extreme outliers (>2x or <0.5x median)
    cleaned_prices = [
        p for p in prices
        if initial_median * 0.5 <= p <= initial_median * 2.0
    ]

    if not cleaned_prices:
        # All prices are outliers? Just use median
        return initial_median

    # Step 3: Recalculate median on cleaned data
    cleaned_median = median(cleaned_prices)

    # Step 4: Try to find mode with clustering (£5 tolerance)
    if len(cleaned_prices) >= 3:
        sorted_prices = sorted(cleaned_prices)
        clusters = []
        current_cluster = [sorted_prices[0]]

        for price in sorted_prices[1:]:
            if price - current_cluster[-1] <= 5.0:  # £5 tolerance
                current_cluster.append(price)
            else:
                clusters.append(current_cluster)
                current_cluster = [price]

        clusters.append(current_cluster)

        # Find largest cluster (must have at least 2 items to be meaningful)
        largest_cluster = max(clusters, key=len)

        if len(largest_cluster) >= 2:
            # Use median of largest cluster as mode
            return median(largest_cluster)

    # Step 5: No clear mode, use cleaned median
    return cleaned_median


def is_price_in_range(price: float, target: float, tolerance_pct: float = 20.0) -> bool:
    """
    Check if price is within tolerance percentage of target.

    Args:
        price: Price to check
        target: Target price (usually the mode)
        tolerance_pct: Tolerance percentage (default 20%)

    Returns:
        True if price is within range
    """
    lower = target * (1 - tolerance_pct / 100)
    upper = target * (1 + tolerance_pct / 100)
    return lower <= price <= upper


async def search_duckduckgo(page: Page, query: str, max_links: int = MAX_LINKS_TO_SCRAPE) -> List[Dict[str, str]]:
    """
    Search DuckDuckGo and extract top search result links.

    Args:
        page: Playwright page instance
        query: Search query
        max_links: Maximum number of links to extract

    Returns:
        List of dicts with keys: url, title, snippet
    """
    print(f"  Searching DuckDuckGo: {query}")

    try:
        # Navigate to DuckDuckGo
        await page.goto("https://duckduckgo.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # Fill search box and submit
        await page.fill('input[name="q"]', query)
        await page.press('input[name="q"]', "Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        # Extract search result links - try multiple selectors
        selectors_to_try = [
            'a[data-testid="result-title-a"]',
            'article h2 a',
            '.result__a',
            '[data-testid="result"] a',
            'h2 a',  # More generic
            'a[href*="http"]',  # Very generic fallback
        ]

        result_links = []
        for selector in selectors_to_try:
            result_links = await page.query_selector_all(selector)
            if result_links:
                print(f"  Found {len(result_links)} search results using selector: {selector}")
                break

        if not result_links:
            print(f"  Warning: No search results found with any selector")
            # Save screenshot for debugging
            await page.screenshot(path="debug_search_results.png")
            print(f"  Debug screenshot saved: debug_search_results.png")

        extracted_links = []
        for link in result_links[:max_links]:
            try:
                url = await link.get_attribute('href')
                title = await link.inner_text() or ''

                # Try to get snippet from parent
                snippet = ''
                try:
                    parent = await link.evaluate_handle('el => el.closest("article") || el.closest("li")')
                    snippet = await parent.evaluate('el => el.textContent')
                    snippet = snippet[:200] if snippet else ''
                except:
                    pass

                if url and url.startswith('http'):
                    extracted_links.append({
                        'url': url,
                        'title': title,
                        'snippet': snippet
                    })
            except Exception as e:
                print(f"    Warning: Failed to extract link - {e}")
                continue

        print(f"  Extracted {len(extracted_links)} valid links")
        return extracted_links

    except Exception as e:
        print(f"  Error during search: {e}")
        return []


async def extract_price_from_page(page: Page, url: str, timeout: int = 30000,
                                  target_price: Optional[float] = None,
                                  tolerance_pct: float = 20.0) -> Tuple[Optional[str], str]:
    """
    Navigate to URL and extract price using regex.

    Args:
        page: Playwright page instance
        url: URL to visit (may be DuckDuckGo redirect)
        timeout: Navigation timeout in milliseconds
        target_price: If provided, prefer prices within tolerance of this value
        tolerance_pct: Tolerance percentage for target_price (default 20%)

    Returns:
        Tuple of (price_string, final_url)
        - price_string: Price like "299.99" or None if not found
        - final_url: Actual product page URL after redirects
    """
    try:
        # Navigate to page (follows redirects automatically)
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await asyncio.sleep(2)  # Let page settle

        # Get the ACTUAL URL after all redirects
        final_url = page.url

        # Get page content
        content = await page.content()

        # Collect ALL valid prices on the page
        all_prices = []
        for pattern in PRICE_PATTERNS:
            matches = re.findall(pattern, content)
            for match in matches:
                price_str = match.replace(',', '')  # Remove commas
                try:
                    price_float = float(price_str)
                    if 1.0 <= price_float <= 10000.0:
                        all_prices.append((price_str, price_float))
                except ValueError:
                    continue

        if not all_prices:
            return None, final_url

        # If we have a target price, prefer prices within range
        if target_price is not None:
            in_range_prices = [
                (price_str, price_float)
                for price_str, price_float in all_prices
                if is_price_in_range(price_float, target_price, tolerance_pct)
            ]

            if in_range_prices:
                # Return first price in range
                return in_range_prices[0][0], final_url

        # Otherwise return first valid price
        return all_prices[0][0], final_url

    except Exception as e:
        print(f"    Error extracting price from {url[:60]}: {str(e)[:50]}")
        return None, url


async def scrape_prices_for_product(product_name: str, headless: bool = True) -> Dict:
    """
    Main function to discover prices for a product.

    Args:
        product_name: Product name (e.g., "Ninja AF101 Air Fryer")
        headless: Run browser in headless mode

    Returns:
        Dict with keys:
            - product: Product name
            - prices: List of dicts with 'link' and 'price'
            - status: "success" or "failed"
            - error: Error message if failed
    """
    print(f"\n{'='*80}")
    print(f"Price Discovery: {product_name}")
    print(f"{'='*80}")

    result = {
        'product': product_name,
        'prices': [],
        'status': 'failed',
        'error': None
    }

    try:
        # Create browser instance with full stealth mode
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            )

            # Create stealth context
            context = await browser.new_context(
                viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="en-GB",
                timezone_id="Europe/London",
                extra_http_headers={
                    "Accept-Language": "en-GB,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                }
            )

            page = await context.new_page()

            # Hide automation
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # Step 1: Search DuckDuckGo
            search_query = f"{product_name} buy online UK"
            search_links = await search_duckduckgo(page, search_query)

            if not search_links:
                result['error'] = "No search results found"
                return result

            # Step 2: Extract URLs from top search results (in rank order)
            purchase_links = [link['url'] for link in search_links[:MAX_LINKS_TO_SCRAPE]]

            print(f"\n  PASS 1: Extracting initial prices from top {len(purchase_links)} search results...")

            # Step 3: First pass - extract prices without validation
            initial_prices = []
            for i, url in enumerate(purchase_links, 1):
                print(f"  [{i}/{len(purchase_links)}] {url[:70]}...")

                price, final_url = await extract_price_from_page(page, url)

                if price:
                    price_float = float(price)
                    initial_prices.append({
                        'link': final_url,
                        'price': f"£{price}",
                        'price_float': price_float,
                        'url': url  # Keep original for re-scraping
                    })
                    print(f"    ✓ Found price: £{price}")
                else:
                    print(f"    ✗ No price found")

                # Rate limiting
                await asyncio.sleep(2)

            if not initial_prices:
                result['error'] = "No prices found in first pass"
                return result

            # Step 4: Calculate target price using hybrid approach
            price_values = [p['price_float'] for p in initial_prices]
            target_price = calculate_price_target(price_values)

            if target_price:
                # Check if this is median or mode
                from statistics import median
                is_median_fallback = (len(price_values) < 3)

                print(f"\n  Target price: £{target_price:.2f}")
                print(f"  Method: {'Median (fallback)' if is_median_fallback else 'Mode (cluster analysis)'}")
                print(f"  Valid range: £{target_price * 0.8:.2f} - £{target_price * 1.2:.2f} (±20%)")

                # Step 5: Second pass - re-scrape outliers
                outliers = [
                    p for p in initial_prices
                    if not is_price_in_range(p['price_float'], target_price, tolerance_pct=20.0)
                ]

                if outliers:
                    print(f"\n  PASS 2: Re-scraping {len(outliers)} outlier(s) with target price £{target_price:.2f}...")

                    for i, item in enumerate(outliers, 1):
                        print(f"  [{i}/{len(outliers)}] Re-checking {item['link'][:70]}...")
                        print(f"    Previous price: {item['price']} (outlier)")

                        # Re-scrape with target price
                        price, final_url = await extract_price_from_page(
                            page, item['url'], target_price=target_price, tolerance_pct=20.0
                        )

                        if price:
                            price_float = float(price)
                            if is_price_in_range(price_float, target_price, tolerance_pct=20.0):
                                # Update with better price
                                item['price'] = f"£{price}"
                                item['price_float'] = price_float
                                item['link'] = final_url
                                print(f"    ✓ Found better price: £{price} (in range)")
                            else:
                                print(f"    ⚠ Found £{price} but still out of range, keeping original")
                        else:
                            print(f"    ✗ No alternative price found, keeping original")

                        # Rate limiting
                        await asyncio.sleep(2)

            # Step 6: Filter out remaining outliers and prepare final results
            if target_price:
                # Remove any prices still outside the valid range
                filtered_prices = [
                    p for p in initial_prices
                    if is_price_in_range(p['price_float'], target_price, tolerance_pct=20.0)
                ]

                removed_count = len(initial_prices) - len(filtered_prices)
                if removed_count > 0:
                    print(f"\n  ✓ Removed {removed_count} uncorrectable outlier(s) from final results")

                prices_found = [
                    {'link': p['link'], 'price': p['price']}
                    for p in filtered_prices
                ]
            else:
                # No target price calculated, keep all
                prices_found = [
                    {'link': p['link'], 'price': p['price']}
                    for p in initial_prices
                ]

            # Update result
            result['prices'] = prices_found
            result['status'] = 'success' if prices_found else 'failed'
            if not prices_found:
                result['error'] = "No prices found on any pages"

            await browser.close()

    except Exception as e:
        result['error'] = str(e)
        print(f"  Error: {e}")

    # Summary
    print(f"\n{'='*80}")
    print(f"Summary: {product_name}")
    print(f"{'='*80}")
    if result['prices']:
        print(f"✓ Found {len(result['prices'])} prices:")
        for item in result['prices']:
            print(f"  {item['price']} - {item['link'][:70]}")
    else:
        print(f"✗ No prices found: {result['error']}")

    return result


async def batch_scrape_prices(products: List[str], headless: bool = True) -> List[Dict]:
    """
    Scrape prices for multiple products (sequential processing).

    Args:
        products: List of product names
        headless: Run browser in headless mode

    Returns:
        List of result dicts (one per product)
    """
    results = []

    print(f"\n{'='*80}")
    print(f"BATCH PRICE DISCOVERY")
    print(f"{'='*80}")
    print(f"Products: {len(products)}")
    print(f"Mode: {'Headless' if headless else 'Visible'}")

    for i, product_name in enumerate(products, 1):
        print(f"\n[{i}/{len(products)}] Processing: {product_name}")

        result = await scrape_prices_for_product(product_name, headless=headless)
        results.append(result)

        # Delay between products
        if i < len(products):
            print(f"\nWaiting 5 seconds before next product...")
            await asyncio.sleep(5)

    # Final summary
    print(f"\n{'='*80}")
    print(f"BATCH SUMMARY")
    print(f"{'='*80}")
    total_prices = sum(len(r['prices']) for r in results)
    successful = sum(1 for r in results if r['status'] == 'success')

    print(f"Products processed: {len(results)}")
    print(f"Successful: {successful}/{len(results)}")
    print(f"Total prices found: {total_prices}")

    return results


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Price Discovery Scraper - Find product prices across retailers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single product
  python price_scraper.py "Ninja AF101 Air Fryer"

  # Multiple products with output
  python price_scraper.py "Ninja AF101" "Tower T17190" -o prices.json

  # With visible browser
  python price_scraper.py "Philips HD9252/90" --no-headless
        """
    )

    parser.add_argument('products', nargs='+', help='Product name(s) to search for')
    parser.add_argument('--output', '-o', help='Output JSON file (optional)')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')

    args = parser.parse_args()

    # Run scraper
    if len(args.products) == 1:
        result = asyncio.run(scrape_prices_for_product(args.products[0], headless=not args.no_headless))
        results = [result]
    else:
        results = asyncio.run(batch_scrape_prices(args.products, headless=not args.no_headless))

    # Save output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Results saved to: {output_path}")
