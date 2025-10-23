"""
Marks Electrical Retailer Scraper
Extracts detailed product specifications from Marks Electrical product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse, unquote
from src.scrapers.retailers.base import RetailerScraper
import re


class MarksElectricalScraper(RetailerScraper):
    """Scraper for Marks Electrical product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Marks Electrical"

    @property
    def url_patterns(self) -> List[str]:
        return ['markselectrical.co.uk', 'visit.markselectrical.co.uk']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from Marks Electrical URLs.

        Handles tracking URLs like:
        https://visit.markselectrical.co.uk/click?a(...)url(https%3A%2F%2Fmarkselectrical.co.uk%2Fproduct)

        Converts to:
        https://markselectrical.co.uk/product
        """
        # If it's a tracking URL, extract the actual URL
        if 'visit.markselectrical.co.uk' in url and 'url(' in url:
            # Extract URL from url(...) parameter
            match = re.search(r'url\(([^)]+)\)', url)
            if match:
                encoded_url = match.group(1)
                # URL decode it
                decoded_url = unquote(encoded_url)
                url = decoded_url

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
        Scrape product specifications from Marks Electrical product page.

        Args:
            page: Playwright page object (already navigated to URL)
            url: Marks Electrical product URL

        Returns:
            Dict with scraped product data
        """
        try:
            # Check if this is still a tracking URL - if so, we need to navigate directly
            current_url = page.url
            if 'visit.markselectrical.co.uk' in current_url and 'url(' in current_url:
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
        Extract specifications from Marks Electrical tables.

        The page uses tables with 2-column rows (key, value).
        Multiple tables contain different spec categories.

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

                            // Clean up the key
                            let key = keyText
                                .replace(/[:\\.]/g, '')  // Remove colons and dots
                                .toLowerCase()
                                .replace(/[^a-z0-9]+/g, '_')
                                .replace(/^_|_$/g, '');

                            // Skip empty keys or values
                            if (!key || !valueText || key === '_' || valueText === '-') {
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
