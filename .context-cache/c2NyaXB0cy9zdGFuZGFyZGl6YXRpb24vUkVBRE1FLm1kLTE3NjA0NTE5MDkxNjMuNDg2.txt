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
