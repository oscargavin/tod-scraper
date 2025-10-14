#!/usr/bin/env python3
"""
AO.com Review Enricher
Processes Which.com product JSON files and enriches them with AO.com review data
"""
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
import argparse
from playwright.async_api import async_playwright
from .ao_search import search_and_extract
from .ao_sentiment_scraper import get_sentiment_analysis


def calculate_tod_score(rating, count, global_avg=4.0, min_reviews=30):
    """
    Calculate TOD Score: confidence-weighted rating as percentage (0-100)
    
    Args:
        rating: Product's average rating (e.g., "4.5/5" → 4.5)
        count: Number of reviews
        global_avg: Average rating across all products (default 4.0)
        min_reviews: Minimum reviews for full confidence (default 30)
    
    Returns:
        tod_score: Weighted rating as percentage (0-100)
    
    Examples:
        5.0 stars with 2 reviews → ~81 (pulled toward average)
        4.5 stars with 1000 reviews → ~90 (stays near actual rating)
    """
    # Convert rating string if needed ("4.5/5" → 4.5)
    if isinstance(rating, str):
        if '/' in rating:
            rating = float(rating.split('/')[0])
        else:
            rating = float(rating)
    
    # Bayesian average formula
    confidence_score = (count / (count + min_reviews)) * rating + \
                      (min_reviews / (count + min_reviews)) * global_avg
    
    # Convert to percentage (0-5 scale → 0-100)
    tod_score = (confidence_score / 5.0) * 100
    
    return round(tod_score, 1)


def extract_search_terms(product_name: str, category: str = None) -> tuple[str, Optional[str]]:
    """
    Extract search query and target model from product name
    
    Examples:
    "Ninja Crispi FN101UKGY" -> ("ninja crispi", "FN101UKGY")
    "Tower T17190 Vortx 11L" -> ("tower vortx", "T17190")
    
    Args:
        product_name: Product name from Which.com
        category: Category slug (e.g., 'built-in-ovens', 'washing-machines')
    """
    # Try to find model number (uppercase letters/numbers, often at end or after brand)
    model_patterns = [
        r'\b([A-Z]{1,3}\d{3,}[A-Z]*\w*)\b',  # Like FN101UKGY, T17190
        r'\b([A-Z]+[-]?\d+[A-Z]*)\b',         # Like R901, XXL-10
        r'\b(\d+[A-Z]+)\b'                     # Like 10L, 8L
    ]
    
    target_model = None
    for pattern in model_patterns:
        match = re.search(pattern, product_name)
        if match:
            target_model = match.group(1)
            break
    
    # Create search query - if we have a strong model number, include it
    name_parts = product_name.split()
    
    # Check if this looks like a "Brand Model" pattern (e.g., "Ninja AF180UK")
    if len(name_parts) == 2 and target_model and len(target_model) >= 5:
        # For simple "Brand Model" products, search for both
        search_query = f"{name_parts[0].lower()} {target_model}"
    else:
        # Otherwise use the original approach
        search_parts = []
        
        for part in name_parts[:3]:
            # Skip if it's the model number we found
            if target_model and target_model in part:
                continue
            # Skip common size indicators
            if re.match(r'^\d+(\.\d+)?[Ll]$', part):
                continue
            search_parts.append(part.lower())
        
        # If we have too few parts, add more
        if len(search_parts) < 2 and len(name_parts) > 3:
            for part in name_parts[3:5]:
                if not re.match(r'^\d+(\.\d+)?[Ll]$', part):
                    search_parts.append(part.lower())
        
        search_query = ' '.join(search_parts[:3])  # Max 3 words
    
    # Add category context to search query if available
    if category:
        # Map category slugs to AO.com search terms
        category_mappings = {
            'built-in-ovens': 'oven',
            'washing-machines': 'washing machine',
            'dishwashers': 'dishwasher',
            'fridge-freezers': 'fridge freezer',
            'coffee-machines': 'coffee machine',
            'air-fryers': 'air fryer',
            'tvs': 'tv',
            'laptops': 'laptop',
            'mobile-phones': 'mobile phone',
            'microwaves': 'microwave'
        }
        
        # Get the category search term
        category_term = category_mappings.get(category)
        if category_term and category_term not in search_query.lower():
            # Add category to search query to improve matching
            search_query = f"{search_query} {category_term}"
    
    return search_query, target_model


async def process_product(product: Dict, index: int, total: int, page=None, worker_id: int = 0, 
                         extract_sentiment: bool = False, category: str = "product") -> tuple[Dict, Dict]:
    """
    Process a single product and add AO.com review data
    
    Args:
        product: Product dict to process
        index: Product index (for display)
        total: Total number of products (for display)
        page: Optional Playwright page instance (for parallel processing)
        worker_id: Worker ID for display (0 for single-threaded mode)
        extract_sentiment: Whether to extract sentiment from reviews
        category: Product category for sentiment analysis context
    
    Returns:
        tuple of (product, stats) where stats contains review metadata for aggregation
    """
    name = product.get('name', 'Unknown')
    stats = {'success': False, 'stars': 0, 'count': 0, 'sentiment_extracted': False}
    
    # Extract search terms with category context
    search_query, target_model = extract_search_terms(name, category)
    
    # Search and extract reviews
    try:
        result = await search_and_extract(
            search_query=search_query,
            target_product=target_model,
            silent=True,
            page=page
        )
        
        if result['success']:
            stars = float(result['reviews']['stars'])
            count = result['reviews']['count']
            ao_url = result['ao_url']
            
            # Calculate TOD score
            tod_score = calculate_tod_score(stars, count)
            
            # Build reviews dict
            reviews_data = {
                'rating': f"{stars}/5",
                'count': count,
                'todScore': tod_score,
                'ao_url': ao_url
            }
            
            # Extract sentiment if requested
            if extract_sentiment and ao_url:
                try:
                    # Get streamlined sentiment analysis
                    sentiment = await get_sentiment_analysis(ao_url, max_pages=4)
                    
                    # Add sentiment to reviews data
                    reviews_data['sentiment'] = sentiment
                    stats['sentiment_extracted'] = True
                    
                    if worker_id > 0:
                        print(f"├─ Worker {worker_id}: [{index}/{total}] ✓ {name[:40]}... → TOD: {tod_score}% + Sentiment")
                    else:
                        print(f"[{index}/{total}] ✓ {name} → TOD: {tod_score}% + Sentiment analyzed")
                except Exception as e:
                    print(f"  └─ Sentiment extraction failed: {str(e)[:50]}...")
            else:
                # Print without sentiment
                if worker_id > 0:
                    print(f"├─ Worker {worker_id}: [{index}/{total}] ✓ {name[:40]}... → TOD: {tod_score}%")
                else:
                    print(f"[{index}/{total}] ✓ {name} → TOD Score: {tod_score}%")
            
            product['reviews'] = reviews_data
            stats = {'success': True, 'stars': stars, 'count': count, 'sentiment_extracted': stats['sentiment_extracted']}
            
        else:
            if worker_id > 0:
                print(f"├─ Worker {worker_id}: [{index}/{total}] ✗ {name[:40]}...")
            else:
                print(f"[{index}/{total}] ✗ {name}: {result['error']}")
            
    except Exception as e:
        if worker_id > 0:
            print(f"├─ Worker {worker_id}: [{index}/{total}] ✗ {name[:40]}... - Error")
        else:
            print(f"[{index}/{total}] ✗ {name}: {str(e)}")
    
    # Rate limiting per worker
    await asyncio.sleep(1)  # 1 second between requests
    
    return product, stats


async def worker_process_chunk(worker_id: int, products_chunk: List[Dict], browser,
                              extract_sentiment: bool = False, category: str = "product") -> tuple[List[Dict], List[Dict]]:
    """
    Worker that processes its assigned chunk of products
    
    Args:
        worker_id: Worker identifier (1-based)
        products_chunk: List of products to process
        browser: Shared browser instance
        extract_sentiment: Whether to extract sentiment from reviews
        category: Product category for sentiment analysis context
    
    Returns:
        tuple of (products, stats_list)
    """
    # Create context and page for this worker
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()
    
    products = []
    stats_list = []
    chunk_size = len(products_chunk)
    
    for i, product in enumerate(products_chunk, 1):
        enriched_product, stats = await process_product(
            product, i, chunk_size, page, worker_id,
            extract_sentiment=extract_sentiment,
            category=category
        )
        products.append(enriched_product)
        stats_list.append(stats)
    
    await page.close()
    await context.close()
    
    return products, stats_list


async def process_file(input_file: str, output_file: str = None, limit: int = None, workers: int = 3,
                      extract_sentiment: bool = False, category: str = None):
    """
    Process a JSON file of products and enrich with AO.com reviews
    
    Args:
        input_file: Input JSON file path
        output_file: Output JSON file path (optional)
        limit: Limit number of products to process (optional)
        workers: Number of parallel workers (default: 3)
    """
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"Error: File {input_file} not found")
        return
    
    # Load data
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    products = data.get('products', [])
    
    if not products:
        print("No products found in file")
        return
    
    # Apply limit if specified
    if limit:
        products = products[:limit]
        print(f"Processing first {limit} products only")
    
    total = len(products)
    print(f"\nProcessing {total} products from {input_path.name}")
    
    start_time = time.time()
    
    # Determine if we should use parallel processing
    use_parallel = workers > 1 and total > 1
    all_stats = []
    
    if use_parallel:
        print(f"Using {workers} parallel workers")
        print("="*60)
        
        # Create shared browser instance
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Split products into chunks for workers
            chunk_size = len(products) // workers + (1 if len(products) % workers else 0)
            chunks = [products[i:i + chunk_size] for i in range(0, len(products), chunk_size)]
            
            # Sentiment analysis setup
            if extract_sentiment:
                print("Sentiment analysis enabled with Gemini")
            
            # Detect category if not provided
            if not category and input_path.stem:
                # Try to infer category from filename
                filename = input_path.stem.lower()
                if 'washing' in filename or 'washer' in filename:
                    category = 'washing machine'
                elif 'air-fryer' in filename or 'airfryer' in filename:
                    category = 'air fryer'
                elif 'coffee' in filename:
                    category = 'coffee machine'
                else:
                    category = 'appliance'
                print(f"Detected category: {category}")
            
            # Create tasks for each worker
            tasks = [
                worker_process_chunk(i + 1, chunk, browser,
                                   extract_sentiment=extract_sentiment,
                                   category=category)
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
        # Single-threaded processing
        print("="*60)
        
        # Sentiment analysis setup
        if extract_sentiment:
            print("Sentiment analysis enabled with Gemini")
        
        # Detect category if not provided
        if not category and input_path.stem:
            filename = input_path.stem.lower()
            if 'washing' in filename or 'washer' in filename:
                category = 'washing machine'
            elif 'air-fryer' in filename or 'airfryer' in filename:
                category = 'air fryer'
            elif 'coffee' in filename:
                category = 'coffee machine'
            else:
                category = 'appliance'
            print(f"Detected category: {category}")
        
        enriched_products = []
        for i, product in enumerate(products, 1):
            enriched, stats = await process_product(
                product, i, total,
                extract_sentiment=extract_sentiment,
                category=category
            )
            enriched_products.append(enriched)
            all_stats.append(stats)
    
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
    
    # Calculate global average for future use
    global_avg = round(total_ratings_sum / total_reviews, 2) if total_reviews > 0 else 4.0
    
    # Prepare output
    output_data = {
        **data,  # Keep all original fields
        'products': enriched_products,
        'aoEnrichment': {
            'totalProcessed': total,
            'successful': successful,
            'failed': failed,
            'sentimentExtracted': sentiment_extracted,
            'successRate': f"{(successful/total*100):.1f}%",
            'processingTime': f"{time.time() - start_time:.1f}s",
            'globalAverage': global_avg,
            'totalReviews': total_reviews,
            'category': category
        }
    }
    
    # Save output
    if not output_file:
        suffix = '_ao_reviews_sentiment' if extract_sentiment else '_ao_reviews'
        output_file = str(input_path.parent / f"{input_path.stem}{suffix}.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✓ Processed: {total} products")
    print(f"✓ Successful: {successful} ({successful/total*100:.1f}%)")
    print(f"✗ Failed: {failed}")
    if extract_sentiment:
        print(f"💭 Sentiment analyzed: {sentiment_extracted}")
    print(f"📊 Global average: {global_avg}★ from {total_reviews:,} reviews")
    print(f"⏱ Time: {time.time() - start_time:.1f} seconds")
    print(f"📁 Output: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Enrich Which.com product data with AO.com reviews',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process air fryers file
  python ao_review_enricher.py ../output/air-fryers.json
  
  # Process with custom output file
  python ao_review_enricher.py ../output/washing_machines.json -o enriched_washers.json
  
  # Process only first 10 products (for testing)
  python ao_review_enricher.py ../output/coffee-machines.json --limit 10
        """
    )
    
    parser.add_argument('input_file',
                       help='Input JSON file from Which.com scraper')
    parser.add_argument('-o', '--output',
                       help='Output file name (default: input_ao_reviews.json)')
    parser.add_argument('-l', '--limit',
                       type=int,
                       help='Limit number of products to process (for testing)')
    parser.add_argument('-w', '--workers',
                       type=int,
                       default=3,
                       help='Number of parallel workers (default: 3)')
    parser.add_argument('-s', '--sentiment',
                       action='store_true',
                       help='Extract sentiment analysis from reviews')
    parser.add_argument('-c', '--category',
                       help='Product category for sentiment context (e.g. "washing machine", "air fryer")')
    
    args = parser.parse_args()
    
    asyncio.run(process_file(args.input_file, args.output, args.limit, args.workers,
                           extract_sentiment=args.sentiment, category=args.category))


if __name__ == '__main__':
    main()