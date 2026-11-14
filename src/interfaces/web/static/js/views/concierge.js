import { api } from "../api.js";
import { openLogDialog, queueButton } from "../actions.js";
import { bannerArt } from "../placeholder-art.js";
import { emptyState, fmtPct, h, progressBar, segmented, toast } from "../util.js";

const CITE = /\[\^(\d+)\]/g;

function queryFromHash() {
  return new URLSearchParams((location.hash.split("?")[1]) || "").get("q") || "";
}

export async function mount(el, ctx) {
  const state = { scope: "unseen" };
  const input = h("input", { type: "text", placeholder: "I have 90 minutes. Give me a movie.", "aria-label": "Ask the concierge", maxlength: "500" });
  const submit = h("button", { class: "btn btn--accent", type: "submit" }, "Find a Film →");
  const queueNote = h("span", { class: "num muted", style: "font-size:.8rem" });
  const chips = h("div", { class: "chips" });
  const results = h("section", { "aria-live": "polite" });
  const heroArt = h("div", { class: "hero__art", style: "position:relative;min-height:260px" }, bannerArt("concierge"));
  const caption = h("div", { style: "position:absolute;left:0;right:0;bottom:0;padding:16px;background:linear-gradient(transparent,rgba(20,19,15,.78));color:#fff" });
  heroArt.append(caption);
  const statsBox = h("div", { class: "stats" });
  const radarBox = h("div", {});

  const form = h("form", { class: "concierge-form", onsubmit: (e) => { e.preventDefault(); ask(input.value.trim()); } },
    h("span", { "aria-hidden": "true", class: "muted" }, "⌕"), input, submit);

  el.append(
    h("section", { class: "hero hero--split" },
      h("div", {},
        h("p", { class: "eyebrow" }, "Personal cinema concierge"),
        h("h1", {}, "Tell me your window, mood, or the collection you want to finish."),
        h("p", { class: "hero__lede" }, "Kinolog weighs your watch list runtimes, past ratings, and director completion milestones to recommend the exact film for tonight."),
        h("div", { style: "margin-top:20px" }, form),
        h("div", { class: "toolbar", style: "margin:12px 0" },
          segmented([["unseen", "Watch List + Blind Spots"], ["watchlist", "Watch List Only"]], state.scope, (v) => { state.scope = v; }), queueNote),
        h("div", {}, h("p", { class: "muted", style: "font-size:.875rem;margin-bottom:8px" }, "Try asking"), chips)),
      heroArt),
    results, statsBox, radarBox);

  async function ask(q) {
    if (!q) { input.focus(); return; }
    input.value = q;
    history.replaceState(null, "", `#/concierge?q=${encodeURIComponent(q)}`);
    submit.disabled = true;
    results.replaceChildren(h("p", { class: "loading" }, "Searching your index…"));
    try {
      const data = await api.post("/api/concierge", { query: q, scope: state.scope, limit: 5 });
      renderResults(data);
    } catch (e) {
      results.replaceChildren(emptyState("Could not get a recommendation", e.message));
    } finally {
      submit.disabled = false;
      if (ctx.refreshHealth) ctx.refreshHealth();
    }
  }

  function renderResults(data) {
    results.replaceChildren();
    const curated = h("p", { class: "muted", style: "font-size:.875rem;margin:8px 0" }, "Curated for “", data.query, "”");
    const chipRow = h("div", { class: "chips", style: "margin-bottom:12px" },
      data.parsed.chips.map((c) => h("span", { class: "chip" }, c.label)));
    results.append(curated, chipRow);
    const notes = data.degraded.filter((d) => !d.startsWith("no_llm"));
    if (data.excluded_unknown_runtime) {
      notes.push(`${data.excluded_unknown_runtime} film(s) with unknown runtime were skipped`);
    }
    if (notes.length) results.append(h("p", { class: "muted", style: "font-size:.8rem;margin-bottom:12px" }, notes.map((n) => n.split(":")[0].replace(/_/g, " ") + (n.includes(":") ? ":" + n.split(":").slice(1).join(":") : "")).join(" · ")));
    if (!data.picks.length) {
      const relax = (data.empty && data.empty.relax) || [];
      results.append(emptyState("Nothing fits all of that", relax.length
        ? `Relaxing the ${relax.map((r) => `${r.filter} constraint (${r.would_match}+ matches)`).join(" or ")} would bring results back.`
        : "Try different words, a longer window, or import more of your library."));
      return;
    }
    data.picks.forEach((p, i) => {
      const card = pickCard(p, i === 0);
      if (i === 0) results.append(card);
      else {
        let grid = results.querySelector(".pick-grid");
        if (!grid) { grid = h("div", { class: "grid grid--2 pick-grid" }); results.append(grid); }
        grid.append(card);
      }
    });
    const tag = data.picks[0].rationale.generator;
    results.append(h("p", { class: "muted", style: "font-size:.75rem;margin-top:8px" }, `Rationales: ${tag === "llm" ? "written by the model, checked against the cited text" : "template built from your index"}.`));
  }

  function pickCard(p, primary) {
    const it = p.item;
    const onList = it.status.on_watchlist;
    const reload = () => ask(input.value.trim());
    return h("article", { class: "card pick" },
      h("div", { class: "pick__tags" },
        h("span", { class: "primary" }, primary ? "Primary Pick" : "Alternative Angle"),
        h("span", {}, "·"), h("span", {}, onList ? "In Your Watch List" : "Blind Spot"),
        it.runtime_min ? h("span", { class: "num" }, `· ${it.runtime_min} min`) : null,
        h("span", { class: "num", style: "margin-left:auto" }, it.year ?? "")),
      h("h3", {}, it.title),
      h("p", { class: "muted" }, "Directed by ", h("strong", { style: "color:var(--color-ink);font-weight:600" }, it.directors.map((d) => d.name).join(", ") || "unknown"),
        it.genres && it.genres.length ? ` · ${it.genres.join(" / ")}` : ""),
      rationale(p.rationale),
      p.completion.slice(0, 1).map((d) => completionPanel(d)),
      h("div", { style: "display:flex;gap:8px;margin-top:16px;padding-top:16px;border-top:1px solid var(--color-rule);flex-wrap:wrap" },
        h("button", { class: "btn btn--primary", type: "button", onclick: () => openLogDialog(it, ctx, reload) }, "✓ Log as Watched"),
        onList ? null : queueButton(it, ctx, reload)));
  }

  function rationale(r) {
    const wrap = h("div", { class: "pick__rationale" });
    const para = h("p", {});
    const panel = h("div", { class: "cite-panel", hidden: true });
    let last = 0, m;
    CITE.lastIndex = 0;
    while ((m = CITE.exec(r.text))) {
      para.append(r.text.slice(last, m.index));
      const n = Number(m[1]);
      const c = r.citations.find((x) => x.n === n);
      para.append(c ? h("button", { class: "cite", type: "button", "aria-label": `Source ${n}`,
        onclick: () => {
          const open = !panel.hidden && panel.dataset.n === String(n);
          panel.hidden = open; panel.dataset.n = String(n);
          panel.replaceChildren(h("strong", {}, `[${n}] ${c.title}${c.year ? ` (${c.year})` : ""}`),
            c.source ? h("span", { class: "muted" }, ` · ${c.source}${c.section_name ? ` · ${c.section_name}` : ""}`) : null,
            h("p", { style: "margin-top:6px" }, c.snippet));
        } }, `[${n}]`) : "");
      last = m.index + m[0].length;
    }
    para.append(r.text.slice(last));
    wrap.append(para, panel);
    return wrap;
  }

  function completionPanel(d) {
    return h("div", { class: "completion" },
      h("div", { class: "completion__head" }, h("span", {}, `${d.name} Collection`),
        h("span", { class: "num" }, `${d.seen}/${d.total} watched (${fmtPct(d.before_pct)} → `, h("strong", { style: "color:var(--color-accent)" }, fmtPct(d.after_pct)), ")")),
      progressBar(d.seen, d.total, d.seen + 1),
      d.remaining && d.remaining.length
        ? h("p", { class: "muted", style: "font-size:.8rem;margin-top:8px" }, "Remaining after this: ", d.remaining.map((r) => `${r.title}${r.year ? ` (${r.year})` : ""}`).join(", "))
        : h("p", { class: "muted", style: "font-size:.8rem;margin-top:8px" }, "This would complete the filmography."));
  }

  // --- home data ---
  const [overview, sugg] = await Promise.all([api.get("/api/concierge/overview"), api.get("/api/concierge/suggestions")]);
  for (const prompt of sugg.prompts) chips.append(h("button", { class: "chip chip--plain", type: "button", onclick: () => ask(prompt) }, prompt));
  queueNote.textContent = `${overview.watchlist.short_count} queued ≤ 90 min`;
  const c = overview.closest;
  caption.replaceChildren(
    h("div", { class: "num", style: "font-size:.8rem;opacity:.85" }, c ? `Nearest director milestone · ${c.seen}/${c.total} (${fmtPct(c.pct)})` : "Director milestones"),
    h("div", { style: "font-family:var(--font-display);font-size:1.5rem;font-weight:700" }, c ? c.name : "No collections yet"),
    h("div", { style: "font-size:.85rem;opacity:.9" }, c && c.quickest
      ? `Next up: ${c.quickest.title}${c.quickest.runtime_min ? ` (${c.quickest.runtime_min} min)` : ""}${c.quickest.on_watchlist ? " is in your watch list" : ""} — reaches ${fmtPct(c.quickest.after_pct)}.`
      : "Run the enrich step to load crew credits."));

  const stat = (label, value, sub, accent = false) => h("div", {}, h("div", { class: "stat__label" }, label),
    h("div", { class: `stat__value${accent ? " stat__value--accent" : ""}` }, value), h("div", { class: "stat__sub" }, sub));
  statsBox.append(
    stat("Watch List", `${overview.watchlist.count} films`, `${Math.round(overview.watchlist.total_minutes / 60)} hrs queued`),
    stat("Watching Log", `${overview.log.count} logged`, overview.log.avg_rating ? `${overview.log.avg_rating} avg rating` : "no ratings yet"),
    stat("Directors Tracked", `${overview.directors.tracked} active`, "Full feature filmographies"),
    stat("Closest Completion", c ? fmtPct(c.pct) : "–", c ? c.name : "", true));

  if (overview.radar.length) {
    radarBox.append(
      h("div", { style: "display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px" },
        h("h2", { style: "font-size:1.6rem" }, "Collection Completion Radar"), h("a", { class: "link", href: "#/collections" }, "View all collections")),
      h("p", { class: "muted", style: "margin:4px 0 16px" }, "Directors where one or two screenings push your filmography past a major milestone."),
      h("div", { class: "grid grid--3" }, overview.radar.map((d) => h("article", { class: "card dir-card" },
        h("div", { class: "dir-card__head" }, h("h3", { style: "font-size:1.25rem" }, d.name), h("span", { class: "pct num" }, fmtPct(d.pct))),
        h("p", { class: "dir-card__meta" }, `${d.seen} of ${d.total} features seen`),
        progressBar(d.seen, d.total),
        d.quickest ? h("p", { class: "muted", style: "font-size:.85rem;margin:12px 0" }, "Quickest step: ", h("strong", { style: "color:var(--color-ink);font-weight:600" }, d.quickest.title),
          d.quickest.runtime_min ? ` (${d.quickest.runtime_min} min)` : "", d.quickest.on_watchlist ? " — in Watch List" : "", `. Brings you to ${fmtPct(d.quickest.after_pct)}.`) : null,
        h("button", { class: "link", style: "background:none;border:0;padding:0;cursor:pointer", type: "button",
          onclick: () => { ask(`What should I watch next from ${d.name}?`); window.scrollTo({ top: 0, behavior: "smooth" }); } }, `Ask concierge about ${d.name} →`)))));
  }

  const q = queryFromHash();
  if (q) await ask(q);
}
