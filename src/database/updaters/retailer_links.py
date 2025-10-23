#!/usr/bin/env python3
"""
Update existing products in database with retailer links by running scraper
and matching products by brand and model

Usage:
    python update_retailer_links_bulk.py                    # Process all categories
    python update_retailer_links_bulk.py --test             # Test with smallest category, 2 pages
    python update_retailer_links_bulk.py --missing          # Process only kettles, speakers, smartwatches
    python update_retailer_links_bulk.py --categories tvs,ovens  # Process specific categories
"""
import asyncio
import json
import os
from typing import Dict, List, Tuple
from supabase import create_client
from dotenv import load_dotenv
from complete_scraper import main as scraper_main
from insert_to_db import extract_brand_model

load_dotenv()

async def get_categories_needing_updates(supabase) -> List[Tuple[str, str, int]]:
    """Get categories with products missing retailer links"""
    # Get all categories first
    categories_result = supabase.table('categories').select('*').execute()

    categories_with_counts = []

    # Check each category individually to avoid fetching too many products at once
    for category in categories_result.data:
        # Count products without retailer links for this specific category
        # First get all products for this category
        all_products = supabase.table('products').select('id, retailer_links').eq('category_id', category['id']).execute()

        # Count those without retailer links
        count = 0
        for product in all_products.data:
            if not product.get('retailer_links') or product['retailer_links'] == []:
                count += 1

        if count > 0:
            categories_with_counts.append((
                category['name'],
                category['slug'],
                count
            ))

    # Sort by count descending
    categories_with_counts.sort(key=lambda x: x[2], reverse=True)

    return categories_with_counts

async def scrape_category_for_links(category_slug: str, pages='all') -> Dict:
    """Run scraper for a specific category to get retailer links"""
    # Construct Which.com URL from category slug
    url = f"https://www.which.co.uk/reviews/{category_slug}"
    output_file = f"temp_retailer_update_{category_slug}.json"

    # Run scraper with retailer links enabled but skip images/reviews
    await scraper_main(
        url=url,
        pages=pages,
        workers=3,
        skip_specs=False,  # Need specs to get retailer links
        output_file=output_file,
        download_images=False,
        skip_retailers=False
    )

    # Load scraped data
    with open(f'output/{output_file}', 'r') as f:
        data = json.load(f)

    # Clean up temp file
    os.remove(f'output/{output_file}')

    return data

def update_products_with_retailer_links(supabase, scraped_data: Dict, category_slug: str) -> Tuple[int, int]:
    """Match scraped products with DB products and update retailer links"""
    products = scraped_data.get('products', [])
    updated_count = 0
    not_found_count = 0

    # Get category ID
    category_result = supabase.table('categories').select('id').eq('slug', category_slug).execute()
    if not category_result.data:
        print(f"Category {category_slug} not found in database")
        return 0, 0

    category_id = category_result.data[0]['id']

    for product in products:
        # Extract brand and model from product name
        brand, model = extract_brand_model(product['name'])
        retailer_links = product.get('retailerLinks', [])

        if retailer_links:  # Only update if we have retailer links
            # Find matching product in DB by brand, model and category
            match_result = supabase.table('products').select('id, name').eq('brand', brand).eq('model', model).eq('category_id', category_id).execute()

            if match_result.data:
                product_id = match_result.data[0]['id']

                # Update only retailer_links field
                update_result = supabase.table('products').update({
                    'retailer_links': retailer_links
                }).eq('id', product_id).execute()

                if update_result.data:
                    updated_count += 1
                    print(f"  ✓ Updated: {product['name']} ({len(retailer_links)} links)")
            else:
                not_found_count += 1
                print(f"  ✗ No match found for: {product['name']} (brand: {brand}, model: {model})")

    return updated_count, not_found_count

async def main(test_mode=False, specific_categories=None):
    """Main function to update all products with retailer links"""
    # Initialize Supabase
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        return

    supabase = create_client(supabase_url, supabase_key)

    # Get categories needing updates
    print("Fetching categories with products missing retailer links...")
    categories = await get_categories_needing_updates(supabase)

    if not categories:
        print("No categories found with products missing retailer links")
        return

    # Filter by specific categories if provided
    if specific_categories:
        categories = [(name, slug, count) for name, slug, count in categories
                      if slug in specific_categories]
        print(f"\nFiltered to {len(categories)} specific categories")

    print(f"\nFound {len(categories)} categories needing updates:")
    for name, slug, count in categories:
        print(f"  • {name}: {count} products")

    # In test mode, process only the smallest category
    if test_mode:
        # Find smallest category
        smallest_category = min(categories, key=lambda x: x[2])
        categories = [smallest_category]
        print(f"\nTEST MODE: Processing only {smallest_category[0]} ({smallest_category[2]} products)")

    # Process each category
    total_updated = 0
    total_not_found = 0

    for name, slug, count in categories:
        print(f"\n{'='*60}")
        print(f"Processing {name} ({count} products missing links)")
        print("="*60)

        try:
            # Scrape category
            print(f"Scraping {name}...")
            pages_to_scrape = 2 if test_mode else 'all'  # In test mode, only scrape first 2 pages
            scraped_data = await scrape_category_for_links(slug, pages=pages_to_scrape)

            scraped_count = len(scraped_data.get('products', []))
            print(f"Scraped {scraped_count} products from Which.com")

            # Update database
            print("\nUpdating database...")
            updated, not_found = update_products_with_retailer_links(supabase, scraped_data, slug)

            total_updated += updated
            total_not_found += not_found

            print(f"\nCategory summary:")
            print(f"  • Updated: {updated} products")
            print(f"  • Not found: {not_found} products")

            # Add delay between categories to avoid rate limiting
            if categories.index((name, slug, count)) < len(categories) - 1:
                print("\nWaiting 5 seconds before next category...")
                await asyncio.sleep(5)

        except Exception as e:
            print(f"Error processing {name}: {e}")
            continue

    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Total products updated: {total_updated}")
    print(f"Total products not found: {total_not_found}")

if __name__ == "__main__":
    import sys
    test_mode = '--test' in sys.argv

    # Check if specific categories were requested
    specific_categories = None
    if '--categories' in sys.argv:
        idx = sys.argv.index('--categories')
        if idx + 1 < len(sys.argv):
            specific_categories = sys.argv[idx + 1].split(',')

    # Also check for the predefined missing categories
    if '--missing' in sys.argv:
        specific_categories = ['kettles', 'wireless-and-bluetooth-speakers', 'smartwatches']

    asyncio.run(main(test_mode=test_mode, specific_categories=specific_categories))