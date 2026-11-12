// Small enhancements: copy button, snippet tabs, table filters, site search. No dependencies.
(() => {
  const root = document.body.dataset.root || "";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  // ---- snippet tabs (remembers the last chosen tab, e.g. polytope) ----
  const tabs = document.querySelector(".tabs");
  const showTab = (id) => {
    if (!tabs.querySelector(`[data-tab="${id}"]`)) return false;
    tabs.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === id));
    tabs.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== id; });
    return true;
  };
  if (tabs) {
    const saved = store.get("tab");
    if (saved) showTab(saved);
  }

  document.addEventListener("click", (e) => {
    const tab = e.target.closest("[data-tab]");
    if (tab && showTab(tab.dataset.tab)) store.set("tab", tab.dataset.tab);

    const copy = e.target.closest("[data-copy]");
    if (copy) {
      const text = copy.parentElement.querySelector("pre").textContent;
      navigator.clipboard.writeText(text).then(() => {
        copy.textContent = "Copied";
        setTimeout(() => { copy.textContent = "Copy"; }, 1500);
      }, () => { copy.textContent = "Select + ⌘C"; });
    }
  });

  // ---- source table: text filter + chips (within a group OR, across groups AND) ----
  const section = document.querySelector(".filterable");
  if (section) {
    const rows = [...section.querySelectorAll("tbody tr")];
    const input = section.querySelector("#rowfilter");
    const bar = section.querySelector("#chipbar");
    const count = section.querySelector("#rowcount");
    const active = { driver: new Set(), levtype: new Set(), grid: new Set() };
    const labels = { driver: "driver", levtype: "levels", grid: "grid" };

    const apply = () => {
      const q = input.value.trim().toLowerCase();
      let n = 0;
      rows.forEach((r) => {
        const ok = (!q || r.textContent.toLowerCase().includes(q)) &&
          Object.entries(active).every(([k, set]) => !set.size || set.has(r.dataset[k]));
        r.hidden = !ok;
        if (ok) n += 1;
      });
      count.textContent = n === rows.length ? String(n) : `${n} of ${rows.length}`;
    };

    Object.keys(active).forEach((key) => {
      const values = [...new Set(rows.map((r) => r.dataset[key]).filter(Boolean))].sort();
      if (values.length < 2) return;
      bar.append(el("span", "grp", labels[key]));
      values.forEach((v) => {
        const b = el("button", "chip", v);
        b.type = "button";
        b.addEventListener("click", () => {
          active[key].has(v) ? active[key].delete(v) : active[key].add(v);
          b.classList.toggle("on");
          apply();
        });
        bar.append(b);
      });
    });
    input.addEventListener("input", apply);
  }

  // ---- site search over search.json (loaded on first focus) ----
  const q = document.getElementById("q");
  const results = document.getElementById("results");
  let index = null;
  let sel = -1;

  const load = () => index || (index = fetch(root + "search.json").then((r) => r.json()).then((rows) =>
    rows.map((r) => ({ ...r, hay: `${r.t} ${r.d} ${r.k} ${r.g || ""}`.toLowerCase() }))).catch(() => []));

  const render = (hits) => {
    results.replaceChildren();
    if (!hits.length) results.append(el("li", "empty", "No match"));
    hits.forEach((h) => {
      const li = el("li");
      const a = el("a");
      a.href = root + h.u;
      a.append(el("div", "", h.t));
      a.append(el("div", "d", `${h.k}${h.d ? " · " + h.d : ""}`));
      li.append(a);
      results.append(li);
    });
    results.hidden = false;
    sel = -1;
  };

  q.addEventListener("focus", load);
  q.addEventListener("input", async () => {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { results.hidden = true; return; }
    const rows = await load();
    render(rows.filter((r) => terms.every((t) => r.hay.includes(t))).slice(0, 40));
  });
  q.addEventListener("keydown", (e) => {
    const links = [...results.querySelectorAll("a")];
    if (e.key === "Escape") { results.hidden = true; q.blur(); }
    if (!links.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
      links.forEach((l, i) => l.classList.toggle("sel", i === sel));
      links[sel].scrollIntoView({ block: "nearest" });
    }
    if (e.key === "Enter") { e.preventDefault(); (links[sel] || links[0]).click(); }
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) results.hidden = true; });
})();
