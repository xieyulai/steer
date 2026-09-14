#!/usr/bin/env bash
# 清空 HUMAN_GUIDANCE.md 路线图为「全自主」空模板（默认 dry-run；须 --apply）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/HUMAN_GUIDANCE.md"
APPLY=0
BACKUP=1

usage() {
  cat <<'EOF'
用法: bash scripts/clear-human-guidance-roadmap.sh [--apply] [--no-backup] [HUMAN_GUIDANCE.md]

  将路线图阶段清空为全自主（无 ### 阶段）。
  **保留**已有「## 公平约束」正文（与路线图无关）。
  默认 dry-run；--apply 才写入。
  默认备份现有文件为 HUMAN_GUIDANCE.md.bak（--no-backup 跳过）。

  不清 TSV / EXPERIENCE / keeper。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --no-backup) BACKUP=0; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "[clear-human-guidance-roadmap] 未知选项: $1" >&2; usage >&2; exit 1 ;;
    *) TARGET="$1"; shift ;;
  esac
done

_run_batch_hint() {
  if [[ -f "$ROOT/scripts/human_guidance_gate.py" ]]; then
    python3 "$ROOT/scripts/human_guidance_gate.py" --repo-root "$ROOT" batch-hint >&2 || true
  fi
}

_run_batch_hint

# 清空只清路线图阶段；保留已有「公平约束」正文（与路线图无关）
_build_empty_content() {
  python3 - "$TARGET" <<'PY'
import re
import sys
from pathlib import Path

target = Path(sys.argv[1])
fair_body = ""
if target.is_file():
    text = target.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"##\s*公平约束\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
    if m:
        raw = m.group(1)
        # 去掉仅注释的占位
        stripped = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()
        if stripped:
            fair_body = raw.strip()

fair_section = (
    "## 公平约束\n\n" + fair_body + "\n"
    if fair_body
    else "## 公平约束\n\n<!-- 可选；与路线图并列。无比较锁则留空或删节。 -->\n"
)
print(
    "# 人类指导（Human guidance）\n\n"
    "> 意图归人；经 `/auto-nn-human-guidance` 代写落盘。当前阶段由台账推断。"
    "优先级见 PROTOCOL §7.5。\n\n"
    f"{fair_section}\n"
    "## 路线图\n\n"
    "<!-- 添加 ### 阶段 N — … 启用路线图；无阶段 = Agent 全自主 -->\n"
)
PY
}

EMPTY_ROADMAP="$(_build_empty_content)"

if [[ "$APPLY" -eq 0 ]]; then
  echo "[clear-human-guidance-roadmap] dry-run: 将清空路线图阶段（保留公平约束正文若有）→ $TARGET"
  if [[ -f "$TARGET" ]]; then
    echo "[clear-human-guidance-roadmap] 当前文件: $(wc -l < "$TARGET") 行"
  else
    echo "[clear-human-guidance-roadmap] 当前文件: （不存在，将新建）"
  fi
  echo "--- 目标内容 ---"
  printf '%s' "$EMPTY_ROADMAP"
  echo "[clear-human-guidance-roadmap] 确认后: bash scripts/clear-human-guidance-roadmap.sh --apply"
  exit 0
fi

if [[ -f "$TARGET" && "$BACKUP" -eq 1 ]]; then
  cp "$TARGET" "${TARGET}.bak"
  echo "[clear-human-guidance-roadmap] 已备份 → ${TARGET}.bak"
fi

printf '%s' "$EMPTY_ROADMAP" > "$TARGET"
echo "[clear-human-guidance-roadmap] OK: 已清空路线图（公平约束已保留若原先有正文）"

if [[ -f "$(dirname "$TARGET")/scripts/validate-human-guidance.sh" ]]; then
  bash "$(dirname "$TARGET")/scripts/validate-human-guidance.sh" "$TARGET" || true
fi
