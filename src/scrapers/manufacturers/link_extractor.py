"""Link extraction utility for manufacturer spec scraping.

This module handles deterministic search result extraction from DuckDuckGo,
prioritizing manufacturer sites over retailers with strong bot detection.
"""

from typing import List, Dict, Tuple
from playwright.sync_api import Page, sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


# EXCLUDED DOMAINS - Sites we scrape elsewhere (never select for Gemini)
EXCLUDED_DOMAINS = [
    # Which.co.uk (scraped in Phase 2)
    'which.co.uk', 'which.digidip.net',

    # Our retailer scrapers (scraped in Phase 3)
    'ao.com', 'ao.co.uk',
    'amazon.co.uk', 'amazon.com',
    'appliancecentre.co.uk',
    'appliancesdirect.co.uk',
    'boots.com', 'boots.co.uk',
    'markselectrical.co.uk', 'visit.markselectrical.co.uk',
    'currys.co.uk', 'currys.com',
    'johnlewis.com', 'johnlewis.co.uk',
    'argos.co.uk', 'argos.com',
    'very.co.uk',

    # Other major retailers (high bot detection, we don't scrape these)
    'tesco', 'asda', 'sainsburys', 'ebay',
]

# Manufacturer domains (prioritize these)
MANUFACTURER_DOMAINS = [
    'ninja', 'philips', 'tefal', 'tower', 'cuisinart', 'salter',
    'cosori', 'breville', 'delonghi', 'russell-hobbs', 'russellhobbs',
    'swan', 'morphy', 'morphyrichards', 'lakeland', 'xiaomi',
    'instant', 'gourmia', 'proscenic', 'dreo', 'chefman',
    'klarstein', 'princess', 'sage', 'sageappliances', 'tefal',
    'airfryer', 'pro-breeze', 'probreeze', 'vonshef', 'aigostar',
]

# Review/comparison sites (use as fallback if no manufacturer found)
REVIEW_SITES = [
    'trustpilot', 'reevoo', 'reviewed.com',
    'goodhousekeeping', 'techradar', 'tomsguide', 'cnet',
]


def categorize_url(url: str) -> Tuple[str, int]:
    """Categorize URL and assign priority score.

    Args:
        url: URL to categorize

    Returns:
        Tuple of (category, priority) where priority is:
        - 0: Excluded (Which.co.uk or our retailers - NEVER select)
        - 1: Manufacturer site (highest priority)
        - 2: Review/comparison sites (fallback)
        - 3: Unknown/other sites
    """
    url_lower = url.lower()

    # Check excluded domains first (Which.co.uk + our retailers)
    for domain in EXCLUDED_DOMAINS:
        if domain in url_lower:
            return ("excluded", 0)

    # Check manufacturer domains
    for domain in MANUFACTURER_DOMAINS:
        if domain in url_lower:
            return ("manufacturer", 1)

    # Check review/comparison sites
    for site in REVIEW_SITES:
        if site in url_lower:
            return ("review_site", 2)

    return ("unknown", 3)


def extract_search_links(page: Page, product_name: str, max_links: int = 20) -> List[Dict[str, str]]:
    """Extract links from DuckDuckGo search results.

    Args:
        page: Playwright page instance
        product_name: Product to search for
        max_links: Maximum number of links to extract

    Returns:
        List of dicts with keys: url, title, category, priority, price, retailer_name
    """
    print(f"\n{'='*80}")
    print(f"Searching: {product_name}")
    print(f"{'='*80}")

    try:
        # Navigate to DuckDuckGo
        page.goto("https://duckduckgo.com", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)  # Increased wait

        # Search for product name + "buy" to get shopping results with prices
        search_query = f"{product_name} buy"

        # Try to find and fill search box
        try:
            page.fill('input[name="q"]', search_query, timeout=5000)
            page.press('input[name="q"]', "Enter")
        except Exception as e:
            print(f"  Warning: Could not fill search box - {e}")
            # Try alternative selector
            page.fill('input[type="text"]', search_query)
            page.press('input[type="text"]', "Enter")

        page.wait_for_load_state("domcontentloaded", timeout=15000)
        time.sleep(3)  # Increased wait for results

        # Extract all result links - try multiple selectors
        result_elements = []

        # Try primary selector for results
        result_elements = page.query_selector_all('[data-testid="result"]')

        # If no results, try alternative selectors
        if not result_elements:
            print(f"  Trying alternative selectors...")
            result_elements = page.query_selector_all('article')

        if not result_elements:
            result_elements = page.query_selector_all('.result')

        print(f"  Found {len(result_elements)} result elements")

        extracted_links = []

        for element in result_elements[:max_links]:
            try:
                # Extract link
                link = element.query_selector('a[data-testid="result-title-a"]') or \
                       element.query_selector('h2 a') or \
                       element.query_selector('a[href^="http"]')

                if not link:
                    continue

                url = link.get_attribute('href')
                title = link.inner_text() or link.get_attribute('aria-label') or ''

                if not url or not url.startswith('http'):
                    continue

                category, priority = categorize_url(url)

                # Skip excluded domains (priority 0)
                if priority == 0:
                    print(f"  ⛔ Excluded: {url[:80]}")
                    continue

                # Try to extract price from the result snippet
                price = None
                try:
                    # Get the full text of the result element
                    element_text = element.inner_text()

                    # Look for price patterns (£X.XX, £X, £X,XXX.XX)
                    import re
                    price_match = re.search(r'£\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', element_text)
                    if price_match:
                        price = f"£{price_match.group(1)}"
                except Exception:
                    pass

                # Extract retailer name from domain
                retailer_name = None
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc
                    # Remove www. and extract main domain name
                    domain = domain.replace('www.', '')
                    retailer_name = domain.split('.')[0].title()
                except Exception:
                    pass

                extracted_links.append({
                    'url': url,
                    'title': title,
                    'category': category,
                    'priority': priority,
                    'price': price,
                    'retailer_name': retailer_name
                })

                if price:
                    print(f"  ✓ {retailer_name}: {price} - {url[:60]}")
                else:
                    print(f"  ✓ {retailer_name}: No price - {url[:60]}")

            except Exception as e:
                print(f"  Warning: Failed to extract link - {e}")
                continue

        print(f"Extracted {len(extracted_links)} valid links (excluded Which.co.uk and retailers)")

    except Exception as e:
        print(f"  Error during search: {e}")
        extracted_links = []

    return extracted_links


def select_best_links(links: List[Dict[str, str]], count: int = 3) -> List[Dict[str, str]]:
    """Select the best links with prioritization.

    Priority (excluded domains already filtered out):
    1. Manufacturer sites (priority 1)
    2. Review/comparison sites (priority 2)
    3. Unknown sites (priority 3)

    Args:
        links: List of link dicts from extract_search_links
        count: Number of links to return (default 3)

    Returns:
        List of best links sorted by priority
    """
    # Sort by priority (1 = best, 0 = excluded and already filtered)
    sorted_links = sorted(links, key=lambda x: x['priority'])

    selected = []

    # Get first manufacturer link
    manufacturer_links = [l for l in sorted_links if l['priority'] == 1]
    if manufacturer_links:
        selected.append(manufacturer_links[0])
        print(f"  ✅ Manufacturer: {manufacturer_links[0]['url'][:80]}")

    # Get review/comparison sites
    review_links = [l for l in sorted_links if l['priority'] == 2 and l not in selected]
    for link in review_links:
        if len(selected) >= count:
            break
        selected.append(link)
        print(f"  🔍 Review site: {link['url'][:80]}")

    # Get unknown sites as last resort
    if len(selected) < count:
        unknown_links = [l for l in sorted_links if l['priority'] == 3 and l not in selected]
        for link in unknown_links[:count - len(selected)]:
            selected.append(link)
            print(f"  🌐 Unknown: {link['url'][:80]}")

    return selected[:count]


def get_prioritized_links(page: Page, product_name: str, count: int = 3) -> List[str]:
    """Main function to get prioritized manufacturer links.

    Excludes Which.co.uk and all retailer sites we scrape elsewhere.

    Args:
        page: Playwright page instance
        product_name: Product to search for
        count: Number of links to return

    Returns:
        List of URLs prioritized by manufacturer > review sites > unknown
        (Which.co.uk and retailer domains are completely excluded)
    """
    all_links = extract_search_links(page, product_name)
    best_links = select_best_links(all_links, count)

    return [link['url'] for link in best_links]


def get_retailer_links_with_prices(page: Page, product_name: str, count: int = 5) -> List[Dict[str, str]]:
    """Get retailer links with prices for a product from search results.

    Args:
        page: Playwright page instance
        product_name: Product to search for
        count: Maximum number of links to return (default 5)

    Returns:
        List of dicts in retailerLinks format:
        [
            {
                "name": "Currys",
                "price": "£299.99",
                "url": "https://currys.co.uk/..."
            },
            ...
        ]
    """
    all_links = extract_search_links(page, product_name, max_links=count * 2)

    # Convert to retailerLinks format
    retailer_links = []
    for link_data in all_links[:count]:
        if link_data.get('url'):
            retailer_links.append({
                'name': link_data.get('retailer_name', 'Unknown'),
                'price': link_data.get('price'),
                'url': link_data['url']
            })

    return retailer_links


def batch_extract_links(products: List[Dict], workers: int = 5, headless: bool = True, links_per_product: int = 3) -> Dict[str, List[str]]:
    """Extract links for multiple products in parallel (batch operation).

    This is the main entry point for the link extraction system.
    Runs headless Playwright sessions in parallel to quickly gather
    manufacturer links for products that need Gemini enrichment.

    Args:
        products: List of product dicts (must have 'name' key)
        workers: Number of parallel Playwright sessions (default 5)
        headless: Run browsers headless (default True for production)
        links_per_product: Number of URLs to extract per product (default 3)

    Returns:
        Dict mapping product name to list of URLs:
        {
            "Ninja Crispi FN101UKGY": ["https://ninja.com/...", "https://...", ...],
            "Tower T17190": ["https://tower.com/...", ...],
            ...
        }

    Example:
        >>> products = [{"name": "Ninja AF101"}, {"name": "Tower T17190"}]
        >>> link_map = batch_extract_links(products, workers=5, headless=True)
        >>> link_map["Ninja AF101"]
        ["https://ninjakitchen.co.uk/...", "https://lakeland.co.uk/...", ...]
    """
    print(f"\n{'='*80}")
    print(f"BATCH LINK EXTRACTION")
    print(f"{'='*80}")
    print(f"Products: {len(products)}")
    print(f"Workers: {workers}")
    print(f"Mode: {'Headless' if headless else 'Visible'}")
    print(f"Links per product: {links_per_product}")

    link_map = {}
    product_names = [p.get('name', 'Unknown') for p in products]

    def link_extraction_worker(worker_id: int, product_chunk: List[str]) -> Dict[str, List[str]]:
        """Worker function that processes a chunk of products."""
        worker_results = {}

        # Create Playwright session for this worker with full stealth
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-GB",
            timezone_id="Europe/London",
            extra_http_headers={
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        )
        page = context.new_page()

        # Hide automation
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            for i, product_name in enumerate(product_chunk, 1):
                print(f"Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}")
                try:
                    urls = get_prioritized_links(page, product_name, count=links_per_product)
                    worker_results[product_name] = urls
                    print(f"Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name} → {len(urls)} links ✓")
                except Exception as e:
                    print(f"Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name} → Error: {e}")
                    worker_results[product_name] = []

        finally:
            browser.close()
            playwright.stop()

        return worker_results

    # Split products among workers
    chunk_size = len(product_names) // workers
    remainder = len(product_names) % workers

    chunks = []
    start = 0
    for i in range(workers):
        size = chunk_size + (1 if i < remainder else 0)
        chunks.append(product_names[start:start + size])
        start += size

    # Run workers in parallel
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(link_extraction_worker, i+1, chunk)
            for i, chunk in enumerate(chunks)
        ]

        # Collect results
        for future in as_completed(futures):
            try:
                worker_results = future.result()
                link_map.update(worker_results)
            except Exception as e:
                print(f"Worker error: {e}")

    # Summary
    total_with_links = sum(1 for urls in link_map.values() if urls)
    total_links = sum(len(urls) for urls in link_map.values())

    print(f"\n{'='*80}")
    print(f"LINK EXTRACTION COMPLETE")
    print(f"{'='*80}")
    print(f"Products processed: {len(link_map)}/{len(products)}")
    print(f"Products with links: {total_with_links}")
    print(f"Total links extracted: {total_links}")
    print(f"Average links per product: {total_links/len(link_map) if link_map else 0:.1f}")

    return link_map
