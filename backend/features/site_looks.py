"""Website looks for consultants (ported from Owner Desk's site looks, with the six industry palettes of the current hub's
Website Builder GPT). Each look is a full palette, a font pairing and a corner style; the page structure is the same.
The member picks one (we suggest one from their industry). "editorial" is the L2 look: a light, magazine-style page
with a large serif type and numbered sections (the current hub's Editorial Website Builder).

Fonts load as one Google Fonts stylesheet (CSS only, font-display swap). The page itself has no JavaScript.
"""
from __future__ import annotations

import re
from urllib.parse import quote

LOOKS: dict[str, dict] = {
    "boardroom": {"name": "Boardroom", "about": "Deep navy and warm gold. Calm and senior. Suits finance, legal and strategy.",
                  "dark": True, "fonts": (("DM Serif Display", "400"), ("Inter", "400;500;600")), "r": "10px",
                  "c": {"bg": "#0A1628", "alt": "#101E35", "card": "#162032", "line": "#26344D", "ink": "#F5F3EE",
                        "muted": "#B8C0CE", "accent": "#C9A84C", "accent2": "#F5E6C8", "hi": "#F0C24B", "on": "#0A1628"}},
    "mentor": {"name": "Mentor", "about": "Forest green and terracotta. Warm and steady. Suits HR, leadership and coaching.",
               "dark": True, "fonts": (("Fraunces", "600"), ("Inter", "400;500;600")), "r": "14px",
               "c": {"bg": "#0D2B1F", "alt": "#123426", "card": "#112820", "line": "#24473A", "ink": "#FDFAF4",
                     "muted": "#B5C6B5", "accent": "#E08A5A", "accent2": "#FAF0DC", "hi": "#E8B84B", "on": "#1B1208"}},
    "signal": {"name": "Signal", "about": "Charcoal and electric cyan. Sharp and modern. Suits technology, data and AI.",
               "dark": True, "fonts": (("Space Grotesk", "500;700"), ("Inter", "400;500;600")), "r": "8px",
               "c": {"bg": "#0E0E1A", "alt": "#15152A", "card": "#12121F", "line": "#262640", "ink": "#FFFFFF",
                     "muted": "#B0B8C8", "accent": "#00D4FF", "accent2": "#A58BFF", "hi": "#00FFD1", "on": "#04121A"}},
    "works": {"name": "Works", "about": "Steel grey and burnt orange. Solid and practical. Suits manufacturing and operations.",
              "dark": True, "fonts": (("Barlow Condensed", "600;700"), ("Barlow", "400;500;600")), "r": "3px",
              "c": {"bg": "#0F1419", "alt": "#161C22", "card": "#1A2129", "line": "#2A333D", "ink": "#FFFFFF",
                    "muted": "#C8C0B8", "accent": "#EE7440", "accent2": "#F5A623", "hi": "#F5A623", "on": "#120A05"}},
    "care": {"name": "Care", "about": "Deep teal and soft gold. Reassuring and clear. Suits healthcare and life sciences.",
             "dark": True, "fonts": (("Plus Jakarta Sans", "600;800"), ("Inter", "400;500;600")), "r": "16px",
             "c": {"bg": "#0A2028", "alt": "#0F2A35", "card": "#0D2530", "line": "#1F3F4B", "ink": "#FFFFFF",
                   "muted": "#B8D4D8", "accent": "#2EC4B6", "accent2": "#D4AF6A", "hi": "#4ECDC4", "on": "#04201C"}},
    "launch": {"name": "Launch", "about": "Rich black with gold. Bold and confident. Suits sales, FMCG, retail and startups.",
               "dark": True, "fonts": (("Sora", "600;700"), ("Inter", "400;500;600")), "r": "12px",
               "c": {"bg": "#0A0A0A", "alt": "#141414", "card": "#111111", "line": "#2A2A2A", "ink": "#FFFFFF",
                     "muted": "#CFC8BC", "accent": "#FFD24A", "accent2": "#3DDC84", "hi": "#FFD24A", "on": "#0A0A0A"}},
    "paper": {"name": "Paper", "about": "White page, deep blue accent. Clean and quiet. Suits any field.",
              "dark": False, "fonts": (("Sora", "600;700"), ("Inter", "400;500;600")), "r": "10px",
              "c": {"bg": "#FFFFFF", "alt": "#F4F5F7", "card": "#FFFFFF", "line": "#E3E6EB", "ink": "#14181F",
                    "muted": "#545B66", "accent": "#1F4E79", "accent2": "#A07E2C", "hi": "#1F4E79", "on": "#FFFFFF"}},
    "editorial": {"name": "Editorial", "about": "Cream paper, large serif type and numbered sections, like a magazine. L2 only.",
                  "dark": False, "editorial": True, "fonts": (("Instrument Serif", "400"), ("Inter", "400;500;600")),
                  "r": "2px", "min_plan": "l2",
                  "c": {"bg": "#F6F1E7", "alt": "#EFE7D8", "card": "#FBF8F2", "line": "#D9CFBD", "ink": "#1B1A17",
                        "muted": "#5B564D", "accent": "#7A2E2A", "accent2": "#1B1A17", "hi": "#7A2E2A", "on": "#FFFFFF"}},
}
DEFAULT = "boardroom"

# industry words → the look we suggest first (the member can pick any other)
SUGGEST = [
    ("care", r"\b(health|hospital|pharma|clinic|medical|wellness|life ?science|diagnostic|nursing)"),
    ("signal", r"\b(tech|software|it\b|data|ai\b|digital|cloud|cyber|saas|analytics|automation)"),
    ("works", r"\b(manufactur|operation|supply|logistic|plant|engineer|quality|procure|factory|warehouse|lean)"),
    ("mentor", r"\b(hr\b|people|leader|coach|culture|talent|training|learning|human resource|education)"),
    ("launch", r"\b(sales|fmcg|retail|startup|real estate|marketing|brand|d2c|consumer|distribution)"),
    ("boardroom", r"\b(financ|bank|legal|law|account|tax|audit|strategy|insurance|compliance|investment)"),
]


def allowed(look: str, plan: str) -> bool:
    from plans import RANK
    lk = LOOKS.get(look)
    return bool(lk) and RANK.get(plan, 0) >= RANK[lk.get("min_plan", "member")]


def suggest(*words: str) -> str:
    t = " ".join(w for w in words if w).lower()
    for key, rx in SUGGEST:
        if re.search(rx, t):
            return key
    return DEFAULT


def listing(plan: str) -> list[dict]:
    return [{"key": k, "name": v["name"], "about": v["about"], "dark": v["dark"], "locked": not allowed(k, plan),
             "plan_needed": v.get("min_plan", "member"), "colors": [v["c"]["bg"], v["c"]["accent"], v["c"]["ink"]]}
            for k, v in LOOKS.items()]


def theme(look: str, plan: str) -> dict:
    """CSS values for the page. A look the plan no longer opens falls back to the default."""
    key = look if look in LOOKS and allowed(look, plan) else DEFAULT
    lk = LOOKS[key]
    (hf, hw), (bf, bw) = lk["fonts"]
    fams = [(hf, hw)] + ([(bf, bw)] if bf != hf else [])
    url = "https://fonts.googleapis.com/css2?" + "&".join(
        f"family={quote(f).replace('%20', '+')}:wght@{w}" for f, w in fams) + "&display=swap"
    return {"key": key, "name": lk["name"], "dark": lk["dark"], "editorial": bool(lk.get("editorial")),
            "head": hf, "body": bf, "fonts_url": url, "r": lk["r"], **lk["c"]}
