"""Load governance_sync_manifest.yaml and expand globs against template package root."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_MANIFEST_NAME = "governance_sync_manifest.yaml"


def manifest_path_for_scripts_lib(scripts_lib_dir: Path) -> Path:
    return scripts_lib_dir / _MANIFEST_NAME


def load_manifest(scripts_lib_dir: Path) -> dict[str, Any]:
    path = manifest_path_for_scripts_lib(scripts_lib_dir)
    if not path.is_file():
        raise FileNotFoundError(f"missing manifest: {path}")
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ImportError("PyYAML required to load governance_sync_manifest.yaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "groups" not in data:
        raise ValueError(f"invalid manifest structure: {path}")
    return data


def iter_group_patterns(manifest: dict[str, Any], group: str) -> list[str]:
    groups = manifest.get("groups") or {}
    raw = groups.get(group) or []
    if not isinstance(raw, list):
        return []
    return [str(p) for p in raw]


def expand_patterns(pkg_root: Path, patterns: list[str]) -> list[str]:
    """Expand globs relative to pkg_root; return repo-relative posix paths."""
    out: list[str] = []
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        if "*" in pat:
            base = pkg_root / pat
            parent = base.parent
            glob_part = base.name
            if not parent.is_dir():
                out.append(pat.replace("\\", "/"))
                continue
            hits = list(parent.glob(glob_part))
            if not hits:
                out.append(pat.replace("\\", "/"))
                continue
            for hit in sorted(hits):
                if hit.is_file():
                    out.append(hit.relative_to(pkg_root).as_posix())
            continue
        out.append(pat.replace("\\", "/"))
    return out


def all_manifest_paths(pkg_root: Path, *, group: str | None = None) -> list[str]:
    manifest = load_manifest(pkg_root / "scripts" / "lib")
    groups = manifest.get("groups") or {}
    names = [group] if group else list(groups.keys())
    paths: list[str] = []
    for name in names:
        paths.extend(expand_patterns(pkg_root, iter_group_patterns(manifest, name)))
    return sorted(set(paths))


def list_stamp_required_relpaths(root: Path) -> list[str]:
    """Write-version 前必齐路径；真源 = manifest 组 ``train_runtime``。

    ``root`` = ``template/package`` 或业务仓根（均须含 ``scripts/lib/governance_sync_manifest.yaml``）。
    """
    return all_manifest_paths(Path(root), group="train_runtime")


def missing_stamp_required(
    root: Path, *, manifest_root: Path | None = None
) -> list[str]:
    """``list_stamp_required_relpaths`` 中在 ``root`` 下不存在为文件的相对路径。

    ``manifest_root``：读清单的根（默认 = ``root``）。governance-sync 写戳前应传
    ``manifest_root=TEMPLATE_PKG``、``root=PROJECT_ROOT``（此时 dest 可能尚无 manifest 副本）。
    """
    root = Path(root)
    src = Path(manifest_root) if manifest_root is not None else root
    return [
        rel
        for rel in list_stamp_required_relpaths(src)
        if not (root / rel).is_file()
    ]
