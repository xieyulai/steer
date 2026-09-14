"""L3-A1: verify_governance_sync_dest.sh 端到端验证 dest 镜像下发 presets + train_branch* + auto_mode lib。"""
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _setup_dest(src_template_root: Path) -> Path:
    """造一个 fake dest 仓根：含 template/package/scripts/* + dest/scripts/governance-sync.sh + scripts/lib/。
    然后用真 governance-sync.sh 跑（带 --template-root 指向 src template）。"""
    dest = Path(tempfile.mkdtemp())
    # 1) cp 整个 template 仓根到 dest（让 governance-sync 能找到 $TEMPLATE_PKG/scripts/*）
    import shutil
    shutil.copytree(src_template_root, dest / "template")
    # 2) 造一个 minimal dest/scripts/：cp 真 governance-sync.sh + 整个 scripts/lib/（供 source 引用）
    (dest / "scripts").mkdir()
    shutil.copy(src_template_root / "package" / "scripts" / "governance-sync.sh",
                dest / "scripts" / "governance-sync.sh")
    shutil.copytree(src_template_root / "package" / "scripts" / "lib",
                    dest / "scripts" / "lib")
    # 3) 造个 minimal dest .auto-nn/（让 abcde_migrate 不报缺目录）
    (dest / ".auto-nn").mkdir()
    return dest


def test_verify_pass_when_both_libs_synced(tmp_path, monkeypatch):
    """端到端：dest 跑 governance-sync 后，presets + train_branch* + auto_mode + refresh 脚本真存在 → exit 0。"""
    # 此测试在 template/package/scripts/tests/ 下；
    # ..parent = template/package/scripts/；..parent.parent = template/package/；
    # ..parent.parent.parent = template/  ← 仓根（含 package/）
    template_root = Path(__file__).parent.parent.parent.parent
    if not (template_root / "package" / "scripts" / "governance-sync.sh").exists():
        import pytest
        pytest.skip("template root not found")
    dest = _setup_dest(template_root)
    script = (Path(__file__).parent.parent / "verify_governance_sync_dest.sh").resolve()
    result = subprocess.run(
        ["bash", str(script), "--dest", str(dest)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"FAIL stdout={result.stdout}\nstderr={result.stderr}"
    assert (dest / "scripts/lib/presets.py").exists()
    assert (dest / "scripts/lib/train_branch.py").exists()
    assert (dest / "scripts/lib/train_branch_types.py").exists()
    assert (dest / "scripts/lib/adapter_accept.py").exists()
    assert (dest / "scripts/lib/framework_binding.py").exists()
    assert (dest / "scripts/lib/auto_mode.py").exists()
    assert (dest / "scripts/refresh-human-guidance-baseline.sh").exists()
    assert (dest / "scripts/refresh-human-guidance-baseline.sh").stat().st_mode & 0o111
    assert "PASS:" in result.stdout
    assert "train_branch" in result.stdout
    assert "auto_mode" in result.stdout
    assert "refresh-human-guidance-baseline" in result.stdout
    assert (dest / "contract/__main__.py").exists()
    assert "contract/__main__" in result.stdout
