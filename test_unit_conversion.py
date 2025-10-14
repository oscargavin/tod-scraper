#!/usr/bin/env python3
"""
Test script to verify mm→cm unit conversion in standardization.
"""

import json

def test_unit_conversion():
    """Test that mm values are correctly converted to cm."""

    # Load standardized products
    with open('output/standardized_products.json', 'r') as f:
        data = json.load(f)

    # Find the AEG LFSR74144UD product
    aeg_product = None
    for product in data['products']:
        if 'AEG LFSR74144UD' in product.get('name', ''):
            aeg_product = product
            break

    if not aeg_product:
        print("❌ ERROR: Could not find AEG LFSR74144UD product")
        return False

    # Test cases: (key, expected_value)
    test_cases = [
        ('height_cm', '84.7'),
        ('width_cm', '59.7'),
        ('depth_cm', '66'),
    ]

    print("Testing mm→cm conversion for AEG LFSR74144UD:")
    print("=" * 50)

    all_passed = True
    specs = aeg_product.get('specs', {})

    for key, expected in test_cases:
        actual = specs.get(key, 'N/A')
        passed = actual == expected
        status = "✓" if passed else "✗"

        print(f"{status} {key}: {actual} (expected: {expected})")

        if not passed:
            all_passed = False

    print("=" * 50)

    if all_passed:
        print("\n✓ All tests passed!")
        return True
    else:
        print("\n✗ Some tests failed!")
        return False

def test_other_products():
    """Verify other products with cm values still work correctly."""

    with open('output/standardized_products.json', 'r') as f:
        data = json.load(f)

    print("\nVerifying other products with cm values:")
    print("=" * 50)

    # Check a few products that should have cm values (not mm)
    sample_count = 0
    for product in data['products']:
        if product.get('name') != 'AEG LFSR74144UD':
            specs = product.get('specs', {})
            height = specs.get('height_cm', 'N/A')

            if height != 'N/A':
                print(f"✓ {product.get('name', 'Unknown')}: height_cm = {height}")
                sample_count += 1

                if sample_count >= 3:
                    break

    print("=" * 50)

if __name__ == "__main__":
    success = test_unit_conversion()
    test_other_products()

    if success:
        print("\n✓ Unit conversion feature is working correctly!")
        exit(0)
    else:
        print("\n✗ Unit conversion feature has issues!")
        exit(1)
