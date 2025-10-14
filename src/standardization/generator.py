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


def create_analysis_prompt(analysis: Dict) -> str:
    """Create prompt for Gemini to analyze keys and generate unification map."""

    specs_summary = []
    for key, data in sorted(analysis['specs'].items(), key=lambda x: x[1]['count'], reverse=True):
        coverage = f"{data['count']}/{analysis['total_products']}"
        samples = ", ".join(data['samples'][:5])
        specs_summary.append(f"  - {key} ({coverage} products): [{samples}]")

    features_summary = []
    for key, data in sorted(analysis['features'].items(), key=lambda x: x[1]['count'], reverse=True):
        coverage = f"{data['count']}/{analysis['total_products']}"
        samples = ", ".join(data['samples'][:5])
        features_summary.append(f"  - {key} ({coverage} products): [{samples}]")

    prompt = f"""You are analyzing product specification data from multiple sources. The data comes from Which.com (authoritative source, appears first) and various retailer sites (supplementary data).

**SPECS ({len(analysis['specs'])} unique keys):**
{chr(10).join(specs_summary)}

**FEATURES ({len(analysis['features'])} unique keys):**
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
2. DELETIONS: Keys that are completely redundant (e.g., "dimensions" when we have height/width/depth separately).
3. UNIT_EXTRACTIONS: Keys whose values contain units (like "84.3cm", "1400 RPM"). Extract units from values and add to key names. List all unit variations to strip.
4. CROSS_CATEGORY_REMOVALS: Keys that appear in both specs AND features - decide which category they belong to and remove from the other.
5. Units should ONLY be in key names, NEVER in values. Values should be pure numbers or strings.
6. Use snake_case for all keys.
7. Do NOT include reasoning or explanations, only the JSON map.

Return ONLY valid JSON, nothing else."""

    return prompt


def generate_unification_map(analysis_file: str, output_file: str) -> Dict:
    """Call Gemini API to generate unification map."""

    # Load API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")

    genai.configure(api_key=api_key)

    # Load analysis
    with open(analysis_file, 'r') as f:
        analysis = json.load(f)

    # Create prompt
    prompt = create_analysis_prompt(analysis)

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


def main():
    """Main entry point for map generation."""
    from dotenv import load_dotenv
    load_dotenv()

    analysis_file = DEFAULT_KEY_ANALYSIS_FILE
    output_file = DEFAULT_UNIFICATION_MAP_FILE

    unification_map = generate_unification_map(analysis_file, output_file)

    print(f"\nGenerated unification map:")
    print(f"  Merges: {len(unification_map.get('merges', {}))}")
    print(f"  Deletions: {len(unification_map.get('deletions', []))}")
    print(f"  Unit extractions: {len(unification_map.get('unit_extractions', {}))}")
    print(f"  Cross-category removals: {sum(len(v) for v in unification_map.get('cross_category_removals', {}).values())}")


if __name__ == "__main__":
    main()
