import { logButton, lookupList, queueButton } from "../actions.js";
import { h, openModal, searchBox, toast } from "../util.js";

export function openAddFilm() {
  openModal("Add Film", (close) => {
    const rerender = async () => { close(); if (location.hash) window.dispatchEvent(new HashChangeEvent("hashchange")); };
    const { box, search } = lookupList((it) => {
      const sub = [it.year, it.directors.map((d) => d.name).join(", ")].filter(Boolean).join(" · ");
      const note = (t) => h("span", { class: "muted", style: "font-size:.875rem" }, t);
      const actions = [it.status.seen ? note("Watched") : it.status.on_watchlist ? note("In Watch List") : queueButton(it, rerender),
        logButton(it, rerender, true)];
      return h("div", { class: "list-row" },
        h("div", { class: "list-row__main" }, h("div", { style: "font-weight:600" }, it.title), h("div", { class: "list-row__sub" }, sub)),
        h("div", { class: "list-row__actions" }, actions));
    });
    return h("div", {}, h("p", { class: "muted", style: "font-size:.875rem;margin-bottom:12px" }, "Find a film already in your index to queue or log it."),
      searchBox("Search by title…", (q) => search(q).catch((e) => toast(e.message, "error"))), box);
  });
}
