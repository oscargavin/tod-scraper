#!/usr/bin/env python3
"""
Insert generated field metadata into Supabase category_metadata table.
Extends existing field_stats JSONB with field categorization data.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Mapping from filenames to category slugs
FILENAME_TO_CATEGORY = {
    'air-fryers': 'air-fryers',
    'air-fryers_full': 'air-fryers',
    'air-fryers_ao_reviews': 'air-fryers',  # Skip - test file
    'washing_machines': 'washing-machines',
    'washing_machines_full': 'washing-machines',
    'washing-machines_full': 'washing-machines',
    'dishwashers_full': 'dishwashers',
    'ovens_full': 'ovens',
    'microwaves_full': 'microwaves',
    'fridge-freezers': 'fridge-freezers',
    'fridge-freezers_full': 'fridge-freezers',
    'fridges_full': 'fridges',
    'freezers_full': 'freezers',
    'vacuum-cleaners_full': 'vacuum-cleaners',
    'coffee-machines': 'coffee-machines',
    'coffee-machines_full': 'coffee-machines',
    'tvs': 'tvs',
    'tvs_full': 'tvs',
    'laptops': 'laptops',
    'laptops_full': 'laptops',
    'mobile-phones': 'mobile-phones',
    'mobile-phones_full': 'mobile-phones',
    'tablets_full': 'tablets',
    'tumble-dryers_full': 'tumble-dryers',
    'wireless-and-bluetooth-speakers_full': 'wireless-and-bluetooth-speakers',
    'smartwatches_full': 'smartwatches',
    'kettles_full': 'kettles',
    'cars': None,  # Skip - not in categories table
    'headphones': None,  # Skip - not in categories table
    'printers': None,  # Skip - not in categories table
    'smartwatches': None,  # Skip - not in categories table
    # Test files - skip these
    'test_': None,
    'full_pipeline_output': None,
}

def get_category_slug(filename: str) -> Optional[str]:
    """Map filename to category slug."""
    # Remove .metadata.json or .json extension
    base_name = filename.replace('.metadata.json', '').replace('.json', '')
    
    # Check for test files
    if base_name.startswith('test_'):
        return None
    
    # Direct mapping
    if base_name in FILENAME_TO_CATEGORY:
        return FILENAME_TO_CATEGORY[base_name]
    
    # Default: use base name as slug
    return None  # Be conservative, only use known mappings

def prepare_metadata_for_db(metadata: Dict) -> Dict:
    """
    Prepare metadata for database insertion.
    Uses the simplified field_values structure.
    """
    # For the new simplified structure, the metadata already contains only field_values
    if 'field_values' in metadata and isinstance(metadata['field_values'], dict):
        # New format - just return field_values directly
        return {
            'field_values': metadata['field_values']
        }
    else:
        # Legacy format - extract what we need
        return {
            'field_values': metadata.get('field_values', {})
        }


def insert_category_metadata(metadata: Dict, category_slug: str, supabase: Optional[Client] = None) -> Tuple[bool, str]:
    """
    Insert category metadata into Supabase.
    
    Args:
        metadata: Generated metadata dictionary
        category_slug: Category slug (e.g., 'washing-machines', 'air-fryers')
        supabase: Optional Supabase client instance (will create one if not provided)
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Initialize Supabase if not provided
    if not supabase:
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not supabase_url or not supabase_key:
            return False, "SUPABASE_URL and SUPABASE_KEY must be set in environment"
        
        supabase = create_client(supabase_url, supabase_key)
    
    try:
        # Get category ID from slug
        category_result = supabase.table('categories').select('id').eq('slug', category_slug).execute()
        if not category_result.data:
            return False, f"Category with slug '{category_slug}' not found in database"
        
        category_id = category_result.data[0]['id']
        
        # Prepare data for database
        field_data = prepare_metadata_for_db(metadata)
        
        # Get existing field_stats if any
        existing = supabase.table('category_metadata')\
            .select('field_stats')\
            .eq('category_id', category_id)\
            .execute()
        
        if existing.data:
            # Merge with existing data
            current_stats = existing.data[0]['field_stats']
            # Preserve existing price, tod_score, numeric_specs
            for key in ['price', 'tod_score', 'numeric_specs']:
                if key in current_stats:
                    field_data[key] = current_stats[key]
            
            # Update existing record
            result = supabase.table('category_metadata')\
                .update({'field_stats': field_data})\
                .eq('category_id', category_id)\
                .execute()
            
            # Build summary
            spec_count = len(field_data.get('field_values', {}).get('specs', {}))
            feature_count = len(field_data.get('field_values', {}).get('features', {}))

            message = f"✓ Updated metadata for {category_slug} (category_id: {category_id})\n"
            message += f"  • Spec fields with values: {spec_count}\n"
            message += f"  • Feature fields with values: {feature_count}"
            
            return True, message
        else:
            # Insert new record
            result = supabase.table('category_metadata')\
                .insert({
                    'category_id': category_id,
                    'field_stats': field_data
                })\
                .execute()
            
            # Build summary
            spec_count = len(field_data.get('field_values', {}).get('specs', {}))
            feature_count = len(field_data.get('field_values', {}).get('features', {}))

            message = f"✓ Inserted metadata for {category_slug} (category_id: {category_id})\n"
            message += f"  • Spec fields with values: {spec_count}\n"
            message += f"  • Feature fields with values: {feature_count}"
            
            return True, message
            
    except Exception as e:
        return False, f"Failed to insert metadata for {category_slug}: {e}"

def main():
    """Insert field metadata into Supabase."""
    # Initialize Supabase client
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")
        return
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Get category mappings from database
    result = supabase.table('categories').select('id, slug').execute()
    categories_map = {cat['slug']: cat['id'] for cat in result.data}
    
    print(f"Found {len(categories_map)} categories in database")
    print(f"Categories: {list(categories_map.keys())}")
    print()
    
    # Process metadata files
    output_dir = Path("output")
    metadata_files = list(output_dir.glob("*.metadata.json"))
    
    if not metadata_files:
        print("No metadata files found in output directory")
        return
    
    print(f"Found {len(metadata_files)} metadata files")
    print()
    
    updated = 0
    skipped = 0
    failed = 0
    
    for metadata_file in metadata_files:
        filename = metadata_file.name
        category_slug = get_category_slug(filename)
        
        if not category_slug:
            print(f"⊘ Skipping {filename} (no category mapping)")
            skipped += 1
            continue
        
        if category_slug not in categories_map:
            print(f"⊘ Skipping {filename} (category '{category_slug}' not in database)")
            skipped += 1
            continue
        
        category_id = categories_map[category_slug]
        
        try:
            # Load metadata
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Prepare data for database
            field_data = prepare_metadata_for_db(metadata)
            
            # Get existing field_stats if any
            existing = supabase.table('category_metadata')\
                .select('field_stats')\
                .eq('category_id', category_id)\
                .execute()
            
            if existing.data:
                # Merge with existing data
                current_stats = existing.data[0]['field_stats']
                # Preserve existing price, tod_score, numeric_specs
                for key in ['price', 'tod_score', 'numeric_specs']:
                    if key in current_stats:
                        field_data[key] = current_stats[key]
                
                # Update existing record
                result = supabase.table('category_metadata')\
                    .update({'field_stats': field_data})\
                    .eq('category_id', category_id)\
                    .execute()
                print(f"✓ Updated metadata for {category_slug} (category_id: {category_id})")
            else:
                # Insert new record
                result = supabase.table('category_metadata')\
                    .insert({
                        'category_id': category_id,
                        'field_stats': field_data
                    })\
                    .execute()
                print(f"✓ Inserted metadata for {category_slug} (category_id: {category_id})")
            
            # Show summary of what was added
            spec_count = len(field_data.get('field_values', {}).get('specs', {}))
            feature_count = len(field_data.get('field_values', {}).get('features', {}))
            print(f"  • Spec fields with values: {spec_count}")
            print(f"  • Feature fields with values: {feature_count}")
            print()
            
            updated += 1
            
        except Exception as e:
            print(f"✗ Failed to process {filename}: {e}")
            failed += 1
    
    # Summary
    print("="*60)
    print("SUMMARY")
    print("="*60)
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(metadata_files)}")

if __name__ == '__main__':
    main()