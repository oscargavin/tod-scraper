#!/usr/bin/env python3
"""
Command-line interface for the data standardization pipeline.
Python replacement for run_full_pipeline.sh with additional features.
"""

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_INPUT_FILE, get_pipeline_paths
from . import analyzer, generator, transformer, validator


def check_input_file(input_file: str) -> bool:
    """Check if input file exists."""
    if not Path(input_file).exists():
        print(f"Error: {input_file} not found")
        print("Please run the scrapers first to generate the input JSON file")
        return False
    return True


def run_pipeline(input_file: str = None, force_regenerate: bool = False, verbose: bool = False, min_coverage_percent: int = 10):
    """
    Run the complete standardization pipeline.

    Args:
        input_file: Path to input products JSON (default: DEFAULT_INPUT_FILE)
        force_regenerate: Force regeneration of unification map even if it exists
        verbose: Enable verbose output
        min_coverage_percent: Minimum coverage % for keys to include (default: 10%)
    """
    # Use default if not specified
    input_file = input_file or DEFAULT_INPUT_FILE

    # Derive all pipeline paths from input file
    paths = get_pipeline_paths(input_file)

    print("=" * 60)
    print("Data Standardization Pipeline")
    print("=" * 60)
    print(f"Input: {paths['input']}")
    print(f"Output: {paths['output']}")

    # Check input file exists
    if not check_input_file(paths['input']):
        sys.exit(1)

    try:
        # Step 1: Collect keys
        print("\n[1/4] Collecting spec/feature keys...")
        analyzer.main(
            input_file=paths['input'],
            output_file=paths['key_analysis']
        )

        # Step 2: Generate unification map
        print("\n[2/4] Generating unification map with Gemini...")
        generator.main(
            analysis_file=paths['key_analysis'],
            output_file=paths['unification_map'],
            min_coverage_percent=min_coverage_percent
        )

        # Step 3: Apply standardization
        print("\n[3/4] Applying standardization...")
        transformer.main(
            input_file=paths['input'],
            map_file=paths['unification_map'],
            output_file=paths['output']
        )

        # Step 4: Validate
        print("\n[4/4] Validating standardized data...")
        validator.main(input_file=paths['output'])

        print("\n" + "=" * 60)
        print("Pipeline complete!")
        print(f"Output: {paths['output']}")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during pipeline execution: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Data standardization pipeline for product specs/features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline on default file (complete_products.json)
  python -m src.standardization.cli
  python src/standardization/cli.py

  # Run on a specific category file
  python -m src.standardization.cli --input output/air-fryers_full.json

  # Run with verbose output
  python -m src.standardization.cli --verbose --input output/air-fryers_full.json

  # Force regeneration of unification map
  python -m src.standardization.cli --force-regenerate

Individual steps:
  python -m src.standardization.analyzer
  python -m src.standardization.generator
  python -m src.standardization.transformer
  python -m src.standardization.validator
        """
    )

    parser.add_argument(
        '--input', '-i',
        type=str,
        default=None,
        help=f'Path to input products JSON file (default: {DEFAULT_INPUT_FILE})'
    )

    parser.add_argument(
        '--force-regenerate',
        action='store_true',
        help='Force regeneration of unification map even if it exists'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    run_pipeline(
        input_file=args.input,
        force_regenerate=args.force_regenerate,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
