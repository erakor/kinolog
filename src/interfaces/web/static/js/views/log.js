import { api } from "../api.js";
import { ratingOptions } from "../actions.js";
import { emptyState, h, openModal, searchBox, segmented, toast } from "../util.js";

const PAGE = 100;

export async function mount(el, ctx) {
  const state = { q: "", min: "", offset: 0 };
  const subtitle = h("p", { class: "hero__lede" });
  const tbody = h("tbody");
  const more = h("button", { class: "btn", type: "button", hidden: true, onclick: () => { state.offset += PAGE; load(true); } }, "Show more");
  const tools = h("div", { style: "display:flex;gap:8px;flex-wrap:wrap" });
  const empty = h("div", { hidden: true });
  const holder = h("div", { class: "table-wrap" },
    h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["Date", "Film", "Director", "Runtime", "Rating", ""].map((t) => h("th", { scope: "col" }, t)))), tbody));

  el.append(
    h("section", { class: "hero", style: "margin-bottom:16px" },
      h("div", { style: "display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:end" },
        h("div", {}, h("p", { class: "eyebrow" }, "Chronological diary"), h("h1", {}, "Watching Log"), subtitle), tools)),
    h("div", { class: "toolbar" },
      searchBox("Search watched films or directors…", (v) => { state.q = v; state.offset = 0; load(); }),
      segmented([["", "All Ratings"], ["9", "4.5+ Stars"], ["8", "4.0+ Stars"]], state.min, (v) => { state.min = v; state.offset = 0; load(); })),
    empty, holder, h("div", { style: "text-align:center;margin-top:16px" }, more));

  ctx.logTools = tools; // the import control (added by the import module) mounts here
  const importMod = await import("./import.js").catch(() => null);
  if (importMod) tools.append(importMod.importButton(ctx, () => load()));

  async function load(append = false) {
    const data = await api.get("/api/log", { q: state.q, min_rating: state.min, limit: PAGE, offset: state.offset });
    const s = data.summary;
    subtitle.replaceChildren(h("span", { class: "num" }, s.count), " films logged · ",
      h("span", { class: "num" }, Math.round(s.total_minutes / 60)), " hrs watched");
    if (!append) tbody.replaceChildren();
    const none = !data.entries.length && !append;
    empty.hidden = !none;
    holder.hidden = none;
    if (none) {
      empty.replaceChildren(emptyState(s.count || state.q || state.min ? "No entries match" : "Nothing logged yet",
        "Log a film from your Watch List, use + Add Film, or import a Letterboxd export."));
      more.hidden = true;
      return;
    }
    for (const e of data.entries) tbody.append(row(e));
    more.hidden = state.offset + PAGE >= data.total;
  }

  function row(e) {
    const it = e.item;
    const rating = h("select", { class: "rating-select", "aria-label": `Rating for ${it.title}`,
      onchange: async () => {
        try { await api.patch(`/api/log/${e.entry_id}`, { rating: rating.value ? Number(rating.value) : null }); toast("Rating saved"); }
        catch (err) { toast(err.message, "error"); }
      } }, ratingOptions(e.rating));
    return h("tr", {},
      h("td", { class: "num" }, e.watched_on),
      h("td", {}, it.title, " ", h("span", { class: "num muted" }, it.year ? `(${it.year})` : ""),
        e.rewatch ? h("div", { class: "note" }, "Rewatch") : null),
      h("td", { class: "muted" }, it.directors.map((d) => d.name).join(", ")),
      h("td", { class: "num muted" }, it.runtime_min ? `${it.runtime_min} min` : ""),
      h("td", {}, e.rating ? h("span", { class: "star", "aria-hidden": "true" }, "★ ") : null, rating),
      h("td", { style: "white-space:nowrap" },
        h("button", { class: "btn btn--icon", type: "button", "aria-label": `Edit ${it.title}`, title: "Edit", onclick: () => edit(e) }, "✎"),
        h("button", { class: "btn btn--icon", type: "button", "aria-label": `Delete ${it.title} entry`, title: "Delete entry",
          onclick: async () => {
            if (!confirm(`Delete this log entry for ${it.title}?`)) return;
            try { await api.del(`/api/log/${e.entry_id}`); toast("Entry deleted"); state.offset = 0; load(); }
            catch (err) { toast(err.message, "error"); }
          } }, "🗑")));
  }

  function edit(e) {
    openModal(`Edit ${e.item.title}`, (close) => {
      const date = h("input", { type: "date", value: e.watched_on, required: true });
      const rating = h("select", {}, ratingOptions(e.rating));
      const rewatch = h("input", { type: "checkbox", checked: e.rewatch });
      return h("form", {
        onsubmit: async (ev) => {
          ev.preventDefault();
          try {
            await api.patch(`/api/log/${e.entry_id}`, { watched_on: date.value, rating: rating.value ? Number(rating.value) : null, rewatch: rewatch.checked });
            close(); toast("Entry updated"); state.offset = 0; load();
          } catch (err) { toast(err.message, "error"); }
        } },
      h("div", { class: "field-row" }, h("label", { class: "field" }, "Date watched", date), h("label", { class: "field" }, "Rating", rating)),
      h("label", { class: "field", style: "display:flex;gap:8px;align-items:center" }, rewatch, "Rewatch"),
      h("div", { class: "modal__actions" }, h("button", { class: "btn", type: "button", onclick: close }, "Cancel"),
        h("button", { class: "btn btn--primary", type: "submit" }, "Save")));
    });
  }

  await load();
}
