"""
Retailer Enrichment Orchestrator
Intelligently selects and executes retailer scrapers to enrich product data
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.utils.url_resolver import resolve_tracking_url
from src.scrapers.retailers.registry import RetailerScraperRegistry
from src.scrapers.retailers.base import RetailerScraper
from src.scrapers.retailers.ao_scraper import AOScraper
from src.scrapers.retailers.appliance_centre_scraper import ApplianceCentreScraper
from src.scrapers.retailers.marks_electrical_scraper import MarksElectricalScraper
from src.scrapers.retailers.boots_scraper import BootsScraper
from src.scrapers.retailers.appliances_direct_scraper import AppliancesDirectScraper
from src.scrapers.retailers.amazon_scraper import AmazonScraper


class RetailerEnrichmentOrchestrator:
    """
    Coordinates retailer scraping to maximize data coverage.

    Features:
    - Intelligent retailer selection based on priority and availability
    - Fallback chain if primary retailer fails
    - Quality scoring to pick best data source
    - Configurable behavior via retailer_config.json
    """

    def __init__(self, config_path: str = 'config/retailer_config.json'):
        """
        Initialize orchestrator with configuration.

        Args:
            config_path: Path to retailer configuration JSON file
        """
        self.registry = RetailerScraperRegistry()
        self.config = self._load_config(config_path)
        self._register_all_scrapers()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Config file '{config_path}' not found, using defaults")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"⚠️  Error parsing config file: {e}, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Get default configuration if config file not found"""
        return {
            'priority_order': ['AO', 'Appliance Centre'],
            'fallback_enabled': True,
            'max_fallback_attempts': 2,
            'min_specs_threshold': 5,
            'stop_at_first_success': True,
            'scrapers': {
                'AO': {'enabled': True, 'expected_spec_count': 50},
                'Appliance Centre': {'enabled': True, 'expected_spec_count': 50}
            }
        }

    def _register_all_scrapers(self) -> None:
        """
        Register all available retailer scrapers.

        Add new scrapers here as they are implemented.
        """
        # Register AO scraper
        self.registry.register(AOScraper())

        # Register Appliance Centre scraper
        self.registry.register(ApplianceCentreScraper())

        # Register Marks Electrical scraper
        self.registry.register(MarksElectricalScraper())

        # Register Boots Kitchen Appliances scraper
        self.registry.register(BootsScraper())

        # Register Appliances Direct scraper
        self.registry.register(AppliancesDirectScraper())

        # Register Amazon scraper
        self.registry.register(AmazonScraper())

        # Future scrapers will be added here:
        # Very scraper archived due to aggressive anti-bot protection (HTTP2 errors)
        # self.registry.register(CurrysScraper())
        # etc.

    async def enrich_product(self, product: Dict, page) -> Tuple[Dict, Dict]:
        """
        Enrich a single product with retailer specifications.

        Strategy:
        1. Find available retailers from product's retailerLinks
        2. Filter by enabled status and sort by priority
        3. Try primary retailer
        4. If fails or insufficient data, try fallback retailers
        5. Return best result based on quality score

        Args:
            product: Product dict with retailerLinks
            page: Playwright page object for scraping

        Returns:
            Tuple of (enriched_product, enrichment_stats)
        """
        retailer_links = product.get('retailerLinks', [])

        if not retailer_links:
            return product, {
                'attempted': False,
                'success': False,
                'reason': 'No retailer links available'
            }

        # Find available scrapers for this product
        available_scrapers = self._find_available_scrapers(retailer_links)

        if not available_scrapers:
            return product, {
                'attempted': False,
                'success': False,
                'reason': 'No enabled scrapers available for retailer links'
            }

        # Try scrapers in order
        best_result = None
        best_score = 0.0
        attempts = []

        for scraper, url in available_scrapers:
            # Try this scraper
            result = await self._try_scraper(scraper, url, page)
            attempts.append({
                'retailer': scraper.retailer_name,
                'success': result['success'],
                'spec_count': len(result['specs'])
            })

            if result['success']:
                score = scraper.calculate_quality_score(result['specs'])

                # Check if this is better than current best
                if score > best_score:
                    best_result = result
                    best_score = score

                # Stop if we got good enough data
                if self.config.get('stop_at_first_success', True):
                    break

            # Check if we should continue trying
            if not self.config.get('fallback_enabled', True):
                break

            if len(attempts) >= self.config.get('max_fallback_attempts', 2) + 1:
                break

        # Merge best result into product
        if best_result and best_result['success']:
            # Combine specs: retailer specs FILL GAPS, but Which.com data wins on conflicts
            # Order matters: retailer specs first, then Which.com specs overwrite conflicts
            which_specs = product.get('specs', {})
            retailer_specs = best_result['specs']

            # Combine: retailer enriches, Which.com has priority
            merged_specs = {**retailer_specs, **which_specs}

            product['specs'] = merged_specs
            product['retailerEnrichmentUrl'] = best_result['retailerUrl']
            product['retailerEnrichmentSource'] = best_result.get('source', 'unknown')

            return product, {
                'attempted': True,
                'success': True,
                'source': best_result.get('source'),
                'spec_count': len(best_result['specs']),
                'quality_score': best_score,
                'attempts': attempts
            }
        else:
            # All retailers failed - will be handled in Phase 4 (Gemini enrichment)
            return product, {
                'attempted': True,
                'success': False,
                'reason': 'All retailer scrapers failed or returned insufficient data',
                'attempts': attempts
            }

    async def _try_scraper(self, scraper: RetailerScraper, url: str, page) -> Dict:
        """
        Try to scrape a product using the given scraper.

        Args:
            scraper: RetailerScraper instance
            url: Product URL (may be tracking URL)
            page: Playwright page object

        Returns:
            Dict with scraping result
        """
        try:
            # Resolve tracking redirects with requests before Playwright navigation
            # Tracking URLs (clicks.trx-hub.com → awin1.com → final destination)
            # cause HTTP2 errors in Playwright, so we pre-resolve them
            if 'trx-hub.com' in url or 'awin1.com' in url or 'rakuten' in url:
                print(f"  ├─ Resolving tracking redirect chain...")
                resolved_url = resolve_tracking_url(url)

                if resolved_url:
                    print(f"  ├─ Resolved to: {resolved_url[:80]}...")
                    url = resolved_url
                else:
                    print(f"  ├─ Failed to resolve tracking URL")
                    return {
                        'success': False,
                        'specs': {},
                        'retailerUrl': url,
                        'error': 'Failed to resolve tracking redirect chain'
                    }

            # Clean URL before navigation (remove tracking params like ?tag=which1-21&linkCode=...)
            clean_url = scraper.clean_url(url)

            # Navigate to clean URL
            # Use 'domcontentloaded' for Amazon (cookie banners can block networkidle)
            wait_strategy = 'domcontentloaded' if scraper.retailer_name == 'Amazon' else 'networkidle'
            await page.goto(clean_url, wait_until=wait_strategy, timeout=60000)

            # Check if we actually ended up on the retailer's product page
            current_url = page.url
            if not scraper.matches_url(current_url):
                return {
                    'success': False,
                    'specs': {},
                    'retailerUrl': url,
                    'error': f'Redirect did not lead to {scraper.retailer_name} product page'
                }

            # Scrape the product
            result = await scraper.scrape_product(page, current_url)
            result['source'] = scraper.retailer_name

            # Validate result meets minimum threshold
            spec_count = len(result.get('specs', {}))
            min_threshold = self.config.get('min_specs_threshold', 20)

            if spec_count < min_threshold:
                result['success'] = False
                result['error'] = f'Insufficient specs: {spec_count} < {min_threshold}'

            return result

        except Exception as e:
            return {
                'success': False,
                'specs': {},
                'retailerUrl': url,
                'error': f'Exception during scraping: {str(e)[:100]}'
            }

    def _find_available_scrapers(self, retailer_links: List[Dict]) -> List[Tuple[RetailerScraper, str]]:
        """
        Find available and enabled scrapers for the given retailer links.

        Args:
            retailer_links: List of retailer link dicts from Which.com

        Returns:
            List of (scraper, url) tuples, sorted by priority
        """
        available = []

        for link in retailer_links:
            # Find scraper for this link
            scraper = self.registry.find_scraper_for_retailer_link(link)

            if scraper:
                # Check if scraper is enabled in config
                scraper_config = self.config.get('scrapers', {}).get(scraper.retailer_name, {})

                if scraper_config.get('enabled', False):
                    url = link.get('url', '')
                    if url:
                        available.append((scraper, url))

        # Sort by priority order from config
        priority_order = self.config.get('priority_order', [])
        available.sort(key=lambda x: self._get_priority(x[0].retailer_name, priority_order))

        return available

    def _get_priority(self, retailer_name: str, priority_order: List[str]) -> int:
        """
        Get priority index for a retailer (lower = higher priority).

        Args:
            retailer_name: Name of retailer
            priority_order: List of retailer names in priority order

        Returns:
            Priority index (0 = highest priority)
        """
        try:
            return priority_order.index(retailer_name)
        except ValueError:
            # Not in priority list, put at end
            return len(priority_order)

    def get_stats(self) -> Dict:
        """
        Get statistics about the orchestrator.

        Returns:
            Dict with orchestrator stats
        """
        return {
            'registered_scrapers': self.registry.count(),
            'enabled_scrapers': sum(
                1 for name in self.registry.get_retailer_names()
                if self.config.get('scrapers', {}).get(name, {}).get('enabled', False)
            ),
            'scrapers': self.registry.get_retailer_names(),
            'config': {
                'priority_order': self.config.get('priority_order', []),
                'fallback_enabled': self.config.get('fallback_enabled', True),
                'max_fallback_attempts': self.config.get('max_fallback_attempts', 2)
            }
        }

    def __repr__(self) -> str:
        """String representation"""
        stats = self.get_stats()
        return f"RetailerEnrichmentOrchestrator({stats['enabled_scrapers']}/{stats['registered_scrapers']} scrapers enabled)"
