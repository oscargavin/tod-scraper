#!/usr/bin/env python3
"""
Auto-categorize fields into specs vs features based on value types.

Rules:
- Boolean fields (all values in {"Yes", "No", "True", "False"}) → Features
- Everything else (numeric, categorical text, mixed) → Specs
"""

import json
import copy
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from .config import DEFAULT_OUTPUT_FILE


# Boolean value variations (case-insensitive)
BOOLEAN_VALUES = {"yes", "no", "true", "false"}


def is_boolean_field(values: Set[str]) -> bool:
    """
    Check if all non-empty values are boolean-like.

    Args:
        values: Set of unique values for a field

    Returns:
        True if all non-empty values are boolean ("Yes"/"No"/"True"/"False")
    """
    # Filter out None and empty strings
    non_empty = {str(v).strip() for v in values if v and str(v).strip()}

    # Empty field - can't determine, treat as non-boolean
    if not non_empty:
        return False

    # Check if all values are boolean (case-insensitive)
    return all(v.lower() in BOOLEAN_VALUES for v in non_empty)


def collect_field_values(products: List[Dict]) -> Tuple[Dict[str, Set], Dict[str, Set]]:
    """
    Collect all unique values for each field across all products.

    Returns:
        (spec_field_values, feature_field_values)
        Each is a dict: {field_name: set_of_unique_values}
    """
    spec_values = defaultdict(set)
    feature_values = defaultdict(set)

    for product in products:
        # Collect from specs
        for key, value in product.get('specs', {}).items():
            # Convert lists to tuples (hashable) for set storage
            if isinstance(value, list):
                spec_values[key].add(tuple(value))
            else:
                spec_values[key].add(value)

        # Collect from features
        for key, value in product.get('features', {}).items():
            # Convert lists to tuples (hashable) for set storage
            if isinstance(value, list):
                feature_values[key].add(tuple(value))
            else:
                feature_values[key].add(value)

    return dict(spec_values), dict(feature_values)


def categorize_fields(spec_values: Dict[str, Set], feature_values: Dict[str, Set]) -> Dict:
    """
    Determine which fields should move between specs and features.

    Args:
        spec_values: {field_name: set_of_values} from specs
        feature_values: {field_name: set_of_values} from features

    Returns:
        {
            "move_to_features": [list of field names],
            "move_to_specs": [list of field names],
            "stats": {...}
        }
    """
    move_to_features = []
    move_to_specs = []

    # Check specs - move boolean fields to features
    for field_name, values in spec_values.items():
        if is_boolean_field(values):
            move_to_features.append(field_name)

    # Check features - move non-boolean fields to specs
    for field_name, values in feature_values.items():
        if not is_boolean_field(values):
            move_to_specs.append(field_name)

    return {
        "move_to_features": sorted(move_to_features),
        "move_to_specs": sorted(move_to_specs),
        "stats": {
            "total_spec_fields": len(spec_values),
            "total_feature_fields": len(feature_values),
            "boolean_fields_in_specs": len(move_to_features),
            "non_boolean_fields_in_features": len(move_to_specs)
        }
    }


def apply_categorization(products: List[Dict], categorization: Dict) -> List[Dict]:
    """
    Apply field categorization to all products.

    Args:
        products: List of product dicts
        categorization: Output from categorize_fields()

    Returns:
        List of products with fields moved to correct categories
    """
    move_to_features = set(categorization["move_to_features"])
    move_to_specs = set(categorization["move_to_specs"])

    recategorized_products = []

    for product in products:
        recategorized = copy.deepcopy(product)
        specs = recategorized.get('specs', {})
        features = recategorized.get('features', {})

        # Move boolean fields from specs to features
        fields_to_move = {}
        for field_name in move_to_features:
            if field_name in specs:
                fields_to_move[field_name] = specs.pop(field_name)

        # Add them to features
        features.update(fields_to_move)

        # Move non-boolean fields from features to specs
        fields_to_move = {}
        for field_name in move_to_specs:
            if field_name in features:
                fields_to_move[field_name] = features.pop(field_name)

        # Add them to specs
        specs.update(fields_to_move)

        # Update product
        recategorized['specs'] = specs
        recategorized['features'] = features

        recategorized_products.append(recategorized)

    return recategorized_products


def auto_categorize(input_file: str, verbose: bool = True) -> Dict:
    """
    Auto-categorize fields into specs vs features based on value types.

    Args:
        input_file: Path to standardized products JSON
        verbose: Print progress messages

    Returns:
        Statistics about categorization
    """
    if verbose:
        print(f"Loading {input_file}...")

    # Load data
    with open(input_file, 'r') as f:
        data = json.load(f)

    products = data['products']

    if verbose:
        print(f"Analyzing {len(products)} products...")

    # Collect all field values
    spec_values, feature_values = collect_field_values(products)

    if verbose:
        print(f"  Found {len(spec_values)} unique spec fields")
        print(f"  Found {len(feature_values)} unique feature fields")

    # Determine categorization
    categorization = categorize_fields(spec_values, feature_values)

    # Show what will be moved
    move_to_features = categorization["move_to_features"]
    move_to_specs = categorization["move_to_specs"]

    if verbose:
        print(f"\nCategorization plan:")
        print(f"  Boolean fields to move to features: {len(move_to_features)}")
        if move_to_features and len(move_to_features) <= 10:
            for field in move_to_features:
                print(f"    - {field}")
        elif move_to_features:
            for field in move_to_features[:10]:
                print(f"    - {field}")
            print(f"    ... and {len(move_to_features) - 10} more")

        print(f"  Non-boolean fields to move to specs: {len(move_to_specs)}")
        if move_to_specs and len(move_to_specs) <= 10:
            for field in move_to_specs:
                print(f"    - {field}")
        elif move_to_specs:
            for field in move_to_specs[:10]:
                print(f"    - {field}")
            print(f"    ... and {len(move_to_specs) - 10} more")

    # Check if any changes needed
    if not move_to_features and not move_to_specs:
        if verbose:
            print("\n✓ No categorization changes needed - fields already in correct categories")
        return categorization["stats"]

    # Apply categorization
    if verbose:
        print(f"\nApplying categorization...")

    recategorized_products = apply_categorization(products, categorization)

    # Save back to file
    data['products'] = recategorized_products

    with open(input_file, 'w') as f:
        json.dump(data, f, indent=2)

    if verbose:
        print(f"✓ Categorization complete, saved to {input_file}")

    return categorization["stats"]


def main(input_file: str = None):
    """
    CLI entry point for categorizer.

    Args:
        input_file: Path to standardized products JSON (default: DEFAULT_OUTPUT_FILE)
    """
    input_file = input_file or DEFAULT_OUTPUT_FILE

    stats = auto_categorize(input_file, verbose=True)

    print("\n" + "="*60)
    print("CATEGORIZATION SUMMARY")
    print("="*60)
    print(f"Total spec fields: {stats['total_spec_fields']}")
    print(f"Total feature fields: {stats['total_feature_fields']}")
    print(f"Boolean fields moved to features: {stats['boolean_fields_in_specs']}")
    print(f"Non-boolean fields moved to specs: {stats['non_boolean_fields_in_features']}")
    print("="*60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
