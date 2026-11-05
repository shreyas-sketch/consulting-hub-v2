"""Cases: the live case on the webinar, the practice bank, and (₹1,999 plan) the weekly case from real news.

Reference layout for a tool (see docs/ARCHITECTURE.md):

    router.py      HTTP only: parse, call the service, return a dict
    service.py     business rules: plan checks, metering, AI calls, validation of AI output
    repository.py  the only code that queries this tool's collections
    prompts.py     the AI's instructions and the deterministic fake used by tests / QA
    schemas.py     request bodies and the mappers that shape responses
"""
from .prompts import SYSTEM
from .router import router
from .service import WEBINAR_QUEUE_WAIT, CaseService, ensure_seed, get_case

__all__ = ["router", "SYSTEM", "CaseService", "ensure_seed", "get_case", "WEBINAR_QUEUE_WAIT"]
