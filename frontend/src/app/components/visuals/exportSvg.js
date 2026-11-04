// Export a rendered visual: the SVG as a file, or a PNG drawn on a canvas at 2x the SVG's own size.
// Exported files use Manrope when it's installed on the device and a plain sans-serif otherwise.

export function fileName(title, ext) {
  const slug = String(title || "visual").normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "-").slice(0, 60) || "visual";
  return `${slug}.${ext}`;
}

function serialise(svg) {
  const vb = svg.viewBox?.baseVal;
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (vb) {
    clone.setAttribute("width", String(vb.width));
    clone.setAttribute("height", String(vb.height));
  }
  clone.removeAttribute("style");
  return { text: `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(clone)}`, w: vb?.width || 1200, h: vb?.height || 800 };
}

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function downloadSvg(svg, name) {
  if (!svg) return;
  save(new Blob([serialise(svg).text], { type: "image/svg+xml;charset=utf-8" }), name);
}

export async function downloadPng(svg, name, scale = 2) {
  if (!svg) return;
  const { text, w, h } = serialise(svg);
  const img = new Image();
  img.decoding = "async";
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
  await (img.decode ? img.decode() : new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; }));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext("2d");
  ctx.scale(scale, scale);
  ctx.drawImage(img, 0, 0, w, h);
  const blob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
  if (blob) save(blob, name);
}
