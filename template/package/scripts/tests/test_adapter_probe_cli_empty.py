"""probe_cfg_to_cli_empty_passthrough / static_scan — adapter 空串 CLI 探测。"""
from __future__ import annotations

import textwrap
from pathlib import Path
from types import ModuleType

import pytest

from lib.adapter_accept import (
    probe_cfg_to_cli_empty_passthrough,
    static_scan_cfg_to_cli_empty_passthrough,
)


def _mod(source: str, name: str = "ws_probe") -> ModuleType:
    mod = ModuleType(name)
    exec(textwrap.dedent(source), mod.__dict__)  # noqa: S102
    return mod


def test_probe_missing_cfg_to_cli_returns_not_probed():
    mod = _mod(
        """
        def build_command(cfg, exp_dir):
            return []
        """
    )
    probed, flags = probe_cfg_to_cli_empty_passthrough(mod)
    assert probed is False
    assert flags == []


def test_probe_missing_build_command_returns_not_probed():
    mod = _mod(
        """
        CFG_TO_CLI = {"ALPHA": "alpha"}
        """
    )
    probed, flags = probe_cfg_to_cli_empty_passthrough(mod)
    assert probed is False
    assert flags == []


def test_probe_bad_passthrough_detects_empty_flag():
    mod = _mod(
        """
        CFG_TO_CLI = {"ALPHA": "alpha", "LR": "lr"}

        def build_command(cfg, exp_dir):
            cmd = ["python", "main.py"]
            for cfg_key, cli_key in CFG_TO_CLI.items():
                if cfg_key in cfg and cfg[cfg_key] is not None:
                    cmd.extend([f"--{cli_key}", str(cfg[cfg_key])])
            return cmd
        """
    )
    probed, flags = probe_cfg_to_cli_empty_passthrough(mod)
    assert probed is True
    assert "alpha" in flags


def test_probe_append_cfg_cli_passes():
    mod = _mod(
        """
        from lib.adapter_accept import append_cfg_cli

        CFG_TO_CLI = {"ALPHA": "alpha", "LR": "lr"}

        def build_command(cfg, exp_dir):
            cmd = ["python", "main.py"]
            append_cfg_cli(cmd, cfg, CFG_TO_CLI)
            return cmd
        """
    )
    probed, flags = probe_cfg_to_cli_empty_passthrough(mod)
    assert probed is True
    assert flags == []


def test_static_scan_detects_is_not_none_passthrough(tmp_path: Path):
    ws = tmp_path / "__init__.py"
    ws.write_text(
        textwrap.dedent(
            """
            CFG_TO_CLI = {"ALPHA": "alpha"}

            def build_command(cfg, exp_dir):
                cmd = []
                for cfg_key, cli_key in CFG_TO_CLI.items():
                    if cfg_key in cfg and cfg[cfg_key] is not None:
                        cmd.extend([f"--{cli_key}", str(cfg[cfg_key])])
                return cmd
            """
        ),
        encoding="utf-8",
    )
    hits = static_scan_cfg_to_cli_empty_passthrough(ws)
    assert hits


def test_static_scan_skips_when_append_cfg_cli_imported(tmp_path: Path):
    ws = tmp_path / "__init__.py"
    ws.write_text(
        textwrap.dedent(
            """
            from lib.adapter_accept import append_cfg_cli
            CFG_TO_CLI = {"ALPHA": "alpha"}

            def build_command(cfg, exp_dir):
                cmd = []
                append_cfg_cli(cmd, cfg, CFG_TO_CLI)
                return cmd
            """
        ),
        encoding="utf-8",
    )
    assert static_scan_cfg_to_cli_empty_passthrough(ws) == []


def test_static_scan_missing_file():
    assert static_scan_cfg_to_cli_empty_passthrough(Path("/nonexistent/__init__.py")) == []
