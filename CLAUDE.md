# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a comprehensive web scraping system for Which.com product reviews with AO.com review enrichment capabilities. The system uses Playwright for browser automation and supports parallel processing with multiple workers.

## Key Commands

### Running Scrapers
```bash
# Basic scraping with default settings (washing machines, 1 page)
python complete_scraper.py

# Scrape all pages from a category with specifications
python complete_scraper.py --url "https://www.which.co.uk/reviews/air-fryers" --pages all --workers 5

# Quick product discovery without specifications
python complete_scraper.py --pages 3 --skip-specs

# Scrape with specifications but skip retailer prices
python complete_scraper.py --pages 2 --skip-retailers

# Full pipeline with AO.com review enrichment
python full_pipeline.py --pages all --workers 5 --review-workers 3

# Test image extraction functionality
python test_complete_scraper_images.py
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

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Architecture

### Core Scraping Pipeline

1. **Product Discovery Phase** (`complete_scraper.py: scrape_products_phase`)
   - Scrapes product listings from Which.com category pages
   - Detects total pages automatically
   - Extracts: name, price, Which.com URL, retailer links

2. **Specification Extraction Phase** (`complete_scraper.py: enrich_specs_phase`)
   - Parallel worker architecture for concurrent processing
   - Navigates to individual product pages
   - Extracts detailed specifications and features tables
   - Extracts retailer prices from "Where to buy" section (enabled by default)
   - Optional image extraction capability
   - Uses shared browser context for efficiency

3. **Review Enrichment Phase** (`review_scrapers/ao_review_enricher.py`)
   - Searches AO.com for matching products
   - Extracts review ratings and counts
   - Calculates TOD score (Bayesian weighted rating)
   - Parallel processing with configurable workers

### Key Components

- **Browser Management**: Single browser instance shared across workers with stealth mode
- **Worker System**: Distributes products evenly among workers for parallel processing
- **Data Models**: JSON output with structured specs, features, reviews, and images
- **Database Integration**: Supabase client for persistent storage

### Output Structure
```json
{
  "products": [
    {
      "name": "Product Name",
      "price": "£299",
      "whichUrl": "https://www.which.co.uk/reviews/...",
      "specs": {},
      "features": {},
      "reviews": {
        "rating": "4.5/5",
        "count": 150,
        "todScore": 89.5
      },
      "images": {},
      "retailerLinks": [
        {
          "name": "Currys",
          "price": "£429",
          "url": "https://..."
        }
      ]
    }
  ],
  "total": 79,
  "successful_enriched": 79,
  "failed_enriched": 0
}
```

## Environment Variables

Required in `.env` file:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase service key

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