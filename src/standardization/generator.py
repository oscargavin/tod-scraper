#!/usr/bin/env python3
"""
Use Gemini 2.5 Flash to analyze key_analysis.json and generate unification_map.json.
"""

import json
import os
from pathlib import Path
from typing import Dict
import google.generativeai as genai

from .config import DEFAULT_KEY_ANALYSIS_FILE, DEFAULT_UNIFICATION_MAP_FILE


def create_analysis_prompt(analysis: Dict, min_coverage_percent: int = 10) -> str:
    """
    Create prompt for Gemini to analyze keys and generate unification map.

    Args:
        analysis: Key analysis dictionary with specs/features
        min_coverage_percent: Minimum coverage % to include keys (default: 10%)
    """
    total_products = analysis['total_products']
    min_count = max(2, int(total_products * min_coverage_percent / 100))  # At least 2 products

    # Filter specs by coverage
    filtered_specs = {
        key: data for key, data in analysis['specs'].items()
        if data['count'] >= min_count
    }

    # Filter features by coverage
    filtered_features = {
        key: data for key, data in analysis['features'].items()
        if data['count'] >= min_count
    }

    specs_summary = []
    for key, data in sorted(filtered_specs.items(), key=lambda x: x[1]['count'], reverse=True):
        coverage = f"{data['count']}/{total_products}"

        # If we have all_values (for unit-containing keys), show them all
        if 'all_values' in data and data['all_values']:
            all_vals = ", ".join(data['all_values'][:20])  # Show up to 20 unique values
            if len(data['all_values']) > 20:
                all_vals += f" ... ({len(data['all_values'])} total unique values)"
            specs_summary.append(f"  - {key} ({coverage} products): [{all_vals}]")
        else:
            # Otherwise show samples
            samples = ", ".join(data['samples'][:5])
            specs_summary.append(f"  - {key} ({coverage} products): [{samples}]")

    features_summary = []
    for key, data in sorted(filtered_features.items(), key=lambda x: x[1]['count'], reverse=True):
        coverage = f"{data['count']}/{total_products}"
        samples = ", ".join(data['samples'][:5])
        features_summary.append(f"  - {key} ({coverage} products): [{samples}]")

    # Log filtering stats
    specs_filtered = len(analysis['specs']) - len(filtered_specs)
    features_filtered = len(analysis['features']) - len(filtered_features)
    print(f"Filtered out {specs_filtered} low-coverage spec keys (<{min_coverage_percent}% coverage)")
    print(f"Filtered out {features_filtered} low-coverage feature keys (<{min_coverage_percent}% coverage)")

    prompt = f"""You are analyzing product specification data from multiple sources. The data comes from Which.com (authoritative source, appears first) and various retailer sites (supplementary data).

**SPECS ({len(filtered_specs)} unique keys, ≥{min_coverage_percent}% coverage):**
{chr(10).join(specs_summary)}

**FEATURES ({len(filtered_features)} unique keys, ≥{min_coverage_percent}% coverage):**
{chr(10).join(features_summary)}

Your task: Generate a unification map as valid JSON with this exact structure:

{{
  "merges": {{
    "alias_key": "canonical_key"
  }},
  "deletions": ["key_to_delete"],
  "unit_extractions": {{
    "current_key": {{
      "units": ["unit1", "unit2"],
      "new_key": "key_with_unit"
    }}
  }},
  "cross_category_removals": {{
    "specs": ["key_in_specs_but_belongs_in_features"],
    "features": ["key_in_features_but_belongs_in_specs"]
  }}
}}

Rules:
1. MERGES: When multiple keys represent the same concept (e.g., "max_spin_speed" and "max_spin_speed_rpm"), map the less specific one to the more specific canonical version.
2. DELETIONS: Delete keys that are:
   - Completely redundant (e.g., "dimensions" when we have height/width/depth separately)
   - Inventory/metadata not useful for purchase decisions (e.g., variations of part_number, sku, ean, product_code, item_number, catalog_number)
   - Redundant identifiers (e.g., id, product_id, variant_id)
   - Retailer-specific operational data (e.g., stock_status, availability, delivery_time)
3. UNIT_EXTRACTIONS: Keys whose values contain units (like "84.3cm", "1400 RPM", "6,2 liter"). Extract units from values and add to key names.
   - List ALL unit variations you see in the all_values (e.g., ["Litres", "litres", "liter", "L", "l"])
   - Handle European decimals: "6,2" and "6.2" both mean 6.2
   - Handle ranges: "220-240V" → extract 220-240, unit is V
   - Handle complex units: "1–48 hr" → extract 1-48, unit is hr
   - CRITICAL: Put longer/more specific forms FIRST (e.g., ["Litres", "litres", "liter", "L"], NOT ["L", "Litres"])
4. CROSS_CATEGORY_REMOVALS: Keys that appear in both specs AND features - decide which category they belong to and remove from the other.
5. Units should ONLY be in key names, NEVER in values. Values should be pure numbers or strings.
6. Use snake_case for all keys.
7. When you see all_values for a key, use THOSE values (not samples) to determine ALL unit variations.
8. Do NOT include reasoning or explanations, only the JSON map.

Return ONLY valid JSON, nothing else."""

    return prompt


def generate_unification_map(analysis_file: str, output_file: str, min_coverage_percent: int = 10) -> Dict:
    """
    Call Gemini API to generate unification map.

    Args:
        analysis_file: Path to key analysis JSON
        output_file: Path to save unification map
        min_coverage_percent: Minimum coverage % for keys to include (default: 10%)
    """
    # Load API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    genai.configure(api_key=api_key)

    # Load analysis
    with open(analysis_file, 'r') as f:
        analysis = json.load(f)

    # Create prompt (with coverage filtering)
    prompt = create_analysis_prompt(analysis, min_coverage_percent=min_coverage_percent)

    # Call Gemini
    print("Calling Gemini 2.5 Flash API...")
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

    unification_map = json.loads(response_text)

    # Save to file
    with open(output_file, 'w') as f:
        json.dump(unification_map, f, indent=2)

    print(f"Unification map saved to {output_file}")
    return unification_map


def main(analysis_file: str = None, output_file: str = None, min_coverage_percent: int = 10):
    """
    Main entry point for map generation.

    Args:
        analysis_file: Path to key analysis JSON (default: DEFAULT_KEY_ANALYSIS_FILE)
        output_file: Path to output unification map JSON (default: DEFAULT_UNIFICATION_MAP_FILE)
        min_coverage_percent: Minimum coverage % for keys to include (default: 10%)
    """
    from dotenv import load_dotenv
    load_dotenv()

    analysis_file = analysis_file or DEFAULT_KEY_ANALYSIS_FILE
    output_file = output_file or DEFAULT_UNIFICATION_MAP_FILE

    unification_map = generate_unification_map(analysis_file, output_file, min_coverage_percent=min_coverage_percent)

    print(f"\nGenerated unification map:")
    print(f"  Merges: {len(unification_map.get('merges', {}))}")
    print(f"  Deletions: {len(unification_map.get('deletions', []))}")
    print(f"  Unit extractions: {len(unification_map.get('unit_extractions', {}))}")
    print(f"  Cross-category removals: {sum(len(v) for v in unification_map.get('cross_category_removals', {}).values())}")


if __name__ == "__main__":
    main()
