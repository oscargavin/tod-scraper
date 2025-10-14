#!/usr/bin/env python3
"""
Complete Which.com Scraper Pipeline
Combines product discovery and specification extraction in a single efficient pipeline
Now includes image extraction and optional Supabase storage
"""
import asyncio
import argparse
import json
import os
import io
import aiohttp
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# ============= Helper Functions =============

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to use only British English letters and safe characters.
    Handles foreign characters by converting to ASCII equivalents.
    """
    # First, normalize unicode characters and convert to ASCII
    # This converts characters like é->e, ñ->n, ü->u, etc.
    normalized = unicodedata.normalize('NFKD', filename)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')

    # Replace spaces and common separators with hyphens
    ascii_str = re.sub(r'[\s_]+', '-', ascii_str)

    # Remove any remaining non-alphanumeric characters except hyphens
    ascii_str = re.sub(r'[^a-zA-Z0-9\-]', '', ascii_str)

    # Clean up multiple hyphens and trim
    ascii_str = re.sub(r'-+', '-', ascii_str).strip('-')

    # Convert to lowercase
    ascii_str = ascii_str.lower()

    # If the result is empty, use a default
    if not ascii_str:
        ascii_str = 'product'

    # Limit length to avoid filesystem issues
    if len(ascii_str) > 100:
        ascii_str = ascii_str[:100].rstrip('-')

    return ascii_str

def parse_price(price_str: str) -> float:
    """Convert price string to float, handling various formats."""
    if not price_str:
        return 0.0
    
    # Remove currency symbol and any text after the number
    price_str = str(price_str).replace('£', '').replace(',', '')
    
    # Extract just the numeric part (handles "999Typical price" format)
    match = re.search(r'^(\d+(?:\.\d+)?)', price_str)
    if match:
        try:
            return float(match.group(1))
        except:
            return 0.0
    return 0.0


# ============= Phase 1: Product Discovery =============

async def detect_total_pages(page) -> Optional[int]:
    """Detect total number of pages from Which.com pagination"""
    page_info = await page.evaluate('''
        (() => {
            const pagePattern = /Page\\s+(\\d+)\\s+of\\s+(\\d+)/i;
            const allText = document.body.textContent;
            const match = allText.match(pagePattern);
            
            if (match) {
                return parseInt(match[2]);  // Return total pages
            }
            return null;
        })()
    ''')
    return page_info


async def scrape_products_phase(browser, url: str, max_pages) -> List[Dict]:
    """
    Phase 1: Scrape products from Which.com listings
    """
    print("\n" + "="*60)
    print("PHASE 1: Product Discovery")
    print("="*60)
    
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = await context.new_page()
    
    print(f"Loading {url}")
    await page.goto(url, wait_until='domcontentloaded', timeout=60000)
    
    # Detect total pages if "all" specified
    if max_pages == "all":
        total_pages = await detect_total_pages(page)
        if total_pages:
            print(f"├─ Detected {total_pages} total pages")
            max_pages = total_pages
        else:
            print("├─ Could not detect total pages, defaulting to 1")
            max_pages = 1
    
    all_products = []
    
    for page_num in range(1, max_pages + 1):
        if page_num > 1:
            separator = '&' if '?' in url else '?'
            page_url = f"{url}{separator}page={page_num}"
            await page.goto(page_url, wait_until='domcontentloaded', timeout=60000)
        
        # Extract products from current page
        products = await page.evaluate('''
            Array.from(document.querySelectorAll('[class*="product"], .item')).map(item => {
                const nameEl = item.querySelector('h3, [class*="title"], a[href*="/reviews/"]');
                const priceEl = item.querySelector('[class*="price"]');
                
                // Get the product link
                const linkEl = item.querySelector('a[href*="/reviews/"]') || 
                              item.querySelector('h3 a') || 
                              item.querySelector('[class*="title"] a') ||
                              item.querySelector('a');
                
                let name = nameEl?.innerText?.trim() || nameEl?.textContent?.trim();
                if (name) name = name.replace(/\\n+/g, ' ').trim();
                
                let price = priceEl?.textContent?.trim();
                if (price) price = price.replace(/View retailers?/gi, '').trim();
                
                let whichUrl = null;
                if (linkEl && linkEl.href) {
                    whichUrl = linkEl.href.startsWith('http') 
                        ? linkEl.href 
                        : new URL(linkEl.href, window.location.origin).href;
                }
                
                return name && price ? {name, price, whichUrl, retailerLinks: []} : null;
            }).filter(Boolean)
        ''')
        
        all_products.extend(products)
        print(f"├─ Page {page_num}/{max_pages}: Found {len(products)} products")
    
    # Remove duplicates and parse prices
    seen = set()
    unique = []
    for p in all_products:
        if p['name'] not in seen:
            seen.add(p['name'])
            # Replace price string with parsed float
            p['price'] = parse_price(p['price'])
            unique.append(p)
    
    await page.close()
    await context.close()
    
    print(f"└─ Total: {len(unique)} unique products found\n")
    return unique


# ============= Phase 2: Specification and Image Extraction =============

async def extract_product_images(page) -> Dict[str, Optional[str]]:
    """
    Extract product images from Which.com product page.
    Returns dict with image URLs organized by view type (front, side, rear).
    """
    images = await page.evaluate('''
        () => {
            const images = [];
            
            // Get all .webp images from dam.which.co.uk at 800x600 resolution
            document.querySelectorAll('img').forEach(img => {
                if (img.src && img.src.includes('dam.which.co.uk') && 
                    img.src.includes('.webp') && img.src.includes('800x600')) {
                    images.push(img.src);
                }
            });
            
            // Remove duplicates and sort by view type
            const unique = [...new Set(images)];
            const sorted = unique.sort((a, b) => {
                const order = ['front', 'side', 'rear'];
                const getView = url => {
                    for (let view of order) {
                        if (url.includes(view)) return order.indexOf(view);
                    }
                    return 999;
                };
                return getView(a) - getView(b);
            });
            
            return {
                front: sorted.find(url => url.includes('front')) || null,
                side: sorted.find(url => url.includes('side')) || null,
                rear: sorted.find(url => url.includes('rear')) || null
            };
        }
    ''')
    
    return images


async def download_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """
    Download image from URL and return bytes.
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.read()
            else:
                print(f"    ✗ Failed to download {url.split('/')[-1]}: Status {response.status}")
                return None
    except Exception as e:
        print(f"    ✗ Error downloading {url.split('/')[-1]}: {e}")
        return None


async def download_product_images(image_urls: Dict[str, str]) -> Dict[str, bytes]:
    """
    Download all product images concurrently.
    """
    async with aiohttp.ClientSession() as session:
        tasks = {
            view: download_image(session, url)
            for view, url in image_urls.items() if url
        }
        
        if not tasks:
            return {}
        
        results = await asyncio.gather(*tasks.values())
        
        return {
            view: content 
            for view, content in zip(tasks.keys(), results) 
            if content
        }


def upload_to_supabase(
    supabase, 
    category: str, 
    product_slug: str, 
    images: Dict[str, bytes]
) -> Dict[str, str]:
    """
    Upload product images to Supabase Storage.
    Returns dict with Supabase URLs for each view.
    """
    import tempfile
    uploaded_urls = {}
    bucket_name = "product-images"
    
    for view, image_bytes in images.items():
        # Construct path in bucket with sanitized components
        sanitized_category = sanitize_filename(category)
        sanitized_view = sanitize_filename(view)
        file_path = f"{sanitized_category}/{product_slug}/{sanitized_view}.webp"
        
        try:
            # Supabase Python client needs a real file, not BytesIO
            # Create a temporary file
            with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            
            # Upload the temporary file
            with open(tmp_path, 'rb') as f:
                response = supabase.storage.from_(bucket_name).upload(
                    file_path,
                    f,
                    {"content-type": "image/webp", "upsert": "true"}
                )
            
            # Clean up temp file
            os.unlink(tmp_path)
            
            # Get public URL
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
            uploaded_urls[view] = public_url
            
        except Exception as e:
            print(f"    ✗ Failed to upload {view} image: {e}")
            uploaded_urls[view] = None
    
    return uploaded_urls


# ============= Phase 2: Specification Extraction =============

async def extract_specifications(page, skip_retailers: bool = False) -> Dict:
    """Extract specifications, features, and retailer links from product page"""
    await page.wait_for_timeout(500)
    
    # Try to click on "Where to buy" accordion button to expand it (if not skipping retailers)
    if not skip_retailers:
        try:
            # Click the accordion button
            await page.click('button[data-testid="accordion-item-button"]:has-text("Where to buy")', timeout=2000)

            # Wait for content to load after expansion
            await page.wait_for_timeout(2000)

            # Try to wait for the retailer list to be fully loaded
            try:
                await page.wait_for_selector('ul[data-testid="product-offers"] li', timeout=2000)
            except:
                pass
        except:
            pass  # Section might not exist or already be expanded
    
    result = await page.evaluate(f'''
        () => {{
            const skipRetailers = {str(skip_retailers).lower()};
            const specs = {{}};
            const features = {{}};
            const retailerLinks = [];

            // Simple function to clean obvious affiliate parameters
            function cleanObviousAffiliateParams(url) {{
                try {{
                    const urlObj = new URL(url);

                    // Amazon - remove tag and other affiliate params
                    if (urlObj.hostname.includes('amazon.co.uk')) {{
                        urlObj.searchParams.delete('tag');
                        urlObj.searchParams.delete('ascsubtag');
                        urlObj.searchParams.delete('linkCode');
                        return urlObj.toString();
                    }}

                    // Argos - remove tag parameter
                    if (urlObj.hostname.includes('argos.co.uk')) {{
                        urlObj.searchParams.delete('tag');
                        return urlObj.toString();
                    }}

                    // eBay - remove marketing parameters
                    if (urlObj.hostname.includes('ebay.co.uk')) {{
                        urlObj.searchParams.delete('mkevt');
                        urlObj.searchParams.delete('mkcid');
                        urlObj.searchParams.delete('mkrid');
                        urlObj.searchParams.delete('campid');
                        urlObj.searchParams.delete('toolid');
                        urlObj.searchParams.delete('customid');
                        return urlObj.toString();
                    }}

                    // Return original if not a known pattern
                    return url;
                }} catch (e) {{
                    return url;
                }}
            }}

            // Find all h3 headings once
            const allHeadings = document.querySelectorAll('h3');
            let buyHeading = null;
            let specHeading = null;

            // Find both headings in one pass
            for (const h of allHeadings) {{
                if (h.textContent.includes('Where to buy')) {{
                    buyHeading = h;
                }}
                if (h.textContent.includes('Specifications')) {{
                    specHeading = h;
                }}
            }}

            // Extract retailer offers (if not skipping)
            if (!skipRetailers && buyHeading) {{
                // Find the accordion section containing the offers
                let element = buyHeading.closest('[data-testid="accordion-item"]') || buyHeading.parentElement;
                let attempts = 0;

                while (element && attempts < 10) {{
                    const offersList = element.querySelector('ul[data-testid="product-offers"]');

                    if (offersList) {{
                        // Extract all retailer offers
                        const allListItems = offersList.querySelectorAll('li');

                        allListItems.forEach(li => {{
                            // Look for any link within the li - some use product-offer-card, others use trackonomics-link
                            const link = li.querySelector('a[data-testid="product-offer-card"]') ||
                                        li.querySelector('a[data-testid="trackonomics-link"]') ||
                                        li.querySelector('a[data-which-id="affiliate-link"]');

                            if (link) {{
                                const retailerEl = li.querySelector('[class*="retailerNameText"]');
                                const priceEl = li.querySelector('[data-testid="retailer-price"]');

                                const retailerName = retailerEl?.textContent?.trim();
                                const price = priceEl?.textContent?.trim();
                                const href = link.href;

                                if (retailerName && href) {{
                                    const cleanedUrl = cleanObviousAffiliateParams(href);
                                    retailerLinks.push({{
                                        name: retailerName,
                                        price: price || null,
                                        url: cleanedUrl
                                    }});
                                }}
                            }}
                        }});
                        break;
                    }}
                    element = element.nextElementSibling;
                    attempts++;
                }}
            }}

            // Extract specifications and features
            if (!specHeading) return {{ specs, features, retailerLinks }};
            
            // Find ALL tables after the specifications heading
            let element = specHeading.nextElementSibling;
            const tables = [];
            let attempts = 0;
            
            while (element && attempts < 10) {{
                if (element.tagName === 'TABLE') {{
                    tables.push(element);
                }} else {{
                    const innerTables = element.querySelectorAll('table');
                    innerTables.forEach(t => tables.push(t));
                }}
                element = element.nextElementSibling;
                attempts++;
            }}
            
            // Process tables - first is specs, second is features
            tables.forEach((table, index) => {{
                const targetObj = index === 0 ? specs : features;
                
                const rows = table.querySelectorAll('tr');
                for (const row of rows) {{
                    const cells = row.querySelectorAll('td, th');
                    if (cells.length === 2) {{
                        const key = cells[0].textContent.trim();
                        const value = cells[1].textContent.trim();
                        
                        if (key && value) {{
                            const cleanKey = key
                                .replace(/[:]/g, '')
                                .toLowerCase()
                                .replace(/[^a-z0-9]+/g, '_')
                                .replace(/^_|_$/g, '');
                            
                            if (cleanKey) {{
                                targetObj[cleanKey] = value;
                            }}
                        }}
                    }}
                }}
            }});
            
            return {{ specs, features, retailerLinks }};
        }}
    ''')
    
    # Add image extraction
    images = await extract_product_images(page)
    result['whichImageUrls'] = images  # Internal use only, not returned in final output
    
    return result


async def enrich_single_product(page, product: Dict, supabase=None, category=None, skip_retailers: bool = False) -> Dict:
    """Enrich a single product with specifications and optionally upload images"""
    url = product.get('whichUrl')
    if not url:
        return {**product, 'specs': {}, 'features': {}, 'retailerLinks': [], 'images': {}, 'specs_error': 'No Which.com URL'}
    
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        
        data = await extract_specifications(page, skip_retailers)
        specs = data.get('specs', {})
        features = data.get('features', {})
        retailerLinks = data.get('retailerLinks', [])
        whichImageUrls = data.get('whichImageUrls', {})

        # Update with the new retailer links (array with prices)
        if retailerLinks:
            product['retailerLinks'] = retailerLinks
        
        # Download and upload images if Supabase client provided
        supabase_image_urls = {}
        if supabase and category and whichImageUrls:
            # Check if any images were found
            valid_images = {k: v for k, v in whichImageUrls.items() if v}
            if valid_images:
                # Download images
                downloaded = await download_product_images(valid_images)
                
                if downloaded:
                    # Generate product slug from name using sanitization function
                    product_slug = sanitize_filename(product['name'])

                    # Upload to Supabase
                    supabase_image_urls = upload_to_supabase(
                        supabase,
                        category,
                        product_slug,
                        downloaded
                    )
        
        return {
            **product,
            'specs': specs,
            'features': features,
            'images': supabase_image_urls  # Only return Supabase URLs, not Which URLs
        }
    except Exception as e:
        return {
            **product,
            'specs': {},
            'features': {},
            'images': {},
            'retailerLinks': [],
            'specs_error': str(e)
        }


async def worker_enrich_chunk(worker_id: int, products_chunk: List[Dict], browser, supabase=None, category=None, skip_retailers: bool = False) -> List[Dict]:
    """Worker that enriches its assigned chunk of products with optional image upload"""
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    page = await context.new_page()
    
    results = []
    for i, product in enumerate(products_chunk, 1):
        result = await enrich_single_product(page, product, supabase, category, skip_retailers)
        results.append(result)
        specs = result.get('specs', {})
        status = "✓" if specs else "✗"
        print(f"├─ Worker {worker_id + 1}: [{i}/{len(products_chunk)}] {status} {product.get('name', 'Unknown')}")
    
    await page.close()
    await context.close()
    
    return results


async def enrich_specs_phase(browser, products: List[Dict], workers: int = 3, supabase=None, category=None, skip_retailers: bool = False) -> List[Dict]:
    """
    Phase 2: Enrich products with specifications and images using parallel workers
    """
    print("="*60)
    if supabase:
        print("PHASE 2: Specification and Image Extraction")
    else:
        print("PHASE 2: Specification Extraction")
    print("="*60)
    
    if not products:
        return []
    
    # Calculate chunk size and split products evenly
    chunk_size = len(products) // workers + (1 if len(products) % workers else 0)
    chunks = [products[i:i + chunk_size] for i in range(0, len(products), chunk_size)]
    
    print(f"Starting {len(chunks)} workers for {len(products)} products...")
    
    # Create tasks for each worker
    tasks = [
        worker_enrich_chunk(i, chunk, browser, supabase, category, skip_retailers)
        for i, chunk in enumerate(chunks)
    ]
    
    # Run all workers in parallel
    all_results = await asyncio.gather(*tasks)
    
    # Flatten results from all workers
    enriched_products = [item for worker_results in all_results for item in worker_results]
    
    # Summary
    successful = sum(1 for p in enriched_products if p.get('specs'))
    total_specs = sum(len(p.get('specs', {})) for p in enriched_products)
    total_features = sum(len(p.get('features', {})) for p in enriched_products)
    
    print(f"└─ Completed: {successful}/{len(enriched_products)} products enriched")
    print(f"   Total specs: {total_specs}, Total features: {total_features}\n")
    
    return enriched_products


# ============= Main Pipeline =============

async def main(url: str, pages, workers: int, skip_specs: bool, output_file: str, download_images: bool = False, storage_bucket: str = "product-images", skip_retailers: bool = False):
    """Main pipeline coordinator with optional image storage"""
    print(f"\nWhich.com Complete Scraper Pipeline")
    print(f"URL: {url}")
    print(f"Pages: {pages}")
    print(f"Workers: {workers}")
    print(f"Skip specs: {skip_specs}")
    print(f"Skip retailers: {skip_retailers}")
    print(f"Download images: {download_images}")
    
    # Initialize Supabase if image download enabled
    supabase = None
    category = None
    if download_images:
        try:
            from supabase import create_client
            supabase_url = os.environ.get("SUPABASE_URL")
            supabase_key = os.environ.get("SUPABASE_KEY")
            
            if not supabase_url or not supabase_key:
                print("⚠️  Warning: SUPABASE_URL or SUPABASE_KEY not set. Skipping image upload.")
                download_images = False
            else:
                supabase = create_client(supabase_url, supabase_key)
                # Extract category from URL
                category = url.split('/reviews/')[-1].split('/')[0].split('?')[0]
                print(f"Category detected: {category}")
                
                # Ensure bucket exists - skip check as list_buckets may not work with anon key
                # The bucket 'product-images' should already exist
                print(f"Using storage bucket: {storage_bucket}")
        except ImportError:
            print("⚠️  Warning: supabase package not installed. Run: pip install supabase")
            download_images = False
    
    # Single browser instance for entire pipeline
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # Phase 1: Scrape products
        products = await scrape_products_phase(browser, url, pages)
        
        # Phase 2: Enrich with specs and images (if enabled)
        if not skip_specs and products:
            products = await enrich_specs_phase(browser, products, workers, supabase, category, skip_retailers)
        
        await browser.close()
    
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
    
    # Add spec stats if specs were extracted
    if not skip_specs:
        successful = sum(1 for p in products if p.get('specs'))
        total_specs = sum(len(p.get('specs', {})) for p in products)
        total_features = sum(len(p.get('features', {})) for p in products)
        
        # Add image stats if images were processed
        if download_images:
            products_with_images = sum(1 for p in products if p.get('images'))
            total_images = sum(len(p.get('images', {})) for p in products)
        
        output_data.update({
            'successful_enriched': successful,
            'failed_enriched': len(products) - successful,
            'total_specs_extracted': total_specs,
            'total_features_extracted': total_features
        })
        
        if download_images:
            output_data.update({
                'products_with_images': products_with_images,
                'total_images_uploaded': total_images
            })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Final summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✓ Results saved to {output_path}")
    print(f"  • Products found: {len(products)}")
    
    # Check for price parsing issues
    zero_price_count = sum(1 for p in products if p.get('price', 0) == 0)
    if zero_price_count > 0:
        print(f"  • Warning: {zero_price_count} products have price 0 (parsing failed)")
    
    if not skip_specs and products:
        print(f"  • Successfully enriched: {successful}/{len(products)}")
        print(f"  • Total specs extracted: {total_specs}")
        print(f"  • Total features extracted: {total_features}")
        
        if download_images:
            print(f"  • Products with images: {products_with_images}/{len(products)}")
            print(f"  • Total images uploaded: {total_images}")
    
    products_with_urls = sum(1 for p in products if p.get('whichUrl'))
    print(f"  • Products with Which.com URLs: {products_with_urls}/{len(products)}")
    
    # Generate metadata for the scraped data
    print("\nGenerating metadata for searchability...")
    try:
        import subprocess
        result = subprocess.run(['python', 'generate_metadata.py', output_path], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ Metadata generated successfully")
        else:
            print(f"⚠ Metadata generation failed: {result.stderr}")
    except Exception as e:
        print(f"⚠ Could not generate metadata: {e}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Complete Which.com Scraper Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all air fryer pages with specs
  python complete_scraper.py --url "https://www.which.co.uk/reviews/air-fryers" --pages all
  
  # Scrape 5 pages of washing machines with 8 workers
  python complete_scraper.py --url "https://www.which.co.uk/reviews/washing-machines" --pages 5 --workers 8
  
  # Just get product listings without specs
  python complete_scraper.py --url "https://www.which.co.uk/reviews/tvs" --pages 3 --skip-specs
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
                       help='Skip specification extraction, only get products')
    parser.add_argument('--output', '-o',
                       default='complete_products.json',
                       help='Output JSON file (default: complete_products.json)')
    parser.add_argument('--download-images', '-d',
                       action='store_true',
                       help='Download and upload product images to Supabase storage')
    parser.add_argument('--storage-bucket',
                       default='product-images',
                       help='Supabase storage bucket name (default: product-images)')
    parser.add_argument('--skip-retailers', '-r',
                       action='store_true',
                       help='Skip retailer price extraction (enabled by default)')

    args = parser.parse_args()
    
    # Convert pages to int if not "all"
    if args.pages.lower() == 'all':
        pages_arg = 'all'
    else:
        try:
            pages_arg = int(args.pages)
        except ValueError:
            print(f"Error: --pages must be a number or 'all', got '{args.pages}'")
            exit(1)
    
    asyncio.run(main(
        args.url,
        pages_arg,
        args.workers,
        args.skip_specs,
        args.output,
        args.download_images,
        args.storage_bucket,
        args.skip_retailers
    ))