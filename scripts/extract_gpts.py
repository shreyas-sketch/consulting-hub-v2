"""Split the current hub's working document into one prompt file per GPT plus a catalogue.

    python scripts/extract_gpts.py path/to/Consultation_Hub_Working.md

Writes backend/gpts/catalog.json and backend/gpts/prompts/<slug>.md (verbatim prompt text).
Re-run whenever the team exports a fresh working document.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "gpts"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("&", " and ").replace(":", " ")).strip("-")
    return re.sub(r"-+", "-", s)


def main(src: str) -> None:
    lines = Path(src).read_text(encoding="utf-8").split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("# Appendix"))
    program, cur, fence, buf, items = None, None, False, [], []
    for line in lines[start:]:
        if not fence:
            if line.startswith("## Action Program"):
                program = "action"
                continue
            if line.startswith("## 6 Months Mentorship"):
                program = "mentorship"
                continue
            if line.startswith("### ") and program:
                cur = {"name": line[4:].strip(), "program": program, "starter": None, "description": None}
                continue
            m = re.match(r"^\*Starter:\*\s*`(.*)`", line)
            if m and cur:
                cur["starter"] = m.group(1)
                continue
            m = re.match(r"^\*Description:\*\s*(.*)$", line)
            if m and cur:
                cur["description"] = m.group(1).strip()
                continue
            if line.startswith("````") and cur:
                fence, buf = True, []
                continue
        else:
            if line.startswith("````"):
                fence = False
                cur["slug"] = slug(cur["name"])
                cur["prompt_chars"] = len("\n".join(buf))
                items.append(cur)
                (OUT / "prompts" / f"{cur['slug']}.md").write_text("\n".join(buf).rstrip() + "\n", encoding="utf-8")
                cur = None
                continue
            buf.append(line)
    (OUT / "prompts").mkdir(parents=True, exist_ok=True)
    seen = set()
    for it in items:
        assert it["slug"] not in seen, it["slug"]
        seen.add(it["slug"])
    (OUT / "catalog.json").write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by = {}
    for it in items:
        by[it["program"]] = by.get(it["program"], 0) + 1
    print(len(items), by)


if __name__ == "__main__":
    main(sys.argv[1])
