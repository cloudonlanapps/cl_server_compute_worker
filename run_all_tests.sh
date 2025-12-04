#!/bin/bash

# Activate venv
source .venv/bin/activate

echo "=== Running Main Worker Tests ==="
python -m pytest tests/ -v --tb=short
WORKER_EXIT=$?

# Clear caches between test runs
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null

echo ""
echo "=== Running Image Conversion Tests ==="
python -m pytest compute_modules/image_conversion/tests/test_image_conversion_task.py -v --tb=short
CONVERSION_EXIT=$?

# Clear caches between test runs
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null

echo ""
echo "=== Running Image Resize Tests ==="
python -m pytest compute_modules/image_resize/tests/test_image_resize_task.py -v --tb=short
RESIZE_EXIT=$?

# Summary
echo ""
echo "====== TEST SUMMARY ======"
echo "Worker Tests: $([ $WORKER_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo "Image Conversion Tests: $([ $CONVERSION_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
echo "Image Resize Tests: $([ $RESIZE_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"

# Exit with failure if any test failed
exit $(( $WORKER_EXIT + $CONVERSION_EXIT + $RESIZE_EXIT ))
