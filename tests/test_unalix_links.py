#!/usr/bin/env python3
"""
Test Unalix on various affiliate link patterns from Which.com
"""
import unalix
import json
from datetime import datetime

# Test links from the examples provided
test_links = [
    # Amazon - should clean tracking parameters
    {
        "retailer": "Amazon",
        "original": "https://www.amazon.co.uk/dp/B0CQKCG1T2?tag=which-squirrel-21&ascsubtag=[URL]&th=1"
    },
    {
        "retailer": "Amazon Marketplace UK",
        "original": "https://www.amazon.co.uk/dp/B0DVZQCWY8?tag=which1-21&linkCode=ogi&th=1&psc=1"
    },

    # TRX Hub redirects - should follow and resolve
    {
        "retailer": "B and Q",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fdiy.pxf.io%2Fc%2F3065153%2F2194679%2F18948%3Fprodsku%3D5011832074652%26u%3Dhttps%3A%2F%2Fwww.diy.com%2Fdepartments%2Ftower-heritage-3kw-pyramid-kettle-dome-white%2F5011832074652_BQ.prd&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fmorphy-richards-venture-100130&event_type=click&userid=&clickid=2ad46b45-b42b-4e2e-8d5e-bcebe853f8f5&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Morphy+Richards+Venture+100130&product_id=WH12085-0173-00&productprice=59.99"
    },
    {
        "retailer": "AO",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D39307971600%26a%3D634144%26m%3D19526&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fmorphy-richards-venture-100130&event_type=click&userid=&clickid=02fb8577-1bb4-43f7-b3f0-0a60b0f45a2f&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Morphy+Richards+Venture+100130&product_id=WH12085-0173-00&productprice=59.99"
    },
    {
        "retailer": "Very",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D41678118280%26a%3D634144%26m%3D3090&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fdelonghi-ballerina-seta-kbds3001-bl&event_type=click&userid=&clickid=f9fb0f61-83a6-4b71-8e03-8dadb8dd7ac1&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=DeLonghi+Ballerina+Seta+KBDS3001.BL&product_id=WH12085-0176-00&productprice=59.99"
    },
    {
        "retailer": "Currys",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D39641778865%26a%3D634144%26m%3D1599&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Ftower-heritage-t10076wht&event_type=click&userid=&clickid=6b5f4540-c4e5-4edd-9c69-fc0c3b4b41f4&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Tower+Heritage+T10076WHT&product_id=WH12085-0177-00&productprice=44.99"
    },

    # GetSquirrel redirects
    {
        "retailer": "George at ASDA",
        "original": "https://zeta-live.getsquirrel.co/marketplace/96/12877279/1999?click_ref=***"
    },
    {
        "retailer": "Morphy Richards UK",
        "original": "https://zeta-live.getsquirrel.co/marketplace/96/12877279/210?click_ref=***"
    },

    # Marks Electrical - has URL in parameters
    {
        "retailer": "Marks Electrical",
        "original": "https://visit.markselectrical.co.uk/click?a(3310879)p(327928)product(50555-100130)ttid(3)url(https%3A%2F%2Fmarkselectrical.co.uk%2F100130_morphy-richards-pyramid-kettle%3Freferrer%3DTradedoubler%26utm_source%3Dtradedoubler%26utm_medium%3Daffiliate%26utm_campaign%3DTradedoubler)"
    },

    # Nested redirects (TRX Hub -> Digidip -> actual URL)
    {
        "retailer": "Ryman UK (nested)",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwhich.digidip.net%2Fvisit%3Furl%3Dhttps%3A%2F%2Fwww.ryman.co.uk%2Fmorphy-richards-venture-brushed-stainless-steel-pyramid-kettle-2%3F%2526https%3A%2F%2Fwww.ryman.co.uk%2Fmorphy-richards-venture-brushed-stainless-steel-pyramid-kettle-2%26utm_source%3D!!!sitename!!!_!!!promotype!!!%26utm_medium%3Daffiliates%26utm_content%3Dsite_link%26utm_campaign%3Dproduct_feed&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fmorphy-richards-venture-100130&event_type=click&userid=&clickid=cc82c8d5-8e73-4b03-ae20-86e456e43494&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Morphy+Richards+Venture+100130&product_id=WH12085-0173-00&productprice=59.99"
    },
    {
        "retailer": "Wayfair (nested)",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwhich.digidip.net%2Fvisit%3Furl%3Dhttps%3A%2F%2Fwww.wayfair.co.uk%2FTower--Tower-Heritage-Dome-Kettle-with-Rapid-Boil-1.7L-3000W-Optic-White-with-Chrome-Accents-T10076WHT-L1070-K~SBSF1838.html&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Ftower-heritage-t10076wht&event_type=click&userid=&clickid=82bbef5e-4a60-4cb6-a4d0-7c3b00a5cbec&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Tower+Heritage+T10076WHT&product_id=WH12085-0177-00&productprice=44.99"
    },

    # Other patterns
    {
        "retailer": "Downtown Stores",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fdowntownstores.pxf.io%2Fc%2F3065153%2F1891674%2F22610%3Fprodsku%3D9001527525%26u%3Dhttps%3A%2F%2Fwww.downtownstores.co.uk%2Fmorphy-richards-100130-15l-venture-pyramid-rapid-boil-kettle-brushed-stainless-steel%2Fp67816%3Fcv%3D229144%26intsrc%3DCATF_15273&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fmorphy-richards-venture-100130&event_type=click&userid=&clickid=819a7542-6b96-4145-8f34-0d34ce315fa6&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Morphy+Richards+Venture+100130&product_id=WH12085-0173-00&productprice=59.99"
    },
    {
        "retailer": "Sonic Direct",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D41213274404%26a%3D634144%26m%3D5363&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Fmorphy-richards-venture-100130&event_type=click&userid=&clickid=323bb8af-d6c1-4075-85ad-4bd1d6b9476e&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Morphy+Richards+Venture+100130&product_id=WH12085-0173-00&productprice=59.99"
    },
    {
        "retailer": "Lakeland",
        "original": "https://clicks.trx-hub.com/xid/which_c9990_which?q=https%3A%2F%2Fwww.awin1.com%2Fpclick.php%3Fp%3D40097467677%26a%3D634144%26m%3D1712&p=https%3A%2F%2Fwww.which.co.uk%2Freviews%2Fkettles%2Flakeland-27578&event_type=click&userid=&clickid=4dd29a83-58f2-46d5-a0f9-9e1c37e37cd5&content_type=product+page&vertical=appliances&sub_vertical=kettles-and-coffee-makers&category=kettles&super_category=&platform=web&item_group=Lowest+Available+Prices&product_name=Lakeland+27578&product_id=WH12085-0179-00&productprice=27.99"
    }
]

def test_unalix():
    """Test both clear_url and unshort_url functions"""
    results = []

    for test in test_links:
        result = {
            "retailer": test["retailer"],
            "original": test["original"]
        }

        try:
            # Try clear_url first (removes tracking parameters)
            cleared = unalix.clear_url(test["original"])
            result["clear_url"] = cleared
            result["clear_changed"] = cleared != test["original"]

            # Try unshort_url (follows redirects + removes tracking)
            print(f"\nProcessing {test['retailer']}...")
            unshorted = unalix.unshort_url(test["original"])
            result["unshort_url"] = unshorted
            result["unshort_changed"] = unshorted != test["original"]

            # Determine which method worked better
            if result["unshort_changed"] and result["unshort_url"] != result["clear_url"]:
                result["best_method"] = "unshort_url"
                result["final_url"] = result["unshort_url"]
            elif result["clear_changed"]:
                result["best_method"] = "clear_url"
                result["final_url"] = result["clear_url"]
            else:
                result["best_method"] = "none"
                result["final_url"] = test["original"]

        except Exception as e:
            result["error"] = str(e)
            result["final_url"] = test["original"]

        results.append(result)

    return results

# Run the test
print("Testing Unalix on affiliate links...")
print("="*80)

results = test_unalix()

# Save results to file
output_data = {
    "timestamp": datetime.now().isoformat(),
    "total_links": len(results),
    "results": results
}

with open('unalix_test_results.json', 'w') as f:
    json.dump(output_data, f, indent=2)

# Generate HTML report for easy clicking
html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Unalix Test Results - {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .success {{ color: green; font-weight: bold; }}
        .failed {{ color: red; }}
        .url {{ word-break: break-all; font-size: 12px; }}
        .method {{ font-weight: bold; }}
        a {{ color: blue; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <h1>Unalix URL Cleaning Test Results</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Click any cleaned URL to test if it works!</p>

    <table>
        <tr>
            <th>Retailer</th>
            <th>Best Method</th>
            <th>Original URL</th>
            <th>Cleaned URL</th>
            <th>Status</th>
        </tr>
"""

for result in results:
    status = "✓ Cleaned" if result.get("final_url") != result["original"] else "✗ Failed"
    status_class = "success" if result.get("final_url") != result["original"] else "failed"
    method = result.get("best_method", "error")

    html_content += f"""
        <tr>
            <td>{result['retailer']}</td>
            <td class="method">{method}</td>
            <td class="url">{result['original'][:80]}...</td>
            <td class="url">
                <a href="{result.get('final_url', result['original'])}" target="_blank">
                    {result.get('final_url', result['original'])}
                </a>
            </td>
            <td class="{status_class}">{status}</td>
        </tr>
    """

html_content += """
    </table>

    <h2>Summary</h2>
    <ul>
"""

# Add summary statistics
total = len(results)
cleaned = sum(1 for r in results if r.get("final_url") != r["original"])
clear_url_wins = sum(1 for r in results if r.get("best_method") == "clear_url")
unshort_url_wins = sum(1 for r in results if r.get("best_method") == "unshort_url")

html_content += f"""
        <li>Total URLs tested: {total}</li>
        <li>Successfully cleaned: {cleaned} ({cleaned/total*100:.1f}%)</li>
        <li>Best with clear_url: {clear_url_wins}</li>
        <li>Best with unshort_url: {unshort_url_wins}</li>
        <li>Failed to clean: {total - cleaned}</li>
    </ul>
</body>
</html>
"""

with open('unalix_test_results.html', 'w') as f:
    f.write(html_content)

# Print summary
print("\nSummary:")
print(f"Total links tested: {total}")
print(f"Successfully cleaned: {cleaned} ({cleaned/total*100:.1f}%)")
print(f"Best with clear_url: {clear_url_wins}")
print(f"Best with unshort_url: {unshort_url_wins}")
print(f"Failed to clean: {total - cleaned}")

print("\n✓ Results saved to:")
print("  - unalix_test_results.json (detailed data)")
print("  - unalix_test_results.html (clickable links)")

# Show some examples
print("\n" + "="*80)
print("Example Results:")
for result in results[:5]:
    print(f"\n{result['retailer']}:")
    print(f"  Original: {result['original'][:80]}...")
    print(f"  Cleaned:  {result.get('final_url', 'FAILED')[:80]}...")
    if result.get('error'):
        print(f"  Error: {result['error']}")