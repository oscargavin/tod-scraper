"""
Boots Kitchen Appliances Retailer Scraper
Extracts detailed product specifications from Boots Kitchen Appliances product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse
from src.scrapers.retailers.base import RetailerScraper


class BootsScraper(RetailerScraper):
    """Scraper for Boots Kitchen Appliances product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Boots Kitchen Appliances"

    @property
    def url_patterns(self) -> List[str]:
        return ['bootskitchenappliances.com']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from Boots Kitchen Appliances URLs.

        Args:
            url: Raw retailer URL (may contain tracking params)

        Returns:
            str: Cleaned URL without tracking parameters
        """
        # Clean query parameters
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
        Scrape product specifications from Boots Kitchen Appliances product page.

        The site uses multiple tables with section headers and 2-column rows (key, value).
        Tables include: Product Detail, Product Overview, Warranty, Performance,
        Unique Features, Features We Love, Design, Installation, Wireless Connections

        Args:
            page: Playwright page object (already navigated to URL)
            url: Boots Kitchen Appliances product URL

        Returns:
            Dict with scraped product data
        """
        try:
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

            # Extract specifications from tables
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
        Extract specifications from Boots Kitchen Appliances tables.

        The site uses multiple tables with section headers and 2-column rows.
        Each table has a header row with a section name and empty second cell,
        followed by key-value rows.

        Returns:
            Dict with flattened specifications
        """
        print("  ├─ Extracting specifications from tables...")

        specs = await page.evaluate('''
            () => {
                const allSpecs = {};
                let specCount = 0;

                // Find all tables
                const tables = document.querySelectorAll('table');

                tables.forEach((table, tableIndex) => {
                    // Look for rows with 2 cells (key-value pairs)
                    const rows = table.querySelectorAll('tr');

                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, th');

                        // If row has exactly 2 cells, treat as key-value
                        if (cells.length === 2) {
                            const keyText = cells[0].textContent.trim();
                            const valueText = cells[1].textContent.trim();

                            // Skip header rows (empty value cell)
                            if (!valueText || valueText === '') {
                                return;
                            }

                            // Clean up the key
                            let key = keyText
                                .replace(/[:\\.]/g, '')  // Remove colons and dots
                                .toLowerCase()
                                .replace(/[^a-z0-9]+/g, '_')
                                .replace(/^_|_$/g, '');

                            // Skip empty keys or invalid values
                            if (!key || key === '_' || valueText === '-') {
                                return;
                            }

                            // Store the spec
                            allSpecs[key] = valueText;
                            specCount++;
                        }
                    });
                });

                console.log(`Extracted ${specCount} specifications from ${tables.length} tables`);
                return allSpecs;
            }
        ''')

        spec_count = len(specs)
        print(f"  └─ Extracted {spec_count} specifications")

        return specs
