#!/usr/bin/env python3
"""
Batch scraper for all Which.com categories
Scrapes specs and features for all categories and generates metadata
"""
import subprocess
import json
import os
import time
from datetime import datetime
from pathlib import Path

# All categories from the database
CATEGORIES = [
    {"id": 1, "name": "Washing Machines", "slug": "washing-machines"},
    {"id": 2, "name": "Dishwashers", "slug": "dishwashers"},
    {"id": 3, "name": "Air Fryers", "slug": "air-fryers"},
    {"id": 4, "name": "Fridge Freezers", "slug": "fridge-freezers"},
    {"id": 5, "name": "Fridges", "slug": "fridges"},
    {"id": 6, "name": "Freezers", "slug": "freezers"},
    {"id": 7, "name": "Vacuum Cleaners", "slug": "vacuum-cleaners"},
    {"id": 8, "name": "Coffee Machines", "slug": "coffee-machines"},
    {"id": 9, "name": "TVs", "slug": "tvs"},
    {"id": 10, "name": "Laptops", "slug": "laptops"},
    {"id": 11, "name": "Mobile Phones", "slug": "mobile-phones"},
    {"id": 12, "name": "Tablets", "slug": "tablets"},
    {"id": 13, "name": "Tumble Dryers", "slug": "tumble-dryers"},
    {"id": 14, "name": "Ovens", "slug": "ovens"},
    {"id": 15, "name": "Microwaves", "slug": "microwaves"},
    {"id": 62, "name": "Wireless And Bluetooth Speakers", "slug": "wireless-and-bluetooth-speakers"},
    {"id": 63, "name": "Smartwatches", "slug": "smartwatches"},
    {"id": 64, "name": "Kettles", "slug": "kettles"},
]

def log(message):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def scrape_category(category):
    """Scrape a single category"""
    slug = category['slug']
    name = category['name']
    output_file = f"output/{slug}_full.json"

    # Check if already scraped
    if Path(output_file).exists():
        # Check if file has content
        with open(output_file, 'r') as f:
            data = json.load(f)
            if data.get('products') and len(data['products']) > 0:
                log(f"⚠️  {name} already scraped ({len(data['products'])} products), skipping...")
                return True

    log(f"🔍 Scraping {name}...")

    # Build command
    url = f"https://www.which.co.uk/reviews/{slug}"
    cmd = [
        'python', 'complete_scraper.py',
        '--url', url,
        '--pages', 'all',
        '--workers', '5',
        '--output', output_file
    ]

    try:
        # Run scraper
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30 min timeout

        if result.returncode == 0:
            log(f"✅ Successfully scraped {name}")

            # Check if metadata was generated
            metadata_file = output_file.replace('.json', '.metadata.json')
            if Path(metadata_file).exists():
                log(f"✅ Metadata generated for {name}")
            else:
                log(f"⚠️  Metadata generation failed for {name}")

            return True
        else:
            log(f"❌ Failed to scrape {name}: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        log(f"❌ Timeout scraping {name} (exceeded 30 minutes)")
        return False
    except Exception as e:
        log(f"❌ Error scraping {name}: {e}")
        return False

def main():
    """Main batch scraping function"""
    log("="*60)
    log("BATCH CATEGORY SCRAPER")
    log("="*60)

    # Track progress
    successful = []
    failed = []
    skipped = []

    # Process each category
    for i, category in enumerate(CATEGORIES, 1):
        log(f"\nProcessing {i}/{len(CATEGORIES)}: {category['name']}")

        # Check if output exists and skip if requested
        output_file = f"output/{category['slug']}_full.json"
        if Path(output_file).exists():
            with open(output_file, 'r') as f:
                data = json.load(f)
                if data.get('products') and len(data['products']) > 0:
                    skipped.append(category)
                    log(f"⚠️  Skipping {category['name']} (already has {len(data['products'])} products)")
                    continue

        success = scrape_category(category)

        if success:
            successful.append(category)
        else:
            failed.append(category)

        # Add delay between scrapes to be respectful
        if i < len(CATEGORIES):
            log("Waiting 5 seconds before next scrape...")
            time.sleep(5)

    # Summary report
    log("\n" + "="*60)
    log("SUMMARY")
    log("="*60)
    log(f"Total categories: {len(CATEGORIES)}")
    log(f"✅ Successfully scraped: {len(successful)}")
    log(f"⚠️  Skipped (already scraped): {len(skipped)}")
    log(f"❌ Failed: {len(failed)}")

    if failed:
        log("\nFailed categories:")
        for cat in failed:
            log(f"  - {cat['name']}")

    # Insert metadata into database
    if successful:
        log("\nInserting metadata into database...")
        try:
            result = subprocess.run(['python', 'insert_metadata_to_db.py'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                log("✅ Metadata inserted successfully")
            else:
                log(f"❌ Failed to insert metadata: {result.stderr}")
        except Exception as e:
            log(f"❌ Error inserting metadata: {e}")

    log("\n✅ Batch scraping complete!")

if __name__ == '__main__':
    main()