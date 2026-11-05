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


def test_json_calls_get_at_least_the_minimum_room(monkeypatch):
    """Offer Card asked for 1,000 tokens and the live answer was cut mid-JSON → "AI is busy"."""
    import asyncio

    import llm
    seen = {}

    async def fake_call(*, model, max_tokens, system, content):
        seen["max_tokens"] = max_tokens
        return '{"ok": true}'
    monkeypatch.setattr(llm, "mode", lambda: "live")
    monkeypatch.setattr(llm, "_call_text", fake_call)
    out = asyncio.run(llm.complete_json(task="t", system="s", prompt="p", fake=dict, model="strong", max_tokens=1000))
    assert out == {"ok": True} and seen["max_tokens"] == llm.MIN_JSON_TOKENS
    asyncio.run(llm.complete_json(task="t", system="s", prompt="p", fake=dict, model="strong", max_tokens=7000))
    assert seen["max_tokens"] == 7000
