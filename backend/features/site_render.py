"""Website Builder: turns a stored site into the HTML a visitor sees (templates/site.html, Jinja2, no JavaScript).

`base` is the prefix links on the page use: "/s/<slug>" on the hub, "" on the site's own address (own domain or
<slug>.SITES_DOMAIN, rewritten by install_domain_middleware in website.py).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

import plans
from core.settings import settings
from growth.clock import IST, utcnow

from . import site_looks
from .site_model import PAGE_KEYS, PAGE_LABEL, PLACEHOLDER, public_data

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]),
                   trim_blocks=True, lstrip_blocks=True)


def _ph(v) -> Markup:
    """Escaped text with any [placeholder] marked (only the owner's preview ever has them)."""
    e = str(escape(v or ""))
    return Markup(PLACEHOLDER.sub(lambda m: f'<mark class="ph">{m.group(0)}</mark>', e))


def _paras(v) -> list[str]:
    return [p for p in str(v or "").split("\n\n") if p.strip()]


_env.filters["ph"] = _ph
_env.filters["paras"] = _paras


def app_host() -> str:
    return (urlparse(public_base()).hostname or "").lower()


def public_base() -> str:
    return settings.app.public_base_url


def sites_domain() -> str:
    return settings.sites.domain


def site_root(site: dict, plan: str) -> str:
    """The site's main address: its own domain once connected (and on L1/L2), else <slug>.SITES_DOMAIN, else the hub."""
    if site.get("domain") and site.get("domain_status") == "connected" and plans.cap("custom_domain", plan):
        return f"https://{site['domain']}"
    sd = sites_domain()
    if sd:
        return f"https://{site['slug']}.{sd}"
    return f"{public_base()}/s/{site['slug']}"


def page_keys_for(site: dict, plan: str) -> list[str]:
    """Pages a visitor can open: the site's pages, in menu order, up to the plan's page count."""
    have = [k for k in PAGE_KEYS if k in (site.get("pages") or {})]
    return have[:max(1, plans.cap("site_pages", plan))]


def wa_digits(v: str) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    if len(d) == 10:
        d = "91" + d
    return d if 11 <= len(d) <= 15 else ""


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p[:1].isalpha()]
    return "".join(p[0] for p in parts[:2]).upper() or "C"


def _has_content(site: dict, key: str) -> bool:
    """A page is in the live menu only when a visitor would find something on it besides the contact form."""
    return any(not s.get("hidden") and s["type"] != "contact" and public_data(s["type"], s.get("data") or {}) is not None
               for s in (site.get("pages") or {}).get(key, []))


FORM_ERRORS = {"details": "Please add your name, and an email or a phone number.",
               "busy": "Too many messages from this network just now. Please try again in a few minutes."}


def render(site: dict, page_key: str, *, plan: str, preview: bool, base: str, sent: bool = False,
           err: str = "") -> str:
    keys = page_keys_for(site, plan)
    th = site_looks.theme(site.get("look") or "", plan)
    prof = site.get("profile") or {}
    name = prof.get("name") or "Consultant"
    title = prof.get("title") or ""
    sections = []
    for s in (site.get("pages") or {}).get(page_key, []):
        if s.get("hidden"):
            continue
        d = s.get("data") or {}
        d = d if preview else public_data(s["type"], d)
        if d is not None:
            sections.append({"id": s["id"], "type": s["type"], "d": d})
    has_contact = any(s["type"] == "contact" for s in sections)
    contact = site.get("contact") or {}
    wa = wa_digits(contact.get("whatsapp"))
    booking = contact.get("calendly") or ""
    if booking:
        cta_href, cta_ext = booking, True
    elif has_contact or "contact" not in keys:
        cta_href, cta_ext = "#contact", False
    else:
        cta_href, cta_ext = f"{base}/contact", False
    root = site_root(site, plan)
    v = lambda bid: (bid or "")[:8]  # noqa: E731 — cache-busting suffix
    logo = f"{base}/img/logo?v={v(site.get('logo_id'))}" if site.get("logo_id") else ""
    photo = f"{base}/img/photo?v={v(site.get('photo_id'))}" if site.get("photo_id") else ""
    og = (f"{root}/img/photo?v={v(site.get('photo_id'))}" if site.get("photo_id")
          else f"{root}/img/logo?v={v(site.get('logo_id'))}" if site.get("logo_id") else "")
    hero = next((s["d"] for s in sections if s["type"] == "hero"), None)
    # one h1 per page: Home's headline; on other pages the first section's heading
    h1_id = (next((s["id"] for s in sections if s["type"] == "hero"), None) if page_key == "home"
             else (sections[0]["id"] if sections else None))
    seo = site.get("seo") or {}
    label = PAGE_LABEL.get(page_key, "")
    page_title = (seo.get("title") or (f"{name} | {title}" if title else name)) if page_key == "home" else f"{label} | {name}"
    desc = seo.get("description") or (hero or {}).get("sub") or (f"{name}, {title}." if title else name)
    shown = [k for k in keys if k in ("home", "contact", page_key) or preview or _has_content(site, k)]
    nav = [{"key": k, "label": PAGE_LABEL[k], "href": (base or "/") if k == "home" else f"{base}/{k}"}
           for k in shown] if len(shown) > 1 else []
    ctx = {
        "t": th, "name": name, "title": title, "initials": _initials(name), "page_key": page_key, "page_label": label,
        "sections": sections, "nav": nav, "h1_id": h1_id, "base": base, "preview": preview, "published": bool(site.get("published")),
        "email": contact.get("email") or "", "wa_link": f"https://wa.me/{wa}" if wa else "", "booking": booking,
        "cta_href": cta_href, "cta_ext": cta_ext, "logo": logo, "photo": photo,
        "seo": {"title": page_title[:80], "description": desc[:170], "canonical": root + ("" if page_key == "home" else f"/{page_key}"),
                "image": og},
        "form_action": f"/api/website/public/{site['slug']}/leads", "sent": sent, "form_error": FORM_ERRORS.get(err, ""),
        "year": utcnow().astimezone(IST).year,
    }
    return _env.get_template("site.html").render(**ctx)


def not_found_html() -> str:
    return _env.get_template("site_404.html").render()
