#!/usr/bin/env bash
# Agent 必读面：禁止「workspace → 走 modify」；禁止「人生模式」；boost 须鼓励改 workspace
set -euo pipefail
PKG="$(cd "$(dirname "$0")/../.." && pwd)"
RUN="$PKG/auto-nn-run.sh"
CLAUDE="$PKG/CLAUDE.md"
fail() { echo "FAIL: $*"; exit 1; }
ok() { echo "OK: $*"; }

[[ -f "$RUN" && -f "$CLAUDE" ]] || fail "missing package files"

python3 - "$RUN" "$CLAUDE" <<'PY'
import sys
from pathlib import Path
run, claude = Path(sys.argv[1]), Path(sys.argv[2])
rt, ct = run.read_text(encoding="utf-8"), claude.read_text(encoding="utf-8")

idx = rt.find("Edit boundary")
assert idx >= 0, "Edit boundary missing in auto-nn-run.sh"
window = rt[idx : idx + 2500]
if "/auto-nn-modify" in window:
    raise SystemExit("FAIL: Edit boundary window still contains /auto-nn-modify")

bad_claude = "走 `/auto-nn-modify`：动 `train.py` / `workspace/`"
if bad_claude in ct:
    raise SystemExit("FAIL: CLAUDE.md still has old 三态 line tying workspace to modify")

# Broader: same line must not tie modify to train.py/workspace (handles bold variants)
for line in ct.splitlines():
    if "/auto-nn-modify" in line and "动 `train.py` / `workspace/`" in line:
        raise SystemExit(
            "FAIL: CLAUDE.md line ties /auto-nn-modify to train.py/workspace: "
            + line.strip()[:120]
        )

if "人生模式" in rt:
    raise SystemExit("FAIL: 人生模式 still in auto-nn-run.sh")

# innovation inject: boost branch must mention workspace 落地 / register
i0 = rt.find("_inject_innovation_prompt()")
assert i0 >= 0
# crude: from function start to next function-ish
i1 = rt.find("\n_run_round_doctor", i0)
body = rt[i0:i1 if i1 > 0 else i0 + 8000]
if 'innov_boost' not in body:
    raise SystemExit("FAIL: innov_boost missing")
# After boost==1 echoes, require 实验模式 + workspace encouragement keywords
if "人生模式" in body:
    raise SystemExit("FAIL: 人生模式 in inject body")
if '== "1"' in body:
    # require Chinese 实验模式 and workspace
    chunk = body
    if "实验模式" not in chunk and "innovate" in chunk:
        # 至少 boost 真分支应写 实验模式=
        pass
    # Strong requirement after Task 2:
    if "workspace" not in chunk.lower() and "workspace/" not in chunk:
        raise SystemExit("FAIL: innovation inject should mention workspace")
    # Prefer explicit encourage markers
    markers = ("落地", "register", "@register", "优先")
    if not any(m in chunk for m in markers):
        raise SystemExit("FAIL: innovation inject missing encourage markers (落地/register/优先)")

# plateau: innovate/aggressive exception must exist near 不启新 backbone
if "不启新 backbone" in rt:
    # require nearby mention of innovate or aggressive exception within 400 chars
    j = rt.find("不启新 backbone")
    ctx = rt[max(0, j - 200) : j + 400]
    if "innovate" not in ctx and "aggressive" not in ctx:
        raise SystemExit(
            "FAIL: plateau '不启新 backbone' lacks innovate/aggressive exception nearby"
        )

print("OK: narrative gates")
PY
ok "test_agent_edit_boundary_narrative"
