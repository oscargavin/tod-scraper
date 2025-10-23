#!/usr/bin/env python3
"""
Boots Streamlined Sentiment Scraper
Outputs only summary, pros, and cons from review analysis

NOTE: Boots uses BazaarVoice with Shadow DOM for reviews.
Reviews are NOT in the regular DOM - they're encapsulated in a Web Component.
We access them via element.shadowRoot property.
"""
import asyncio
from typing import Dict, List
from playwright.async_api import async_playwright, Browser
import re
from src.reviews.sentiment import SentimentAnalyzer, format_reviews_for_analysis, create_sentiment_result, get_empty_result


async def handle_cookie_banner(page) -> None:
    """Handle cookie consent banner"""
    try:
        btn = await page.query_selector('#onetrust-accept-btn-handler')
        if btn and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(500)
    except:
        pass


async def click_show_more_until_done(page) -> int:
    """Click Show more button in Shadow DOM until all reviews loaded"""
    clicks = 0
    max_clicks = 10

    while clicks < max_clicks:
        # Try to click Show more button in shadow DOM
        has_more = await page.evaluate('''
            () => {
                const allElements = document.querySelectorAll('*');
                for (const el of allElements) {
                    if (el.shadowRoot) {
                        const shadowText = el.shadowRoot.textContent || '';
                        if (shadowText.includes('Rating snapshot')) {
                            const buttons = el.shadowRoot.querySelectorAll('button');
                            for (const btn of buttons) {
                                if (btn.textContent.includes('Show more') && !btn.disabled && btn.offsetHeight > 0) {
                                    btn.click();
                    return true;
                                }
                            }
                        }
                    }
                }
                return false;
            }
        ''')

        if not has_more:
            break

        clicks += 1
        await page.wait_for_timeout(1500)

    return clicks


def parse_reviews_from_shadow_text(full_text: str) -> List[str]:
    """
    Parse review texts from Shadow DOM content.

    Reviews are separated by "X out of 5 stars." pattern.
    Extract just the review text for sentiment analysis.
    """
    review_texts = []

    # Split by star rating pattern
    parts = re.split(r'\d+\s+out of 5 stars\.', full_text)

    # Skip first part (rating summary), process rest
    for content in parts[1:]:
        # Extract date to find where review starts
        date_match = re.search(
            r'(a day ago|a week ago|a month ago|\d+ days? ago|\d+ weeks? ago|\d+ months? ago|today|yesterday)',
            content,
            re.IGNORECASE
        )

        if not date_match:
            continue

        # Review text is after the date
        after_date = content[date_match.end():].strip()

        # Extract text before "Yes/No, I would recommend"
        recommend_match = re.search(r'(Yes|No), I would', after_date)
        if recommend_match:
            review_text = after_date[:recommend_match.start()].strip()
        else:
            # Or before "Originally posted"
            posted_match = re.search(r'Originally posted', after_date)
            if posted_match:
                review_text = after_date[:posted_match.start()].strip()
            else:
                review_text = after_date[:200].strip()

        # Clean and validate
        review_text = review_text.strip('.,; ')
        if review_text and len(review_text) > 10:
            review_texts.append(review_text)

    return review_texts


async def scrape_all_reviews(product_url: str) -> List[str]:
    """
    Scrape ALL reviews from Boots product page.

    Reviews are in Shadow DOM, so we:
    1. Access element.shadowRoot
    2. Click "Show more" to load all reviews
    3. Parse the shadow DOM text content
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(product_url, wait_until='networkidle', timeout=30000)
            await handle_cookie_banner(page)

            # Scroll to reviews section to trigger loading
            for i in range(10):
                await page.evaluate(f'window.scrollBy(0, 500)')
                await page.wait_for_timeout(100)

            # Wait for Shadow DOM to populate
            await page.wait_for_timeout(3000)

            # Click Show more to load all reviews
            await click_show_more_until_done(page)

            # Extract full shadow DOM text
            shadow_text = await page.evaluate('''
                () => {
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.shadowRoot) {
                            const text = el.shadowRoot.textContent || '';
                            if (text.includes('Rating snapshot')) {
                                return text;
                            }
                        }
                    }
                    return '';
                }
            ''')

            if not shadow_text:
                return []

            # Parse reviews from shadow text
            review_texts = parse_reviews_from_shadow_text(shadow_text)
            return review_texts

        except Exception as e:
            print(f"  Error scraping reviews: {str(e)[:100]}")
            return []
        finally:
            await browser.close()


async def get_sentiment_analysis(product_url: str, max_pages: int = None) -> Dict:
    """
    Scrape Boots reviews from Shadow DOM and return sentiment analysis
    with rating and count data.

    Note: max_pages parameter is ignored for Boots since we load all reviews
    from the Shadow DOM by clicking "Show more".

    Returns:
        Dict with rating, count, summary, pros, and cons
    """
    from src.reviews.boots.scraper import extract_review

    print("Scraping Boots reviews from Shadow DOM...")

    # First get rating and count from summary
    rating_data = await extract_review(product_url)

    # Then scrape all review text from Shadow DOM
    all_reviews = await scrape_all_reviews(product_url)

    print(f"Found {len(all_reviews)} reviews")

    if not all_reviews:
        return get_empty_result(
            rating=rating_data.get('score') if rating_data else None,
            count=rating_data.get('count') if rating_data else 0
        )

    # Analyze sentiment
    print("Analyzing sentiment...")

    # Convert to format for analyzer using shared utility
    review_dicts = format_reviews_for_analysis(all_reviews)

    analyzer = SentimentAnalyzer()
    sentiment = await analyzer.analyze_reviews(review_dicts, "Product", "product")

    # Return complete data using shared utility
    return create_sentiment_result(
        sentiment,
        rating=rating_data.get('score') if rating_data else None,
        count=rating_data.get('count') if rating_data else 0
    )


async def main():
    """Example usage"""
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sentiment_scraper.py <boots_product_url>")
        print("Example: python sentiment_scraper.py https://www.boots.com/product-url")
        sys.exit(1)

    product_url = sys.argv[1]

    result = await get_sentiment_analysis(product_url)

    # Pretty print the result
    print("\n" + "="*60)
    print("BOOTS REVIEW ANALYSIS")
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
