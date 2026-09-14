# scripts/abcde_migrate.py
"""Migrate existing framework project → generate ABCDE manual.
Used for projects that pre-date the redesign (e.g., mammoth-cl, fmnist-v2).
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

from init_workflow import detect
from init_o3_abcde import write_init_outputs


_TEMPLATES_SUBDIR = "skills/maintainer/auto-nn-init/templates"


def _resolve_template_root(repo_root: Path) -> Path | None:
    """复用 lib/nn-state.sh::nn_resolve_template_root 解析维护仓根。

    三档：$NN_TEMPLATE_ROOT env > ~/.cursor/skills/auto-nn-* symlink > .auto-nn/template-root
    """
    lib = Path(__file__).parent / "lib" / "nn-state.sh"
    if not lib.exists():
        return None
    try:
        out = subprocess.run(
            ["bash", "-c", f'source "{lib}" && nn_resolve_template_root "{repo_root}"'],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    resolved = out.stdout.strip()
    return Path(resolved) if resolved else None


def _resolve_templates_dir(repo_root: Path, explicit: Path | str | None) -> Path | None:
    """解析 ABCDE 模板目录（v1.28+ 业务仓不再持有 skills/）。

    优先级：
      1. 显式入参 templates_dir
      2. 环境变量 NN_ABCDE_TEMPLATES_DIR（运维临时覆盖）
      3. <维护仓根>/skills/maintainer/auto-nn-init/templates/（nn_resolve_template_root 解析）
      4. <this_file>/../../skills/maintainer/auto-nn-init/templates/
         （仅当该路径有 .template-maintainer 标志 — 维护仓直跑 fallback）
    """
    if explicit:
        return Path(explicit)
    env_dir = os.environ.get("NN_ABCDE_TEMPLATES_DIR")
    if env_dir:
        return Path(env_dir)
    tmpl_root = _resolve_template_root(repo_root)
    if tmpl_root:
        cand = tmpl_root / _TEMPLATES_SUBDIR
        if cand.is_dir():
            return cand
    # 维护仓直跑 fallback（仅当祖先路径有 .template-maintainer 标志）
    dev_root = Path(__file__).parent.parent.parent
    if (dev_root / ".template-maintainer").exists():
        cand = dev_root / _TEMPLATES_SUBDIR
        if cand.is_dir():
            return cand
    return None


def migrate_existing_project(repo_root: Path | str, templates_dir: Path | str | None = None) -> dict:
    """Detect workflow via detect(); write references/manual/abcde-manual.md if absent.
    Idempotent: skip if manual exists.

    templates_dir 解析链：见 _resolve_templates_dir。
    v1.28+ 不再读业务仓 skills/maintainer/...（业务仓已不再持有）。

    PR2.3: 走 init_workflow.detect() 单一入口（workflow + object_type + pattern），
    write_init_outputs 用新 4-参签名（target_root / workflow / object_type /
    templates_dir / pattern）。
    """
    repo_root = Path(repo_root)
    md_path = repo_root / "references" / "manual" / "abcde-manual.md"

    if md_path.exists():
        return {"workflow": "skipped (already migrated)",
                "md_path": str(md_path)}

    result = detect(repo_root=repo_root, source_root=repo_root)
    resolved = _resolve_templates_dir(repo_root, templates_dir)
    if resolved is None or not resolved.is_dir():
        raise FileNotFoundError(
            f"无法定位 ABCDE 模板目录（v1.28+ 业务仓不再持有 skills/）："
            f"显式传 templates_dir / 设 $NN_ABCDE_TEMPLATES_DIR / "
            f"或确保 .auto-nn/template-root 指向维护仓根"
        )
    templates_dir = resolved

    out = write_init_outputs(
        target_root=repo_root,
        workflow=result.workflow,
        object_type=result.object_type,
        templates_dir=templates_dir,
        pattern=result.pattern,
    )
    out["workflow"] = result.workflow.value
    out["object_type"] = result.object_type
    out["pattern"] = result.pattern
    out["templates_dir"] = str(templates_dir)
    return out


if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", required=True)
    p.add_argument("--templates-dir", default=None,
                   help="可选：覆盖 templates 目录（默认从 repo_root/skills/.../templates/ 解析；"
                        "也可用 NN_ABCDE_TEMPLATES_DIR 环境变量）")
    a = p.parse_args()
    print(json.dumps(migrate_existing_project(Path(a.repo_root), templates_dir=a.templates_dir), indent=2))