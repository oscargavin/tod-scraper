#!/usr/bin/env python3
"""
Currys Review Scraper
Extracts rating and count from Currys product pages via JSON-LD schema
"""
import asyncio
from playwright.async_api import async_playwright


async def extract_review(product_url: str):
    """
    Extract review rating and count from Currys product page.

    Currys stores review data in JSON-LD schema, making extraction simple.

    Args:
        product_url: Currys product page URL

    Returns:
        Dict with 'score' (str like "4.5/5") and 'count' (int)
        Returns None if no reviews found
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
            review_data = await page.evaluate('''
                () => {
                    // Find JSON-LD script with aggregateRating
                    const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
                    for (const script of scripts) {
                        try {
                            const data = JSON.parse(script.textContent);
                            if (data.aggregateRating) {
                                return {
                                    score: data.aggregateRating.ratingValue + '/5',
                                    count: parseInt(data.aggregateRating.reviewCount)
                                };
                            }
                        } catch (e) {}
                    }
                    return null;
                }
            ''')

            return review_data

        except Exception as e:
            print(f"Error extracting Currys reviews: {str(e)[:100]}")
            return None
        finally:
            await browser.close()


async def main():
    """Test the scraper"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python scraper.py <currys_product_url>")
        sys.exit(1)

    url = sys.argv[1]
    result = await extract_review(url)

    if result:
        print(f"Rating: {result['score']}")
        print(f"Count: {result['count']}")
    else:
        print("No reviews found")


if __name__ == '__main__':
    asyncio.run(main())
