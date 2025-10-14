#!/usr/bin/env python3
"""
Insert fridge-freezer products from output/fridge-freezers.json into main Supabase database.
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
    # Common fridge-freezer brands
    brands = ['AEG', 'Bosch', 'Samsung', 'LG', 'Whirlpool', 'Hotpoint', 'Beko', 'Liebherr', 
              'Siemens', 'Miele', 'Haier', 'Hisense', 'Candy', 'Hoover', 'Fisher & Paykel',
              'Fisher and Paykel', 'Smeg', 'Zanussi', 'Indesit', 'Gorenje', 'John Lewis', 
              'Bush', 'Ikea', 'Kenwood', 'Russell Hobbs', 'Logik', 'Essentials']
    
    name_upper = name.upper()
    for brand in brands:
        if name_upper.startswith(brand.upper()):
            # Extract model as the rest after brand
            model = name[len(brand):].strip()
            if not model:
                model = name
            return brand, model
    
    # Fallback: split on first space
    parts = name.split(' ', 1)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return name, name

def parse_price(price_str: str) -> float:
    """Convert price string to float, handling various formats."""
    if not price_str:
        return 0
    
    # Remove currency symbol and any text after the number
    price_str = str(price_str).replace('£', '').replace(',', '')
    
    # Extract just the numeric part (handles "999Typical price" format)
    match = re.search(r'^(\d+(?:\.\d+)?)', price_str)
    if match:
        try:
            return float(match.group(1))
        except:
            return 0
    return 0

def main():
    # Initialize Supabase client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Load products from JSON
    with open('output/fridge-freezers.json', 'r') as f:
        data = json.load(f)
    
    products = data['products']
    print(f"Found {len(products)} fridge-freezer products to insert")
    
    # Check if category exists and get/create category_id
    category_result = supabase.table('categories').select('id').eq('name', 'Fridge Freezers').execute()
    
    if category_result.data:
        category_id = category_result.data[0]['id']
        print(f"Using existing category: Fridge Freezers (ID: {category_id})")
    else:
        # Create category
        new_category = supabase.table('categories').insert({
            'name': 'Fridge Freezers',
            'slug': 'fridge-freezers',
            'description': 'Combination refrigerators and freezers'
        }).execute()
        category_id = new_category.data[0]['id']
        print(f"Created new category: Fridge Freezers (ID: {category_id})")
    
    success_count = 0
    error_count = 0
    
    for i, product in enumerate(products, 1):
        try:
            brand, model = extract_brand_model(product['name'])
            
            # Prepare product data with new schema
            product_data = {
                'category_id': category_id,
                'name': product['name'],
                'brand': brand,
                'model': model,
                'price': parse_price(product.get('price')),
                'source_url': product.get('whichUrl'),
                'specs': product.get('specs', {}),
                'features': product.get('features', {}),
                'tod_score': product.get('reviews', 0),  # reviews field becomes tod_score
                'images': product.get('images', {})
            }
            
            # Check if product already exists
            existing = supabase.table('products').select('id').eq('name', product['name']).eq('category_id', category_id).execute()
            
            if existing.data:
                # Update existing product
                result = supabase.table('products').update(product_data).eq('id', existing.data[0]['id']).execute()
                action = "Updated"
            else:
                # Insert new product
                result = supabase.table('products').insert(product_data).execute()
                action = "Inserted"
            
            if result.data:
                success_count += 1
                price_str = f"£{product_data['price']:.0f}" if product_data['price'] > 0 else "No price"
                print(f"✓ {i}/{len(products)}: {action} {product['name']} ({price_str}, TOD: {product_data['tod_score']})")
            else:
                error_count += 1
                print(f"✗ {i}/{len(products)}: Failed to insert {product['name']}")
                
        except Exception as e:
            error_count += 1
            print(f"✗ {i}/{len(products)}: Error with {product.get('name', 'Unknown')}: {e}")
    
    print(f"\n{'='*50}")
    print(f"Fridge-Freezer Import Complete!")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"Total: {len(products)}")
    
    # Show summary statistics
    stats = supabase.table('products').select('COUNT(*), AVG(price)::numeric(10,2) as avg_price, AVG(tod_score)::numeric(10,1) as avg_tod').eq('category_id', category_id).execute()
    if stats.data:
        print(f"\nDatabase Statistics for Fridge Freezers:")
        print(f"Total in DB: {stats.data[0]['count']}")
        print(f"Average Price: £{stats.data[0]['avg_price']}")
        print(f"Average TOD Score: {stats.data[0]['avg_tod']}")

if __name__ == "__main__":
    main()