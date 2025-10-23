"""
Very.co.uk Retailer Scraper
Extracts detailed product specifications from Very.co.uk product pages
"""

from typing import Dict, List
from urllib.parse import urlparse
from src.scrapers.retailers.base import RetailerScraper
import os
import json
import google.generativeai as genai


class VeryScraper(RetailerScraper):
    """Scraper for Very.co.uk product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Very"

    @property
    def url_patterns(self) -> List[str]:
        return ['very.co.uk', 'www.very.co.uk']

    def clean_url(self, url: str) -> str:
        """
        Very URLs come from complex tracking redirects that we can't pre-clean.

        Example:
        https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com...

        We can't extract the final Very.co.uk URL from this, so we:
        1. Return the URL as-is (orchestrator will navigate to it)
        2. After redirect completes, orchestrator gets final URL from page.url
        3. That final URL is what we return as retailerUrl
        """
        # If already a very.co.uk URL, return as-is
        if 'very.co.uk' in url:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Otherwise, return as-is and let browser handle redirects
        return url

    async def scrape_product(self, page, url: str) -> Dict:
        """
        Scrape product specifications from Very.co.uk product page.

        Args:
            page: Playwright page object (already navigated to URL after redirects)
            url: Very product URL (final URL after redirects)

        Returns:
            Dict with scraped product data
        """
        try:
            # Wait for page to load
            print("  ├─ Waiting for page content...")
            await page.wait_for_timeout(2000)

            # Handle cookie consent if present
            try:
                cookie_button = page.locator('button:has-text("Accept all cookies"), button:has-text("Accept All")')
                if await cookie_button.count() > 0:
                    await cookie_button.first.click()
                    await page.wait_for_timeout(500)
            except:
                pass

            # Click all accordion buttons to expand content
            await self._expand_accordions(page)

            # Extract specifications from technical specs table
            specs = await self._extract_technical_specs(page)

            # Extract features from features section
            features_text = await self._extract_features(page)

            # Extract description with embedded specs
            description_text = await self._extract_description(page)

            # Combine all text data for Gemini parsing
            all_text_data = {**features_text, **description_text, **specs}

            # Parse with Gemini to extract structured data
            structured_specs = {}
            if all_text_data:
                print("  ├─ Parsing content with Gemini to extract structured specs...")
                try:
                    structured_specs = await self._parse_with_gemini(all_text_data)
                    print(f"  └─ Extracted {len(structured_specs)} structured specs from Gemini")
                except Exception as e:
                    print(f"  └─ Gemini parsing failed: {str(e)[:50]}")

            # Combine: Gemini-parsed structured specs + clean table specs
            # Table specs win on conflicts
            combined_specs = {**structured_specs, **specs}

            # Get current URL (after redirects)
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

    async def _expand_accordions(self, page) -> None:
        """
        Click all accordion buttons to expand content sections.

        Very uses accordions for:
        - Product description
        - Product features
        - Technical specification
        """
        print("  ├─ Expanding accordion sections...")

        try:
            # Find all accordion buttons
            accordion_buttons = page.locator('button.fuse-accordion__button')
            count = await accordion_buttons.count()
            print(f"  │  Found {count} accordion sections")

            # Click each button
            for i in range(count):
                try:
                    button = accordion_buttons.nth(i)
                    heading = await button.locator('.fuse-accordion__heading').text_content()
                    print(f"  │  ├─ Expanding: {heading}")

                    # Check if already expanded
                    is_expanded = await button.get_attribute('aria-expanded')
                    if is_expanded != 'true':
                        await button.click(timeout=3000)
                        await page.wait_for_timeout(500)
                except Exception as e:
                    print(f"  │  ├─ Could not expand section {i}: {str(e)[:30]}")
                    continue

            print("  └─ All accordions expanded")

        except Exception as e:
            print(f"  └─ Error expanding accordions: {str(e)[:50]}")

    async def _extract_technical_specs(self, page) -> Dict:
        """
        Extract specifications from technical specification table.

        Table structure: 2 columns (key, value) in tbody rows
        """
        print("  ├─ Extracting technical specifications...")

        specs = await page.evaluate('''
            () => {
                const allSpecs = {};

                // Find the technical specs table
                const table = document.querySelector('#ccs-combo-spec table');
                if (!table) {
                    console.log('No technical specs table found');
                    return allSpecs;
                }

                // Get all rows
                const rows = table.querySelectorAll('tbody tr');

                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');

                    if (cells.length >= 2) {
                        const keyEl = cells[0];
                        const valueEl = cells[1];

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

                console.log(`Extracted ${Object.keys(allSpecs).length} technical specs`);
                return allSpecs;
            }
        ''')

        spec_count = len(specs)
        print(f"  └─ Extracted {spec_count} technical specifications")

        return specs

    async def _extract_features(self, page) -> Dict:
        """
        Extract features from the features section.
        Features have headings (h3) and descriptions (p).
        """
        print("  ├─ Extracting product features...")

        features = await page.evaluate('''
            () => {
                const features = {};

                // Find the features container
                const featuresContainer = document.querySelector('#ccs-features');
                if (!featuresContainer) {
                    console.log('No features section found');
                    return features;
                }

                // Get all h3 headings and their following paragraphs
                const headings = featuresContainer.querySelectorAll('h3');

                headings.forEach((heading, index) => {
                    const title = heading.textContent.trim();
                    const nextP = heading.nextElementSibling;

                    if (nextP && nextP.tagName === 'P') {
                        const description = nextP.textContent.trim();
                        const key = `feature_${index + 1}`;
                        features[key] = `${title}: ${description}`;
                    }
                });

                console.log(`Extracted ${Object.keys(features).length} features`);
                return features;
            }
        ''')

        feature_count = len(features)
        print(f"  └─ Extracted {feature_count} product features")

        return features

    async def _extract_description(self, page) -> Dict:
        """
        Extract product description with embedded specs.

        The description contains:
        - Item number
        - EAN
        - Marketing text
        - Embedded specs in <ul> lists
        """
        print("  ├─ Extracting product description...")

        description = await page.evaluate('''
            () => {
                const desc = {};

                // Find the description container
                const descContainer = document.querySelector('[data-testid="product_description_body"]');
                if (!descContainer) {
                    console.log('No description found');
                    return desc;
                }

                // Get all text content including list items
                const text = descContainer.textContent.trim();

                // Store as a single description field
                desc['description'] = text;

                console.log('Extracted product description');
                return desc;
            }
        ''')

        print(f"  └─ Extracted product description")

        return description

    async def _parse_with_gemini(self, text_data: Dict) -> Dict:
        """
        Use Gemini 2.5 Flash to extract structured specifications from all text content.
        """
        # Load API key
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")

        genai.configure(api_key=api_key)

        # Build text input for prompt
        text_input = "\n".join([f"- {key}: \"{value}\"" for key, value in text_data.items()])

        # Create prompt
        prompt = f"""You are extracting structured product specifications from Very.co.uk product text.

Product text (features, descriptions, and embedded specs):
{text_input}

Your task: Extract ALL product specifications as clean key-value pairs.

Rules:
1. Use snake_case for keys (e.g., "width_cm", "water_tank_capacity_l")
2. Values should be clean strings (numbers or Yes/No when appropriate)
3. Extract dimensions: "14.1 cm x 31.1 cm x 28.3 cm" → width_cm: "14.1", depth_cm: "31.1", height_cm: "28.3"
4. Extract capacities: "1.2-litre water tank" → water_tank_capacity_l: "1.2"
5. Extract pressure: "20 bar" → pressure_bar: "20"
6. Extract features: "Removable drip tray" → removable_drip_tray: "Yes", "Steam wand" → steam_wand: "Yes"
7. Extract functions: "LED display" → led_display: "Yes"
8. Extract weight: "10.2 kg" → weight_kg: "10.2"
9. Extract warranty: "3 years" → manufacturer_warranty_years: "3"
10. Extract compatibility: "Ground coffee" → coffee_type_compatibility: "Ground coffee"
11. Include units in key names (e.g., _cm, _kg, _l, _bar, _years)
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
