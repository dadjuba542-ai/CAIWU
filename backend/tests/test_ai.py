import json
from types import SimpleNamespace

import pytest

import app.ai as ai


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": json.dumps(self.payload, ensure_ascii=False)}}]}


class FakeClient:
    payload = {}
    request = None

    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def post(self, _url, **kwargs):
        FakeClient.request = kwargs
        return FakeResponse(FakeClient.payload)


def evidence():
    chunk = SimpleNamespace(id=7, content="前文。" + "关键证据" * 100, locator="第 8 页")
    document = SimpleNamespace(id=3, name="税法讲义")
    return [(0.9, chunk, document)]


def test_grounded_answer_uses_complete_chunk_and_claim_citations(monkeypatch):
    monkeypatch.setattr(ai, "retrieve", lambda *_args, **_kwargs: evidence())
    monkeypatch.setattr(ai, "decrypt_key", lambda _db: ("secret", "deepseek-chat"))
    monkeypatch.setattr(ai.httpx, "Client", FakeClient)
    FakeClient.payload = {"claims": [{"text": "结论", "citation_ids": ["C7"], "reasoning_type": "direct"}],
                          "insufficient_evidence": [], "suggested_materials": [], "follow_up_questions": []}
    result = ai.grounded_answer(object(), "问题是什么", None, None, "answer")
    prompt = FakeClient.request["json"]["messages"][0]["content"]
    assert "关键证据" * 100 in prompt
    assert result["answer"] == "结论"
    assert result["citations"][0]["chunk_id"] == 7


def test_grounded_answer_rejects_claim_without_valid_source(monkeypatch):
    monkeypatch.setattr(ai, "retrieve", lambda *_args, **_kwargs: evidence())
    monkeypatch.setattr(ai, "decrypt_key", lambda _db: ("secret", "deepseek-chat"))
    monkeypatch.setattr(ai.httpx, "Client", FakeClient)
    FakeClient.payload = {"claims": [{"text": "无依据结论", "citation_ids": [999], "reasoning_type": "direct"}]}
    with pytest.raises(ValueError, match="无依据结论"):
        ai.grounded_answer(object(), "问题是什么", None, None, "answer")
