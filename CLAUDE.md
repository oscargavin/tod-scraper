# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a comprehensive web scraping system for Which.com product reviews with AO.com review enrichment capabilities. The system uses Playwright for browser automation and supports parallel processing with multiple workers.

## Key Commands

### Running Scrapers
```bash
# Basic scraping (default: discovery + specs + standardization + metadata)
python src/scrapers/which/complete_scraper.py --pages 2

# Full enrichment pipeline with database insertion
python src/scrapers/which/complete_scraper.py --pages all --enrich-retailers --enrich-reviews --save-to-db

# Maximum enrichment (including AI)
python src/scrapers/which/complete_scraper.py --pages all --enrich-retailers --enrich-reviews --enrich-ai --save-to-db

# Quick product discovery only (no specs)
python src/scrapers/which/complete_scraper.py --pages 3 --skip-specs

# Raw data only (skip processing phases)
python src/scrapers/which/complete_scraper.py --pages 2 --no-standardization --no-metadata
```

### Database Operations
```bash
# Insert scraped data into Supabase
python insert_to_db.py

# Insert to main database
python insert_to_main_db.py

# Fix prices in database
python fix_prices.py

# Transfer images between databases
python transfer_images.py
```

### Standardization Pipeline
```bash
# Run full standardization pipeline
python -m src.standardization.cli --input output/complete_products.json

# Run on specific category
python -m src.standardization.cli --input output/air-fryers_full.json

# Skip value normalization (faster)
python -m src.standardization.cli --no-value-normalization

# Individual steps
python -m src.standardization.analyzer
python -m src.standardization.generator
python -m src.standardization.transformer
python -m src.standardization.value_normalizer
python -m src.standardization.categorizer
python -m src.standardization.validator
```

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Set up Gemini API for standardization (required)
echo "GEMINI_API_KEY=your_api_key" >> .env
```

## Architecture

### 10-Phase Scraping Pipeline

The scraper operates as a sequential 10-phase pipeline:

**Data Collection (Phases 1-7):**
1. **Product Discovery** - Which.com listings
2. **Base Spec Extraction** - Which.com specs and features
3. **Retailer Link Discovery** - DuckDuckGo search for retailer URLs
4. **Retailer Spec Enrichment** - Additional specs from AO, Currys, etc. (opt-in)
5. **PDF Spec Enrichment** - Manufacturer PDFs as fallback (automatic with Phase 4)
6. **Review Enrichment** - Customer reviews from AO/Boots/Amazon (opt-in)
7. **AI Spec Enrichment** - Gemini AI fallback for missing specs (opt-in)

**Data Processing & Persistence (Phases 8-10):**
8. **Data Standardization** - AI-powered 6-step pipeline to clean and unify field names/units (runs by default)
   - Analyzer: Collects all spec/feature keys with pattern detection
   - Generator: Gemini AI creates unification rules
   - Transformer: Applies standardization + unit extraction
   - Value Normalizer: Gemini AI normalizes field values (language, case, formatting)
   - Categorizer: Separates boolean features from quantitative specs
   - Validator: Ensures data quality
9. **Metadata Generation** - Extract unique values for filtering (runs by default)
10. **Database Insertion** - Persist to Supabase (opt-in)

### Key Architecture Principles

- **Parallel worker architecture** for concurrent processing in collection phases
- **Single browser instance** shared across entire pipeline for efficiency
- **Plugin-style retailer scrapers** with priority-based selection
- **Intelligent fallback chains** (Retailer → PDF → AI)
- **Graceful degradation** - each phase optional, pipeline continues on failures

### Key Components

- **Browser Management**: Single browser instance shared across workers with stealth mode
- **Worker System**: Distributes products evenly among workers for parallel processing
- **Data Models**: JSON output with structured specs, features, reviews, and images
- **Database Integration**: Supabase client for persistent storage

### Output Structure

**Standardized Output** (`complete_products.standardized.json`):
```json
{
  "products": [
    {
      "name": "Ninja Crispi FN101UKGY",
      "price": 129.99,
      "whichUrl": "https://www.which.co.uk/reviews/...",
      "specs": {
        "depth_cm": "25",
        "width_cm": "30",
        "height_cm": "30",
        "weight_kg": "4.242",
        "capacity_l": "3.8",
        "power_w": "1700",
        "cable_length_cm": "91",
        "measured_maximum_cooking_capacity_kg": "0.967",
        "colour": "Cyber Space Blue",
        "material": "Glass"
      },
      "features": {
        "air_fry_function": "Yes",
        "dishwasher_safe_parts": "Yes",
        "keep_warm_function": "Yes",
        "smart_controls": "No"
      },
      "reviews": {
        "rating": "4.5/5",
        "count": 150,
        "todScore": 89.5
      },
      "retailerLinks": [...]
    }
  ],
  "total": 79,
  "successful_enriched": 79,
  "failed_enriched": 0
}
```

**Key Features:**
- ✅ **Unit suffixes in keys** (`_cm`, `_kg`, `_l`, `_w`) - values are pure numbers
- ✅ **No duplicates** - `capacity_l` (not both `capacity` and `capacity_l`)
- ✅ **Type separation** - specs = quantitative/categorical, features = boolean only
- ✅ **Normalized values** - "Yes"/"No" standardized, English language, consistent casing

## Environment Variables

Required in `.env` file:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase service key
- `GEMINI_API_KEY` - Google Gemini API key (required for standardization pipeline)

## Performance Considerations

- Default 3 workers for specs extraction (configurable 1-10)
- Product discovery: ~2-3 seconds per page
- Specification extraction: ~2-4 seconds per product (parallelized)
- Review enrichment: ~1-2 seconds per product (parallelized)
- Shared browser context reduces memory usage

## Common Issues & Solutions

1. **Timeout errors**: Reduce worker count or check internet connection
2. **Missing specifications**: Some products may not have specs available
3. **Memory issues**: Limit workers to 3 or fewer
4. **Debug mode**: Set `headless=False` in browser launch for visual debugging