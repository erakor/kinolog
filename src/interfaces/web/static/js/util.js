// DOM helpers. Text is always set via textContent/createTextNode, never innerHTML.
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) { el.replaceChildren(); return el; }

export function toast(message, kind = "info") {
  const root = document.getElementById("toasts");
  const t = h("div", { class: `toast${kind === "error" ? " toast--error" : ""}`, role: "status" }, message);
  root.append(t);
  setTimeout(() => t.remove(), 4000);
}

export function openModal(title, bodyBuilder) {
  const root = document.getElementById("modal-root");
  const prev = document.activeElement;
  const close = () => { clear(root); prev && prev.focus && prev.focus(); };
  const titleEl = h("h2", { id: "modal-title" }, title);
  const modal = h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "modal-title" },
    h("div", { class: "modal__head" }, titleEl, h("button", { class: "btn btn--icon", type: "button", "aria-label": "Close", onclick: close }, "✕")),
    bodyBuilder(close));
  const backdrop = h("div", { class: "modal-backdrop", onclick: (e) => { if (e.target === backdrop) close(); } }, modal);
  backdrop.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  clear(root).append(backdrop);
  const first = modal.querySelector("input, select, button:not(.btn--icon)");
  (first || modal).focus();
  return close;
}

export function ratingLabel(r) { return r == null ? "" : (r / 2).toFixed(1); }
export function fmtMin(m) { return m == null ? "" : `${m} min`; }
export function fmtPct(p) { return `${Math.round(p)}%`; }
export function today() { return new Date().toISOString().slice(0, 10); }
export function debounce(fn, ms = 200) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

export function searchBox(placeholder, onInput, value = "") {
  const input = h("input", { type: "search", placeholder, "aria-label": placeholder, value });
  input.addEventListener("input", debounce(() => onInput(input.value.trim()), 200));
  return h("label", { class: "search" }, h("span", { "aria-hidden": "true" }, "⌕"), input);
}

export function segmented(options, current, onChange) {
  const wrap = h("div", { class: "segmented", role: "group" });
  const render = (cur) => {
    clear(wrap);
    for (const [value, label] of options) {
      wrap.append(h("button", { type: "button", "aria-pressed": String(value === cur), onclick: () => { onChange(value); render(value); } }, label));
    }
  };
  render(current);
  return wrap;
}

export function progressBar(seen, total, afterSeen = null) {
  const pct = (n) => (total ? Math.min(100, (n / total) * 100) : 0);
  const bar = h("div", { class: "progress", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(total), "aria-valuenow": String(seen) });
  if (afterSeen != null) bar.append(h("div", { class: "progress__after", style: `width:${pct(afterSeen)}%` }));
  bar.append(h("div", { class: "progress__seen", style: `width:${pct(seen)}%` }));
  return bar;
}

export function emptyState(title, text) {
  return h("div", { class: "empty" }, h("h3", {}, title), h("p", {}, text));
}
