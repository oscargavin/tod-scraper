# Which.com Product Scraper

A high-performance, parallel web scraper for Which.com product reviews that extracts product listings along with detailed specifications and features.

## Features

- 🚀 **Fast Parallel Processing**: Multi-worker architecture for concurrent specification extraction
- 📊 **Complete Data Extraction**: Products, prices, specifications, and features
- 🎯 **Smart Pagination**: Automatically detects and processes all pages
- 🔄 **Single Browser Instance**: Efficient resource usage across entire pipeline
- 📈 **Progress Tracking**: Real-time updates showing worker progress
- 🛠️ **Flexible Options**: Skip specs extraction for quick product discovery

## Installation

1. **Clone the repository**:
```bash
cd /path/to/scraperv4
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers**:
```bash
playwright install chromium
```

## Usage

### Basic Usage

Scrape all products from a category with specifications:
```bash
python complete_scraper.py --url "https://www.which.co.uk/reviews/air-fryers" --pages all
```

### Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--url` | `-u` | washing-machines | Which.com category URL to scrape |
| `--pages` | `-p` | 1 | Number of pages (`1-99` or `all`) |
| `--workers` | `-w` | 3 | Parallel workers for spec extraction (1-10) |
| `--skip-specs` | `-s` | False | Only get products, skip specifications |
| `--output` | `-o` | complete_products.json | Output filename |

### Examples

**Scrape all air fryers with 5 workers**:
```bash
python complete_scraper.py \
  --url "https://www.which.co.uk/reviews/air-fryers" \
  --pages all \
  --workers 5 \
  --output air_fryers.json
```

**Get first 3 pages of TVs (products only)**:
```bash
python complete_scraper.py \
  --url "https://www.which.co.uk/reviews/tvs" \
  --pages 3 \
  --skip-specs \
  --output tvs_quick.json
```

**Scrape washing machines with default settings**:
```bash
python complete_scraper.py
```

## Supported Categories

The scraper works with any Which.com reviews URL:

- **Kitchen Appliances**: air-fryers, coffee-machines, food-processors, microwaves
- **Large Appliances**: washing-machines, dishwashers, fridge-freezers, tumble-dryers
- **Electronics**: tvs, laptops, tablets, headphones, soundbars
- **Home & Garden**: vacuum-cleaners, lawn-mowers, pressure-washers
- **And many more...**

## Output Format

The scraper generates a JSON file with the following structure:

```json
{
  "products": [
    {
      "name": "Product Name",
      "price": "£299",
      "whichUrl": "https://www.which.co.uk/reviews/...",
      "specs": {
        "type": "Freestanding",
        "height": "85cm",
        "width": "60cm",
        "capacity": "8kg",
        ...
      },
      "features": {
        "quick_wash": "Yes",
        "steam_function": "No",
        "smart_control": "Yes",
        ...
      }
    }
  ],
  "total": 79,
  "url": "https://www.which.co.uk/reviews/air-fryers",
  "successful_enriched": 79,
  "failed_enriched": 0,
  "total_specs_extracted": 877,
  "total_features_extracted": 588
}
```

## Performance

- **Product Discovery**: ~2-3 seconds per page
- **Specification Extraction**: ~2-4 seconds per product (parallelized)
- **Example**: 79 air fryers with specs in ~90 seconds with 5 workers

### Optimization Tips

1. **More Workers**: Increase `--workers` for faster spec extraction (diminishing returns after 8)
2. **Skip Specs**: Use `--skip-specs` for quick product discovery
3. **Specific Pages**: Limit pages instead of using `all` for testing

## How It Works

The scraper operates in two phases:

### Phase 1: Product Discovery
- Navigates to the Which.com category URL
- Detects total pages automatically
- Extracts product names, prices, and URLs
- Removes duplicates

### Phase 2: Specification Extraction
- Distributes products evenly among workers
- Each worker maintains a persistent browser context
- Navigates to individual product pages
- Extracts specifications and features tables
- Returns structured data

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
- Try again (Which.com may have temporary issues)

**Missing specifications**:
- Some products may not have specs available
- Check the `specs_error` field in output

**Memory issues**:
- Reduce workers to 3 or less
- Process fewer pages at once

### Debug Mode

View browser actions (non-headless mode):
```python
# In complete_scraper.py, change:
browser = await p.chromium.launch(
    headless=False,  # Change from True
    ...
)
```

## License

This tool is for educational purposes. Please respect Which.com's terms of service and robots.txt.

## Contributing

Improvements welcome! Key areas:
- Additional product metadata extraction
- Export formats (CSV, Excel)
- Retry logic for failed requests
- Price history tracking