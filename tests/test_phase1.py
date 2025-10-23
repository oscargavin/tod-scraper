#!/usr/bin/env python3
"""Quick test that Phase 1 migration worked"""

import asyncio
from playwright.async_api import async_playwright
from src.scrapers.retailers.orchestrator import RetailerEnrichmentOrchestrator

async def test_phase1():
    """Test retailer orchestrator in new location"""

    product = {
        'name': 'Test Product',
        'retailerLinks': [
            {
                'name': 'Appliance Centre',
                'url': 'https://www.appliancecentre.co.uk/p/siemens-iq500-wg46h2a9gb-white-9kg-freestanding-washing-machine/',
                'price': '£699'
            }
        ]
    }

    print("Testing Phase 1: Retailer Scrapers in new location")
    print("="*60)

    orchestrator = RetailerEnrichmentOrchestrator()
    stats = orchestrator.get_stats()

    print(f"✓ Orchestrator loaded successfully")
    print(f"✓ Registered scrapers: {stats['scrapers']}")
    print(f"✓ Config loaded from: config/retailer_config.json")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        enriched, enrichment_stats = await orchestrator.enrich_product(product, page)

        await browser.close()

    if enrichment_stats['success']:
        print(f"✓ Scraping test passed")
        print(f"  Source: {enrichment_stats['source']}")
        print(f"  Specs: {enrichment_stats['spec_count']}")
        print("\n✅ Phase 1 migration successful!")
        return True
    else:
        print(f"✗ Scraping test failed: {enrichment_stats.get('reason')}")
        return False

if __name__ == '__main__':
    success = asyncio.run(test_phase1())
    exit(0 if success else 1)
