"""
Base Retailer Scraper
Abstract base class that all retailer scrapers must inherit from
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class RetailerScraper(ABC):
    """
    Abstract base class for all retailer scrapers.
    Each retailer implementation must inherit from this class.
    """

    @property
    @abstractmethod
    def retailer_name(self) -> str:
        """
        Official retailer name for matching against Which.com retailer links.

        Examples: 'AO', 'Marks Electrical', 'Currys', 'John Lewis'

        Returns:
            str: Retailer name as it appears in Which.com retailer links
        """
        pass

    @property
    @abstractmethod
    def url_patterns(self) -> List[str]:
        """
        URL patterns/domains to match against retailer links.
        Used for identifying which scraper to use for a given URL.

        Examples: ['ao.com', 'ao.co.uk'] or ['markselectrical.co.uk']

        Returns:
            List[str]: List of URL patterns that identify this retailer
        """
        pass

    @abstractmethod
    async def scrape_product(self, page, url: str) -> Dict:
        """
        Scrape product specifications from retailer's product page.

        Args:
            page: Playwright page object
            url: Product URL to scrape

        Returns:
            Dict: Product data with structure:
                {
                    'specs': {key: value, ...},  # Flattened specifications
                    'name': str,                  # Product name (optional)
                    'price': str,                 # Product price (optional)
                    'retailerUrl': str,           # Cleaned product URL
                    'success': bool,              # Whether scraping succeeded
                    'error': str                  # Error message if failed (optional)
                }
        """
        pass

    @abstractmethod
    def clean_url(self, url: str) -> str:
        """
        Remove tracking parameters from retailer URL.

        Args:
            url: Raw retailer URL (may contain tracking params)

        Returns:
            str: Cleaned URL without tracking parameters
        """
        pass

    def calculate_quality_score(self, specs: Dict) -> float:
        """
        Calculate quality/confidence score for scraped data.
        Higher score = better data coverage.

        Default implementation: simple spec count metric.
        Override this in subclass for retailer-specific scoring.

        Args:
            specs: Dictionary of scraped specifications

        Returns:
            float: Quality score between 0.0 and 1.0
        """
        if not specs:
            return 0.0

        # Simple metric: normalize spec count (50+ specs = perfect score)
        spec_count = len(specs)
        return min(spec_count / 50.0, 1.0)

    def matches_url(self, url: str) -> bool:
        """
        Check if this scraper can handle the given URL.

        Args:
            url: URL to check

        Returns:
            bool: True if this scraper can handle the URL
        """
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in self.url_patterns)

    def matches_name(self, name: str) -> bool:
        """
        Check if this scraper matches the given retailer name.

        Args:
            name: Retailer name to check

        Returns:
            bool: True if names match (case-insensitive)
        """
        return name.upper() == self.retailer_name.upper()
