// "Download proposal (PDF)": a PDF file of the proposal only, nothing else on the page.
// The proposal is copied into a hidden frame exactly one A4 page wide (794 px), so it takes its full desktop layout
// even on a phone; each designed page is captured as an image (html-to-image, the browser's own rendering, so the
// gradients and fonts match the screen) and placed full-bleed on an A4 page (jsPDF). Libraries load only on click.
const A4_PX = { w: 794, h: 1123 };

const safeName = (s) => (s || "").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
export const proposalFileName = (p) => `${["Proposal", safeName(p.client), safeName(p.framework)].filter(Boolean).join(" - ")}.pdf`;

function frameWith(el) {
  const f = document.createElement("iframe");
  f.setAttribute("aria-hidden", "true");
  f.style.cssText = `position:fixed;left:-20000px;top:0;width:${A4_PX.w}px;height:${A4_PX.h}px;border:0;opacity:0;pointer-events:none`;
  document.body.appendChild(f);
  const d = f.contentDocument;
  d.open();
  // styles only: copying the app's scripts would start a second copy of the app in the frame
  const styles = [...document.head.querySelectorAll("style, link[rel='stylesheet']")].map((n) => n.outerHTML).join("");
  d.write(`<!doctype html><html><head><meta charset="utf-8"><base href="${window.location.origin}/">${styles}</head>`
    + `<body class="pd-capture">${el.outerHTML}</body></html>`);
  d.close();
  return f;
}

async function ready(d) {
  const links = [...d.querySelectorAll("link[rel='stylesheet']")];
  await Promise.all(links.map((l) => (l.sheet ? null : new Promise((r) => { l.onload = r; l.onerror = r; setTimeout(r, 4000); }))));
  await (d.fonts?.ready || Promise.resolve());
  await new Promise((r) => setTimeout(r, 150));
}

export async function downloadProposalPdf(el, p) {
  const [{ toJpeg }, { jsPDF }] = await Promise.all([import("html-to-image"), import("jspdf")]);
  const f = frameWith(el);
  try {
    await ready(f.contentDocument);
    const pages = [...f.contentDocument.querySelectorAll(".pd-page")];
    const pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait", compress: true });
    for (let i = 0; i < pages.length; i += 1) {
      const light = pages[i].classList.contains("pd-light");
      const opts = { quality: 0.9, pixelRatio: 2, width: A4_PX.w, height: A4_PX.h, backgroundColor: light ? "#ffffff" : "#07080d" };
      let img;
      try {
        img = await toJpeg(pages[i], opts);
      } catch {
        img = await toJpeg(pages[i], { ...opts, skipFonts: true });   // a font that can't be read: system font
      }
      if (i) pdf.addPage();
      pdf.addImage(img, "JPEG", 0, 0, 210, 297, undefined, "FAST");
    }
    pdf.setProperties({ title: `${p.framework || "Proposal"}: ${p.client || ""}`, author: (p.prepared_by || "").split(",")[0] });
    pdf.save(proposalFileName(p));
  } finally {
    f.remove();
  }
}

// Proposals made before the designed layout (plain text): the text alone, on A4.
export async function downloadTextPdf(markdown, p) {
  const { jsPDF } = await import("jspdf");
  const pdf = new jsPDF({ unit: "mm", format: "a4" });
  const plain = (markdown || "").replace(/^#+\s*/gm, "").replace(/\*\*(.*?)\*\*/g, "$1").replace(/\*(.*?)\*/g, "$1")
    .replace(/₹/g, "Rs ");    // the standard PDF fonts have no rupee sign
  const lines = pdf.splitTextToSize(plain, 180);
  let y = 18;
  pdf.setFontSize(11);
  for (const line of lines) {
    if (y > 282) { pdf.addPage(); y = 18; }
    pdf.text(line, 15, y);
    y += 6;
  }
  pdf.save(proposalFileName(p));
}
