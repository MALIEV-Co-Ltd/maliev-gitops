#!/usr/bin/env bash
# Script to lint only base deployment files with kube-linter
# Used by pre-commit hook and can be run manually

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Linting base deployment files with kube-linter..."

# Check if kube-linter is installed
if ! command -v kube-linter &> /dev/null; then
    echo -e "${YELLOW}⚠️  kube-linter not installed${NC}"
    echo "Install from: https://github.com/stackrox/kube-linter#installing-kubelinter"
    echo "Or use Docker: docker run -v \$(pwd):/src stackrox/kube-linter lint ..."
    exit 0  # Don't fail the commit, just warn
fi

# Find all base deployment files
DEPLOYMENT_FILES=$(find 3-apps -name "deployment.yaml" -path "*/base/*" 2>/dev/null)

if [ -z "$DEPLOYMENT_FILES" ]; then
    echo -e "${YELLOW}⚠️  No base deployment files found${NC}"
    exit 0
fi

# Count files
FILE_COUNT=$(echo "$DEPLOYMENT_FILES" | wc -l)
echo "Found $FILE_COUNT base deployment files to lint"

# Run kube-linter
if echo "$DEPLOYMENT_FILES" | xargs kube-linter lint --config .kube-linter.yml; then
    echo -e "${GREEN}✅ All base deployments passed kube-linter checks${NC}"
    exit 0
else
    echo -e "${RED}❌ Kube-linter found issues in base deployments${NC}"
    echo ""
    echo "Fix the issues above before committing."
    echo "Or run: ./scripts/lint-base-deployments.sh to see details"
    exit 1
fi
