#!/usr/bin/env bash
# bump-version.sh — 模板仓版本 bump 一条龙
#
# 流程（详见 skills/bump-version/SKILL.md）：
#   1. parse_args
#   2. check_repo (git + VERSION)
#   3. check_tag (或 retro-tag)
#   4. compute_bump (conventional commits heuristic)
#   5. dry-run preview 或 y/N 确认
#   6. 写 VERSION + 更新 CHANGELOG + git commit
#   7. 跑 release-check.sh
#   8. git tag (T1 默认 ON)
#   9. --push 时 git push --follow-tags
#
# 退出码:
#   0 success
#   1 missing tag (提示 --retro-tag)
#   2 major without --accept-major-bump / 参数错误
#   3 不是 git 仓 / 无 VERSION / VERSION 非 semver
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 用 git toplevel 解析 REPO_ROOT（不依赖 SCRIPT_DIR 在仓内的相对位置，
# 兼容 .claude/skills/bump-version/ 与 skills/bump-version/ 两种历史布局）
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../.." && pwd))"
TEMPLATE_SCRIPTS="$REPO_ROOT/template/package/scripts"

usage() {
  cat <<'USAGE'
Usage: bump-version [auto|major|minor|patch|<semver>] [options]

Modes:
  (无)         auto — 从 git log conventional commits 推断 bump type
  auto         同上
  major        强制 major (需 --accept-major-bump)
  minor        强制 minor
  patch        强制 patch
  <semver>     显式指定目标版本 (如 1.2.0)

Options:
  --retro-tag <ver>         retro 补 <ver> tag (用于历史 commit 漏打 tag)
  --accept-major-bump       显式 accept major bump
  --no-tag                  跳过 git tag (默认 ON)
  --dry-run                 只打印 preview,不改任何文件
  --push                    bump 成功后 git push --follow-tags (谨慎)
  -h, --help                显示本帮助

Exit codes:
  0 success | 1 missing tag | 2 major without --accept-major-bump | 3 not git repo
USAGE
}

# ---------- arg parse ----------

MODE="auto"
RETRO_TAG=""
ACCEPT_MAJOR=0
NO_TAG=0
DRY_RUN=0
PUSH=0

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      auto|major|minor|patch) MODE="$1"; shift ;;
      --retro-tag) RETRO_TAG="$2"; shift 2 ;;
      --accept-major-bump) ACCEPT_MAJOR=1; shift ;;
      --no-tag) NO_TAG=1; shift ;;
      --dry-run) DRY_RUN=1; shift ;;
      --push) PUSH=1; shift ;;
      -h|--help) usage; exit 0 ;;
      -*) echo "Unknown flag: $1" >&2; usage >&2; exit 2 ;;
      *)
        if [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
          MODE="$1"
        else
          echo "Invalid semver: $1" >&2; exit 2
        fi
        shift
        ;;
    esac
  done

  if [[ "$MODE" == "major" && "$ACCEPT_MAJOR" != "1" ]]; then
    echo "major bump requires --accept-major-bump" >&2
    exit 2
  fi
}

# ---------- git/VERSION 检测 ----------

CURRENT_VER=""
NEW_VER=""
BUMP_TYPE=""

check_repo() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Not a git repo: $PWD" >&2
    exit 3
  fi
  [[ -s VERSION ]] || { echo "VERSION missing or empty" >&2; exit 3; }
  CURRENT_VER="$(tr -d '\r\n' < VERSION)"
  [[ "$CURRENT_VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "VERSION not semver: $CURRENT_VER" >&2; exit 3
  }
}

# ---------- retro-tag ----------

retro_tag_mode() {
  local tag="$RETRO_TAG"
  local ver="${tag#v}"
  local sha
  sha="$(git log --all --oneline --grep="release: ${ver}\b" -1 | awk '{print $1}')"
  if [[ -z "$sha" ]]; then
    echo "No release commit found for ${ver} (grep 'release: ${ver}')" >&2
    exit 1
  fi
  echo "[retro-tag] create ${tag} at ${sha}"
  if [[ "$DRY_RUN" != "1" ]]; then
    git tag "$tag" "$sha"
    echo "[retro-tag] done"
  fi
}

check_tag() {
  local tag="v${CURRENT_VER}"
  if ! git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
    echo "Tag ${tag} missing. First run: bump-version --retro-tag ${tag}" >&2
    exit 1
  fi
}

# ---------- bump type 推断 ----------

# compute_bump: 决定 NEW_VER + BUMP_TYPE
# 三种路径:
#   1. MODE 是 semver → NEW_VER=MODE, BUMP_TYPE=explicit
#   2. MODE 是 major/minor/patch → 用 inline python 计算 NEW_VER
#   3. MODE=auto → 扫 conventional commits, 取最高严重度
compute_bump() {
  if [[ "$MODE" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    NEW_VER="$MODE"
    BUMP_TYPE="explicit"
    return
  fi

  if [[ "$MODE" != "auto" ]]; then
    # explicit major/minor/patch
    BUMP_TYPE="$MODE"
    NEW_VER="$(PYTHONPATH="$TEMPLATE_SCRIPTS" python3 -c "
from check_template_version import parse
cur = parse('$CURRENT_VER')
if '$MODE' == 'major':
    print(f'{cur.major + 1}.0.0')
elif '$MODE' == 'minor':
    print(f'{cur.major}.{cur.minor + 1}.0')
else:
    print(f'{cur.major}.{cur.minor}.{cur.patch + 1}')
")"
    return
  fi

  # auto: conventional commits heuristic
  # 扫描 v${CURRENT_VER}..HEAD 的 commit subject + body
  # 规则 (max severity):
  #   - 含 'BREAKING' → major
  #   - 'feat:' (无 BREAKING) → minor
  #   - 'fix:' / 'refactor:' → patch
  #   - 其它 (docs/test/chore/perf) → skip (除非全是 skip, fallback patch)
  local has_breaking=0 has_feat=0 has_fix=0 has_skip=0
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ "$line" == *BREAKING* || "$line" == *Breaking* ]]; then
      has_breaking=1
    elif [[ "$line" == feat:* || "$line" == "feat("* ]]; then
      has_feat=1
    elif [[ "$line" == fix:* || "$line" == "fix("* ]]; then
      has_fix=1
    elif [[ "$line" == refactor:* || "$line" == "refactor("* ]]; then
      has_fix=1
    else
      has_skip=1
    fi
  done < <(git log "v${CURRENT_VER}..HEAD" --format='%s%n%b' 2>/dev/null || \
           git log "v${CURRENT_VER}..HEAD" --format='%s%n%b')

  if [[ "$has_breaking" == "1" ]]; then
    BUMP_TYPE="major"
  elif [[ "$has_feat" == "1" ]]; then
    BUMP_TYPE="minor"
  elif [[ "$has_fix" == "1" ]]; then
    BUMP_TYPE="patch"
  elif [[ "$has_skip" == "1" ]]; then
    # 全是 docs/test/chore 等 → 不算 bump; 但保持 patch 以有进展
    BUMP_TYPE="patch"
  else
    # 0 commit → 不 bump (但 exit 不出错)
    BUMP_TYPE="patch"
  fi

  NEW_VER="$(PYTHONPATH="$TEMPLATE_SCRIPTS" python3 -c "
from check_template_version import parse
cur = parse('$CURRENT_VER')
bt = '$BUMP_TYPE'
if bt == 'major':
    print(f'{cur.major + 1}.0.0')
elif bt == 'minor':
    print(f'{cur.major}.{cur.minor + 1}.0')
else:
    print(f'{cur.major}.{cur.minor}.{cur.patch + 1}')
")"
}

# ---------- CHANGELOG 更新 ----------

update_changelog() {
  local today new_ver="$NEW_VER"
  today="$(date +%Y-%m-%d)"
  local tmp_cl
  tmp_cl="$(mktemp)"

  # 用 python 做插入 (更可靠: scan commits + 写段 + 插入 ## [Unreleased] 后)
  # 注意: 传 CURRENT_VER (旧值) 给 python, 因为 VERSION 文件已被写为 NEW_VER
  PYTHONPATH="$TEMPLATE_SCRIPTS" python3 - "$new_ver" "$today" "$CURRENT_VER" <<PYEOF > "$tmp_cl"
import sys, re
from pathlib import Path

new_ver, today, prev_ver = sys.argv[1], sys.argv[2], sys.argv[3]
content = Path("CHANGELOG.md").read_text()

# 构造新段
lines = [f"## [{new_ver}] - {today}", ""]
# 收集 commits (从 git log)
import subprocess
out = subprocess.check_output(
    ["git", "log", f"v{prev_ver}..HEAD", "--format=%s"],
    text=True,
).strip().splitlines()

added, fixed, changed = [], [], []
for subj in out:
    if "BREAKING" in subj:
        changed.append(subj)
    elif subj.startswith("feat"):
        added.append(subj)
    elif subj.startswith("fix"):
        fixed.append(subj)
    elif subj.startswith("refactor"):
        changed.append(subj)

if added:
    lines.extend(["### Added", ""] + [f"- {s}" for s in added] + [""])
if changed:
    lines.extend(["### Changed", ""] + [f"- {s}" for s in changed] + [""])
if fixed:
    lines.extend(["### Fixed", ""] + [f"- {s}" for s in fixed] + [""])

new_section = "\n".join(lines)

# 替换 ## [Unreleased] → ## [Unreleased]\n\n<new_section>
new_content = re.sub(
    r"^(## \[Unreleased\].*?)(?=^## \[|\Z)",
    lambda m: "## [Unreleased]\n\n" + new_section + "\n",
    content,
    count=1,
    flags=re.MULTILINE | re.DOTALL,
)
print(new_content, end="")
PYEOF

  mv "$tmp_cl" CHANGELOG.md
}

# ---------- preview ----------

render_preview() {
  local push_state="NO"
  [[ "$PUSH" == "1" ]] && push_state="YES (--push)"
  local tag_state="YES"
  [[ "$NO_TAG" == "1" ]] && tag_state="NO (--no-tag)"

  local commit_count
  commit_count="$(git log "v${CURRENT_VER}..HEAD" --oneline | wc -l | tr -d ' ')"

  cat >&2 <<EOF
[bump-version] dry-run preview
  current: ${CURRENT_VER}
  new:     ${NEW_VER} (${BUMP_TYPE})
  commits: ${commit_count}
  tag:     v${NEW_VER} (${tag_state})
  push:    ${push_state}
EOF
}

# ---------- main ----------

main() {
  parse_args "$@"

  # retro-tag 模式: 独立路径 (只需 git, 不需 VERSION)
  if [[ -n "$RETRO_TAG" ]]; then
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      echo "Not a git repo: $PWD" >&2
      exit 3
    fi
    retro_tag_mode
    exit $?
  fi

  check_repo
  check_tag
  compute_bump

  if [[ "$DRY_RUN" == "1" ]]; then
    render_preview
    exit 0
  fi

  echo "[bump-version] ${CURRENT_VER} → ${NEW_VER} (${BUMP_TYPE})"

  # 写 VERSION
  echo "$NEW_VER" > VERSION

  # 更新 CHANGELOG
  update_changelog

  # git commit
  git add VERSION CHANGELOG.md
  git commit -q -m "release: ${NEW_VER}"

  # 跑 release-check (5 步门禁不可绕过)
  # 真源在 template/package/scripts/release-check.sh（root scripts/ 已在
  # commit 9ef43f7 删除，无 mirror 副本）。SCRIPT_DIR = skills/bump-version/。
  if [[ -x "$TEMPLATE_SCRIPTS/release-check.sh" ]]; then
    # RELEASE_CHECK_ROOT 指向被 bump 的仓（= 本脚本 cwd）；否则 release-check.sh
    # 会按自身脚本位置 cd 回模板仓、读到模板仓 VERSION（测试隔离 bug 根因）。
    RELEASE_CHECK_ROOT="$PWD" bash "$TEMPLATE_SCRIPTS/release-check.sh"
  else
    echo "[bump-version] FAIL: $TEMPLATE_SCRIPTS/release-check.sh not found — refusing to bump without 5-step gate" >&2
    exit 3
  fi

  # 打 tag (T1 默认 ON)。必须 annotated（-a）：`git push --follow-tags` 只推 annotated
  # tag，轻量 tag 会被静默漏推（v1.4.2 即踩此坑——bump 报 push 成功但 tag 没上 remote）。
  if [[ "$NO_TAG" != "1" ]]; then
    git tag -a "v${NEW_VER}" -m "release ${NEW_VER}"
    echo "[bump-version] tag v${NEW_VER} created (annotated)"
  fi

  # push (默认不 push)
  if [[ "$PUSH" == "1" ]]; then
    git push --follow-tags
  else
    echo "[bump-version] next: git push --follow-tags"
  fi
}

main "$@"