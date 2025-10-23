#!/usr/bin/env python3
"""
Simplified metadata generator for product JSON files.
Extracts all possible field values for database searchability.
Optimized for JSONB queries with proper type handling.
"""
import json
import os
import sys
import re
from pathlib import Path
from typing import Dict, Set, List, Any, Union
from dotenv import load_dotenv

load_dotenv()

class ProductMetadataGenerator:
    def __init__(self):
        """Initialize the simplified metadata generator."""
        # Field patterns for type detection
        self.numeric_patterns = [
            r'.*_kg$',  # Weight fields ending in _kg
            r'.*_cm$',  # Dimension fields ending in _cm
            r'.*_mins$',  # Time fields ending in _mins
            r'.*_rpm$',  # Rotation fields ending in _rpm
            r'.*capacity.*',  # Capacity fields
            r'.*cost.*',  # Cost/price fields
            r'.*price.*',  # Price fields
            r'width$', r'height$', r'depth$',  # Dimension fields
            r'number_of_.*',  # Count fields
        ]

        # Fields that should be boolean
        self.boolean_fields = {
            'smart', 'autodose', 'quick_wash', 'steam_wash', 'extra_rinse',
            'baby_program', 'steam_refresh', 'door_safety_lock', 'panel_safety_lock',
            'overflow_protection', 'auto_load_adjustment', 'delicates_or_handwash',
            'time_remaining_display', 'hygiene_or_allergy_program', 'program_sequencing_indicator',
            'intensive_program', 'start_end_delay', 'handwash_delicates'
        }
    
    def extract_all_fields(self, products: List[Dict]) -> tuple[Set[str], Set[str]]:
        """Extract all unique fields from all products."""
        all_specs = set()
        all_features = set()

        for product in products:
            if 'specs' in product and product['specs']:
                all_specs.update(product['specs'].keys())
            if 'features' in product and product['features']:
                all_features.update(product['features'].keys())

        # Remove 'which_test_programme' from specs if present
        all_specs.discard('which_test_programme')

        return all_specs, all_features
    
    
    def is_numeric_field(self, field_name: str) -> bool:
        """Check if a field should be treated as numeric based on its name."""
        for pattern in self.numeric_patterns:
            if re.match(pattern, field_name, re.IGNORECASE):
                return True
        return False

    def is_boolean_field(self, field_name: str) -> bool:
        """Check if a field should be treated as boolean."""
        return field_name in self.boolean_fields

    def parse_numeric_value(self, value: str, field_name: str) -> Union[float, None]:
        """Extract numeric value from a string, handling units and currency."""
        if not value or not isinstance(value, str):
            return None

        # Remove currency symbols
        clean_value = value.replace('£', '').replace('$', '').replace('€', '')

        # Extract numeric part using regex
        # Matches integers and decimals, ignoring text after
        match = re.search(r'^(-?\d+(?:\.\d+)?)', clean_value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def parse_boolean_value(self, value: str) -> Union[bool, None]:
        """Convert Yes/No strings to boolean."""
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ['yes', 'true', '1']:
                return True
            elif lower_val in ['no', 'false', '0']:
                return False
        return None

    def extract_field_values(self, products: List[Dict], field_type: str, all_fields: Set[str]) -> Dict[str, List[Union[str, float, bool]]]:
        """Extract all possible values for each field with proper type handling."""
        field_values = {}

        # Initialize all fields with empty sets
        for field in all_fields:
            field_values[field] = set()

        for product in products:
            if field_type in product and product[field_type]:
                for field_name, value in product[field_type].items():
                    # Skip 'which_test_programme' for specs
                    if field_type == 'specs' and field_name == 'which_test_programme':
                        continue

                    if field_name in field_values and value is not None and str(value).strip():
                        # Type-based parsing
                        if self.is_boolean_field(field_name):
                            parsed = self.parse_boolean_value(str(value))
                            if parsed is not None:
                                field_values[field_name].add(parsed)
                        elif self.is_numeric_field(field_name):
                            parsed = self.parse_numeric_value(str(value), field_name)
                            if parsed is not None:
                                field_values[field_name].add(parsed)
                            else:
                                # Fallback to string if parsing fails
                                field_values[field_name].add(str(value))
                        else:
                            # Keep as string for categorical fields
                            field_values[field_name].add(str(value))

        # Convert sets to sorted lists
        result = {}
        for field_name, values in field_values.items():
            if values:
                # Check if all values are of the same type
                values_list = list(values)
                value_types = set(type(v) for v in values_list)

                if len(value_types) == 1:
                    # All same type - sort normally
                    result[field_name] = sorted(values_list)
                else:
                    # Mixed types - separate and sort by type
                    # This handles cases where some values couldn't be parsed
                    numbers = [v for v in values_list if isinstance(v, (int, float))]
                    bools = [v for v in values_list if isinstance(v, bool)]
                    strings = [v for v in values_list if isinstance(v, str)]

                    # If we have mostly numbers with a few strings, keep numbers only
                    if numbers and len(numbers) >= len(strings):
                        result[field_name] = sorted(numbers)
                    # If we have mostly strings, keep everything as strings
                    else:
                        # Convert everything back to strings for consistency
                        all_string_values = [str(v) for v in values_list]
                        result[field_name] = sorted(all_string_values)

        return result
    
    def generate_metadata(self, json_filepath: str) -> Dict:
        """Generate simplified metadata for a product JSON file."""
        # Load the JSON file
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        products = data.get('products', [])
        if not products:
            raise ValueError(f"No products found in {json_filepath}")

        # Extract all unique fields
        specs_fields, features_fields = self.extract_all_fields(products)

        # Extract possible field values - pass all fields to ensure complete coverage
        specs_values = self.extract_field_values(products, 'specs', specs_fields)
        features_values = self.extract_field_values(products, 'features', features_fields)

        # Build simplified metadata structure - only field values
        metadata = {
            "field_values": {
                "specs": specs_values,
                "features": features_values
            }
        }

        return metadata
    
    def save_metadata(self, metadata: Dict, output_path: str):
        """Save metadata to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"✓ Metadata saved to {output_path}")

def generate_product_metadata(json_filepath: str) -> Dict:
    """
    Generate metadata for a product JSON file.
    
    Args:
        json_filepath: Path to the JSON file containing product data
        
    Returns:
        Dictionary containing metadata
    """
    generator = ProductMetadataGenerator()
    return generator.generate_metadata(json_filepath)


def main():
    """Generate metadata for product JSON files."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate metadata for product JSON files')
    parser.add_argument('file', nargs='?', help='Specific JSON file to process')
    parser.add_argument('--update-db', action='store_true', help='Update database after generation')
    args = parser.parse_args()
    
    if args.file:
        # Process specific file
        if not os.path.exists(args.file):
            print(f"Error: File {args.file} not found")
            return
        
        files_to_process = [args.file]
    else:
        # Process all JSON files in output directory
        output_dir = Path("output")
        if not output_dir.exists():
            print("Error: output directory not found")
            return
        
        files_to_process = list(output_dir.glob("*.json"))
        # Exclude metadata files
        files_to_process = [f for f in files_to_process if not str(f).endswith('.metadata.json')]
    
    if not files_to_process:
        print("No JSON files found to process")
        return
    
    for json_file in files_to_process:
        json_path = str(json_file)
        print(f"\nProcessing: {json_path}")
        
        try:
            # Generate metadata
            metadata = generate_product_metadata(json_path)
            
            # Save metadata file alongside original
            metadata_path = json_path.replace('.json', '.metadata.json')
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            print(f"✓ Metadata saved to {metadata_path}")
            
            # Print summary
            spec_count = len(metadata['field_values']['specs'])
            feature_count = len(metadata['field_values']['features'])
            print(f"  • Spec fields with values: {spec_count}")
            print(f"  • Feature fields with values: {feature_count}")
            
        except Exception as e:
            print(f"  ✗ Error processing {json_path}: {e}")
    
    print("\n✓ Metadata generation complete!")
    
    # Optionally update database
    if args.update_db:
        print("\nUpdating database with generated metadata...")
        import subprocess
        result = subprocess.run(['python', 'insert_metadata_to_db.py'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ Database updated successfully")
        else:
            print(f"✗ Database update failed: {result.stderr}")

if __name__ == '__main__':
    main()