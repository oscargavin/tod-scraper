# Data Standardization System

Two-phase LLM-powered system to standardize product specs/features from multiple retailer sources.

## Overview

**Problem:** Product data from multiple retailers has inconsistent key names, duplicate keys, contradictory values, and units mixed into values.

**Solution:**
- Phase 1: Analyze all keys and use Gemini 2.5 Flash to generate a unification map
- Phase 2: Apply the map to create standardized data

**Category-Agnostic Design:**
- Works with **any product category** (washing machines, air fryers, TVs, etc.)
- Automatically derives output filenames from input
- No hardcoded category assumptions
- AI adapts to each category's unique specs/features

## Quick Start

```bash
# Run full pipeline on default file (complete_products.json)
python -m src.standardization.cli

# Run on ANY category file (auto-derives output filenames)
python -m src.standardization.cli --input output/air-fryers_full.json

# With verbose output
python -m src.standardization.cli --input output/air-fryers_full.json --verbose

# Force regeneration of unification map
python -m src.standardization.cli --force-regenerate
```

**Output files are automatically named based on input:**
- Input: `output/air-fryers_full.json`
- Generates:
  - `output/air-fryers_full.key_analysis.json`
  - `output/air-fryers_full.unification_map.json`
  - `output/air-fryers_full.standardized.json`

## Architecture

### Phase 1: Analysis
1. `analyzer.py` - Collect all spec/feature keys with occurrence counts
2. `generator.py` - Use Gemini to create unification map

### Phase 2: Application
3. `transformer.py` - Apply map to create standardized data
4. `validator.py` - Validate output

### Supporting Files
- `config.py` - Constants and configuration
- `cli.py` - Command-line interface
- `__init__.py` - Package API

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

## Individual Steps

Run individual steps if needed:

```bash
# Step 1: Analyze keys
python -m src.standardization.analyzer

# Step 2: Generate unification map
python -m src.standardization.generator

# Step 3: Apply standardization
python -m src.standardization.transformer

# Step 4: Validate results
python -m src.standardization.validator
```

## Programmatic Usage

```python
from src.standardization import (
    collect_keys,
    generate_unification_map,
    standardize_products,
    validate_standardization
)
from src.standardization.config import get_pipeline_paths

# Option 1: Use get_pipeline_paths() for any category (RECOMMENDED)
paths = get_pipeline_paths("output/air-fryers_full.json")

analysis = collect_keys(paths['input'])
unification_map = generate_unification_map(paths['key_analysis'], paths['unification_map'])
summary = standardize_products(paths['input'], paths['unification_map'], paths['output'])
results = validate_standardization(paths['output'])

# Option 2: Manual file paths
analysis = collect_keys("output/complete_products.json")
unification_map = generate_unification_map(
    "output/key_analysis.json",
    "output/unification_map.json"
)
summary = standardize_products(
    "output/complete_products.json",
    "output/unification_map.json",
    "output/standardized_products.json"
)
results = validate_standardization("output/standardized_products.json")
```

## Manual Refinement

If Gemini's unification map needs adjustment:

1. Edit `output/unification_map.json` manually
2. Re-run: `python -m src.standardization.transformer`
3. Re-validate: `python -m src.standardization.validator`

## Environment

Requires `GEMINI_API_KEY` in `.env` file at project root.

```bash
GEMINI_API_KEY=your_api_key_here
```

See `.env.example` for template.

## Unit Extraction

The system automatically detects and extracts units from values:

- **Pattern-based detection**: Recognizes cm, mm, kg, rpm, watt, etc.
- **Automatic conversion**: Converts mm to cm when appropriate
- **Key naming**: Appends unit suffix to key names (e.g., `height_cm`)
- **Clean values**: Extracts pure numeric values without units

Example transformation:
```json
// Before
{"height": "84.3cm", "weight": "70 kg"}

// After
{"height_cm": "84.3", "weight_kg": "70"}
```
