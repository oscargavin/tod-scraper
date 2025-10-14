"""
Data standardization system for product specifications and features.

This package provides a comprehensive pipeline to standardize product data
from multiple retailer sources using LLM-powered analysis and rule generation.

Main Functions:
    collect_keys: Analyze all spec/feature keys with occurrence counts
    generate_unification_map: Use Gemini to create standardization rules
    standardize_products: Apply rules to create standardized data
    validate_standardization: Validate the standardized output

Usage:
    # Run full pipeline via CLI
    python -m src.standardization.cli

    # Or use programmatically
    from src.standardization import collect_keys, standardize_products

    analysis = collect_keys("output/complete_products.json")
    summary = standardize_products(
        "output/complete_products.json",
        "output/unification_map.json",
        "output/standardized_products.json"
    )
"""

from .analyzer import collect_keys
from .generator import generate_unification_map
from .transformer import standardize_products, standardize_product
from .validator import validate_standardization, validate_product

__all__ = [
    'collect_keys',
    'generate_unification_map',
    'standardize_products',
    'standardize_product',
    'validate_standardization',
    'validate_product',
]
