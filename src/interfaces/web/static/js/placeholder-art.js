// Deterministic inline-SVG art. No posters, no network. Palette comes from the design tokens.
const PALETTE = ["#d9c9b3", "#c9b5a0", "#b8c1b0", "#c7b3b0", "#cdbfa6", "#b9b2a4"];
const INK = "#14130f";

function hash(n) { let x = (Number(n) * 2654435761) >>> 0; x ^= x >>> 15; return x >>> 0; }
const NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, text) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

export function initials(title) {
  const words = String(title).replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "?").slice(0, 2)).toUpperCase();
}

export function posterArt(item, { width = 40, height = 56 } = {}) {
  const hs = hash(item.item_id ?? item.id ?? 0);
  const root = svg("svg", { viewBox: "0 0 40 56", width, height, class: "poster-art", role: "img", "aria-label": `${item.title} placeholder` });
  root.append(svg("rect", { width: 40, height: 56, fill: PALETTE[hs % PALETTE.length] }));
  root.append(svg("circle", { cx: 8 + (hs >> 3) % 24, cy: 10 + (hs >> 7) % 14, r: 10 + (hs >> 11) % 8, fill: "#fff", opacity: ".25" }));
  root.append(svg("text", { x: 20, y: 34, "text-anchor": "middle", "font-size": 16, "font-family": "Georgia, serif", "font-weight": 700, fill: INK }, initials(item.title)));
  if (item.year) root.append(svg("text", { x: 20, y: 48, "text-anchor": "middle", "font-size": 7, "font-family": "monospace", fill: INK }, String(item.year)));
  return root;
}

// Wide decorative banner for page heroes (reel-and-grain motif, seeded by a string).
export function bannerArt(seed) {
  const hs = hash([...String(seed)].reduce((a, c) => a + c.charCodeAt(0), 7));
  const root = svg("svg", { viewBox: "0 0 360 190", preserveAspectRatio: "xMidYMid slice", "aria-hidden": "true" });
  root.append(svg("rect", { width: 360, height: 190, fill: PALETTE[hs % PALETTE.length] }));
  for (let i = 0; i < 5; i++) {
    const s = hash(hs + i * 97);
    root.append(svg("circle", { cx: 40 + (s % 280), cy: 30 + ((s >> 8) % 130), r: 18 + (s % 42), fill: i % 2 ? "#fff" : INK, opacity: i % 2 ? ".22" : ".08" }));
  }
  for (let i = 0; i < 9; i++) root.append(svg("rect", { x: 8 + i * 40, y: 6, width: 14, height: 9, rx: 2, fill: INK, opacity: ".35" }));
  for (let i = 0; i < 9; i++) root.append(svg("rect", { x: 8 + i * 40, y: 175, width: 14, height: 9, rx: 2, fill: INK, opacity: ".35" }));
  return root;
}
