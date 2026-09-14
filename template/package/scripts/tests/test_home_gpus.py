"""家目录 ~/.gpus 开训活闸。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

from lib.home_gpus import (  # noqa: E402
    HomeGpusError,
    allowed_gpus,
    check_env_status,
    enforce_cuda_visible_devices,
    init_project_gpus_yaml,
    parse_gpus_file,
    read_home_gpus,
    shell_export_cuda,
)
from lib.gpu_snapshot import resolve_whitelist  # noqa: E402


def test_parse_gpus_file_tolerant():
    assert parse_gpus_file("2, 3\n") == {2, 3}
    assert parse_gpus_file("") == set()


def test_parse_gpus_file_invalid():
    with pytest.raises(HomeGpusError, match="非法 token"):
        parse_gpus_file("0,abc")


def test_read_home_gpus_missing(tmp_path):
    assert read_home_gpus(str(tmp_path / "nope")) is None


def test_read_home_gpus_empty_fails(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("  \n", encoding="utf-8")
    with pytest.raises(HomeGpusError, match="为空"):
        read_home_gpus(str(p))


def test_read_home_gpus_ok(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    assert read_home_gpus(str(p)) == {2, 3}


def test_allowed_no_file_uses_all_local(tmp_path):
    assert allowed_gpus(local={0, 1, 2}, home_path=str(tmp_path / "missing")) == {0, 1, 2}


def test_allowed_intersects(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3,9\n", encoding="utf-8")
    assert allowed_gpus(local={0, 1, 2, 3}, home_path=str(p)) == {2, 3}


def test_allowed_empty_intersection_fails(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    with pytest.raises(HomeGpusError, match="交集为空"):
        allowed_gpus(local={0, 1}, home_path=str(p))


def test_allowed_cpu_skips_even_with_file(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    assert allowed_gpus(local=set(), home_path=str(p)) == set()


def test_enforce_no_file_does_not_touch_env(tmp_path):
    env: dict[str, str] = {}
    assert enforce_cuda_visible_devices(
        environ=env, local={0, 1}, home_path=str(tmp_path / "missing")
    ) is None
    assert "CUDA_VISIBLE_DEVICES" not in env


def test_enforce_sets_when_unset(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    env: dict[str, str] = {}
    assert enforce_cuda_visible_devices(
        environ=env, local={0, 1, 2, 3}, home_path=str(p)
    ) == "2,3"
    assert env["CUDA_VISIBLE_DEVICES"] == "2,3"


def test_enforce_rejects_out_of_range(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    env = {"CUDA_VISIBLE_DEVICES": "0"}
    with pytest.raises(HomeGpusError, match="不在家目录授权"):
        enforce_cuda_visible_devices(
            environ=env, local={0, 1, 2, 3}, home_path=str(p)
        )


def test_enforce_keeps_valid_subset(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    env = {"CUDA_VISIBLE_DEVICES": "3"}
    assert (
        enforce_cuda_visible_devices(
            environ=env, local={0, 1, 2, 3}, home_path=str(p)
        )
        == "3"
    )
    assert env["CUDA_VISIBLE_DEVICES"] == "3"


def test_enforce_empty_cvd_is_cpu(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    env = {"CUDA_VISIBLE_DEVICES": ""}
    assert (
        enforce_cuda_visible_devices(
            environ=env, local={2, 3}, home_path=str(p)
        )
        == ""
    )


def test_init_project_gpus_yaml_no_file(tmp_path):
    assert (
        init_project_gpus_yaml(local={0, 1}, home_path=str(tmp_path / "missing"))
        == "[0, 1]"
    )


def test_init_project_gpus_yaml_with_file(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    assert init_project_gpus_yaml(local={0, 1, 2, 3}, home_path=str(p)) == "[2, 3]"


def test_check_env_no_file_ok(tmp_path):
    msg, rc = check_env_status(
        environ={}, local={0, 1}, home_path=str(tmp_path / "missing")
    )
    assert rc == 0
    assert msg.startswith("OK:no_home_gpus")


def test_check_env_cvd_out_of_range_fail(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2,3\n", encoding="utf-8")
    msg, rc = check_env_status(
        environ={"CUDA_VISIBLE_DEVICES": "0"},
        local={0, 1, 2, 3},
        home_path=str(p),
    )
    assert rc == 1
    assert msg.startswith("FAIL:")


def test_check_env_empty_file_fail(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("", encoding="utf-8")
    msg, rc = check_env_status(environ={}, local={0, 1}, home_path=str(p))
    assert rc == 1
    assert msg.startswith("FAIL:")


def test_shell_export_no_file(tmp_path):
    env: dict[str, str] = {}
    assert shell_export_cuda(environ=env, local={0}, home_path=str(tmp_path / "x")) == ""
    assert env == {}


def test_shell_export_sets(tmp_path):
    p = tmp_path / ".gpus"
    p.write_text("2\n", encoding="utf-8")
    env: dict[str, str] = {}
    assert shell_export_cuda(environ=env, local={2, 3}, home_path=str(p)) == (
        "export CUDA_VISIBLE_DEVICES=2"
    )


def test_resolve_whitelist_no_home_empty_cfg_all_local(tmp_path, monkeypatch):
    (tmp_path / "nn-config.yaml").write_text("gpus: []\n", encoding="utf-8")
    monkeypatch.setattr("lib.gpu_snapshot.detect_local_gpus", lambda: {0, 1, 2})
    monkeypatch.setattr("lib.gpu_snapshot.read_home_gpus", lambda: None)
    monkeypatch.setattr(
        "lib.gpu_snapshot.allowed_gpus", lambda local=None: set(local or {0, 1, 2})
    )
    assert resolve_whitelist(tmp_path) == [0, 1, 2]


def test_resolve_whitelist_home_intersects_cfg(tmp_path, monkeypatch):
    (tmp_path / "nn-config.yaml").write_text("gpus: [0, 1, 2, 3]\n", encoding="utf-8")
    monkeypatch.setattr("lib.gpu_snapshot.detect_local_gpus", lambda: {0, 1, 2, 3})
    monkeypatch.setattr("lib.gpu_snapshot.read_home_gpus", lambda: {2, 3})
    monkeypatch.setattr("lib.gpu_snapshot.allowed_gpus", lambda local=None: {2, 3})
    assert resolve_whitelist(tmp_path) == [2, 3]
