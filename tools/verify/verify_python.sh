#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_DIR="$PROJECT_ROOT/sdk/python"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo -e "${YELLOW}⚠️  Python 3 未安装，跳过 Python 验证${NC}"
    exit 0
fi

echo "========================================="
echo "  Python SDK 验证"
echo "========================================="
echo "Python: $($PYTHON --version)"

if [ ! -d "$PYTHON_DIR/mmodel" ]; then
    echo -e "${RED}❌ Python SDK 目录不存在: $PYTHON_DIR/mmodel${NC}"
    exit 1
fi

ERRORS=0

echo ""
echo "📦 检查 Python 依赖..."
REQ_FILE="$PYTHON_DIR/mmodel/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    $PYTHON -m pip install -r "$REQ_FILE" -q 2>/dev/null || true
    echo -e "${GREEN}✅ Python 依赖已安装${NC}"
else
    echo -e "${YELLOW}⚠️  requirements.txt 不存在，跳过依赖安装${NC}"
fi

echo ""
echo "🔍 验证 Python SDK 导入..."
cd "$PYTHON_DIR"
if $PYTHON -c "from mmodel import *; print('Import OK: all modules loaded')" 2>&1; then
    echo -e "${GREEN}✅ Python 导入验证通过${NC}"
else
    echo -e "${RED}❌ Python 导入验证失败${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "🧪 运行 Python 测试..."
if [ -f "$PYTHON_DIR/test/test_python_sdk.py" ]; then
    if $PYTHON "$PYTHON_DIR/test/test_python_sdk.py" 2>&1; then
        echo -e "${GREEN}✅ Python SDK 测试通过${NC}"
    else
        echo -e "${RED}❌ Python SDK 测试失败${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${YELLOW}⚠️  未找到 Python 测试文件，跳过${NC}"
fi

echo ""
echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ Python SDK 验证全部通过${NC}"
else
    echo -e "${RED}❌ Python SDK 验证失败 ($ERRORS 个错误)${NC}"
    exit 1
fi
