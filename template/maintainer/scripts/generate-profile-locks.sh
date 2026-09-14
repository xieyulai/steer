#!/usr/bin/env bash
# generate-profile-locks.sh — 为每个 profile 预生成 poetry.lock
# 在模板维护仓根执行：bash template/maintainer/scripts/generate-profile-locks.sh
# 读 template/package/profiles.yaml；产出 template/maintainer/profiles/<profile>/poetry.lock
set -euo pipefail

MAINTAINER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_ROOT="$(cd "$MAINTAINER_ROOT/../package" && pwd)"
cd "$PACKAGE_ROOT"

PROFILES_YAML="$PACKAGE_ROOT/profiles.yaml"
if [[ ! -f "$PROFILES_YAML" ]]; then
  echo "错误: 找不到 $PROFILES_YAML" >&2
  exit 1
fi

PROFILES="$(python3 -c "
import yaml
for k in yaml.safe_load(open('$PROFILES_YAML'))['profiles']:
    print(k)
")"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

for PROFILE in $PROFILES; do
  echo "=== 生成 profile=$PROFILE 的 poetry.lock ==="
  OUT_DIR="$MAINTAINER_ROOT/profiles/$PROFILE"
  mkdir -p "$OUT_DIR"

  python3 -c "
import yaml

profile = '$PROFILE'
profiles = yaml.safe_load(open('$PROFILES_YAML'))['profiles']
extra_deps = profiles[profile].get('dependencies', {})

with open('$PACKAGE_ROOT/pyproject.toml') as f:
    content = f.read()

if extra_deps:
    lines = content.split('\n')
    inserted = False
    new_lines = []
    for line in lines:
        new_lines.append(line)
        if not inserted and line.startswith('torchvision'):
            for pkg, ver in extra_deps.items():
                new_lines.append(f'{pkg} = \"{ver}\"')
            inserted = True
    content = '\n'.join(new_lines)

with open('$TMPDIR/pyproject.toml', 'w') as f:
    f.write(content)
"

  cd "$TMPDIR"
  poetry lock 2>&1 | tail -5
  cp poetry.lock "$OUT_DIR/poetry.lock"
  rm -f pyproject.toml poetry.lock
  echo "=== $PROFILE → $OUT_DIR/poetry.lock ($(wc -l < "$OUT_DIR/poetry.lock") lines)"
done

echo "=== 全部完成 ==="
