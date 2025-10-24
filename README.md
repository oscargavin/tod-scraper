# Which.com Product Scraper

A high-performance, parallel web scraper for Which.com product reviews with intelligent retailer enrichment. Extracts product listings, detailed specifications, and enriches data with retailer-specific information from multiple sources.

## Features

- 🚀 **Fast Parallel Processing**: Multi-worker architecture for concurrent specification extraction
- 📊 **Complete Data Extraction**: Products, prices, specifications, features, and retailer links
- 🎯 **Smart Pagination**: Automatically detects and processes all pages
- 🛍️ **Retailer Enrichment**: Intelligently enriches products with specs from AO.com and other retailers
- 🏗️ **Extensible Architecture**: Plugin-style retailer scrapers with priority-based selection
- 🔄 **Single Browser Instance**: Efficient resource usage across entire pipeline
- 📈 **Progress Tracking**: Real-time updates showing worker progress
- 🖼️ **Image Download**: Optional product image extraction and Supabase storage
- 🛠️ **Flexible Options**: Skip specs/retailers extraction for quick product discovery

## Installation

1. **Clone the repository**:
```bash
cd /path/to/tod-scraper
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers**:
```bash
playwright install chromium
```

4. **Set up environment variables**:
```bash
# Create .env file
echo "SUPABASE_URL=your_supabase_url" >> .env
echo "SUPABASE_KEY=your_supabase_key" >> .env
echo "GEMINI_API_KEY=your_gemini_api_key" >> .env  # Required for standardization
```

## Usage

### Basic Usage

Scrape all products from a category with specifications, standardization, and metadata:
```bash
python src/scrapers/which/complete_scraper.py --url "https://www.which.co.uk/reviews/air-fryers" --pages all
```

### With Enrichment

Scrape and enrich with retailer specifications and customer reviews:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/washing-machines" \
  --pages all \
  --enrich-retailers \
  --enrich-reviews
```

### Full Pipeline (Recommended)

Run the complete 10-phase pipeline with database insertion:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/washing-machines" \
  --pages all \
  --enrich-retailers \
  --enrich-reviews \
  --save-to-db
```

### Command Line Options

#### Core Options
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--url` | `-u` | washing-machines | Which.com category URL to scrape |
| `--pages` | `-p` | 1 | Number of pages (`1-99` or `all`) |
| `--output` | `-o` | complete_products.json | Output filename |
| `--skip-specs` | `-s` | False | Skip Phase 2 (only get product listings) |

#### Enrichment Phases (opt-in)
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--enrich-retailers` | `-e` | False | Phase 4-5: Enrich with retailer specs and PDFs |
| `--enrich-reviews` | | False | Phase 6: Enrich with customer reviews |
| `--enrich-ai` | | False | Phase 7: Use AI (Gemini) to fill missing specs |

#### Processing Options (enabled by default)
| Option | Default | Description |
|--------|---------|-------------|
| `--no-standardization` | False | Skip Phase 8: data standardization |
| `--no-metadata` | False | Skip Phase 9: metadata generation |

#### Output Destinations
| Option | Default | Description |
|--------|---------|-------------|
| `--save-to-db` | False | Phase 10: Insert to Supabase database |
| `--download-images` | False | Download and upload images to Supabase |
| `--storage-bucket` | product-images | Supabase storage bucket name |

#### Performance Tuning
| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--workers` | `-w` | 3 | Workers for spec extraction |
| `--retailer-workers` | | 3 | Workers for retailer enrichment |
| `--review-workers` | | 3 | Workers for review enrichment |
| `--ai-workers` | | 2 | Workers for AI (Gemini) enrichment |

### Examples

**Full pipeline with all enrichment and database insertion**:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/washing-machines" \
  --pages all \
  --enrich-retailers \
  --enrich-reviews \
  --enrich-ai \
  --save-to-db \
  --output washing_machines_full.json
```

**Basic scraping with standardization** (default):
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/air-fryers" \
  --pages all \
  --workers 5 \
  --output air_fryers.json
```

**Fast mode: products only, no processing**:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/tvs" \
  --pages 3 \
  --skip-specs \
  --no-metadata \
  --output tvs_quick.json
```

**With image download and retailer enrichment**:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/coffee-machines" \
  --pages all \
  --enrich-retailers \
  --download-images \
  --save-to-db
```

**Raw data only (no standardization or metadata)**:
```bash
python src/scrapers/which/complete_scraper.py \
  --url "https://www.which.co.uk/reviews/laptops" \
  --pages 2 \
  --no-standardization \
  --no-metadata
```

## Supported Categories

The scraper works with any Which.com reviews URL:

- **Kitchen Appliances**: air-fryers, coffee-machines, food-processors, microwaves
- **Large Appliances**: washing-machines, dishwashers, fridge-freezers, tumble-dryers
- **Electronics**: tvs, laptops, tablets, headphones, soundbars
- **Home & Garden**: vacuum-cleaners, lawn-mowers, pressure-washers
- **And many more...**

## Output Format

The scraper generates two JSON files:

### Raw Output (`complete_products.json`)
Contains unprocessed data from all sources with mixed field names and formats.

### Standardized Output (`complete_products.standardized.json`)
AI-cleaned data with unified field names, extracted units, and proper categorization:

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
        "material": "Glass",
        "type": "Oven",
        "annual_running_cost_gbp": "21.13"
      },
      "features": {
        "air_fry_function": "Yes",
        "dishwasher_safe_parts": "Yes",
        "keep_warm_function": "Yes",
        "roast_function": "Yes",
        "smart_controls": "No"
      },
      "retailerLinks": [
        {
          "name": "AO",
          "price": "£130",
          "url": "https://..."
        }
      ],
      "reviews": {
        "rating": "4.5/5",
        "count": 150,
        "todScore": 89.5
      }
    }
  ],
  "total": 79,
  "successful_enriched": 79,
  "failed_enriched": 0
}
```

**Standardization Benefits:**
- ✅ **Unit suffixes in keys** (`_cm`, `_kg`, `_l`, `_w`) - values are pure numbers
- ✅ **No duplicates** - Single `capacity_l` field (no `capacity` AND `capacity_l`)
- ✅ **Type separation** - Specs = quantitative/categorical, Features = boolean only
- ✅ **Normalized values** - "Yes"/"No" standardized, English language, consistent casing
- ✅ **AI-powered cleaning** - Gemini handles edge cases and inconsistencies automatically

## Retailer Enrichment Architecture

The scraper features an extensible plugin architecture for enriching product data from multiple retailers.

### How It Works

1. **Automatic Retailer Detection**: Identifies available retailers from Which.com's "Where to buy" links
2. **Priority-Based Selection**: Tries retailers in configured priority order
3. **Intelligent Fallback**: Falls back to next retailer if primary fails or has insufficient data
4. **Quality Scoring**: Tracks data coverage and selects best source
5. **Spec Merging**: Intelligently merges retailer specs with Which.com specs

### Current Retailers

- ✅ **AO.com**: Full specification extraction (49-73 specs per product)
- ✅ **Appliance Centre**: Full specification extraction (50+ specs per product)
- 🔜 **Marks Electrical**: Coming soon
- 🔜 **Currys**: Coming soon
- 🔜 **John Lewis**: Coming soon

### Configuration

Retailer behavior is controlled via `config/retailer_config.json`:

```json
{
  "priority_order": ["AO", "Marks Electrical", "Currys"],
  "fallback_enabled": true,
  "max_fallback_attempts": 2,
  "min_specs_threshold": 20,
  "stop_at_first_success": true,
  "scrapers": {
    "AO": {
      "enabled": true,
      "expected_spec_count": 50
    }
  }
}
```

### Adding New Retailers

The architecture makes adding new retailers simple:

1. **Create scraper class** in `src/scrapers/retailers/your_retailer_scraper.py`:
```python
from src.scrapers.retailers.base import RetailerScraper

class YourRetailerScraper(RetailerScraper):
    @property
    def retailer_name(self) -> str:
        return "Your Retailer"

    @property
    def url_patterns(self) -> List[str]:
        return ['yourretailer.co.uk']

    async def scrape_product(self, page, url: str) -> Dict:
        # Your scraping logic here
        pass

    def clean_url(self, url: str) -> str:
        # URL cleaning logic
        pass
```

2. **Register in orchestrator** (`src/scrapers/retailers/orchestrator.py`):
```python
def _register_all_scrapers(self):
    self.registry.register(AOScraper())
    self.registry.register(ApplianceCentreScraper())
    self.registry.register(YourRetailerScraper())  # Add this line
```

3. **Enable in config** (`config/retailer_config.json`):
```json
{
  "scrapers": {
    "Your Retailer": {
      "enabled": true,
      "expected_spec_count": 40
    }
  }
}
```

That's it! The orchestrator handles everything else automatically.

## Performance

- **Product Discovery**: ~2-3 seconds per page
- **Specification Extraction**: ~2-4 seconds per product (parallelized)
- **Retailer Enrichment**: ~3-5 seconds per product with available retailer link
- **Example**: 20 washing machines with full enrichment in ~60 seconds with 3 workers

### Optimization Tips

1. **More Workers**: Increase `--workers`, `--retailer-workers`, etc. for faster processing
2. **Skip What You Don't Need**: Use `--skip-specs`, `--no-standardization`, or `--no-metadata`
3. **Specific Pages**: Limit pages instead of using `all` for testing
4. **Selective Enrichment**: Only enable the enrichment phases you need

## How It Works

The scraper operates in 10 sequential phases:

### Data Collection (Phases 1-7)

**Phase 1: Product Discovery**
- Navigates to Which.com category URL
- Detects total pages automatically
- Extracts product names, prices, and URLs
- Removes duplicates

**Phase 2: Base Specification Extraction**
- Distributes products evenly among workers
- Each worker maintains a persistent browser context
- Extracts specifications and features tables from Which.com
- Extracts retailer links from "Where to buy" sections
- Optionally downloads and uploads product images

**Phase 3: Retailer Link Discovery**
- For products without Which.com retailer links
- Searches DuckDuckGo to find retailer URLs
- Extracts up to 5 retailer links per product

**Phase 4: Retailer Spec Enrichment** (opt-in with `--enrich-retailers`)
- Orchestrator selects best retailer per product based on:
  - Availability in retailer links
  - Priority order from config
  - Historical success rate
- Parallel workers scrape retailer pages
- Extracts retailer-specific specifications
- Merges retailer specs with Which.com specs

**Phase 5: PDF Spec Enrichment** (automatic with `--enrich-retailers`)
- For products where retailer enrichment failed
- Extracts manufacturer PDF specifications
- Fills gaps in product data

**Phase 6: Review Enrichment** (opt-in with `--enrich-reviews`)
- Scrapes customer reviews from AO, Boots, or Amazon
- Extracts ratings, review counts, and sentiment
- Adds TOD score (Bayesian weighted rating)

**Phase 7: AI Spec Enrichment** (opt-in with `--enrich-ai`)
- Uses Gemini AI as final fallback
- Fills remaining missing specifications
- Only runs for products still missing data

### Data Processing & Persistence (Phases 8-10)

**Phase 8: Data Standardization** (runs by default)
- AI-powered 6-step pipeline using Gemini 2.5 Flash
- Analyzer: Collects all spec/feature keys with duplicate detection
- Generator: AI creates intelligent unification rules
- Transformer: Applies standardization + dynamic unit extraction
- Value Normalizer: AI normalizes field values (language, case, formatting)
- Categorizer: Separates boolean features from quantitative specs
- Validator: Ensures data quality
- Generates `.standardized.json` output with clean, deduplicated data

**Phase 9: Metadata Generation** (runs by default)
- Extracts all unique values for each field
- Creates searchable metadata for filtering
- Generates `.metadata.json` output

**Phase 10: Database Insertion** (opt-in with `--save-to-db`)
- Inserts products to Supabase database
- Inserts metadata for search/filtering
- Tracks insertion statistics

## Project Structure

```
tod-scraper/
├── src/                           # Source code
│   ├── scrapers/                  # Web scraping modules
│   │   ├── which/                 # Which.com scrapers
│   │   │   ├── complete_scraper.py   # Main Which.com scraper
│   │   │   └── batch_scraper.py      # Batch category processor
│   │   └── retailers/             # Retailer-specific scrapers
│   │       ├── base.py               # Abstract base class
│   │       ├── registry.py           # Scraper registration
│   │       ├── orchestrator.py       # Retailer selection & coordination
│   │       ├── ao_scraper.py         # AO.com scraper
│   │       └── appliance_centre_scraper.py  # Appliance Centre scraper
│   │
│   ├── standardization/           # AI-powered data standardization
│   │   ├── cli.py                    # Main pipeline CLI
│   │   ├── analyzer.py               # Key analysis & pattern detection
│   │   ├── generator.py              # Gemini AI unification map generation
│   │   ├── transformer.py            # Apply standardization & unit extraction
│   │   ├── value_normalizer.py       # Gemini AI value normalization
│   │   ├── categorizer.py            # Specs/features categorization
│   │   ├── validator.py              # Data quality validation
│   │   └── config.py                 # Unit patterns & configuration
│   │
│   ├── reviews/                   # Review enrichment system
│   │   └── ao/                    # AO.com review scrapers
│   │       ├── enricher.py           # Review enrichment pipeline
│   │       ├── search.py             # Product search
│   │       ├── sentiment_analyzer.py # Sentiment analysis
│   │       └── sentiment_scraper.py  # Review scraping
│   │
│   ├── database/                  # Database operations
│   │   ├── inserters/             # Data insertion scripts
│   │   │   ├── products.py           # Insert products
│   │   │   ├── metadata.py           # Insert metadata
│   │   │   └── main_db.py            # Main DB insertion
│   │   └── updaters/              # Data update scripts
│   │       └── retailer_links.py     # Update retailer links
│   │
│   └── utils/                     # Utility functions
│       ├── metadata_generator.py     # Generate product metadata
│       └── url_cleaner.py            # Clean tracking URLs
│
├── scripts/                       # Executable entry points
│   ├── run_full_pipeline.py       # Full scraping pipeline
│   ├── run_all_categories.py      # Batch category processor
│   └── scrape_ao_product.py       # AO product scraper
│
├── tests/                         # Test files
├── config/                        # Configuration files
│   └── retailer_config.json       # Retailer settings
├── output/                        # Generated JSON files
├── docs/                          # Documentation
└── migrations/                    # Database migrations
```

## Requirements

- Python 3.7+
- 4GB RAM minimum (8GB recommended for many workers)
- Stable internet connection
- Chrome/Chromium browser (installed via Playwright)

## Troubleshooting

### Common Issues

**Timeout errors**:
- Reduce number of workers
- Check internet connection
- Try again (retailers may have temporary issues)

**Missing specifications**:
- Some products may not have specs available
- Check the `specs_error` field in output
- Some retailer pages may be out of stock or unavailable

**No retailer enrichment**:
- Ensure `--enrich-retailers` flag is set
- Check that retailer is enabled in `config/retailer_config.json`
- Verify retailer links exist (Phase 3 should extract them automatically)

**Memory issues**:
- Reduce workers to 3 or less
- Process fewer pages at once
- Disable image download if enabled

### Debug Mode

View browser actions (non-headless mode):
```python
# In src/scrapers/which/complete_scraper.py or src/scrapers/retailers/ao_scraper.py, change:
browser = await p.chromium.launch(
    headless=False,  # Change from True
    ...
)
```

## License

This tool is for educational purposes. Please respect Which.com's and retailers' terms of service and robots.txt.

## Contributing

Improvements welcome! Key areas:
- Additional retailer scrapers (Marks Electrical, Currys, John Lewis)
- Export formats (CSV, Excel)
- Retry logic for failed requests
- Price history tracking
- Review sentiment analysis integration
- Advanced scraping strategies for dynamic content

## Standardization Pipeline

The scraper includes a powerful standalone standardization system that can be run independently:

```bash
# Run full standardization pipeline
python -m src.standardization.cli --input output/complete_products.json

# Run on specific category
python -m src.standardization.cli --input output/air-fryers_full.json

# Skip value normalization (faster, skips AI normalization)
python -m src.standardization.cli --no-value-normalization

# Adjust coverage threshold (default 10%)
python -m src.standardization.cli --min-coverage-filter 15
```

### Standardization Features

**6-Step AI-Powered Pipeline:**
1. **Analyzer** - Collects all field keys, detects duplicate patterns
2. **Generator** - Gemini AI creates intelligent unification rules
3. **Transformer** - Applies standardization + dynamic unit extraction
4. **Value Normalizer** - Gemini AI normalizes values (optional)
5. **Categorizer** - Separates boolean features from specs
6. **Validator** - Ensures data quality

**What it fixes:**
- Duplicate fields with different names (`capacity` vs `capacity_l` → `capacity_l`)
- Units in values (`"25cm"` → key: `depth_cm`, value: `"25"`)
- Language mixing (`"Ja"` → `"Yes"`, `"Nee"` → `"No"`)
- Case inconsistencies (`"black"` → `"Black"`)
- Field misclassification (boolean functions moved from specs to features)

## Recent Updates

### January 2025 - AI-Powered Standardization System
- Implemented 6-step standardization pipeline with Gemini 2.5 Flash
- Dynamic unit extraction with 26 unit patterns (cm, kg, l, w, etc.)
- AI-powered value normalization (language, case, formatting)
- Automatic specs/features categorization (boolean → features, numeric → specs)
- Intelligent duplicate detection and merging
- Unit-aware field deduplication prevents incorrect merges

### December 2024 - Project Reorganization
- Restructured codebase into logical `src/` hierarchy
- Separated scrapers, reviews, database operations, and utilities
- Centralized configuration in `config/` directory
- Moved executable scripts to `scripts/` directory
- Consolidated all tests in `tests/` directory
- Added Appliance Centre retailer scraper
