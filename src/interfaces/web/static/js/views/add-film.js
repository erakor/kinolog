import { api } from "../api.js";
import { logButton, lookupList, queueButton } from "../actions.js";
import { clear, h, openModal, searchBox, toast } from "../util.js";

export function openAddFilm(ctx) {
  openModal("Add Film", (close) => {
    const rerender = async () => { close(); if (location.hash) window.dispatchEvent(new HashChangeEvent("hashchange")); };
    const { box, search } = lookupList("", (it) => {
      const sub = [it.year, it.directors.map((d) => d.name).join(", ")].filter(Boolean).join(" · ");
      const actions = it.status.seen
        ? [h("span", { class: "muted", style: "font-size:.875rem" }, "Already watched")]
        : [it.status.on_watchlist ? h("span", { class: "muted", style: "font-size:.875rem" }, "In Watch List") : queueButton(it, ctx, rerender),
          logButton(it, ctx, rerender, "Log")];
      return h("div", { class: "list-row" },
        h("div", { class: "list-row__main" }, h("div", { style: "font-weight:600" }, it.title), h("div", { class: "list-row__sub" }, sub)),
        h("div", { class: "list-row__actions" }, actions));
    }, ctx);
    return h("div", {}, h("p", { class: "muted", style: "font-size:.875rem;margin-bottom:12px" }, "Find a film already in your index to queue or log it."),
      searchBox("Search by title…", (q) => search(q).catch((e) => toast(e.message, "error"))), box);
  });
}
