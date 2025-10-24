#!/usr/bin/env python3
"""
Analyze all spec and feature keys from product data.
Output: key_analysis.json with occurrence counts and sample values.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, List
from difflib import SequenceMatcher

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


def detect_duplicate_patterns(analysis: Dict, min_similarity: float = 0.85, min_coverage_ratio: float = 3.0) -> Dict:
    """
    Detect potential duplicate clusters in key_analysis data.

    Args:
        analysis: Key analysis dictionary with specs/features
        min_similarity: Minimum string similarity to flag as potential duplicate (0-1)
        min_coverage_ratio: Minimum coverage ratio to suggest merge (e.g., 3.0 = 3:1 ratio)

    Returns:
        {
            "suffix_clusters": [
                {
                    "base": "timer",
                    "variants": [
                        {"key": "timer", "count": 50, "samples": [...]},
                        {"key": "timer_function", "count": 10, "samples": [...]}
                    ],
                    "suggested_canonical": "timer",
                    "coverage_ratio": "5.0:1"
                }
            ],
            "similar_pairs": [
                {
                    "key1": "adjustable_temperature",
                    "key2": "adjustable_temperature_control",
                    "similarity": 0.92,
                    "coverage": [20, 15]
                }
            ],
            "unit_inconsistencies": [
                {
                    "keys": ["wattage", "wattage_w", "wattage_watt"],
                    "suggested_canonical": "wattage_w",
                    "reason": "inconsistent_unit_suffix"
                }
            ],
            "redundant_pairs": [
                {
                    "key1": "capacity",
                    "key2": "capacity_value",
                    "reason": "generic_value_suffix",
                    "coverage": [51, 66]
                }
            ]
        }
    """
    specs = analysis.get('specs', {})
    total_products = analysis.get('total_products', 1)

    # Common suffixes to detect (expanded)
    SUFFIXES = ['_function', '_feature', '_dial', '_control', '_setting', '_option', '_mode', '_value']

    # 1. DETECT SUFFIX CLUSTERS
    # Group keys by their base name (strip suffixes)
    base_groups = defaultdict(list)

    for key, data in specs.items():
        # Try stripping each suffix to find base
        base = key
        for suffix in SUFFIXES:
            if key.endswith(suffix):
                base = key[:-len(suffix)]
                break

        base_groups[base].append({
            "key": key,
            "count": data['count'],
            "samples": data.get('samples', [])[:3]  # Just first 3 for brevity
        })

    # Filter to groups with multiple variants
    suffix_clusters = []
    for base, variants in base_groups.items():
        if len(variants) > 1:
            # Sort by coverage (highest first)
            variants_sorted = sorted(variants, key=lambda x: x['count'], reverse=True)

            # Calculate coverage ratio (highest:lowest)
            highest_coverage = variants_sorted[0]['count']
            lowest_coverage = variants_sorted[-1]['count']
            coverage_ratio = highest_coverage / lowest_coverage if lowest_coverage > 0 else float('inf')

            # Suggest canonical: most common, or if similar coverage, the base name
            if base in [v['key'] for v in variants]:
                # Base exists, prefer it
                suggested_canonical = base
            else:
                # Base doesn't exist, prefer highest coverage
                suggested_canonical = variants_sorted[0]['key']

            suffix_clusters.append({
                "base": base,
                "variants": variants_sorted,
                "suggested_canonical": suggested_canonical,
                "coverage_ratio": f"{coverage_ratio:.1f}:1"
            })

    # Sort by cluster size (most variants first)
    suffix_clusters.sort(key=lambda x: len(x['variants']), reverse=True)

    # 2. DETECT SIMILAR PAIRS (high string similarity)
    similar_pairs = []
    keys_list = list(specs.keys())

    for i, key1 in enumerate(keys_list):
        for key2 in keys_list[i+1:]:
            # Skip if already in same suffix cluster
            in_same_cluster = any(
                key1 in [v['key'] for v in cluster['variants']] and
                key2 in [v['key'] for v in cluster['variants']]
                for cluster in suffix_clusters
            )
            if in_same_cluster:
                continue

            # Calculate similarity
            similarity = SequenceMatcher(None, key1, key2).ratio()

            if similarity >= min_similarity:
                similar_pairs.append({
                    "key1": key1,
                    "key2": key2,
                    "similarity": round(similarity, 2),
                    "coverage": [specs[key1]['count'], specs[key2]['count']]
                })

    # Sort by similarity (highest first)
    similar_pairs.sort(key=lambda x: x['similarity'], reverse=True)

    # 3. DETECT UNIT INCONSISTENCIES
    # Group keys that differ only by unit suffix variations
    unit_inconsistencies = []
    unit_suffix_patterns = {
        'watt': ['_w', '_watt', '_watts'],
        'kilogram': ['_kg', '_kilogram', '_kilograms'],
        'gram': ['_g', '_gram', '_grams'],
        'litre': ['_l', '_litre', '_litres', '_liter', '_liters'],
        'centimeter': ['_cm', '_centimeter', '_centimeters'],
        'meter': ['_m', '_meter', '_meters'],
        'celsius': ['_c', '_celsius', '_degrees'],
        'minute': ['_min', '_mins', '_minute', '_minutes'],
        'hour': ['_hr', '_hrs', '_hour', '_hours'],
        'second': ['_s', '_sec', '_second', '_seconds'],
    }

    # For each base unit, find keys with different suffix variations
    unit_groups = defaultdict(list)
    for key in specs.keys():
        for unit_type, suffixes in unit_suffix_patterns.items():
            for suffix in suffixes:
                if key.endswith(suffix):
                    base = key[:-len(suffix)]
                    unit_groups[base].append({
                        'key': key,
                        'suffix': suffix,
                        'count': specs[key]['count'],
                        'unit_type': unit_type
                    })
                    break

    # Filter to groups with multiple variations
    for base, variants in unit_groups.items():
        if len(variants) > 1:
            # Sort by coverage (highest first)
            variants_sorted = sorted(variants, key=lambda x: x['count'], reverse=True)

            # Prefer shortest standard suffix (_w over _watt, _l over _litre)
            standard_suffixes = {'_w', '_kg', '_g', '_l', '_cm', '_m', '_c', '_min', '_hr', '_s'}
            canonical = variants_sorted[0]['key']  # Default to highest coverage

            for v in variants_sorted:
                if v['suffix'] in standard_suffixes:
                    canonical = v['key']
                    break

            unit_inconsistencies.append({
                'base': base,
                'variants': [v['key'] for v in variants_sorted],
                'suggested_canonical': canonical,
                'reason': f"inconsistent_{variants_sorted[0]['unit_type']}_suffix",
                'coverage': [v['count'] for v in variants_sorted]
            })

    # 4. DETECT REDUNDANT _VALUE PAIRS
    # Keys that are identical except one has _value suffix
    redundant_pairs = []
    for key in specs.keys():
        if key.endswith('_value'):
            base = key[:-6]  # Remove '_value'
            if base in specs:
                redundant_pairs.append({
                    'key1': base,
                    'key2': key,
                    'reason': 'generic_value_suffix',
                    'coverage': [specs[base]['count'], specs[key]['count']],
                    'suggested_canonical': key if specs[key]['count'] > specs[base]['count'] else base
                })

    return {
        "suffix_clusters": suffix_clusters,
        "similar_pairs": similar_pairs,
        "unit_inconsistencies": unit_inconsistencies,
        "redundant_pairs": redundant_pairs
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
