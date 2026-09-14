"""reflect.py _parse_json_lenient 容错解析单测。

修 R4 sandbox 暴露的 Phase 1/2 'Extra data: line 1 column 430' 错：
LLM 常在 JSON 后追加自然语言解释，json.loads 整段会抛 Extra data。
_parse_json_lenient 用 raw_decode 取首对象，容错前导文本 + 尾随数据。
"""
from __future__ import annotations

import os
import sys

# bootstrap template/package 到 path，使 `import reflect` 可用
# (reflect.py 自身再把 scripts/ 加进 path 以解析 lib.external.*)
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

import reflect  # noqa: E402


def test_clean_json_object():
    assert reflect._parse_json_lenient('{"a": 1}') == {"a": 1}


def test_extra_data_trailing_text():
    # R4 真实 bug：有效 JSON + 尾随解释 → json.loads 抛 Extra data
    raw = '{"findings": [1, 2], "references_to_add": []}\n\n以上是本轮发现。'
    assert reflect._parse_json_lenient(raw) == {"findings": [1, 2], "references_to_add": []}


def test_leading_text():
    raw = 'Sure! Here is the JSON:\n{"wall_crash": false, "streak_count": 0}'
    assert reflect._parse_json_lenient(raw) == {"wall_crash": False, "streak_count": 0}


def test_markdown_fence():
    raw = '```json\n{"wall_crash": true}\n```'
    assert reflect._parse_json_lenient(raw) == {"wall_crash": True}


def test_bare_array():
    assert reflect._parse_json_lenient('[{"a": 1}, {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_empty_and_garbage_return_none():
    assert reflect._parse_json_lenient("") is None
    assert reflect._parse_json_lenient("   ") is None
    assert reflect._parse_json_lenient("no json here at all") is None
    assert reflect._parse_json_lenient(None) is None


def test_truncated_json_returns_none():
    # 不完整 JSON（raw_decode 抛 JSONDecodeError）→ None，不抛
    assert reflect._parse_json_lenient('{"wall_crash":') is None
