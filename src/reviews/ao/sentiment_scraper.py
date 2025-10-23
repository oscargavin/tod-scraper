#!/usr/bin/env python3
"""
AO.com Streamlined Sentiment Scraper
Outputs only summary, pros, and cons from review analysis
"""
import asyncio
from typing import Dict, List
from playwright.async_api import async_playwright, Browser
from urllib.parse import urlparse
import time
from src.reviews.sentiment import SentimentAnalyzer, format_reviews_for_analysis, get_empty_result


def transform_to_reviews_url(product_url: str, page_num: int = 1) -> str:
    """Transform product URL to reviews URL with page number"""
    parsed = urlparse(product_url)
    path = parsed.path
    
    if '.aspx' in path:
        path = path.split('.aspx')[0]
    
    if '/product/' in path:
        path = path.replace('/product/', '/p/reviews/')
    
    return f"{parsed.scheme}://{parsed.netloc}{path}?order=HelpfulnessDescending&page={page_num}"


async def handle_cookie_banner(page) -> None:
    """Handle cookie consent banner if present"""
    try:
        await page.wait_for_timeout(500)
        accept_button = await page.query_selector('button[id="onetrust-accept-btn-handler"]')
        if accept_button and await accept_button.is_visible():
            await accept_button.click()
            await page.wait_for_timeout(500)
    except:
        pass


async def scrape_page(browser: Browser, product_url: str, page_num: int) -> List[str]:
    """Scrape reviews from a specific page"""
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()
    
    try:
        reviews_url = transform_to_reviews_url(product_url, page_num)
        await page.goto(reviews_url, wait_until='networkidle', timeout=30000)
        
        if page_num == 1:
            await handle_cookie_banner(page)
        
        await page.wait_for_timeout(1500)
        
        # Extract review texts only
        reviews = await page.evaluate('''
            () => {
                const reviewBodies = document.querySelectorAll('[itemprop="reviewBody"]');
                return Array.from(reviewBodies).map(el => el.textContent.trim()).filter(text => text.length > 0);
            }
        ''')
        
        return reviews
        
    except:
        return []
    finally:
        await context.close()


async def get_sentiment_analysis(product_url: str, max_pages: int = 4) -> Dict:
    """
    Scrape reviews and return only sentiment analysis
    
    Returns:
        Dict with summary, pros, and cons only
    """
    print("Scraping reviews...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        try:
            # Scrape pages in parallel
            tasks = [
                scrape_page(browser, product_url, page_num)
                for page_num in range(1, max_pages + 1)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Combine all reviews
            all_reviews = []
            for page_reviews in results:
                all_reviews.extend(page_reviews)
            
            print(f"Found {len(all_reviews)} reviews")

            if not all_reviews:
                return get_empty_result()

            # Analyze sentiment
            print("Analyzing sentiment...")

            # Convert to format for analyzer using shared utility
            review_dicts = format_reviews_for_analysis(all_reviews)

            analyzer = SentimentAnalyzer()
            sentiment = await analyzer.analyze_reviews(review_dicts, "Product", "product")

            # Return only essential data
            return {
                "summary": sentiment['summary'],
                "pros": sentiment['pros'],
                "cons": sentiment['cons']
            }
            
        finally:
            await browser.close()


async def main():
    """Example usage"""
    import json
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ao_sentiment_scraper.py <product_url> [max_pages]")
        sys.exit(1)
    
    product_url = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    result = await get_sentiment_analysis(product_url, max_pages)
    
    # Pretty print the result
    print("\n" + "="*60)
    print("SENTIMENT ANALYSIS")
    print("="*60)
    
    print(f"\nSUMMARY:\n{result['summary']}")
    
    print("\nPROS:")
    for pro in result['pros']:
        print(f"  ✓ {pro}")
    
    print("\nCONS:")
    for con in result['cons']:
        print(f"  ✗ {con}")
    
    # Also output as clean JSON
    print("\n\nJSON OUTPUT:")
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())