#!/usr/bin/env python3
"""
Use Gemini to normalize field values across products.
Handles language mixing, case inconsistencies, formatting variations, etc.
"""

import json
import os
from typing import Dict, List, Set
from collections import defaultdict
import google.generativeai as genai


def collect_field_values(products: List[Dict]) -> Dict[str, Set[str]]:
    """
    Collect all unique values for each field across all products.

    Returns:
        {field_name: set of unique values}
    """
    field_values = defaultdict(set)

    for product in products:
        # Collect from specs
        for key, value in product.get('specs', {}).items():
            # Skip empty values
            if value is not None and str(value).strip():
                field_values[key].add(str(value))

        # Collect from features
        for key, value in product.get('features', {}).items():
            if value is not None and str(value).strip():
                field_values[key].add(str(value))

    # Convert sets to sorted lists for consistent ordering
    return {k: sorted(list(v)) for k, v in field_values.items()}


def should_normalize_field(field_name: str, values: List[str]) -> bool:
    """
    Determine if a field needs normalization.
    Skip numeric fields, fields with only 1 value, etc.
    """
    # Skip if only one unique value
    if len(values) <= 1:
        return False

    # Skip fields with '_value' suffix (already extracted units, should be numeric)
    if field_name.endswith('_value'):
        return False

    # Skip if all values are purely numeric
    try:
        all_numeric = all(float(v.replace(',', '.')) for v in values if v)
        if all_numeric:
            return False
    except (ValueError, AttributeError):
        pass  # Not all numeric, continue

    # Normalize if we see potential issues
    # 1. Case variations (Black vs black)
    lower_values = [v.lower() for v in values]
    if len(set(lower_values)) < len(values):
        return True

    # 2. Common boolean variations (Yes/Ja/No)
    boolean_variants = {'yes', 'ja', 'oui', 'si', 'no', 'nee', 'non', 'nein'}
    if any(v.lower() in boolean_variants for v in values):
        return True

    # 3. Multiple values (probably needs normalization)
    if len(values) >= 3:
        return True

    return False


def create_normalization_prompt(field_name: str, values: List[str]) -> str:
    """
    Create prompt for Gemini to normalize field values.
    """
    values_str = '\n'.join([f'  - "{v}"' for v in values])

    prompt = f"""You are normalizing product specification values for the field "{field_name}".

CURRENT VALUES:
{values_str}

Your task: Normalize these values following these rules:

1. LANGUAGE: Translate to English
   - "Ja" → "Yes"
   - "Nee" / "Non" → "No"
   - "Maximaal 60 minuten" → describe in English

2. CASE: Use consistent capitalization
   - Booleans: "Yes" / "No" (title case)
   - Colors: "Black", "Silver" (title case each word)
   - Other categorical: Title case for readability

3. FORMATTING: Clean up inconsistencies
   - Separators: Use " / " for combinations (e.g., "Black / Silver")
   - Remove redundant words (e.g., "Black 5-in-1" → "Black")
   - Trim whitespace

4. CONSOLIDATION: Merge equivalent values
   - "Black/Silver", "Black, Silver", "Black & Silver" → "Black / Silver"
   - "Drawer" vs "drawer" → "Drawer"

5. PRESERVE MEANING: Don't change semantics
   - "Matte Black" stays "Matte Black" (different from "Black")
   - "Cyber Space Blue" stays as is (specific product name)

6. NUMERIC: Keep numeric values as-is (no translation needed)

Output format (JSON):
{{
  "original_value1": "normalized_value1",
  "original_value2": "normalized_value2"
}}

Return ONLY the JSON mapping, nothing else.
"""
    return prompt


def normalize_field_values(field_name: str, values: List[str]) -> Dict[str, str]:
    """
    Use Gemini to normalize values for a single field.

    Returns:
        Mapping of original_value → normalized_value
    """
    # Load API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    genai.configure(api_key=api_key)

    # Create prompt
    prompt = create_normalization_prompt(field_name, values)

    # Call Gemini
    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)

    # Parse response
    response_text = response.text.strip()

    # Remove markdown code blocks if present
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        response_text = '\n'.join(lines[1:-1])
        if response_text.startswith('json'):
            response_text = response_text[4:].strip()

    normalization_map = json.loads(response_text)

    return normalization_map


def normalize_all_values(products: List[Dict], verbose: bool = True) -> tuple:
    """
    Normalize values across all fields in all products using Gemini.

    Args:
        products: List of product dicts with specs/features
        verbose: Print progress

    Returns:
        (normalized_products, normalization_stats)
    """
    # Step 1: Collect unique values per field
    if verbose:
        print("Collecting unique values per field...")

    field_values = collect_field_values(products)

    # Step 2: Determine which fields need normalization
    fields_to_normalize = []
    for field_name, values in field_values.items():
        if should_normalize_field(field_name, values):
            fields_to_normalize.append((field_name, values))

    if verbose:
        print(f"Found {len(fields_to_normalize)} fields needing normalization")

    # Step 3: Normalize each field with Gemini
    all_normalizations = {}

    for i, (field_name, values) in enumerate(fields_to_normalize, 1):
        if verbose:
            print(f"  [{i}/{len(fields_to_normalize)}] Normalizing {field_name} ({len(values)} unique values)...")

        try:
            normalization_map = normalize_field_values(field_name, values)
            all_normalizations[field_name] = normalization_map
        except Exception as e:
            if verbose:
                print(f"    Warning: Failed to normalize {field_name}: {e}")
            continue

    # Step 4: Apply normalizations to all products
    if verbose:
        print("\nApplying normalizations to products...")

    normalized_products = []
    total_changes = 0

    for product in products:
        normalized = product.copy()

        # Normalize specs
        if 'specs' in normalized:
            normalized_specs = {}
            for key, value in normalized['specs'].items():
                if key in all_normalizations and str(value) in all_normalizations[key]:
                    normalized_value = all_normalizations[key][str(value)]
                    normalized_specs[key] = normalized_value
                    if normalized_value != str(value):
                        total_changes += 1
                else:
                    normalized_specs[key] = value
            normalized['specs'] = normalized_specs

        # Normalize features
        if 'features' in normalized:
            normalized_features = {}
            for key, value in normalized['features'].items():
                if key in all_normalizations and str(value) in all_normalizations[key]:
                    normalized_value = all_normalizations[key][str(value)]
                    normalized_features[key] = normalized_value
                    if normalized_value != str(value):
                        total_changes += 1
                else:
                    normalized_features[key] = value
            normalized['features'] = normalized_features

        normalized_products.append(normalized)

    # Stats
    stats = {
        'fields_normalized': len(all_normalizations),
        'total_value_changes': total_changes,
        'normalization_maps': all_normalizations
    }

    return normalized_products, stats


def main():
    """Test the value normalizer."""
    from dotenv import load_dotenv
    load_dotenv()

    # Test on a sample file
    import sys
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = 'output/complete_products.standardized.json'

    print(f"Loading {input_file}...")
    with open(input_file) as f:
        data = json.load(f)

    products = data['products']

    normalized_products, stats = normalize_all_values(products, verbose=True)

    print(f"\nNormalization complete!")
    print(f"  Fields normalized: {stats['fields_normalized']}")
    print(f"  Total value changes: {stats['total_value_changes']}")

    # Show some examples
    print("\nSample normalizations:")
    for field_name, mapping in list(stats['normalization_maps'].items())[:5]:
        print(f"\n{field_name}:")
        for orig, norm in list(mapping.items())[:5]:
            if orig != norm:
                print(f"  {orig} → {norm}")


if __name__ == "__main__":
    main()
