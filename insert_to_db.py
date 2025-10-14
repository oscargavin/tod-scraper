#!/usr/bin/env python3
"""
Insert scraped products into Supabase database
"""
import json
import os
import re
from typing import Dict, List, Optional, Tuple
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def parse_price(price_value) -> Optional[float]:
    """Extract numeric value from price string or float"""
    if price_value is None:
        return None
    
    # If it's already a number, return it
    if isinstance(price_value, (int, float)):
        return float(price_value)
    
    # If it's a string, parse it
    if isinstance(price_value, str):
        # Remove currency symbols and commas
        price_clean = re.sub(r'[£$,]', '', price_value)
        try:
            return float(price_clean)
        except:
            return None
    
    return None

def slug_to_display_name(slug: str) -> str:
    """Convert slug to display name (e.g., 'washing-machines' -> 'Washing Machines')"""
    return ' '.join(word.capitalize() for word in slug.split('-'))

def extract_brand_model(name: str) -> Tuple[str, str]:
    """Extract brand and model from product name"""
    # Common brand patterns
    brands = ['Miele', 'Candy', 'AEG', 'Bosch', 'Samsung', 'LG', 'Hotpoint', 
              'Indesit', 'Beko', 'Whirlpool', 'Zanussi', 'Hoover', 'Hisense',
              'Grundig', 'Haier', 'Electrolux', 'Siemens', 'Fisher & Paykel',
              'Blomberg', 'Sharp']
    
    for brand in brands:
        if name.lower().startswith(brand.lower()):
            model = name[len(brand):].strip()
            return brand, model
    
    # Default: first word is brand, rest is model
    parts = name.split(' ', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return name, name

def insert_products(data: Dict, category_slug: str, supabase: Optional[Client] = None) -> Dict[str, int]:
    """
    Insert products into Supabase database.
    
    Args:
        data: Dictionary containing products array
        category_slug: Category slug (e.g., 'washing-machines', 'air-fryers')
        supabase: Optional Supabase client instance (will create one if not provided)
    
    Returns:
        Dictionary with insertion statistics
    """
    # Initialize Supabase if not provided
    if not supabase:
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment")
        
        supabase = create_client(supabase_url, supabase_key)
    
    # Get or create category ID from slug
    try:
        category_result = supabase.table('categories').select('id').eq('slug', category_slug).execute()
        
        if category_result.data:
            # Category exists
            category_id = category_result.data[0]['id']
            print(f"Using existing category: {category_slug} (ID: {category_id})")
        else:
            # Create new category
            display_name = slug_to_display_name(category_slug)
            new_category = supabase.table('categories').insert({
                'slug': category_slug,
                'name': display_name
            }).execute()
            
            if new_category.data:
                category_id = new_category.data[0]['id']
                print(f"✓ Created new category: {display_name} (slug: {category_slug}, ID: {category_id})")
            else:
                raise ValueError(f"Failed to create category with slug '{category_slug}'")
                
    except Exception as e:
        raise ValueError(f"Failed to fetch or create category: {e}")
    
    # Process each product
    products = data.get('products', [])
    inserted = 0
    failed = 0
    errors = []
    
    for product in products:
        try:
            # Extract brand and model
            brand, model = extract_brand_model(product['name'])
            
            # Extract review data and TOD score
            review_data = product.get('reviews', {})
            tod_score = None
            reviews_json = {}
            
            if review_data:
                # Extract TOD score
                tod_score = review_data.get('todScore')
                
                # Extract review sentiment if available
                sentiment = review_data.get('sentiment', {})
                if sentiment:
                    reviews_json = {
                        'summary': sentiment.get('summary', ''),
                        'pros': sentiment.get('pros', []),
                        'cons': sentiment.get('cons', [])
                    }
            
            # Prepare product data
            product_data = {
                'category_id': category_id,
                'name': product['name'],
                'brand': brand,
                'model': model,
                'price': parse_price(product.get('price')),
                'source_url': product.get('whichUrl'),
                'specs': product.get('specs', {}),
                'features': product.get('features', {}),
                'tod_score': tod_score,
                'reviews': reviews_json if reviews_json else None,
                'images': product.get('images', {}),
                'retailer_links': product.get('retailerLinks', [])  # Now included in schema
            }
            
            # Insert into database
            result = supabase.table('products').insert(product_data).execute()
            inserted += 1
            print(f"✓ Inserted: {product['name']}")
            
        except Exception as e:
            failed += 1
            error_msg = f"Failed to insert {product['name']}: {e}"
            errors.append(error_msg)
            print(f"✗ {error_msg}")
    
    return {
        'inserted': inserted,
        'failed': failed,
        'total': len(products),
        'errors': errors
    }


def main():
    """Command-line interface for standalone usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Insert scraped products into Supabase database')
    parser.add_argument('--file', '-f', default='output/full_pipeline_output.json',
                        help='JSON file to process (default: output/full_pipeline_output.json)')
    parser.add_argument('--category', '-c', default='washing-machines',
                        help='Category slug (default: washing-machines)')
    args = parser.parse_args()
    
    # Load data
    with open(args.file, 'r') as f:
        data = json.load(f)
    
    try:
        # Initialize Supabase
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
            return
        
        supabase = create_client(supabase_url, supabase_key)
        
        # Insert products
        stats = insert_products(data, args.category, supabase)
        
        print(f"\nSummary:")
        print(f"  Inserted: {stats['inserted']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Total: {stats['total']}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())