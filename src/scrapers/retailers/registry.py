"""
Retailer Scraper Registry
Manages registration and lookup of retailer scrapers
"""

from typing import Dict, List, Optional
from src.scrapers.retailers.base import RetailerScraper


class RetailerScraperRegistry:
    """
    Registry for all available retailer scrapers.
    Provides methods to find the right scraper for a given URL or retailer name.
    """

    def __init__(self):
        """Initialize empty registry"""
        self._scrapers: Dict[str, RetailerScraper] = {}

    def register(self, scraper: RetailerScraper) -> None:
        """
        Register a retailer scraper.

        Args:
            scraper: RetailerScraper instance to register

        Raises:
            ValueError: If scraper with this name is already registered
        """
        name = scraper.retailer_name.upper()

        if name in self._scrapers:
            raise ValueError(f"Scraper for '{scraper.retailer_name}' is already registered")

        self._scrapers[name] = scraper

    def get_by_name(self, name: str) -> Optional[RetailerScraper]:
        """
        Get scraper by retailer name (case-insensitive).

        Args:
            name: Retailer name (e.g., 'AO', 'Marks Electrical')

        Returns:
            RetailerScraper if found, None otherwise
        """
        return self._scrapers.get(name.upper())

    def get_by_url(self, url: str) -> Optional[RetailerScraper]:
        """
        Find scraper that can handle the given URL.

        Args:
            url: Product URL to match

        Returns:
            RetailerScraper if matching scraper found, None otherwise
        """
        for scraper in self._scrapers.values():
            if scraper.matches_url(url):
                return scraper
        return None

    def find_scraper_for_retailer_link(self, retailer_link: Dict) -> Optional[RetailerScraper]:
        """
        Find scraper for a retailer link from Which.com.

        Tries to match by:
        1. Retailer name (from 'name' field)
        2. URL patterns (from 'url' field)

        Args:
            retailer_link: Dict with 'name' and 'url' fields

        Returns:
            RetailerScraper if found, None otherwise
        """
        name = retailer_link.get('name', '')
        url = retailer_link.get('url', '')

        # First try to match by name (more reliable)
        if name:
            scraper = self.get_by_name(name)
            if scraper:
                return scraper

        # Fallback to URL pattern matching
        if url:
            return self.get_by_url(url)

        return None

    def get_all_scrapers(self) -> List[RetailerScraper]:
        """
        Get all registered scrapers.

        Returns:
            List of all registered RetailerScraper instances
        """
        return list(self._scrapers.values())

    def get_retailer_names(self) -> List[str]:
        """
        Get names of all registered retailers.

        Returns:
            List of retailer names
        """
        return [scraper.retailer_name for scraper in self._scrapers.values()]

    def is_registered(self, name: str) -> bool:
        """
        Check if a retailer scraper is registered.

        Args:
            name: Retailer name to check

        Returns:
            True if registered, False otherwise
        """
        return name.upper() in self._scrapers

    def count(self) -> int:
        """
        Get number of registered scrapers.

        Returns:
            Number of scrapers in registry
        """
        return len(self._scrapers)

    def __repr__(self) -> str:
        """String representation of registry"""
        retailers = ', '.join(self.get_retailer_names())
        return f"RetailerScraperRegistry({self.count()} scrapers: {retailers})"
