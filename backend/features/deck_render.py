"""Presentation Builder engine, part 2: draw the boxes from features/deck_layout.py as PowerPoint and as PDF.

PowerPoint (python-pptx): 16:9 (13.33 x 7.5 in), one editable text box per text item with the fitted size, exact line
spacing and native bullets; panels, rules, circles and arrow heads are native shapes; tables are native tables. Text
is set in "Manrope" (bold for the Bold and ExtraBold roles). On a computer without Manrope, PowerPoint swaps in a
similar font and its own line breaks may move slightly; the screen says so.

PDF (reportlab): one slide per page (960 x 540 pt), the Manrope files embedded, every line drawn where the layout put it.
"""
from __future__ import annotations

import io
import math

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Emu, Pt
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as rl_canvas

from .deck_layout import FONTS, PPTX_BOLD, H, W

PPTX_FONT = "Manrope"
EMU_PER_PT = 12700
NO_STYLE_TABLE = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"      # "No Style, No Grid"
ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}


def _e(v: float) -> Emu:
    return Emu(int(round(v * EMU_PER_PT)))


def _rgb(hex_: str) -> RGBColor:
    return RGBColor.from_string(hex_.lstrip("#").upper())


def _hex(hex_: str) -> str:
    return hex_.lstrip("#").upper()


# ------------------------------------------------------------------ PowerPoint ----
def _no_style(shape) -> None:
    """Drop the theme style python-pptx adds to shapes (it brings a shadow and white centred text)."""
    st = shape._element.find(qn("p:style"))
    if st is not None:
        shape._element.remove(st)


def _paint(shape, fill, stroke, sw) -> None:
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(fill)
    else:
        shape.fill.background()
    if stroke and sw:
        shape.line.color.rgb = _rgb(stroke)
        shape.line.width = Pt(sw)
    else:
        shape.line.fill.background()


def _pptx_bg(slide, bg: dict) -> None:
    g = bg.get("grad")
    if g:
        diag = math.hypot(W, H)
        stops = list(g["stops"]) + [[1.0, g["stops"][-1][1]]]
        gs = "".join(f'<a:gs pos="{min(100000, int(p * g["rx"] / diag * 100000))}"><a:srgbClr val="{_hex(c)}"/></a:gs>'
                     for p, c in stops)
        left, top = int(g["cx"] / W * 100000), int(g["cy"] / H * 100000)
        fill = (f'<a:gradFill rotWithShape="1"><a:gsLst>{gs}</a:gsLst><a:path path="circle">'
                f'<a:fillToRect l="{left}" t="{top}" r="{100000 - left}" b="{100000 - top}"/></a:path></a:gradFill>')
    else:
        fill = f'<a:solidFill><a:srgbClr val="{_hex(bg["color"])}"/></a:solidFill>'
    c_sld = slide._element.find(qn("p:cSld"))
    old = c_sld.find(qn("p:bg"))
    if old is not None:
        c_sld.remove(old)
    c_sld.insert(0, parse_xml(f'<p:bg {nsdecls("p", "a")}><p:bgPr>{fill}<a:effectLst/></p:bgPr></p:bg>'))


def _pptx_rect(slide, it: dict) -> None:
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if it["r"] else MSO_SHAPE.RECTANGLE
    sp = slide.shapes.add_shape(kind, _e(it["x"]), _e(it["y"]), _e(it["w"]), _e(it["h"]))
    _no_style(sp)
    if it["r"]:
        sp.adjustments[0] = min(0.5, it["r"] / max(1.0, min(it["w"], it["h"])))
    _paint(sp, it["fill"], it["stroke"], it["sw"])


def _pptx_oval(slide, it: dict) -> None:
    sp = slide.shapes.add_shape(MSO_SHAPE.OVAL, _e(it["x"]), _e(it["y"]), _e(it["w"]), _e(it["h"]))
    _no_style(sp)
    _paint(sp, it["fill"], it["stroke"], it["sw"])


def _pptx_line(slide, it: dict) -> None:
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, _e(it["x1"]), _e(it["y1"]), _e(it["x2"]), _e(it["y2"]))
    _no_style(ln)
    ln.line.color.rgb = _rgb(it["stroke"])
    ln.line.width = Pt(it["sw"])


def _pptx_tri(slide, it: dict) -> None:
    x, y, w, h = it["x"], it["y"], it["w"], it["h"]
    if it["dir"] == "right":                         # an up-pointing triangle turned 90°: swap the box around its centre
        cx, cy = x + w / 2, y + h / 2
        x, y, w, h = cx - h / 2, cy - w / 2, h, w
    sp = slide.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, _e(x), _e(y), _e(w), _e(h))
    _no_style(sp)
    _paint(sp, it["fill"], None, 0)
    if it["dir"] == "right":
        sp.rotation = 90.0


def _bullet_xml(p, it: dict) -> None:
    ppr = p._p.get_or_add_pPr()
    ind = int(_e(it["indent"]))
    ppr.set("marL", str(ind))
    ppr.set("indent", str(-ind))
    b = it["bullet"]
    pct = max(25000, min(400000, int(b["size"] / 0.6 / it["size"] * 100000)))   # ■ is about 0.6 em in Arial
    for xml in (f'<a:buClr {nsdecls("a")}><a:srgbClr val="{_hex(b["color"])}"/></a:buClr>',
                f'<a:buSzPct {nsdecls("a")} val="{pct}"/>', f'<a:buFont {nsdecls("a")} typeface="Arial"/>',
                f'<a:buChar {nsdecls("a")} char="■"/>'):
        ppr.append(parse_xml(xml))


def _fill_frame(tf, it: dict) -> None:
    for i, para in enumerate(it["paras"]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = ALIGN[it["align"]]
        p.line_spacing = Pt(it["lh"])
        if i and it["gap"]:
            p.space_before = Pt(it["gap"])
        if it.get("bullet"):
            _bullet_xml(p, it)
        for text, color in para["runs"]:
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = PPTX_FONT
            f.size = Pt(it["size"])
            f.bold = PPTX_BOLD[it["font"]]
            rpr = r._r.get_or_add_rPr()
            if it["cs"]:
                rpr.set("spc", str(int(round(it["cs"] * 100))))
            if it.get("outline"):
                o = it["outline"]
                rpr.insert(0, parse_xml(f'<a:noFill {nsdecls("a")}/>'))
                rpr.insert(0, parse_xml(f'<a:ln {nsdecls("a")} w="{int(_e(o["w"]))}"><a:solidFill>'
                                        f'<a:srgbClr val="{_hex(o["color"])}"/></a:solidFill></a:ln>'))
            else:
                f.color.rgb = _rgb(color)


def _pptx_text(slide, it: dict) -> None:
    tb = slide.shapes.add_textbox(_e(it["x"]), _e(it["y"]), _e(it["w"]), _e(it["h"]))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE if it.get("valign") == "middle" else MSO_ANCHOR.TOP
    _fill_frame(tf, it)
    if it.get("rot"):
        tb.rotation = float((360 + it["rot"]) % 360)


def _cell_borders(cell, bottom: str, sw: float) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for child in list(tc_pr):
        tc_pr.remove(child)
    for side in ("lnL", "lnR", "lnT"):
        tc_pr.append(parse_xml(f'<a:{side} {nsdecls("a")} w="0"><a:noFill/></a:{side}>'))
    tc_pr.append(parse_xml(f'<a:lnB {nsdecls("a")} w="{int(_e(sw))}"><a:solidFill><a:srgbClr val="{_hex(bottom)}"/>'
                           f'</a:solidFill></a:lnB>'))
    tc_pr.append(parse_xml(f'<a:noFill {nsdecls("a")}/>'))


def _pptx_table(slide, it: dict) -> None:
    nrows, ncols = len(it["rows"]), len(it["cols"])
    gf = slide.shapes.add_table(nrows, ncols, _e(it["x"]), _e(it["y"]), _e(it["w"]), _e(sum(it["rows"])))
    tbl = gf.table
    tbl_pr = tbl._tbl.tblPr
    tbl_pr.set("firstRow", "0")
    tbl_pr.set("bandRow", "0")
    sid = tbl_pr.find(qn("a:tableStyleId"))
    if sid is None:
        sid = parse_xml(f'<a:tableStyleId {nsdecls("a")}/>')
        tbl_pr.append(sid)
    sid.text = NO_STYLE_TABLE
    for c, w in enumerate(it["cols"]):
        tbl.columns[c].width = _e(w)
    for r, h in enumerate(it["rows"]):
        tbl.rows[r].height = _e(h)
    for idx, cit in enumerate(it["cells"]):
        r, c = divmod(idx, ncols)
        cell = tbl.cell(r, c)
        cell.margin_left = cell.margin_right = _e(it["px"])
        cell.margin_top = cell.margin_bottom = _e(it["py"])
        cell.vertical_anchor = MSO_ANCHOR.TOP
        tf = cell.text_frame
        tf.word_wrap = True
        _fill_frame(tf, cit)
        _cell_borders(cell, it["head_rule"] if r == 0 else it["row_rule"], 1.25 if r == 0 else 0.75)


PPTX_DRAW = {"rect": _pptx_rect, "oval": _pptx_oval, "line": _pptx_line, "tri": _pptx_tri, "text": _pptx_text,
             "table": _pptx_table}


def render_pptx(slides: list, *, title: str, author: str, notes: list) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = _e(W), _e(H)
    blank = prs.slide_layouts[6]
    for sl, note in zip(slides, notes):
        slide = prs.slides.add_slide(blank)
        _pptx_bg(slide, sl["bg"])
        for it in sl["items"]:
            PPTX_DRAW[it["t"]](slide, it)
        if note:
            slide.notes_slide.notes_text_frame.text = note
    cp = prs.core_properties
    cp.title, cp.author, cp.last_modified_by = title[:200], author[:100], author[:100]
    cp.subject = cp.keywords = cp.comments = cp.category = ""
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ PDF ----
def _pdf_bg(c, bg: dict) -> None:
    c.setFillColor(HexColor(bg["color"]))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    g = bg.get("grad")
    if not g:
        return
    stops = list(g["stops"]) + [[1.0, g["stops"][-1][1]]]
    c.saveState()
    p = c.beginPath()
    p.rect(0, 0, W, H)
    c.clipPath(p, stroke=0, fill=0)
    c.translate(g["cx"], H - g["cy"])
    c.scale(1, g["ry"] / g["rx"])
    c.radialGradient(0, 0, g["rx"], [HexColor(col) for _, col in stops], [float(pos) for pos, _ in stops], extend=True)
    c.restoreState()


def _pdf_rect(c, it: dict) -> None:
    fill, stroke = it["fill"], it["stroke"] if it["sw"] else None
    if fill:
        c.setFillColor(HexColor(fill))
    if stroke:
        c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(it["sw"])
    y = H - it["y"] - it["h"]
    if it["r"]:
        c.roundRect(it["x"], y, it["w"], it["h"], min(it["r"], it["w"] / 2, it["h"] / 2), stroke=int(bool(stroke)),
                    fill=int(bool(fill)))
    else:
        c.rect(it["x"], y, it["w"], it["h"], stroke=int(bool(stroke)), fill=int(bool(fill)))


def _pdf_oval(c, it: dict) -> None:
    fill, stroke = it["fill"], it["stroke"] if it["sw"] else None
    if fill:
        c.setFillColor(HexColor(fill))
    if stroke:
        c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(it["sw"])
    c.ellipse(it["x"], H - it["y"] - it["h"], it["x"] + it["w"], H - it["y"], stroke=int(bool(stroke)), fill=int(bool(fill)))


def _pdf_line(c, it: dict) -> None:
    c.setStrokeColor(HexColor(it["stroke"]))
    c.setLineWidth(it["sw"])
    c.line(it["x1"], H - it["y1"], it["x2"], H - it["y2"])


def _pdf_tri(c, it: dict) -> None:
    x, y, w, h = it["x"], it["y"], it["w"], it["h"]
    pts = [(x, y + h), (x + w, y + h), (x + w / 2, y)] if it["dir"] == "up" else [(x, y), (x, y + h), (x + w, y + h / 2)]
    p = c.beginPath()
    p.moveTo(pts[0][0], H - pts[0][1])
    for px, py in pts[1:]:
        p.lineTo(px, H - py)
    p.close()
    c.setFillColor(HexColor(it["fill"]))
    c.drawPath(p, stroke=0, fill=1)


def _pdf_text(c, it: dict) -> None:
    c.saveState()
    if it.get("rot"):
        cx, cy = it["x"] + it["w"] / 2, it["y"] + it["h"] / 2
        c.translate(cx, H - cy)
        c.rotate(-it["rot"])                          # layout rot -90 = a quarter turn anticlockwise
        ox, oy = -it["w"] / 2, -it["h"] / 2

        def at(lx, ly):
            return ox + lx, -(oy + ly)
    else:
        def at(lx, ly):
            return it["x"] + lx, H - (it["y"] + ly)
    font, size, cs = FONTS[it["font"]], it["size"], it["cs"]
    outline = it.get("outline")
    avail = it["w"] - it["indent"]
    for para in it["paras"]:
        if it.get("bullet") and para.get("mark"):
            b = it["bullet"]
            mx, my = at(para["mark"][0], para["mark"][1] + b["size"])
            c.setFillColor(HexColor(b["color"]))
            c.rect(mx, my, b["size"], b["size"], stroke=0, fill=1)
        for li, (segs, lw) in enumerate(zip(para["lines"], para["widths"])):
            if it["align"] == "c":
                lx = it["indent"] + (avail - lw) / 2
            elif it["align"] == "r":
                lx = it["w"] - lw
            else:
                lx = it["indent"]
            px, py = at(lx, para["dy"] + li * it["lh"] + it["base"])
            t = c.beginText(px, py)
            t.setFont(font, size)
            t.setCharSpace(cs)
            if outline:
                t.setTextRenderMode(1)
                c.setStrokeColor(HexColor(outline["color"]))
                c.setLineWidth(outline["w"])
            for text, color in segs:
                t.setFillColor(HexColor(color))
                t.textOut(text)
            c.drawText(t)
    c.restoreState()


def _pdf_table(c, it: dict) -> None:
    for r in it["rules"]:
        _pdf_line(c, r)
    for cell in it["cells"]:
        _pdf_text(c, cell)


PDF_DRAW = {"rect": _pdf_rect, "oval": _pdf_oval, "line": _pdf_line, "tri": _pdf_tri, "text": _pdf_text,
            "table": _pdf_table}


def render_pdf(slides: list, *, title: str, author: str) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H), pageCompression=1)
    c.setTitle(title[:200])
    c.setAuthor(author[:100])
    c.setCreator("Consultation Hub")
    c.setSubject("")
    if hasattr(c, "setProducer"):
        c.setProducer("Consultation Hub")
    for sl in slides:
        _pdf_bg(c, sl["bg"])
        for it in sl["items"]:
            PDF_DRAW[it["t"]](c, it)
        c.showPage()
    c.save()
    return buf.getvalue()
