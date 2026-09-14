#!/usr/bin/env python3
"""Template version parser/compare/classify (semver + git SHA suffix).

Used by:
  - `_check_template_version.sh` (auto-nn-update.sh gate) → CLI `--check`
  - `release-check.sh` → library import (`from check_template_version import parse, classify, BumpType`)
  - unit tests (see tests/template_tests/ via the standalone sandbox facility)

CLI:
  python3 check_template_version.py --self-test                  # exit 0 = OK
  python3 check_template_version.py --check \
      --business-version "<0.1.0+abc>" \
      --template-version "<0.2.0+def>" \
      [--accept-major-bump] \
      [--strict-version]
"""
from __future__ import annotations

import argparse
import enum
import re
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Stamp:
    major: int
    minor: int
    patch: int
    sha: str  # "" if no SHA suffix


class BumpType(enum.Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    EQUAL = "equal"
    STAMP_DRIFT = "stamp_drift"  # semver equal, SHA differs
    DOWNGRADE = "downgrade"


# Strict-ish semver (X.Y.Z) + optional `[+hex-sha]` suffix. Leading zeros
# in numeric identifiers are tolerated (e.g., "01.2.3" parses as 1.2.3) —
# git-describe output never produces them, so this is acceptable laxness.
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\+([0-9a-fA-F]+))?$")


def parse(s: str) -> Stamp:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty version")
    m = _SEMVER_RE.match(s)
    if not m:
        raise ValueError(f"invalid semver: {s!r}")
    return Stamp(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")


def format_stamp(st: Stamp) -> str:
    base = f"{st.major}.{st.minor}.{st.patch}"
    return f"{base}+{st.sha}" if st.sha else base


def compare(a: Stamp, b: Stamp) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b. SHA ignored."""
    if (a.major, a.minor, a.patch) < (b.major, b.minor, b.patch):
        return -1
    if (a.major, a.minor, a.patch) > (b.major, b.minor, b.patch):
        return 1
    return 0


def classify(prev: Stamp, new: Stamp) -> BumpType:
    """Classify bump from prev to new (used by release-check + update gate).

    STAMP_DRIFT semantics: BOTH prev.sha and new.sha must be non-empty AND
    different. If one side has no SHA (e.g., template VERSION is pure semver
    pre-stamp, business has been stamped), returns EQUAL — the gate stage
    is not where drift is detected; it's where the template's pure semver
    is compared to the business's last-known stamp.
    """
    c = compare(prev, new)
    if c < 0:
        # prev < new; determine level
        if new.major > prev.major:
            return BumpType.MAJOR
        if new.minor > prev.minor:
            return BumpType.MINOR
        return BumpType.PATCH
    if c > 0:
        return BumpType.DOWNGRADE
    # equal semver
    if prev.sha and new.sha and prev.sha != new.sha:
        return BumpType.STAMP_DRIFT
    return BumpType.EQUAL


# === CLI ===

def _self_test() -> int:
    # 12 invariants; prints "OK" + newline; exit 0 on all pass
    assert parse("0.1.0+abc1234") == Stamp(0, 1, 0, "abc1234")
    assert parse("0.1.0") == Stamp(0, 1, 0, "")
    try:
        parse("")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert compare(parse("0.1.0"), parse("0.2.0")) == -1
    assert compare(parse("0.1.0"), parse("0.1.0")) == 0
    assert classify(parse("0.9.9"), parse("1.0.0")) == BumpType.MAJOR
    assert classify(parse("0.1.0"), parse("0.2.0")) == BumpType.MINOR
    assert classify(parse("0.1.0"), parse("0.1.1")) == BumpType.PATCH
    assert classify(parse("1.0.0"), parse("0.9.9")) == BumpType.DOWNGRADE
    assert classify(parse("0.1.0+abc"), parse("0.1.0+def")) == BumpType.STAMP_DRIFT
    assert classify(parse("0.1.0"), parse("0.1.0")) == BumpType.EQUAL
    assert format_stamp(parse("0.1.0+abc1234")) == "0.1.0+abc1234"
    print("OK")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Called by `_check_template_version.sh` from auto-nn-update.

    Logic:
      - business_version == "" → first update, allow (echo "首次 update")
      - classify(business, template) == MAJOR and not accept_major_bump → exit 1
      - classify == DOWNGRADE and strict_version → exit 1
      - classify == STAMP_DRIFT → warn to stderr, exit 0
      - classify in (MINOR, PATCH, EQUAL) → exit 0
      - print "<prev> → <new> (<bump>)" to stderr
    """
    bv = args.business_version.strip()
    tv = args.template_version.strip()
    try:
        new = parse(tv)
    except ValueError as e:
        print(f"FAIL: invalid template version {tv!r}: {e}", file=sys.stderr)
        return 2

    if not bv:
        print(f"[check] 首次 update，自动 stamp = {format_stamp(new)}", file=sys.stderr)
        return 0

    try:
        old = parse(bv)
    except ValueError as e:
        print(f"WARN: 业务仓 version 不可解析 {bv!r}（视同首次 update）: {e}", file=sys.stderr)
        print(f"[check] 自动 stamp = {format_stamp(new)}", file=sys.stderr)
        return 0

    btype = classify(old, new)

    if btype == BumpType.MAJOR and not args.accept_major_bump:
        print(
            f"FAIL: major bump ({format_stamp(old)} → {format_stamp(new)}) 需 --accept-major-bump",
            file=sys.stderr,
        )
        return 1

    if btype == BumpType.DOWNGRADE and args.strict_version:
        print(
            f"FAIL: downgrade ({format_stamp(old)} → {format_stamp(new)}) 拒绝（--strict-version）",
            file=sys.stderr,
        )
        return 1

    # PASS cases
    if btype == BumpType.STAMP_DRIFT:
        print(
            f"WARN: stamp drift（semver 同，SHA 异）{format_stamp(old)} → {format_stamp(new)}",
            file=sys.stderr,
        )
    elif btype == BumpType.DOWNGRADE:
        print(
            f"WARN: downgrade {format_stamp(old)} → {format_stamp(new)}（仍 sync）",
            file=sys.stderr,
        )
    else:
        print(
            f"[check] {format_stamp(old)} → {format_stamp(new)} ({btype.value})",
            file=sys.stderr,
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--self-test", action="store_true", help="run 12 invariants, exit 0 on pass")
    p.add_argument(
        "--check",
        action="store_true",
        help="business vs template version gate (used by _check_template_version.sh)",
    )
    p.add_argument("--business-version", default="", help="当前业务仓 stamp（可能空）")
    p.add_argument("--template-version", default="", help="新模板仓 semver（--check 模式必填；空/无效时 exit 2）")
    p.add_argument("--accept-major-bump", action="store_true")
    p.add_argument("--strict-version", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return _self_test()
    if args.check:
        return _cmd_check(args)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())