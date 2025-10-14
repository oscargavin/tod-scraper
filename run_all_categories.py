#!/usr/bin/env python3
"""
Run full pipeline for multiple product categories sequentially
"""
import subprocess
import time
from datetime import datetime

# Product categories to scrape
CATEGORIES = [
    'dishwashers',
    'ovens',
    'microwaves',
    'air-fryers',
    'coffee-machines',
    'vacuum-cleaners',
    'tvs',
    'tablets',
    'mobile-phones'
]

def run_category(category):
    """Run full pipeline for a single category"""
    url = f"https://www.which.co.uk/reviews/{category}"
    output = f"output/{category}_full.json"
    
    cmd = [
        'python', 'full_pipeline.py',
        '--url', url,
        '--pages', 'all',
        '--workers', '4',
        '--review-workers', '3',
        '--download-images',
        '--output', output
    ]
    
    print(f"\n{'='*60}")
    print(f"Starting: {category}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    start_time = time.time()
    
    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✓ {category} completed successfully in {elapsed:.1f}s")
        else:
            print(f"✗ {category} failed with exit code {result.returncode}")
            return False
            
    except KeyboardInterrupt:
        print(f"\n⚠️  {category} interrupted by user")
        raise
    except Exception as e:
        print(f"✗ {category} failed with error: {e}")
        return False
    
    return True

def main():
    """Run all categories sequentially"""
    print("="*60)
    print("BATCH SCRAPING PIPELINE")
    print("="*60)
    print(f"Categories to process: {len(CATEGORIES)}")
    for cat in CATEGORIES:
        print(f"  - {cat}")
    print()
    
    start_time = time.time()
    successful = []
    failed = []
    
    try:
        for i, category in enumerate(CATEGORIES, 1):
            print(f"\nProgress: {i}/{len(CATEGORIES)}")
            
            if run_category(category):
                successful.append(category)
            else:
                failed.append(category)
            
            # Small delay between runs to avoid overwhelming the server
            if i < len(CATEGORIES):
                print(f"Waiting 5 seconds before next category...")
                time.sleep(5)
                
    except KeyboardInterrupt:
        print("\n\n⚠️  Batch processing interrupted by user")
        remaining = CATEGORIES[len(successful) + len(failed):]
        if remaining:
            print(f"Remaining categories not processed: {', '.join(remaining)}")
    
    # Final summary
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print("BATCH PROCESSING COMPLETE")
    print('='*60)
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Successful: {len(successful)}/{len(CATEGORIES)}")
    
    if successful:
        print(f"\n✓ Completed categories:")
        for cat in successful:
            print(f"  - {cat}")
    
    if failed:
        print(f"\n✗ Failed categories:")
        for cat in failed:
            print(f"  - {cat}")
    
    print(f"\nAll outputs saved to: output/")

if __name__ == '__main__':
    main()