import { api } from "./api.js";
import { register, start } from "./router.js";

const ctx = { health: null, refreshHealth };

register("concierge", () => import("./views/concierge.js"));
register("watchlist", () => import("./views/watchlist.js"));
register("log", () => import("./views/log.js"));
register("collections", () => import("./views/collections.js"));

async function refreshHealth() {
  try { ctx.health = await api.get("/api/health"); } catch { ctx.health = null; }
  const banner = document.getElementById("banner");
  const h = ctx.health;
  const notes = [];
  if (h && !h.vec_available) notes.push("Vector search is unavailable, so keyword (BM25) search is used.");
  else if (h && !h.model_enabled) notes.push("Embedding model is off (--no-model): keyword search only, no taste ranking.");
  banner.textContent = notes.join(" ");
  banner.hidden = notes.length === 0;
}

document.getElementById("add-film").addEventListener("click", async () => {
  const { openAddFilm } = await import("./views/add-film.js");
  openAddFilm(ctx);
});

await refreshHealth();
await start(ctx);
