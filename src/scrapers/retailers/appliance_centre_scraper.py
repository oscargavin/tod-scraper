"""
Appliance Centre Retailer Scraper
Extracts detailed product specifications from Appliance Centre product pages
"""

from typing import Dict, List
from urllib.parse import urlparse, urlunparse
from src.scrapers.retailers.base import RetailerScraper


class ApplianceCentreScraper(RetailerScraper):
    """Scraper for Appliance Centre product specifications"""

    @property
    def retailer_name(self) -> str:
        return "Appliance Centre"

    @property
    def url_patterns(self) -> List[str]:
        return ['appliancecentre.co.uk']

    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from Appliance Centre URLs.

        Converts:
        https://www.appliancecentre.co.uk/p/product-name/?utm_source=...

        To:
        https://www.appliancecentre.co.uk/p/product-name/
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
        Scrape product specifications from Appliance Centre product page.

        Args:
            page: Playwright page object (already navigated to URL)
            url: Appliance Centre product URL

        Returns:
            Dict with scraped product data
        """
        try:
            # Wait for page to stabilize
            await page.wait_for_timeout(1000)

            # Expand all accordion sections to access specs
            await self._expand_accordions(page)

            # Extract specifications from both Overview and Features sections
            specs = await self._extract_specifications(page)

            # Clean the URL
            clean_product_url = self.clean_url(url)

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

    async def _expand_accordions(self, page) -> None:
        """
        Expand all accordion sections (Overview and Features) to make specs visible.
        """
        print("  ├─ Expanding accordion sections...")

        try:
            accordions = page.locator('.product-accordion')
            accordion_count = await accordions.count()
            print(f"  ├─ Found {accordion_count} accordion sections")

            # Click each accordion to expand it
            for i in range(accordion_count):
                accordion = accordions.nth(i)
                title_elem = accordion.locator('.title')
                title_text = await title_elem.text_content()
                print(f"  │  ├─ Expanding: {title_text.strip()}")

                # Click the title to expand
                await title_elem.click(timeout=2000)
                await page.wait_for_timeout(300)  # Wait for animation

            print("  ├─ All sections expanded")
        except Exception as e:
            print(f"  ├─ Error expanding accordions: {str(e)[:50]}")

    async def _extract_specifications(self, page) -> Dict:
        """
        Extract specifications from Appliance Centre product page.

        Handles two types of accordion content:
        1. Overview section: table with th/td rows
        2. Features section: nested .group-details with .detail items

        Returns:
            Dict with flattened specifications
        """
        print("  ├─ Extracting specifications...")

        specs = await page.evaluate('''
            () => {
                const allSpecs = {};

                // Find all accordion sections
                const accordions = document.querySelectorAll('.product-accordion');

                accordions.forEach(accordion => {
                    const titleElem = accordion.querySelector('.title');
                    const sectionName = titleElem ? titleElem.textContent.trim().split('\\n')[0] : 'Unknown';
                    const body = accordion.querySelector('.body');

                    if (!body) return;

                    // Check if this is the Overview section (has table)
                    const table = body.querySelector('table');
                    if (table) {
                        const rows = table.querySelectorAll('tr');
                        rows.forEach(row => {
                            const th = row.querySelector('th');
                            const td = row.querySelector('td');
                            if (th && td) {
                                const key = th.textContent.trim()
                                    .toLowerCase()
                                    .replace(/[^a-z0-9]+/g, '_')
                                    .replace(/^_|_$/g, '');
                                const value = td.textContent.trim();
                                if (key && value) {
                                    allSpecs[key] = value;
                                }
                            }
                        });
                    }

                    // Check if this is the Features section (has group-details)
                    const groupDetails = body.querySelectorAll('.group-details');
                    if (groupDetails.length > 0) {
                        groupDetails.forEach(group => {
                            const details = group.querySelectorAll('.detail');
                            details.forEach(detail => {
                                const strong = detail.querySelector('strong');
                                const span = detail.querySelector('span');
                                if (strong && span) {
                                    const key = strong.textContent.trim()
                                        .toLowerCase()
                                        .replace(/[^a-z0-9]+/g, '_')
                                        .replace(/^_|_$/g, '');
                                    const value = span.textContent.trim();
                                    if (key && value) {
                                        allSpecs[key] = value;
                                    }
                                }
                            });
                        });
                    }
                });

                return allSpecs;
            }
        ''')

        spec_count = len(specs)
        print(f"  └─ Extracted {spec_count} specifications")

        return specs
