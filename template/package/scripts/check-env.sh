#!/usr/bin/env bash
# check-env.sh — Python / Poetry / torch / CUDA / GPU 名单 就绪检查
#
# 换机、git clone、新同事接手后：在 auto-run / smoke 之前先跑本脚本。
# .venv 不入库；须 poetry install。有 ~/.gpus 时开训必须落在名单内；没建该文件不限制占用。
#
# 用法（项目根）:
#   bash scripts/check-env.sh
#   bash scripts/check-env.sh --quiet          # 仅 FAIL/WARN；供 nn-doctor
#   bash scripts/check-env.sh --snapshot       # 成功时打印 torch 快照（auto-run 缓存用）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

QUIET=0
SNAPSHOT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    --snapshot) SNAPSHOT=1; shift ;;
    -h|--help)
      cat <<'EOF'
用法: bash scripts/check-env.sh [--quiet] [--snapshot]

检查 Poetry 虚拟环境、torch、CUDA、家目录 ~/.gpus（有则收紧）与 nn-config GPU 名单是否就绪。
FAIL 时打印修复命令（常见：换机后 poetry install）及换源 / 复用本机环境提示。

  --quiet    仅输出 FAIL/WARN
  --snapshot 成功时在 stdout 打印 torch/CUDA 快照（供 auto-nn-run 缓存）
EOF
      exit 0
      ;;
    *) echo "[check-env] 未知参数: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
WARN=0

log_ok() {
  [[ $QUIET -eq 0 ]] && echo "[check-env] OK: $*"
  return 0
}
log_warn() {
  WARN=$((WARN + 1))
  echo "[check-env] WARN: $*" >&2
}
log_fail() {
  FAIL=$((FAIL + 1))
  echo "[check-env] FAIL: $*" >&2
}

hint_install_slow_and_local() {
  cat >&2 <<'EOF'
  ── 安装很慢 / 超时？可先换源再装 ──
  Poetry 拉 PyPI（当前终端有效）:
    export POETRY_PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
  pip 镜像（装 poetry / 部分依赖）:
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple poetry
  可选: poetry config installer.max-workers 4
  PyTorch 体积大: 见 pyproject.toml 的 [[tool.poetry.source]]（须与 CUDA 匹配）
    可加长超时: POETRY_HTTP_TIMEOUT=600 poetry install
    官方 wheel: https://download.pytorch.org/whl/

  ── 先看本机是否已有环境（避免重复下载）──
  1) 系统 Python 是否已有 torch:
       python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
     若版本合适 → 让 Poetry 复用该解释器:
       poetry env use "$(which python3)" && poetry install
  2) 本项目是否已有 Poetry 虚拟环境:
       poetry env list
     选对解释器: poetry env use <路径>  或  poetry env remove python 后重装
  3) 希望 venv 在项目内 .venv/:
       poetry config virtualenvs.in-project true && poetry install
EOF
  if command -v poetry >/dev/null 2>&1; then
    _pel="$(poetry env list 2>/dev/null | head -5 || true)"
    if [[ -n "$_pel" ]]; then
      echo "  当前 poetry env list:" >&2
      echo "$_pel" | sed 's/^/    /' >&2
    fi
  fi
  if command -v python3 >/dev/null 2>&1; then
    _st="$(python3 -c "import torch; print(torch.__version__)" 2>/dev/null || true)"
    if [[ -n "$_st" ]]; then
      echo "  检测到系统 python3 已装 torch ${_st}（可用 poetry env use 复用）" >&2
    fi
  fi
  if [[ -d "$ROOT/.venv" ]]; then
    echo "  检测到 $ROOT/.venv 目录（可 poetry config virtualenvs.in-project true && poetry install）" >&2
  fi
}

hint_poetry_install() {
  cat >&2 <<EOF
  原因: .venv 不在 git 里；换机 / clone 后须重装依赖
  修复: cd "$ROOT" && poetry install
  验证: poetry run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
EOF
  hint_install_slow_and_local
}

# ── 1. Python ──
if ! command -v python3 >/dev/null 2>&1; then
  log_fail "未找到 python3"
  echo "  修复: 安装 Python 3.10+（见 pyproject.toml）" >&2
else
  _py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  _py_ok="$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')"
  if [[ "$_py_ok" != "1" ]]; then
    log_fail "Python $_py_ver 过低（需要 >= 3.10）"
  else
    log_ok "Python $_py_ver"
  fi
fi

# ── 2. Poetry + pyproject ──
if [[ ! -f pyproject.toml ]]; then
  log_fail "缺少 pyproject.toml"
else
  log_ok "pyproject.toml 存在"
fi

if ! command -v poetry >/dev/null 2>&1; then
  log_fail "未找到 poetry（项目依赖通过 Poetry 管理）"
  echo "  修复: pip install poetry  或见 https://python-poetry.org/docs/#installation" >&2
  hint_install_slow_and_local
else
  log_ok "poetry $(poetry --version 2>/dev/null | head -1)"
fi

[[ -f poetry.lock ]] || log_warn "缺少 poetry.lock（建议 poetry lock 后提交）"

# ── 3. 虚拟环境与核心 import（须 poetry run）──
if [[ $FAIL -eq 0 ]] && command -v poetry >/dev/null 2>&1 && [[ -f pyproject.toml ]]; then
  _venv_path="$(poetry env info -p 2>/dev/null || true)"
  if [[ -z "$_venv_path" || ! -d "$_venv_path" ]]; then
    log_fail "Poetry 虚拟环境未创建或未安装依赖"
    hint_poetry_install
  else
    log_ok "venv: $_venv_path"
    set +e
    _imp_out="$(poetry run python - <<'PY' 2>&1
import importlib
errors = []
for mod in ("yaml", "torch"):
    try:
        importlib.import_module(mod)
    except ModuleNotFoundError as e:
        errors.append(f"{mod}: {e}")
if errors:
    print("\n".join(errors))
    raise SystemExit(1)
import torch
print(f"torch={torch.__version__} cuda={torch.cuda.is_available()} devices={torch.cuda.device_count() if torch.cuda.is_available() else 0}")
PY
    )"
    _imp_rc=$?
    set -e
    if [[ $_imp_rc -ne 0 ]]; then
      _imp_kind="missing_pkg"
      if [[ -f "$ROOT/scripts/lib/check_env_import_classify.py" ]]; then
        _imp_kind="$(printf '%s' "$_imp_out" | PYTHONPATH="$ROOT/scripts/lib${PYTHONPATH:+:$PYTHONPATH}" \
          python3 -c "from check_env_import_classify import classify_torch_import_failure; import sys; print(classify_torch_import_failure(sys.stdin.read()))" \
          2>/dev/null || echo missing_pkg)"
      else
        echo "  提示: 缺 scripts/lib/check_env_import_classify.py — 先运行 governance-sync.sh（doctor sync_need_files 亦会 FAIL）" >&2
      fi
      if [[ "$_imp_kind" == "dynamic_lib" ]]; then
        log_fail "CUDA/cuDNN 动态库不可用（非缺 pip 包名）"
        echo "$_imp_out" | sed 's/^/  /' >&2
        cat >&2 <<'EOF'
  ── 动态库缺失修法（优先）──
  1) 查 venv 是否有 nvidia cudnn 轮：poetry run python -c "import importlib.util; print(importlib.util.find_spec('nvidia.cudnn'))"
  2) 常见缺 libcusparseLt：poetry add nvidia-cusparselt-cu12（CUDA 12.x；或重跑 /auto-nn-setup）
  3) 对照系统 Python（常已含 nvidia_cudnn_cu12）：python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
  4) 对齐：poetry env use "$(which python3)" && poetry install
     或重装与 CUDA 匹配的 torch 轮（见 pyproject.toml [[tool.poetry.source]]）
  若确认尚未安装 torch/yaml：再执行 poetry install
EOF
      else
        log_fail "Poetry 环境中缺少核心依赖"
        echo "$_imp_out" | sed 's/^/  /' >&2
        hint_poetry_install
      fi
    else
      log_ok "${_imp_out}"
      if [[ $SNAPSHOT -eq 1 ]]; then
        poetry run python - <<'PY'
import torch
print(f"python3_system: $(__import__('shutil').which('python3') or 'n/a')")
import subprocess
pp = subprocess.run(["poetry", "run", "which", "python"], capture_output=True, text=True)
print(f"poetry_python: {pp.stdout.strip() or 'n/a'}")
print(f"torch: {torch.__version__}")
print(f"cuda_available: {torch.cuda.is_available()}")
print(f"torch_cuda: {torch.version.cuda}")
if torch.cuda.is_available():
    print(f"gpu_name: {torch.cuda.get_device_name(0)}")
PY
      fi
    fi
  fi
fi

# ── 4. 家目录 ~/.gpus 活闸（有文件才收紧；无文件不拦）──
if [[ $FAIL -eq 0 && -f "$ROOT/scripts/lib/home_gpus.py" ]]; then
  set +e
  _home_gpu_msg="$(PYTHONPATH="$ROOT/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY' 2>&1
from lib.home_gpus import check_env_status
msg, rc = check_env_status()
print(msg)
raise SystemExit(rc)
PY
)"
  _home_gpu_rc=$?
  set -e
  if [[ "$_home_gpu_msg" == FAIL:* ]]; then
    log_fail "${_home_gpu_msg#FAIL:}"
    echo "  修复: 改 ~/.gpus 授权的卡号，或把 CUDA_VISIBLE_DEVICES 改到名单内；也可删掉该文件（不限制占用）" >&2
  elif [[ $_home_gpu_rc -ne 0 ]]; then
    log_fail "无法检查家目录显卡名单: ${_home_gpu_msg}"
  elif [[ $QUIET -eq 0 && "$_home_gpu_msg" == OK:home_gpus* ]]; then
    log_ok "${_home_gpu_msg#OK:}"
  elif [[ $QUIET -eq 0 && "$_home_gpu_msg" == OK:no_home_gpus ]]; then
    log_ok "未建 ~/.gpus，不限制本机显卡占用"
  elif [[ $QUIET -eq 0 && "$_home_gpu_msg" == OK:* ]]; then
    log_ok "${_home_gpu_msg#OK:}"
  fi
fi

# ── 4b. nn-config GPU 白名单 vs 本机（WARN 不阻断）──
if [[ -f nn-config.yaml ]] && [[ $FAIL -eq 0 ]] && command -v poetry >/dev/null 2>&1; then
  set +e
  _gpu_msg="$(poetry run python - <<'PY' 2>&1
import yaml
from pathlib import Path
cfg = yaml.safe_load(Path("nn-config.yaml").read_text()) or {}
_raw = cfg.get("gpus")
if isinstance(_raw, list):
    gpus = _raw
elif isinstance(_raw, dict):
    gpus = _raw.get("devices") or []
else:
    gpus = []
if not gpus:
    print("OK:no_gpu_whitelist")
    raise SystemExit(0)
import torch
n = torch.cuda.device_count() if torch.cuda.is_available() else 0
bad = [g for g in gpus if not isinstance(g, int) or g < 0 or g >= n]
if not torch.cuda.is_available() and gpus:
    print(f"WARN:no_cuda whitelist={gpus}")
    raise SystemExit(0)
if bad:
    print(f"WARN:whitelist {gpus} 但本机仅 {n} 张 GPU（无效索引 {bad}）")
else:
    print(f"OK:gpu_whitelist {gpus} / device_count={n}")
PY
  )"
  _gpu_rc=$?
  set -e
  if [[ $_gpu_rc -ne 0 ]]; then
    log_warn "无法读取 nn-config GPU 白名单: ${_gpu_msg}"
  elif [[ "$_gpu_msg" == WARN:* ]]; then
    log_warn "${_gpu_msg#WARN:}"
    echo "  修复: 改 nn-config.yaml → gpus: [索引列表]，或 export CUDA_VISIBLE_DEVICES" >&2
  elif [[ $QUIET -eq 0 && "$_gpu_msg" == OK:* ]]; then
    log_ok "${_gpu_msg#OK:}"
  fi
fi

if [[ $FAIL -gt 0 ]]; then
  echo "[check-env] 未通过（${FAIL} FAIL${WARN:+, ${WARN} WARN}）— 请先修复环境再 auto-run / smoke" >&2
  exit 1
fi

[[ $QUIET -eq 0 && $WARN -gt 0 ]] && echo "[check-env] 通过（${WARN} 条 WARN，可继续但建议处理）" >&2
exit 0
