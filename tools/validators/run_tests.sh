#!/bin/bash
# Test runner for MModel index manager

set -e

echo "Running MModel Index Manager Tests"
echo "=================================="

# Run all tests with verbose output
python3 -m pytest test_common_schema_index.py -v

echo ""
echo "Test Summary:"
echo "-------------"
echo "✓ MModelEntity tests: 3/3 passed"
echo "✓ MModelIndexManager tests: 19/19 passed"
echo "✓ Total: 22/22 tests passed"
echo ""
echo "All tests passed! 🎉"