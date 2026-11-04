"""Live vendor clients against mocked HTTP: web search / page reading (Anthropic server-side tools) and audio (Gemini).

No network: the Anthropic SDK client gets an httpx MockTransport; the Gemini clients get a mocked httpx.AsyncClient.
"""
import base64
import io
import json
import math
import struct
import wave

import anthropic
import httpx
import pytest

import llm
from audio import stt, tts
from core import vendors
from research import search

TOOL_URLS = ["https://www.livemint.com/companies/acme-expands-pune-plant", "https://economictimes.com/acme-q2-results",
             "https://www.business-standard.com/acme-new-ceo"]


def _msg(content, stop="end_turn"):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "test-model", "content": content,
            "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5, "server_tool_use": {"web_search_requests": 1}}}


def _search_blocks(answer_text, citations=None):
    return [
        {"type": "text", "text": "I'll search for that."},
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "acme india"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
            {"type": "web_search_result", "url": TOOL_URLS[0], "title": "Acme to expand Pune plant", "page_age": "2 days ago",
             "encrypted_content": "abc"},
            {"type": "web_search_result", "url": TOOL_URLS[1], "title": "Acme Q2: margins fall", "page_age": "October 30, 2026",
             "encrypted_content": "def"},
            {"type": "web_search_result", "url": TOOL_URLS[2], "title": "Acme names new CEO", "page_age": None,
             "encrypted_content": "ghi"},
            {"type": "web_search_result", "url": "javascript:alert(1)", "title": "bad", "encrypted_content": "x"}]},
        {"type": "text", "text": answer_text, "citations": citations},
    ]


class Recorder:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request):
        self.requests.append(json.loads(request.content))
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, httpx.Response):
            return r
        return httpx.Response(200, json=r)


@pytest.fixture
def live_search(monkeypatch):
    monkeypatch.setenv("SEARCH_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def install(*replies):
        rec = Recorder(*replies)
        client = anthropic.AsyncAnthropic(api_key="sk-test", max_retries=0,
                                          http_client=httpx.AsyncClient(transport=httpx.MockTransport(rec)))
        monkeypatch.setitem(llm._CLIENT, "c", client)
        return rec
    return install


# ------------------------------------------------------------------ vendors ----
def test_vendor_switches(monkeypatch):
    assert "openai" not in vendors.REQUIRED_KEYS and "gamma" not in vendors.REQUIRED_KEYS
    assert vendors.REQUIRED_KEYS["search"] == ("ANTHROPIC_API_KEY",)
    monkeypatch.delenv("QA_MODE", raising=False)
    monkeypatch.delenv("SEARCH_MODE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert search.mode() == "off"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert search.mode() == "live"
    monkeypatch.setenv("SEARCH_MODE", "off")
    assert search.mode() == "off"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert tts.mode() == stt.mode() == "off"
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    assert tts.mode() == stt.mode() == "live"


# ------------------------------------------------------------------ search ----
async def test_news_parses_tool_results_and_never_returns_other_urls(live_search):
    answer = json.dumps({"items": [
        {"url": "https://evil.example.com/made-up", "summary": "A link the search never returned."},
        {"url": "https://livemint.com/companies/acme-expands-pune-plant/", "summary":
            "Acme will spend ₹400 crore to double its Pune plant by March 2027. See https://x.y/z for more."},
        {"url": TOOL_URLS[1], "summary": "ok"},
    ]})
    cites = [{"type": "web_search_result_location", "url": TOOL_URLS[1], "title": "Acme Q2",
              "cited_text": "Acme's operating margin fell to 9% in the July-September quarter on higher steel costs.",
              "encrypted_index": "z"}]
    rec = live_search(_msg(_search_blocks("Here you go: " + answer, cites)))
    out = await search.news("Acme India", max_results=5)
    assert [r["url"] for r in out] == TOOL_URLS[:2]
    assert all(r["url"] in TOOL_URLS for r in out) and not any("evil" in r["url"] for r in out)
    a, b = out
    assert a["title"] == "Acme to expand Pune plant" and a["source"] == "livemint.com" and a["published"] == "2 days ago"
    assert "₹400 crore" in a["snippet"] and "http" not in a["snippet"] and a["test"] is False
    assert b["snippet"].startswith("Acme's operating margin fell")      # too-short summary → cited text
    assert b["published"] == "October 30, 2026" and b["source"] == "economictimes.com"
    body = rec.requests[0]
    tool = body["tools"][0]
    assert tool["type"] == "web_search_20250305" and tool["name"] == "web_search" and tool["max_uses"] >= 1
    assert tool["user_location"]["country"] == "IN" and tool["user_location"]["type"] == "approximate"
    assert "Acme India" in body["messages"][0]["content"]
    assert all(set(r) == {"title", "url", "source", "published", "snippet", "test"} for r in out)


async def test_news_respects_max_results_and_falls_back_to_raw_results(live_search):
    live_search(_msg(_search_blocks("Sorry, I could not format that.")))
    out = await search.news("Acme India", max_results=2)
    assert [r["url"] for r in out] == TOOL_URLS[:2]          # no JSON: the tool's own top results, links from the tool


async def test_news_empty_pick_list_means_no_news(live_search):
    live_search(_msg(_search_blocks('{"items": []}')))
    assert await search.news("Acme India") == []


async def test_news_tool_error_and_api_error_give_empty_list(live_search):
    live_search(_msg([{"type": "server_tool_use", "id": "s", "name": "web_search", "input": {"query": "q"}},
                      {"type": "web_search_tool_result", "tool_use_id": "s",
                       "content": {"type": "web_search_tool_result_error", "error_code": "too_many_requests"}},
                      {"type": "text", "text": '{"items": [{"url": "https://economictimes.com/acme-q2-results", "summary": "x y z w"}]}'}]))
    assert await search.news("Acme India") == []
    live_search(httpx.Response(400, json={"type": "error", "error": {
        "type": "invalid_request_error", "message": "web search is not enabled for this organization"}}))
    assert await search.news("Acme India") == []


async def test_news_continues_after_pause_turn(live_search):
    first = _search_blocks("")[:3]
    rec = live_search(_msg(first, stop="pause_turn"),
                      _msg([{"type": "text", "text": json.dumps({"items": [
                          {"url": TOOL_URLS[2], "summary": "Acme named Priya Rao as its new chief executive from 1 December."}]})}]))
    out = await search.news("Acme India")
    assert [r["url"] for r in out] == [TOOL_URLS[2]] and out[0]["published"] == ""
    assert len(rec.requests) == 2
    second = rec.requests[1]["messages"]
    assert second[1]["role"] == "assistant" and second[1]["content"][2]["type"] == "web_search_tool_result"


async def test_search_goes_through_the_ai_guard(live_search, monkeypatch):
    live_search(_msg(_search_blocks('{"items": []}')))
    seen = []
    real = llm._guarded

    async def spy(fn, task, timeout=None):
        seen.append((task, timeout))
        return await real(fn, task, timeout)
    monkeypatch.setattr(llm, "_guarded", spy)

    async def no_cache(key):
        return None
    monkeypatch.setattr(search, "_cache_get", no_cache)       # an earlier test may have cached this query
    await search.news("Acme India")
    assert seen and seen[0][0] == "web_search"


async def test_extract_returns_page_text_from_the_fetch_tool(live_search):
    page = "# Acme expands in Pune\n\n" + " ".join(["Acme makes auto parts in Pune and plans a second plant."] * 10)
    rec = live_search(_msg([
        {"type": "server_tool_use", "id": "f1", "name": "web_fetch", "input": {"url": "https://acme.in/news"}},
        {"type": "web_fetch_tool_result", "tool_use_id": "f1", "content": {
            "type": "web_fetch_result", "url": "https://acme.in/news", "retrieved_at": "2026-11-04T10:00:00Z",
            "content": {"type": "document", "title": "Acme news",
                        "source": {"type": "text", "media_type": "text/plain", "data": page}}}},
        {"type": "text", "text": "DONE"}]))
    out = await search.extract(["https://acme.in/news", "not a url"])
    assert len(out) == 1
    p = out[0]
    assert p["url"] == "https://acme.in/news" and p["title"] == "Acme news" and p["test"] is False
    assert "second plant" in p["text"] and "#" not in p["text"]
    assert len(rec.requests) == 1
    body = rec.requests[0]
    assert body["tools"][0]["type"] == "web_fetch_20250910" and body["tools"][0]["max_content_tokens"] > 0
    assert "https://acme.in/news" in body["messages"][0]["content"]       # the tool only fetches URLs in the conversation


async def test_extract_fetch_error_gives_nothing(live_search):
    live_search(_msg([
        {"type": "server_tool_use", "id": "f1", "name": "web_fetch", "input": {"url": "https://acme.in/x"}},
        {"type": "web_fetch_tool_result", "tool_use_id": "f1",
         "content": {"type": "web_fetch_tool_result_error", "error_code": "url_not_accessible"}},
        {"type": "text", "text": "DONE"}]))
    assert await search.extract(["https://acme.in/x"]) == []


# ------------------------------------------------------------------ Gemini audio ----
def _wav(seconds=0.5, rate=24000):
    pcm = b"".join(struct.pack("<h", int(6000 * math.sin(i / 8))) for i in range(int(rate * seconds)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue(), pcm


def _tts_reply(audio: bytes, mime="audio/wav", **extra):
    return {"id": "i1", "status": "completed", "steps": [
        {"type": "model_output", "content": [{"type": "audio", "mime_type": mime,
                                              "data": base64.b64encode(audio).decode(), **extra}]}]}


@pytest.fixture
def gemini_live(monkeypatch):
    monkeypatch.setenv("GEMINI_MODE", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_tts_chunks_long_text_and_returns_mp3(gemini_live):
    wav, _ = _wav()
    calls = []

    def handler(req):
        calls.append((str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)))
        return httpx.Response(200, json=_tts_reply(wav))
    text = " ".join(f"This is sentence number {i} about pricing your first consulting project." for i in range(160))
    parts = tts.split_text(text)
    assert len(parts) >= 3 and all(len(p) <= tts.CHUNK for p in parts)
    async with _client(handler) as c:
        data, ctype = await tts.speak(text, client=c)
    assert ctype == "audio/mpeg" and len(calls) == len(parts)
    assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)          # MP3, not WAV
    assert len(data) < len(wav) * len(parts) / 4                                       # compressed
    url, key, body = calls[0]
    assert url.endswith("/v1beta/interactions") and key == "g-test"
    assert body["model"] == "gemini-3.8-flash-tts" and body["store"] is False
    assert body["response_format"]["type"] == "audio"
    assert body["generation_config"]["speech_config"] == [{"voice": "Iapetus"}]
    item = body["input"][0]
    assert item["type"] == "user_input" and item["content"][0]["type"] == "text"
    assert item["content"][0]["annotations"][0]["type"] == "speech_metadata"
    assert sorted(b["input"][0]["content"][0]["text"] for _, _, b in calls) == sorted(parts)


async def test_tts_env_model_voice_and_raw_pcm(gemini_live, monkeypatch):
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts")
    monkeypatch.setenv("GEMINI_TTS_VOICE", "Schedar")
    _, pcm = _wav(rate=16000)
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=_tts_reply(pcm, mime="audio/l16", sample_rate=16000))
    async with _client(handler) as c:
        data, ctype = await tts.speak("Short and clear. Two sentences only.", client=c)
    assert ctype == "audio/mpeg" and len(data) > 100
    assert seen[0]["model"] == "gemini-3.8-flash-lite-tts" and seen[0]["generation_config"]["speech_config"][0]["voice"] == "Schedar"


async def test_tts_errors_raise_ttserror(gemini_live, monkeypatch):
    async with _client(lambda req: httpx.Response(400, json={"error": {"message": "bad"}})) as c:
        with pytest.raises(tts.TTSError):
            await tts.speak("Hello there. This is a test.", client=c)
    async with _client(lambda req: httpx.Response(200, json={"status": "completed", "steps": []})) as c:
        with pytest.raises(tts.TTSError):
            await tts.speak("Hello there. This is a test.", client=c)

    def boom(req):
        raise httpx.ConnectError("down", request=req)
    async with _client(boom) as c:
        with pytest.raises(tts.TTSError):
            await tts.speak("Hello there. This is a test.", client=c)
    monkeypatch.setenv("GEMINI_MODE", "off")
    with pytest.raises(tts.TTSError):
        await tts.speak("Hello there.")


async def test_stt_inline_returns_text(gemini_live):
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [
            {"type": "text", "text": '{"text": "  I cut late deliveries\\nfrom 30% to 6%  in three months. "}'}]}]})
    audio = b"\x1aE\xdf\xa3" + b"\x00" * 5000
    async with _client(handler) as c:
        out = await stt.transcribe(audio, filename="n.m4a", content_type="audio/mp4", client=c)
    assert out == "I cut late deliveries from 30% to 6% in three months."
    body = seen[0]
    part = body["input"][1]
    assert body["model"] == "gemini-3.8-flash" and body["store"] is False
    assert part["type"] == "audio" and part["mime_type"] == "audio/m4a" and base64.b64decode(part["data"]) == audio
    assert body["input"][0]["type"] == "text"


async def test_stt_large_file_uses_files_api_and_deletes_it(gemini_live, monkeypatch):
    monkeypatch.setattr(stt, "INLINE_MAX", 1000)
    log = []

    def handler(req):
        u = str(req.url)
        log.append((req.method, u))
        if req.method == "POST" and u.endswith("/upload/v1beta/files"):
            return httpx.Response(200, headers={"x-goog-upload-url": "https://upload.example/session/1"}, json={})
        if u.startswith("https://upload.example/"):
            assert req.headers["X-Goog-Upload-Command"] == "upload, finalize" and len(req.content) == 5000
            return httpx.Response(200, json={"file": {"name": "files/abc", "uri": "https://g/files/abc", "state": "ACTIVE",
                                                      "mimeType": "audio/webm"}})
        if u.endswith("/v1beta/interactions"):
            part = json.loads(req.content)["input"][1]
            assert part == {"type": "audio", "uri": "https://g/files/abc", "mime_type": "audio/webm"}
            return httpx.Response(200, json={"status": "completed", "steps": [{"type": "model_output", "content": [
                {"type": "text", "text": '{"text": "Hello from a long note."}'}]}]})
        if req.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(404)
    async with _client(handler) as c:
        out = await stt.transcribe(b"\x00" * 5000, content_type="video/webm", client=c)
    assert out == "Hello from a long note."
    assert ("DELETE", "https://generativelanguage.googleapis.com/v1beta/files/abc") in log


async def test_stt_errors_raise_stterror(gemini_live, monkeypatch):
    async with _client(lambda req: httpx.Response(400, json={})) as c:
        with pytest.raises(stt.STTError):
            await stt.transcribe(b"x" * 2000, client=c)
    empty = {"status": "completed", "steps": [{"type": "model_output", "content": [{}]}]}
    async with _client(lambda req: httpx.Response(200, json=empty)) as c:
        with pytest.raises(stt.STTError):
            await stt.transcribe(b"x" * 2000, client=c)

    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)
    async with _client(boom) as c:
        with pytest.raises(stt.STTError):
            await stt.transcribe(b"x" * 2000, client=c)
    with pytest.raises(stt.STTError):
        await stt.transcribe(b"x" * (stt.MAX_BYTES + 1))
    monkeypatch.setenv("GEMINI_MODE", "off")
    with pytest.raises(stt.STTError):
        await stt.transcribe(b"x" * 2000)


async def test_stt_retries_once_when_busy(gemini_live, monkeypatch):
    monkeypatch.setattr(stt, "RETRY_PAUSE_S", 0)
    replies = [httpx.Response(503, json={}), httpx.Response(200, json={"status": "completed", "steps": [
        {"type": "model_output", "content": [{"type": "text", "text": '{"text": ""}'}]}]})]
    async with _client(lambda req: replies.pop(0)) as c:
        assert await stt.transcribe(b"x" * 2000, client=c) == ""       # nothing said → empty text, not an error


async def test_news_is_cached_for_six_hours(monkeypatch, mdb):
    import state
    state.set_db(mdb)
    calls = []

    async def fake_news(query, max_results=6, *, queue_wait=None):
        calls.append(query)
        return [{"title": "T", "url": "https://x.in/a", "source": "x.in", "published": "", "snippet": "s", "test": True}]
    monkeypatch.setattr(search, "_news", fake_news)
    a = await search.news("Cache Test Co  India", 5)
    b = await search.news("cache test co india", 5)          # same query, other spacing/case → cached
    assert a == b and len(calls) == 1
    await mdb.search_cache.update_many({}, {"$set": {"purge_at": search.utcnow() - search.timedelta(minutes=1)}})
    await search.news("cache test co india", 5)
    assert len(calls) == 2                                    # expired → searched again
