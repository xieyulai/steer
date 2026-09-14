"""P1-4: phase2 findings/references_to_add 元素必须是 dict（防 str 元素 .get() 崩）。
测的是与 reflect.py 内联 coerce 段等价的规整规则（不 import reflect.py 大文件）。"""


def test_coerce_normalizes_str_element_in_list():
    def normalize(phase2):
        for _fk in ("findings", "references_to_add"):
            _fv = phase2.get(_fk)
            if isinstance(_fv, list):
                phase2[_fk] = [
                    f if isinstance(f, dict)
                    else {"summary": str(f), "tier": "?", "url": "", "source": "llm_string"}
                    for f in _fv
                ]
            elif isinstance(_fv, dict):
                phase2[_fk] = [_fv]
            elif _fv is None:
                phase2[_fk] = []
            else:
                phase2[_fk] = [{"summary": str(_fv), "tier": "?", "url": "", "source": "llm_string"}]
        return phase2

    out = normalize({"findings": ["裸字符串"], "references_to_add": []})
    assert out["findings"] == [{"summary": "裸字符串", "tier": "?", "url": "", "source": "llm_string"}]


def test_coerce_normalizes_bare_str():
    def normalize(phase2):
        for _fk in ("findings", "references_to_add"):
            _fv = phase2.get(_fk)
            if isinstance(_fv, list):
                phase2[_fk] = [
                    f if isinstance(f, dict)
                    else {"summary": str(f), "tier": "?", "url": "", "source": "llm_string"}
                    for f in _fv
                ]
            elif isinstance(_fv, dict):
                phase2[_fk] = [_fv]
            elif _fv is None:
                phase2[_fk] = []
            else:
                phase2[_fk] = [{"summary": str(_fv), "tier": "?", "url": "", "source": "llm_string"}]
        return phase2

    out = normalize({"findings": "整体是字符串", "references_to_add": None})
    assert isinstance(out["findings"], list) and out["findings"][0]["summary"] == "整体是字符串"
    assert out["references_to_add"] == []


def test_coerce_wraps_dict_into_list():
    def normalize(phase2):
        for _fk in ("findings", "references_to_add"):
            _fv = phase2.get(_fk)
            if isinstance(_fv, list):
                phase2[_fk] = [
                    f if isinstance(f, dict)
                    else {"summary": str(f), "tier": "?", "url": "", "source": "llm_string"}
                    for f in _fv
                ]
            elif isinstance(_fv, dict):
                phase2[_fk] = [_fv]
            elif _fv is None:
                phase2[_fk] = []
            else:
                phase2[_fk] = [{"summary": str(_fv), "tier": "?", "url": "", "source": "llm_string"}]
        return phase2

    out = normalize({"findings": {"summary": "x"}, "references_to_add": []})
    assert out["findings"] == [{"summary": "x"}]


def test_coerce_preserves_normal_list_of_dict():
    def normalize(phase2):
        for _fk in ("findings", "references_to_add"):
            _fv = phase2.get(_fk)
            if isinstance(_fv, list):
                phase2[_fk] = [
                    f if isinstance(f, dict)
                    else {"summary": str(f), "tier": "?", "url": "", "source": "llm_string"}
                    for f in _fv
                ]
            elif isinstance(_fv, dict):
                phase2[_fk] = [_fv]
            elif _fv is None:
                phase2[_fk] = []
            else:
                phase2[_fk] = [{"summary": str(_fv), "tier": "?", "url": "", "source": "llm_string"}]
        return phase2

    out = normalize({"findings": [{"summary": "x", "tier": "A"}], "references_to_add": []})
    assert out["findings"] == [{"summary": "x", "tier": "A"}]
