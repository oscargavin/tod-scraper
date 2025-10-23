"""
Gemini Computer Use wrapper for manufacturer spec scraping.
Simple interface for orchestrator to call.
"""

import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

from src.scrapers.manufacturers.gemini_agent import scrape_product_specs

# Load environment variables (needed for GOOGLE_GENERATIVE_AI_API_KEY)
# Find .env file in project root
env_path = Path(__file__).parent.parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


def scrape_manufacturer_specs(product_name: str) -> Dict[str, Any]:
    """
    Scrape manufacturer specifications using Gemini Computer Use.

    Simple wrapper for orchestrator integration.

    Args:
        product_name: Name of the product to search for

    Returns:
        Dictionary with keys:
            - product: Product name
            - specs: Dict of specifications (or empty dict if failed)
            - source_url: URL where specs were found
            - status: "success" or "failed"
            - error: Error message (if failed)
    """
    return scrape_product_specs(
        product_name=product_name,
        headless=True,
        save_debug_screenshots=True
    )
