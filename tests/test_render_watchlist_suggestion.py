"""tests/test_render_watchlist_suggestion.py — watchlist suggest 段"""
import importlib.util
import pathlib
import sys

# build-run-context.py uses hyphens — load via importlib
_SCRIPT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "template/package/scripts/build-run-context.py"
)
_spec = importlib.util.spec_from_file_location("build_run_context", str(_SCRIPT_PATH))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_run_context"] = _mod
_spec.loader.exec_module(_mod)
_render_watchlist_suggestion = _mod._render_watchlist_suggestion


def test_render_empty_when_no_exps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = {"repo_root": str(tmp_path)}
    assert _render_watchlist_suggestion(ctx) == ""


def test_render_top5_from_exps(tmp_path, monkeypatch):
    """3 个 exp_dir × 4 cfg keys（2 在 watchlist, 2 不在）→ 输出 top-2"""
    monkeypatch.chdir(tmp_path)

    (tmp_path / "nn-config.yaml").write_text(
        'ledger:\n  watchlist: [LR, BATCH_SIZE]\n'
    )
    runs = tmp_path / "_runs" / "exp"
    runs.mkdir(parents=True)
    for tag in ["a", "b", "c"]:
        d = runs / f"exp_{tag}"
        d.mkdir()
        (d / "config.json").write_text(
            '{"LR": 0.001, "BATCH_SIZE": 32, "MIXUP": 0.2, "WARMUP": 100}'
        )

    ctx = {"repo_root": str(tmp_path)}
    out = _render_watchlist_suggestion(ctx)
    assert "MIXUP" in out
    assert "WARMUP" in out
    assert "LR" not in out  # 已在 watchlist
    assert "Watchlist 建议" in out
