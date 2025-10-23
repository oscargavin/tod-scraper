# Data Standardization System Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Build a two-phase LLM-powered system to standardize product specs/features from multiple retailer sources, ensuring Which.com data takes priority and units are moved from values to key names.

**Architecture:** Phase 1 analyzes all spec/feature keys across products and uses Gemini 2.5 Flash to generate a unification map (merges, deletions, unit extractions). Phase 2 applies this map to create a standardized copy of the data with cleaned specs/features.

**Tech Stack:** Python, Gemini 2.5 Flash API, JSON

---

## Task 1: Environment Setup for Gemini API

**Files:**
- Create: `scripts/standardization/.env.example`
- Modify: `.gitignore`

**Step 1: Create directory structure**

```bash
mkdir -p scripts/standardization
```

**Step 2: Add Gemini API key to environment**

Check if `GEMINI_API_KEY` exists in `.env`:
```bash
grep -q "GEMINI_API_KEY" .env && echo "exists" || echo "missing"
```

If missing, add to `.env`:
```
GEMINI_API_KEY=your_api_key_here
```

**Step 3: Create example env file**

Create `scripts/standardization/.env.example`:
```
GEMINI_API_KEY=your_gemini_api_key_here
```

**Step 4: Install google-generativeai package**

```bash
pip install google-generativeai
```

**Step 5: Update requirements.txt**

```bash
pip freeze | grep google-generativeai >> requirements.txt
```

**Step 6: Commit**

```bash
git add scripts/standardization/.env.example requirements.txt .gitignore
git commit -m "feat: add Gemini API setup for data standardization"
```

---

## Task 2: Data Collection Script

**Files:**
- Create: `scripts/standardization/collect_keys.py`
- Test: Manual verification with output inspection

**Step 1: Write data collection script**

Create `scripts/standardization/collect_keys.py`:

```python
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
```

**Step 2: Make script executable**

```bash
chmod +x scripts/standardization/collect_keys.py
```

**Step 3: Run script to verify**

```bash
python scripts/standardization/collect_keys.py
```

Expected: Creates `output/key_analysis.json` with spec/feature analysis

**Step 4: Verify output structure**

```bash
cat output/key_analysis.json | head -30
```

Expected: JSON with total_products, specs, and features objects

**Step 5: Commit**

```bash
git add scripts/standardization/collect_keys.py output/key_analysis.json
git commit -m "feat: add key collection script for standardization analysis"
```

---

## Task 3: Gemini Unification Map Generator

**Files:**
- Create: `scripts/standardization/generate_unification_map.py`
- Test: Manual verification with sample data

**Step 1: Write Gemini integration script**

Create `scripts/standardization/generate_unification_map.py`:

```python
#!/usr/bin/env python3
"""
Use Gemini 2.5 Flash to analyze key_analysis.json and generate unification_map.json.
"""

import json
import os
from pathlib import Path
import google.generativeai as genai


def create_analysis_prompt(analysis: dict) -> str:
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


def generate_unification_map(analysis_file: str, output_file: str) -> dict:
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
    from dotenv import load_dotenv
    load_dotenv()

    analysis_file = "output/key_analysis.json"
    output_file = "output/unification_map.json"

    unification_map = generate_unification_map(analysis_file, output_file)

    print(f"\nGenerated unification map:")
    print(f"  Merges: {len(unification_map.get('merges', {}))}")
    print(f"  Deletions: {len(unification_map.get('deletions', []))}")
    print(f"  Unit extractions: {len(unification_map.get('unit_extractions', {}))}")
    print(f"  Cross-category removals: {sum(len(v) for v in unification_map.get('cross_category_removals', {}).values())}")


if __name__ == "__main__":
    main()
```

**Step 2: Install python-dotenv if needed**

```bash
pip install python-dotenv
pip freeze | grep python-dotenv >> requirements.txt
```

**Step 3: Make script executable**

```bash
chmod +x scripts/standardization/generate_unification_map.py
```

**Step 4: Run script to generate unification map**

```bash
python scripts/standardization/generate_unification_map.py
```

Expected: Creates `output/unification_map.json`

**Step 5: Inspect unification map**

```bash
cat output/unification_map.json
```

Expected: Valid JSON with merges, deletions, unit_extractions, cross_category_removals

**Step 6: Commit**

```bash
git add scripts/standardization/generate_unification_map.py requirements.txt output/unification_map.json
git commit -m "feat: add Gemini-powered unification map generator"
```

---

## Task 4: Data Standardization Application Script - Core Logic

**Files:**
- Create: `scripts/standardization/apply_standardization.py`
- Test: Manual verification with test product

**Step 1: Write standardization application script**

Create `scripts/standardization/apply_standardization.py`:

```python
#!/usr/bin/env python3
"""
Apply unification map to complete_products.json to create standardized_products.json.
"""

import json
import re
import copy
from pathlib import Path
from typing import Dict, List, Any


def normalize_key(key: str) -> str:
    """Normalize key for comparison (lowercase, no underscores/spaces)."""
    return key.lower().replace('_', '').replace('-', '').replace(' ', '')


def extract_unit_from_value(value: str, units: List[str]) -> tuple[str, str]:
    """
    Extract numeric value and unit from string.
    Returns: (numeric_value, detected_unit)
    """
    value_str = str(value).strip()

    for unit in units:
        # Try to find and remove the unit
        pattern = rf'\s*{re.escape(unit)}\s*'
        if re.search(pattern, value_str, re.IGNORECASE):
            # Remove the unit and extract number
            numeric = re.sub(pattern, '', value_str, flags=re.IGNORECASE).strip()
            return numeric, unit

    return value_str, ""


def apply_merges(specs: dict, merges: dict) -> dict:
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


def apply_deletions(specs: dict, deletions: List[str]) -> dict:
    """Remove keys marked for deletion."""
    return {k: v for k, v in specs.items() if k not in deletions}


def apply_unit_extractions(specs: dict, unit_extractions: dict) -> dict:
    """
    Extract units from values and rename keys to include units.
    Values become pure numbers/strings.
    """
    result = {}

    for key, value in specs.items():
        if key in unit_extractions:
            extraction_rule = unit_extractions[key]
            new_key = extraction_rule['new_key']
            units = extraction_rule['units']

            # Extract unit from value
            numeric_value, detected_unit = extract_unit_from_value(value, units)
            result[new_key] = numeric_value
        else:
            result[key] = value

    return result


def apply_cross_category_removals(specs: dict, features: dict, removals: dict) -> tuple[dict, dict]:
    """Remove keys from wrong category."""
    specs_to_remove = removals.get('specs', [])
    features_to_remove = removals.get('features', [])

    clean_specs = {k: v for k, v in specs.items() if k not in specs_to_remove}
    clean_features = {k: v for k, v in features.items() if k not in features_to_remove}

    return clean_specs, clean_features


def standardize_product(product: dict, unification_map: dict) -> dict:
    """Apply all standardization rules to a single product."""
    # Deep copy to avoid modifying original
    standardized = copy.deepcopy(product)

    # Get specs and features
    specs = standardized.get('specs', {})
    features = standardized.get('features', {})

    # Apply transformations in order
    specs = apply_merges(specs, unification_map.get('merges', {}))
    specs = apply_unit_extractions(specs, unification_map.get('unit_extractions', {}))
    specs = apply_deletions(specs, unification_map.get('deletions', []))

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


def main():
    input_file = "output/complete_products.json"
    map_file = "output/unification_map.json"
    output_file = "output/standardized_products.json"

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

    # Print summary
    print("\nSummary:")
    print(f"  Total products: {len(standardized_products)}")
    print(f"  Merges applied: {len(unification_map.get('merges', {}))}")
    print(f"  Deletions applied: {len(unification_map.get('deletions', []))}")
    print(f"  Unit extractions: {len(unification_map.get('unit_extractions', {}))}")


if __name__ == "__main__":
    main()
```

**Step 2: Make script executable**

```bash
chmod +x scripts/standardization/apply_standardization.py
```

**Step 3: Run standardization**

```bash
python scripts/standardization/apply_standardization.py
```

Expected: Creates `output/standardized_products.json`

**Step 4: Verify output exists and has same structure**

```bash
python3 -c "
import json
with open('output/standardized_products.json', 'r') as f:
    data = json.load(f)
print(f'Products: {len(data[\"products\"])}')
print(f'First product specs count: {len(data[\"products\"][0][\"specs\"])}')
"
```

Expected: Same number of products as input, specs/features are cleaned

**Step 5: Commit**

```bash
git add scripts/standardization/apply_standardization.py output/standardized_products.json
git commit -m "feat: add standardization application script"
```

---

## Task 5: Validation Script

**Files:**
- Create: `scripts/standardization/validate_standardization.py`
- Test: Run against standardized output

**Step 1: Write validation script**

Create `scripts/standardization/validate_standardization.py`:

```python
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
```

**Step 2: Make script executable**

```bash
chmod +x scripts/standardization/validate_standardization.py
```

**Step 3: Run validation**

```bash
python scripts/standardization/validate_standardization.py
```

Expected: Validation report showing any remaining issues

**Step 4: If issues found, review unification map**

If validation finds issues:
1. Review `output/unification_map.json`
2. Manually edit if needed
3. Re-run `apply_standardization.py`
4. Re-run validation

**Step 5: Commit**

```bash
git add scripts/standardization/validate_standardization.py
git commit -m "feat: add standardization validation script"
```

---

## Task 6: End-to-End Runner Script

**Files:**
- Create: `scripts/standardization/run_full_pipeline.sh`
- Test: Run complete pipeline

**Step 1: Create pipeline runner**

Create `scripts/standardization/run_full_pipeline.sh`:

```bash
#!/bin/bash

set -e  # Exit on error

echo "========================================"
echo "Data Standardization Pipeline"
echo "========================================"

# Check input file exists
if [ ! -f "output/complete_products.json" ]; then
    echo "Error: output/complete_products.json not found"
    exit 1
fi

# Step 1: Collect keys
echo ""
echo "[1/4] Collecting spec/feature keys..."
python scripts/standardization/collect_keys.py

# Step 2: Generate unification map
echo ""
echo "[2/4] Generating unification map with Gemini..."
python scripts/standardization/generate_unification_map.py

# Step 3: Apply standardization
echo ""
echo "[3/4] Applying standardization..."
python scripts/standardization/apply_standardization.py

# Step 4: Validate
echo ""
echo "[4/4] Validating standardized data..."
python scripts/standardization/validate_standardization.py

echo ""
echo "========================================"
echo "Pipeline complete!"
echo "Output: output/standardized_products.json"
echo "========================================"
```

**Step 2: Make script executable**

```bash
chmod +x scripts/standardization/run_full_pipeline.sh
```

**Step 3: Run full pipeline**

```bash
./scripts/standardization/run_full_pipeline.sh
```

Expected: Complete pipeline runs successfully, produces standardized output

**Step 4: Commit**

```bash
git add scripts/standardization/run_full_pipeline.sh
git commit -m "feat: add end-to-end standardization pipeline runner"
```

---

## Task 7: Documentation

**Files:**
- Create: `scripts/standardization/README.md`

**Step 1: Write documentation**

Create `scripts/standardization/README.md`:

```markdown
# Data Standardization System

Two-phase LLM-powered system to standardize product specs/features from multiple retailer sources.

## Overview

**Problem:** Product data from multiple retailers has inconsistent key names, duplicate keys, contradictory values, and units mixed into values.

**Solution:**
- Phase 1: Analyze all keys and use Gemini 2.5 Flash to generate a unification map
- Phase 2: Apply the map to create standardized data

## Quick Start

```bash
# Run full pipeline
./scripts/standardization/run_full_pipeline.sh
```

## Architecture

### Phase 1: Analysis
1. `collect_keys.py` - Collect all spec/feature keys with occurrence counts
2. `generate_unification_map.py` - Use Gemini to create unification map

### Phase 2: Application
3. `apply_standardization.py` - Apply map to create standardized data
4. `validate_standardization.py` - Validate output

## Key Principles

- **Which.com data always wins** - Appears first in JSON, kept during merges
- **Units in keys, not values** - `height_cm: 84.3` not `height: "84.3cm"`
- **Enrich only** - Retailer data fills gaps, doesn't override

## Files

**Input:**
- `output/complete_products.json` - Raw product data from scrapers

**Intermediate:**
- `output/key_analysis.json` - Key occurrence analysis
- `output/unification_map.json` - LLM-generated standardization rules

**Output:**
- `output/standardized_products.json` - Clean, standardized data

## Manual Refinement

If Gemini's unification map needs adjustment:

1. Edit `output/unification_map.json` manually
2. Re-run: `python scripts/standardization/apply_standardization.py`
3. Re-validate: `python scripts/standardization/validate_standardization.py`

## Environment

Requires `GEMINI_API_KEY` in `.env` file.

```bash
GEMINI_API_KEY=your_api_key_here
```
```

**Step 2: Commit**

```bash
git add scripts/standardization/README.md
git commit -m "docs: add standardization system documentation"
```

---

## Final Task: Integration Test

**Step 1: Clean previous outputs**

```bash
rm -f output/key_analysis.json output/unification_map.json output/standardized_products.json
```

**Step 2: Run full pipeline**

```bash
./scripts/standardization/run_full_pipeline.sh
```

**Step 3: Compare before/after**

```bash
python3 -c "
import json

with open('output/complete_products.json', 'r') as f:
    original = json.load(f)

with open('output/standardized_products.json', 'r') as f:
    standardized = json.load(f)

print('BEFORE:')
print(f'  Total products: {len(original[\"products\"])}')
print(f'  Sample spec keys: {list(original[\"products\"][0][\"specs\"].keys())[:10]}')

print('\nAFTER:')
print(f'  Total products: {len(standardized[\"products\"])}')
print(f'  Sample spec keys: {list(standardized[\"products\"][0][\"specs\"].keys())[:10]}')

# Check for units in keys
unit_keys = [k for k in standardized['products'][0]['specs'].keys() if any(u in k for u in ['_cm', '_kg', '_rpm', '_kwh'])]
print(f'\n  Keys with units: {unit_keys[:5]}')
"
```

Expected: Standardized data has cleaner keys with units in key names

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete data standardization system

- Phase 1: Collect keys and generate LLM unification map
- Phase 2: Apply map to standardize specs/features
- Which.com data prioritized, units moved to key names
- Full validation and pipeline runner included"
```

---

## Success Criteria

✅ Units extracted from values and added to key names
✅ Duplicate keys merged (Which.com wins)
✅ Redundant keys deleted
✅ Cross-category keys moved to correct location
✅ All products maintain same structure, only specs/features modified
✅ Validation passes with no units in values
✅ Pipeline runs end-to-end successfully
