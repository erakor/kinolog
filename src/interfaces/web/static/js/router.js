const routes = new Map();
let current = null;

export function register(name, loader) { routes.set(name, loader); }

export function currentRoute() {
  const m = location.hash.replace(/^#\/?/, "").split(/[/?]/)[0];
  return routes.has(m) ? m : "concierge";
}

export async function render(ctx) {
  const name = currentRoute();
  document.querySelectorAll(".nav a").forEach((a) => {
    if (a.dataset.route === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const view = document.getElementById("view");
  const token = (current = Symbol(name));
  view.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading";
  loading.textContent = "Loading…";
  view.append(loading);
  try {
    const mod = await routes.get(name)();
    if (token !== current) return;
    view.replaceChildren();
    await mod.mount(view, ctx);
  } catch (e) {
    if (token !== current) return;
    view.replaceChildren();
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = `Could not load this view: ${e.message || e}`;
    view.append(p);
  }
  window.scrollTo(0, 0);
}

export function start(ctx) {
  window.addEventListener("hashchange", () => render(ctx));
  return render(ctx);
}
