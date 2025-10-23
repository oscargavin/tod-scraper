"""
PDF-based specification extraction for product enrichment.

This module provides intelligent PDF extraction with:
- Category-agnostic smart scoring
- Multi-PDF aggregation
- Ad filtering
- Dynamic brand/model detection
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from playwright.async_api import Page
import pypdf
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Generic patterns for identifying good/bad PDF sources (category-agnostic)
MANUAL_KEYWORDS = ['manual', 'user-guide', 'instruction', 'spec', '-im.pdf', '-ib.pdf', 'userguide']
TRUSTED_RETAILER_DOMAINS = ['lakeland.co.uk', 'documents.philips.com', 'media-amazon.com/images/I/']
BAD_PATTERNS = ['recall', 'nestle', 'eurofins', 'f6hoy', 'howdens', '/dp/']
AD_PATTERNS = ['doubleclick', 'googleadservices', 'googlesyndication', 'adroll',
               'advertising.com', 'taboola', 'outbrain', '/y.js', '/l/?']

# Intelligent truncation patterns and weights
SPEC_PATTERNS = {
    'unit_values': r'\b\d+(?:\.\d+)?(?:\s*)?(?:'
                   r'kg|g|mg|lb|lbs|pound|pounds|oz|ounce|ounces|'
                   r'cm|mm|m|km|in|inch|inches|ft|feet|foot|"|\'|′|'
                   r'L|l|ml|cl|dl|gallon|gal|qt|quart|pint|pt|cup|fl\.?\s*oz|'
                   r'W|kW|MW|watt|watts|kilowatt|kilowatts|hp|horsepower|'
                   r'V|kV|volt|volts|A|mA|kA|amp|amps|ampere|amperes|'
                   r'Hz|kHz|MHz|GHz|hertz|'
                   r'°C|°F|C|F|celsius|fahrenheit|kelvin|K|'
                   r'bar|psi|Pa|kPa|MPa|pascal|'
                   r'rpm|rph|mph|km/h|kmh|kph|m/s|ms|'
                   r'kWh|Wh|J|kJ|MJ|joule|joules|'
                   r'dB|dBA|dBC|decibel|decibels|'
                   r'min|mins|minute|minutes|sec|secs|second|seconds|hr|hrs|hour|hours|h|s|ms|'
                   r'%|percent|'
                   r'cycles|year|years|yr|yrs'
                   r')\b',

    'dimensions': r'\b\d+(?:\.\d+)?[\s]*[x×*][\s]*\d+(?:\.\d+)?(?:[\s]*[x×*][\s]*\d+(?:\.\d+)?)?[\s]*(?:cm|mm|m|in|inch|inches|"|ft|′)\b',

    'key_value_pairs': r'(?:^|\n)\s*[A-Za-z][A-Za-z\s]{2,30}[\s:−-]\s*\d+',

    'technical_keywords': r'\b(?:capacity|power|voltage|frequency|dimensions|width|height|depth|weight|'
                         r'energy|temperature|speed|pressure|noise|efficiency|consumption|'
                         r'rating|load|output|input|current|wattage|amperage|diameter|length|'
                         r'volume|mass|flow|range|cycle|spin|program|setting|level|class)\b',

    'table_indicators': r'(?:^|\n)[^\n]*:[^\n]*:[^\n]*',

    'spec_headers': r'\b(?:specification|technical\s+data|product\s+details|features|'
                    r'performance|characteristics|properties)\b',
}

PATTERN_WEIGHTS = {
    'unit_values': 5,
    'dimensions': 8,
    'key_value_pairs': 4,
    'technical_keywords': 2,
    'table_indicators': 10,
    'spec_headers': 15,
}

FLUFF_PATTERNS = r'\b(?:amazing|revolutionary|best|perfect|ultimate|innovative|cutting-edge|' \
                 r'state-of-the-art|premium|luxury|exclusive|unbeatable|superior|exceptional|' \
                 r'outstanding|remarkable|extraordinary|incredible|fantastic|wonderful)\b'

# TOC patterns to filter out
TOC_PATTERNS = [
    # Main pattern: text followed by dots/spaces and page number
    # Allows letters, numbers, spaces, parens, hyphens, slashes, colons, dashes
    r'^[A-Za-z][A-Za-z0-9\s()\-–—/:.]{2,80}[\s.]{8,}\s*\d+\s*$',
    # Just dots/spaces and a number ". . . . . 2"
    r'^[\s.]{10,}\s*\d+\s*$',
    # Alternative format: text, space, dot, then more dots/spaces and number
    r'^[A-Za-z][A-Za-z0-9\s()\-–—/:.]{3,80}\s+\.[\s.]+\d+\s*$',
    # Chapter/Appendix headers (partial TOC entries without page numbers)
    r'^(?:Chapter|Appendix)\s+[A-Z0-9]+\.?\s+.{3,60}$',
    # Orphaned TOC text lines (first half of multi-line TOC entries)
    # These end with incomplete phrases like "of the", "for selected", "using the", etc.
    r'^[A-Z][A-Za-z0-9\s()\-–—/:.]{10,70}\s+(?:of|using|with|for|in|on|the|to|from)\s+the\s*$',
    r'^[A-Z][A-Za-z0-9\s()\-–—/:.]{10,70}\s+\(for\s+selected\s*$',
    # Short capitalized lines that look like TOC entries (< 50 chars, starts with capital)
    r'^[A-Z][a-z]+(?:\s+[A-Z]?[a-z]+){1,5}\s*$',
]

# Gemini system instruction
SPEC_EXTRACTION_INSTRUCTION = """
You are a technical specification extraction assistant.

Your task is to extract specifications from PDF text for a SPECIFIC product.

CRITICAL RULES:
1. Extract ONLY specifications for the SPECIFIC product mentioned in the prompt
2. IGNORE specifications for other models, sizes, or variants mentioned in the PDF
3. If the PDF contains multiple models (e.g., 14-inch vs 16-inch, different generations), extract ONLY the specs matching the product name
4. Use consistent key names (lowercase with underscores)
5. Preserve units exactly as shown (W, L, cm, kg, etc.)
6. Return ONLY valid JSON with a "specs" object
7. If no clear specs found for the specific product, return {"specs": {}}

Common specification keys to look for:
- capacity (L or kg)
- power (W)
- dimensions, width, height, depth (cm or mm)
- weight (kg)
- voltage (V)
- frequency (Hz)
- temperature_range (°C)
- programs, functions, features
- color, material, finish
- cable_length (m)

Example output format:
{
  "specs": {
    "capacity": "11L",
    "power": "1500W",
    "width": "30cm",
    "height": "35cm",
    "depth": "40cm",
    "weight": "5.2kg",
    "temperature_range": "80-200°C",
    "programs": "7"
  }
}

Extract all available specs for the specific product mentioned in the prompt. Ignore other variants.
"""


def calculate_enrichment_target(product: Dict) -> float:
    """
    Calculate target spec count for PDF enrichment.

    Args:
        product: Product dict with '_whichSpecsCount' baseline

    Returns:
        Target spec count (50% of Which.com baseline, minimum 5)
    """
    which_baseline = product.get('_whichSpecsCount', 0)
    target = which_baseline * 0.5
    return max(target, 5)


def get_enrichment_gap(product: Dict) -> float:
    """
    Calculate remaining enrichment gap after PDF extraction.

    Args:
        product: Product dict with PDF enrichment data

    Returns:
        Remaining gap to reach target (0 if target met)
    """
    target = calculate_enrichment_target(product)
    pdf_added = product.get('pdfEnrichment', {}).get('specsCount', 0)
    gap = target - pdf_added
    return max(gap, 0)


def extract_brand_and_model(product_name: str) -> Tuple[str, str]:
    """
    Dynamically extract brand and model number from product name.
    Works across all product categories.
    """
    words = product_name.split()
    brand = words[0].lower() if words else ""

    # Model number patterns
    model_patterns = [
        r'[A-Z]{2,}\d+[A-Z\d/-]*',
        r'[A-Z]\d{5}[A-Z\d/-]*',
        r'[A-Z]{2}\d{3}/\d{2}',
        r'\d{3,}[A-Z]+\d*'
    ]

    model = ""
    for pattern in model_patterns:
        matches = re.findall(pattern, product_name.upper())
        if matches:
            model = matches[0]
            break

    return brand, model


def score_pdf_url(url: str, brand: str, model: str) -> int:
    """
    Score a PDF URL based on relevance indicators.
    Uses dynamic, category-agnostic scoring rules.
    """
    score = 0
    url_lower = url.lower()

    # Brand in domain (very strong signal)
    url_domain = url_lower.split('/')[2] if len(url_lower.split('/')) > 2 else url_lower
    if brand and brand in url_domain:
        score += 50
    elif brand and brand in url_lower:
        score += 20

    # Model number in URL
    if model and model.lower() in url_lower:
        score += 30

    # Manual/spec keywords
    for keyword in MANUAL_KEYWORDS:
        if keyword in url_lower:
            score += 10
            break

    # Trusted retailers
    for trusted in TRUSTED_RETAILER_DOMAINS:
        if trusted in url_lower:
            score += 15
            break

    # Penalize bad patterns
    for bad_pattern in BAD_PATTERNS:
        if bad_pattern in url_lower:
            score -= 50
            break

    # Penalize ad networks (heavy penalty)
    for ad_pattern in AD_PATTERNS:
        if ad_pattern in url_lower:
            score -= 100
            break

    return score


async def search_pdfs_for_product(page: Page, product_name: str, max_pdfs: int = 5) -> List[Dict]:
    """
    Search DuckDuckGo for PDF manuals/specs for a product.
    Uses smart scoring to filter and rank results.
    """
    print(f"  [PDF Search] '{product_name[:50]}'...")

    brand, model = extract_brand_and_model(product_name)

    query = f"{product_name} specifications filetype:pdf"
    search_url = f"https://duckduckgo.com/?q={requests.utils.quote(query)}"

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        # Extract PDF links with ad filtering
        all_pdf_urls = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href*=".pdf"]'));

                const pdfUrls = links
                    .filter(link => {
                        // Filter out ads by checking parent containers
                        let element = link;
                        while (element && element !== document.body) {
                            const className = (element.className || '').toLowerCase();
                            const id = (element.id || '').toLowerCase();

                            // Word boundaries to avoid false positives
                            const adPatterns = /\\b(ad|ads|advert|advertising|sponsor|sponsored)\\b/;

                            if (adPatterns.test(className) || adPatterns.test(id)) {
                                return false;
                            }

                            element = element.parentElement;
                        }
                        return true;
                    })
                    .map(a => a.href)
                    .filter(href => {
                        const lowerHref = href.toLowerCase();

                        if (!lowerHref.endsWith('.pdf')) return false;
                        if (href.includes('duckduckgo.com')) return false;
                        if (href.includes('/y.js') || href.includes('/l/?')) return false;

                        const adNetworks = ['doubleclick', 'googleadservices', 'googlesyndication',
                                          'adroll', 'advertising.com', 'taboola', 'outbrain'];
                        if (adNetworks.some(ad => lowerHref.includes(ad))) return false;

                        return true;
                    });

                return [...new Set(pdfUrls)];
            }
        """)

        # Score all PDFs
        scored_pdfs = []
        for url in all_pdf_urls:
            score = score_pdf_url(url, brand, model)
            scored_pdfs.append({'url': url, 'score': score})

        # Filter out negative scores
        scored_pdfs = [p for p in scored_pdfs if p['score'] >= 0]
        scored_pdfs.sort(key=lambda x: x['score'], reverse=True)

        top_pdfs = scored_pdfs[:max_pdfs]
        print(f"  [PDF Search] Found {len(top_pdfs)} high-quality PDFs (from {len(all_pdf_urls)} total)")

        return top_pdfs

    except Exception as e:
        print(f"  [PDF Search] Error: {e}")
        return []


def download_pdf(url: str, save_path: Path) -> bool:
    """Download a PDF from URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()

        # Verify it's a PDF
        content_type = response.headers.get('Content-Type', '')
        if 'pdf' not in content_type.lower() and not url.lower().endswith('.pdf'):
            return False

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True

    except Exception as e:
        print(f"  [PDF Download] Error: {e}")
        return False


def extract_text_from_pdf(pdf_path: Path) -> Optional[str]:
    """Extract text from a PDF file."""
    try:
        reader = pypdf.PdfReader(str(pdf_path))

        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)

        if len(full_text.strip()) < 100:
            return None

        return full_text

    except Exception as e:
        print(f"  [PDF Extract] Error: {e}")
        return None


def create_windows(pdf_text: str, window_size: int = 1000, overlap: int = 500) -> List[Dict]:
    """
    Create overlapping windows from PDF text.

    Args:
        pdf_text: Full PDF text
        window_size: Size of each window in chars
        overlap: Overlap between windows in chars

    Returns:
        List of window dicts with text, start, end positions
    """
    windows = []
    step = window_size - overlap

    for i in range(0, len(pdf_text), step):
        window_text = pdf_text[i:i + window_size]
        if len(window_text) >= 400:  # Min viable window
            windows.append({
                'text': window_text,
                'start': i,
                'end': i + len(window_text),
                'score': 0.0
            })

    return windows


def calculate_window_density(window_text: str) -> float:
    """
    Calculate spec density score for a text window.

    Args:
        window_text: Text to analyze

    Returns:
        Normalized density score (higher = more spec-like)
    """
    score = 0.0
    pattern_types_found = set()

    # Count matches for each pattern type
    for pattern_name, pattern in SPEC_PATTERNS.items():
        matches = re.findall(pattern, window_text, re.IGNORECASE)
        if matches:
            count = len(matches)
            weight = PATTERN_WEIGHTS.get(pattern_name, 1)
            score += count * weight
            pattern_types_found.add(pattern_name)

    # Bonus for multiple pattern types co-occurring
    if len(pattern_types_found) >= 3:
        score *= 1.5

    # Bonus for spec headers
    if re.search(SPEC_PATTERNS['spec_headers'], window_text, re.IGNORECASE):
        score *= 2.0

    # Penalty for marketing fluff
    fluff_matches = re.findall(FLUFF_PATTERNS, window_text, re.IGNORECASE)
    if len(fluff_matches) > 5:
        score *= 0.5

    # Normalize by window length (score per 1000 chars)
    if len(window_text) > 0:
        normalized_score = (score / len(window_text)) * 1000
    else:
        normalized_score = 0.0

    return normalized_score


def filter_toc_lines(text: str) -> str:
    """
    Remove table of contents lines from text.

    TOC lines typically look like:
    - "Camera . . . . . . . . . . 3"
    - "Power button . . . . . . . 8"

    Args:
        text: Text potentially containing TOC lines

    Returns:
        Text with TOC lines removed
    """
    lines = text.split('\n')
    filtered_lines = []

    for line in lines:
        is_toc = False
        for toc_pattern in TOC_PATTERNS:
            if re.match(toc_pattern, line.strip()):
                is_toc = True
                break

        if not is_toc:
            filtered_lines.append(line)

    return '\n'.join(filtered_lines)


def merge_windows(scored_windows: List[Dict], max_chars: int = 50000) -> str:
    """
    Merge overlapping high-scoring windows into final text.

    Args:
        scored_windows: List of windows with scores
        max_chars: Maximum total characters to return

    Returns:
        Merged text with separators
    """
    # Sort by position
    sorted_windows = sorted(scored_windows, key=lambda w: w['start'])

    merged = []
    total_chars = 0

    for window in sorted_windows:
        window_text = window['text']

        # Check if adding this window would exceed limit
        if total_chars + len(window_text) > max_chars:
            break

        # Check for overlap with previous window
        if merged and window['start'] < merged[-1]['end']:
            # Calculate overlap
            overlap_start = window['start']
            overlap_end = merged[-1]['end']

            # Only add the non-overlapping part
            new_part_start = overlap_end - overlap_start
            if new_part_start < len(window_text):
                new_text = window_text[new_part_start:]
                merged[-1]['text'] += new_text
                merged[-1]['end'] = window['end']
        else:
            # No overlap, add as new window
            merged.append(window.copy())

        total_chars = sum(len(w['text']) for w in merged)

    # Join with separators
    return "\n\n... [content continues] ...\n\n".join(w['text'] for w in merged)


def truncate_intelligently(pdf_text: str, max_chars: int = 50000) -> str:
    """
    Intelligently truncate PDF text by extracting high-density spec sections.

    Args:
        pdf_text: Full PDF text
        max_chars: Maximum characters to return

    Returns:
        Truncated text focused on spec-dense sections
    """
    # Edge case: Very short PDFs
    if len(pdf_text) <= 5000:
        return pdf_text

    # Edge case: Already under limit
    if len(pdf_text) <= max_chars:
        return pdf_text

    print(f"  [Intelligent Truncation] Processing {len(pdf_text):,} chars...")

    # Create windows
    windows = create_windows(pdf_text, window_size=1000, overlap=500)
    print(f"  [Intelligent Truncation] Created {len(windows)} windows")

    # Score each window
    for window in windows:
        window['score'] = calculate_window_density(window['text'])

    # Sort by score (highest first)
    windows.sort(key=lambda w: w['score'], reverse=True)

    # Check if we have any high-scoring windows
    if windows and windows[0]['score'] > 0:
        # Take enough windows to fill up to max_chars
        # Strategy: Take top N windows greedily until we hit the limit
        high_scoring_windows = []
        estimated_chars = 0

        for window in windows:
            # Skip windows with score of 0 (completely non-spec text)
            if window['score'] <= 0:
                break

            # Add window - be greedy to fill the budget
            window_chars = len(window['text'])
            if estimated_chars + window_chars <= max_chars * 1.5:  # Allow 50% overage before merging
                high_scoring_windows.append(window)
                estimated_chars += window_chars

            # Stop if we've gathered enough raw material for merging
            if estimated_chars >= max_chars * 1.2:
                break

        print(f"  [Intelligent Truncation] Selected {len(high_scoring_windows)} high-density windows")
        lowest_score = high_scoring_windows[-1]['score'] if high_scoring_windows else 0
        print(f"  [Intelligent Truncation] Top score: {windows[0]['score']:.2f}, lowest: {lowest_score:.2f}")

        # Merge windows
        result = merge_windows(high_scoring_windows, max_chars)
        print(f"  [Intelligent Truncation] Merged text: {len(result):,} chars")

        # Filter out TOC lines
        result = filter_toc_lines(result)
        print(f"  [Intelligent Truncation] After TOC filtering: {len(result):,} chars")

        return result
    else:
        # Fallback: No good windows found, use first 50k
        print(f"  [Intelligent Truncation] No high-density windows found, using first {max_chars:,} chars")
        return pdf_text[:max_chars]


def extract_specs_with_gemini(pdf_text: str, product_name: str) -> Optional[Dict]:
    """Use Gemini Flash to extract specifications from PDF text."""
    try:
        if not GEMINI_API_KEY:
            print("  [Gemini] Error: GEMINI_API_KEY not set")
            return None

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Intelligently truncate if too long
        max_chars = 50000
        if len(pdf_text) > max_chars:
            pdf_text = truncate_intelligently(pdf_text, max_chars)

        prompt = f"""
SPECIFIC PRODUCT: {product_name}

PDF Text:
{pdf_text}

TASK: Extract ONLY the technical specifications for "{product_name}".

IMPORTANT:
- This PDF may contain specs for multiple models/sizes/variants
- Extract ONLY specs that match "{product_name}"
- Ignore specs for other models, sizes, or variants
- Return as JSON

Return the specifications as JSON.
"""

        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SPEC_EXTRACTION_INSTRUCTION,
                temperature=0.1,
                max_output_tokens=2000
            )
        )

        if not response.candidates:
            print("  [Gemini] Error: No candidates in response")
            return None

        candidate = response.candidates[0]
        text_response = " ".join([part.text for part in candidate.content.parts if hasattr(part, 'text')])

        # Parse JSON
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text_response, re.DOTALL)
        if not json_match:
            print(f"  [Gemini] Error: No JSON found in response")
            return None

        result = json.loads(json_match.group(0))
        specs = result.get('specs', {})

        return specs

    except Exception as e:
        print(f"  [Gemini] Error: {e}")
        return None


async def process_product_pdfs(page: Page, product: Dict, pdf_dir: Path, product_idx: int) -> Dict:
    """
    Process a single product: search PDFs, download, extract specs.
    Aggregates specs from multiple PDFs until target threshold is reached.
    """
    product_name = product['name']
    target_specs = int(calculate_enrichment_target(product))
    max_pdfs = 5

    print(f"\n  Product: {product_name[:60]}")
    print(f"  Target: {target_specs} specs (50% of {product.get('_whichSpecsCount', 0)} Which specs)")

    # Search for PDFs
    scored_pdfs = await search_pdfs_for_product(page, product_name, max_pdfs=max_pdfs)

    if not scored_pdfs:
        product['pdfEnrichment'] = {
            'status': 'failed',
            'reason': 'No PDFs found',
            'pdfsAttempted': 0,
            'specs': {},
            'sourceUrls': []
        }
        return product

    # Accumulate specs from multiple PDFs
    accumulated_specs = {}
    source_urls = []
    pdfs_processed = 0

    for pdf_idx, scored_pdf in enumerate(scored_pdfs, 1):
        pdf_url = scored_pdf['url']
        pdf_score = scored_pdf['score']

        print(f"    PDF {pdf_idx}/{len(scored_pdfs)} (score: {pdf_score}): {len(accumulated_specs)}/{target_specs} specs...")

        # Download PDF
        pdf_filename = f"product_{product_idx:04d}_pdf_{pdf_idx}.pdf"
        pdf_path = pdf_dir / pdf_filename

        if not download_pdf(pdf_url, pdf_path):
            continue

        # Extract text
        pdf_text = extract_text_from_pdf(pdf_path)
        if not pdf_text:
            continue

        # Extract specs with Gemini
        specs = extract_specs_with_gemini(pdf_text, product_name)

        if specs and len(specs) > 0:
            pdfs_processed += 1
            new_keys = set(specs.keys()) - set(accumulated_specs.keys())
            accumulated_specs.update(specs)
            source_urls.append({'url': pdf_url, 'score': pdf_score, 'specs_added': len(new_keys)})

            print(f"      +{len(new_keys)} new specs (total: {len(accumulated_specs)})")

            # Check if we've reached target
            if len(accumulated_specs) >= target_specs:
                print(f"      ✓ Reached target!")
                break

    # Final result
    if accumulated_specs:
        product['pdfEnrichment'] = {
            'status': 'success',
            'sourceUrls': source_urls,
            'pdfsProcessed': pdfs_processed,
            'pdfsAttempted': len(scored_pdfs),
            'specsCount': len(accumulated_specs),
            'specs': accumulated_specs,
            'targetReached': len(accumulated_specs) >= target_specs
        }

        # Merge specs: PDF fills gaps, Which.com wins conflicts
        which_specs = product.get('specs', {})
        merged_specs = {**accumulated_specs, **which_specs}
        product['specs'] = merged_specs
    else:
        product['pdfEnrichment'] = {
            'status': 'failed',
            'reason': 'No specs extracted from any PDF',
            'pdfsAttempted': len(scored_pdfs),
            'specs': {},
            'sourceUrls': []
        }

    return product


async def enrich_pdf_phase(browser, products: List[Dict], workers: int = 3) -> List[Dict]:
    """
    Phase 3.5: PDF extraction with multi-PDF aggregation.
    Only processes products where retailer enrichment failed.

    Args:
        browser: Playwright browser instance
        products: List of product dicts
        workers: Number of parallel workers (currently sequential, but prepared for parallel)

    Returns:
        Products enriched with PDF specs
    """
    # Filter: Only products that need PDF enrichment
    products_to_enrich = [
        p for p in products
        if not p.get('retailerEnrichmentSource')
    ]

    if not products_to_enrich:
        print("No products need PDF enrichment - all have retailer specs")
        return products

    print(f"Running PDF enrichment for {len(products_to_enrich)} products...")

    # Create PDF storage directory
    pdf_dir = Path("output/pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # Create browser context
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        locale="en-GB",
        timezone_id="Europe/London"
    )

    page = await context.new_page()
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # Process each product (sequential for now - can be parallelized later)
    product_map = {p['name']: p for p in products}

    for idx, product in enumerate(products_to_enrich):
        await process_product_pdfs(page, product, pdf_dir, idx)
        # Update in main products list
        product_map[product['name']] = product

    await context.close()

    # Reconstruct products list with updated data
    updated_products = [product_map[p['name']] for p in products]

    return updated_products


# ============= Testing Functions =============

def test_intelligent_truncation(pdf_url: str = "https://gzhls.at/blob/ldb/e/5/b/c/4a47cd2b546bdbdba5878ee45de475e20c7c.pdf",
                                 product_name: str = "Test Product"):
    """
    Test the intelligent truncation system on a real PDF.

    Args:
        pdf_url: URL of PDF to test (default: 50-page test PDF)
        product_name: Product name for context

    Example:
        >>> test_intelligent_truncation()
    """
    import tempfile

    print("="*80)
    print("TESTING INTELLIGENT PDF TRUNCATION")
    print("="*80)
    print(f"PDF URL: {pdf_url}")
    print(f"Product: {product_name}")
    print()

    # Download PDF
    print("[1/5] Downloading PDF...")
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
        pdf_path = Path(tmp_file.name)

    if not download_pdf(pdf_url, pdf_path):
        print("✗ Failed to download PDF")
        return

    print(f"✓ Downloaded to {pdf_path}")

    # Extract text
    print("\n[2/5] Extracting text from PDF...")
    pdf_text = extract_text_from_pdf(pdf_path)

    if not pdf_text:
        print("✗ Failed to extract text")
        pdf_path.unlink()
        return

    print(f"✓ Extracted {len(pdf_text):,} characters from PDF")
    print(f"  Pages estimated: ~{len(pdf_text) // 2000}")

    # Run intelligent truncation
    print("\n[3/5] Running intelligent truncation...")
    truncated_text = truncate_intelligently(pdf_text, max_chars=50000)

    print(f"✓ Truncated to {len(truncated_text):,} characters")
    print(f"  Reduction: {len(pdf_text) - len(truncated_text):,} chars ({(1 - len(truncated_text)/len(pdf_text))*100:.1f}%)")

    # Compare with naive truncation
    print("\n[4/5] Comparing with naive truncation...")
    naive_truncated = pdf_text[:50000]

    print(f"Naive truncation: First {len(naive_truncated):,} chars")
    print(f"Intelligent truncation: {len(truncated_text):,} chars from high-density sections")

    # Count spec patterns in both
    print("\n[5/5] Analyzing spec density...")

    def count_patterns(text):
        counts = {}
        for pattern_name, pattern in SPEC_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            counts[pattern_name] = len(matches)
        return counts

    naive_counts = count_patterns(naive_truncated)
    intelligent_counts = count_patterns(truncated_text)

    print("\nPattern counts comparison:")
    print(f"{'Pattern':<20} {'Naive':<10} {'Intelligent':<12} {'Improvement'}")
    print("-" * 60)

    for pattern_name in SPEC_PATTERNS.keys():
        naive_count = naive_counts.get(pattern_name, 0)
        intelligent_count = intelligent_counts.get(pattern_name, 0)

        if naive_count > 0:
            improvement = ((intelligent_count - naive_count) / naive_count) * 100
            improvement_str = f"+{improvement:.1f}%" if improvement > 0 else f"{improvement:.1f}%"
        else:
            improvement_str = "N/A"

        print(f"{pattern_name:<20} {naive_count:<10} {intelligent_count:<12} {improvement_str}")

    total_naive = sum(naive_counts.values())
    total_intelligent = sum(intelligent_counts.values())
    overall_improvement = ((total_intelligent - total_naive) / total_naive * 100) if total_naive > 0 else 0

    print("-" * 60)
    print(f"{'TOTAL':<20} {total_naive:<10} {total_intelligent:<12} {overall_improvement:+.1f}%")

    # Show sample of truncated text
    print("\n" + "="*80)
    print("SAMPLE OF INTELLIGENTLY TRUNCATED TEXT (first 500 chars)")
    print("="*80)
    print(truncated_text[:500])
    print("...")

    # Cleanup
    pdf_path.unlink()

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

    return {
        'original_length': len(pdf_text),
        'truncated_length': len(truncated_text),
        'naive_pattern_count': total_naive,
        'intelligent_pattern_count': total_intelligent,
        'improvement_percent': overall_improvement
    }
