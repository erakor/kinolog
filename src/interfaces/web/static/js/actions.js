// Shared mutations and dialogs used by several views.
import { api } from "./api.js";
import { h, openModal, ratingLabel, today, toast } from "./util.js";

async function run(promise, okMessage, reload) {
  try {
    await promise;
    if (okMessage) toast(okMessage);
    if (reload) await reload();
  } catch (e) {
    toast(e.message || "Something went wrong", "error");
  }
}

// item may be a card (item_id) or a collection film (item_id) - both expose item_id/title.
export function queueButton(item, reload) {
  return h("button", { class: "btn btn--sm", type: "button",
    onclick: () => run(api.post("/api/watchlist", { item_id: item.item_id }), `Queued ${item.title}`, reload) },
  "+ Queue");
}

export function removeButton(item, reload) {
  return h("button", { class: "btn btn--icon", type: "button", "aria-label": `Remove ${item.title} from Watch List`, title: "Remove from Watch List",
    onclick: () => run(api.del(`/api/watchlist/${item.item_id}`), `Removed ${item.title}`, reload) }, "🗑");
}

export function logButton(item, reload, small = false) {
  return h("button", { class: `btn btn--primary${small ? " btn--sm" : ""}`, type: "button",
    onclick: () => openLogDialog(item, reload) }, small ? "Log" : "✓ Log Watched");
}

export function ratingOptions(selected) {
  const opts = [h("option", { value: "" }, "No rating")];
  for (let r = 10; r >= 1; r--) opts.push(h("option", { value: r, selected: r === selected }, `${ratingLabel(r)} ★`));
  return opts;
}

export function openLogDialog(item, reload) {
  return openModal(`Log ${item.title}`, (close) => {
    const date = h("input", { type: "date", value: today(), max: today(), required: true });
    const rating = h("select", {}, ratingOptions(null));
    const liked = h("input", { type: "checkbox" });
    const keep = h("input", { type: "checkbox" });
    const submit = h("button", { class: "btn btn--primary", type: "submit" }, "Log as watched");
    const form = h("form", {
      onsubmit: async (e) => {
        e.preventDefault();
        submit.disabled = true;
        const body = { watched_on: date.value, keep_on_watchlist: keep.checked };
        if (rating.value) body.rating = Number(rating.value);
        if (liked.checked) body.liked = true;
        await run(api.post(`/api/watchlist/${item.item_id}/watched`, body), `Logged ${item.title}`, reload);
        close();
      },
    },
    h("div", { class: "field-row" },
      h("label", { class: "field" }, "Date watched", date),
      h("label", { class: "field" }, "Rating", rating)),
    h("label", { class: "field", style: "display:flex;gap:8px;align-items:center" }, liked, "Add a heart"),
    h("label", { class: "field", style: "display:flex;gap:8px;align-items:center" }, keep, "Keep on Watch List"),
    h("div", { class: "modal__actions" },
      h("button", { class: "btn", type: "button", onclick: close }, "Cancel"), submit));
    return form;
  });
}

// Used by "+ Add Film": the header button.
export function lookupList(onPick) {
  const box = h("div", { class: "list", style: "margin-top:12px" });
  let seq = 0;
  async function search(q) {
    const my = ++seq;
    if (!q) { box.replaceChildren(); return; }
    const items = await api.get("/api/items/lookup", { q, limit: 8 });
    if (my !== seq) return;
    box.replaceChildren();
    if (!items.length) {
      box.append(h("p", { class: "muted", style: "padding:16px" }, "No match in your index. Import a Letterboxd export or run the ingest pipeline to add new films."));
      return;
    }
    for (const it of items) box.append(onPick(it));
  }
  return { box, search };
}
