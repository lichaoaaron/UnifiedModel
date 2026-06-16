#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     MModel 生成代码验证（全语言）        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0

run_verify() {
    local name="$1"
    local script="$2"
    TOTAL=$((TOTAL + 1))

    echo ""
    echo -e "${BLUE}━━━ $name ━━━${NC}"

    if bash "$script" 2>&1; then
        PASSED=$((PASSED + 1))
    else
        local exit_code=$?
        if [ $exit_code -eq 0 ]; then
            SKIPPED=$((SKIPPED + 1))
        else
            FAILED=$((FAILED + 1))
        fi
    fi
}

run_verify "Go SDK"     "$SCRIPT_DIR/verify_go.sh"
run_verify "Python SDK" "$SCRIPT_DIR/verify_python.sh"
run_verify "Java SDK"   "$SCRIPT_DIR/verify_java.sh"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                验证报告                   ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  总计:    $TOTAL"
echo -e "  通过:    ${GREEN}$PASSED${NC}"
echo -e "  失败:    ${RED}$FAILED${NC}"
echo -e "  跳过:    ${YELLOW}$SKIPPED${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}❌ 验证未完全通过，请检查上面的错误信息${NC}"
    exit 1
else
    echo -e "${GREEN}✅ 所有验证通过！${NC}"
    exit 0
fi
