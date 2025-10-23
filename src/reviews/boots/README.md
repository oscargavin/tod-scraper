# Boots Review Scraper

## Overview

Boots uses **BazaarVoice** for product reviews with **Shadow DOM** encapsulation. This scraper successfully extracts both review summary data AND individual review text.

## Key Discovery: Shadow DOM

BazaarVoice uses Web Components with Shadow DOM to isolate their review widget. Reviews are NOT in the regular DOM - they're encapsulated and only accessible via `element.shadowRoot`.

## What Works ✓

### Review Summary Extraction (`scraper.py`)
- **Rating**: Average star rating (e.g., 4.2/5)
- **Count**: Total number of reviews (e.g., 31 reviews)
- **TOD Score**: Calculated confidence-weighted score (82.0%)

**Target Selector**: `[data-bv-show="rating_summary"]`

**Data extracted using**:
- `[itemprop="ratingValue"]` - Star rating
- `[itemprop="reviewCount"]` - Number of reviews

### Individual Review Text Extraction (`sentiment_scraper.py`) ✓
- **WORKS** via Shadow DOM access
- Extracts full review text for sentiment analysis
- Clicks "Show more" button to load all reviews (typically ~24+ reviews)
- Parses reviewer name, date, rating, text, recommendation

**How it works**:
1. Find element with `shadowRoot` property
2. Access `element.shadowRoot.textContent`
3. Click "Show more" button in shadow DOM to paginate
4. Parse review text from concatenated shadow content

### Product Search (`search.py`)
- Searches Boots.com for products
- Extracts review data from matched products
- Handles search result parsing

### Review Enrichment (`enricher.py`)
- Full pipeline with parallel workers
- TOD score calculation (Bayesian confidence-weighted)
- Follows same pattern as AO.com enricher

### Sentiment Analysis ✓
- Extract ~24+ reviews per product
- Pass to Gemini for sentiment analysis
- Get summary, pros, and cons

## Architecture

```
src/reviews/boots/
├── scraper.py              # Extract rating summary (✓ WORKS)
├── search.py               # Search Boots and delegate to scraper (✓ WORKS)
├── sentiment_scraper.py    # Attempt to scrape review text (✗ DOESN'T WORK)
├── enricher.py             # Full pipeline with TOD scores (✓ WORKS with summary only)
└── README.md              # This file
```

## Usage

### Extract Review Summary

```python
from src.reviews.boots.scraper import extract_review

url = "https://www.boots.com/tower-vortx-11l-dual-layer-air-fryer-black-with-chrome-trim-10369417"
review_data = await extract_review(url)

# Returns:
# {
#     "score": "4.2/5",
#     "stars": 4.2,
#     "count": 31
# }
```

### Full Enrichment Pipeline

```python
from src.reviews.boots.enricher import enrich_boots_reviews

products = [
    {"name": "Tower Air Fryer", "bootsUrl": "https://..."},
]

enriched = await enrich_boots_reviews(products, workers=3)

# Adds to each product:
# {
#     "bootsReviews": {
#         "rating": "4.2/5",
#         "count": 31,
#         "todScore": 82.0
#     }
# }
```

## Comparison with AO.com

| Feature | AO.com | Boots |
|---------|--------|-------|
| Rating Summary | ✓ | ✓ |
| Review Count | ✓ | ✓ |
| TOD Score | ✓ | ✓ |
| Review Text | ✓ | ✗ |
| Sentiment Analysis | ✓ | ✗ |

## Future Improvements

Possible approaches to extract review text:
1. Use BazaarVoice API with valid passkey (requires Boots partnership)
2. Use real browser automation (Selenium with real Chrome profile)
3. Reverse-engineer BazaarVoice's API authentication
4. Accept limitation and use summary data only (current approach)

## Testing

```bash
# Test summary extraction
python src/reviews/boots/scraper.py "https://www.boots.com/tower-vortx-11l-dual-layer-air-fryer-black-with-chrome-trim-10369417"

# Output:
# Score: 4.2/5
# Stars: 4.2
# Count: 31
```

## Implementation Details

### BazaarVoice Integration

Boots uses BazaarVoice's standard deployment:
- Script: `https://apps.bazaarvoice.com/deployments/Boots/main_site/production/en_GB/bv.js`
- Client Name: `Boots`
- Product ID: Boots product code (e.g., `10369417`)

### Data Sources

1. **Rating Summary** (schema.org microdata)
   - Reliable and consistent
   - Loads server-side in initial HTML
   - Not affected by bot detection

2. **Review Text** (BazaarVoice JavaScript)
   - Loads client-side after page load
   - Detects automation and blocks content
   - Would require API access or real browser

