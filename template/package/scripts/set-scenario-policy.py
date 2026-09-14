#!/usr/bin/env python3
"""yaml-safe 设置场景策略：nn-config + README SCENARIO_POLICY 同步。

用法（项目根目录）：
  python3 scripts/set-scenario-policy.py rotate --active "64b,128b,256b,512b,1024b"
  python3 scripts/set-scenario-policy.py focus --default 64b --active 64b
  python3 scripts/set-scenario-policy.py rotate --active "128b,256b,512b,1024b" --dry-run

注意：正在跑的 auto-nn-run batch 读的是启动时配置，改完须停 batch → 改 → 验收 → 重开。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required") from exc

# Load nn-config via load_nn_config() (Phase 2 of config-minimal).
# set-scenario-policy 专管 agent.scenario_*（legacy 位置）;lib/nn_config 显式把
# scenario_default 等保留在 agent,不走 AGENT_TO_TOP_KEYS 回填;round-trip 仍走
# yaml.safe_load 保留未知字段。
# 须把 scripts/ 入 path 后 `from lib.nn_config`（勿只插 lib/：相对 import 会炸）。
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from lib.nn_config import load_nn_config  # noqa: E402

_POLICIES = frozenset({"focus", "rotate", "multi_eval_one_train"})
_SCENARIO_START = "<!-- SCENARIO_POLICY -->"
_SCENARIO_END = "<!-- /SCENARIO_POLICY -->"


def _split_active(raw: str) -> list[str]:
    parts = re.split(r"[,;\s]+", (raw or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _active_display(ids: list[str]) -> str:
    return ",".join(ids)


def _update_nn_config(
    path: Path,
    *,
    policy: str,
    active: list[str],
    default_id: str | None,
) -> bool:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    agent = cfg.setdefault("agent", {})
    before = (
        str(agent.get("scenario_policy") or ""),
        str(agent.get("scenario_active") or ""),
        str(agent.get("scenario_default") or ""),
    )
    agent["scenario_policy"] = policy
    agent["scenario_active"] = _active_display(active) if active else ""
    if default_id:
        agent["scenario_default"] = default_id
    after = (
        str(agent.get("scenario_policy") or ""),
        str(agent.get("scenario_active") or ""),
        str(agent.get("scenario_default") or ""),
    )
    if before == after:
        return False
    path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return True


def _parse_scenario_block(text: str) -> dict[str, str]:
    start = text.find(_SCENARIO_START)
    if start < 0:
        return {}
    start += len(_SCENARIO_START)
    end = text.find(_SCENARIO_END, start)
    body = text[start:end] if end >= 0 else text[start:]
    out: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip()
    return out


def _replace_scenario_field(block_body: str, key: str, value: str) -> str:
    pat = re.compile(rf"^({re.escape(key)}:\s*).*$", re.MULTILINE)
    if pat.search(block_body):
        return pat.sub(rf"\g<1>{value}", block_body, count=1)
    return block_body.rstrip() + f"\n{key}: {value}\n"


def _update_readme_scenario_block(
    path: Path,
    *,
    policy: str,
    active: list[str],
    default_id: str | None,
) -> bool:
    text = path.read_text(encoding="utf-8")
    start = text.find(_SCENARIO_START)
    end = text.find(_SCENARIO_END)
    if start < 0 or end < 0:
        return False
    head = start + len(_SCENARIO_START)
    body = text[head:end]
    new_body = body
    new_body = _replace_scenario_field(new_body, "SCENARIO_POLICY", policy)
    if active:
        new_body = _replace_scenario_field(new_body, "ACTIVE_SCENARIOS", _active_display(active))
    if default_id:
        new_body = _replace_scenario_field(new_body, "DEFAULT_SCENARIO", default_id)
    if new_body == body:
        return False
    out = text[:head] + new_body + text[end:]
    path.write_text(out, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", choices=sorted(_POLICIES))
    parser.add_argument(
        "--active",
        default="",
        help="参与轮换/聚焦的场景 ID，逗号分隔（须已在 README 场景清单）",
    )
    parser.add_argument(
        "--default",
        dest="default_id",
        default="",
        help="scenario_default；默认不改 nn-config 里已有值",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="改完后跑 scenario_policy_gate + readme_consistency_gate",
    )
    args = parser.parse_args()

    root = args.repo_root.resolve()
    cfg_path = root / "nn-config.yaml"
    readme_path = root / "README.md"
    if not cfg_path.is_file():
        print(f"ERROR: 缺少 {cfg_path}", file=sys.stderr)
        return 1

    active = _split_active(args.active)
    # 走 load_nn_config:preset expansion 自动注入 14 段;agent.* 经 AGENT_TO_TOP_KEYS 回填。
    # scenario_default 不在回填表(故意留 agent),所以仍读 cfg["agent"]（loader 也返回 agent 子表）。
    cfg = load_nn_config(root)
    agent = (cfg.get("agent") or {}) if isinstance(cfg, dict) else {}
    default_id = (args.default_id or str(agent.get("scenario_default") or "")).strip() or None

    if args.policy == "focus" and not active and default_id:
        active = [default_id]
    if args.policy == "rotate" and not active:
        print("ERROR: rotate 须 --active 列出要轮换的场景", file=sys.stderr)
        return 1

    print(f"[set-scenario-policy] policy={args.policy} active={_active_display(active) or '(空)'}")
    if default_id:
        print(f"[set-scenario-policy] default={default_id}")

    if args.dry_run:
        print("[set-scenario-policy] dry-run（未写盘）")
        print("[set-scenario-policy] 提醒：须先停掉正在跑的 auto-nn-run batch，改完再重开")
        return 0

    changed_cfg = _update_nn_config(
        cfg_path, policy=args.policy, active=active, default_id=default_id,
    )
    changed_readme = False
    if readme_path.is_file():
        changed_readme = _update_readme_scenario_block(
            readme_path, policy=args.policy, active=active, default_id=default_id,
        )
    else:
        print("[set-scenario-policy] WARN: 无 README.md，仅改了 nn-config", file=sys.stderr)

    if not changed_cfg and not changed_readme:
        print("[set-scenario-policy] 无变更（已是目标值）")
    else:
        parts = []
        if changed_cfg:
            parts.append("nn-config.yaml")
        if changed_readme:
            parts.append("README SCENARIO_POLICY")
        print(f"[set-scenario-policy] 已更新: {', '.join(parts)}")

    print("[set-scenario-policy] 下一步：停 batch（若在跑）→ commit → 重开 ./auto-nn-run.sh N")

    if args.verify:
        import subprocess

        for script in ("scenario_policy_gate.py", "readme_consistency_gate.py"):
            p = root / "scripts" / script
            if not p.is_file():
                print(f"[set-scenario-policy] WARN: 跳过 {script}（不存在）", file=sys.stderr)
                continue
            print(f"[set-scenario-policy] 运行 {script} …")
            r = subprocess.run([sys.executable, str(p), str(root)], cwd=str(root))
            if r.returncode != 0:
                return r.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
