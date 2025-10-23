#!/usr/bin/env python3
"""
Collect all spec and feature keys from complete_products.json.
Output: key_analysis.json with occurrence counts and sample values.
"""

import json
from collections import defaultdict
from pathlib import Path


def collect_keys(products_file: str) -> dict:
    """Collect all spec/feature keys with counts and samples."""
    with open(products_file, 'r') as f:
        data = json.load(f)

    spec_analysis = defaultdict(lambda: {"count": 0, "samples": []})
    feature_analysis = defaultdict(lambda: {"count": 0, "samples": []})

    for product in data['products']:
        # Analyze specs
        for key, value in product.get('specs', {}).items():
            spec_analysis[key]["count"] += 1
            if len(spec_analysis[key]["samples"]) < 10:
                spec_analysis[key]["samples"].append(str(value))

        # Analyze features
        for key, value in product.get('features', {}).items():
            feature_analysis[key]["count"] += 1
            if len(feature_analysis[key]["samples"]) < 10:
                feature_analysis[key]["samples"].append(str(value))

    total_products = len(data['products'])

    return {
        "total_products": total_products,
        "specs": dict(spec_analysis),
        "features": dict(feature_analysis)
    }


def main():
    input_file = "output/complete_products.json"
    output_file = "output/key_analysis.json"

    print(f"Analyzing keys from {input_file}...")
    analysis = collect_keys(input_file)

    print(f"Found {len(analysis['specs'])} unique spec keys")
    print(f"Found {len(analysis['features'])} unique feature keys")

    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)

    print(f"Analysis saved to {output_file}")


if __name__ == "__main__":
    main()
