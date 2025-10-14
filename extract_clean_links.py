#!/usr/bin/env python3
"""
Extract retailer links from scraped data and show original vs cleaned URLs
"""
import json
import asyncio
from complete_scraper import main

async def scrape_and_extract_links(category_name, url):
    """Scrape 1 page and extract retailer links"""
    print(f"\n{'='*80}")
    print(f"{category_name.upper()}")
    print("="*80)

    # Run scraper for 1 page
    await main(
        url=url,
        pages=1,
        workers=1,
        skip_specs=False,
        output_file=f"{category_name.lower()}_1page.json",
        download_images=False,
        skip_retailers=False
    )

    # Load and display results
    with open(f'output/{category_name.lower()}_1page.json', 'r') as f:
        data = json.load(f)

    products = data.get('products', [])
    print(f"\nFound {len(products)} products")

    # Extract all unique retailer links
    all_retailers = {}

    for product in products[:5]:  # Show first 5 products
        print(f"\n{product['name']}:")
        retailer_links = product.get('retailerLinks', [])

        for link in retailer_links:
            retailer_name = link.get('name', 'Unknown')
            clean_url = link.get('url', '')
            original_url = link.get('originalUrl', clean_url)

            if retailer_name not in all_retailers:
                all_retailers[retailer_name] = {
                    'clean': clean_url,
                    'original': original_url,
                    'changed': clean_url != original_url
                }

            print(f"\n  {retailer_name}:")
            print(f"    Original:  {original_url[:100]}...")
            print(f"    Cleaned:   {clean_url}")
            if clean_url != original_url:
                print(f"    ✓ URL was cleaned")

    return all_retailers

async def main_extract():
    """Extract links from all three categories"""
    categories = [
        ("Kettles", "https://www.which.co.uk/reviews/kettles"),
        ("Tablets", "https://www.which.co.uk/reviews/tablets"),
        ("Washing Machines", "https://www.which.co.uk/reviews/washing-machines")
    ]

    for category_name, url in categories:
        await scrape_and_extract_links(category_name, url)
        print("\n" + "-"*80)

if __name__ == "__main__":
    asyncio.run(main_extract())