#!/usr/bin/env python3
"""
Command-line interface for the data standardization pipeline.
Python replacement for run_full_pipeline.sh with additional features.
"""

import argparse
import json
import sys
from pathlib import Path

from .config import DEFAULT_INPUT_FILE, get_pipeline_paths
from . import analyzer, generator, transformer, validator, value_normalizer, categorizer


def check_input_file(input_file: str) -> bool:
    """Check if input file exists."""
    if not Path(input_file).exists():
        print(f"Error: {input_file} not found")
        print("Please run the scrapers first to generate the input JSON file")
        return False
    return True


def run_pipeline(input_file: str = None, force_regenerate: bool = False, verbose: bool = False,
                  min_coverage_percent: int = 10, min_coverage_filter_percent: float = 10.0,
                  normalize_values: bool = True):
    """
    Run the complete standardization pipeline.

    Args:
        input_file: Path to input products JSON (default: DEFAULT_INPUT_FILE)
        force_regenerate: Force regeneration of unification map even if it exists
        verbose: Enable verbose output
        min_coverage_percent: Minimum coverage % for keys during unification map generation (default: 10%)
        min_coverage_filter_percent: Minimum coverage % to keep fields in final output (default: 10%, 0 = keep all)
        normalize_values: Use Gemini to normalize field values (default: True)
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
        transformer.standardize_products(
            input_file=paths['input'],
            map_file=paths['unification_map'],
            output_file=paths['output'],
            min_coverage_percent=min_coverage_filter_percent
        )

        # Step 3.5: Normalize values (optional)
        if normalize_values:
            print("\n[3.5/5] Normalizing field values with Gemini...")

            # Load standardized data
            with open(paths['output']) as f:
                data = json.load(f)

            # Normalize values
            import copy
            normalized_products, norm_stats = value_normalizer.normalize_all_values(
                data['products'],
                verbose=True
            )

            # Save normalized data
            normalized_data = copy.deepcopy(data)
            normalized_data['products'] = normalized_products

            with open(paths['output'], 'w') as f:
                json.dump(normalized_data, f, indent=2)

            print(f"  Fields normalized: {norm_stats['fields_normalized']}")
            print(f"  Total value changes: {norm_stats['total_value_changes']}")

        # Step 4 or 4.5: Auto-categorize specs vs features
        if normalize_values:
            print("\n[4/6] Auto-categorizing specs vs features...")
        else:
            print("\n[3.5/5] Auto-categorizing specs vs features...")

        categorizer.auto_categorize(paths['output'], verbose=True)

        # Step 5 or 6: Validate
        step_num = "6" if normalize_values else "5"
        print(f"\n[{step_num}/{step_num}] Validating standardized data...")
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
  python -m src.standardization.value_normalizer
  python -m src.standardization.categorizer
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

    parser.add_argument(
        '--min-coverage-filter',
        type=float,
        default=10.0,
        help='Minimum coverage %% to keep fields in final output (default: 10%%, 0 = keep all)'
    )

    parser.add_argument(
        '--no-value-normalization',
        action='store_true',
        help='Skip value normalization step (faster but keeps inconsistencies)'
    )

    args = parser.parse_args()

    run_pipeline(
        input_file=args.input,
        force_regenerate=args.force_regenerate,
        verbose=args.verbose,
        min_coverage_filter_percent=args.min_coverage_filter,
        normalize_values=not args.no_value_normalization
    )


if __name__ == "__main__":
    main()
