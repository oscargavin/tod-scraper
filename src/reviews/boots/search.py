#!/usr/bin/env python3
"""Boots Search and Review Extraction"""
import asyncio
import argparse
import urllib.parse
from playwright.async_api import async_playwright
from src.reviews.boots.scraper import extract_review


async def search_and_extract(search_query: str, target_product: str = None, select_index: int = 0, silent: bool = False, page=None):
    """
    Search for products on Boots and extract reviews - returns data instead of printing

    Args:
        search_query: Simplified search term
        target_product: Specific product to match
        select_index: Index of product to select
        silent: Whether to suppress print output
        page: Optional Playwright page instance (for reuse in parallel processing)

    Returns:
        dict with keys: success, product_name, boots_url, reviews (score, stars, count), error
    """
    # Build search URL for Boots
    encoded_query = urllib.parse.quote(search_query)
    search_url = f"https://www.boots.com/search?text={encoded_query}"

    result = {
        'success': False,
        'search_query': search_query,
        'target': target_product,
        'product_name': None,
        'boots_url': None,
        'reviews': None,
        'error': None
    }

    # If page provided, use it directly (parallel mode)
    if page:
        own_page = False
        browser = None
        p = None
    else:
        # Create browser instance (standalone mode)
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        own_page = True

    try:
        if not silent:
            print(f"Searching Boots for: {search_query}")

        # Navigate to search page
        await page.goto(search_url, wait_until='networkidle', timeout=15000)

        # Check if we were redirected to a product page
        current_url = page.url
        if '/p/' in current_url or '/products/' in current_url:
            # We've been redirected directly to a product page
            if not silent:
                print(f"  → Redirected to product page")

            # Get product name from the page
            try:
                product_name = await page.evaluate('''
                    () => {
                        const h1 = document.querySelector('h1') ||
                                   document.querySelector('[itemprop="name"]') ||
                                   document.querySelector('.product-name');
                        return h1 ? h1.textContent.trim() : 'Unknown Product';
                    }
                ''')
                result['product_name'] = product_name
                result['boots_url'] = current_url
                # Skip directly to review extraction
                if own_page:
                    await browser.close()
                    await p.stop()
                review_data = await extract_review(current_url, page if not own_page else None)
                if review_data:
                    result['reviews'] = {
                        'score': review_data.get('score'),
                        'stars': review_data.get('stars'),
                        'count': review_data.get('count')
                    }
                    result['success'] = True
                else:
                    result['error'] = "No reviews found on product page"
                return result
            except Exception as e:
                result['error'] = f"Error on product page: {str(e)}"
                return result

        # Otherwise, wait for search results to load
        try:
            await page.wait_for_selector('[class*="product"], [data-product], .product-grid__item', timeout=5000)
        except:
            result['error'] = "No products found"
            return result

        # Extract product listings
        products = await page.evaluate('''
            () => {
                // Try multiple selector patterns for Boots
                const productCards = document.querySelectorAll('[class*="product-grid__item"], [class*="product-card"], [data-product]') ||
                                    document.querySelectorAll('.product, [itemtype*="Product"]');

                return Array.from(productCards).slice(0, 10).map((card, index) => {
                    // Get name
                    const nameEl = card.querySelector('h3, h2, [class*="product-name"], [itemprop="name"]');
                    const name = nameEl?.textContent?.trim() || 'Unknown Product';

                    // Get link
                    const linkEl = card.querySelector('a[href*="/p/"], a[href*="/products/"]') ||
                                  card.querySelector('a');
                    const href = linkEl?.href || null;

                    // Get price
                    const priceEl = card.querySelector('[class*="price"], [itemprop="price"]');
                    const price = priceEl?.textContent?.trim() || 'Price not found';

                    return { index, name, href, price };
                });
            }
        ''')

        if not products:
            result['error'] = "No products found in search results"
            return result

        # Select product based on target match or index
        selected = None

        if target_product:
            # Normalize target for matching
            target_normalized = target_product.upper().replace(' ', '').replace('-', '')

            for p in products:
                name_normalized = p['name'].upper().replace(' ', '').replace('-', '')
                if target_normalized in name_normalized:
                    selected = p
                    break

            if not selected and products:
                selected = products[0]  # Default to first if no match
        else:
            selected = products[select_index] if select_index < len(products) else products[0]

        if not selected or not selected['href']:
            result['error'] = "No valid product URL found"
            return result

        result['product_name'] = selected['name']
        result['boots_url'] = selected['href']

    finally:
        if own_page and browser:
            await browser.close()
            await p.stop()

    # Extract reviews from selected product
    review_data = await extract_review(result['boots_url'], page if not own_page else None)

    if review_data:
        result['reviews'] = {
            'score': review_data.get('score'),
            'stars': review_data.get('stars'),
            'count': review_data.get('count')
        }
        result['success'] = True
    else:
        result['error'] = "No reviews found on product page"

    return result


async def main():
    parser = argparse.ArgumentParser(
        description='Search Boots for products and extract reviews',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search broadly and find specific model
  python search.py "ninja air fryer" --target "AF180UK"

  # Search for specific product
  python search.py "Philips Air Fryer"

  # Search and select second result (index 1)
  python search.py "Tower air fryer" --index 1
        """
    )

    parser.add_argument('search_query',
                       help='Product to search for (simplified search term)')
    parser.add_argument('--target', '-t',
                       help='Specific product model/code to match')
    parser.add_argument('--index', '-i',
                       type=int, default=0,
                       help='Index of product to select if target not found (0-based, default: 0)')

    args = parser.parse_args()

    result = await search_and_extract(args.search_query, args.target, args.index)

    if result['success']:
        print(f"\n✓ Product: {result['product_name']}")
        print(f"  URL: {result['boots_url']}")
        print(f"  Score: {result['reviews']['score']}")
        print(f"  Stars: {result['reviews']['stars']}")
        print(f"  Count: {result['reviews']['count']}")
    else:
        print(f"\n✗ Error: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
