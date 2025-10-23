#!/bin/bash

set -e  # Exit on error

echo "========================================"
echo "Data Standardization Pipeline"
echo "========================================"

# Check input file exists
if [ ! -f "output/complete_products.json" ]; then
    echo "Error: output/complete_products.json not found"
    exit 1
fi

# Step 1: Collect keys
echo ""
echo "[1/4] Collecting spec/feature keys..."
python scripts/standardization/collect_keys.py

# Step 2: Generate unification map
echo ""
echo "[2/4] Generating unification map with Gemini..."
python scripts/standardization/generate_unification_map.py

# Step 3: Apply standardization
echo ""
echo "[3/4] Applying standardization..."
python scripts/standardization/apply_standardization.py

# Step 4: Validate
echo ""
echo "[4/4] Validating standardized data..."
python scripts/standardization/validate_standardization.py

echo ""
echo "========================================"
echo "Pipeline complete!"
echo "Output: output/standardized_products.json"
echo "========================================"
