#!/usr/bin/env python3
"""
Currys Sentiment Scraper
Extracts rating, count, and review samples for sentiment analysis
"""
import asyncio
import sys
from pathlib import Path
from typing import Dict
from playwright.async_api import async_playwright

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.reviews.sentiment import SentimentAnalyzer, format_reviews_for_analysis, create_sentiment_result, get_empty_result


async def get_sentiment_analysis(product_url: str) -> Dict:
    """
    Scrape Currys reviews and return sentiment analysis with rating/count.

    Args:
        product_url: Currys product page URL

    Returns:
        Dict with rating, count, summary, pros, and cons
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Currys detects headless mode
        page = await browser.new_page()

        try:
            await page.goto(product_url, wait_until='networkidle', timeout=30000)

            # Handle cookie banner
            try:
                cookie_btn = await page.query_selector('#onetrust-accept-btn-handler')
                if cookie_btn:
                    await cookie_btn.click()
                    await page.wait_for_timeout(500)
            except:
                pass

            # Extract from JSON-LD schema
            data = await page.evaluate('''
                () => {
                    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
                    for (const script of scripts) {
                        try {
                            const data = JSON.parse(script.textContent);
                            if (data.aggregateRating && data.review) {
                                return {
                                    rating: data.aggregateRating.ratingValue + '/5',
                                    count: parseInt(data.aggregateRating.reviewCount),
                                    reviews: data.review.map(r => r.reviewBody).filter(text => text && text.length > 10)
                                };
                            }
                        } catch (e) {}
                    }
                    return null;
                }
            ''')

            await browser.close()

            if not data or not data.get('reviews'):
                return get_empty_result(
                    rating=data.get('rating') if data else None,
                    count=data.get('count') if data else 0
                )

            # Format and analyze reviews
            review_dicts = format_reviews_for_analysis(data['reviews'])
            analyzer = SentimentAnalyzer()
            sentiment = await analyzer.analyze_reviews(review_dicts, "Product", "product")

            # Return complete data
            return create_sentiment_result(
                sentiment,
                rating=data['rating'],
                count=data['count']
            )

        except Exception as e:
            print(f"Error in Currys sentiment scraper: {str(e)[:100]}")
            await browser.close()
            return get_empty_result()


async def main():
    """Example usage"""
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sentiment_scraper.py <currys_product_url>")
        sys.exit(1)

    product_url = sys.argv[1]
    result = await get_sentiment_analysis(product_url)

    # Pretty print the result
    print("\n" + "="*60)
    print("CURRYS REVIEW ANALYSIS")
    print("="*60)

    print(f"\nRATING: {result.get('rating', 'N/A')}")
    print(f"REVIEW COUNT: {result.get('count', 0)}")

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
