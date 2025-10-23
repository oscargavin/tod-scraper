#!/usr/bin/env python3
"""Boots Review Scraper"""
import asyncio
from playwright.async_api import async_playwright


async def extract_review(url: str, page=None) -> dict:
    """
    Extract review rating from Boots product page

    Target selector: div[data-bv-show="rating_summary"]

    Args:
        url: Product page URL
        page: Optional Playwright page instance (for reuse in parallel processing)

    Returns:
        dict with keys: score, stars, count
        or None if no reviews found
    """
    # If page provided, use it directly (parallel mode)
    if page:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)

        # Try to wait for rating summary, but don't fail if not found
        try:
            await page.wait_for_selector('[data-bv-show="rating_summary"]', state='visible', timeout=5000)
        except:
            return None  # No reviews on this product

        return await page.evaluate('''
            () => {
                const ratingSummary = document.querySelector('[data-bv-show="rating_summary"]');
                if (!ratingSummary) return null;

                // Extract rating using schema.org itemprop (most reliable for BazaarVoice)
                const ratingValueEl = ratingSummary.querySelector('[itemprop="ratingValue"]');
                const reviewCountEl = ratingSummary.querySelector('[itemprop="reviewCount"]');

                let stars = null;
                if (ratingValueEl) {
                    // Try textContent first, then content attribute
                    stars = ratingValueEl.textContent?.trim() || ratingValueEl.getAttribute('content');
                }

                // Fallback: Try BazaarVoice specific selectors
                if (!stars) {
                    const bvRating = ratingSummary.querySelector('.bv_avgRating_component_container');
                    if (bvRating) {
                        const ratingText = bvRating.textContent?.trim();
                        const match = ratingText?.match(/([\\d.]+)/);
                        if (match) stars = match[1];
                    }
                }

                let count = null;
                if (reviewCountEl) {
                    // Try textContent first, then content attribute
                    const countText = reviewCountEl.textContent?.trim() || reviewCountEl.getAttribute('content');
                    if (countText) {
                        const countMatch = countText.match(/(\\d+)/);
                        if (countMatch) count = parseInt(countMatch[1]);
                    }
                }

                // Fallback: Try BazaarVoice count selector
                if (!count) {
                    const bvCount = ratingSummary.querySelector('.bv_numReviews_component_container');
                    if (bvCount) {
                        const countText = bvCount.textContent?.trim();
                        const match = countText?.match(/(\\d+)/);
                        if (match) count = parseInt(match[1]);
                    }
                }

                // Create score string (e.g., "4.5/5")
                const score = stars ? `${stars}/5` : null;

                return {
                    score,
                    stars: stars ? parseFloat(stars) : null,
                    count
                };
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
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Try to wait for rating summary
            try:
                await page.wait_for_selector('[data-bv-show="rating_summary"]', state='visible', timeout=5000)
            except:
                return None  # No reviews on this product

            return await page.evaluate('''
                () => {
                    const ratingSummary = document.querySelector('[data-bv-show="rating_summary"]');
                    if (!ratingSummary) return null;

                    // Extract rating using schema.org itemprop (most reliable for BazaarVoice)
                    const ratingValueEl = ratingSummary.querySelector('[itemprop="ratingValue"]');
                    const reviewCountEl = ratingSummary.querySelector('[itemprop="reviewCount"]');

                    let stars = null;
                    if (ratingValueEl) {
                        // Try textContent first, then content attribute
                        stars = ratingValueEl.textContent?.trim() || ratingValueEl.getAttribute('content');
                    }

                    // Fallback: Try BazaarVoice specific selectors
                    if (!stars) {
                        const bvRating = ratingSummary.querySelector('.bv_avgRating_component_container');
                        if (bvRating) {
                            const ratingText = bvRating.textContent?.trim();
                            const match = ratingText?.match(/([\\d.]+)/);
                            if (match) stars = match[1];
                        }
                    }

                    let count = null;
                    if (reviewCountEl) {
                        // Try textContent first, then content attribute
                        const countText = reviewCountEl.textContent?.trim() || reviewCountEl.getAttribute('content');
                        if (countText) {
                            const countMatch = countText.match(/(\\d+)/);
                            if (countMatch) count = parseInt(countMatch[1]);
                        }
                    }

                    // Fallback: Try BazaarVoice count selector
                    if (!count) {
                        const bvCount = ratingSummary.querySelector('.bv_numReviews_component_container');
                        if (bvCount) {
                            const countText = bvCount.textContent?.trim();
                            const match = countText?.match(/(\\d+)/);
                            if (match) count = parseInt(match[1]);
                        }
                    }

                    // Create score string (e.g., "4.5/5")
                    const score = stars ? `${stars}/5` : null;

                    return {
                        score,
                        stars: stars ? parseFloat(stars) : null,
                        count
                    };
                }
            ''')
        finally:
            await browser.close()


if __name__ == "__main__":
    # Test with a Boots product URL
    import sys

    if len(sys.argv) < 2:
        print("Usage: python scraper.py <boots_product_url>")
        print("Example: python scraper.py https://www.boots.com/...")
        sys.exit(1)

    url = sys.argv[1]
    result = asyncio.run(extract_review(url))

    if result:
        print(f"Score: {result['score']}")
        print(f"Stars: {result['stars']}")
        print(f"Count: {result['count']}")
    else:
        print("No reviews found")
