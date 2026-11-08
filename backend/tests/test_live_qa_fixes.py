"""Fixes from the production QA run of 5 Nov 2026 (live AI)."""


def test_spread_uses_every_chunk_when_they_fit():
    from features.docs import spread
    chunks = [{"i": i, "text": "w " * 350} for i in range(10)]
    assert [c["i"] for c in spread(chunks, 9000)] == list(range(10))       # used to drop every other chunk
    picked = spread(chunks, 350 * 4)
    assert len(picked) == 4 and picked == sorted(picked, key=lambda c: c["i"])


def test_timeline_context_keeps_a_date_in_an_odd_chunk():
    from features.docs import make_chunks, spread
    from features.kb import CHUNK_WORDS
    words = ["filler"] * (CHUNK_WORDS * 3)
    at = int(CHUNK_WORDS * 0.85) + CHUNK_WORDS + 5          # only inside chunk 1 (and its overlap)
    words[at:at + 3] = ["14", "January", "2027"]
    chunks = make_chunks(" ".join(words))
    texts = " ".join(c["text"] for c in spread(chunks, 9000))
    assert "14 January 2027" in texts


def test_citation_names_the_page_the_passage_is_on():
    from features.docs import make_chunks, page_at, snippet_at, with_page_marks
    p3 = "Background on the market and the team. " * 25          # 175 words
    p4 = "The Surat plant goes live with the new line in January. " + "More detail follows here. " * 10
    full = (p3 + p4).strip()
    starts = [0, 0, 0, len(p3.split())]                        # pages 1-2 empty, page 3, page 4
    c = make_chunks(full, starts)[0]
    assert c["page"] == 3 and c["breaks"] == [[len(p3.split()), 4]]
    _, at = snippet_at(c["text"], "When does the Surat plant go live?")
    assert page_at(c, at) == 4
    assert "[page 4] The Surat plant" in with_page_marks(c)
    assert page_at({"page": 2, "text": "x"}, 10) == 2           # old chunks without breaks keep their page


def test_snapshot_option_repairs_title_and_value_prop():
    from features.start import _repair
    row = {"niche": "Plant cost reduction", "who": "Mid-size auto component makers", "problem": "High scrap rates",
           "result": "Cut scrap by a third in 6 months", "title": "",
           "value_prop": "I help [target audience] achieve [desired result] by helping them solve [problem]"}
    _repair(row)
    assert row["title"] == "Plant cost reduction Consultant"
    assert "[" not in row["value_prop"] and row["value_prop"].startswith("I help Mid-size auto component makers cut scrap")


def test_time_budget_grows_with_answer_length(monkeypatch):
    import llm
    monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
    assert llm.time_budget(1200) == 60
    assert llm.time_budget(4000) > 130
    assert llm.time_budget(20000) == 180
    assert llm.time_budget(4000, 30) == 30
    assert llm.time_budget(300) == 45                           # never below LLM_TIMEOUT_S


def test_every_ai_call_gets_the_same_output_room(monkeypatch):
    """Every tool writes up to LLM_MAX_OUTPUT_TOKENS (default 15,000), whatever max_tokens it passes."""
    import asyncio

    import llm
    seen = []

    async def fake_call(*, model, max_tokens, system, content):
        seen.append(max_tokens)
        return '{"ok": true}'
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "_call_text", fake_call)
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)
    for asked in (700, 1000, 7000):
        asyncio.run(llm.complete_json(task="t", system="s", prompt="p", fake=dict, model="strong", max_tokens=asked))
    asyncio.run(llm.complete_text(task="t", system="s", prompt="p", fake=str, max_tokens=300))
    assert seen == [15000, 15000, 15000, 15000]
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "6000")
    asyncio.run(llm.complete_json(task="t", system="s", prompt="p", fake=dict, max_tokens=700))
    assert seen[-1] == 6000
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "50000")                    # above the SDK's non-streaming limit
    asyncio.run(llm.complete_json(task="t", system="s", prompt="p", fake=dict, max_tokens=700))
    assert seen[-1] == 21000


def test_portfolio_review_accepts_how_a_real_model_writes():
    """Live: "AI is busy" after the member filled the approach. Steps as objects, scores as {"score": n}, a missing
    lesson list and title must not throw the whole review away."""
    from features.portfolio import STEPS, _clean_review
    p = {"brief": {"company": "Shree Polymers", "client_words": "Our cash is always stuck."},
         "answer": {"scope": "Cash cycle, Surat plant, last 12 months", "objective": "From 95 to 60 days by March",
                    "framework_options": "Cash conversion cycle; options on debtors, stock, creditors",
                    "do_first": "Weekly debtor calls", "owner_metrics": "Finance head, debtor days weekly"}}
    raw = {"scores": {"Scope": {"score": 8}, "objective": 7, "strategy": "6", "execution": 7},
           "good": ["Clear scope"], "improve": [{"text": "Name the owner"}], "summary": "Solid first go.",
           "case_study": {"client_context": "A Surat polymer maker.", "challenge": "Cash stuck in debtors.",
                          "approach": [{"step": STEPS[i], "text": f"Did step {i + 1}."} for i in range(5)],
                          "expected_outcome": "Debtor days could fall to 60."},
           "video_script": {"hook": "h", "problem": "p", "approach": "a", "result": "r", "call_to_action": "c"}}
    r = _clean_review(raw, p)
    assert r["scores"] == {"scope": 8, "objective": 7, "strategy": 6, "execution": 7}
    assert [s["text"] for s in r["case_study"]["approach"]][:5] == [f"Did step {i + 1}." for i in range(5)]
    assert r["case_study"]["approach"][5]["text"] == "Finance head, debtor days weekly"   # filled from the member
    assert r["case_study"]["title"].startswith("Practice project: Shree Polymers")
    assert r["improve"] == ["Name the owner"]


def test_portfolio_review_still_refuses_a_review_without_a_script():
    import pytest

    import llm
    from features.portfolio import _clean_review
    raw = {"scores": {"scope": 5, "objective": 5, "strategy": 5, "execution": 5},
           "case_study": {"client_context": "x", "challenge": "y", "approach": ["a"] * 6, "expected_outcome": "z"}}
    with pytest.raises(llm.LLMError) as e:
        _clean_review(raw, {})
    assert "script.hook" in str(e.value)


def _gemini_ok(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def test_gemini_rides_out_a_high_demand_spike(monkeypatch):
    """Live: HTTP 503 UNAVAILABLE "high demand" on gemini-3.8-flash; one 4 s retry was not enough."""
    import asyncio

    import httpx

    from features import pitch_video

    async def no_sleep(_):
        return None
    monkeypatch.setattr(pitch_video.asyncio, "sleep", no_sleep)
    busy = httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "high demand"}})
    replies = [busy, busy, busy, httpx.Response(200, json=_gemini_ok('{"text": "ok"}'))]

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: replies.pop(0))) as c:
            return await pitch_video.generate_parts(c, "k", [{"text": "x"}], "s", model="m")
    assert asyncio.run(go()) == '{"text": "ok"}'


def test_gemini_falls_back_to_a_second_model_when_busy(monkeypatch):
    import asyncio

    import httpx

    from features import pitch_video

    async def no_sleep(_):
        return None
    monkeypatch.setattr(pitch_video.asyncio, "sleep", no_sleep)
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "backup-model")
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if "/models/main-model:" in str(req.url):
            return httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "high demand"}})
        return httpx.Response(200, json=_gemini_ok('{"text": "from backup"}'))

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await pitch_video.generate_parts(c, "k", [{"text": "x"}], "s", model="main-model")
    assert asyncio.run(go()) == '{"text": "from backup"}'
    assert sum("main-model" in u for u in seen) == 4 and "backup-model" in seen[-1]
    # a non-busy error (bad key, bad request) does not switch models
    monkeypatch.setattr(pitch_video, "RETRY_PAUSES_S", ())

    async def bad():
        t = httpx.MockTransport(lambda req: httpx.Response(400, json={"error": {"message": "bad"}}))
        async with httpx.AsyncClient(transport=t) as c:
            return await pitch_video.generate_parts(c, "k", [{"text": "x"}], "s", model="main-model")
    import pytest
    with pytest.raises(pitch_video.VideoError):
        asyncio.run(bad())
