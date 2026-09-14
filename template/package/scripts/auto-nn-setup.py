"""auto-nn-setup — 换机/重装/依赖损坏后把环境拉到 smoke 可过。

系统 python3 直接跑（venv 未建时它来建 venv），零第三方依赖，仅标准库。
GPU 名单解析走 scripts/lib/home_gpus.py（标准库）；验收复用 smoke-check.sh（内嵌 check-env）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from lib.home_gpus import (  # noqa: E402
    HomeGpusError,
    detect_local_gpus as _home_detect_local_gpus,
    parse_gpus_file as _parse_gpus_tokens,
    read_home_gpus,
)


class SetupFail(Exception):
    """硬失败——abort setup，不静默降级。"""


@dataclass(frozen=True)
class TorchSource:
    torch_version: str        # "2.5.1+cu124"
    torchvision_version: str  # "0.20.1+cu124"
    source_name: str          # "pytorch-cu124"
    url_suffix: str           # "cu124" → https://download.pytorch.org/whl/cu124


_TORCH_BASE = "2.5.1"
_TORCHVISION_BASE = "0.20.1"

_CUDA_VER_RE = re.compile(r"CUDA Version:\s*(\d+\.\d+)")


def parse_driver_cuda_version(nvidia_smi_output: str) -> str | None:
    """从 nvidia-smi 标题行解析驱动支持的最高 CUDA 版（如 '12.4'）。无则 None。"""
    m = _CUDA_VER_RE.search(nvidia_smi_output)
    return m.group(1) if m else None


def map_cuda_to_source(cuda_version: str | None) -> TorchSource:
    """驱动 CUDA 版 → torch wheel 源（spec §5.2 五档表）。"""
    if cuda_version is None:
        # 无 GPU / 无 nvidia-smi → cpu（§5.2）
        return TorchSource(f"{_TORCH_BASE}+cpu", f"{_TORCHVISION_BASE}+cpu",
                           "pytorch-cpu", "cpu")
    major, minor = (int(x) for x in cuda_version.split("."))
    # 档位语义：[12.4,∞)→cu124 / [12.1,12.4)→cu121 / [11.8,12.1)→cu118 / <11.8→FAIL
    if (major, minor) >= (12, 4):
        tag = "cu124"
    elif (major, minor) >= (12, 1):
        tag = "cu121"
    elif (major, minor) >= (11, 8):
        tag = "cu118"
    else:
        # <11.8 → FAIL，不自动降 cpu（§5.2）
        raise SetupFail(
            f"驱动 CUDA 版本 {cuda_version} 过旧（<11.8），无对应 torch wheel。"
            f"请升级显卡驱动，或换一台 CUDA≥11.8 的机器。"
        )
    return TorchSource(f"{_TORCH_BASE}+{tag}", f"{_TORCHVISION_BASE}+{tag}",
                       f"pytorch-{tag}", tag)


_TORCH_DEP_RE = re.compile(
    r'^(torch = \{ version = ")[^"]+(", source = ")(pytorch-[^"]+)(" ?\})', re.M
)
_TORCHVISION_DEP_RE = re.compile(
    r'^(torchvision = \{ version = ")[^"]+(", source = ")(pytorch-[^"]+)(" ?\})', re.M
)
_SOURCE_NAME_RE = re.compile(r'^(name = ")(pytorch-[^"]+)(")', re.M)
_SOURCE_URL_RE = re.compile(r'^(url = "https://download\.pytorch\.org/whl/)([^"]+)(")', re.M)


def _sub_or_fail(pattern: re.Pattern, text: str, repl: str, what: str) -> str:
    new_text, n = pattern.subn(repl, text)
    if n == 0:
        raise SetupFail(f"pyproject.toml 改写失败：找不到 {what}（格式不符预期？）")
    return new_text


def rewrite_pyproject_torch_source(text: str, src: TorchSource) -> str:
    """改 pyproject 的 torch 源（4 处：torch/torchvision 依赖行 + source name/url）。
    不碰 PyPI source 段（正则锚定 pytorch- 前缀 / download.pytorch.org url）。
    """
    text = _sub_or_fail(_TORCH_DEP_RE, text,
                        rf'\g<1>{src.torch_version}\g<2>{src.source_name}\g<4>',
                        "torch 依赖行")
    text = _sub_or_fail(_TORCHVISION_DEP_RE, text,
                        rf'\g<1>{src.torchvision_version}\g<2>{src.source_name}\g<4>',
                        "torchvision 依赖行")
    text = _sub_or_fail(_SOURCE_NAME_RE, text,
                        rf'\g<1>{src.source_name}\g<3>',
                        "pytorch source name（可能缺 pytorch source 段）")
    text = _sub_or_fail(_SOURCE_URL_RE, text,
                        rf'\g<1>{src.url_suffix}\g<3>',
                        "pytorch source url")
    return text


# ============================ §6 GPU 白名单 ============================

def parse_gpus_file(content: str) -> set[int]:
    """解析 GPU 索引列表（~/.gpus 全局授权 或 nn-config.yaml 的 gpus 值）。
    逗号/空格/换行分隔；容忍空格换行；非法 token raise（文案中性，不特指 ~/.gpus——
    也用于 nn-config，特指会误导排查方向）。"""
    try:
        return _parse_gpus_tokens(content)
    except HomeGpusError as e:
        raise SetupFail(str(e)) from e


def read_global_gpus_file(path: str = "~/.gpus") -> set[int] | None:
    """读全局 GPU 授权文件。不存在 → None（跳过收紧）；空/非法 → FAIL。"""
    try:
        return read_home_gpus(path)
    except HomeGpusError as e:
        raise SetupFail(str(e)) from e


def parse_gpu_indices(query_output: str) -> set[int]:
    """解析 `nvidia-smi --query-gpu=index --format=csv,noheader` 输出。"""
    return {int(line.strip()) for line in (query_output or "").splitlines()
            if line.strip().isdigit()}


def intersect_gpus(global_whitelist: set[int], local_gpus: set[int]) -> set[int]:
    """§6 交集。空 → FAIL（提示更新 ~/.gpus 或确认本机 GPU）。"""
    result = global_whitelist & local_gpus
    if not result:
        raise SetupFail(
            f"GPU 交集为空：~/.gpus={sorted(global_whitelist)}，"
            f"本机实际 GPU={sorted(local_gpus)}。"
            f"请更新 ~/.gpus（新机器可能需重新授权）或确认本机 GPU。"
        )
    return result


# 顶层 `gpus:` 行 + 紧随的 block-list 项（`- 2` / 缩进 `  - 3`）整块匹配。
# group1 = 行内值（inline '0,1' / flow '[2, 3]' / 空）；group2 = 后续 block 项。
# 关键：用 [ \t] 不用 \s*——旧 `\s*` 吞掉 block list 的换行，把 `- 2` 当成行内值，
# 既让 read 读错，又让 write 只替头部留下孤儿 `- 3` 损坏 YAML。
_NNCFG_GPUS_BLOCK_RE = re.compile(
    r'^gpus:[ \t]*([^\n]*)'                  # 顶层 gpus: 行（行内值，可空）
    r'((?:\n[ \t]*-[ \t]+[^\n]*)*)',         # 紧随的 block-list 项（0 或多行）
    re.M,
)


def read_nnconfig_gpus(text: str) -> str | None:
    """读 nn-config.yaml 顶层 gpus 值，支持 inline（'0,1'）/ flow list（[2, 3]）/
    block list（`gpus:` 后多行 `-`）。归一为逗号分隔串以复用 parse_gpus_file 契约
    （调用方仍会 parse_gpus_file 一次，幂等）。无 gpus 键 → None。"""
    m = _NNCFG_GPUS_BLOCK_RE.search(text)
    if not m:
        return None
    inline, block = m.group(1), m.group(2)
    if block.strip():                          # block list：取每个 `- ` 后的 token
        raw = ",".join(re.findall(r'-[ \t]+([^\n]+)', block))
    else:                                      # inline / flow：去 flow 括号
        raw = inline.strip().lstrip("[").rstrip("]").strip()
    if not raw:
        return None
    return ",".join(str(g) for g in sorted(parse_gpus_file(raw)))


def write_nnconfig_gpus(text: str, gpus_value: str) -> str:
    """改写 nn-config.yaml 顶层 gpus（输入可为 inline/flow/block 任意格式）。
    统一输出 YAML flow list（`gpus: [2, 3]`）——check-env.sh 只认 list/dict，
    写成字符串会被当无白名单静默忽略。无 gpus 行 → FAIL。"""
    nums = parse_gpus_file(gpus_value)         # 校验 + 归一成索引集合
    new_line = "gpus: [" + ", ".join(str(g) for g in sorted(nums)) + "]"
    new_text, n = _NNCFG_GPUS_BLOCK_RE.subn(lambda m: new_line, text, count=1)
    if n == 0:
        raise SetupFail("nn-config.yaml 找不到顶层 gpus: 行")
    return new_text


# ============================ §7 备份/还原 + §10.2 系统 pyyaml ============================


def backup_files(paths: list[str]) -> None:
    """§7 改盘前备份：对每个 path 造 <path>.bak（copy2 保留元数据）。

    源文件缺失/不可读 → SetupFail（与 read_global_gpus_file 等同——
    面向资源的失败统一包成可操作中文提示，不抛原始 OSError）。
    """
    for p in paths:
        try:
            shutil.copy2(p, p + ".bak")
        except OSError as e:
            raise SetupFail(f"备份失败：{p} 不存在或不可读（{e}）") from e


def restore_files(paths: list[str]) -> None:
    """§7 回滚：把 <path>.bak 覆盖回 <path>，并清掉 .bak。无 .bak 则跳过。"""
    for p in paths:
        bak = p + ".bak"
        if os.path.exists(bak):
            shutil.move(bak, p)


def drop_backups(paths: list[str]) -> None:
    """§7 成功路径：删 <path>.bak（PASS 分支不需要回滚）。无 .bak 则跳过。"""
    for p in paths:
        bak = p + ".bak"
        if os.path.exists(bak):
            os.remove(bak)


def probe_system_pyyaml() -> bool:
    """smoke-check.sh 读 nn-config profile 用系统 python3 `import yaml`——探针系统层依赖。"""
    return subprocess.run(
        ["python3", "-c", "import yaml"], capture_output=True
    ).returncode == 0


def ensure_system_pyyaml() -> None:
    """缺则系统级装 pyyaml（系统包，非 venv、非项目依赖）。
    注：这是「严禁 pip install」铁律之外的【系统层】例外（spec §10.2）——
    poetry 只管 venv 内，系统 shell 脚本（smoke-check.sh）的依赖须系统装。"""
    if probe_system_pyyaml():
        return
    subprocess.run(["python3", "-m", "pip", "install", "pyyaml"])
    if not probe_system_pyyaml():
        raise SetupFail(
            "系统 python3 缺 pyyaml（smoke-check.sh 读 nn-config profile 需要），"
            "且 `python3 -m pip install pyyaml` 失败。请手动装系统 pyyaml。"
        )


# ============================ §4/§7/§8 编排：检测→改盘→验收 ============================


def _run(cmd: list[str]) -> str:
    """跑外部命令，返回 stdout（失败/不存在返回 ''）。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout or ""
    except FileNotFoundError:
        return ""


def _detect_cuda() -> str | None:
    return parse_driver_cuda_version(_run(["nvidia-smi"]))


def _detect_local_gpus() -> set[int]:
    return _home_detect_local_gpus()


# ---- §4 检测项 1-3：Python 版本 / Poetry / venv（自实现，不调 check-env）----

def _detect_python_version() -> tuple[int, int, int]:
    v = sys.version_info
    return (v.major, v.minor, v.micro)


def _detect_poetry_present() -> bool:
    return shutil.which("poetry") is not None


def _detect_venv_ready(project_root: str) -> bool:
    """项目 .venv 能否 import torch+yaml（venv 不在/依赖坏 → False）。
    直接探 `.venv/bin/python`，不走 `poetry run`（后者可能触发自动建 venv，
    在 dry-run 检测路径里产生副作用）。venv 在 poetry 缓存目录时保守返回
    False → 触发幂等的 `poetry install`，安全方向（最多多跑一次 install）。"""
    venv_py = os.path.join(project_root, ".venv", "bin", "python")
    if not os.path.exists(venv_py):
        return False
    try:
        r = subprocess.run([venv_py, "-c", "import torch, yaml"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return r.returncode == 0


def build_setup_report(project_root: str,
                       detect_cuda=None,
                       detect_local_gpus=None,
                       read_global=None,
                       detect_python=None,
                       detect_poetry=None,
                       detect_venv=None) -> dict:
    """只检测，不改盘（dry-run + apply 共用）。注入检测函数便于单测。
    关键：用 None 默认值 + 运行期解析模块全局名（`(x or _x)`），使
    monkeypatch 模块级 `_detect_cuda` / `read_global_gpus_file` 也能生效——
    若用 `detect_cuda=_detect_cuda` 形式，Python 在 def 期就把默认值绑定死，
    测试里 monkeypatch 模块属性会静默失效（测试假绿/假红的坑）。"""
    root = os.path.abspath(project_root)
    nncfg_path = os.path.join(root, "nn-config.yaml")
    pyproj_path = os.path.join(root, "pyproject.toml")

    cuda = (detect_cuda or _detect_cuda)()
    source = map_cuda_to_source(cuda)  # <11.8 在此 raise SetupFail

    local_gpus = (detect_local_gpus or _detect_local_gpus)()
    planned_writes: list[str] = []

    if local_gpus:  # 有 GPU 才走白名单（cpu 盒子跳过）
        global_whitelist = (read_global or read_global_gpus_file)()
        if global_whitelist is None:
            # 没建 ~/.gpus = 没立规矩，不改项目名单
            gpus_new = None
        else:
            gpus_new = intersect_gpus(global_whitelist, local_gpus)
    else:
        # cpu 盒子：跳过白名单，gpus 原样不动
        global_whitelist = set()
        gpus_new = None

    # §4 检测项 1-3：系统 python3 直接探（不调 check-env——接口不匹配，§4 末段）
    py_ver = (detect_python or _detect_python_version)()
    python_ok = (3, 10) <= py_ver[:2] < (3, 14)  # 检测项 1：目标区间 [3.10, 3.14)
    poetry_present = (detect_poetry or _detect_poetry_present)()  # 检测项 2
    venv_ready = (detect_venv or _detect_venv_ready)(root)  # 检测项 3

    gpus_old = None
    if os.path.exists(nncfg_path):
        with open(nncfg_path, encoding="utf-8") as f:
            old = read_nnconfig_gpus(f.read())
        gpus_old = parse_gpus_file(old) if old else set()

    # §4 检测项 2「Poetry+pyproject+lock 齐全」：pyproject 不存在 → clean FAIL。
    # 不能改写不存在的文件（否则 open() 抛原始 FileNotFoundError traceback，
    # 破坏模块「一律中文 SetupFail」约定）；缺 pyproject 说明项目未 init，非 setup 职责。
    if not os.path.exists(pyproj_path):
        raise SetupFail(f"pyproject.toml 不存在（{pyproj_path}）——setup 只改写既有源段，"
                        "不凭空生成 pyproject。请先 /auto-nn-init 建项目。")
    # §4 对称守卫：有 GPU 要写白名单时，nn-config 缺 → clean FAIL。
    # 否则 apply 期 open(nncfg) 抛原始 FileNotFoundError（与 pyproj 同类防御）。
    if gpus_new is not None and not os.path.exists(nncfg_path):
        raise SetupFail(f"nn-config.yaml 不存在（{nncfg_path}）——setup 要写 GPU 白名单，"
                        "无法改写不存在的文件。请先 /auto-nn-init 建项目。")
    with open(pyproj_path, encoding="utf-8") as f:
        txt = f.read()
    # 源是否需改（当前 pyproject 的 source name 与目标不同才改）
    need_pyproj_edit = f'name = "{source.source_name}"' not in txt
    # §4 检测项 3 处理：venv 坏（torch/yaml 缺）也要建 venv+install，
    # 与源改独立（venv 在源匹配时仍可能损坏——被删 / 装了一半）
    need_install = need_pyproj_edit or not venv_ready
    if need_pyproj_edit:
        planned_writes.append("pyproject.toml")
    elif not venv_ready:
        # 源未改但 venv 坏：单独列一条 install（源改时 install 隐含在改写流程里）
        planned_writes.append("venv/依赖重建（poetry install）")
    if gpus_new is not None and gpus_new != gpus_old:
        planned_writes.append("nn-config.yaml")

    return {
        "project_root": root,
        "cuda": cuda,
        "source": source,
        "gpus_new": gpus_new,
        "gpus_old": gpus_old,
        "global_whitelist": global_whitelist,
        "local_gpus": local_gpus,
        "need_pyproject_edit": need_pyproj_edit,
        "need_install": need_install,
        "planned_writes": planned_writes,
        "nncfg_path": nncfg_path,
        "pyproj_path": pyproj_path,
        "python_version": py_ver,
        "python_ok": python_ok,
        "poetry_present": poetry_present,
        "venv_ready": venv_ready,
    }


def _print_report(report: dict) -> None:
    s = report["source"]
    # §4 检测项 1-3：Python 版本 / Poetry / venv（自实现，不调 check-env）
    pyv = report["python_version"]
    if report["python_ok"]:
        print(f"[setup] ✓ Python {pyv[0]}.{pyv[1]}.{pyv[2]}（目标 [3.10, 3.14)）")
    else:
        print(f"[setup] ⚠️ Python {pyv[0]}.{pyv[1]}.{pyv[2]} 不在 [3.10, 3.14)——"
              "系统级，setup 不擅自动装，请自行换系统 python3（检测项 1）")
    print("[setup] ✓ Poetry 在 PATH" if report["poetry_present"]
          else "[setup] ⚠️ Poetry 不在 PATH——lock+install 需要它（检测项 2）")
    print("[setup] ✓ .venv 可 import torch+yaml" if report["venv_ready"]
          else "[setup] · .venv 缺/坏 → 将建 venv + poetry install（检测项 3）")
    print(f"[setup] 驱动 CUDA = {report['cuda']}  → torch 源 = {s.source_name} "
          f"({s.torch_version} / {s.torchvision_version})")
    if not report["local_gpus"]:
        print("[setup] 本机无 GPU → cpu 训练（跳过 GPU 白名单）")
    elif report["global_whitelist"] is None:
        print("[setup] 未找到 ~/.gpus，跳过白名单收紧（开训不限制占用）")
    else:
        print(f"[setup] GPU 白名单：~/.gpus={sorted(report['global_whitelist'])} ∩ "
              f"本机={sorted(report['local_gpus'])} → {sorted(report['gpus_new'])}")
    print(f"[setup] 计划改写：{report['planned_writes'] or '（无需改）'}")


def _run_poetry(report: dict) -> None:
    """§7: lock 一次 + install（直连失败则带超时/镜像 env 重试一次）。

    lock 不带 ``--no-update``：Poetry 2.x 起 no-update 是 ``lock`` 的默认行为、旧 flag 已移除
    （带上反而在 2.x 报未知参数失败）。1.x 下 bare ``lock`` 会更新依赖，但模板目标环境为 2.x。

    重试 env（§5.3，与 check-env.sh:58 同源约定）：
      - POETRY_HTTP_TIMEOUT=600：Poetry 原生支持，对超时类失败真有效。
      - POETRY_PYPI_MIRROR=清华：**需另装 poetry-plugin-pypi-mirror 才生效**，否则
        Poetry 忽略它（本机未装该插件时重试等价直连）。机制统一待 repo-wide 决策。
    lock 只跑一次：重试仅因 install 源/超时失败，lock 态未变，无须重解（避免无谓 I/O）。"""
    root = report["project_root"]
    base_env = os.environ.copy()
    if subprocess.run(["poetry", "lock"], cwd=root, env=base_env).returncode != 0:
        raise SetupFail("poetry lock 失败")

    retry_env = base_env.copy()
    retry_env["POETRY_HTTP_TIMEOUT"] = "600"
    retry_env["POETRY_PYPI_MIRROR"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
    for attempt, env in enumerate((base_env, retry_env)):
        if subprocess.run(["poetry", "install"], cwd=root, env=env).returncode == 0:
            return
        if attempt == 0:
            print("[setup] poetry install 失败，重试一次（加长超时 + TUNA 镜像 env，见 check-env.sh）…")
    raise SetupFail("poetry install 失败（直连 + 镜像 env 重试均失败）")


def _probe_torch_import(root: str) -> tuple[bool, str]:
    """poetry run import torch；返回 (ok, stdout+stderr)。"""
    r = subprocess.run(
        ["poetry", "run", "python", "-c", "import torch; print(torch.__version__)"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    text = f"{getattr(r, 'stderr', None) or ''}\n{getattr(r, 'stdout', None) or ''}"
    return r.returncode == 0, text


def _try_poetry_add_dynamic_lib_wheels(root: str, cuda_tag: str, error_text: str) -> list[str]:
    """缺常见 .so 时 best-effort ``poetry add`` nvidia 轮；返回已尝试的包名。

    不调 check-env；分类逻辑与 ``check_env_import_classify`` 同源（scripts/lib）。
    仅 cu12* 映射；装失败只打日志，不升 SetupFail（交给后续 smoke）。
    """
    scripts_lib = os.path.join(root, "scripts", "lib")
    if scripts_lib not in sys.path:
        sys.path.insert(0, scripts_lib)
    try:
        from check_env_import_classify import (  # type: ignore
            classify_torch_import_failure,
            pip_packages_for_dynamic_libs,
        )
    except ImportError:
        print("[setup] ⚠️ 无 check_env_import_classify — 跳过动态库 pip 补装（先 governance-sync）")
        return []

    if classify_torch_import_failure(error_text) != "dynamic_lib":
        return []
    pkgs = pip_packages_for_dynamic_libs(error_text, cuda_wheel_tag=cuda_tag)
    if not pkgs:
        print("[setup] · 动态库缺失但无映射到 cu12 nvidia 轮（可能需系统驱动/手动装）")
        return []
    installed: list[str] = []
    for pkg in pkgs:
        print(f"[setup] · 尝试 poetry add {pkg}（常见 .so → pip 轮）…")
        rc = subprocess.run(["poetry", "add", pkg], cwd=root).returncode
        if rc == 0:
            installed.append(pkg)
        else:
            print(f"[setup] ⚠️ poetry add {pkg} 失败（继续；smoke 会终判）")
    return installed


def apply_setup(report: dict) -> int:
    """改盘：edit pyproject → lock+install → 写 gpus → smoke。失败回滚 pyproject/lock。"""
    root = report["project_root"]
    pyproj, nncfg = report["pyproj_path"], report["nncfg_path"]
    lock_path = os.path.join(root, "poetry.lock")
    touched = [p for p in (pyproj, lock_path) if os.path.exists(p)]
    install_ran = False  # M-1：install 是否真跑过；venv-drift 告警只在此为真时打（poetry 缺/装失败时 .venv 未动，不可误报「已写入」）
    backed_up = False    # M-1：是否真备份过；回滚只在备份过时做（poetry 缺/装失败前置失败时未备份，不可谎报「回滚」）

    try:
        ensure_system_pyyaml()  # §10.2 smoke-check 隐式依赖（放 try 内：失败走 clean message 不抛 traceback）
        # §4 检测项 2：poetry 缺则 lock+install 必失败——提前 clean FAIL（不抛原始 traceback）
        if report["need_install"] and not report["poetry_present"]:
            raise SetupFail("poetry 未安装在 PATH——lock+install 需要它（建 venv / 装依赖）。"
                            "请先装 poetry（见 check-env.sh 提示）。")
        if report["need_pyproject_edit"]:
            backup_files(touched)
            backed_up = True  # 备份过 → 失败才回滚（改写 truncate 后必须 restore）
            with open(pyproj, encoding="utf-8") as f:
                txt = f.read()
            with open(pyproj, "w", encoding="utf-8") as f:
                f.write(rewrite_pyproject_torch_source(txt, report["source"]))
            install_ran = True  # 调 poetry 前标记：venv 可能被写入
            _run_poetry(report)
        elif report["need_install"]:
            # §4 检测项 3 处理：源未改但 venv 坏（被删/装了一半）→ 仅建 venv+install，不备份/改写
            install_ran = True  # 同上：venv 可能被写入
            _run_poetry(report)
        if report["gpus_new"] is not None and report["gpus_new"] != report["gpus_old"]:
            # nit #1：写前备份 nn-config——写用 truncate-then-write，中途被杀会截断丢内容；
            # 有 .bak 才能还原。备份在写完成/失败时统一丢弃（GPU 交集是安全收敛、不回滚，§8）。
            backup_files([nncfg])
            with open(nncfg, encoding="utf-8") as f:
                cfg = f.read()
            with open(nncfg, "w", encoding="utf-8") as f:
                f.write(write_nnconfig_gpus(cfg, ", ".join(str(g) for g in sorted(report["gpus_new"]))))

        # 常见 .so（如 cusparseLt）→ nvidia pip 轮 best-effort（不替装系统 apt）
        if report["poetry_present"]:
            ok_imp, imp_out = _probe_torch_import(root)
            if not ok_imp:
                added = _try_poetry_add_dynamic_lib_wheels(
                    root, report["source"].url_suffix, imp_out
                )
                if added:
                    install_ran = True
                    ok_imp, imp_out = _probe_torch_import(root)
                    if ok_imp:
                        print(f"[setup] ✓ 动态库 pip 补装后 torch 可 import（{', '.join(added)}）")

        # §8 验收：smoke-check.sh（L33 内嵌 check-env，环境就绪+能训一道覆盖）
        smoke = subprocess.run(["bash", os.path.join(root, "scripts", "smoke-check.sh")],
                               cwd=root)
        if smoke.returncode != 0:
            raise SetupFail("smoke-check.sh 不过（重装不算成功，§8）")
        drop_backups(touched)  # 成功：清 .bak
        drop_backups([nncfg])  # nit #1：清 nn-config 备份（gpus 已落地）
        print("[setup] ✅ 环境就绪，smoke 通过。")
        return 0
    except SetupFail as e:
        print(f"[setup] ❌ 失败：{e}")
        if backed_up:  # M-1：仅当真备份过才回滚（poetry 缺/装失败前置失败时未备份，无物可还原、不可谎报「回滚」）
            print("[setup] 回滚 pyproject/poetry.lock（§7）…")
            restore_files(touched)
            # lock 重解回滚态。poetry 缺时跳过 re-lock（本就是它失败的，且无 poetry 可调）。
            if report["poetry_present"]:
                subprocess.run(["poetry", "lock"], cwd=root)
        drop_backups([nncfg])  # nit #1：gpus 安全收敛保留新值，清掉本次备份（无残留）
        if install_ran:
            # I5：install 已把 .venv 写到新态（新源依赖 / 重建），venv 不回滚——
            # pyproject/lock 回到旧源但 .venv 暂留新态，可能短暂不一致；重跑 setup 会按
            # pyproject 重新对齐。显式告知用户，避免误以为「全回滚干净」。
            # M-1：仅当 install 真跑过才打——poetry 缺/装失败时 .venv 未被写入，打此告警是错误事实。
            print("[setup] ⚠️ .venv 已被 install 写入、未回滚（可能与回滚后的 pyproject 短暂不一致）；"
                  "重跑 /auto-nn-setup 会按 pyproject 重新对齐。")
        # GPU 白名单交集是安全收敛，不回滚（§8）
        return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="auto-nn-setup",
        description="换机/重装/依赖损坏后把环境拉到 smoke 可过（检测+修复+验收）。",
    )
    ap.add_argument("--project-root", default=".", help="业务仓根（含 nn-config.yaml / pyproject.toml）")
    ap.add_argument("--dry-run", action="store_true", help="只检测报告，不改盘")
    args = ap.parse_args(argv)

    try:
        report = build_setup_report(args.project_root)
        _print_report(report)
        if args.dry_run or not report["planned_writes"]:
            if args.dry_run:
                print("[setup] --dry-run：以上为计划，不改盘。")
            elif not report["planned_writes"]:
                print("[setup] 无需改写，环境已匹配。")
            return 0
        return apply_setup(report)
    except SetupFail as e:
        # 检测期失败（CUDA 过旧 / ~/.gpus 空或交集空 / pyproject 缺 / nn-config 缺 / python 区间外）
        # 统一走中文信息 + rc=1，不向 __main__ 透传 traceback（模块约定，与 apply_setup 同构）。
        print(f"[setup] ❌ 失败：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
