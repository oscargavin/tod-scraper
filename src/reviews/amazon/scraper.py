#!/usr/bin/env python3
"""
Amazon Review Scraper
Extracts review summary and rating from Amazon product pages
Amazon already provides AI-generated sentiment, we just extract and reformat it
"""
import asyncio
from typing import Dict, Optional
from playwright.async_api import async_playwright


async def extract_review_data(product_url: str) -> Optional[Dict]:
    """
    Extract review rating, count, and Amazon's AI summary from product page

    Returns:
        Dict with rating, count, and amazon_summary
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        try:
            await page.goto(product_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)

            # Handle cookie banner
            try:
                accept_btn = await page.query_selector('#sp-cc-accept')
                if accept_btn:
                    await accept_btn.click()
                    await page.wait_for_timeout(500)
            except:
                pass

            # Extract review data
            review_data = await page.evaluate('''
                () => {
                    // Extract rating
                    const ratingEl = document.querySelector('[data-hook="rating-out-of-text"]');
                    const ratingText = ratingEl ? ratingEl.textContent.trim() : null;
                    const rating = ratingText ? parseFloat(ratingText.split(' ')[0]) : null;

                    // Extract count
                    const countEl = document.querySelector('#acrCustomerReviewText');
                    const countText = countEl ? countEl.textContent.trim() : null;
                    const count = countText ? parseInt(countText.replace(/[^0-9]/g, '')) : null;

                    // Extract Amazon's AI summary
                    const summaryEl = document.querySelector('[data-hook="cr-insights-widget-summary"] p');
                    const amazonSummary = summaryEl ? summaryEl.textContent.trim() : null;

                    // Extract aspect sentiments (Quality, Ease of use, etc.)
                    const aspects = [];
                    const aspectButtons = document.querySelectorAll('[data-hook="cr-insights-aspect-link"]');
                    aspectButtons.forEach(btn => {
                        const label = btn.textContent.trim();
                        aspects.push(label);
                    });

                    return {
                        rating,
                        count,
                        amazonSummary,
                        aspects
                    };
                }
            ''')

            await browser.close()

            if not review_data['rating']:
                return None

            return review_data

        except Exception as e:
            print(f"Error extracting Amazon review data: {e}")
            await browser.close()
            return None


async def main():
    """Test the scraper"""
    url = "https://www.amazon.co.uk/dp/B0CM43QN7V?th=1&psc=1"

    data = await extract_review_data(url)

    if data:
        print(f"Rating: {data['rating']}/5")
        print(f"Count: {data['count']:,} ratings")
        print(f"\nAmazon Summary:\n{data['amazonSummary']}")
        print(f"\nAspects ({len(data['aspects'])}):")
        for aspect in data['aspects']:
            print(f"  - {aspect}")
    else:
        print("Failed to extract review data")


if __name__ == '__main__':
    asyncio.run(main())
