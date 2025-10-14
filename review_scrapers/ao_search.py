#!/usr/bin/env python3
"""AO.com Search and Review Extraction"""
import asyncio
import argparse
import urllib.parse
from playwright.async_api import async_playwright
from .ao_scraper import extract_review


async def search_and_extract(search_query: str, target_product: str = None, select_index: int = 0, silent: bool = False, page=None):
    """
    Search for products and extract reviews - returns data instead of printing
    
    Args:
        search_query: Simplified search term
        target_product: Specific product to match
        select_index: Index of product to select
        silent: Whether to suppress print output
        page: Optional Playwright page instance (for reuse in parallel processing)
    
    Returns:
        dict with keys: success, product_name, ao_url, reviews (score, stars, count), error
    """
    # Build search URL
    encoded_query = urllib.parse.quote(search_query)
    search_url = f"https://ao.com/l/search/101/99/?search={encoded_query}"
    
    result = {
        'success': False,
        'search_query': search_query,
        'target': target_product,
        'product_name': None,
        'ao_url': None,
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
            print(f"Searching AO.com for: {search_query}")
        
        # Use networkidle to wait for all network activity to finish (including redirects)
        await page.goto(search_url, wait_until='networkidle', timeout=15000)
        
        # Check if we were redirected to a product page instead of search results
        current_url = page.url
        if '/product/' in current_url:
            # We've been redirected directly to a product page
            if not silent:
                print(f"  → Redirected to product page")
            
            # Get product name from the page
            try:
                product_name = await page.evaluate('''
                    () => {
                        const h1 = document.querySelector('h1');
                        return h1 ? h1.textContent.trim() : 'Unknown Product';
                    }
                ''')
                result['product_name'] = product_name
                result['ao_url'] = current_url
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
            await page.wait_for_selector('h2[itemprop="name"]', timeout=5000)
        except:
            result['error'] = "No products found"
            return result
        
        # Extract product listings
        products = await page.evaluate('''
            () => {
                const nameElements = document.querySelectorAll('h2[itemprop="name"]');
                return Array.from(nameElements).slice(0, 10).map((nameEl, index) => {
                    let container = nameEl.closest('li') || nameEl.closest('div[itemscope]') || nameEl.parentElement;
                    const name = nameEl?.textContent?.trim() || 'Unknown Product';
                    const linkEl = container?.querySelector('a[href*="/product/"]') || 
                                  container?.querySelector('a[itemprop="url"]');
                    const href = linkEl?.href || null;
                    return { index, name, href };
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
        result['ao_url'] = selected['href']
            
    finally:
        if own_page and browser:
            await browser.close()
            await p.stop()
    
    # Extract reviews from selected product
    review_data = await extract_review(result['ao_url'], page if not own_page else None)
    
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


async def search_products(search_query: str, target_product: str = None, select_index: int = 0):
    """
    Search for products on AO.com and extract review from selected result
    
    Args:
        search_query: Simplified search term (e.g. "ninja luxe cafe")
        target_product: Specific product to match (e.g. "ES601UK") - optional
        select_index: Index of product to select from results (0-based) - used if target_product not specified
    """
    # Build search URL
    encoded_query = urllib.parse.quote(search_query)
    search_url = f"https://ao.com/l/search/101/99/?search={encoded_query}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            print(f"Searching for: {search_query}")
            print(f"URL: {search_url}")
            
            # Navigate to search page
            await page.goto(search_url, wait_until='networkidle', timeout=15000)
            
            # Wait for products to load
            try:
                await page.wait_for_selector('h2[itemprop="name"]', timeout=5000)
            except:
                pass  # Will be handled by checking products list
            
            # Extract product listings - use h2 elements as base since they exist
            products = await page.evaluate('''
                () => {
                    // Find all h2 product names first
                    const nameElements = document.querySelectorAll('h2[itemprop="name"]');
                    
                    return Array.from(nameElements).slice(0, 10).map((nameEl, index) => {
                        // Get the parent container (should be the product card)
                        let container = nameEl.closest('li') || nameEl.closest('div[itemscope]') || nameEl.parentElement;
                        
                        const name = nameEl?.textContent?.trim() || 'Unknown Product';
                        
                        // Get product link - search within container
                        const linkEl = container?.querySelector('a[href*="/product/"]') || 
                                      container?.querySelector('a[itemprop="url"]');
                        const href = linkEl?.href || null;
                        
                        // Get price
                        const priceEl = container?.querySelector('[data-testid="price-now"]') ||
                                       container?.querySelector('.main-price');
                        const price = priceEl?.textContent?.trim() || 'Price not found';
                        
                        // Get review info
                        const ratingEl = container?.querySelector('[itemprop="aggregateRating"]');
                        let reviews = null;
                        if (ratingEl) {
                            const ratingValue = ratingEl.querySelector('[itemprop="ratingValue"]')?.content;
                            const ratingCount = ratingEl.querySelector('[itemprop="ratingCount"]')?.content;
                            reviews = { rating: ratingValue, count: ratingCount };
                        }
                        
                        return { index, name, href, price, reviews };
                    });
                }
            ''')
            
            if not products:
                print("No products found in search results")
                return None
            
            # Display found products
            print(f"\nFound {len(products)} products:")
            for p in products:
                review_str = f" ({p['reviews']['rating']}★, {p['reviews']['count']} reviews)" if p['reviews'] else ""
                print(f"  [{p['index']}] {p['name'][:60]}... - {p['price']}{review_str}")
            
            # Select product based on target match or index
            selected = None
            
            if target_product:
                # Try to find product matching the target string
                print(f"\nSearching for product containing: {target_product}")
                
                # Normalize target for matching
                target_normalized = target_product.upper().replace(' ', '').replace('-', '')
                
                for p in products:
                    # Check if target appears in product name
                    name_normalized = p['name'].upper().replace(' ', '').replace('-', '')
                    if target_normalized in name_normalized:
                        selected = p
                        print(f"✓ Found match: {p['name']}")
                        break
                
                if not selected:
                    print(f"⚠️  No product found containing '{target_product}', using index {select_index}")
                    selected = products[select_index] if select_index < len(products) else products[0]
            else:
                # Use index selection
                if select_index >= len(products):
                    print(f"\n⚠️  Index {select_index} out of range, selecting first product")
                    select_index = 0
                selected = products[select_index]
            
            print(f"\n✓ Selected: {selected['name']}")
            
            if not selected['href']:
                print("❌ No product URL found for selected item")
                return None
            
            print(f"Product URL: {selected['href']}")
            
        finally:
            await browser.close()
    
    # Extract reviews from selected product
    print("\nExtracting reviews...")
    review_data = await extract_review(selected['href'])
    
    if review_data:
        print(f"\n📊 Review Data:")
        print(f"  Score: {review_data.get('score', 'N/A')}")
        print(f"  Stars: {review_data.get('stars', 'N/A')}")
        print(f"  Count: {review_data.get('count', 'N/A')}")
    else:
        print("❌ No reviews found on product page")
    
    return review_data


async def main():
    parser = argparse.ArgumentParser(
        description='Search AO.com for products and extract reviews',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search broadly and find specific model
  python ao_search.py "ninja luxe cafe" --target "ES601UK"
  
  # Search for Samsung Galaxy Watch
  python ao_search.py "Samsung Galaxy Watch Ultra"
  
  # Search and select second result (index 1)
  python ao_search.py "iPhone 15" --index 1
  
  # Search for washing machine with specific model
  python ao_search.py "bosch washing" --target "WGG254Z0GB"
        """
    )
    
    parser.add_argument('search_query', 
                       help='Product to search for (simplified search term)')
    parser.add_argument('--target', '-t',
                       help='Specific product model/code to match (e.g. ES601UK)')
    parser.add_argument('--index', '-i',
                       type=int, default=0,
                       help='Index of product to select if target not found (0-based, default: 0)')
    
    args = parser.parse_args()
    
    await search_products(args.search_query, args.target, args.index)


if __name__ == "__main__":
    asyncio.run(main())