#!/usr/bin/env python3
"""
Test the orchestrator with Appliance Centre scraper integration
"""

import asyncio
from playwright.async_api import async_playwright
from retailer_enrichment_orchestrator import RetailerEnrichmentOrchestrator


async def test_orchestrator_with_appliance_centre():
    """Test that orchestrator can find and use Appliance Centre scraper"""

    # Create a mock product with Appliance Centre retailer link
    product = {
        'name': 'Siemens iQ500 WG46H2A9GB White 9kg Freestanding Washing Machine',
        'whichUrl': 'https://www.which.co.uk/reviews/washing-machines/article/...',
        'specs': {},
        'retailerLinks': [
            {
                'name': 'Appliance Centre',
                'url': 'https://www.appliancecentre.co.uk/p/siemens-iq500-wg46h2a9gb-white-9kg-freestanding-washing-machine/',
                'price': '£699'
            }
        ]
    }

    print("Testing RetailerEnrichmentOrchestrator with Appliance Centre")
    print("="*60)

    # Initialize orchestrator
    orchestrator = RetailerEnrichmentOrchestrator()

    # Print orchestrator stats
    stats = orchestrator.get_stats()
    print(f"\n{orchestrator}")
    print(f"Registered scrapers: {stats['scrapers']}")
    print(f"Priority order: {stats['config']['priority_order']}")

    print("\n" + "="*60)
    print("Enriching product...")
    print("="*60)

    # Launch browser and enrich product
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # Enrich the product
        enriched_product, enrichment_stats = await orchestrator.enrich_product(product, page)

        await browser.close()

    # Print results
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"\nEnrichment successful: {enrichment_stats['success']}")
    print(f"Source: {enrichment_stats.get('source', 'N/A')}")
    print(f"Specs extracted: {enrichment_stats.get('spec_count', 0)}")
    print(f"Quality score: {enrichment_stats.get('quality_score', 0):.2f}")

    if enrichment_stats['success']:
        print(f"\nSample specs from enriched product:")
        for i, (key, value) in enumerate(list(enriched_product['specs'].items())[:10]):
            print(f"  {key}: {value}")
        if len(enriched_product['specs']) > 10:
            print(f"  ... and {len(enriched_product['specs']) - 10} more")

        print(f"\nRetailer enrichment URL: {enriched_product.get('retailerEnrichmentUrl', 'N/A')}")
        print(f"Retailer enrichment source: {enriched_product.get('retailerEnrichmentSource', 'N/A')}")
    else:
        print(f"\nReason: {enrichment_stats.get('reason', 'Unknown')}")
        print(f"Attempts: {enrichment_stats.get('attempts', [])}")


if __name__ == '__main__':
    asyncio.run(test_orchestrator_with_appliance_centre())
