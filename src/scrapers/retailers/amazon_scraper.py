"""
Amazon UK Retailer Scraper
Extracts detailed product specifications from Amazon.co.uk product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse, parse_qs
from src.scrapers.retailers.base import RetailerScraper
import re
import os
import json
import google.generativeai as genai


class AmazonScraper(RetailerScraper):
    """Scraper for Amazon.co.uk product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Amazon"

    @property
    def url_patterns(self) -> List[str]:
        return ['amazon.co.uk', 'www.amazon.co.uk']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from Amazon URLs.

        Converts:
        https://www.amazon.co.uk/dp/B0CXTPK12L?ref=xyz&tag=abc

        To:
        https://www.amazon.co.uk/dp/B0CXTPK12L
        """
        parsed = urlparse(url)

        # Extract ASIN/product ID from path
        # Amazon URLs can be /dp/ASIN or /gp/product/ASIN
        path_match = re.search(r'/(dp|gp/product)/([A-Z0-9]{10})', parsed.path)
        if path_match:
            asin = path_match.group(2)
            # Construct clean URL with just the ASIN
            return f"https://www.amazon.co.uk/dp/{asin}"

        # Fallback: just remove query parameters
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',  # params
            '',  # query
            ''   # fragment
        ))
        return clean_url

    async def scrape_product(self, page, url: str) -> Dict:
        """
        Scrape product specifications from Amazon.co.uk product page.

        Args:
            page: Playwright page object (already navigated to URL)
            url: Amazon product URL

        Returns:
            Dict with scraped product data
        """
        try:
            # Amazon cookie banner appears immediately and blocks page load
            # Handle it FIRST before waiting for full page load
            print("  ├─ Checking for cookie banner...")
            try:
                # Wait for either cookie banner or page content (whichever comes first)
                cookie_button = page.locator('#sp-cc-accept, input#sp-cc-accept')
                await cookie_button.wait_for(state='visible', timeout=5000)
                print("  ├─ Cookie banner detected, accepting...")
                await cookie_button.first.click()
                await page.wait_for_timeout(1000)
                print("  ├─ Cookie banner accepted")
            except Exception as e:
                print(f"  ├─ No cookie banner found or already accepted: {str(e)[:50]}")

            # Now wait for page content to load
            print("  ├─ Waiting for page content...")
            await page.wait_for_timeout(2000)

            # Extract specifications from product overview table
            specs = await self._extract_specifications(page)

            # Extract feature bullets
            features = await self._extract_features(page)

            # Parse ALL text data (features + specs) with Gemini to extract structured data
            # This includes parsing "special_feature" which also contains structured info
            structured_specs = {}
            if features or specs:
                print("  ├─ Parsing features & specs with Gemini to extract structured data...")
                try:
                    # Combine features and specs for comprehensive parsing
                    all_text_data = {**features, **specs}
                    structured_specs = await self._parse_features_with_gemini(all_text_data)
                    print(f"  └─ Extracted {len(structured_specs)} structured specs from Gemini")
                except Exception as e:
                    print(f"  └─ Gemini parsing failed: {str(e)[:50]}")
                    structured_specs = {}

            # Remove text blobs that have been parsed by Gemini
            # Keep clean specs like "capacity", "colour", "material"
            # Remove: "special_feature" (parsed into functions), "product_dimensions" (parsed into height/width/depth)
            text_blob_keys = ['special_feature', 'product_dimensions']
            clean_specs = {k: v for k, v in specs.items() if k not in text_blob_keys}

            # Combine: Gemini-parsed structured specs + clean table specs
            # Clean specs win on conflicts (e.g., keep "capacity: 9.5 litres" from table vs "capacity_l: 9.5" from Gemini)
            combined_specs = {**structured_specs, **clean_specs}

            # Get current URL (after any redirects)
            current_url = page.url
            clean_product_url = self.clean_url(current_url)

            return {
                'specs': combined_specs,
                'retailerUrl': clean_product_url,
                'success': True
            }

        except Exception as e:
            return {
                'specs': {},
                'retailerUrl': url,
                'success': False,
                'error': str(e)
            }

    async def _extract_specifications(self, page) -> Dict:
        """
        Extract specifications from Amazon product overview table.

        The table has rows with 2 cells:
        - First cell: key (with class a-text-bold)
        - Second cell: value (with class po-break-word)

        Returns:
            Dict with flattened specifications
        """
        print("  ├─ Extracting specifications from product table...")

        specs = await page.evaluate('''
            () => {
                const allSpecs = {};

                // Find the product overview table
                const table = document.querySelector('table.a-normal.a-spacing-micro');
                if (!table) {
                    console.log('No product overview table found');
                    return allSpecs;
                }

                // Get all rows
                const rows = table.querySelectorAll('tr');

                rows.forEach(row => {
                    // Find key and value cells
                    const cells = row.querySelectorAll('td');

                    if (cells.length >= 2) {
                        // First cell is the key
                        const keyEl = cells[0].querySelector('.a-text-bold');

                        // Second cell contains the value
                        // Check for truncated content first (prefer full text)
                        let valueEl = cells[1].querySelector('.a-truncate-full');
                        if (!valueEl) {
                            valueEl = cells[1].querySelector('.po-break-word, span');
                        }

                        if (keyEl && valueEl) {
                            const keyText = keyEl.textContent.trim();
                            const valueText = valueEl.textContent.trim();

                            // Clean up the key
                            let key = keyText
                                .toLowerCase()
                                .replace(/[^a-z0-9]+/g, '_')
                                .replace(/^_|_$/g, '');

                            // Skip empty keys or values
                            if (key && valueText && valueText !== '-' && valueText !== 'N/A') {
                                allSpecs[key] = valueText;
                            }
                        }
                    }
                });

                console.log(`Extracted ${Object.keys(allSpecs).length} specifications from table`);
                return allSpecs;
            }
        ''')

        spec_count = len(specs)
        print(f"  └─ Extracted {spec_count} specifications from table")

        return specs

    async def _extract_features(self, page) -> Dict:
        """
        Extract feature bullets from Amazon product page.

        The features are in an unordered list with id="feature-bullets".
        Each feature is a list item with descriptive text.

        We'll extract these as numbered feature keys.

        Returns:
            Dict with feature descriptions
        """
        print("  ├─ Extracting feature bullets...")

        features = await page.evaluate('''
            () => {
                const featureDict = {};

                // Find the feature bullets section
                const featureBullets = document.querySelector('#feature-bullets ul');
                if (!featureBullets) {
                    console.log('No feature bullets found');
                    return featureDict;
                }

                // Get all list items
                const items = featureBullets.querySelectorAll('li span.a-list-item');

                items.forEach((item, index) => {
                    const text = item.textContent.trim();

                    // Skip empty or very short items
                    if (text && text.length > 10) {
                        // Use numbered keys: feature_1, feature_2, etc.
                        const key = `feature_${index + 1}`;
                        featureDict[key] = text;
                    }
                });

                console.log(`Extracted ${Object.keys(featureDict).length} feature bullets`);
                return featureDict;
            }
        ''')

        feature_count = len(features)
        print(f"  └─ Extracted {feature_count} feature bullets")

        return features

    async def _parse_features_with_gemini(self, text_data: Dict) -> Dict:
        """
        Use Gemini 2.5 Flash to extract structured specifications from text data.

        Amazon product pages contain rich data buried in marketing text across:
        - Feature bullets: "INCLUDES: ... Dimensions: H38.5cm x W28cm x D47cm..."
        - Special features: "6 Cooking Functions, Air Fry, Max Crisp, Roast, Bake..."
        - Product descriptions: Various text fields with embedded specs

        This method extracts structured key-value pairs like:
        - "Dimensions: H38.5cm x W28cm" → height_cm: "38.5", width_cm: "28"
        - "9.5L capacity" → capacity_l: "9.5"
        - "Air Fry, Roast, Bake" → air_fry_function: "Yes", roast_function: "Yes"

        Args:
            text_data: Dict of text fields (features, specs, etc.)

        Returns:
            Dict of structured specs extracted from all text
        """
        # Load API key
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=api_key)

        # Build text data for prompt
        text_input = "\n".join([f"- {key}: \"{value}\"" for key, value in text_data.items()])

        # Create prompt
        prompt = f"""You are extracting structured product specifications from Amazon product text.

Product text (marketing copy, features, and specs with embedded data):
{text_input}

Your task: Extract ALL product specifications as clean key-value pairs.

Rules:
1. Use snake_case for keys (e.g., "height_cm", "drawer_capacity_l")
2. Values should be clean strings (numbers or Yes/No when appropriate)
3. Extract dimensions: "H38.5cm x W28cm x D47cm" → height_cm: "38.5", width_cm: "28", depth_cm: "47"
4. Extract capacities: "9.5L capacity" → capacity_l: "9.5"
5. Extract counts: "2x drawers" → number_of_drawers: "2", "2 independent cooking zones" → number_of_cooking_zones: "2"
6. Extract functions from comma-separated lists: "Air Fry, Max Crisp, Roast, Bake, Reheat, Dehydrate" → air_fry_function: "Yes", max_crisp_function: "Yes", roast_function: "Yes", bake_function: "Yes", reheat_function: "Yes", dehydrate_function: "Yes"
7. Extract features: "Dishwasher Safe Parts" → dishwasher_safe_parts: "Yes", "2 racks" → number_of_racks: "2"
8. Extract performance: "55% less energy" → energy_efficiency_percentage: "55"
9. Extract weight: "10.3kg" → weight_kg: "10.3"
10. Extract warranty: "2 year guarantee" → manufacturer_warranty_years: "2"
11. Include units in key names (e.g., _cm, _kg, _l, _w, _years, _percentage)
12. Skip marketing fluff - only extract factual specs
13. Return ONLY valid JSON, no explanations

Return format:
{{
  "key_name": "value",
  ...
}}"""

        # Call Gemini
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

        # Parse JSON
        structured_specs = json.loads(response_text)

        return structured_specs
