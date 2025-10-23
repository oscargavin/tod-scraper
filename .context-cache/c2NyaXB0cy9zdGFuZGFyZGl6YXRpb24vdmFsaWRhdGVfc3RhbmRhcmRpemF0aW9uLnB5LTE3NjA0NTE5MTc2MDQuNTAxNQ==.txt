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


def check_units_in_values(value: str, common_units: list) -> list:
    """Check if value contains any common units."""
    found_units = []
    value_str = str(value)

    for unit in common_units:
        if re.search(rf'\b{re.escape(unit)}\b', value_str, re.IGNORECASE):
            found_units.append(unit)

    return found_units


def normalize_key(key: str) -> str:
    """Normalize key for duplicate detection."""
    return key.lower().replace('_', '').replace('-', '').replace(' ', '')


def validate_product(product: dict, product_idx: int) -> dict:
    """Validate a single product, return issues found."""
    issues = defaultdict(list)

    common_units = ['cm', 'mm', 'kg', 'g', 'rpm', 'kwh', 'watt', 'db', 'mins', 'hours']

    # Check specs
    specs = product.get('specs', {})
    normalized_keys = {}

    for key, value in specs.items():
        # Check for units in values
        units_found = check_units_in_values(value, common_units)
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
        units_found = check_units_in_values(value, common_units)
        if units_found:
            issues['units_in_features'].append({
                'product_idx': product_idx,
                'product_name': product.get('name'),
                'key': key,
                'value': value,
                'units_found': units_found
            })

    return issues


def main():
    input_file = "output/standardized_products.json"

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

    # Print validation report
    print("\n" + "="*60)
    print("VALIDATION REPORT")
    print("="*60)

    if not any(all_issues.values()):
        print("✓ All validations passed!")
    else:
        for issue_type, issue_list in all_issues.items():
            print(f"\n✗ {issue_type.replace('_', ' ').upper()}: {len(issue_list)} issues")
            for issue in issue_list[:5]:  # Show first 5
                print(f"  {issue}")
            if len(issue_list) > 5:
                print(f"  ... and {len(issue_list) - 5} more")

    # Key consistency report
    print("\n" + "="*60)
    print("KEY CONSISTENCY")
    print("="*60)

    spec_key_counts = Counter(all_spec_keys)
    feature_key_counts = Counter(all_feature_keys)

    total_products = len(data['products'])

    print(f"\nSpec keys present in all products: {sum(1 for c in spec_key_counts.values() if c == total_products)}/{len(spec_key_counts)}")
    print(f"Feature keys present in all products: {sum(1 for c in feature_key_counts.values() if c == total_products)}/{len(feature_key_counts)}")

    # Show keys with low coverage
    print(f"\nSpec keys with <50% coverage:")
    for key, count in spec_key_counts.most_common()[::-1]:
        if count < total_products * 0.5:
            print(f"  {key}: {count}/{total_products} ({count*100//total_products}%)")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()
