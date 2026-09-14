"""auto-nn-setup 单测：CUDA 版本解析 + 五档 torch 源映射（§5.1/§5.2）。

连字符脚本 auto-nn-setup.py 不可直接 `import auto_nn_setup`（Python 不把连字符
文件名映射成下划线模块名），按本仓既有惯例（test_nn_config_load_seam.py /
test_run_context_*.py）用 importlib 按 path 加载。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent


def _load_setup():
    path = _SCRIPTS / "auto-nn-setup.py"
    spec = importlib.util.spec_from_file_location("_auto_nn_setup_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_setup = _load_setup()
parse_driver_cuda_version = _setup.parse_driver_cuda_version
map_cuda_to_source = _setup.map_cuda_to_source
SetupFail = _setup.SetupFail
rewrite_pyproject_torch_source = _setup.rewrite_pyproject_torch_source
TorchSource = _setup.TorchSource
parse_gpus_file = _setup.parse_gpus_file
parse_gpu_indices = _setup.parse_gpu_indices
intersect_gpus = _setup.intersect_gpus
read_nnconfig_gpus = _setup.read_nnconfig_gpus
write_nnconfig_gpus = _setup.write_nnconfig_gpus
read_global_gpus_file = _setup.read_global_gpus_file
backup_files = _setup.backup_files
restore_files = _setup.restore_files
drop_backups = _setup.drop_backups
probe_system_pyyaml = _setup.probe_system_pyyaml
build_setup_report = _setup.build_setup_report
apply_setup = _setup.apply_setup
main = _setup.main


def test_parse_cuda_version_typical():
    out = ("+-----------------------------------------------------------------------------+\n"
           "| NVIDIA-SMI 535.183.01   Driver Version: 535.183.01   CUDA Version: 12.4     |\n"
           "+-----------------------------------------------------------------------------+\n")
    assert parse_driver_cuda_version(out) == "12.4"


def test_parse_cuda_version_missing():
    assert parse_driver_cuda_version("no cuda here") is None
    assert parse_driver_cuda_version("") is None


def test_map_cu124_high():
    assert map_cuda_to_source("12.8").source_name == "pytorch-cu124"
    assert map_cuda_to_source("12.4").url_suffix == "cu124"


def test_map_cu121_band():
    s = map_cuda_to_source("12.2")
    assert s.source_name == "pytorch-cu121"
    assert s.torch_version == "2.5.1+cu121"
    assert s.torchvision_version == "0.20.1+cu121"
    assert s.url_suffix == "cu121"
    # 锁定下界 12.1（inclusive）——元组比较对边界最敏感
    assert map_cuda_to_source("12.1").source_name == "pytorch-cu121"


def test_map_cu118_band():
    s = map_cuda_to_source("11.8")
    assert s.source_name == "pytorch-cu118"
    s2 = map_cuda_to_source("12.0")
    assert s2.source_name == "pytorch-cu118"


def test_map_old_driver_fails():
    with pytest.raises(SetupFail):
        map_cuda_to_source("11.7")


def test_map_no_gpu_to_cpu():
    s = map_cuda_to_source(None)
    assert s.torch_version == "2.5.1+cpu"
    assert s.source_name == "pytorch-cpu"
    assert s.url_suffix == "cpu"


CURRENT_PYPROJECT = """[tool.poetry]
name = "auto-nn-experiment"
version = "0.1.0"

[tool.poetry.dependencies]
python = ">=3.10,<3.14"
torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }
torchvision = { version = "0.20.1+cu124", source = "pytorch-cu124" }

[tool.poetry.group.dev.dependencies]

[[tool.poetry.source]]
name = "PyPI"
priority = "primary"

[[tool.poetry.source]]
name = "pytorch-cu124"
url = "https://download.pytorch.org/whl/cu124"
priority = "explicit"
"""


def test_rewrite_cu124_to_cu121_all_four_spots():
    src = TorchSource("2.5.1+cu121", "0.20.1+cu121", "pytorch-cu121", "cu121")
    out = rewrite_pyproject_torch_source(CURRENT_PYPROJECT, src)
    assert 'torch = { version = "2.5.1+cu121", source = "pytorch-cu121" }' in out
    assert 'torchvision = { version = "0.20.1+cu121", source = "pytorch-cu121" }' in out
    assert 'name = "pytorch-cu121"' in out
    assert 'url = "https://download.pytorch.org/whl/cu121"' in out


def test_rewrite_does_not_touch_pypi_block():
    src = TorchSource("2.5.1+cpu", "0.20.1+cpu", "pytorch-cpu", "cpu")
    out = rewrite_pyproject_torch_source(CURRENT_PYPROJECT, src)
    assert 'name = "PyPI"\npriority = "primary"' in out  # PyPI 段原样


def test_rewrite_to_cpu_url():
    src = TorchSource("2.5.1+cpu", "0.20.1+cpu", "pytorch-cpu", "cpu")
    out = rewrite_pyproject_torch_source(CURRENT_PYPROJECT, src)
    assert 'url = "https://download.pytorch.org/whl/cpu"' in out
    assert 'source = "pytorch-cpu"' in out


def test_rewrite_idempotent():
    src = TorchSource("2.5.1+cu124", "0.20.1+cu124", "pytorch-cu124", "cu124")
    assert rewrite_pyproject_torch_source(CURRENT_PYPROJECT, src) == CURRENT_PYPROJECT


def test_rewrite_missing_pytorch_source_fails():
    broken = CURRENT_PYPROJECT.replace(
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n', ''
    )
    src = TorchSource("2.5.1+cu121", "0.20.1+cu121", "pytorch-cu121", "cu121")
    with pytest.raises(SetupFail):
        rewrite_pyproject_torch_source(broken, src)


# ---------- §6 GPU 白名单 ----------

def test_parse_gpus_file_tolerant():
    assert parse_gpus_file("2, 3\n") == {2, 3}
    assert parse_gpus_file("0,1,2") == {0, 1, 2}
    assert parse_gpus_file("5") == {5}
    assert parse_gpus_file("") == set()


def test_parse_gpus_file_invalid_token():
    with pytest.raises(SetupFail):
        parse_gpus_file("0,abc,2")


def test_parse_gpu_indices():
    assert parse_gpu_indices("0\n1\n2\n") == {0, 1, 2}
    assert parse_gpu_indices("") == set()


def test_intersect_normal():
    assert intersect_gpus({0, 1, 2}, {1, 2, 3}) == {1, 2}


def test_intersect_empty_fails():
    with pytest.raises(SetupFail):
        intersect_gpus({0, 1}, {5, 6})


def test_nnconfig_gpus_roundtrip():
    cfg = "profile: default\ngpus: 0,1\nmax_parallel: 2\n"
    assert read_nnconfig_gpus(cfg) == "0,1"
    out = write_nnconfig_gpus(cfg, "2,3")
    assert read_nnconfig_gpus(out) == "2,3"
    # 非 gpus 行不动
    assert "profile: default" in out
    assert "max_parallel: 2" in out


def test_read_global_gpus_file_normal(tmp_path):
    g = tmp_path / "gpus"
    g.write_text("0,1,2\n", encoding="utf-8")
    assert read_global_gpus_file(str(g)) == {0, 1, 2}


def test_read_global_gpus_file_missing():
    assert read_global_gpus_file("/nonexistent/path/should/not/exist/.gpus") is None


def test_read_global_gpus_file_empty(tmp_path):
    g = tmp_path / "gpus"
    g.write_text("", encoding="utf-8")
    with pytest.raises(SetupFail):
        read_global_gpus_file(str(g))


def test_write_nnconfig_gpus_no_gpus_line():
    with pytest.raises(SetupFail):
        write_nnconfig_gpus("profile: default\nmax_parallel: 2\n", "2,3")


def test_read_nnconfig_gpus_missing():
    assert read_nnconfig_gpus("profile: default\nmax_parallel: 2\n") is None


# ---------- gpus 多格式（inline / flow list / block list）----------
# 背景：迁移过来的业务仓 nn-config.yaml 用 YAML block list 写 gpus
# （`gpus:\n- 2\n- 3`），旧正则 \s* 吃掉换行把 `- 2` 当 token →
# parse 报「~/.gpus 含非法 token '-'」误伤。read 须正确读出 {2,3}。

def test_read_nnconfig_gpus_block_list():
    cfg = "profile: default\ngpus:\n- 2\n- 3\nmax_parallel: 2\n"
    assert read_nnconfig_gpus(cfg) == "2,3"


def test_read_nnconfig_gpus_flow_list():
    cfg = "profile: default\ngpus: [2, 3]\nmax_parallel: 2\n"
    assert read_nnconfig_gpus(cfg) == "2,3"


def test_write_nnconfig_gpus_block_list_to_flow():
    """block list 输入：write 整块替换成 flow list，不留孤儿 `- 3` 行。"""
    cfg = "profile: default\ngpus:\n- 2\n- 3\nmax_parallel: 2\n"
    out = write_nnconfig_gpus(cfg, "5,6")
    assert read_nnconfig_gpus(out) == "5,6"          # roundtrip 读得回
    assert "- 3" not in out                           # 旧 bug：孤儿列表项残留
    assert "max_parallel: 2" in out                   # 非相邻行不动


def test_write_nnconfig_gpus_outputs_yaml_list():
    """write 输出必须是 YAML list（`gpus: [...]`），check-env.sh 才认——
    写成字符串 `gpus: 2, 3` 会被 check-env 当成无白名单静默忽略。"""
    cfg = "profile: default\ngpus: 0,1\nmax_parallel: 2\n"
    out = write_nnconfig_gpus(cfg, "2,3")
    assert "gpus: [" in out


# ---------- §7 备份/还原 + §10.2 系统 pyyaml 探针 ----------

def test_backup_restore_roundtrip(tmp_path):
    f = tmp_path / "pyproject.toml"
    f.write_text("original", encoding="utf-8")
    backup_files([str(f)])
    assert (tmp_path / "pyproject.toml.bak").exists()
    f.write_text("mutated", encoding="utf-8")
    restore_files([str(f)])
    assert f.read_text(encoding="utf-8") == "original"
    assert not (tmp_path / "pyproject.toml.bak").exists()  # restore 即清 .bak


def test_drop_backups(tmp_path):
    f = tmp_path / "x.toml"
    f.write_text("x", encoding="utf-8")
    backup_files([str(f)])
    drop_backups([str(f)])
    assert not (tmp_path / "x.toml.bak").exists()


def test_backup_files_missing_raises_setupfail(tmp_path):
    # 源文件不存在 → SetupFail（不抛原始 FileNotFoundError，与模块约定一致）
    with pytest.raises(SetupFail):
        backup_files([str(tmp_path / "nope.toml")])


def test_probe_system_pyyaml_returns_bool():
    # 不论系统是否装 pyyaml，都应返回 bool（环境无关）
    assert isinstance(probe_system_pyyaml(), bool)


# ---------- §4/§8 编排：build_setup_report + main ----------

def test_build_setup_report_structures_detection(tmp_path):
    # 造一个 nn-config + pyproject
    (tmp_path / "nn-config.yaml").write_text("profile: default\ngpus: 9,9\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8",
    )
    # 显式注入检测：CUDA=12.2 → cu121；本机 GPU {0,1,2}；~/.gpus {1,2,8} → 交集 {1,2}
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.2",
        detect_local_gpus=lambda: {0, 1, 2},
        read_global=lambda: {1, 2, 8},
    )
    assert report["source"].source_name == "pytorch-cu121"
    assert report["gpus_new"] == {1, 2}
    assert report["gpus_old"] == {9}
    assert "pyproject.toml" in report["planned_writes"]


def test_main_dry_run_does_not_write(monkeypatch, tmp_path):
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text("gpus: 0,1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(_setup, "_detect_cuda", lambda: "12.4")
    monkeypatch.setattr(_setup, "_detect_local_gpus", lambda: {0, 1})
    monkeypatch.setattr(_setup, "read_global_gpus_file", lambda path="~/.gpus": {0, 1})
    rc = main(["--dry-run", "--project-root", str(tmp_path)])
    assert rc == 0
    assert cfg.read_text(encoding="utf-8") == "gpus: 0,1\n"  # 未改（cu124 不变档 + gpus 未变）


def test_main_missing_gpus_file_skips_whitelist(monkeypatch, tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text("gpus: 0,1\n", encoding="utf-8")
    monkeypatch.setattr(_setup, "_detect_cuda", lambda: "12.4")
    monkeypatch.setattr(_setup, "_detect_local_gpus", lambda: {0, 1})
    monkeypatch.setattr(_setup, "read_global_gpus_file", lambda path="~/.gpus": None)
    rc = main(["--dry-run", "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "跳过" in out and "未找到 ~/.gpus" in out


# ---------- §4 检测项 1-3：Python 版本 / Poetry / venv ----------

def test_build_setup_report_detects_env(tmp_path):
    (tmp_path / "nn-config.yaml").write_text("gpus: 0,1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n', encoding="utf-8")
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.4",
        detect_local_gpus=lambda: {0, 1},
        read_global=lambda: {0, 1},
        detect_python=lambda: (3, 11, 5),
        detect_poetry=lambda: True,
        detect_venv=lambda root: True,
    )
    assert report["python_version"] == (3, 11, 5)
    assert report["python_ok"] is True
    assert report["poetry_present"] is True
    assert report["venv_ready"] is True
    # 源匹配 + venv 好 + gpus 不变 → 一切就绪，无需改
    assert report["need_pyproject_edit"] is False
    assert report["need_install"] is False
    assert report["planned_writes"] == []


def test_build_setup_report_missing_pyproject_fails(tmp_path):
    # §4 检测项 2「齐全」：pyproject 不存在 → clean SetupFail（非 open() traceback）
    with pytest.raises(SetupFail):
        build_setup_report(str(tmp_path), detect_cuda=lambda: "12.4",
                           detect_local_gpus=lambda: set())  # cpu 盒子，免 ~/.gpus 依赖


def test_build_setup_report_python_out_of_range_flagged(tmp_path):
    # cpu 盒子（无 GPU）避免 ~/.gpus 依赖，纯测 python 区间判定
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n', encoding="utf-8")
    low = build_setup_report(str(tmp_path), detect_cuda=lambda: "12.4",
                             detect_local_gpus=lambda: set(),
                             detect_python=lambda: (3, 9, 1))
    assert low["python_ok"] is False  # 下界 3.10 以下
    high = build_setup_report(str(tmp_path), detect_cuda=lambda: "12.4",
                              detect_local_gpus=lambda: set(),
                              detect_python=lambda: (3, 14, 0))
    assert high["python_ok"] is False  # 上界 3.14（不含）


def test_build_setup_report_venv_broken_plans_install(tmp_path):
    # 源匹配（cu124）但 venv 坏 → 单独 install 条目，无需改 pyproject
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n', encoding="utf-8")
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.4",
        detect_local_gpus=lambda: set(),
        detect_poetry=lambda: True,
        detect_venv=lambda root: False,
    )
    assert report["need_pyproject_edit"] is False
    assert report["need_install"] is True  # §4 检测项 3：venv 坏也要建
    assert any("venv" in w or "install" in w for w in report["planned_writes"])
    assert "pyproject.toml" not in report["planned_writes"]


def test_apply_setup_missing_poetry_returns_fail(monkeypatch, tmp_path, capsys):
    # poetry 缺 + 需 install → clean FAIL（rc=1，不抛 traceback，不调真 poetry）
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n', encoding="utf-8")
    monkeypatch.setattr(_setup, "ensure_system_pyyaml", lambda: None)  # 跳过系统 pip 探针
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.4",
        detect_local_gpus=lambda: set(),
        detect_poetry=lambda: False,   # 关键：poetry 缺
        detect_venv=lambda root: False,  # venv 坏 → need_install True
    )
    rc = apply_setup(report)
    assert rc == 1  # apply_setup 内部吞 SetupFail 返回 1（不向调用方抛）
    out = capsys.readouterr().out
    assert "poetry" in out
    assert "未安装" in out


def test_apply_setup_no_drift_no_rollback_when_install_never_ran(monkeypatch, tmp_path, capsys):
    # M-1：poetry 缺 → 在 backup/install 之前就 FAIL。
    # 即便 need_pyproject_edit=True，也未备份、未 install ——
    # 不可谎报「回滚 pyproject」（无物可还原）或「.venv 已写入」（.venv 未动）。
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        'torchvision = { version = "0.20.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8")
    original = pyproj.read_text(encoding="utf-8")
    monkeypatch.setattr(_setup, "ensure_system_pyyaml", lambda: None)  # 跳过系统 pip 探针
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.2",          # → cu121（源需改 → need_pyproject_edit True）
        detect_local_gpus=lambda: set(),     # 无 GPU → 不写白名单、不碰 nn-config
        detect_poetry=lambda: False,         # poetry 缺 → 在 backup/install 前 FAIL
        detect_venv=lambda root: False,      # venv 坏 → need_install True
    )
    assert report["need_pyproject_edit"] is True
    rc = apply_setup(report)
    assert rc == 1
    out = capsys.readouterr().out
    assert "回滚 pyproject" not in out   # M-1：未备份 → 不报「回滚」
    assert ".venv" not in out            # M-1：未 install → 不报 venv-drift
    assert pyproj.read_text(encoding="utf-8") == original  # 文件未被 truncate/改写


def test_build_setup_report_missing_nnconfig_with_gpus_fails(tmp_path):
    # §4 对称守卫（I3）：有 GPU 要写白名单时，nn-config 缺 → clean SetupFail
    # （否则 apply 期 open(nncfg) 抛原始 FileNotFoundError traceback）
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n', encoding="utf-8")
    with pytest.raises(SetupFail):
        build_setup_report(str(tmp_path), detect_cuda=lambda: "12.4",
                           detect_local_gpus=lambda: {0, 1},
                           read_global=lambda: {0, 1})  # 有 GPU → 要写白名单 → 缺 nn-config FAIL


def test_apply_setup_rollback_restores_pyproject(monkeypatch, tmp_path, capsys):
    # I5/回滚：改源 + install 中途失败 → pyproject 应回滚到原内容、.bak 清掉；
    # 且提示 .venv 未回滚（install 真跑过）
    monkeypatch.setattr(_setup, "ensure_system_pyyaml", lambda: None)  # 跳过系统 pip 探针
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        'torchvision = { version = "0.20.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8")
    (tmp_path / "nn-config.yaml").write_text("gpus: 0,1\n", encoding="utf-8")
    original = pyproj.read_text(encoding="utf-8")
    # CUDA=12.2 → cu121（源需改）；本机 GPU {0,1}；~/.gpus {0,1} → 交集 {0,1}（不变）
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.2",
        detect_local_gpus=lambda: {0, 1},
        read_global=lambda: {0, 1},
        detect_poetry=lambda: True,
        detect_venv=lambda root: True,
    )
    assert report["need_pyproject_edit"] is True
    # install 抛 SetupFail（模拟重装失败）——改写已成功、backup 已做，故 install_ran/backed_up 均 True
    def _fail(r):
        raise SetupFail("install 失败")
    monkeypatch.setattr(_setup, "_run_poetry", _fail)
    # except 内 poetry_present=True 会触发 re-lock subprocess —— 假掉，避免触真 poetry
    monkeypatch.setattr(_setup.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 0})())
    rc = apply_setup(report)
    assert rc == 1
    assert pyproj.read_text(encoding="utf-8") == original  # 回滚到原内容
    assert not (tmp_path / "pyproject.toml.bak").exists()  # restore 即清 .bak
    out = capsys.readouterr().out
    assert "回滚 pyproject/poetry.lock" in out  # 备份过 → 真回滚
    assert ".venv" in out and "未回滚" in out  # install 真跑过 → I5 venv-drift 提示


def test_run_poetry_lock_uses_bare_lock_no_update_flag_removed(monkeypatch, tmp_path):
    # 回归（issue 1）：Poetry 2.x 移除了 --no-update（默认即 no-update），带上报未知参数失败。
    # _run_poetry 的 lock 调用必须是裸 ["poetry", "lock"]，不可带 --no-update。
    calls = []

    def _fake_run(args, *a, **k):
        calls.append(list(args))
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(_setup.subprocess, "run", _fake_run)
    _setup._run_poetry({"project_root": str(tmp_path)})
    lock_calls = [c for c in calls if "lock" in c]
    assert lock_calls, "应当调用 poetry lock"
    assert lock_calls[0] == ["poetry", "lock"], (
        f"lock 调用不可带 --no-update（Poetry 2.x 已移除）：{lock_calls[0]}"
    )


def test_apply_setup_nnconfig_backed_up_during_gpus_write_then_cleaned(monkeypatch, tmp_path):
    # nit #1：写 gpus 时 nn-config 必须已备份（.bak 存在）——防 truncate-then-write 中途被杀
    # 截断丢内容；smoke 通过后 .bak 清掉、无残留。
    monkeypatch.setattr(_setup, "ensure_system_pyyaml", lambda: None)
    nncfg = tmp_path / "nn-config.yaml"
    nncfg.write_text("profile: default\ngpus: 9\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8")
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.4",
        detect_local_gpus=lambda: {0, 1},
        read_global=lambda: {0, 1},
        detect_poetry=lambda: True,
        detect_venv=lambda root: True,
    )
    assert report["need_pyproject_edit"] is False
    assert report["need_install"] is False
    bak_seen = {"yes": False}

    def _smoke_spy(*a, **k):
        if (tmp_path / "nn-config.yaml.bak").exists():
            bak_seen["yes"] = True
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(_setup.subprocess, "run", _smoke_spy)
    rc = apply_setup(report)
    assert rc == 0
    assert bak_seen["yes"] is True
    assert "gpus: [0, 1]" in nncfg.read_text(encoding="utf-8")
    assert not (tmp_path / "nn-config.yaml.bak").exists()


def test_apply_setup_keeps_gpus_and_cleans_backup_on_smoke_fail(monkeypatch, tmp_path, capsys):
    # nit #1 + §8：smoke 失败时 gpus 是安全收敛——保留新值、不清回旧值；
    # 但写时建的 .bak 要清掉（无残留）。pyproject 未动（不改源）→ 不报「回滚」。
    monkeypatch.setattr(_setup, "ensure_system_pyyaml", lambda: None)
    nncfg = tmp_path / "nn-config.yaml"
    nncfg.write_text("profile: default\ngpus: 9\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        'torch = { version = "2.5.1+cu124", source = "pytorch-cu124" }\n'
        '[[tool.poetry.source]]\nname = "pytorch-cu124"\n'
        'url = "https://download.pytorch.org/whl/cu124"\npriority = "explicit"\n',
        encoding="utf-8")
    report = build_setup_report(
        str(tmp_path),
        detect_cuda=lambda: "12.4",
        detect_local_gpus=lambda: {0, 1},
        read_global=lambda: {0, 1},
        detect_poetry=lambda: True,
        detect_venv=lambda root: True,
    )
    monkeypatch.setattr(_setup.subprocess, "run",
                        lambda *a, **k: type("R", (), {"returncode": 1})())
    rc = apply_setup(report)
    assert rc == 1
    txt = nncfg.read_text(encoding="utf-8")
    assert "gpus: [0, 1]" in txt
    assert not (tmp_path / "nn-config.yaml.bak").exists()
    out = capsys.readouterr().out
    assert "回滚 pyproject" not in out
