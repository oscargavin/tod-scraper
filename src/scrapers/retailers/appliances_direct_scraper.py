"""
Appliances Direct Retailer Scraper
Extracts detailed product specifications from Appliances Direct product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse, parse_qs, unquote
from src.scrapers.retailers.base import RetailerScraper
import re


class AppliancesDirectScraper(RetailerScraper):
    """Scraper for Appliances Direct product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Appliances Direct"

    @property
    def url_patterns(self) -> List[str]:
        return ['appliancesdirect.co.uk', 'digidip.net']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from Appliances Direct URLs.

        Handles tracking URLs like:
        https://which.digidip.net/visit?url=https%3A%2F%2Fwww.appliancesdirect.co.uk%2Fp%2Fwgg254z1gb%2F...

        Converts to:
        https://www.appliancesdirect.co.uk/p/wgg254z1gb/...
        """
        # If it's a digidip.net tracking URL, extract the actual URL
        if 'digidip.net' in url:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            # Extract the 'url' parameter which contains the actual product URL
            if 'url' in query_params:
                encoded_url = query_params['url'][0]
                # URL decode it
                decoded_url = unquote(encoded_url)
                url = decoded_url

        # Clean query parameters from final URL
        parsed = urlparse(url)
        clean_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            '',  # params
            '',  # query (remove tracking params)
            ''   # fragment
        ))
        return clean_url

    async def scrape_product(self, page, url: str) -> Dict:
        """
        Scrape product specifications from Appliances Direct product page.

        Args:
            page: Playwright page object (already navigated to URL)
            url: Appliances Direct product URL

        Returns:
            Dict with scraped product data
        """
        try:
            # Check if this is still a tracking URL - if so, we need to navigate directly
            current_url = page.url
            if 'digidip.net' in current_url:
                # Extract and navigate to the actual product URL
                direct_url = self.clean_url(current_url)
                print(f"  ├─ Tracking URL detected, navigating to: {direct_url}")
                await page.goto(direct_url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(1000)

            # Wait for page to load
            await page.wait_for_timeout(1500)

            # Check if we need to handle cookie banner
            try:
                cookie_button = page.locator('button:has-text("Accept"), button:has-text("accept")', timeout=2000)
                if await cookie_button.count() > 0:
                    await cookie_button.first.click()
                    await page.wait_for_timeout(500)
            except:
                pass

            # Extract specifications from table
            specs = await self._extract_specifications(page)

            # Get current URL (after any redirects)
            current_url = page.url
            clean_product_url = self.clean_url(current_url)

            return {
                'specs': specs,
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
        Extract specifications from Appliances Direct table.

        The page uses a table with id "gvwSpec" containing rows with 2 columns:
        - Left column: key in <span class="Header">
        - Right column: value in <span class="BodyText">

        Some values contain SVG icons for Yes/No (checkmark or X).

        Returns:
            Dict with flattened specifications
        """
        print("  ├─ Extracting specifications from table...")

        specs = await page.evaluate('''
            () => {
                const allSpecs = {};
                let specCount = 0;

                // Find the specification table
                const table = document.querySelector('#gvwSpec, table.table-bordered');

                if (!table) {
                    console.log('Specification table not found');
                    return allSpecs;
                }

                // Get all rows
                const rows = table.querySelectorAll('tr');
                console.log(`Found ${rows.length} rows in specification table`);

                rows.forEach(row => {
                    const cells = row.querySelectorAll('td');

                    // If row has exactly 2 cells, treat as key-value
                    if (cells.length === 2) {
                        // Extract key from first cell (look for .Header span)
                        const keySpan = cells[0].querySelector('.Header, span.Header');
                        if (!keySpan) return;

                        const keyText = keySpan.textContent.trim();

                        // Extract value from second cell (look for .BodyText span)
                        const valueSpan = cells[1].querySelector('.BodyText, span.BodyText');
                        if (!valueSpan) return;

                        // Check if value contains an SVG icon (checkmark or X)
                        let valueText = valueSpan.textContent.trim();
                        const hasSvg = valueSpan.querySelector('svg');

                        if (hasSvg) {
                            // Check if it's a checkmark or X
                            const isCheck = hasSvg.getAttribute('data-icon') === 'check' ||
                                          hasSvg.querySelector('path[d*="M438.6"]') !== null;
                            const isXmark = hasSvg.getAttribute('data-icon') === 'xmark' ||
                                          hasSvg.querySelector('path[d*="M342.6"]') !== null;

                            if (isCheck) {
                                valueText = 'Yes';
                            } else if (isXmark) {
                                valueText = 'No';
                            }
                        }

                        // Clean up the key
                        let key = keyText
                            .replace(/[:\\.]/g, '')  // Remove colons and dots
                            .toLowerCase()
                            .replace(/[^a-z0-9]+/g, '_')
                            .replace(/^_|_$/g, '');

                        // Skip empty keys or values, or section headers
                        if (!key || !valueText || key === '_' || valueText === '-') {
                            return;
                        }

                        // Store the spec
                        allSpecs[key] = valueText;
                        specCount++;
                    }
                });

                console.log(`Extracted ${specCount} specifications`);
                return allSpecs;
            }
        ''')

        spec_count = len(specs)
        print(f"  └─ Extracted {spec_count} specifications")

        return specs
