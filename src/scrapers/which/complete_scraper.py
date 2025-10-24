#!/usr/bin/env python3
"""
Complete Which.com Scraper Pipeline
Combines product discovery and specification extraction in a single efficient pipeline
Now includes image extraction, optional Supabase storage, and AO.com enrichment
"""
import asyncio
import argparse
import json
import os
import io
import sys
import aiohttp
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Add the project root to sys.path for src imports
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent.parent
sys.path.insert(0, str(project_root))

# Import retailer enrichment orchestrator
from src.scrapers.retailers.orchestrator import RetailerEnrichmentOrchestrator

# Import PDF enrichment module
from src.scrapers.pdf import enrich_pdf_phase, get_enrichment_gap

# Import review enrichment orchestrator
from src.reviews.orchestrator import ReviewEnrichmentOrchestrator


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


# ============= Phase 2: Base Specification Extraction =============

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


# ============= Specification Extraction Helpers =============

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

                    // Skip sanitization for tracking/redirect URLs - they need all params to work
                    const trackingDomains = ['clicks.trx-hub.com', 'awin1.com', 'trx-hub.com'];
                    if (trackingDomains.some(domain => urlObj.hostname.includes(domain))) {{
                        return url;  // Return as-is, don't sanitize tracking URLs
                    }}

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


# ============= Phase 3: Retailer Link Discovery =============

async def worker_search_retailer_links(
    worker_id: int,
    products_chunk: List[Dict],
    browser
) -> List[Dict]:
    """
    Worker that extracts retailer links from search results for products without Which.com retailer links.

    Args:
        worker_id: Worker identifier
        products_chunk: Chunk of products to process
        browser: Shared browser instance (not used, as we need sync Playwright for link extractor)

    Returns:
        List of enriched products with retailerLinks added
    """
    from src.scrapers.manufacturers.link_extractor import get_retailer_links_with_prices
    from playwright.sync_api import sync_playwright
    import asyncio

    # Run the entire worker in executor to avoid async/sync conflicts
    def worker_sync():
        """Synchronous worker function that processes all products in the chunk."""
        playwright_sync = sync_playwright().start()
        results = []

        try:
            browser_sync = playwright_sync.chromium.launch(
                headless=False,  # DuckDuckGo blocks headless
                args=['--disable-blink-features=AutomationControlled']
            )
            context_sync = browser_sync.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page_sync = context_sync.new_page()

            for i, product in enumerate(products_chunk, 1):
                product_name = product.get('name', 'Unknown')

                try:
                    # Extract retailer links with prices
                    retailer_links = get_retailer_links_with_prices(page_sync, product_name, count=5)

                    if retailer_links:
                        product['retailerLinks'] = retailer_links
                        print(f"├─ Worker {worker_id}: [{i}/{len(products_chunk)}] {product_name[:40]}... ✓ {len(retailer_links)} links")
                    else:
                        print(f"├─ Worker {worker_id}: [{i}/{len(products_chunk)}] {product_name[:40]}... ✗ No links found")

                except Exception as e:
                    print(f"├─ Worker {worker_id}: [{i}/{len(products_chunk)}] {product_name[:40]}... ✗ Error: {e}")

                results.append(product)

            browser_sync.close()

        except Exception as e:
            print(f"Worker {worker_id} fatal error: {e}")
            # Return products as-is if worker fails
            results = products_chunk

        finally:
            playwright_sync.stop()

        return results

    # Run in executor to allow async main function to continue
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, worker_sync)

    return results


async def enrich_search_retailer_links_phase(browser, products: List[Dict], workers: int = 2) -> List[Dict]:
    """
    Phase 3: Extract retailer links from search results for products without Which.com retailer links.

    This phase runs after base spec extraction and fills in retailer links for products where
    Which.com didn't provide any "Where to buy" information.

    Args:
        browser: Shared browser instance
        products: List of products
        workers: Number of parallel workers (default: 2, fewer due to DuckDuckGo rate limiting)

    Returns:
        Products with retailerLinks added where missing
    """
    print("="*60)
    print("PHASE 3: Retailer Link Discovery")
    print("="*60)

    if not products:
        return []

    # Filter products without retailer links
    products_without_links = [p for p in products if not p.get('retailerLinks') or len(p.get('retailerLinks', [])) == 0]
    products_with_links = [p for p in products if p.get('retailerLinks') and len(p.get('retailerLinks', [])) > 0]

    print(f"Found {len(products_without_links)} products without retailer links")

    if not products_without_links:
        print("└─ All products already have retailer links, skipping search extraction\n")
        return products

    # Calculate chunk size and split products evenly
    chunk_size = len(products_without_links) // workers + (1 if len(products_without_links) % workers else 0)
    chunks = [products_without_links[i:i + chunk_size] for i in range(0, len(products_without_links), chunk_size)]

    print(f"Starting {len(chunks)} workers for {len(products_without_links)} products...")
    print(f"Note: Using visible browsers (DuckDuckGo blocks headless)")

    # Create tasks for each worker
    tasks = [
        worker_search_retailer_links(i + 1, chunk, browser)
        for i, chunk in enumerate(chunks)
    ]

    # Run all workers in parallel
    all_results = await asyncio.gather(*tasks)

    # Flatten results from all workers
    enriched_products = []
    for worker_results in all_results:
        enriched_products.extend(worker_results)

    # Combine enriched and already-had-links products
    all_products = enriched_products + products_with_links

    # Calculate summary statistics
    successful = sum(1 for p in enriched_products if p.get('retailerLinks'))
    total_links = sum(len(p.get('retailerLinks', [])) for p in enriched_products)

    print(f"└─ Completed: {successful}/{len(products_without_links)} products enriched with retailer links")
    print(f"   Total links added: {total_links}\n")

    return all_products


# ============= Phase 4: Retailer Spec Enrichment =============

async def worker_retailer_enrich_chunk(
    worker_id: int,
    products_chunk: List[Dict],
    browser,
    orchestrator: RetailerEnrichmentOrchestrator
) -> Tuple[List[Dict], List[Dict]]:
    """
    Worker that enriches products with retailer data using the orchestrator.

    Returns:
        Tuple of (enriched_products, stats_list)
    """
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()

    results = []
    stats_list = []

    for i, product in enumerate(products_chunk, 1):
        # Use orchestrator to enrich product
        enriched_product, enrichment_stats = await orchestrator.enrich_product(product, page)
        results.append(enriched_product)
        stats_list.append(enrichment_stats)

        # Display progress
        if enrichment_stats.get('success'):
            source = enrichment_stats.get('source', 'unknown')
            spec_count = enrichment_stats.get('spec_count', 0)
            print(f"├─ Worker {worker_id + 1}: [{i}/{len(products_chunk)}] {product.get('name', 'Unknown')[:35]}... ✓ +{source} ({spec_count} specs)")
        else:
            print(f"├─ Worker {worker_id + 1}: [{i}/{len(products_chunk)}] {product.get('name', 'Unknown')[:35]}... ✗")

    await page.close()
    await context.close()

    return results, stats_list


async def enrich_retailer_phase(browser, products: List[Dict], workers: int = 3) -> List[Dict]:
    """
    Phase 4: Enrich products with retailer specifications using orchestrator.

    Uses intelligent retailer selection based on:
    - Availability of retailer links
    - Priority order from config
    - Fallback chain if primary fails
    """
    print("="*60)
    print("PHASE 4: Retailer Spec Enrichment")
    print("="*60)

    if not products:
        return []

    # Initialize orchestrator
    orchestrator = RetailerEnrichmentOrchestrator()

    # Display orchestrator info
    stats = orchestrator.get_stats()
    print(f"Orchestrator: {stats['enabled_scrapers']}/{stats['registered_scrapers']} scrapers enabled")
    print(f"Priority order: {', '.join(stats['config']['priority_order'][:3])}...")

    # Filter products that have retailer links
    products_with_links = [p for p in products if p.get('retailerLinks')]
    products_without_links = [p for p in products if not p.get('retailerLinks')]

    print(f"Found {len(products_with_links)} products with retailer links")

    if not products_with_links:
        print("└─ No retailer links found, skipping retailer enrichment\n")
        return products

    # Calculate chunk size and split products evenly
    chunk_size = len(products_with_links) // workers + (1 if len(products_with_links) % workers else 0)
    chunks = [products_with_links[i:i + chunk_size] for i in range(0, len(products_with_links), chunk_size)]

    print(f"Starting {len(chunks)} workers for {len(products_with_links)} products...")

    # Create tasks for each worker
    tasks = [
        worker_retailer_enrich_chunk(i, chunk, browser, orchestrator)
        for i, chunk in enumerate(chunks)
    ]

    # Run all workers in parallel
    all_results = await asyncio.gather(*tasks)

    # Flatten results from all workers
    enriched_products = []
    all_stats = []
    for products_result, stats_result in all_results:
        enriched_products.extend(products_result)
        all_stats.extend(stats_result)

    # Combine enriched and non-enriched products
    all_products = enriched_products + products_without_links

    # Calculate summary statistics
    successful = sum(1 for s in all_stats if s.get('success'))
    total_specs_added = sum(s.get('spec_count', 0) for s in all_stats if s.get('success'))

    # Count by source
    sources = {}
    for s in all_stats:
        if s.get('success'):
            source = s.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1

    print(f"└─ Completed: {successful}/{len(products_with_links)} products enriched with retailer data")
    print(f"   Sources: {', '.join(f'{k}={v}' for k, v in sources.items())}")
    print(f"   Total specs added: {total_specs_added}\n")

    return all_products


# ============= Phase 6: Review Enrichment =============

async def worker_review_enrich_chunk(
    worker_id: int,
    products_chunk: List[Dict],
    browser,
    orchestrator: ReviewEnrichmentOrchestrator
) -> Tuple[List[Dict], Dict]:
    """
    Worker that enriches products with reviews using the orchestrator.

    Returns:
        Tuple of (enriched_products, stats)
    """
    # Create context and page for this worker (SAME as old enricher)
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = await context.new_page()

    results = []
    stats = {'successful': 0, 'failed': 0}

    for i, product in enumerate(products_chunk, 1):
        enriched_product = await orchestrator.enrich_product(product, page=page)
        results.append(enriched_product)

        # Track stats
        if enriched_product.get('reviews'):
            stats['successful'] += 1
            # Note: No longer tracking source since we removed that field
            product_name = product.get('name', 'Unknown')[:40]
            print(f"├─ Worker {worker_id + 1}: [{i}/{len(products_chunk)}] {product_name}... ✓")
        else:
            stats['failed'] += 1

    await page.close()
    await context.close()

    return results, stats


async def enrich_review_phase(products: List[Dict], workers: int = 3, browser=None) -> List[Dict]:
    """
    Phase 6: Enrich products with review sentiment from AO or Boots.

    Priority:
    1. AO.com (search-based using product name)
    2. Boots (direct URL from retailerLinks)
    3. None (skip if no matching retailers)

    Args:
        products: List of products to enrich
        workers: Number of parallel workers (default: 3)
        browser: Shared browser instance

    Returns:
        Products with 'reviews' field added
    """
    print("="*60)
    print("PHASE 6: Review Enrichment")
    print("="*60)

    if not products:
        return []

    # Initialize orchestrator
    orchestrator = ReviewEnrichmentOrchestrator()
    stats_info = orchestrator.get_stats()
    print(f"Orchestrator: {', '.join(stats_info['priority_order'])}")

    # Filter products that have retailer links (AO, Boots, or Amazon)
    def has_review_source(product):
        retailer_links = product.get('retailerLinks', [])
        for link in retailer_links:
            name = link.get('name', '').lower()
            if 'ao' in name or 'boots' in name or 'amazon' in name:
                return True
        return False

    products_with_links = [p for p in products if has_review_source(p)]
    products_without_links = [p for p in products if not has_review_source(p)]

    print(f"Found {len(products_with_links)} products with review sources")

    if not products_with_links:
        print("└─ No review sources found, skipping review enrichment\n")
        return products

    # Split products into chunks for parallel processing
    chunk_size = len(products_with_links) // workers + (1 if len(products_with_links) % workers else 0)
    chunks = [products_with_links[i:i + chunk_size] for i in range(0, len(products_with_links), chunk_size)]

    print(f"Starting {len(chunks)} workers for {len(products_with_links)} products...")

    # Create tasks for each worker (pass browser like old enricher)
    tasks = [
        worker_review_enrich_chunk(i, chunk, browser, orchestrator)
        for i, chunk in enumerate(chunks)
    ]

    # Run all workers in parallel
    all_results = await asyncio.gather(*tasks)

    # Flatten results and aggregate stats
    enriched_products = []
    total_stats = {'successful': 0, 'failed': 0}

    for products_result, worker_stats in all_results:
        enriched_products.extend(products_result)
        for key in total_stats:
            total_stats[key] += worker_stats[key]

    # Combine enriched and non-enriched products
    all_products = enriched_products + products_without_links

    # Print summary
    print(f"└─ Completed: {total_stats['successful']}/{len(products_with_links)} products enriched")
    print(f"   Failed: {total_stats['failed']}\n")

    return all_products


# ============= Phase 7: AI Spec Enrichment (Gemini) =============

async def enrich_manufacturer_phase(products: List[Dict], gemini_workers: int = 2, link_workers: int = 2) -> List[Dict]:
    """
    Phase 7: Enrich products that failed retailer enrichment with Gemini manufacturer scraper.

    NEW ARCHITECTURE:
    1. Batch extract links for all failed products (parallel, headless, fast)
    2. Gemini scraping with pre-fetched links (no search waste, fallback URLs)

    This is more efficient than the old approach:
    - Saves 5-6 Gemini turns per product (no DuckDuckGo search)
    - Enables fallback to 2nd/3rd URLs if first fails (CAPTCHA/no specs)
    - Faster link extraction (5+ parallel workers, headless)

    Args:
        products: List of products
        gemini_workers: Number of parallel Gemini workers (default 2)
        link_workers: Number of parallel link extraction workers (default 5)

    Returns:
        Products with manufacturer enrichment
    """
    import asyncio
    from src.scrapers.manufacturers.gemini_agent import create_scraper_session, scrape_with_urls
    from src.scrapers.manufacturers.link_extractor import batch_extract_links

    # Find products that failed retailer enrichment
    failed_products = [p for p in products if not p.get('retailerEnrichmentSource')]

    if not failed_products:
        print("\n✓ All products have retailer enrichment, skipping Gemini phase")
        return products

    print(f"\n{'='*60}")
    print(f"PHASE 4: Gemini Manufacturer Enrichment (With Pre-Fetched Links)")
    print(f"{'='*60}")
    print(f"Orchestrator: {len(failed_products)} products failed retailer enrichment")

    # PHASE 4a: Batch extract links (parallel, visible browsers)
    # NOTE: Using headless=False because DuckDuckGo detects headless browsers
    print(f"\n[Phase 4a] Extracting manufacturer links with {link_workers} workers...")
    print(f"  (Using visible browsers - DuckDuckGo blocks headless)")
    link_map = batch_extract_links(
        products=failed_products,
        workers=link_workers,
        headless=False,  # Must use visible browsers for DuckDuckGo
        links_per_product=3  # Get 3 URLs per product for fallback
    )

    # PHASE 4b: Gemini scraping with pre-fetched links
    print(f"\n[Phase 4b] Gemini scraping with {gemini_workers} workers...")

    # Split products among workers
    def chunk_products(products_list, num_chunks):
        """Split products into roughly equal chunks"""
        if num_chunks == 0:
            return []
        if num_chunks >= len(products_list):
            # If more workers than products, give each product its own chunk
            return [[p] for p in products_list]

        chunk_size = len(products_list) // num_chunks
        remainder = len(products_list) % num_chunks

        chunks = []
        start = 0
        for i in range(num_chunks):
            size = chunk_size + (1 if i < remainder else 0)
            chunks.append(products_list[start:start + size])
            start += size

        return chunks

    product_chunks = chunk_products(failed_products, gemini_workers)

    # Worker function (runs in thread, not async)
    def gemini_worker(worker_id: int, product_chunk: List[Dict]):
        """Worker that maintains one browser session and processes multiple products"""
        print(f"├─ Worker {worker_id}: Starting ({len(product_chunk)} products)")

        successful = 0
        failed = 0

        try:
            # Create persistent session
            playwright, browser, page, client = create_scraper_session(headless=True)

            for i, product in enumerate(product_chunk, 1):
                product_name = product.get('name', 'Unknown')
                print(f"├─ Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}...")

                try:
                    # Get pre-fetched URLs for this product
                    urls = link_map.get(product_name, [])

                    if not urls:
                        print(f"├─ Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}... ✗ No URLs found")
                        failed += 1
                        continue

                    # Scrape with pre-fetched URLs (tries all 3 with fallback)
                    result = scrape_with_urls(page, client, product_name, urls)

                    if result['status'] == 'success' and result.get('specs'):
                        # Merge specs: manufacturer fills gaps, Which.com wins conflicts
                        which_specs = product.get('specs', {})
                        manufacturer_specs = result['specs']
                        merged_specs = {**manufacturer_specs, **which_specs}

                        product['specs'] = merged_specs
                        product['retailerEnrichmentUrl'] = result['source_url']
                        product['retailerEnrichmentSource'] = 'Gemini Manufacturer'

                        successful += 1
                        print(f"├─ Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}... ✓ +Gemini ({len(result['specs'])} specs)")
                    else:
                        failed += 1
                        error_msg = result.get('error', 'Unknown error')
                        print(f"├─ Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}... ✗ {error_msg}")

                except Exception as e:
                    failed += 1
                    print(f"├─ Worker {worker_id}: [{i}/{len(product_chunk)}] {product_name}... ✗ Error: {e}")

            # Cleanup
            browser.close()
            playwright.stop()

        except Exception as e:
            print(f"├─ Worker {worker_id}: Fatal error: {e}")
            failed = len(product_chunk)

        return {'worker_id': worker_id, 'successful': successful, 'failed': failed}

    # Run workers in parallel using thread pool
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, gemini_worker, i+1, chunk)
        for i, chunk in enumerate(product_chunks)
    ]

    # Wait for all workers to complete
    results = await asyncio.gather(*tasks)

    # Print summary
    total_successful = sum(r['successful'] for r in results)
    total_failed = sum(r['failed'] for r in results)

    print(f"\n└─ Completed: {total_successful}/{len(failed_products)} products enriched with manufacturer data")
    print(f"   Sources: Gemini Manufacturer={total_successful}")
    total_specs_added = sum(len(p.get('specs', {})) for p in failed_products if p.get('retailerEnrichmentSource') == 'Gemini Manufacturer')
    print(f"   Total specs added: {total_specs_added}\n")

    return products


# ============= Main Pipeline =============

async def main(url: str, pages, workers: int, skip_specs: bool, output_file: str, download_images: bool = False, storage_bucket: str = "product-images", skip_retailers: bool = False, enrich_retailers: bool = False, retailer_workers: int = 3, gemini_workers: int = 2, enrich_reviews: bool = False, review_workers: int = 3, skip_standardization: bool = False, skip_db_insert: bool = True, skip_metadata: bool = False):
    """Main pipeline coordinator with optional image storage and retailer enrichment"""
    print(f"\nWhich.com Complete Scraper Pipeline")
    print(f"URL: {url}")
    print(f"Pages: {pages}")
    print(f"Workers: {workers}")
    print(f"Skip specs: {skip_specs}")
    print(f"Skip retailers: {skip_retailers}")
    print(f"Download images: {download_images}")
    print(f"Retailer enrichment: {enrich_retailers}")
    if enrich_retailers:
        print(f"Retailer workers: {retailer_workers}")
        print(f"Gemini workers: {gemini_workers}")
    print(f"Review enrichment: {enrich_reviews}")
    if enrich_reviews:
        print(f"Review workers: {review_workers}")
    
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

            # Store Which.com baseline for enrichment target calculation
            for product in products:
                product['_whichSpecsCount'] = len(product.get('specs', {}))

        # Phase 3: Extract retailer links from search for products without Which.com retailer links
        if products and not skip_retailers:
            products = await enrich_search_retailer_links_phase(browser, products, workers=2)

        # Phase 4: Enrich with retailer specs (if enabled)
        if enrich_retailers and products and not skip_specs:
            products = await enrich_retailer_phase(browser, products, retailer_workers)

        # Phase 5: PDF enrichment for products where retailer failed (only if doing retailer enrichment)
        if enrich_retailers and products and not skip_specs:
            print(f"\n{'='*80}")
            print(f"PHASE 5: PDF Spec Enrichment")
            print(f"{'='*80}")
            pdf_candidates = [p for p in products if not p.get('retailerEnrichmentSource')]
            if pdf_candidates:
                print(f"Running PDF enrichment for {len(pdf_candidates)} products where retailer failed...")
                print(f"Target: Add >= 50% of Which.com baseline specs per product")
                products = await enrich_pdf_phase(browser, products, workers=3)
            else:
                print("No products need PDF enrichment - all have retailer specs")

        # Phase 6: Review enrichment (if enabled)
        if enrich_reviews and products:
            products = await enrich_review_phase(products, review_workers, browser)

        # Phase 7: AI Spec Enrichment with Gemini (only for products with remaining gap)
        if enrich_retailers and products and not skip_specs and gemini_workers > 0:
            # Check which products still need Gemini supplementation
            gemini_candidates = [p for p in products if not p.get('retailerEnrichmentSource') and get_enrichment_gap(p) > 0]

            if gemini_candidates:
                print(f"\n{'='*80}")
                print(f"PHASE 7: AI Spec Enrichment (Gemini)")
                print(f"{'='*80}")
                print(f"Supplementing {len(gemini_candidates)} products where PDF didn't reach 50% threshold...")
                for p in gemini_candidates:
                    gap = get_enrichment_gap(p)
                    pdf_added = p.get('pdfEnrichment', {}).get('specsCount', 0)
                    print(f"  - {p['name'][:50]}: PDF added {pdf_added}, need {gap:.0f} more from Gemini")

                # Create a product map for merging results
                product_map = {p['name']: p for p in products}

                # Only enrich the candidates that need it
                enriched_candidates = await enrich_manufacturer_phase(gemini_candidates, gemini_workers)

                # Merge enriched candidates back into the main product list
                for enriched in enriched_candidates:
                    product_map[enriched['name']] = enriched

                # Reconstruct products list with updated data
                products = [product_map[p['name']] for p in products]
            else:
                print(f"\n{'='*80}")
                print("PHASE 7: AI Spec Enrichment (Gemini) - SKIPPED")
                print(f"{'='*80}")
                print("All products either have retailer specs or PDF reached 50% threshold!")

        await browser.close()

    # Save results (need to save first for standardization to use as input)
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

    # Phase 8: Data Standardization (if enabled)
    std_paths = None
    if not skip_standardization and not skip_specs and products:
        print(f"\n{'='*80}")
        print("PHASE 8: Data Standardization")
        print(f"{'='*80}")

        try:
            from src.standardization.config import get_pipeline_paths
            from src.standardization.cli import run_pipeline as run_std_pipeline

            # Get standardized paths from raw output
            std_paths = get_pipeline_paths(str(output_path))

            print(f"Standardizing {len(products)} products...")
            print(f"Input: {std_paths['input']}")
            print(f"Output: {std_paths['output']}")
            print()

            # Run standardization (all 4 steps: analyze, generate map, transform, validate)
            run_std_pipeline(
                input_file=str(output_path),
                force_regenerate=False,
                verbose=False,
                min_coverage_percent=10  # Filter out keys with <10% coverage
            )

            print(f"\n✓ Standardization complete")
            print(f"  • Key analysis: {std_paths['key_analysis']}")
            print(f"  • Unification map: {std_paths['unification_map']}")
            print(f"  • Standardized output: {std_paths['output']}")

        except Exception as e:
            print(f"\n⚠️  Standardization failed: {e}")
            print("   Raw data still available in output file")
            import traceback
            traceback.print_exc()
            std_paths = None

    # Phase 9: Metadata Generation (if not skipped)
    metadata_path = None
    if not skip_metadata and not skip_specs and products:
        print(f"\n{'='*80}")
        print("PHASE 9: Metadata Generation")
        print(f"{'='*80}")

        try:
            from src.utils.metadata_generator import ProductMetadataGenerator

            # Use standardized data if available, otherwise use raw data
            input_for_metadata = std_paths['output'] if std_paths else output_path

            print(f"Generating metadata from: {input_for_metadata}")

            # Generate metadata (pass file path, not products list)
            generator = ProductMetadataGenerator()
            metadata = generator.generate_metadata(str(input_for_metadata))

            # Save metadata
            metadata_path = input_for_metadata.parent / f"{input_for_metadata.stem}.metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            print(f"✓ Metadata generated successfully")
            print(f"  • Output: {metadata_path}")
            print(f"  • Unique spec fields: {len(metadata.get('field_values', {}).get('specs', {}))}")
            print(f"  • Unique feature fields: {len(metadata.get('field_values', {}).get('features', {}))}")

        except Exception as e:
            print(f"\n⚠️  Metadata generation failed: {e}")
            import traceback
            traceback.print_exc()
            metadata_path = None

    # Phase 10: Database Insertion (if not skipped)
    db_stats = None
    if not skip_db_insert and products:
        print(f"\n{'='*80}")
        print("PHASE 10: Database Insertion")
        print(f"{'='*80}")

        try:
            from src.database.inserters.products import insert_products
            from src.database.inserters.metadata import insert_metadata

            # Extract category from URL
            category = url.split('/reviews/')[-1].split('/')[0].split('?')[0]

            # Use standardized data if available, otherwise use raw data
            data_for_db = None
            if std_paths:
                print(f"Inserting standardized data from: {std_paths['output']}")
                with open(std_paths['output'], encoding='utf-8') as f:
                    data_for_db = json.load(f)
            else:
                print(f"Inserting raw data from: {output_path}")
                data_for_db = output_data

            # Insert products
            print(f"Inserting {len(data_for_db['products'])} products to category '{category}'...")
            product_stats = insert_products(data_for_db, category)

            print(f"✓ Products inserted successfully")
            print(f"  • Inserted: {product_stats.get('inserted', 0)}")
            print(f"  • Updated: {product_stats.get('updated', 0)}")
            print(f"  • Skipped: {product_stats.get('skipped', 0)}")

            # Insert metadata if available
            if metadata_path:
                print(f"\nInserting metadata from: {metadata_path}")
                with open(metadata_path, encoding='utf-8') as f:
                    metadata_data = json.load(f)

                metadata_stats = insert_metadata(metadata_data, category)
                print(f"✓ Metadata inserted successfully")
                print(f"  • Spec fields: {metadata_stats.get('spec_fields', 0)}")
                print(f"  • Feature fields: {metadata_stats.get('feature_fields', 0)}")

                db_stats = {**product_stats, **metadata_stats}
            else:
                db_stats = product_stats

        except Exception as e:
            print(f"\n⚠️  Database insertion failed: {e}")
            import traceback
            traceback.print_exc()
            db_stats = None

    # Final summary
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
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

    # Standardization summary
    if std_paths:
        print()
        print(f"📁 Standardized data: {std_paths['output']}")
        print(f"   ✓ Specs/features cleaned and unified")

    # Metadata summary
    if metadata_path:
        print(f"📁 Metadata: {metadata_path}")

    # Database insertion summary
    if db_stats:
        print()
        print(f"💾 Database: Products and metadata inserted to Supabase")
        print(f"   • Inserted: {db_stats.get('inserted', 0)}")
        print(f"   • Updated: {db_stats.get('updated', 0)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Complete Which.com Scraper Pipeline with 10-Phase Data Collection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Phases:
  Data Collection (1-7):
    1. Product Discovery - Which.com listings (always runs)
    2. Base Spec Extraction - Which.com specs (use --skip-specs to disable)
    3. Retailer Link Discovery - DuckDuckGo search (always runs with specs)
    4-5. Retailer & PDF Enrichment - Additional specs [--enrich-retailers]
    6. Review Enrichment - Customer reviews [--enrich-reviews]
    7. AI Enrichment - Gemini fallback [--enrich-ai]

  Data Processing & Persistence (8-10):
    8. Data Standardization - Clean/unify data [runs by default, --no-standardization to skip]
    9. Metadata Generation - Extract field values [runs by default, --no-metadata to skip]
   10. Database Insertion - Persist to Supabase [--save-to-db to enable]

Examples:
  # Basic scraping (JSON output only)
  python complete_scraper.py --url "https://www.which.co.uk/reviews/air-fryers" --pages 2

  # Full enrichment pipeline with database
  python complete_scraper.py --pages all --enrich-retailers --enrich-reviews --save-to-db

  # Maximum enrichment (all phases including AI)
  python complete_scraper.py --pages all --enrich-retailers --enrich-reviews --enrich-ai --save-to-db

  # Fast mode: just product listings (no specs)
  python complete_scraper.py --pages 3 --skip-specs

  # Raw data only (no standardization or metadata)
  python complete_scraper.py --pages 2 --no-standardization --no-metadata
        """
    )

    # Core Options
    core = parser.add_argument_group('Core Options')
    core.add_argument('--url', '-u',
                       default='https://www.which.co.uk/reviews/washing-machines',
                       help='Which.com category URL to scrape')
    core.add_argument('--pages', '-p',
                       default='1',
                       help='Number of pages to scrape or "all" for all pages')
    core.add_argument('--output', '-o',
                       default='complete_products.json',
                       help='Output JSON file (default: complete_products.json)')
    core.add_argument('--skip-specs', '-s',
                       action='store_true',
                       help='Skip Phase 2: spec extraction (only get product listings)')

    # Enrichment Phases (opt-in)
    enrichment = parser.add_argument_group('Enrichment Phases (optional, opt-in)')
    enrichment.add_argument('--enrich-retailers', '-e',
                       action='store_true',
                       help='Phase 4-5: Enrich with retailer specs and PDFs')
    enrichment.add_argument('--enrich-reviews',
                       action='store_true',
                       help='Phase 6: Enrich with customer reviews from AO/Boots/Amazon')
    enrichment.add_argument('--enrich-ai',
                       action='store_true',
                       help='Phase 7: Use AI (Gemini) to fill missing specs')

    # Processing Options (on by default, use --no-X to disable)
    processing = parser.add_argument_group('Processing Options (enabled by default)')
    processing.add_argument('--no-standardization',
                       action='store_true',
                       help='Skip Phase 8: data standardization')
    processing.add_argument('--no-metadata',
                       action='store_true',
                       help='Skip Phase 9: metadata generation')

    # Output Destinations
    output = parser.add_argument_group('Output Destinations')
    output.add_argument('--save-to-db',
                       action='store_true',
                       help='Phase 10: Insert products and metadata to Supabase database')
    output.add_argument('--download-images',
                       action='store_true',
                       help='Download and upload product images to Supabase storage')
    output.add_argument('--storage-bucket',
                       default='product-images',
                       help='Supabase storage bucket name (default: product-images)')

    # Performance Tuning
    perf = parser.add_argument_group('Performance Tuning')
    perf.add_argument('--workers', '-w',
                       type=int, default=3,
                       help='Workers for spec extraction (default: 3)')
    perf.add_argument('--retailer-workers',
                       type=int, default=3,
                       help='Workers for retailer enrichment (default: 3)')
    perf.add_argument('--review-workers',
                       type=int, default=3,
                       help='Workers for review enrichment (default: 3)')
    perf.add_argument('--ai-workers',
                       type=int, default=2,
                       help='Workers for AI (Gemini) enrichment (default: 2)')

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

    # Determine gemini_workers based on --enrich-ai flag
    gemini_workers = args.ai_workers if args.enrich_ai else 0

    asyncio.run(main(
        url=args.url,
        pages=pages_arg,
        workers=args.workers,
        skip_specs=args.skip_specs,
        output_file=args.output,
        download_images=args.download_images,
        storage_bucket=args.storage_bucket,
        skip_retailers=False,  # Always extract retailer links (Phase 3)
        enrich_retailers=args.enrich_retailers,
        retailer_workers=args.retailer_workers,
        gemini_workers=gemini_workers,
        enrich_reviews=args.enrich_reviews,
        review_workers=args.review_workers,
        skip_standardization=args.no_standardization,
        skip_db_insert=not args.save_to_db,
        skip_metadata=args.no_metadata
    ))