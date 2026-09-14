"""Parse auto-nn-experiment/profiles.yaml to extract profile boundaries."""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import yaml

_VALID_PROFILES = frozenset({"supervised", "rl", "physical"})


class ProfileBoundary(TypedDict):
    profile: str
    description: str
    contract_methods: list[str]
    workspace_methods: list[str]


def template_pkg(root: str | Path) -> Path:
    """Business install package: template/package/ if present, else flat template/ or repo root."""
    p = Path(root)
    if (p / "template" / "package" / "profiles.yaml").is_file():
        return p / "template" / "package"
    if (p / "template" / "profiles.yaml").is_file():
        return p / "template"
    return p


def load_profile_boundaries(template_root: str | Path) -> dict[str, ProfileBoundary]:
    """Load all profile boundaries from the template repo (template/package/profiles.yaml)."""
    root = Path(template_root)
    yaml_file = template_pkg(root) / "profiles.yaml"

    with yaml_file.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result: dict[str, ProfileBoundary] = {}
    for name, profile_data in data.get("profiles", {}).items():
        result[name] = ProfileBoundary(
            profile=name,
            description=profile_data.get("description", ""),
            contract_methods=list(profile_data.get("contract", []) or []),
            workspace_methods=list(profile_data.get("workspace", []) or []),
        )

    return result


def require_profile(repo_root: str | Path) -> str:
    """Read profile from nn-config.yaml (authoritative; no heuristic fallback)."""
    root = Path(repo_root).resolve()
    cfg_path = root / "nn-config.yaml"
    if not cfg_path.is_file():
        raise ValueError(
            f"缺少 {cfg_path} — 请从模板复制 nn-config.yaml 并设置 profile，"
            "或运行: ./scripts/new-project.sh <目录> <名> --profile supervised|rl|physical"
        )
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"无法解析 {cfg_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{cfg_path} 须为 YAML 映射（含 profile 字段）")
    profile = str(data.get("profile", "")).strip()
    if profile not in _VALID_PROFILES:
        raise ValueError(
            f"{cfg_path} 的 profile={profile!r} 无效；"
            f"须为: {', '.join(sorted(_VALID_PROFILES))}"
        )
    return profile


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python profile_data.py <template_root>")
        sys.exit(1)

    boundaries = load_profile_boundaries(sys.argv[1])
    for name, b in boundaries.items():
        print(f"\n[{name}] ({b['description']})")
        print(f"  contract: {b['contract_methods']}")
        print(f"  workspace: {b['workspace_methods']}")
