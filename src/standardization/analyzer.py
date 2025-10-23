#!/usr/bin/env python3
"""
Analyze all spec and feature keys from product data.
Output: key_analysis.json with occurrence counts and sample values.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set

from .config import DEFAULT_INPUT_FILE, DEFAULT_KEY_ANALYSIS_FILE


# Keys to exclude - inventory/metadata that don't help purchase decisions
BLACKLIST_KEYS = {
    # Inventory codes
    'part_number', 'sku', 'upc_ean_code', 'model_number', 'ean', 'mpn', 'asin',
    'product_code', 'item_number', 'catalog_number', 'gtin', 'upc',
    # Internal identifiers
    'id', 'product_id', 'item_id', 'variant_id',
    # Redundant metadata (already in product name or not decision-relevant)
    'brand', 'manufacturer', 'category', 'product_name', 'title', 'name', 'model',
    'model_year',
    # Location/origin metadata
    'country_of_origin', 'manufacturing_location', 'assembly_location', 'use_location',
    # Packaging info
    'packed_dimensions', 'packed_weight', 'packed_dimensions_cm', 'packed_weight_kg',
    # Warranty/support (not specs, more like service terms)
    'warranty', 'manufacturer_warranty', 'service_and_support',
    # Certifications/labels (nice to have but not core specs)
    'certifications', 'ecolabels', 'energy_star_certified', 'regulatory_compliance',
    # Trial software (temporary, not permanent features)
    'software_trial_pc_game_pass', 'software_trial_adobe', 'software_trial_mcafee',
    'software_trial_microsoft_365', 'trial_software', 'dropbox_storage',
    # Aesthetic options (color variations, finish options)
    'color', 'colour', 'colors', 'product_color', 'color_options_aluminum_chassis',
    'color_options_plastic_chassis', 'finish',
    # Retailer-specific
    'availability', 'in_stock', 'stock_status', 'delivery_time',
    'price', 'sale_price', 'rrp', 'msrp',
}


def has_unit_pattern(value: str) -> bool:
    """
    Check if a value likely contains a unit that should be extracted.

    Patterns we look for:
    - Numbers followed by letters (e.g., "10kg", "230°C", "1400 RPM")
    - Numbers with units containing spaces (e.g., "10 kg", "230 °C")
    - Ranges with units (e.g., "1-48 hr", "220-240V")
    """
    # Pattern: number (with optional decimal comma/point) followed by optional space and letters/symbols
    unit_pattern = r'\d+[,.]?\d*\s*[A-Za-z°µ%£€$]+'
    return bool(re.search(unit_pattern, str(value)))


def collect_keys(products_file: str) -> Dict:
    """Collect all spec/feature keys with counts and samples."""
    with open(products_file, 'r') as f:
        data = json.load(f)

    spec_analysis = defaultdict(lambda: {"count": 0, "samples": [], "all_values": set()})
    feature_analysis = defaultdict(lambda: {"count": 0, "samples": [], "all_values": set()})

    # Track blacklisted keys
    blacklisted_specs = set()
    blacklisted_features = set()

    for product in data['products']:
        # Analyze specs
        for key, value in product.get('specs', {}).items():
            # Skip blacklisted keys
            if key in BLACKLIST_KEYS:
                blacklisted_specs.add(key)
                continue

            spec_analysis[key]["count"] += 1

            # Always collect first 10 samples for preview
            if len(spec_analysis[key]["samples"]) < 10:
                spec_analysis[key]["samples"].append(str(value))

            # For values with units, collect ALL unique values
            str_value = str(value)
            if has_unit_pattern(str_value):
                spec_analysis[key]["all_values"].add(str_value)

        # Analyze features
        for key, value in product.get('features', {}).items():
            # Skip blacklisted keys
            if key in BLACKLIST_KEYS:
                blacklisted_features.add(key)
                continue

            feature_analysis[key]["count"] += 1
            if len(feature_analysis[key]["samples"]) < 10:
                feature_analysis[key]["samples"].append(str(value))

    # Convert sets to sorted lists for JSON serialization
    for key_data in spec_analysis.values():
        if key_data["all_values"]:
            key_data["all_values"] = sorted(list(key_data["all_values"]))
        else:
            del key_data["all_values"]  # Remove empty all_values

    for key_data in feature_analysis.values():
        if key_data["all_values"]:
            key_data["all_values"] = sorted(list(key_data["all_values"]))
        else:
            del key_data["all_values"]  # Remove empty all_values

    total_products = len(data['products'])

    return {
        "total_products": total_products,
        "specs": dict(spec_analysis),
        "features": dict(feature_analysis),
        "blacklisted": {
            "specs": sorted(list(blacklisted_specs)),
            "features": sorted(list(blacklisted_features))
        }
    }


def main(input_file: str = None, output_file: str = None):
    """
    Main entry point for key analysis.

    Args:
        input_file: Path to input products JSON (default: DEFAULT_INPUT_FILE)
        output_file: Path to output analysis JSON (default: DEFAULT_KEY_ANALYSIS_FILE)
    """
    input_file = input_file or DEFAULT_INPUT_FILE
    output_file = output_file or DEFAULT_KEY_ANALYSIS_FILE

    print(f"Analyzing keys from {input_file}...")
    analysis = collect_keys(input_file)

    print(f"Found {len(analysis['specs'])} unique spec keys")
    print(f"Found {len(analysis['features'])} unique feature keys")

    # Show blacklist stats
    blacklisted = analysis.get('blacklisted', {})
    if blacklisted.get('specs') or blacklisted.get('features'):
        total_blacklisted = len(blacklisted.get('specs', [])) + len(blacklisted.get('features', []))
        print(f"Filtered out {total_blacklisted} blacklisted keys (inventory/metadata)")
        if blacklisted.get('specs'):
            print(f"  Specs: {', '.join(blacklisted['specs'][:5])}" +
                  (f" ... (+{len(blacklisted['specs'])-5} more)" if len(blacklisted['specs']) > 5 else ""))
        if blacklisted.get('features'):
            print(f"  Features: {', '.join(blacklisted['features'][:5])}" +
                  (f" ... (+{len(blacklisted['features'])-5} more)" if len(blacklisted['features']) > 5 else ""))

    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"Analysis saved to {output_file}")


if __name__ == "__main__":
    main()
