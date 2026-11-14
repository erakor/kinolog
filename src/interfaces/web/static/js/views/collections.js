import { api } from "../api.js";
import { logButton, queueButton } from "../actions.js";
import { bannerArt } from "../placeholder-art.js";
import { emptyState, fmtPct, h, progressBar, ratingLabel, searchBox, segmented } from "../util.js";

export async function mount(el) {
  const state = { status: "all", q: "" };
  const stats = h("div", { class: "num muted", style: "display:flex;gap:24px;flex-wrap:wrap;margin-top:24px" });
  const grid = h("div", { class: "grid grid--2" });

  el.append(
    h("section", { class: "hero hero--split" },
      h("div", {},
        h("p", { class: "eyebrow" }, "Filmography completion"),
        h("h1", {}, "Director Collections"),
        h("p", { class: "hero__lede" }, "Track every feature in a director's body of work. See how close you are to completing each filmography and queue or log the missing titles."),
        stats),
      h("div", { class: "hero__art" }, bannerArt("collections"))),
    h("div", { class: "toolbar" },
      segmented([["all", "All Collections"], ["in_progress", "In Progress"], ["completed", "Completed"]], state.status,
        (v) => { state.status = v; load(); }),
      searchBox("Filter by director or title…", (v) => { state.q = v; load(); })),
    grid);

  async function load() {
    const data = await api.get("/api/collections/directors", { status: state.status, q: state.q, include_films: true, limit: 60 });
    const s = data.summary;
    stats.replaceChildren(
      h("span", {}, h("strong", {}, s.above_50), " directors above 50%"),
      h("span", {}, h("strong", {}, s.completed), " completed filmographies"),
      h("span", {}, h("strong", {}, s.tracked), " tracked total"));
    grid.replaceChildren();
    if (!data.items.length) {
      grid.append(emptyState(
        s.tracked ? "No directors match" : "No collections yet",
        s.tracked ? "Try another filter." : "Run `ingest enrich` to load crew credits, then reload."));
      return;
    }
    for (const d of data.items) grid.append(directorCard(d, load));
  }
  await load();
}

function directorCard(d, reload) {
  const queued = d.films.filter((f) => !f.seen && f.on_watchlist).length;
  return h("article", { class: "card dir-card" },
    h("div", { class: "dir-card__head" }, h("h3", {}, d.name), h("span", { class: "pct num" }, fmtPct(d.pct))),
    h("p", { class: "dir-card__meta" }, `${d.seen} / ${d.total} watched`, queued ? ` · ${queued} queued` : ""),
    progressBar(d.seen, d.total, d.seen + queued),
    h("ul", { class: "film-list" }, d.films.map((f) => filmRow(f,
      (film) => film.seen ? [] : [film.on_watchlist ? null : queueButton(film, reload), logButton(film, reload, true)]))),
    h("div", { class: "card__foot" },
      h("a", { class: "link", href: `#/concierge?q=${encodeURIComponent(`What should I watch next from ${d.name}?`)}` },
        `Ask Concierge for next ${d.name} pick →`)));
}

export function filmRow(f, actions = null) {
  const meta = [f.year, f.runtime_min ? `${f.runtime_min} min` : "runtime unknown",
    f.seen && f.rating ? `${ratingLabel(f.rating)}★` : null,
    !f.seen && f.on_watchlist ? "In Watch List" : null].filter(Boolean).join(" · ");
  return h("li", { class: "film-row" },
    h("span", { class: `check${f.seen ? " check--seen" : f.on_watchlist ? " check--queued" : ""}`, role: "img",
      "aria-label": f.seen ? "Watched" : f.on_watchlist ? "In Watch List" : "Not watched" }, f.seen ? "✓" : ""),
    h("div", { class: "film-row__body" },
      h("div", { class: `film-row__title${f.seen ? "" : " muted"}` }, f.title),
      h("div", { class: "film-row__meta" }, meta)),
    actions ? h("div", { class: "film-row__actions" }, actions(f)) : null);
}
