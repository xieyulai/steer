"""reflect.py _agent_call_timeout 超时解析单测（R7）。

Phase 1 claude -p 曾在硬编码 300s 超时（R4）。R7：超时可配（NN_AGENT_CALL_TIMEOUT）、
默认 600s、超时重试 1 次。本测只验超时值解析（重试逻辑需 mock subprocess，另议）。
"""
from __future__ import annotations

import os
import sys
import unittest

# bootstrap template/package 到 path，使 `import reflect` 可用
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

import reflect  # noqa: E402


class AgentCallTimeoutTest(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.pop("NN_AGENT_CALL_TIMEOUT", None)

    def tearDown(self):
        if self._prev is not None:
            os.environ["NN_AGENT_CALL_TIMEOUT"] = self._prev
        else:
            os.environ.pop("NN_AGENT_CALL_TIMEOUT", None)

    def test_default_when_env_unset(self):
        self.assertEqual(reflect._agent_call_timeout(), 600)

    def test_env_override(self):
        os.environ["NN_AGENT_CALL_TIMEOUT"] = "900"
        self.assertEqual(reflect._agent_call_timeout(), 900)

    def test_invalid_env_falls_back_to_default(self):
        for bad in ("notanum", "0", "-5", "3.5", ""):
            with self.subTest(bad=bad):
                os.environ["NN_AGENT_CALL_TIMEOUT"] = bad
                self.assertEqual(reflect._agent_call_timeout(), 600)


if __name__ == "__main__":
    unittest.main()
