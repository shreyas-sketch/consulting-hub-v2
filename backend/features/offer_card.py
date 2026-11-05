"""Offer Card: the member's consulting offer on one printable page.

Follows Step 5 "Your Consulting Offer" of the current hub's Define Your Niche GPT (offer name, ideal client, problem,
outcome, suggested engagement for a beginner, suggested fee in India) and the packaging rules of the Signature Offer
Builder (a clear promise, concrete deliverables, honest: no outcome guarantees). Proof comes only from what the member
told us (their Career Story Bank stories or their own notes), never invented.

offer_cards {_id, user_id, input: {...}, offer_name, ideal_client, problem, outcome, engagement, what_you_get: [str],
             fee_from_inr, fee_to_inr, fee_basis, proof, call_to_action, edited: bool, at, updated_at}

The card fields sit at the top level of the document: the Website Builder reads the member's latest card
(sorted by `at`) and uses these exact names. Editing a card (PUT) is free; making one is metered (`offer_card`).
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

import indexes
import llm
import plans
from core.deps import user_dep
from core.errors import NotFound
from growth import events
from growth.clock import utcnow
from state import db
from util import inr, iso

from .common import clamp_int, run_metered, text, text_list
from .knowledge import knowledge, system_block

router = APIRouter(prefix="/offer-card", tags=["offer-card"])

events.register("offer_card_made", "Offer Card made by AI (props.edited_inputs)")
events.register("offer_card_edited", "Offer Card fields edited and saved")
indexes.register("offer_cards", [("user_id", 1), ("at", -1)])

FIELDS = ("offer_name", "ideal_client", "problem", "outcome", "engagement", "what_you_get", "fee_from_inr", "fee_to_inr",
          "fee_basis", "proof", "call_to_action")
FEE_MIN, FEE_MAX = 5_000, 1_00_00_000

SYSTEM = (
    "You write the one-page consulting offer for a member of Akshat Dani's 4-3-2-1 Consulting Action Program. Members "
    "are experienced Indian professionals (mostly 40+, 15-35 years in jobs) launching as consultants. You follow the "
    "'Your Consulting Offer' step of Akshat's Define Your Niche method: Offer Name, Ideal Client, Problem You Solve, "
    "Outcome, Suggested Engagement (Beginner), Suggested Fee (India). Make ONE offer, never several. Be specific: one "
    "kind of client, one painful problem, one clear result. Package it like a signature offer: a clear promise, "
    "concrete deliverables a client can picture, a sensible engagement length. Keep it honest: it must reflect what "
    "the member can really deliver. Never guarantee an outcome and never promise the member income. Fees in Indian "
    "rupees only, realistic for India: beginner consultants typically charge ₹10,000-₹50,000 per client a month, "
    "established ones ₹50,000-₹2,00,000, specialists more; adjust for the niche and the client's size. Proof: use only "
    "facts and numbers the member gave (their stories or notes). Never invent numbers, clients, companies or results; "
    "if there is no proof yet, write one honest line about their experience without any number. Plain, short, spoken "
    "English. No buzzwords, no hype, no emojis. Avoid: unlock, leverage, game-changer, seamless, robust, elevate, "
    "empower, transformative, passionate, results-driven. Never mention or describe the AI or who makes it."
)


class OfferIn(BaseModel):
    offer_name: str = Field("", max_length=80)
    engagement: str = Field("", max_length=160)          # e.g. "3 months, one visit a week"
    what_you_get: str = Field("", max_length=800)        # what the client gets, in the member's words
    fee_from_inr: Optional[int] = Field(None, ge=FEE_MIN, le=FEE_MAX)
    fee_to_inr: Optional[int] = Field(None, ge=FEE_MIN, le=FEE_MAX)
    notes: str = Field("", max_length=800)               # anything else: proof, who it's for

    @model_validator(mode="after")
    def _fees(self):
        if self.fee_from_inr and self.fee_to_inr and self.fee_to_inr < self.fee_from_inr:
            raise ValueError("The top of your fee range must be at least the bottom.")
        return self


class OfferEdit(BaseModel):
    offer_name: str = Field(..., min_length=2, max_length=80)
    ideal_client: str = Field(..., min_length=2, max_length=240)
    problem: str = Field(..., min_length=2, max_length=300)
    outcome: str = Field(..., min_length=2, max_length=300)
    engagement: str = Field(..., min_length=2, max_length=200)
    what_you_get: list[str] = Field(..., min_length=1, max_length=8)
    fee_from_inr: int = Field(..., ge=FEE_MIN, le=FEE_MAX)
    fee_to_inr: int = Field(..., ge=FEE_MIN, le=FEE_MAX)
    fee_basis: str = Field("", max_length=60)
    proof: str = Field("", max_length=400)
    call_to_action: str = Field(..., min_length=2, max_length=240)

    @field_validator("what_you_get")
    @classmethod
    def _items(cls, v: list[str]) -> list[str]:
        out = [text(x, 160) for x in v if text(x, 160)]
        if not out:
            raise ValueError("Add at least one thing the client gets.")
        return out

    @model_validator(mode="after")
    def _fees(self):
        if self.fee_to_inr < self.fee_from_inr:
            raise ValueError("The top of your fee range must be at least the bottom.")
        return self


async def _proof_material(uid: str) -> list[str]:
    """Up to three of the member's own Career Story Bank stories (title + result): the only proof the AI may use."""
    out = []
    async for s in db().stories.find({"user_id": uid}, {"title": 1, "result": 1}).sort("at", -1).limit(3):
        if s.get("result"):
            out.append(f"{s.get('title') or 'Story'}: {s['result']}")
    return out


def _fake(body: OfferIn, k: dict, proof: list[str]) -> dict:
    who = k.get("target_audience") or "owner-led Indian businesses with ₹10-100 crore revenue"
    prob = "profit that doesn't grow with sales"
    niche = k.get("niche") or "Operations consulting"
    lo = body.fee_from_inr or 25000
    hi = body.fee_to_inr or max(lo, 75000)
    items = [x.strip(" -•") for x in body.what_you_get.replace(";", "\n").split("\n") if x.strip(" -•")] or [
        "A two-week diagnosis of where the money and time go", "One clear 90-day plan with owners and dates",
        "A weekly 60-minute working session with your team", "One page of numbers to track every week"]
    return {"offer_name": body.offer_name or f"The 90-Day {niche.split(' for ')[0].title()} Reset",
            "ideal_client": who, "problem": prob[0].upper() + prob[1:],
            "outcome": "A clear plan and a team that runs it, with one number moving in the right direction in 90 days.",
            "engagement": body.engagement or "3 months: a 2-week diagnosis, then weekly working sessions",
            "what_you_get": items[:6], "fee_from_inr": lo, "fee_to_inr": hi, "fee_basis": "per month",
            "proof": proof[0] if proof else "Years of running this kind of work from the inside, not from a textbook.",
            "call_to_action": "Book a 30-minute conversation. We'll look at one problem together and see if this fits.",
            "note": "Test mode card. Live mode writes it from what the app knows about you."}


def _prompt(body: OfferIn, k: dict, proof: list[str], name: Optional[str]) -> str:
    kb = system_block(k) or "Nothing known yet about their niche: build the best offer from their inputs."
    given = [("Offer name they want", body.offer_name), ("Engagement they have in mind", body.engagement),
             ("What the client gets (their words)", body.what_you_get),
             ("Fee range they want", f"{inr(body.fee_from_inr)} to {inr(body.fee_to_inr)}"
              if body.fee_from_inr and body.fee_to_inr else (inr(body.fee_from_inr or body.fee_to_inr)
                                                             if (body.fee_from_inr or body.fee_to_inr) else "")),
             ("Other notes", body.notes)]
    lines = "\n".join(f"- {a}: {b}" for a, b in given if b) or "- Nothing extra: suggest everything."
    pr = "\n".join(f"- {p}" for p in proof) or "- None yet."
    return (f"{kb}\n\n" + (f"FINALIZED NICHE PACKAGE:\n{k['blueprint']}\n\n" if k.get("blueprint") else "")
            + f"Member name: {name or 'not given'}\n\nWHAT THE MEMBER TYPED (keep their choices; improve wording only):\n{lines}\n\n"
            f"THEIR OWN PROOF (from their Career Story Bank; the only numbers you may use):\n{pr}\n\n"
            "Write the offer card: offer_name (a short, plain name, max 8 words), ideal_client (who exactly: kind of "
            "business, size, decision-maker), problem (the painful problem, in the client's words), outcome (what "
            "changes for the client, with a time frame; no guarantee), engagement (length and rhythm for a beginner "
            "consultant), what_you_get (4-6 concrete deliverables or touchpoints, each under 12 words), fee_from_inr and "
            "fee_to_inr (whole rupees; keep the member's range if they gave one), fee_basis (e.g. 'per month' or 'for the "
            "full engagement'), proof (one or two sentences), call_to_action (one inviting next step, low pressure).\n"
            'JSON: {"offer_name": "", "ideal_client": "", "problem": "", "outcome": "", "engagement": "", '
            '"what_you_get": [""], "fee_from_inr": 0, "fee_to_inr": 0, "fee_basis": "", "proof": "", "call_to_action": ""}')


def _clean(raw: dict, body: OfferIn) -> dict:
    card = {"offer_name": text(raw.get("offer_name"), 80), "ideal_client": text(raw.get("ideal_client"), 240),
            "problem": text(raw.get("problem"), 300), "outcome": text(raw.get("outcome"), 300),
            "engagement": text(raw.get("engagement"), 200), "what_you_get": text_list(raw.get("what_you_get"), 6, 160),
            "fee_basis": text(raw.get("fee_basis"), 60), "proof": text(raw.get("proof"), 400),
            "call_to_action": text(raw.get("call_to_action"), 240)}
    need = ("offer_name", "ideal_client", "problem", "outcome", "engagement", "call_to_action")
    if not all(card[f] for f in need) or len(card["what_you_get"]) < 2:
        raise llm.LLMError("offer_card: incomplete")
    lo = clamp_int(raw.get("fee_from_inr"), 0, FEE_MAX, 0)
    hi = clamp_int(raw.get("fee_to_inr"), 0, FEE_MAX, 0)
    if body.fee_from_inr or body.fee_to_inr:        # the member's own numbers win
        lo = body.fee_from_inr or body.fee_to_inr
        hi = body.fee_to_inr or body.fee_from_inr
    if lo < FEE_MIN and hi < FEE_MIN:
        raise llm.LLMError("offer_card: no fee")
    lo, hi = max(FEE_MIN, lo or hi), max(FEE_MIN, hi or lo)
    card["fee_from_inr"], card["fee_to_inr"] = min(lo, hi), max(lo, hi)
    return card


def _public(d: dict) -> dict:
    return {"id": d["_id"], **{f: d.get(f) for f in FIELDS}, "edited": bool(d.get("edited")), "input": d.get("input") or {},
            "at": iso(d["at"]), "updated_at": iso(d.get("updated_at") or d["at"])}


async def _own(card_id: str, uid: str) -> dict:
    d = await db().offer_cards.find_one({"_id": card_id, "user_id": uid})
    if not d:
        raise NotFound("Offer Card not found.")
    return d


@router.post("")
async def make(body: OfferIn, user: dict = Depends(user_dep())):
    uid = str(user["_id"])

    async def work(plan: str):
        k = await knowledge(db(), user)
        proof = await _proof_material(uid)
        raw = await llm.complete_json(task="offer_card", system=SYSTEM, prompt=_prompt(body, k, proof, user.get("name")),
                                      fake=lambda: _fake(body, k, proof), model="strong", max_tokens=1000)
        card = _clean(raw, body)
        now = utcnow()
        doc = {"_id": uuid.uuid4().hex, "user_id": uid, "input": body.model_dump(), **card, "edited": False,
               "at": now, "updated_at": now}
        await db().offer_cards.insert_one(doc)
        await events.track(db(), "offer_card_made", user_id=uid,
                           props={"edited_inputs": sum(1 for v in body.model_dump().values() if v)})
        return _public(doc)
    return await run_metered(db(), user, "offer_card", work)


@router.get("")
async def mine(user: dict = Depends(user_dep())):
    rows = [_public(d) async for d in db().offer_cards.find({"user_id": str(user["_id"])}).sort("at", -1).limit(20)]
    return {"latest": rows[0] if rows else None,
            "history": [{"id": r["id"], "offer_name": r["offer_name"], "edited": r["edited"], "at": r["at"],
                         "updated_at": r["updated_at"]} for r in rows]}


@router.get("/{card_id}")
async def one(card_id: str, user: dict = Depends(user_dep())):
    return _public(await _own(card_id, str(user["_id"])))


@router.put("/{card_id}")
async def edit(card_id: str, body: OfferEdit, user: dict = Depends(user_dep())):
    """Save the member's own edits. Free: no AI, not metered."""
    uid = str(user["_id"])
    await plans.require(db(), user, "offer_card")
    await _own(card_id, uid)
    await db().offer_cards.update_one({"_id": card_id, "user_id": uid},
                                      {"$set": {**body.model_dump(), "edited": True, "updated_at": utcnow()}})
    await events.track(db(), "offer_card_edited", user_id=uid)
    return _public(await _own(card_id, uid))
