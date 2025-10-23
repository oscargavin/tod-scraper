"""
Test script for Very scraper
Tests extraction from a Very.co.uk product page via tracking redirect
"""

import asyncio
import json
from playwright.async_api import async_playwright
from src.scrapers.retailers.very_scraper import VeryScraper
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def test_very_scraper():
    """Test Very scraper on example product"""

    # Test with tracking redirect URL (what we get from Which.com)
    test_url = "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D40725437813%26a%3D634144%26m%3D3090&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fcoffee-machines%2Fdaewoo-sda2700ge&event_type=click&userid=&clickid=c6b35346-9912-4883-8d0b-9186fb56d78d&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=coffee-machines&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Daewoo+SDA2700GE&product_id=IC23024-0100-00&productprice=129.00"

    print("=" * 70)
    print("Testing Very Scraper")
    print("=" * 70)
    print(f"Product URL: {test_url}")
    print()

    # Initialize scraper
    scraper = VeryScraper()

    # Launch browser
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=False)  # Try non-headless first
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        try:
            # Navigate to Very.co.uk product URL
            print(f"Navigating to Very.co.uk...")
            await page.goto(test_url, wait_until='domcontentloaded', timeout=60000)

            print(f"Final URL: {page.url}")
            print("\nPage loaded, starting scrape...\n")

            # Scrape product
            result = await scraper.scrape_product(page, page.url)

            # Display results
            print("\n" + "=" * 70)
            print("SCRAPING RESULTS")
            print("=" * 70)
            print(f"Success: {result['success']}")

            if result['success']:
                specs = result['specs']
                print(f"Total specs extracted: {len(specs)}")
                print(f"Retailer URL: {result['retailerUrl']}")
                print("\nExtracted specifications:")
                print("-" * 70)

                for key, value in specs.items():
                    # Truncate long values
                    display_value = value if len(value) < 100 else value[:97] + "..."
                    print(f"{key:.<40} {display_value}")

                # Save full results to JSON
                output_file = "test_very_scraper_output.json"
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2)
                print(f"\nFull results saved to: {output_file}")

            else:
                print(f"Error: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"\nError during test: {str(e)}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()

    print("\n" + "=" * 70)
    print("Test complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_very_scraper())
