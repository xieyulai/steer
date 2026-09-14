"""家目录 GPU 授权（~/.gpus）——开训活闸的单一真源。

规则（对人：家目录允许用的显卡名单）：
- 文件不存在 = 没立规矩 = 本机全部卡都能用（不改 CUDA_VISIBLE_DEVICES）
- 文件存在 = 每次开训收紧为「名单 ∩ 本机」；指定名单外的卡 → 拒绝
- 文件存在但为空，或与本机交集为空 → 拒绝（立了规矩但授权是空的）
- 本机无 GPU（CPU 盒子）→ 跳过，即使有 ~/.gpus

本模块只依赖标准库，且 **不得在模块顶层 import torch**
（train.py 必须在 import torch 之前调用 enforce，否则名单外的卡仍会被进程看见）。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping, MutableMapping

_GPUS_DELIM_RE = re.compile(r"[,\s]+")
DEFAULT_GPUS_PATH = "~/.gpus"


class HomeGpusError(Exception):
    """家目录显卡名单不合法，或当前占用超出授权。"""


def parse_gpus_file(content: str) -> set[int]:
    """解析 GPU 索引列表（逗号/空格/换行分隔）。空串 → 空集；非法 token raise。"""
    nums: set[int] = set()
    for tok in _GPUS_DELIM_RE.split((content or "").strip()):
        if not tok:
            continue
        if not tok.isdigit():
            raise HomeGpusError(
                f"GPU 索引列表含非法 token: {tok!r}（应为逗号分隔的非负整数索引）"
            )
        nums.add(int(tok))
    return nums


def read_home_gpus(path: str = DEFAULT_GPUS_PATH) -> set[int] | None:
    """读 ~/.gpus。不存在 → None（无规矩）；存在但解析后为空 → raise。"""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return None
    with open(expanded, encoding="utf-8") as f:
        gpus = parse_gpus_file(f.read())
    if not gpus:
        raise HomeGpusError(
            f"{path} 解析后为空（空文件或全是空白）。请填入授权的 GPU 索引，"
            f"例如 echo \"0,1\" > {path}。"
        )
    return gpus


def detect_local_gpus() -> set[int]:
    """本机物理 GPU 索引（nvidia-smi）。无卡 / 无 nvidia-smi → 空集。不 import torch。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if r.returncode != 0:
        return set()
    return {
        int(line.strip())
        for line in (r.stdout or "").splitlines()
        if line.strip().isdigit()
    }


def allowed_gpus(
    *,
    local: set[int] | None = None,
    home_path: str = DEFAULT_GPUS_PATH,
) -> set[int]:
    """开训允许的物理卡号。无 ~/.gpus → 本机全部；有文件 → 交集（空则 raise）。

    本机无卡时返回空集（CPU，不因 ~/.gpus 失败）。
    """
    if local is None:
        local = detect_local_gpus()
    if not local:
        return set()
    home = read_home_gpus(home_path)
    if home is None:
        return set(local)
    result = home & local
    if not result:
        raise HomeGpusError(
            f"GPU 交集为空：{home_path}={sorted(home)}，本机实际 GPU={sorted(local)}。"
            f"请更新 {home_path}（新机器可能需重新授权）或确认本机 GPU。"
        )
    return result


def parse_cuda_visible_devices(value: str | None) -> list[int] | None:
    """None = 未设置；空串 = 显式不用卡；否则为物理索引列表（保序）。"""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return []
    parse_gpus_file(stripped)  # 校验 token
    return [int(tok) for tok in _GPUS_DELIM_RE.split(stripped) if tok]


def enforce_cuda_visible_devices(
    environ: MutableMapping[str, str] | None = None,
    *,
    local: set[int] | None = None,
    home_path: str = DEFAULT_GPUS_PATH,
) -> str | None:
    """有 ~/.gpus 时确保 CUDA_VISIBLE_DEVICES ⊆ 授权集；未设则写入允许集。

    无文件或本机无卡：不改环境，返回 None。
    返回最终 CUDA_VISIBLE_DEVICES 字符串（含显式空串），或 None（未改）。
    """
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    home = read_home_gpus(home_path)
    if home is None:
        return None
    if local is None:
        local = detect_local_gpus()
    if not local:
        return None
    allowed = allowed_gpus(local=local, home_path=home_path)
    raw = env["CUDA_VISIBLE_DEVICES"] if "CUDA_VISIBLE_DEVICES" in env else None
    parsed = parse_cuda_visible_devices(raw)
    if parsed is None:
        val = ",".join(str(i) for i in sorted(allowed))
        env["CUDA_VISIBLE_DEVICES"] = val
        return val
    if parsed == []:
        return raw if raw is not None else ""
    bad = [i for i in parsed if i not in allowed]
    if bad:
        raise HomeGpusError(
            f"CUDA_VISIBLE_DEVICES={raw!r} 不在家目录授权 {sorted(allowed)} 内"
            f"（越界 {bad}）。请只用 {home_path} 列出的卡，或改该文件。"
        )
    return raw


def init_project_gpus_yaml(
    *,
    local: set[int] | None = None,
    home_path: str = DEFAULT_GPUS_PATH,
) -> str:
    """立项写入 nn-config.yaml 的 ``gpus:`` 值，如 ``[0, 1]`` 或 ``[]``。"""
    if local is None:
        local = detect_local_gpus()
    if not local:
        return "[]"
    allowed = allowed_gpus(local=local, home_path=home_path)
    if not allowed:
        return "[]"
    return "[" + ", ".join(str(i) for i in sorted(allowed)) + "]"


def check_env_status(
    environ: Mapping[str, str] | None = None,
    *,
    local: set[int] | None = None,
    home_path: str = DEFAULT_GPUS_PATH,
) -> tuple[str, int]:
    """check-env.sh 用：``(OK:...|FAIL:..., rc)``。rc=1 仅当立了规矩却无法授权。"""
    env = os.environ if environ is None else environ
    try:
        home = read_home_gpus(home_path)
    except HomeGpusError as exc:
        return (f"FAIL:{exc}", 1)
    if home is None:
        return ("OK:no_home_gpus", 0)
    if local is None:
        local = detect_local_gpus()
    if not local:
        return ("OK:cpu skip_home_gpus", 0)
    try:
        allowed = allowed_gpus(local=local, home_path=home_path)
        raw = env["CUDA_VISIBLE_DEVICES"] if "CUDA_VISIBLE_DEVICES" in env else None
        parse_cuda_visible_devices(raw)  # 校验 token
        enforce_cuda_visible_devices(
            environ=dict(env),  # type: ignore[arg-type]
            local=local,
            home_path=home_path,
        )
    except HomeGpusError as exc:
        return (f"FAIL:{exc}", 1)
    return (f"OK:home_gpus allowed={sorted(allowed)}", 0)


def shell_export_cuda(
    environ: MutableMapping[str, str] | None = None,
    *,
    local: set[int] | None = None,
    home_path: str = DEFAULT_GPUS_PATH,
) -> str:
    """给 bash eval：有文件则 ``export CUDA_VISIBLE_DEVICES=...``；否则空串。"""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    val = enforce_cuda_visible_devices(environ=env, local=local, home_path=home_path)
    if val is None:
        return ""
    return f"export CUDA_VISIBLE_DEVICES={val}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="家目录 GPU 授权（~/.gpus）")
    ap.add_argument(
        "--shell-export",
        action="store_true",
        help="打印 export CUDA_VISIBLE_DEVICES=...（供 bash eval）",
    )
    ap.add_argument("--init-yaml", action="store_true", help="打印立项 gpus: 值")
    args = ap.parse_args(argv)
    try:
        if args.init_yaml:
            print(init_project_gpus_yaml())
            return 0
        if args.shell_export:
            line = shell_export_cuda()
            if line:
                print(line)
            return 0
        allowed = allowed_gpus()
        print(",".join(str(i) for i in sorted(allowed)))
        return 0
    except HomeGpusError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
