"""The module registry: which parts of the app exist and in what order they are mounted.

Each entry is a dotted module path. A module contributes by exposing any of:

    router         APIRouter mounted under /api                       (required)
    public_router  APIRouter mounted at the site root (member websites at /s/<name>, …)

Modules also self-register their indexes, jobs, analytics events and inbox message kinds at import time
(`indexes.register`, `jobs.registry.register`, `growth.events.register`, `notify.service.register_kind`), which is why
importing every module here before start-up is what makes those registries complete.

To add a tool: create `features/<name>.py` (or a `features/<name>/` package, see `features/cases/`) and list it in
the right group below. Nothing else needs editing.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

PLATFORM = ("auth", "accounts.routes", "misc_routes", "notify.service", "billing.routes", "jobs.routes",
            "admin.routes", "media", "growth.events")

# Free account (webinar) tools
WEBINAR = ("features.readiness", "features.start", "features.cases", "features.brief", "features.linkedin",
           "features.file")

# ₹1,999 plan
MEMBER = ("features.weekly", "features.decks", "features.visuals", "features.listen", "features.progress",
          "features.docs", "features.website", "features.support")

# L1
L1 = ("features.gpts", "features.akshat_ai", "features.program", "features.calls", "features.library",
      "features.recaps", "features.offer_card", "features.stories", "features.insights", "features.portfolio",
      "features.pitch", "features.notebook")

# L2 Mentorship
L2 = ("features.network", "features.outreach", "features.radar", "features.call_prep", "features.proposals",
      "features.diagnostic", "features.social", "features.bootcamps")

ALL: tuple[str, ...] = PLATFORM + WEBINAR + MEMBER + L1 + L2


@dataclass(frozen=True)
class LoadedModule:
    name: str
    module: ModuleType

    @property
    def router(self):
        return getattr(self.module, "router")

    @property
    def public_router(self):
        return getattr(self.module, "public_router", None)


def load(names: tuple[str, ...] = ALL) -> list[LoadedModule]:
    out = []
    for name in names:
        mod = importlib.import_module(name)
        if not hasattr(mod, "router"):
            raise RuntimeError(f"module {name} has no `router`")
        out.append(LoadedModule(name, mod))
    return out
