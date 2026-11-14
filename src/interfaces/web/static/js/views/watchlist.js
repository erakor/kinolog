import { api } from "../api.js";
import { bannerArt } from "../placeholder-art.js";
import { emptyState, fmtPct, h, searchBox, segmented, toast } from "../util.js";

export async function mount(el, ctx) {
  const state = { q: "", runtime: "", sort: "impact" };
  const showing = h("span", { class: "num muted" });
  const list = h("div", { class: "list" });
  const sortSel = h("select", { class: "select", "aria-label": "Sort", onchange: () => { state.sort = sortSel.value; load(); } });
  const pickBtn = h("button", { class: "btn", type: "button", onclick: pickShort }, "Pick 90m Film");

  el.append(
    h("section", { class: "hero hero--split" },
      h("div", {},
        h("p", { class: "eyebrow" }, "Queued screenings"),
        h("h1", {}, "Watch List"),
        h("p", { class: "hero__lede" }, "Filter by available runtime or prioritize films that push a director filmography toward completion."),
        h("div", { class: "toolbar", style: "margin-bottom:0" },
          searchBox("Filter by title or director…", (v) => { state.q = v; load(); }),
          pickBtn)),
      h("div", { class: "hero__art" }, bannerArt("watchlist"))),
    h("div", { class: "toolbar" },
      segmented([["", "All Runtimes"], ["90", "≤ 90 min"], ["105", "≤ 105 min"], ["120", "≤ 120 min"]], state.runtime,
        (v) => { state.runtime = v; load(); }),
      h("div", { style: "display:flex;gap:12px;align-items:center" }, showing, sortSel)),
    list);

  function fillSorts(tasteOk) {
    const opts = [["impact", "Sort: Director Impact"], ["added", "Sort: Recently Added"], ["runtime", "Sort: Shortest"],
      ["year", "Sort: Newest Film"], ["title", "Sort: Title"]];
    if (tasteOk) opts.push(["taste", "Sort: Taste Match"]);
    sortSel.replaceChildren(...opts.map(([v, l]) => h("option", { value: v, selected: v === state.sort }, l)));
  }

  let lastItems = [];
  async function load() {
    let data;
    try {
      data = await api.get("/api/watchlist", { sort: state.sort, runtime_max: state.runtime, q: state.q });
    } catch (e) {
      if (e.code === "taste_unavailable") { toast("Taste ranking is unavailable.", "error"); state.sort = "impact"; return load(); }
      throw e;
    }
    fillSorts(data.taste_available);
    lastItems = data.items;
    showing.textContent = `Showing ${data.total} of ${data.summary.count}`;
    list.replaceChildren();
    if (!data.items.length) {
      list.replaceWith(list = h("div", { class: "list" }));
      list.append(emptyState(data.summary.count ? "Nothing fits those filters" : "Your Watch List is empty",
        data.summary.count ? "Try a longer runtime or clear the search." : "Add films with “+ Add Film” or import a Letterboxd export."));
      return;
    }
    for (const row of data.items) list.append(listRow(row, ctx, load));
  }

  function pickShort() {
    const shorts = lastItems.filter((r) => r.runtime_min && r.runtime_min <= 90);
    if (!shorts.length) { toast("No film of 90 minutes or less in your Watch List."); return; }
    const pick = shorts[0];
    const node = list.querySelector(`[data-item="${pick.item_id}"]`);
    if (node) { node.scrollIntoView({ block: "center", behavior: "smooth" }); node.style.background = "var(--color-accent-wash)"; }
    toast(`Try ${pick.title} (${pick.runtime_min} min).`);
  }

  await load();
}

export function pushText(row) {
  const d = row.completion && row.completion[0];
  return d ? `Pushes ${d.name} ${fmtPct(d.before_pct)} → ${fmtPct(d.after_pct)}` : null;
}

export function listRow(row, ctx, reload, actions = null) {
  const dirs = row.directors.map((d) => d.name).join(", ");
  const push = pushText(row);
  const sub = [dirs, row.genres && row.genres.join(" / ")].filter(Boolean).join(" · ");
  return h("div", { class: "list-row", dataset: { item: row.item_id } },
    h("div", { class: "list-row__main" },
      h("div", { class: "list-row__title" }, row.title,
        h("span", { class: "num" }, row.year ?? ""), row.runtime_min ? h("span", { class: "num" }, `${row.runtime_min} min`) : null),
      h("div", { class: "list-row__sub" }, sub, sub && push ? " · " : "", push ? h("span", { class: "push" }, push) : null),
      row.overview ? h("p", { class: "list-row__plot" }, row.overview) : null),
    actions ? h("div", { class: "list-row__actions" }, actions(row)) : null);
}
