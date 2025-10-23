#!/usr/bin/env python3
"""
Apply unification map to complete_products.json to create standardized_products.json.
"""

import json
import re
import copy
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from .config import (
    DEFAULT_INPUT_FILE,
    DEFAULT_UNIFICATION_MAP_FILE,
    DEFAULT_OUTPUT_FILE,
    UNIT_PATTERNS,
    UNIT_PATTERN_ORDER,
)


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
    for unit_name in UNIT_PATTERN_ORDER:
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


def normalize_numeric_value(value_str: str) -> str:
    """
    Normalize numeric values:
    - Convert European comma decimals to periods (6,2 → 6.2)
    - Preserve ranges (220-240, 1–48)
    - Remove extra spaces
    """
    # Handle European decimal comma ONLY if it's between digits
    # Pattern: digit + comma + digits (e.g., "6,2")
    value_str = re.sub(r'(\d),(\d)', r'\1.\2', value_str)

    # Normalize en-dash and em-dash to hyphen in ranges
    value_str = value_str.replace('–', '-').replace('—', '-')

    return value_str.strip()


def extract_unit_from_value(value: str, units: List[str], new_key: str = None) -> Tuple[str, str]:
    """
    Extract numeric value and unit from string.
    Automatically converts units when needed (e.g., mm -> cm).
    Handles:
    - European decimals (6,2 → 6.2)
    - Ranges (220-240V, 1–48 hr)
    - Complex patterns (2s for seconds, etc.)

    Returns: (numeric_value, detected_unit)
    """
    value_str = str(value).strip()

    # First, try to detect mm in the value (before checking expected units)
    mm_pattern = r'\s*mm\s*'
    if re.search(mm_pattern, value_str, re.IGNORECASE):
        # Extract numeric value
        numeric = re.sub(mm_pattern, '', value_str, flags=re.IGNORECASE).strip()
        numeric = normalize_numeric_value(numeric)

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

    # Sort units by length (longest first) to match specific forms before generic ones
    # This prevents "L" matching before "Litres", which would leave "itres"
    sorted_units = sorted(units, key=len, reverse=True)

    # Try expected units from the unification map
    for unit in sorted_units:
        # Try to find and remove the unit (case-insensitive, handles trailing/embedded units)
        pattern = rf'\s*{re.escape(unit)}\s*$'
        if re.search(pattern, value_str, re.IGNORECASE):
            # Remove the unit and extract number
            numeric = re.sub(pattern, '', value_str, flags=re.IGNORECASE).strip()
            numeric = normalize_numeric_value(numeric)
            return numeric, unit

    # If no exact match, try non-anchored pattern (unit anywhere in string)
    for unit in sorted_units:
        pattern = rf'\s*{re.escape(unit)}\s*'
        if re.search(pattern, value_str, re.IGNORECASE):
            numeric = re.sub(pattern, '', value_str, flags=re.IGNORECASE).strip()
            numeric = normalize_numeric_value(numeric)
            return numeric, unit

    # No unit found, just normalize the value
    return normalize_numeric_value(value_str), ""


def apply_merges(specs: Dict, merges: Dict) -> Dict:
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


def apply_deletions(specs: Dict, deletions: List[str]) -> Dict:
    """Remove keys marked for deletion."""
    return {k: v for k, v in specs.items() if k not in deletions}


def apply_unit_extractions(specs: Dict, unit_extractions: Dict) -> Dict:
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


def apply_cross_category_removals(specs: Dict, features: Dict, removals: Dict) -> Tuple[Dict, Dict]:
    """Remove keys from wrong category."""
    specs_to_remove = removals.get('specs', [])
    features_to_remove = removals.get('features', [])

    clean_specs = {k: v for k, v in specs.items() if k not in specs_to_remove}
    clean_features = {k: v for k, v in features.items() if k not in features_to_remove}

    return clean_specs, clean_features


def standardize_product(product: Dict, unification_map: Dict) -> Dict:
    """Apply all standardization rules to a single product."""
    # Deep copy to avoid modifying original
    standardized = copy.deepcopy(product)

    # Get specs and features
    specs = standardized.get('specs', {})
    features = standardized.get('features', {})

    # Apply unit extractions BEFORE merges so old key names are found
    specs = apply_unit_extractions(specs, unification_map.get('unit_extractions', {}))
    features = apply_unit_extractions(features, unification_map.get('unit_extractions', {}))

    # Apply merges to both specs and features
    specs = apply_merges(specs, unification_map.get('merges', {}))
    features = apply_merges(features, unification_map.get('merges', {}))

    # Apply deletions
    specs = apply_deletions(specs, unification_map.get('deletions', []))
    features = apply_deletions(features, unification_map.get('deletions', []))

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


def standardize_products(input_file: str, map_file: str, output_file: str) -> Dict:
    """
    Apply standardization to all products.

    Returns:
        Dictionary with summary statistics.
    """
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

    # Return summary
    return {
        'total_products': len(standardized_products),
        'merges_applied': len(unification_map.get('merges', {})),
        'deletions_applied': len(unification_map.get('deletions', [])),
        'unit_extractions': len(unification_map.get('unit_extractions', {})),
    }


def main(input_file: str = None, map_file: str = None, output_file: str = None):
    """
    Main entry point for transformation.

    Args:
        input_file: Path to input products JSON (default: DEFAULT_INPUT_FILE)
        map_file: Path to unification map JSON (default: DEFAULT_UNIFICATION_MAP_FILE)
        output_file: Path to output standardized JSON (default: DEFAULT_OUTPUT_FILE)
    """
    input_file = input_file or DEFAULT_INPUT_FILE
    map_file = map_file or DEFAULT_UNIFICATION_MAP_FILE
    output_file = output_file or DEFAULT_OUTPUT_FILE

    summary = standardize_products(input_file, map_file, output_file)

    # Print summary
    print("\nSummary:")
    print(f"  Total products: {summary['total_products']}")
    print(f"  Merges applied: {summary['merges_applied']}")
    print(f"  Deletions applied: {summary['deletions_applied']}")
    print(f"  Unit extractions: {summary['unit_extractions']}")


if __name__ == "__main__":
    main()
