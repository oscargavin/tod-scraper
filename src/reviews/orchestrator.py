#!/usr/bin/env python3
"""
Review Enrichment Orchestrator
Intelligently selects and applies review enrichment from AO, Boots, or Amazon
"""
from typing import Dict, List, Optional
from src.reviews.ao.sentiment_scraper import get_sentiment_analysis as get_ao_sentiment
from src.reviews.ao.search import search_and_extract
from src.reviews.ao.enricher import extract_search_terms
from src.reviews.boots.sentiment_scraper import get_sentiment_analysis as get_boots_sentiment
from src.reviews.amazon.sentiment_scraper import get_sentiment_analysis as get_amazon_sentiment
from src.reviews.utils import calculate_tod_score


class ReviewEnrichmentOrchestrator:
    """
    Orchestrates review enrichment with intelligent source selection.
    Priority: AO (search-based) > Boots (URL-based) > Amazon (URL-based)
    """

    @staticmethod
    def has_retailer(product: Dict, retailer_names: List[str]) -> bool:
        """Check if product has a specific retailer by name"""
        retailer_links = product.get('retailerLinks', [])
        for link in retailer_links:
            name = link.get('name', '').lower()
            for retailer in retailer_names:
                if retailer.lower() in name:
                    return True
        return False

    @staticmethod
    def find_retailer_url(product: Dict, retailer_names: List[str]) -> Optional[str]:
        """Find direct URL for a retailer (for Boots)"""
        retailer_links = product.get('retailerLinks', [])
        for link in retailer_links:
            name = link.get('name', '').lower()
            url = link.get('url', '').lower()
            for retailer in retailer_names:
                retailer_lower = retailer.lower()
                if retailer_lower in name or retailer_lower in url:
                    return link.get('url')
        return None

    async def enrich_product(self, product: Dict, page=None) -> Dict:
        """
        Enrich product with reviews from best available source.

        Priority:
        1. AO (search-based using product name - EXACT same approach as old enricher)
        2. Boots (direct URL from retailerLinks)
        3. Amazon (direct URL from retailerLinks - uses Amazon's AI summary)
        4. None (no enrichment)

        Returns:
            Product dict with 'reviews' field added if successful
        """
        product_name = product.get('name', 'Unknown')

        # Try AO first (EXACT same approach as old ao_review_enricher.py)
        if self.has_retailer(product, ['ao', 'ao.com']):
            try:
                # Extract search terms from product name (SAME as old enricher)
                search_query, target_model = extract_search_terms(product_name)

                # Search and extract (SAME as old enricher)
                result = await search_and_extract(
                    search_query=search_query,
                    target_product=target_model,
                    silent=True,
                    page=page
                )

                if result['success'] and result.get('ao_url'):
                    # Get sentiment from the found AO product page
                    sentiment = await get_ao_sentiment(result['ao_url'], max_pages=4)

                    # Only add if we actually got reviews
                    if sentiment.get('summary') != 'No reviews found for analysis':
                        # Calculate TOD score from rating and count
                        tod_score = calculate_tod_score(
                            sentiment.get('rating'),
                            sentiment.get('count')
                        )

                        product['reviews'] = {
                            'summary': sentiment['summary'],
                            'pros': sentiment['pros'],
                            'cons': sentiment['cons'],
                            'todScore': tod_score
                        }
                        return product

            except Exception as e:
                print(f"  ⚠ AO search failed for {product_name[:40]}: {str(e)[:50]}")

        # Fallback to Boots (direct URL approach)
        boots_url = self.find_retailer_url(product, ['boots', 'boots.com'])
        if boots_url:
            try:
                sentiment = await get_boots_sentiment(boots_url)
                if sentiment.get('summary') != 'No reviews found for analysis':
                    # Calculate TOD score from rating and count
                    tod_score = calculate_tod_score(
                        sentiment.get('rating'),
                        sentiment.get('count')
                    )

                    product['reviews'] = {
                        'summary': sentiment['summary'],
                        'pros': sentiment['pros'],
                        'cons': sentiment['cons'],
                        'todScore': tod_score
                    }
                    return product
            except Exception as e:
                print(f"  ⚠ Boots enrichment failed for {product_name[:40]}: {str(e)[:50]}")

        # Fallback to Amazon (uses Amazon's existing AI summary)
        amazon_url = self.find_retailer_url(product, ['amazon', 'amazon.co.uk'])
        if amazon_url:
            try:
                sentiment = await get_amazon_sentiment(amazon_url)
                if sentiment.get('summary') != 'No reviews found for analysis':
                    # Calculate TOD score from rating and count
                    tod_score = calculate_tod_score(
                        sentiment.get('rating'),
                        sentiment.get('count')
                    )

                    product['reviews'] = {
                        'summary': sentiment['summary'],
                        'pros': sentiment['pros'],
                        'cons': sentiment['cons'],
                        'todScore': tod_score
                    }
                    return product
            except Exception as e:
                print(f"  ⚠ Amazon enrichment failed for {product_name[:40]}: {str(e)[:50]}")

        # No enrichment available
        return product

    def get_stats(self) -> Dict:
        """Get orchestrator statistics"""
        return {
            'available_sources': ['AO', 'Boots', 'Amazon'],
            'priority_order': ['AO', 'Boots', 'Amazon'],
            'enabled': True
        }
