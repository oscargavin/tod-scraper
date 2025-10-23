"""
AO.com Retailer Scraper
Extracts detailed product specifications from AO.com product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse
from src.scrapers.retailers.base import RetailerScraper


class AOScraper(RetailerScraper):
    """Scraper for AO.com product specifications"""

    @property
    def retailer_name(self) -> str:
        return "AO"

    @property
    def url_patterns(self) -> List[str]:
        return ['ao.com', 'ao.co.uk']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from AO.com URLs.

        Converts:
        https://ao.com/product/wg46h2a9gb-siemens-iq500-idos-washing-machine-white-105192-1.aspx?utm_medium=affiliates...

        To:
        https://ao.com/product/wg46h2a9gb-siemens-iq500-idos-washing-machine-white-105192-1.aspx
        """
        parsed = urlparse(url)
        # Reconstruct URL without query parameters and fragment
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
        Scrape product specifications from AO.com product page.

        Args:
            page: Playwright page object (already navigated to URL)
            url: AO.com product URL

        Returns:
            Dict with scraped product data
        """
        try:
            # Extract specifications by clicking through accordions
            nested_specs = await self._extract_specifications(page)

            # Flatten nested structure
            flattened_specs = self._flatten_specs(nested_specs)

            # Extract basic info (name, price)
            basic_info = await self._extract_basic_info(page)

            # Clean the URL
            clean_product_url = self.clean_url(url)

            return {
                'specs': flattened_specs,
                'name': basic_info.get('name'),
                'price': basic_info.get('price'),
                'retailerUrl': clean_product_url,
                'success': True
            }

        except Exception as e:
            return {
                'specs': {},
                'name': None,
                'price': None,
                'retailerUrl': url,
                'success': False,
                'error': str(e)
            }

    async def _extract_specifications(self, page) -> Dict:
        """
        Extract specifications from AO.com product page.
        Clicks through all accordion sections to get complete specs.

        Returns:
            Nested dict with sections like:
            {
                'key_information': {...},
                'design': {...},
                ...
            }
        """
        print("  ├─ Waiting for page to load...")
        await page.wait_for_timeout(1000)

        # Try to click the main "View full specification" button
        try:
            print("  ├─ Clicking 'View full specification' button...")
            view_spec_button = page.locator('button[data-parent-accordion-trigger]')
            await view_spec_button.click(timeout=5000)
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"  ├─ Could not click main button (may already be expanded): {str(e)[:50]}")

        # Get all accordion section headers and expand them
        try:
            print("  ├─ Expanding all specification sections...")
            accordion_headers = page.locator('header[data-accordion-trigger]')
            count = await accordion_headers.count()
            print(f"  ├─ Found {count} specification sections")

            # Click each accordion header to expand it
            for i in range(count):
                try:
                    header = accordion_headers.nth(i)
                    section_name = await header.locator('h3').text_content()
                    print(f"  │  ├─ Expanding: {section_name}")
                    await header.click(timeout=2000)
                    await page.wait_for_timeout(300)  # Brief wait for animation
                except Exception as e:
                    print(f"  │  ├─ Could not expand section {i}: {str(e)[:30]}")
                    continue

            print("  ├─ All sections expanded")
        except Exception as e:
            print(f"  ├─ Error expanding sections: {str(e)[:50]}")

        # Extract all specifications using JavaScript
        print("  ├─ Extracting specifications...")
        specs = await page.evaluate('''
            () => {
                const specs = {};

                // Find all accordion sections
                const sections = document.querySelectorAll('[data-accordion="specification-features"]');

                sections.forEach(section => {
                    // Get section name from header
                    const header = section.querySelector('header h3');
                    const sectionName = header ? header.textContent.trim() : 'Unknown';

                    // Get the content div
                    const content = section.querySelector('[data-accordion-content]');
                    if (!content) return;

                    // Create a clean section name for the key
                    const sectionKey = sectionName
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, '_')
                        .replace(/^_|_$/g, '');

                    // Extract all key-value pairs from this section
                    const sectionSpecs = {};
                    const specRows = content.querySelectorAll('.flex.items-center.p-3');

                    specRows.forEach(row => {
                        // Find the key (the div with text-body-sm that contains the spec name)
                        const keyDiv = row.querySelector('div.text-body-sm[data-tag-type="accordion"]');
                        // Find the value (the span at the end)
                        const valueSpan = row.querySelector('span.ml-auto, span.flex-shrink-0.ml-auto');

                        if (keyDiv && valueSpan) {
                            const key = keyDiv.textContent.trim();
                            const value = valueSpan.textContent.trim();

                            if (key && value) {
                                // Create clean key
                                const cleanKey = key
                                    .toLowerCase()
                                    .replace(/[^a-z0-9]+/g, '_')
                                    .replace(/^_|_$/g, '');

                                if (cleanKey) {
                                    sectionSpecs[cleanKey] = value;
                                }
                            }
                        }
                    });

                    // Add section to main specs object
                    if (Object.keys(sectionSpecs).length > 0) {
                        specs[sectionKey] = sectionSpecs;
                    }
                });

                return specs;
            }
        ''')

        # Count total specs extracted
        total_specs = sum(len(section) for section in specs.values())
        print(f"  └─ Extracted {len(specs)} sections with {total_specs} total specifications")

        return specs

    async def _extract_basic_info(self, page) -> Dict:
        """Extract basic product information like name and price"""
        print("  ├─ Extracting basic product info...")

        info = await page.evaluate('''
            () => {
                const result = {
                    name: null,
                    price: null
                };

                // Extract product name from h1
                const nameEl = document.querySelector('h1');
                if (nameEl) {
                    result.name = nameEl.textContent.trim();
                }

                // Extract price
                const priceEl = document.querySelector('[data-testid="product-price"]');
                if (priceEl) {
                    result.price = priceEl.textContent.trim();
                }

                return result;
            }
        ''')

        return info

    def _flatten_specs(self, specifications: Dict) -> Dict:
        """
        Flatten nested AO.com specifications into a single dictionary.

        Converts from:
          {
            "key_information": {"max_spin_speed": "1600 RPM", ...},
            "design": {"adjustable_feet": "Yes", ...}
          }
        To:
          {
            "max_spin_speed": "1600 RPM",
            "adjustable_feet": "Yes",
            ...
          }
        """
        flattened = {}
        for section_name, section_specs in specifications.items():
            if isinstance(section_specs, dict):
                # Merge all specs from this section into the flat dictionary
                flattened.update(section_specs)
        return flattened
