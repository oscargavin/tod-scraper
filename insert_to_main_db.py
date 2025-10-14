#!/usr/bin/env python3
"""
Insert products from full_pipeline_output.json into main Supabase database.
"""

import json
import os
import re
from supabase import create_client, Client
from typing import Dict, Any

# Main branch credentials
SUPABASE_URL = "https://rbylmlwdqrjvtgifwjyp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJieWxtbHdkcXJqdnRnaWZ3anlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTQzOTAwMDUsImV4cCI6MjA2OTk2NjAwNX0.vTT9vdB3ambZBtPVgsOwopOr1nl-xZL20aL05Ow0PHA"

def extract_brand_model(name: str) -> tuple[str, str]:
    """Extract brand and model from product name."""
    parts = name.split(' ', 1)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return name, name

def parse_price(price_str: str) -> float:
    """Convert price string to float."""
    if not price_str:
        return 0
    price_str = str(price_str).replace('£', '').replace(',', '')
    try:
        return float(price_str)
    except:
        return 0

def update_image_urls(images: Dict[str, str]) -> Dict[str, str]:
    """Image URLs should already point to main branch storage."""
    if not images:
        return {}
    # Images are already uploaded to main branch, just return as-is
    return images

def main():
    # Initialize Supabase client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Load products from JSON
    with open('output/washing_machines_full.json', 'r') as f:
        data = json.load(f)
    
    products = data['products']
    print(f"Found {len(products)} products to insert")
    
    success_count = 0
    error_count = 0
    
    for i, product in enumerate(products, 1):
        try:
            brand, model = extract_brand_model(product['name'])
            
            # Prepare product data with new schema
            product_data = {
                'category_id': 1,  # Washing machines
                'name': product['name'],
                'brand': brand,
                'model': model,
                'price': parse_price(product.get('price')),
                'source_url': product.get('whichUrl'),
                'specs': product.get('specs', {}),
                'features': product.get('features', {}),
                'tod_score': product.get('reviews', 0),  # reviews field becomes tod_score
                'images': update_image_urls(product.get('images', {})),
                'retailer_links': product.get('retailerLinks', [])  # Add retailer links
            }
            
            # Insert into database
            result = supabase.table('products').insert(product_data).execute()
            
            if result.data:
                success_count += 1
                print(f"✓ {i}/{len(products)}: Inserted {product['name']}")
            else:
                error_count += 1
                print(f"✗ {i}/{len(products)}: Failed to insert {product['name']}")
                
        except Exception as e:
            error_count += 1
            print(f"✗ {i}/{len(products)}: Error inserting {product.get('name', 'Unknown')}: {e}")
    
    print(f"\n{'='*50}")
    print(f"Migration Complete!")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"Total: {len(products)}")

if __name__ == "__main__":
    main()