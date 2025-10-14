# Image Storage Pipeline Documentation

## Overview

This document outlines the implementation of an image storage pipeline for Which.com product images using Supabase Storage. The pipeline will extract product images, download them, and store them in Supabase Storage buckets for reliable hosting.

## Image Discovery Results

From our testing, we discovered:
- Each product has **3 images**: front, side, and rear views
- Images are available in **800x600 .webp format**
- URLs follow pattern: `https://dam.which.co.uk/[PRODUCT-CODE]-[VIEW]-800x600.webp`
- Images are already loaded in the DOM (no carousel navigation needed)

Example URLs:
```
https://dam.which.co.uk/IC22009-0697-00-front-800x600.webp
https://dam.which.co.uk/IC22009-0697-00-side-800x600.webp
https://dam.which.co.uk/IC22009-0697-00-rear-800x600.webp
```

## Supabase Storage Setup

### 1. Create Storage Bucket

```python
from supabase import create_client
import os

# Initialize Supabase client
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

# Create a public bucket for product images
bucket_options = {
    "public": True,  # Make images publicly accessible
    "allowed_mime_types": ["image/webp", "image/jpeg", "image/png"],
    "file_size_limit": 5242880  # 5MB limit per image
}

supabase.storage.create_bucket("product-images", bucket_options)
```

### 2. Storage Structure

Organize images by category and product:
```
product-images/
├── washing-machines/
│   ├── miele-wwj880-wcs/
│   │   ├── front.webp
│   │   ├── side.webp
│   │   └── rear.webp
│   └── bosch-wan28281gb/
│       ├── front.webp
│       ├── side.webp
│       └── rear.webp
├── air-fryers/
│   └── ninja-foodi-af300uk/
│       ├── front.webp
│       ├── side.webp
│       └── rear.webp
└── tvs/
    └── lg-oled55c3pua/
        ├── front.webp
        ├── side.webp
        └── rear.webp
```

## Implementation Components

### 1. Image Extraction Function

```python
async def extract_product_images(page) -> Dict[str, List[str]]:
    """
    Extract product images from Which.com product page.
    Returns dict with image URLs organized by view type.
    """
    images = await page.evaluate('''
        () => {
            const images = [];
            
            // Get all .webp images from dam.which.co.uk
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
```

### 2. Image Download Function

```python
import aiohttp
import asyncio
from typing import Dict, Optional

async def download_image(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    """
    Download image from URL and return bytes.
    """
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                return await response.read()
            else:
                print(f"Failed to download {url}: Status {response.status}")
                return None
    except Exception as e:
        print(f"Error downloading {url}: {e}")
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
        
        results = await asyncio.gather(*tasks.values())
        
        return {
            view: content 
            for view, content in zip(tasks.keys(), results) 
            if content
        }
```

### 3. Supabase Upload Function

```python
from typing import Dict
import io

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
    uploaded_urls = {}
    bucket_name = "product-images"
    
    for view, image_bytes in images.items():
        # Construct path in bucket
        file_path = f"{category}/{product_slug}/{view}.webp"
        
        try:
            # Upload using file-like object
            file_obj = io.BytesIO(image_bytes)
            
            response = supabase.storage.from_(bucket_name).upload(
                file_path,
                file_obj,
                {"content-type": "image/webp", "upsert": True}
            )
            
            # Get public URL
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
            uploaded_urls[view] = public_url
            
            print(f"✓ Uploaded {view} image: {file_path}")
            
        except Exception as e:
            print(f"✗ Failed to upload {view} image: {e}")
            uploaded_urls[view] = None
    
    return uploaded_urls
```

### 4. Integration with complete_scraper.py

Update the `extract_specifications` function to include image extraction:

```python
async def extract_specifications(page) -> Dict:
    """Extract specifications, features, retailer links, and images."""
    
    # Existing spec extraction code...
    
    # Add image extraction
    images = await extract_product_images(page)
    
    return {
        'specs': specs,
        'features': features,
        'retailerLinks': retailerLinks,
        'whichImageUrls': images  # Store original Which.com URLs
    }

async def enrich_single_product(page, product: Dict, supabase=None, category=None) -> Dict:
    """Enrich product with specs and optionally upload images."""
    
    # Existing enrichment code...
    data = await extract_specifications(page)
    
    # Download and upload images if Supabase client provided
    supabase_image_urls = {}
    if supabase and category:
        # Download images
        which_images = data.get('whichImageUrls', {})
        if which_images:
            downloaded = await download_product_images(which_images)
            
            # Generate product slug from name
            product_slug = product['name'].lower().replace(' ', '-').replace('/', '-')
            
            # Upload to Supabase
            supabase_image_urls = upload_to_supabase(
                supabase, 
                category, 
                product_slug, 
                downloaded
            )
    
    return {
        **product,
        'specs': data.get('specs', {}),
        'features': data.get('features', {}),
        'whichImageUrls': data.get('whichImageUrls', {}),
        'images': supabase_image_urls  # Supabase-hosted URLs
    }
```

### 5. Main Pipeline Updates

```python
async def main(url: str, pages, workers: int, skip_specs: bool, 
               output_file: str, download_images: bool = False):
    """Main pipeline coordinator with optional image storage."""
    
    # Initialize Supabase if image download enabled
    supabase = None
    category = None
    if download_images:
        supabase = create_client(
            os.environ.get("SUPABASE_URL"),
            os.environ.get("SUPABASE_KEY")
        )
        # Extract category from URL
        category = url.split('/reviews/')[-1].split('/')[0]
    
    # ... existing pipeline code ...
    
    # Pass supabase and category to enrichment phase
    if not skip_specs and products:
        products = await enrich_specs_phase(
            browser, products, workers, supabase, category
        )
```

## Environment Variables

Required environment variables:
```bash
# Supabase credentials
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-key"

# Optional: separate storage URL if needed
export SUPABASE_STORAGE_URL="https://your-project.supabase.co/storage/v1"
```

## Command Line Usage

```bash
# Basic scraping without images
python complete_scraper.py --url "https://which.co.uk/reviews/washing-machines" --pages 1

# With image download and storage
python complete_scraper.py \
    --url "https://which.co.uk/reviews/washing-machines" \
    --pages 1 \
    --download-images

# Specify storage bucket
python complete_scraper.py \
    --url "https://which.co.uk/reviews/washing-machines" \
    --pages 1 \
    --download-images \
    --storage-bucket "product-images-staging"
```

## Output Format

The enhanced product data structure:

```json
{
  "name": "Miele WWJ880 WCS",
  "price": "£1,299",
  "whichUrl": "https://which.co.uk/reviews/washing-machines/miele-wwj880-wcs",
  "specs": {
    "capacity": "9kg",
    "spin_speed": "1600rpm"
  },
  "whichImageUrls": {
    "front": "https://dam.which.co.uk/IC22009-0697-00-front-800x600.webp",
    "side": "https://dam.which.co.uk/IC22009-0697-00-side-800x600.webp",
    "rear": "https://dam.which.co.uk/IC22009-0697-00-rear-800x600.webp"
  },
  "images": {
    "front": "https://your-project.supabase.co/storage/v1/object/public/product-images/washing-machines/miele-wwj880-wcs/front.webp",
    "side": "https://your-project.supabase.co/storage/v1/object/public/product-images/washing-machines/miele-wwj880-wcs/side.webp",
    "rear": "https://your-project.supabase.co/storage/v1/object/public/product-images/washing-machines/miele-wwj880-wcs/rear.webp"
  }
}
```

## Benefits of This Approach

1. **No Hotlinking**: Avoids ethical and technical issues with using Which.com's bandwidth
2. **Reliability**: Images always available, even if Which.com changes or blocks access
3. **Performance**: Supabase CDN provides fast global delivery
4. **Control**: Full control over image availability and organization
5. **Scalability**: Easy to scale storage as needed
6. **Cost-Effective**: Supabase free tier handles ~1,700 products (1GB storage)

## Storage Calculations

- Average image size: ~200KB per image (800x600 webp)
- Per product: 3 images × 200KB = 600KB
- Free tier capacity: 1GB ÷ 600KB ≈ 1,700 products
- Bandwidth: 2GB/month free (enough for ~3,400 full product image sets served)

## Error Handling

The pipeline includes robust error handling:
- Failed downloads are logged but don't stop the pipeline
- Partial image sets are accepted (e.g., if only front/side available)
- Original Which.com URLs are preserved as backup
- Upload failures are logged with specific error messages

## Testing

Test the image storage pipeline:

```python
# test_image_storage.py
import asyncio
from complete_scraper import extract_product_images, download_product_images, upload_to_supabase

async def test_storage_pipeline():
    # Test with a known product URL
    test_url = "https://which.co.uk/reviews/washing-machines/miele-wwj880-wcs"
    
    # Extract images
    async with ... as browser:
        page = await browser.new_page()
        await page.goto(test_url)
        
        # Extract
        images = await extract_product_images(page)
        print(f"Extracted: {images}")
        
        # Download
        downloaded = await download_product_images(images)
        print(f"Downloaded {len(downloaded)} images")
        
        # Upload
        supabase = create_client(...)
        urls = upload_to_supabase(supabase, "washing-machines", "test-product", downloaded)
        print(f"Uploaded URLs: {urls}")

asyncio.run(test_storage_pipeline())
```

## Security Considerations

1. **API Keys**: Never commit API keys to version control
2. **Bucket Permissions**: Set appropriate public/private access
3. **File Validation**: Validate image content before upload
4. **Rate Limiting**: Implement delays between downloads to respect Which.com
5. **Error Logging**: Log errors without exposing sensitive information

## Future Enhancements

1. **Image Optimization**: Compress images before storage
2. **Multiple Resolutions**: Store different sizes for different use cases
3. **Fallback Logic**: Use Which.com URLs if Supabase upload fails
4. **Batch Processing**: Upload images in batches for efficiency
5. **CDN Integration**: Add CloudFlare or other CDN for better performance
6. **Image Validation**: Verify image content matches expected product