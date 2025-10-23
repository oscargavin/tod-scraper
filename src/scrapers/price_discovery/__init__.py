"""
Price Discovery Module
AI-powered price scraping across retailers
"""

from src.scrapers.price_discovery.price_scraper import (
    scrape_prices_for_product,
    batch_scrape_prices,
)

__all__ = [
    'scrape_prices_for_product',
    'batch_scrape_prices',
]
