#!/usr/bin/env python3
"""
Apply unification map to complete_products.json to create standardized_products.json.
"""

import json
import re
import copy
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional


# Dynamic unit detection patterns
# Each pattern includes: suffix for the new key, regex pattern, and optional conversion function
UNIT_PATTERNS = {
    'cm': {
        'suffix': '_cm',
        'regex': r'\b(\d+\.?\d*)\s*cm\b',
    },
    'mm': {
        'suffix': '_cm',  # Convert mm to cm
        'regex': r'\b(\d+\.?\d*)\s*mm\b',
        'convert': lambda x: float(x) / 10,
    },
    'kg': {
        'suffix': '_kg',
        'regex': r'\b(\d+\.?\d*)\s*kg\b',
    },
    'g': {
        'suffix': '_g',
        'regex': r'\b(\d+\.?\d*)\s*g\b',
    },
    'rpm': {
        'suffix': '_rpm',
        'regex': r'\b(\d+\.?\d*)\s*rpm\b',
    },
    'kwh': {
        'suffix': '_kwh',
        'regex': r'\b(\d+\.?\d*)\s*kwh\b',
    },
    'watt': {
        'suffix': '_watt',
        'regex': r'\b(\d+\.?\d*)\s*(?:watt|W)\b',
    },
    'db': {
        'suffix': '_db',
        'regex': r'\b(\d+\.?\d*)\s*db\b',
    },
    'mins': {
        'suffix': '_mins',
        'regex': r'\b(\d+\.?\d*)\s*mins?\b',
    },
    'hours': {
        'suffix': '_hours',
        'regex': r'\b(\d+\.?\d*)\s*(?:hours?|h)\b',
    },
    'litres': {
        'suffix': '_litres',
        'regex': r'\b(\d+\.?\d*)\s*(?:litres?|L)\b',
    },
    'm': {
        'suffix': '_m',
        'regex': r'\b(\d+\.?\d*)\s*m\b',
    },
    'v': {
        'suffix': '_v',
        'regex': r'\b(\d+\.?\d*)\s*V\b',
    },
    'hz': {
        'suffix': '_hz',
        'regex': r'\b(\d+\.?\d*)\s*Hz\b',
    },
    'amps': {
        'suffix': '_amps',
        'regex': r'\b(\d+\.?\d*)\s*(?:amps?|A)\b',
    },
    'degrees': {
        'suffix': '_degrees',
        'regex': r'\b(\d+\.?\d*)\s*°\b',
    },
    'percent': {
        'suffix': '_percent',
        'regex': r'\b(\d+\.?\d*)\s*%\b',
    },
    'gbp': {
        'suffix': '_gbp',
        'regex': r'£\s*(\d+\.?\d*)\b',
    },
}


def normalize_key(key: str) -> str:
    """Normalize key for comparison (lowercase, no underscores/spaces)."""
    return key.lower().replace('_', '').replace('-', '').replace(' ', '')


def auto_extract_unit(value: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Automatically detect and extract units from a value string using UNIT_PATTERNS.

    Returns:
        (numeric_value, detected_unit, suggested_suffix) if unit found
        (original_value, None, None) if no unit found

    Examples:
        "2.1 cm" -> ("2.1", "cm", "_cm")
        "630 mm" -> ("63.0", "mm", "_cm")  # converted to cm
        "A to G" -> ("A to G", None, None)  # no digit before 'g', skipped
    """
    value_str = str(value).strip()

    # Try each pattern in priority order (most specific first)
    # Order matters: try 'kwh' before 'watt', 'mins' before 'm', etc.
    pattern_order = [
        'kwh', 'rpm', 'watt', 'litres', 'hours', 'mins', 'mm', 'cm',
        'kg', 'g', 'db', 'amps', 'degrees', 'percent', 'gbp', 'm', 'v', 'hz'
    ]

    for unit_name in pattern_order:
        if unit_name not in UNIT_PATTERNS:
            continue

        pattern_config = UNIT_PATTERNS[unit_name]
        regex = pattern_config['regex']

        # Search for the pattern (case-insensitive)
        match = re.search(regex, value_str, re.IGNORECASE)
        if match:
            # Extract the numeric value
            numeric_str = match.group(1)

            # Apply conversion if needed (e.g., mm -> cm)
            if 'convert' in pattern_config:
                try:
                    numeric_value = pattern_config['convert'](numeric_str)
                    # Format as integer if whole number, otherwise keep decimal
                    if numeric_value == int(numeric_value):
                        numeric_str = str(int(numeric_value))
                    else:
                        numeric_str = str(numeric_value)
                except (ValueError, TypeError):
                    pass  # Keep original if conversion fails

            return numeric_str, unit_name, pattern_config['suffix']

    # No unit detected
    return value_str, None, None


def extract_unit_from_value(value: str, units: List[str], new_key: str = None) -> tuple[str, str]:
    """
    Extract numeric value and unit from string.
    Automatically converts units when needed (e.g., mm → cm).
    Returns: (numeric_value, detected_unit)
    """
    value_str = str(value).strip()

    # First, try to detect mm in the value (before checking expected units)
    mm_pattern = r'\s*mm\s*'
    if re.search(mm_pattern, value_str, re.IGNORECASE):
        # Extract numeric value
        numeric = re.sub(mm_pattern, '', value_str, flags=re.IGNORECASE).strip()

        # Check if target key expects cm
        if new_key and new_key.endswith('_cm'):
            try:
                # Convert mm to cm (divide by 10)
                mm_value = float(numeric)
                cm_value = mm_value / 10
                # Format as integer if whole number, otherwise one decimal place
                if cm_value == int(cm_value):
                    return str(int(cm_value)), "cm"
                else:
                    return str(cm_value), "cm"
            except (ValueError, TypeError):
                # If conversion fails, return as-is
                return numeric, "mm"
        else:
            # Target expects mm, return as-is
            return numeric, "mm"

    # Try expected units from the unification map
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

    Process:
    1. First check if key is in unification_map (explicit rules)
    2. If not, try auto_extract_unit() for dynamic detection
    3. If unit detected dynamically, update key name and extract value
    """
    result = {}

    for key, value in specs.items():
        if key in unit_extractions:
            # Explicit rule from unification_map
            extraction_rule = unit_extractions[key]
            new_key = extraction_rule['new_key']
            units = extraction_rule['units']

            # Extract unit from value (pass new_key for unit conversion)
            numeric_value, detected_unit = extract_unit_from_value(value, units, new_key)
            result[new_key] = numeric_value
        else:
            # Try dynamic unit detection
            numeric_value, detected_unit, suggested_suffix = auto_extract_unit(value)

            if detected_unit is not None:
                # Unit detected! Create new key with suffix
                new_key = key + suggested_suffix
                result[new_key] = numeric_value
            else:
                # No unit detected, keep as-is
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

    # BUG FIX 1: Apply unit extractions BEFORE merges so old key names are found
    specs = apply_unit_extractions(specs, unification_map.get('unit_extractions', {}))
    features = apply_unit_extractions(features, unification_map.get('unit_extractions', {}))

    # BUG FIX 3: Apply merges to both specs and features
    specs = apply_merges(specs, unification_map.get('merges', {}))
    features = apply_merges(features, unification_map.get('merges', {}))

    # Apply deletions
    specs = apply_deletions(specs, unification_map.get('deletions', []))
    features = apply_deletions(features, unification_map.get('deletions', []))

    # BUG FIX 2: Actually use the returned values from cross-category removals
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
