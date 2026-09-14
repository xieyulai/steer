#!/usr/bin/env bash
# 校验 HUMAN_GUIDANCE.md（## 公平约束 可选；## 路线图 可空=全自主）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
F="${1:-HUMAN_GUIDANCE.md}"
[[ -f "$F" ]] || { echo "[validate-human-guidance] 缺少 $F" >&2; exit 1; }
set +e
python3 - "$F" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")

if re.search(r"##\s*生效中", text, re.I):
    print("[validate-human-guidance] WARN: 含旧版 ## 生效中，请迁移至 ## 路线图", file=sys.stderr)

# 可选：文首级 ## 公平约束（与路线图并列）
fair = re.search(r"##\s*公平约束\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
if fair and fair.group(1).strip():
    print("[validate-human-guidance] INFO: 含文首「公平约束」节", file=sys.stderr)

m = re.search(r"##\s*路线图\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
if not m:
    print("[validate-human-guidance] FAIL: 无 ## 路线图", file=sys.stderr)
    sys.exit(1)

body = m.group(1)
phases = re.findall(r"^###\s*阶段\s*\d+", body, re.MULTILINE | re.I)
if not phases:
    print("[validate-human-guidance] OK: 空路线图（全自主）")
    sys.exit(0)

errors = []
for block in re.split(r"(?=^###\s*阶段\s*\d+)", body, flags=re.MULTILINE | re.I):
    block = block.strip()
    if not block.startswith("###"):
        continue
    title = block.splitlines()[0]
    if "目标" not in block:
        errors.append(f"{title}: 缺少 **目标**")
    if "完成条件" not in block:
        errors.append(f"{title}: 缺少 **完成条件**")
    # 阶段内不应再出现「公平约束」字段（应在文首 ## 公平约束）
    if re.search(r"^\s*-\s*\*\*公平约束\*\*", block, re.MULTILINE):
        errors.append(
            f"{title}: 勿在阶段内写「公平约束」字段；请改到文首 ## 公平约束"
        )
    if re.search(r"\*\*NOTE\*\*", block) and re.search(
        r"(N_EPOCHS|BUFFER_SIZE|BUF\s*=|EP\s*=|双向对账|公平判定)", block
    ):
        if not fair or not fair.group(1).strip():
            print(
                f"[validate-human-guidance] WARN: {title} "
                "比较口径建议写在文首 ## 公平约束，NOTE 保持极短",
                file=sys.stderr,
            )

if errors:
    for e in errors:
        print(f"[validate-human-guidance] FAIL: {e}", file=sys.stderr)
    sys.exit(1)

for block in re.split(r"(?=^###\s*阶段\s*\d+)", body, flags=re.MULTILINE | re.I):
    block = block.strip()
    if not block.startswith("###"):
        continue
    if re.search(r"objective\s*:\s*explore", block, re.I):
        has_grid = "探索网格" in block
        has_order = "场景顺序" in block
        if not has_grid and not has_order:
            print(
                f"[validate-human-guidance] WARN: {block.splitlines()[0]} "
                "探索阶段建议含「探索网格」或「场景顺序」",
                file=sys.stderr,
            )
    if re.search(r"objective\s*:\s*(explore|optimize)", block, re.I):
        mobj = re.search(r"objective\s*:\s*(explore|optimize)", block, re.I)
        if mobj:
            print(
                f"[validate-human-guidance] INFO: {block.splitlines()[0]} objective={mobj.group(1)}",
                file=sys.stderr,
            )

print(f"[validate-human-guidance] OK: 路线图 {len(phases)} 个阶段")
PY
_rc=$?
set -e

if [[ -f scripts/human_guidance_gate.py ]]; then
  python3 scripts/human_guidance_gate.py --repo-root . batch-hint >&2 || true
fi
exit "$_rc"
