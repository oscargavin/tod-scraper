#!/usr/bin/env python3
"""
Validate standardized_products.json to ensure:
1. No units remain in values
2. No duplicate keys (normalized)
3. All products have consistent key sets
"""

import json
import re
from collections import Counter, defaultdict
from typing import Dict, List

from .config import DEFAULT_OUTPUT_FILE, COMMON_UNITS


def check_units_in_values(value: str, common_units: List[str]) -> List[str]:
    """
    Check if value contains any common units (with digits).
    Only flags units that have a digit preceding them to avoid false positives like "A to G".
    """
    found_units = []
    value_str = str(value)

    for unit in common_units:
        # Pattern requires a digit before the unit to avoid false positives
        pattern = rf'\b(\d+\.?\d*)\s*{re.escape(unit)}\b'
        if re.search(pattern, value_str, re.IGNORECASE):
            found_units.append(unit)

    return found_units


def normalize_key(key: str) -> str:
    """Normalize key for duplicate detection."""
    return key.lower().replace('_', '').replace('-', '').replace(' ', '')


def validate_product(product: Dict, product_idx: int) -> Dict:
    """Validate a single product, return issues found."""
    issues = defaultdict(list)

    # Check specs
    specs = product.get('specs', {})
    normalized_keys = {}

    for key, value in specs.items():
        # Check for units in values
        units_found = check_units_in_values(value, COMMON_UNITS)
        if units_found:
            issues['units_in_values'].append({
                'product_idx': product_idx,
                'product_name': product.get('name'),
                'key': key,
                'value': value,
                'units_found': units_found
            })

        # Check for duplicate keys
        normalized = normalize_key(key)
        if normalized in normalized_keys:
            issues['duplicate_keys'].append({
                'product_idx': product_idx,
                'product_name': product.get('name'),
                'key1': normalized_keys[normalized],
                'key2': key
            })
        else:
            normalized_keys[normalized] = key

    # Check features
    features = product.get('features', {})
    for key, value in features.items():
        units_found = check_units_in_values(value, COMMON_UNITS)
        if units_found:
            issues['units_in_features'].append({
                'product_idx': product_idx,
                'product_name': product.get('name'),
                'key': key,
                'value': value,
                'units_found': units_found
            })

    return issues


def validate_standardization(input_file: str) -> Dict:
    """
    Validate standardized products file.

    Returns:
        Dictionary with validation results and statistics.
    """
    print(f"Validating {input_file}...")

    with open(input_file, 'r') as f:
        data = json.load(f)

    all_issues = defaultdict(list)
    all_spec_keys = []
    all_feature_keys = []

    # Validate each product
    for idx, product in enumerate(data['products']):
        issues = validate_product(product, idx)
        for issue_type, issue_list in issues.items():
            all_issues[issue_type].extend(issue_list)

        all_spec_keys.extend(product.get('specs', {}).keys())
        all_feature_keys.extend(product.get('features', {}).keys())

    # Calculate statistics
    spec_key_counts = Counter(all_spec_keys)
    feature_key_counts = Counter(all_feature_keys)
    total_products = len(data['products'])

    return {
        'issues': dict(all_issues),
        'total_products': total_products,
        'spec_key_counts': spec_key_counts,
        'feature_key_counts': feature_key_counts,
        'passed': not any(all_issues.values())
    }


def print_validation_report(results: Dict):
    """Print formatted validation report."""
    print("\n" + "="*60)
    print("VALIDATION REPORT")
    print("="*60)

    if results['passed']:
        print("✓ All validations passed!")
    else:
        issues = results['issues']
        for issue_type, issue_list in issues.items():
            print(f"\n✗ {issue_type.replace('_', ' ').upper()}: {len(issue_list)} issues")
            for issue in issue_list[:5]:  # Show first 5
                print(f"  {issue}")
            if len(issue_list) > 5:
                print(f"  ... and {len(issue_list) - 5} more")

    # Key consistency report
    print("\n" + "="*60)
    print("KEY CONSISTENCY")
    print("="*60)

    spec_key_counts = results['spec_key_counts']
    feature_key_counts = results['feature_key_counts']
    total_products = results['total_products']

    print(f"\nSpec keys present in all products: {sum(1 for c in spec_key_counts.values() if c == total_products)}/{len(spec_key_counts)}")
    print(f"Feature keys present in all products: {sum(1 for c in feature_key_counts.values() if c == total_products)}/{len(feature_key_counts)}")

    # Show keys with low coverage
    print(f"\nSpec keys with <50% coverage:")
    for key, count in spec_key_counts.most_common()[::-1]:
        if count < total_products * 0.5:
            print(f"  {key}: {count}/{total_products} ({count*100//total_products}%)")

    print("\n" + "="*60)


def main():
    """Main entry point for validation."""
    input_file = DEFAULT_OUTPUT_FILE
    results = validate_standardization(input_file)
    print_validation_report(results)


if __name__ == "__main__":
    main()
