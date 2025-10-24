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


def format_patterns_for_prompt(patterns: Dict, total_products: int) -> str:
    """Format detected patterns into readable prompt section."""
    lines = []

    lines.append("\nDETECTED PATTERNS (pre-analyzed):\n")

    # Format suffix clusters
    if patterns['suffix_clusters']:
        lines.append("SUFFIX CLUSTERS:")
        for cluster in patterns['suffix_clusters'][:15]:  # Show top 15
            base = cluster['base']
            variants = cluster['variants']
            canonical = cluster['suggested_canonical']
            ratio = cluster['coverage_ratio']

            # Format variants list
            variants_str = " ← ".join([
                f"{v['key']} ({v['count']})" for v in variants
            ])
            lines.append(f"  • {variants_str}")
            lines.append(f"    Coverage ratio: {ratio}, Suggested canonical: {canonical}")

        if len(patterns['suffix_clusters']) > 15:
            lines.append(f"  ... and {len(patterns['suffix_clusters']) - 15} more clusters")
        lines.append("")

    # Format unit inconsistencies
    if patterns.get('unit_inconsistencies'):
        lines.append("UNIT INCONSISTENCIES:")
        for inconsistency in patterns['unit_inconsistencies']:
            variants = inconsistency['variants']
            canonical = inconsistency['suggested_canonical']
            coverage = inconsistency['coverage']
            reason = inconsistency['reason']

            variants_str = " ← ".join([
                f"{v} ({c})" for v, c in zip(variants, coverage)
            ])
            lines.append(f"  • {variants_str}")
            lines.append(f"    Reason: {reason}, Suggested canonical: {canonical}")

        lines.append("")

    # Format redundant pairs
    if patterns.get('redundant_pairs'):
        lines.append("REDUNDANT PAIRS (_value suffix):")
        for pair in patterns['redundant_pairs']:
            key1, key2 = pair['key1'], pair['key2']
            cov1, cov2 = pair['coverage']
            canonical = pair['suggested_canonical']
            lines.append(f"  • {key1} ({cov1}) ↔ {key2} ({cov2})")
            lines.append(f"    Suggested canonical: {canonical}")

        lines.append("")

    # Format similar pairs
    if patterns['similar_pairs']:
        lines.append("SIMILAR PAIRS (high string similarity):")
        for pair in patterns['similar_pairs'][:10]:  # Show top 10
            key1, key2 = pair['key1'], pair['key2']
            sim = pair['similarity']
            cov1, cov2 = pair['coverage']
            lines.append(f"  • {key1} ({cov1}) ↔ {key2} ({cov2})")
            lines.append(f"    Similarity: {int(sim*100)}%")

        if len(patterns['similar_pairs']) > 10:
            lines.append(f"  ... and {len(patterns['similar_pairs']) - 10} more pairs")
        lines.append("")

    return "\n".join(lines)


def create_analysis_prompt(analysis: Dict, min_coverage_percent: int = 10) -> str:
    """
    Create prompt for Gemini to analyze keys and generate unification map.

    Args:
        analysis: Key analysis dictionary with specs/features
        min_coverage_percent: Minimum coverage % to include keys (default: 10%)
    """
    from .analyzer import detect_duplicate_patterns

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

    # Detect duplicate patterns
    print("Detecting duplicate patterns...")
    patterns = detect_duplicate_patterns(analysis)
    print(f"Found {len(patterns['suffix_clusters'])} suffix clusters, "
          f"{len(patterns.get('unit_inconsistencies', []))} unit inconsistencies, "
          f"{len(patterns.get('redundant_pairs', []))} redundant pairs, "
          f"and {len(patterns['similar_pairs'])} similar pairs")

    # Format patterns section for prompt
    patterns_section = format_patterns_for_prompt(patterns, total_products)

    prompt = f"""ROLE: You are a data standardization expert analyzing product specifications.

CONTEXT:
- Data sources: Which.com (authoritative) + retailer sites (supplementary)
- Goal: Reduce field redundancy while preserving semantic distinctions
- Total products: {total_products}

INPUT DATA:

**SPECS ({len(filtered_specs)} unique keys, ≥{min_coverage_percent}% coverage):**
{chr(10).join(specs_summary)}

**FEATURES ({len(filtered_features)} unique keys, ≥{min_coverage_percent}% coverage):**
{chr(10).join(features_summary)}

{patterns_section}

DECISION RULES (in priority order):

1. MERGE when:
   ✓ Variants differ only by _function/_feature/_dial/_control/_mode/_value suffixes AND mean the same thing
   ✓ Coverage ratio >3:1 AND values are identical (e.g., all "Yes")
   ✓ Semantic equivalence (e.g., "adjustable_temperature" = "adjustable_temperature_control")
   ✓ Unit suffix variants: "wattage_w" vs "wattage_watt" vs "wattage_watts" → merge to shortest standard suffix (_w)
   ✓ Redundant _value suffix: "capacity" vs "capacity_value" → merge to higher coverage form

2. KEEP SEPARATE when:
   ✗ Different semantics (e.g., "bake" vs "bake_temperature_celsius")
   ✗ Different value types (e.g., "timer" boolean vs "timer_duration_mins" numeric)
   ✗ Coverage is balanced (40 vs 35 products = both are meaningful)
   ✗ Different specificity: "basket_capacity_l" vs "total_capacity_l" (different meanings)

3. CRITICAL - NEVER MERGE KEYS WITH UNITS TO KEYS WITHOUT UNITS:
   ✗ NEVER: "depth_cm" → "depth" (depth_cm has unit in key, depth has unit in value)
   ✗ NEVER: "weight_kg" → "weight" (weight_kg has unit in key, weight has unit in value)
   ✗ NEVER: "capacity_l" → "capacity" (capacity_l has unit in key, capacity has unit in value)

   WHY: Keys with unit suffixes (_cm, _kg, _l) have already-extracted values (pure numbers).
        Keys without suffixes still have units in their values ("25cm", "4.2kg").
        These are DIFFERENT and will be handled by unit extraction phase.

   ✓ DO MERGE: "depth_cm" ↔ "depth_centimeters" (both have extracted units, just different suffix forms)

4. CANONICAL SELECTION:
   • Prefer most specific name (e.g., "timer_function" > "timer" IF it clarifies meaning)
   • If specificity equal, prefer highest coverage

5. UNIT EXTRACTIONS:
   - Keys whose values contain units (like "84.3cm", "1400 RPM", "6,2 liter")
   - List ALL unit variations you see in the all_values (e.g., ["Litres", "litres", "liter", "L"])
   - CRITICAL: Put longer/more specific forms FIRST (e.g., ["Litres", "litres", "liter", "L"], NOT ["L", "Litres"])
   - Handle European decimals: "6,2" and "6.2" both mean 6.2
   - Handle ranges: "220-240V" → extract 220-240, unit is V

   UNIT SUFFIX NAMING RULES:
   - Use shortest standard unit suffix in new_key:
     • Litres/litres/L → use "_l" (e.g., capacity → capacity_l)
     • Watts/W → use "_w" (e.g., power → power_w)
     • Kilograms/kg → use "_kg" (e.g., weight → weight_kg)
     • Centimeters/cm → use "_cm" (e.g., depth → depth_cm)
     • Grams/g → use "_g"
     • Minutes/min → use "_min"
     • Hours/hr → use "_hr"
   - NEVER use generic suffixes like "_value" unless the unit is truly ambiguous
   - Examples:
     ✓ "capacity": "3.8 litres" → new_key: "capacity_l" (NOT "capacity_value")
     ✓ "power": "1700 W" → new_key: "power_w" (NOT "power_value")
     ✓ "weight": "4.2 kg" → new_key: "weight_kg" (NOT "weight_value")

6. DELETIONS:
   - Completely redundant fields (e.g., "dimensions" when we have height/width/depth separately)
   - Inventory/metadata not useful for purchase decisions

7. CROSS_CATEGORY_REMOVALS:
   - Keys that appear in both specs AND features - decide which category they belong to

EXAMPLES:

Good merge:
  timer_function → timer (both just indicate presence of timer, 5:1 coverage ratio)

Bad merge:
  timer → timer_duration_mins (different types: boolean vs numeric)

Good merge:
  air_fry_function → air_fry (semantic equivalent, _function suffix adds no meaning)

Good merge:
  wattage_w ↔ wattage_watt ↔ wattage_watts → wattage_w (unit suffix variants, standardize to shortest)

Good merge:
  capacity / capacity_value → capacity_value (redundant _value suffix, use higher coverage)

Bad merge:
  basket_capacity_l → total_capacity_l (different meanings, keep separate)

CRITICAL - BAD MERGE (unit extraction will handle this):
  depth_cm → depth (NEVER merge - depth has "25cm", depth_cm has "25")
  weight_kg → weight (NEVER merge - weight has "4.2kg", weight_kg has "4.2")
  capacity_l → capacity (NEVER merge - capacity has "3.8 litres", capacity_l has "3.8")

OUTPUT FORMAT:
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
