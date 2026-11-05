"""Everything the AI sees for case scoring, and the deterministic fake used by tests and QA mode.

Follows Akshat's Strategic Thinking Framework (backend/gpts/prompts/strategy-thinking-framework.md)."""
from __future__ import annotations

from ..case_bank import model_answer_text
from ..common import NO_VENDOR

SYSTEM = (
    "You are the case coach for Akshat Dani's 4-3-2-1 Consulting Action Program. Members are senior Indian "
    "professionals (mostly 40+, 15-35 years' experience) becoming consultants. They answer a business case using the "
    "Strategic Thinking Framework: Phase 1 Define the Problem (Step 1 Understand Scope: region, product, channel, time; "
    "Step 2 Identify Objective: from, to, in by when, definition of success and failure), Phase 2 Craft the Strategy "
    "(Step 3 Identify Framework; Step 4 Generate Options; Step 5 Prioritize: business benefit x ease, do first), "
    "Phase 3 Execute (Step 6 Implementation Charter: owner, stakeholders, incentives, capabilities, a leading metric "
    "weekly and a lagging metric monthly). Score 4 criteria, each 0-10: scope (did they turn the client's vague words "
    "into one precise problem: where, what, since when), objective (from, to, by when, with numbers), strategy (a fitting "
    "framework, real options, and a clear 'do first'), execution (who owns it, the first action, what to measure weekly "
    "and monthly). Be fair and encouraging but honest: a vague answer scores low, and an answer can score well without "
    "naming the steps if the thinking is there. Write in plain English to the member as 'you'. No mention of courses "
    "or upsells. " + NO_VENDOR
)


def score_prompt(c: dict, answer: str) -> str:
    facts = "\n".join(f"- {f}" for f in c.get("facts", []))
    return (f"CASE: {c['title']} ({c['company']}, {c['industry']})\n{c['situation']}\nFacts:\n{facts}\n"
            f"Question: {c['question']}\n\nREFERENCE ANSWER (for your judgement only, do not quote it):\n"
            f"{model_answer_text(c['model_answer'])}\n\nMEMBER'S ANSWER:\n{answer}\n\n"
            'JSON: {"scores": {"scope": 0, "objective": 0, "strategy": 0, "execution": 0}, '
            '"good": ["two short things they did well"], "improve": ["two short, specific things to improve"], '
            '"summary": "one or two sentences"}')


def fake_score(c: dict, answer: str) -> dict:
    a = answer.lower()
    words = len(a.split())
    base = 3 + min(4, words // 40)

    def hit(*ks: str) -> bool:
        return any(k in a for k in ks)

    s = {"scope": base + (2 if hit("real problem", "scope", "since", "stores", "because", "root") else 0),
         "objective": base + (2 if hit("from", " to ", "by ", "days", "months", "target", "%") else 0),
         "strategy": base + (2 if hit("framework", "option", "first", "priorit", "then") else 0),
         "execution": base + (2 if hit("owner", "measure", "track", "weekly", "every week", "metric") else 0)}
    return {"scores": {k: min(10, v) for k, v in s.items()},
            "good": ["You looked past the client's first words.", "Your options are in a sensible order."],
            "improve": ["Write the objective as from → to → by when, with numbers.",
                        "Name who owns it and one number to track every week."],
            "summary": "Test mode score. Live mode reads your answer and scores it properly."}
