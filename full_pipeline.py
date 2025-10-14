#!/usr/bin/env python3
"""
Full Scraping Pipeline
Combines Which.com product scraping with AO.com review enrichment
Includes database insertion and metadata generation
"""
import asyncio
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Import the main functions from both scrapers
from complete_scraper import scrape_products_phase, enrich_specs_phase
from review_scrapers.ao_review_enricher import (
    worker_process_chunk, 
    process_product
)

# Import database and metadata functions
from insert_to_db import insert_products
from generate_metadata import generate_product_metadata
from insert_metadata_to_db import insert_category_metadata

from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def enrich_reviews_phase(products: List[Dict], workers: int = 3, extract_sentiment: bool = True, category: str = None) -> List[Dict]:
    """
    Phase 3: Enrich products with AO.com reviews using parallel workers
    
    Args:
        products: List of product dictionaries
        workers: Number of parallel workers
        extract_sentiment: Whether to extract sentiment analysis
        category: Product category (e.g., 'washing-machines', 'built-in-ovens')
    """
    print("="*60)
    print("PHASE 3: AO.com Review Enrichment")
    print("="*60)
    
    if not products:
        return []
    
    total = len(products)
    print(f"Processing {total} products with {workers} workers")
    if category:
        print(f"Category: {category}")
    
    start_time = time.time()
    
    # Use parallel processing if workers > 1
    all_stats = []
    
    if workers > 1 and total > 1:
        # Create shared browser instance
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Split products into chunks for workers
            chunk_size = len(products) // workers + (1 if len(products) % workers else 0)
            chunks = [products[i:i + chunk_size] for i in range(0, len(products), chunk_size)]
            
            # Create tasks for each worker
            tasks = [
                worker_process_chunk(i + 1, chunk, browser, extract_sentiment=extract_sentiment, category=category or "product")
                for i, chunk in enumerate(chunks)
            ]
            
            # Run all workers in parallel
            all_results = await asyncio.gather(*tasks)
            
            # Flatten results from all workers
            enriched_products = []
            for products_result, stats_result in all_results:
                enriched_products.extend(products_result)
                all_stats.extend(stats_result)
            
            await browser.close()
    else:
        # Single-threaded processing - create a browser instance
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            enriched_products = []
            for i, product in enumerate(products, 1):
                enriched, stats = await process_product(
                    product, i, total, page=page, 
                    extract_sentiment=extract_sentiment, 
                    category=category or "product"
                )
                enriched_products.append(enriched)
                all_stats.append(stats)
            
            await page.close()
            await context.close()
            await browser.close()
    
    # Calculate statistics from stats data
    successful = 0
    failed = 0
    sentiment_extracted = 0
    total_ratings_sum = 0
    total_reviews = 0
    
    for stats in all_stats:
        if stats['success']:
            successful += 1
            total_ratings_sum += stats['stars'] * stats['count']
            total_reviews += stats['count']
            if stats.get('sentiment_extracted', False):
                sentiment_extracted += 1
        else:
            failed += 1
    
    # Calculate global average
    global_avg = round(total_ratings_sum / total_reviews, 2) if total_reviews > 0 else 4.0
    
    # Summary
    print(f"└─ Completed: {successful}/{len(enriched_products)} products enriched with reviews")
    print(f"   Global average: {global_avg}★ from {total_reviews:,} reviews")
    print(f"   Time: {time.time() - start_time:.1f} seconds\n")
    
    # Return enriched products with metadata
    return enriched_products, {
        'totalProcessed': total,
        'successful': successful,
        'failed': failed,
        'sentimentExtracted': sentiment_extracted,
        'successRate': f"{(successful/total*100):.1f}%" if total > 0 else "0%",
        'processingTime': f"{time.time() - start_time:.1f}s",
        'globalAverage': global_avg,
        'totalReviews': total_reviews
    }


async def main(url: str, pages, workers: int, skip_specs: bool, skip_reviews: bool, 
               review_workers: int, output_file: str, download_images: bool = False,
               insert_db: bool = False, generate_metadata: bool = False):
    """Main pipeline coordinator"""
    print(f"\n{'='*60}")
    print("FULL SCRAPING PIPELINE")
    print('='*60)
    print(f"Target: {url}")
    print(f"Pages: {pages}")
    print(f"Workers: {workers} (specs) | {review_workers} (reviews)")
    print(f"Skip specs: {skip_specs}")
    print(f"Skip reviews: {skip_reviews}")
    print(f"Download images: {download_images}")
    print(f"Insert to DB: {insert_db}")
    print(f"Generate metadata: {generate_metadata}")
    print(f"Output: {output_file}")
    print()
    
    # Extract category from URL
    category = url.split('/reviews/')[-1].split('/')[0].split('?')[0]
    
    # Initialize Supabase if needed (for images, DB insertion, or metadata)
    supabase = None
    if download_images or insert_db or generate_metadata:
        try:
            from supabase import create_client
            from dotenv import load_dotenv
            
            load_dotenv()
            
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            
            if supabase_url and supabase_key:
                supabase = create_client(supabase_url, supabase_key)
                print(f"✓ Supabase initialized for category: {category}")
                if download_images:
                    print("  • Image storage enabled")
                if insert_db:
                    print("  • Database insertion enabled")
                if generate_metadata:
                    print("  • Metadata generation enabled")
                print()
            else:
                print("⚠️ SUPABASE_URL or SUPABASE_KEY not found in environment")
                if download_images:
                    print("   Images will not be uploaded to storage")
                if insert_db or generate_metadata:
                    print("   Database operations will be skipped")
                print()
                # Disable DB operations if no credentials
                insert_db = False
                generate_metadata = False
        except ImportError:
            print("⚠️ Supabase library not installed (pip install supabase)")
            print("   Database operations and image storage will be skipped")
            print()
            insert_db = False
            generate_metadata = False
        except Exception as e:
            print(f"⚠️ Failed to initialize Supabase: {e}")
            print("   Database operations and image storage will be skipped")
            print()
            insert_db = False
            generate_metadata = False
    
    # Single browser instance for Which.com phases
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Phase 1: Scrape products from Which.com
        products = await scrape_products_phase(browser, url, pages)
        
        # Phase 2: Enrich with specs (if enabled)
        if not skip_specs and products:
            products = await enrich_specs_phase(browser, products, workers, supabase, category)
        
        await browser.close()
    
    # Phase 3: Enrich with AO.com reviews (if enabled)
    ao_enrichment = None
    if not skip_reviews and products:
        products, ao_enrichment = await enrich_reviews_phase(products, review_workers, extract_sentiment=True, category=category)
    
    # Save results
    output_path = Path(output_file)
    if not str(output_path).startswith('output/'):
        output_path = Path('output') / output_path.name
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Prepare output data
    output_data = {
        'products': products,
        'total': len(products),
        'url': url
    }
    
    # Add Which.com spec stats if specs were extracted
    if not skip_specs:
        successful = sum(1 for p in products if p.get('specs'))
        total_specs = sum(len(p.get('specs', {})) for p in products)
        total_features = sum(len(p.get('features', {})) for p in products)
        
        output_data.update({
            'successful_enriched': successful,
            'failed_enriched': len(products) - successful,
            'total_specs_extracted': total_specs,
            'total_features_extracted': total_features
        })
        
        # Add image stats if images were downloaded
        if download_images:
            total_images = sum(len(p.get('images', {})) for p in products)
            products_with_images = sum(1 for p in products if p.get('images'))
            output_data.update({
                'total_images_uploaded': total_images,
                'products_with_images': products_with_images
            })
    
    # Add AO enrichment stats if reviews were extracted
    if ao_enrichment:
        output_data['aoEnrichment'] = ao_enrichment
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Database operations
    db_stats = None
    metadata_success = False
    
    if insert_db and supabase and len(products) > 0:
        print("\n" + "="*60)
        print("DATABASE INSERTION")
        print("="*60)
        
        try:
            db_stats = insert_products({'products': products}, category, supabase)
            print(f"\nDatabase insertion summary:")
            print(f"  Inserted: {db_stats['inserted']}")
            print(f"  Failed: {db_stats['failed']}")
            print(f"  Total: {db_stats['total']}")
            
            # Generate and insert metadata if requested
            if generate_metadata and db_stats['inserted'] > 0:
                print("\n" + "="*60)
                print("METADATA GENERATION")
                print("="*60)
                
                try:
                    print(f"Generating metadata for {output_path}...")
                    metadata = generate_product_metadata(str(output_path))
                    
                    # Save metadata file
                    metadata_path = str(output_path).replace('.json', '.metadata.json')
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2, ensure_ascii=False)
                    print(f"✓ Metadata saved to {metadata_path}")
                    
                    # Insert metadata to database
                    print("\nInserting metadata to database...")
                    success, message = insert_category_metadata(metadata, category, supabase)
                    
                    if success:
                        print(message)
                        metadata_success = True
                    else:
                        print(f"✗ {message}")
                        
                except Exception as e:
                    print(f"✗ Metadata generation failed: {e}")
                    
        except Exception as e:
            print(f"✗ Database insertion failed: {e}")
    
    # Final summary
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"✓ Total products: {len(products)}")
    
    if not skip_specs:
        print(f"✓ Products with specs: {successful}/{len(products)}")
        print(f"✓ Total specs extracted: {total_specs}")
        
        if download_images and 'total_images_uploaded' in output_data:
            print(f"✓ Images uploaded: {output_data['total_images_uploaded']} for {output_data['products_with_images']} products")
    
    if ao_enrichment:
        print(f"✓ Products with reviews: {ao_enrichment['successful']}/{ao_enrichment['totalProcessed']}")
        print(f"✓ Total reviews collected: {ao_enrichment['totalReviews']}")
    
    if db_stats:
        print(f"✓ Products inserted to DB: {db_stats['inserted']}/{db_stats['total']}")
        if metadata_success:
            print(f"✓ Metadata generated and inserted for category: {category}")
    
    print(f"📁 Results saved to: {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Full Scraping Pipeline: Which.com + AO.com Reviews',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline with all data
  python full_pipeline.py --url "https://www.which.co.uk/reviews/air-fryers" --pages 2
  
  # Full pipeline with database insertion and metadata
  python full_pipeline.py --url "https://www.which.co.uk/reviews/washing-machines" --pages all --insert-db --generate-metadata
  
  # Skip reviews (Which.com only)
  python full_pipeline.py --url "https://www.which.co.uk/reviews/tvs" --pages 1 --skip-reviews
  
  # Skip specs but get reviews (products + reviews only)
  python full_pipeline.py --url "https://www.which.co.uk/reviews/coffee-machines" --pages 1 --skip-specs
  
  # Maximum parallelization with DB insertion
  python full_pipeline.py --url "https://www.which.co.uk/reviews/washing-machines" --pages all --workers 5 --review-workers 5 --insert-db
  
  # Just product listings (no specs, no reviews)
  python full_pipeline.py --url "https://www.which.co.uk/reviews/laptops" --pages 3 --skip-specs --skip-reviews
  
  # Complete pipeline with images and database
  python full_pipeline.py --url "https://www.which.co.uk/reviews/dishwashers" --pages 2 --download-images --insert-db --generate-metadata
        """
    )
    
    parser.add_argument('--url', '-u', 
                       default='https://www.which.co.uk/reviews/washing-machines',
                       help='Which.com category URL to scrape')
    parser.add_argument('--pages', '-p', 
                       default='1',
                       help='Number of pages to scrape or "all" for all pages')
    parser.add_argument('--workers', '-w', 
                       type=int, default=3,
                       help='Number of parallel workers for spec extraction (default: 3)')
    parser.add_argument('--skip-specs', '-s',
                       action='store_true',
                       help='Skip Which.com specification extraction')
    parser.add_argument('--skip-reviews', '-r',
                       action='store_true',
                       help='Skip AO.com review enrichment')
    parser.add_argument('--review-workers', '-rw',
                       type=int, default=3,
                       help='Number of parallel workers for review extraction (default: 3)')
    parser.add_argument('--output', '-o',
                       default='full_pipeline_output.json',
                       help='Output JSON file (default: full_pipeline_output.json)')
    parser.add_argument('--download-images', '-d',
                       action='store_true',
                       help='Download and upload product images to Supabase storage')
    parser.add_argument('--insert-db',
                       action='store_true',
                       help='Insert scraped products into Supabase database')
    parser.add_argument('--generate-metadata',
                       action='store_true',
                       help='Generate and insert field metadata (requires --insert-db)')
    
    args = parser.parse_args()
    
    # Convert pages to int if not "all"
    if args.pages.lower() == 'all':
        pages_arg = 'all'
    else:
        try:
            pages_arg = int(args.pages)
        except ValueError:
            print(f"Error: Invalid pages value '{args.pages}'. Must be a number or 'all'")
            sys.exit(1)
    
    # Validate arguments
    if args.generate_metadata and not args.insert_db:
        print("Error: --generate-metadata requires --insert-db")
        sys.exit(1)
    
    # Run the pipeline
    asyncio.run(main(
        url=args.url,
        pages=pages_arg,
        workers=args.workers,
        skip_specs=args.skip_specs,
        skip_reviews=args.skip_reviews,
        review_workers=args.review_workers,
        output_file=args.output,
        download_images=args.download_images,
        insert_db=args.insert_db,
        generate_metadata=args.generate_metadata
    ))