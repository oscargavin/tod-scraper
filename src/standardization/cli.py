#!/usr/bin/env python3
"""
Command-line interface for the data standardization pipeline.
Python replacement for run_full_pipeline.sh with additional features.
"""

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_INPUT_FILE
from . import analyzer, generator, transformer, validator


def check_input_file(input_file: str) -> bool:
    """Check if input file exists."""
    if not Path(input_file).exists():
        print(f"Error: {input_file} not found")
        print("Please run the scrapers first to generate complete_products.json")
        return False
    return True


def run_pipeline(force_regenerate: bool = False, verbose: bool = False):
    """
    Run the complete standardization pipeline.

    Args:
        force_regenerate: Force regeneration of unification map even if it exists
        verbose: Enable verbose output
    """
    print("=" * 60)
    print("Data Standardization Pipeline")
    print("=" * 60)

    # Check input file exists
    if not check_input_file(DEFAULT_INPUT_FILE):
        sys.exit(1)

    try:
        # Step 1: Collect keys
        print("\n[1/4] Collecting spec/feature keys...")
        analyzer.main()

        # Step 2: Generate unification map
        print("\n[2/4] Generating unification map with Gemini...")
        generator.main()

        # Step 3: Apply standardization
        print("\n[3/4] Applying standardization...")
        transformer.main()

        # Step 4: Validate
        print("\n[4/4] Validating standardized data...")
        validator.main()

        print("\n" + "=" * 60)
        print("Pipeline complete!")
        print("Output: output/standardized_products.json")
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
  # Run full pipeline
  python -m src.standardization.cli
  python src/standardization/cli.py

  # Run with verbose output
  python -m src.standardization.cli --verbose

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
        force_regenerate=args.force_regenerate,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
