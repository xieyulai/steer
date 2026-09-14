#!/usr/bin/env bash
# init.sh — 环境检查与目录初始化
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== auto-nn-experiment 环境检查 ==="

python3 -c "import sys; v=sys.version_info; print(f'Python {v.major}.{v.minor}.{v.micro}')"
python3 - <<'PY'
import torch
print(f"torch {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
PY

cd "$ROOT"
mkdir -p _runs/exp


if [ ! -d .git ]; then
    git init
    git add -A
    git commit -m "init: auto-nn-experiment baseline"
    echo "Git 仓库已初始化。"
else
    echo "Git 仓库已存在。"
fi

echo "=== 完成: poetry run python train.py ==="
