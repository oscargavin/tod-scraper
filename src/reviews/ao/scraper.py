#!/usr/bin/env python3
"""AO.com Review Scraper"""
import asyncio
from playwright.async_api import async_playwright


async def extract_review(url: str, page=None) -> dict:
    """
    Extract review rating from AO.com product page
    
    Args:
        url: Product page URL
        page: Optional Playwright page instance (for reuse in parallel processing)
    """
    # If page provided, use it directly (parallel mode)
    if page:
        await page.goto(url, wait_until='domcontentloaded')
        
        # Try to wait for rating, but don't fail if not found
        try:
            await page.wait_for_selector('.rating', state='visible', timeout=5000)
        except:
            return None  # No reviews on this product
        
        return await page.evaluate('''
            () => {
                const rating = document.querySelector('.rating');
                if (!rating) return null;
                
                const score = rating.querySelector('.score')?.textContent?.trim();
                const count = rating.querySelector('[itemprop="reviewCount"]')?.textContent;
                const stars = rating.querySelector('[class*="ratingSprite_"]')?.className
                    .match(/ratingSprite_([\\d-]+)/)?.[1]?.replace('-', '.');
                
                return { score, stars, count: count ? +count : null };
            }
        ''')
    
    # Otherwise create browser instance (standalone mode)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded')
            
            # Try to wait for rating, but don't fail if not found
            try:
                await page.wait_for_selector('.rating', state='visible', timeout=5000)
            except:
                return None  # No reviews on this product
            
            return await page.evaluate('''
                () => {
                    const rating = document.querySelector('.rating');
                    if (!rating) return null;
                    
                    const score = rating.querySelector('.score')?.textContent?.trim();
                    const count = rating.querySelector('[itemprop="reviewCount"]')?.textContent;
                    const stars = rating.querySelector('[class*="ratingSprite_"]')?.className
                        .match(/ratingSprite_([\\d-]+)/)?.[1]?.replace('-', '.');
                    
                    return { score, stars, count: count ? +count : null };
                }
            ''')
        finally:
            await browser.close()


if __name__ == "__main__":
    url = "https://ao.com/product/hs643d60wuk-hisense-full-size-dishwasher-white-94675-23.aspx"
    result = asyncio.run(extract_review(url))
    
    if result:
        print(f"Score: {result['score']}")
        print(f"Stars: {result['stars']}")
        print(f"Count: {result['count']}")