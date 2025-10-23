"""
Configuration constants for the standardization system.
"""

from pathlib import Path

# Default file paths (relative to project root)
DEFAULT_INPUT_FILE = "output/complete_products.json"
DEFAULT_KEY_ANALYSIS_FILE = "output/key_analysis.json"
DEFAULT_UNIFICATION_MAP_FILE = "output/unification_map.json"
DEFAULT_OUTPUT_FILE = "output/standardized_products.json"


def get_pipeline_paths(input_file: str) -> dict:
    """
    Derive all pipeline file paths from an input file.

    Args:
        input_file: Path to input JSON file (e.g., "output/air-fryers_full.json")

    Returns:
        Dictionary with keys: input, key_analysis, unification_map, output

    Example:
        >>> get_pipeline_paths("output/air-fryers_full.json")
        {
            'input': 'output/air-fryers_full.json',
            'key_analysis': 'output/air-fryers_full.key_analysis.json',
            'unification_map': 'output/air-fryers_full.unification_map.json',
            'output': 'output/air-fryers_full.standardized.json'
        }
    """
    input_path = Path(input_file)
    base_name = input_path.stem  # e.g., "air-fryers_full"
    output_dir = input_path.parent  # e.g., "output"

    return {
        'input': str(input_path),
        'key_analysis': str(output_dir / f"{base_name}.key_analysis.json"),
        'unification_map': str(output_dir / f"{base_name}.unification_map.json"),
        'output': str(output_dir / f"{base_name}.standardized.json"),
    }

# Dynamic unit detection patterns
# Each pattern includes: suffix for the new key, regex pattern, and optional conversion function
UNIT_PATTERNS = {
    'cm': {
        'suffix': '_cm',
        'regex': r'\b(\d+\.?\d*)\s*cm\b',
    },
    'mm': {
        'suffix': '_cm',  # Convert mm to cm
        'regex': r'\b(\d+\.?\d*)\s*mm\b',
        'convert': lambda x: float(x) / 10,
    },
    'kg': {
        'suffix': '_kg',
        'regex': r'\b(\d+\.?\d*)\s*kg\b',
    },
    'g': {
        'suffix': '_g',
        'regex': r'\b(\d+\.?\d*)\s*g\b',
    },
    'rpm': {
        'suffix': '_rpm',
        'regex': r'\b(\d+\.?\d*)\s*rpm\b',
    },
    'kwh': {
        'suffix': '_kwh',
        'regex': r'\b(\d+\.?\d*)\s*kwh\b',
    },
    'watt': {
        'suffix': '_watt',
        'regex': r'\b(\d+\.?\d*)\s*(?:watt|W)\b',
    },
    'db': {
        'suffix': '_db',
        'regex': r'\b(\d+\.?\d*)\s*db\b',
    },
    'mins': {
        'suffix': '_mins',
        'regex': r'\b(\d+\.?\d*)\s*mins?\b',
    },
    'hours': {
        'suffix': '_hours',
        'regex': r'\b(\d+\.?\d*)\s*(?:hours?|h)\b',
    },
    'litres': {
        'suffix': '_litres',
        'regex': r'\b(\d+\.?\d*)\s*(?:litres?|L)\b',
    },
    'm': {
        'suffix': '_m',
        'regex': r'\b(\d+\.?\d*)\s*m\b',
    },
    'v': {
        'suffix': '_v',
        'regex': r'\b(\d+\.?\d*)\s*V\b',
    },
    'hz': {
        'suffix': '_hz',
        'regex': r'\b(\d+\.?\d*)\s*Hz\b',
    },
    'amps': {
        'suffix': '_amps',
        'regex': r'\b(\d+\.?\d*)\s*(?:amps?|A)\b',
    },
    'degrees': {
        'suffix': '_degrees',
        'regex': r'\b(\d+\.?\d*)\s*°\b',
    },
    'percent': {
        'suffix': '_percent',
        'regex': r'\b(\d+\.?\d*)\s*%\b',
    },
    'gbp': {
        'suffix': '_gbp',
        'regex': r'£\s*(\d+\.?\d*)\b',
    },
}

# Common units for validation (units that should be in keys, not values)
COMMON_UNITS = ['cm', 'mm', 'kg', 'g', 'rpm', 'kwh', 'watt', 'db', 'mins', 'hours']

# Unit pattern priority order (most specific first)
# Order matters: try 'kwh' before 'watt', 'mins' before 'm', etc.
UNIT_PATTERN_ORDER = [
    'kwh', 'rpm', 'watt', 'litres', 'hours', 'mins', 'mm', 'cm',
    'kg', 'g', 'db', 'amps', 'degrees', 'percent', 'gbp', 'm', 'v', 'hz'
]
