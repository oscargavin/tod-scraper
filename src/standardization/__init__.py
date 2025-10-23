"""
Data standardization system for product specifications and features.

This package provides a comprehensive pipeline to standardize product data
from multiple retailer sources using LLM-powered analysis and rule generation.

Category-Agnostic Design:
    Works with ANY product category (air fryers, washing machines, TVs, etc.)
    Automatically derives output filenames from input file names

Main Functions:
    get_pipeline_paths: Derive all pipeline file paths from an input file
    collect_keys: Analyze all spec/feature keys with occurrence counts
    generate_unification_map: Use Gemini to create standardization rules
    standardize_products: Apply rules to create standardized data
    validate_standardization: Validate the standardized output

Usage:
    # Run full pipeline via CLI on any category
    python -m src.standardization.cli --input output/air-fryers_full.json

    # Or use programmatically
    from src.standardization import get_pipeline_paths, standardize_products

    paths = get_pipeline_paths("output/air-fryers_full.json")
    analysis = collect_keys(paths['input'])
    summary = standardize_products(
        paths['input'],
        paths['unification_map'],
        paths['output']
    )
"""

from .analyzer import collect_keys
from .generator import generate_unification_map
from .transformer import standardize_products, standardize_product
from .validator import validate_standardization, validate_product
from .config import get_pipeline_paths

__all__ = [
    'collect_keys',
    'generate_unification_map',
    'standardize_products',
    'standardize_product',
    'validate_standardization',
    'validate_product',
    'get_pipeline_paths',
]
