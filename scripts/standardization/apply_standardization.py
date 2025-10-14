#!/usr/bin/env python3
"""
Apply unification map to complete_products.json to create standardized_products.json.
"""

import json
import re
import copy
from pathlib import Path
from typing import Dict, List, Any


def normalize_key(key: str) -> str:
    """Normalize key for comparison (lowercase, no underscores/spaces)."""
    return key.lower().replace('_', '').replace('-', '').replace(' ', '')


def extract_unit_from_value(value: str, units: List[str]) -> tuple[str, str]:
    """
    Extract numeric value and unit from string.
    Returns: (numeric_value, detected_unit)
    """
    value_str = str(value).strip()

    for unit in units:
        # Try to find and remove the unit
        pattern = rf'\s*{re.escape(unit)}\s*'
        if re.search(pattern, value_str, re.IGNORECASE):
            # Remove the unit and extract number
            numeric = re.sub(pattern, '', value_str, flags=re.IGNORECASE).strip()
            return numeric, unit

    return value_str, ""


def apply_merges(specs: dict, merges: dict) -> dict:
    """
    Apply merge rules to specs dict.
    When duplicate keys exist, keep the first occurrence (Which.com data).
    """
    normalized_seen = {}  # Track normalized keys we've seen
    result = {}

    for key, value in specs.items():
        # Check if this key should be merged to a canonical form
        canonical_key = merges.get(key, key)
        normalized = normalize_key(canonical_key)

        # If we haven't seen this normalized key yet, add it
        if normalized not in normalized_seen:
            result[canonical_key] = value
            normalized_seen[normalized] = canonical_key

    return result


def apply_deletions(specs: dict, deletions: List[str]) -> dict:
    """Remove keys marked for deletion."""
    return {k: v for k, v in specs.items() if k not in deletions}


def apply_unit_extractions(specs: dict, unit_extractions: dict) -> dict:
    """
    Extract units from values and rename keys to include units.
    Values become pure numbers/strings.
    """
    result = {}

    for key, value in specs.items():
        if key in unit_extractions:
            extraction_rule = unit_extractions[key]
            new_key = extraction_rule['new_key']
            units = extraction_rule['units']

            # Extract unit from value
            numeric_value, detected_unit = extract_unit_from_value(value, units)
            result[new_key] = numeric_value
        else:
            result[key] = value

    return result


def apply_cross_category_removals(specs: dict, features: dict, removals: dict) -> tuple[dict, dict]:
    """Remove keys from wrong category."""
    specs_to_remove = removals.get('specs', [])
    features_to_remove = removals.get('features', [])

    clean_specs = {k: v for k, v in specs.items() if k not in specs_to_remove}
    clean_features = {k: v for k, v in features.items() if k not in features_to_remove}

    return clean_specs, clean_features


def standardize_product(product: dict, unification_map: dict) -> dict:
    """Apply all standardization rules to a single product."""
    # Deep copy to avoid modifying original
    standardized = copy.deepcopy(product)

    # Get specs and features
    specs = standardized.get('specs', {})
    features = standardized.get('features', {})

    # Apply transformations in order
    specs = apply_merges(specs, unification_map.get('merges', {}))
    specs = apply_unit_extractions(specs, unification_map.get('unit_extractions', {}))
    specs = apply_deletions(specs, unification_map.get('deletions', []))

    # Apply cross-category removals
    specs, features = apply_cross_category_removals(
        specs,
        features,
        unification_map.get('cross_category_removals', {})
    )

    # Update product
    standardized['specs'] = specs
    standardized['features'] = features

    return standardized


def main():
    input_file = "output/complete_products.json"
    map_file = "output/unification_map.json"
    output_file = "output/standardized_products.json"

    # Load data
    print(f"Loading {input_file}...")
    with open(input_file, 'r') as f:
        data = json.load(f)

    print(f"Loading {map_file}...")
    with open(map_file, 'r') as f:
        unification_map = json.load(f)

    # Apply standardization to each product
    print(f"Standardizing {len(data['products'])} products...")
    standardized_products = []

    for i, product in enumerate(data['products'], 1):
        standardized = standardize_product(product, unification_map)
        standardized_products.append(standardized)

        if i % 10 == 0:
            print(f"  Processed {i}/{len(data['products'])} products")

    # Create output with same structure as input
    output_data = copy.deepcopy(data)
    output_data['products'] = standardized_products

    # Save
    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nStandardized data saved to {output_file}")

    # Print summary
    print("\nSummary:")
    print(f"  Total products: {len(standardized_products)}")
    print(f"  Merges applied: {len(unification_map.get('merges', {}))}")
    print(f"  Deletions applied: {len(unification_map.get('deletions', []))}")
    print(f"  Unit extractions: {len(unification_map.get('unit_extractions', {}))}")


if __name__ == "__main__":
    main()
