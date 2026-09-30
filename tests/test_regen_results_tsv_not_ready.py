"""tests/test_regen_results_tsv_not_ready.py — Step 0.4: contract 未就绪时的降级语义。

占位 contract（全注释 metrics.py）+ 存量 _runs/results.tsv 曾致 _load_contract
re-raise → rc=1 连坐 governance-sync / new-project（update 源带成绩表时炸立项）。
现语义：跳过 + 可见警告 + rc=0，TSV 原样保留；--header-only 输出空走 fallback。
"""
import pathlib
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "template" / "package" / "scripts"

PLACEHOLDER_METRICS = """# contract/metrics.py — 占位 contract（脚手架期）
# METRIC_KEYS: dict[str, str] = {"val_accuracy": "max"}
# 具体指标在 contract 迁移后填写
"""


def _make_repo(tmp_path, metrics_py=PLACEHOLDER_METRICS, tsv_lines=None):
    (tmp_path / "contract").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contract" / "metrics.py").write_text(metrics_py, encoding="utf-8")
    tsv = tmp_path / "_runs" / "results.tsv"
    if tsv_lines is not None:
        (tmp_path / "_runs").mkdir(parents=True, exist_ok=True)
        tsv.write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")
    return tsv


def _run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "regen_results_tsv.py"), "--repo-root", str(tmp_path), *args],
        capture_output=True, text=True,
    )


def test_placeholder_contract_existing_tsv_skip_keeps_rows(tmp_path):
    """占位 contract + 存量成绩表 → rc=0、TSV 原样保留、stderr 有可见警告。"""
    tsv = _make_repo(tmp_path, tsv_lines=[
        "experiment\tval_acc\tdescription",
        "exp1\t0.5\tr1",
        "exp2\t0.7\tr2",
    ])
    before = tsv.read_text(encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert tsv.read_text(encoding="utf-8") == before, "存量 TSV 被改动"
    assert "未就绪" in r.stderr


def test_header_only_placeholder_contract_empty_stdout_rc0(tmp_path):
    """--header-only → rc=0、stdout 空（new-project.sh 据此走占位表头 fallback）。"""
    _make_repo(tmp_path)
    r = _run(tmp_path, "--header-only")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""
    assert "未就绪" in r.stderr


def test_real_metrics_literal_still_regens_via_stub(tmp_path):
    """metrics.py 有 METRIC_KEYS 字面量 → stub 接管，regen/校验照常（不因本次改动退化）。"""
    metrics = (
        "METRIC_KEYS: dict[str, str] = {'val_accuracy': 'max'}\n"
        "AUXILIARY_KEYS: dict[str, str] = {}\n"
    )
    tsv = _make_repo(tmp_path, metrics_py=metrics, tsv_lines=[
        "experiment\tval_accuracy\tdescription",
        "exp1\t0.5\tr1",
    ])
    r = _run(tmp_path, "--header-only")
    assert r.returncode == 0, r.stderr
    assert "val_accuracy" in r.stdout
    r2 = _run(tmp_path)
    assert r2.returncode == 0, r2.stderr
    assert "校验通过" in r2.stderr
    lines = tsv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "应有表头 + 1 行数据"


def test_template_demo_metrics_empty_dict_skips(tmp_path):
    """Step 0.4 第二层：模板 metrics.py 是 METRIC_KEYS={}（非全注释）→ 同样未就绪。"""
    tpl_metrics = (SCRIPTS.parent / "contract" / "metrics.py").read_text(encoding="utf-8")
    assert "METRIC_KEYS" in tpl_metrics  # drift-lock：模板仍是占位实现
    tsv = _make_repo(tmp_path, metrics_py=tpl_metrics, tsv_lines=[
        "experiment\tval_acc\tdescription",
        "exp1\t0.5\tr1",
    ])
    before = tsv.read_text(encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert tsv.read_text(encoding="utf-8") == before
    assert "未就绪" in r.stderr


def test_import_ok_but_empty_metric_keys_skips(tmp_path):
    """import 成功但 METRIC_KEYS 为空（模板演示 contract）→ 未就绪，不写 12 列 demo 表头。"""
    (tmp_path / "contract").mkdir(parents=True, exist_ok=True)
    (tmp_path / "contract" / "__init__.py").write_text(
        "class Contract:\n"
        "    metric_keys = {}\n"
        "    auxiliary_keys = {}\n"
        "    metric_key = None\n"
        "    def _default_tsv_columns(self):\n"
        "        return ['experiment', 'demo_col']\n"
        "def create_contract(cfg):\n"
        "    return Contract()\n",
        encoding="utf-8",
    )
    tsv = _make_repo(tmp_path, metrics_py="", tsv_lines=[
        "experiment\tval_acc\tdescription",
        "exp1\t0.5\tr1",
    ])
    before = tsv.read_text(encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert tsv.read_text(encoding="utf-8") == before, "demo 表头不应写入"
    assert "METRIC_KEYS 为空" in r.stderr
