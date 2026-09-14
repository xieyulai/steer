#!/usr/bin/env bash
# install.sh — symlink/copy auto-nn-* skills 到 ~/.cursor/skills（及 ~/.claude/skills）
# 不再注册 kill-guard PreToolUse hook；--uninstall 仍会清理历史 hook 与 ~/.local/bin/nn-kill-guard.sh
set -euo pipefail

TEMPLATE_ROOT="$(cd "$(dirname "$0")" && pwd)"
COPY=0
DRY_RUN=0
UNINSTALL=0

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  echo "用法: $0 [--copy] [--dry-run] [--uninstall]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) COPY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 2 ;;
  esac
done

# 本 install.sh 只装本仓 auto-nn-*；沙箱设施（sandbox-*）归独立仓 sandbox-auto-nn 自装。
skill_src_dirs() {
  local d
  for d in "$TEMPLATE_ROOT/skills/post-migration"/auto-nn-* \
           "$TEMPLATE_ROOT/skills/maintainer"/auto-nn-*; do
    [[ -d "$d" && -f "$d/SKILL.md" ]] || continue
    printf '%s\n' "$d"
  done
}

global_targets() {
  mkdir -p "${HOME}/.cursor/skills" "${HOME}/.claude/skills" 2>/dev/null || true
  [[ -d "${HOME}/.cursor/skills" ]] && printf '%s\n' "${HOME}/.cursor/skills"
  [[ -d "${HOME}/.claude/skills" ]] && printf '%s\n' "${HOME}/.claude/skills"
}

install_one() {
  local src="$1" name="$2" base="$3"
  local dest="${base}/${name}"
  if [[ "$UNINSTALL" -eq 1 ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] rm -f ${dest} (if link)"
    elif [[ -L "$dest" || -d "$dest" ]]; then
      rm -rf "$dest"
      echo "removed ${dest}"
    fi
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] ${dest} -> ${src}"
    return 0
  fi
  mkdir -p "$base"
  rm -rf "$dest"
  if [[ "$COPY" -eq 1 ]]; then
    cp -a "$src" "$dest"
  else
    ln -s "$src" "$dest"
  fi
  echo "installed ${dest}"
}

# 已废止技能名：安装/卸载时移除 stale symlink（源目录已不在 skills/）
LEGACY_SKILL_NAMES=(
  auto-nn-reset
  auto-nn-compress-experience
  auto-nn-experiment-round
  auto-nn-reflect-round
  auto-nn-template-migration
  auto-nn-template-governance
  auto-nn-sync
)

remove_legacy_skills() {
  local base name dest
  for base in "$@"; do
    [[ -n "$base" ]] || continue
    for name in "${LEGACY_SKILL_NAMES[@]}"; do
      dest="${base}/${name}"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        if [[ -L "$dest" || -d "$dest" ]]; then
          echo "[dry-run] remove legacy ${dest}"
        fi
      elif [[ -L "$dest" || -d "$dest" ]]; then
        rm -rf "$dest"
        echo "removed legacy ${dest}"
      fi
    done
  done
}

if [[ "$UNINSTALL" -eq 0 ]]; then
  mapfile -t SRCS < <(skill_src_dirs)
  if [[ ${#SRCS[@]} -eq 0 ]]; then
    echo "FAIL: 未找到技能目录（skills/post-migration/auto-nn-* 或 skills/maintainer/auto-nn-*）" >&2
    exit 1
  fi
fi

while IFS= read -r base; do
  [[ -n "$base" ]] || continue
  if [[ "$UNINSTALL" -eq 1 ]]; then
    mapfile -t SRCS < <(skill_src_dirs)
    for src in "${SRCS[@]}"; do
      install_one "" "$(basename "$src")" "$base"
    done
    remove_legacy_skills "$base"
  else
    for src in "${SRCS[@]}"; do
      install_one "$src" "$(basename "$src")" "$base"
    done
    remove_legacy_skills "$base"
  fi
done < <(global_targets)

# ── kill-guard hook 清理（仅 --uninstall；install 不再注册 hook） ─────────
SETTINGS="${HOME}/.claude/settings.json"
HOOK_MARKER="kill-guard"

_uninstall_hook() {
    local sf="$1"
    [[ -f "$sf" ]] || return 0
    python3 -c "
import json
with open('${sf}') as f:
    s = json.load(f)
hooks = s.get('hooks') or {}
ptu = hooks.get('PreToolUse') or []
before = len(ptu)
ptu = [e for e in ptu if not any('${HOOK_MARKER}' in h.get('command', '') or 'nn-kill-guard' in h.get('command', '') for h in e.get('hooks', []))]
if len(ptu) < before:
    if ptu:
        hooks['PreToolUse'] = ptu
    else:
        hooks.pop('PreToolUse', None)
    if hooks:
        s['hooks'] = hooks
    else:
        s.pop('hooks', None)
    with open('${sf}', 'w') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print('removed kill-guard hook from ${sf}')
else:
    print('no kill-guard hook found in ${sf}')
"
}

if [[ "$UNINSTALL" -eq 1 ]]; then
  if [[ "$DRY_RUN" -eq 0 ]]; then
    rm -f "${HOME}/.auto-nn-skills-rev" "${HOME}/.nn-skills-env"
    rm -f "${HOME}/.local/bin/nn-kill-guard.sh"
    _uninstall_hook "$SETTINGS"
  else
    echo "[dry-run] would uninstall kill-guard hook from ${SETTINGS}"
  fi
  exit 0
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  rm -f "${HOME}/.auto-nn-skills-rev" "${HOME}/.nn-skills-env"
  echo "removed legacy ~/.auto-nn-skills-rev ~/.nn-skills-env (if any)"
fi
