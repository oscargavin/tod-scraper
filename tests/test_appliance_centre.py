#!/usr/bin/env python3
"""
Test script for Appliance Centre scraper
Tests extraction logic before integration with orchestrator
"""

import asyncio
from playwright.async_api import async_playwright


async def test_appliance_centre_scraper():
    """Test scraping from Appliance Centre product page"""

    url = "https://www.appliancecentre.co.uk/p/siemens-iq500-wg46h2a9gb-white-9kg-freestanding-washing-machine/"

    print(f"Testing Appliance Centre scraper with URL:\n{url}\n")
    print("="*60)

    async with async_playwright() as p:
        # Launch browser (headless like AO scraper)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # Navigate to product page
        print("├─ Navigating to product page...")
        await page.goto(url, wait_until='networkidle', timeout=60000)
        print("├─ Page loaded")

        # Wait a bit for any dynamic content
        await page.wait_for_timeout(1000)

        # Find and click accordion buttons
        print("├─ Finding accordion sections...")
        accordions = page.locator('.product-accordion')
        accordion_count = await accordions.count()
        print(f"├─ Found {accordion_count} accordion sections")

        # Click each accordion to expand it
        for i in range(accordion_count):
            accordion = accordions.nth(i)
            title_elem = accordion.locator('.title')
            title_text = await title_elem.text_content()
            print(f"│  ├─ Clicking accordion: {title_text.strip()}")

            # Click the title to expand
            await title_elem.click()
            await page.wait_for_timeout(500)  # Wait for animation

        print("├─ All accordions expanded")

        # Extract specifications
        print("├─ Extracting specifications...")

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

                    console.log(`Processing section: ${sectionName}`);

                    // Check if this is the Overview section (has table)
                    const table = body.querySelector('table');
                    if (table) {
                        console.log('Found table in Overview section');
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
                        console.log(`Found ${groupDetails.length} feature groups`);
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

        print("└─ Extraction complete")

        # Print results
        print("\n" + "="*60)
        print("RESULTS")
        print("="*60)
        print(f"\nTotal Specifications: {len(specs)}")
        print("\nSample specifications:")
        for i, (key, value) in enumerate(list(specs.items())[:10]):
            print(f"  {key}: {value}")
        if len(specs) > 10:
            print(f"  ... and {len(specs) - 10} more")

        # Print all specs for verification
        print("\n" + "="*60)
        print("ALL SPECIFICATIONS")
        print("="*60)
        for key, value in sorted(specs.items()):
            print(f"  {key}: {value}")

        # Close browser
        await browser.close()

        return {
            'specs': specs,
            'success': len(specs) > 0
        }


if __name__ == '__main__':
    result = asyncio.run(test_appliance_centre_scraper())
    print("\n" + "="*60)
    print(f"Success: {result['success']}")
    print(f"Specs extracted: {len(result['specs'])}")
