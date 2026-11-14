import { api } from "../api.js";
import { h, toast } from "../util.js";

// A button that opens a file picker and uploads a Letterboxd export (.zip or a single .csv).
export function importButton(ctx, onDone) {
  const input = h("input", { type: "file", accept: ".zip,.csv", class: "sr-only", tabindex: "-1",
    onchange: async () => {
      const file = input.files[0];
      input.value = "";
      if (!file) return;
      btn.disabled = true;
      try {
        const s = await api.upload("/api/import/letterboxd", file);
        const skipped = s.skipped_manual_override ? `, ${s.skipped_manual_override} kept as you edited them` : "";
        toast(`Imported ${s.diary} diary entries, ${s.watchlist} watch list, ${s.likes} likes${skipped}`);
        if (ctx.refreshHealth) ctx.refreshHealth();
        if (onDone) await onDone();
      } catch (e) {
        toast(e.message, "error");
      } finally {
        btn.disabled = false;
      }
    } });
  const btn = h("button", { class: "btn", type: "button", onclick: () => input.click() }, "↑ Import CSV");
  return h("span", {}, btn, input);
}
