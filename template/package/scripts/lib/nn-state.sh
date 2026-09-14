#!/usr/bin/env bash
# nn-state.sh — .auto-nn/ 项目治理状态读写（单一权威路径）
#
# 被 governance-sync.sh / verify-migration-complete.sh / nn-doctor.sh
# 共同 source。状态文件统一在 <root>/.auto-nn/。
# 无双路径回退、无 migrate。
set -euo pipefail

# nn_state_path <key> [root] — 返回 <root>/.auto-nn/<key>（root 默认 .）
nn_state_path() {
  local key="${1:?key required}"
  local root="${2:-.}"
  printf '%s/.auto-nn/%s\n' "$root" "$key"
}

# nn_state_read <key> [root] — 读并去 CR/LF；文件不存在则空串（不报错）
nn_state_read() {
  local key="${1:?key required}"
  local root="${2:-.}"
  local p
  p="$(nn_state_path "$key" "$root")"
  [[ -f "$p" ]] || return 0
  tr -d '\r\n' < "$p"
}

# nn_state_write <key> <val> [root] — 写 <root>/.auto-nn/<key>（建目录）
nn_state_write() {
  local key="${1:?key required}"
  local val="${2:?val required}"
  local root="${3:-.}"
  mkdir -p "$root/.auto-nn"
  printf '%s\n' "$val" > "$(nn_state_path "$key" "$root")"
}

# nn_state_write_once <key> <val> [root] — 已存在且非空则跳过（立项原始戳等）
nn_state_write_once() {
  local key="${1:?key required}"
  local val="${2:?val required}"
  local root="${3:-.}"
  local p
  p="$(nn_state_path "$key" "$root")"
  if [[ -s "$p" ]]; then
    return 0
  fi
  nn_state_write "$key" "$val" "$root"
}

# nn_resolve_template_root [project-root] — 跨机器解析模板维护仓根
# 顺序：$NN_TEMPLATE_ROOT（env，可选临时覆盖）> 解 ~/.cursor/skills/auto-nn-* symlink 自动定位
#       > .auto-nn/template-root 文件（只读兜底）
# 命中输出绝对路径（stdout）；全失败输出空 + return 1
nn_resolve_template_root() {
  local project_root="${1:-.}" cand real d depth

  # 1) 环境变量（可选临时覆盖；不强求写 ~/.bashrc）
  if [[ -n "${NN_TEMPLATE_ROOT:-}" && -d "$NN_TEMPLATE_ROOT" ]]; then
    printf '%s\n' "$NN_TEMPLATE_ROOT"
    return 0
  fi

  # 2) 解全局技能 symlink 自动定位（零配置默认主路径）
  #    ~/.cursor/skills/auto-nn-* → …/auto-nn-experiment/skills/{post-migration,maintainer}/auto-nn-*
  #    逐级 dirname 往上找 .template-maintainer（模板仓根标志，限深 10）
  for cand in "$HOME"/.cursor/skills/auto-nn-*; do
    [[ -L "$cand" ]] || continue
    real="$(readlink -f "$cand" 2>/dev/null)" || continue
    [[ -n "$real" ]] || continue
    d="$real"; depth=0
    while [[ -n "$d" && "$d" != "/" && $depth -lt 10 ]]; do
      if [[ -f "$d/.template-maintainer" ]]; then
        printf '%s\n' "$d"
        return 0
      fi
      d="$(dirname "$d")"
      depth=$((depth + 1))
    done
  done

  # 3) .auto-nn/template-root 文件（只读历史兜底）
  cand="$(nn_state_read template-root "$project_root")"
  if [[ -n "$cand" && -d "$cand" ]]; then
    printf '%s\n' "$cand"
    return 0
  fi

  return 1
}