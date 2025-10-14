#!/usr/bin/env python3
"""
Test the URL cleaning function with various affiliate link patterns
"""
from urllib.parse import urlparse, parse_qs, unquote
import re

def clean_affiliate_url(url, retailer_name):
    """Python version of the JavaScript cleaning function"""
    try:
        url_obj = urlparse(url)

        # Amazon - remove tracking parameters
        if 'amazon.co.uk' in url_obj.hostname:
            asin_match = re.search(r'/dp/([A-Z0-9]+)', url_obj.path)
            if asin_match:
                return f"https://www.amazon.co.uk/dp/{asin_match.group(1)}"

        # Marks Electrical - extract actual URL from parameters
        if 'markselectrical.co.uk' in url_obj.hostname:
            url_match = re.search(r'url\(([^)]+)\)', url)
            if url_match:
                return unquote(url_match.group(1))

        # Digidip redirect - extract URL parameter
        if 'which.digidip.net' in url_obj.hostname:
            params = parse_qs(url_obj.query)
            if 'url' in params:
                return unquote(params['url'][0])

        # PriceRunner - extract product info
        if 'pricerunner.com' in url_obj.hostname:
            # For now, return as-is since these need to redirect
            return url

        # For other patterns, use retailer domain mapping
        retailer_domains = {
            "AO": "https://ao.com",
            "Currys": "https://www.currys.co.uk",
            "Very": "https://www.very.co.uk",
            "Appliances Direct": "https://www.appliancesdirect.co.uk",
            "Argos": "https://www.argos.co.uk",
            "John Lewis": "https://www.johnlewis.com",
            "Boots Kitchen Appliances": "https://www.boots-kitchen-appliances.co.uk",
            "B and Q": "https://www.diy.com",
            "Dunelm": "https://www.dunelm.com",
            "Lakeland": "https://www.lakeland.co.uk",
            "Robert Dyas": "https://www.robertdyas.co.uk",
            "Ryman UK": "https://www.ryman.co.uk",
            "Wayfair": "https://www.wayfair.co.uk",
            "George at ASDA": "https://direct.asda.com",
            "ASDA Groceries": "https://groceries.asda.com"
        }

        # If it's a redirect service and we have a known domain, return base domain
        if (('clicks.trx-hub.com' in url_obj.hostname or
             'awin1.com' in url_obj.hostname or
             'getsquirrel.co' in url_obj.hostname) and
             retailer_name in retailer_domains):
            return retailer_domains[retailer_name]

        # Otherwise return original URL
        return url

    except Exception as e:
        # If URL parsing fails, return original
        print(f"Error parsing URL: {e}")
        return url

# Test cases from our analysis
test_cases = [
    # Amazon
    {
        "retailer": "Amazon Marketplace UK",
        "url": "https://www.amazon.co.uk/dp/B0F677DTFL?tag=which-squirrel-21&ascsubtag=[URL]&th=1",
        "expected": "https://www.amazon.co.uk/dp/B0F677DTFL"
    },
    # TRX Hub redirects
    {
        "retailer": "AO",
        "url": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D40589010766%26a%3D634144%26m%3D19526",
        "expected": "https://ao.com"
    },
    {
        "retailer": "Currys",
        "url": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D42413881864%26a%3D634144%26m%3D1599",
        "expected": "https://www.currys.co.uk"
    },
    # Marks Electrical
    {
        "retailer": "Marks Electrical",
        "url": "https://visit.markselectrical.co.uk/click?a(3310879)p(327928)product(50555-869991700720)ttid(3)url(https%3A%2F%2Fmarkselectrical.co.uk%2F869991700720_hotpoint-fully-integrated-dishwasher%3Freferrer%3DTradedoubler%26utm_source%3Dtradedoubler%26utm_medium%3Daffiliate%26utm_campaign%3DTradedoubler)",
        "expected": "https://markselectrical.co.uk/869991700720_hotpoint-fully-integrated-dishwasher?referrer=Tradedoubler&utm_source=tradedoubler&utm_medium=affiliate&utm_campaign=Tradedoubler"
    },
    # Digidip redirects
    {
        "retailer": "Appliances Direct",
        "url": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwhich.digidip.net%2Fvisit%3Furl%3Dhttps%253A%252F%252Fwww.appliancesdirect.co.uk%252Fp%252Fhp6ic11bs7la0uk%252Fhotpoint-hp6ic11bs7la0uk-slimline-integrated-dishwasher",
        "expected": "https://www.appliancesdirect.co.uk"  # Since it goes through TRX Hub first
    },
    {
        "retailer": "Ryman UK",
        "url": "https://which.digidip.net/visit?url=https%3A%2F%2Fwww.ryman.co.uk%2Fmorphy-richards-venture-brushed-kettle-grey",
        "expected": "https://www.ryman.co.uk/morphy-richards-venture-brushed-kettle-grey"
    },
    # PriceRunner
    {
        "retailer": "John Lewis",
        "url": "https://www.pricerunner.com/uk/api/frontend-transition-page/gotostore/v1/partner/UK/2952_112049024/price/13831329084",
        "expected": "https://www.pricerunner.com/uk/api/frontend-transition-page/gotostore/v1/partner/UK/2952_112049024/price/13831329084"  # Keep as-is
    },
    # GetSquirrel
    {
        "retailer": "George at ASDA",
        "url": "https://zeta-live.getsquirrel.co/marketplace/96/12877279/1999?click_ref=***",
        "expected": "https://direct.asda.com"
    },
    # Direct links with tracking
    {
        "retailer": "Amazon",
        "url": "https://www.amazon.co.uk/dp/B092RBGQDY?tag=which-squirrel-21&ascsubtag=[URL]&th=1",
        "expected": "https://www.amazon.co.uk/dp/B092RBGQDY"
    },
    # Unknown retailer (should keep original)
    {
        "retailer": "Unknown Store",
        "url": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D12345",
        "expected": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D12345"
    }
]

print("Testing URL Cleaning Function")
print("=" * 80)
print()

passed = 0
failed = 0

for i, test in enumerate(test_cases, 1):
    cleaned_url = clean_affiliate_url(test['url'], test['retailer'])

    if cleaned_url == test['expected']:
        print(f"✓ Test {i}: {test['retailer']}")
        passed += 1
    else:
        print(f"✗ Test {i}: {test['retailer']}")
        failed += 1
        print(f"  Original:  {test['url'][:80]}...")
        print(f"  Expected:  {test['expected']}")
        print(f"  Got:       {cleaned_url}")
    print()

print("=" * 80)
print(f"Summary: {passed} passed, {failed} failed out of {len(test_cases)} tests")

# Additional test for nested digidip URLs
print("\n" + "=" * 80)
print("Testing nested URLs (TRX Hub -> Digidip -> Actual URL)")
print()

# Test the nested digidip case
nested_url = "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwhich.digidip.net%2Fvisit%3Furl%3Dhttps%253A%252F%252Fwww.appliancesdirect.co.uk%252Fp%252Fhp6ic11bs7la0uk%252Fhotpoint-hp6ic11bs7la0uk-slimline-integrated-dishwasher"

# First, extract the 'q' parameter from TRX Hub
parsed = urlparse(nested_url)
params = parse_qs(parsed.query)
if 'q' in params:
    digidip_url = params['q'][0]
    print(f"Step 1 - Extracted from TRX Hub: {digidip_url[:80]}...")

    # Now parse the digidip URL
    if 'which.digidip.net' in digidip_url:
        digidip_parsed = urlparse(digidip_url)
        digidip_params = parse_qs(digidip_parsed.query)
        if 'url' in digidip_params:
            final_url = unquote(digidip_params['url'][0])
            print(f"Step 2 - Extracted from Digidip: {final_url}")
        else:
            print("Step 2 - No URL parameter found in digidip link")