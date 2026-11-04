"use strict";
const ICONS = {
  connect: '<path d="M9 2v6M15 2v6M7 8h10v4a5 5 0 0 1-10 0zM12 17v5"/>',
  cheats: '<path d="M4 7h16l-1.5 9H5.5zM8 7a4 4 0 0 1 8 0"/>',
  games: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  mcp: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
  docs: '<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  check: '<path d="m5 13 4 4L19 7"/>',
};
const ROUTES = [
  ["connect", "Connect"], ["cheats", "Cheats"], ["games", "Games"], ["mcp", "MCP"], ["docs", "Docs"],
];
const BUTTONS = "UP DOWN LEFT RIGHT L1 R1 L2 R2 CROSS CIRCLE SQUARE TRIANGLE".split(" ");

const state = { status: null, games: [], game: null, cheats: [], cart: [], category: "All", query: "", running: false, frame: null, editor: [], run: { index: -1, text: "", tone: "" } };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "html") node.innerHTML = value;
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  node.append(...children.flat().filter((child) => child != null));
  return node;
}
const icon = (name) => el("span", { html: `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`, style: "display:contents" });
const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const init = options.body === undefined ? options : {
    ...options, method: options.method || "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(options.body),
  };
  const reply = await fetch(path, init);
  const text = await reply.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!reply.ok) throw new Error(data.error || "The request failed.");
  return data;
}

let toastTimer;
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4000);
}

function guarded(handler) {
  return async (event) => {
    const button = event?.currentTarget;
    if (button) button.disabled = true;
    try { await handler(event); }
    catch (error) { toast(error.message); }
    finally { if (button) button.disabled = false; }
  };
}

function route() {
  const name = location.hash.replace("#/", "");
  return ROUTES.some(([id]) => id === name) ? name : "connect";
}

function drawNav() {
  const nav = $("#nav");
  nav.replaceChildren(...ROUTES.map(([id, label]) =>
    el("a", { href: `#/${id}`, "aria-current": route() === id ? "page" : false }, icon(id), el("span", {}, label))));
}

function drawPill() {
  const s = state.status;
  const pill = $("#pill");
  let tone = "bad", text = "No console";
  if (s?.running) { tone = "warn"; text = "Running"; }
  else if (s?.console && s.paired) { tone = "ok"; text = `${s.console.name} ready`; }
  else if (s?.console) { tone = "warn"; text = `${s.console.name} not paired`; }
  else if (s?.network_error) { text = "Network blocked"; }
  else if (s?.console_ip) { text = "Console offline"; }
  pill.replaceChildren(el("span", { class: "dot " + tone }), text);
}

async function refreshStatus() {
  try {
    state.status = await api("/api/status");
    drawPill();
  } catch { state.status = null; drawPill(); }
}

/* Connect */
function stepNode(index, title, done, current, body) {
  return el("li", { class: `step ${done ? "done" : ""} ${current ? "current" : ""}` },
    el("div", { class: "mark", "aria-hidden": "true" }, done ? icon("check") : String(index)),
    el("div", {},
      el("div", { class: "row" }, el("h2", {}, title),
        el("span", { class: `badge ${done ? "ok" : current ? "warn" : ""}` }, done ? "Done" : current ? "Action needed" : "Waiting")),
      ...(done && !current ? [] : body)));
}

function drawConnect() {
  const s = state.status || {};
  const found = Boolean(s.console), signedIn = (s.accounts || []).length > 0, paired = Boolean(s.paired);
  const root = el("div", { class: "stack" });
  const scanResult = el("div", { class: "help" });

  const scan = guarded(async () => {
    scanResult.textContent = "Searching your network…";
    const { consoles } = await api("/api/scan", { body: {} });
    await refreshStatus();
    if (consoles.length === 1) { drawView(); return; }
    scanResult.replaceChildren(consoles.length ? "Several consoles answered. Pick one:" : "Nothing answered. Check the list below, or enter the address by hand.",
      ...consoles.map((c) => el("button", { class: "ghost", type: "button", onclick: guarded(async () => { await api("/api/console", { body: { ip: c.ip } }); await refreshStatus(); drawView(); }) }, `${c.name} (${c.ip})`)));
  });
  const ipField = el("input", { id: "ip", inputmode: "decimal", autocomplete: "off", placeholder: "192.168.1.20" });
  const step1 = [
    el("p", { class: "muted small" }, found ? `Found ${s.console.name} at ${s.console.ip}.` : "Turn the PS5 on and connect it to the same network as this computer."),
    el("div", { class: "row" }, el("button", { class: "primary", type: "button", onclick: scan }, "Search network")),
    scanResult,
    el("details", { style: "margin-top:12px" }, el("summary", {}, "Enter the address by hand"),
      el("label", { for: "ip" }, "Console IP address"), ipField,
      el("p", { class: "help" }, "On the PS5: Settings, Network, View Connection Status."),
      el("button", { class: "ghost", type: "button", onclick: guarded(async () => { await api("/api/console", { body: { ip: ipField.value } }); await refreshStatus(); drawView(); }) }, "Use this address")),
  ];

  const redirect = el("input", { id: "redirect", autocomplete: "off", placeholder: "https://remoteplay.dl.playstation.net/…" });
  const step2 = [
    el("ol", { class: "small" },
      el("li", {}, "On the PS5 open Settings, System, Remote Play and turn on Enable Remote Play."),
      el("li", {}, "Open the Sony sign-in page and log in. Your password only goes to Sony."),
      el("li", {}, "After login the page may look blank. Copy the whole address from the address bar.")),
    el("div", { class: "row" }, el("button", { class: "ghost", type: "button", onclick: guarded(async () => { const { url } = await api("/api/pair/url"); window.open(url, "_blank", "noopener"); }) }, "Open Sony sign-in")),
    el("div", { class: "field", style: "margin-top:12px" }, el("label", { for: "redirect" }, "Address after sign-in"), redirect),
    el("button", { class: "primary", type: "button", onclick: guarded(async () => { await api("/api/pair/account", { body: { redirect_url: redirect.value } }); await refreshStatus(); drawView(); }) }, "Save account"),
  ];

  const pin = el("input", { id: "pin", inputmode: "numeric", autocomplete: "one-time-code", placeholder: "12345678", maxlength: 9 });
  const step3 = [
    el("p", { class: "small" }, "On the PS5 open Settings, System, Remote Play, Link Device. Enter the 8-digit code it shows."),
    el("div", { class: "field" }, el("label", { for: "pin" }, "Pairing code"), pin, el("p", { class: "help" }, "Codes expire within a few minutes.")),
    el("button", { class: "primary", type: "button", onclick: guarded(async () => { await api("/api/pair/link", { body: { pin: pin.value } }); await refreshStatus(); drawView(); toast("Paired."); }) }, "Pair console"),
  ];

  if (s.network_error) root.append(el("div", { class: "notice", role: "alert" }, s.network_error));
  root.append(el("ol", { class: "steps" },
    stepNode(1, "Find your console", found, !found, step1),
    stepNode(2, "Sign in to PlayStation Network", signedIn, found && !signedIn, step2),
    stepNode(3, "Pair this computer", paired, found && signedIn && !paired, step3),
    stepNode(4, "Check the screen", false, paired, screenCheck())));
  return root;
}

function screenCheck() {
  const slot = el("div");
  return [
    el("p", { class: "small muted" }, "The PS5 does not report which game is open, so the app looks at the real screen."),
    el("div", { class: "notice" }, "Connecting and disconnecting pauses most games."),
    el("button", { class: "ghost", type: "button", onclick: guarded(async () => {
      slot.replaceChildren(el("p", { class: "status row" }, el("span", { class: "spin" }), "Connecting to the console…"));
      try {
        const { frame } = await api("/api/snapshot", { body: {} });
        slot.replaceChildren(el("img", { class: "shot", src: `data:image/png;base64,${frame}`, alt: "Current PS5 screen" }));
      } catch (error) { slot.replaceChildren(el("p", { class: "status bad" }, error.message)); }
    }) }, "Check open game"), slot,
  ];
}

/* Cheats */
async function loadGames() {
  state.games = await api("/api/games");
  const saved = state.status?.active_game;
  if (!state.games.some((g) => g.id === state.game)) {
    state.game = state.games.some((g) => g.id === saved) ? saved : state.games[0]?.id ?? null;
  }
  state.cheats = state.game ? await api(`/api/games/${state.game}/cheats`) : [];
}

function cheatCard(cheat) {
  return el("button", { class: "cheat", type: "button", onclick: () => { if (state.running) return; state.cart.push(cheat); state.frame = null; state.run = { index: -1, text: "", tone: "" }; drawView(); } },
    el("span", {}, cheat.name,
      el("small", {}, cheat.verified ? "Tested on console" : cheat.category, cheat.warning ? el("span", { class: "flag" }, " · cannot be undone") : null)),
    icon("plus"));
}

function drawCart() {
  const status = el("p", { class: `status ${state.run.tone}`, id: "run-status", role: "status" }, state.run.text);
  const stateClass = (index) => (!state.running ? "" : index < state.run.index ? "sent" : index === state.run.index ? "active" : "");
  const list = el("ol", { class: "list", id: "cart" }, state.cart.map((cheat, index) =>
    el("li", { class: stateClass(index) },
      el("span", {}, cheat.name),
      el("button", { class: "icon", type: "button", disabled: index === 0 || state.running, "aria-label": `Move ${cheat.name} up`, onclick: () => { [state.cart[index - 1], state.cart[index]] = [state.cart[index], state.cart[index - 1]]; drawView(); } }, icon("up")),
      el("button", { class: "icon", type: "button", disabled: state.running, "aria-label": `Remove ${cheat.name}`, onclick: () => { state.cart.splice(index, 1); drawView(); } }, icon("x")))));
  const risky = state.cart.some((cheat) => cheat.warning);
  const t = state.status?.timings || {};
  const timing = (key, label, help) => {
    const input = el("input", { id: `t-${key}`, type: "number", step: "0.01", value: t[key] ?? "", onchange: guarded(async () => { await api("/api/settings", { body: { [key]: input.value } }); await refreshStatus(); }) });
    return el("div", { class: "field" }, el("label", { for: `t-${key}` }, label), input, el("p", { class: "help" }, help));
  };
  return el("aside", { class: "card cart", "aria-label": "Cart" },
    el("div", { class: "row", style: "justify-content:space-between" }, el("h2", {}, `Cart (${state.cart.length})`),
      el("button", { class: "ghost", type: "button", disabled: !state.cart.length || state.running, onclick: () => { state.cart = []; drawView(); } }, "Clear")),
    state.cart.length ? list : el("p", { class: "empty" }, "Pick cheats to add them here."),
    risky ? el("div", { class: "notice" }, "This cart has a cheat that cannot be undone. Do not save afterwards.") : null,
    el("div", { class: "notice info" }, "Stay in gameplay, not in a menu. The game pauses when the app disconnects."),
    el("button", { class: "primary", type: "button", id: "run", style: "width:100%", disabled: !state.cart.length || state.running || !state.status?.paired, onclick: runCart }, "Run"),
    !state.status?.paired ? el("p", { class: "help" }, "Finish the Connect steps first.") : null,
    status,
    state.frame ? el("img", { class: "shot", src: `data:image/png;base64,${state.frame}`, alt: "Screen after the run" }) : null,
    el("details", { style: "margin-top:12px" }, el("summary", {}, "Timing"),
      timing("hold", "Press length (s)", "How long each button stays down."),
      timing("gap", "Between buttons (s)", "Pause after each button."),
      timing("between", "Between cheats (s)", "Pause between two cheats."),
      timing("tail", "Wait before disconnect (s)", "Keeps the session open after the last cheat.")));
}

async function runCart() {
  state.running = true;
  state.frame = null;
  state.run = { index: -1, text: "", tone: "" };
  const slugs = state.cart.map((cheat) => cheat.slug);
  const update = (index, text, tone = "") => {
    state.run = { index, text, tone };
    if (route() === "cheats") drawView();
  };
  update(-1, "Connecting to the console…");
  let finalText = "", tone = "";
  try {
    const reply = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ game: state.game, cheats: slugs }) });
    if (!reply.ok) throw new Error((await reply.json()).error);
    const reader = reply.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines.filter(Boolean)) {
        const event = JSON.parse(line);
        if (event.type === "cheat") update(event.index, `Sending ${state.cart[event.index].name}…`);
        if (event.type === "waiting") update(state.cart.length, `All sent. Waiting ${event.seconds} s…`);
        if (event.type === "done") { state.frame = event.frame; finalText = "Done. Disconnected once."; tone = "good"; }
        if (event.type === "error") { finalText = event.message; tone = "bad"; }
      }
    }
  } catch (error) { finalText = error.message; tone = "bad"; }
  state.running = false;
  update(-1, finalText, tone);
}

function drawCheats() {
  if (!state.games.length) return el("div", { class: "card empty" }, "No games yet. ", el("a", { href: "#/games" }, "Add one on the Games page."));
  const select = el("select", { id: "game", onchange: guarded(async (event) => {
    state.game = event.target.value; state.cart = []; state.category = "All"; state.frame = null;
    state.cheats = await api(`/api/games/${state.game}/cheats`);
    await api("/api/settings", { body: { active_game: state.game } });
    drawView();
  }) }, state.games.map((game) => el("option", { value: game.id, selected: game.id === state.game }, `${game.title} (${game.cheat_count})`)));
  const game = state.games.find((g) => g.id === state.game);
  const results = el("div");
  const paint = () => {
    const q = state.query.toLowerCase();
    const groups = {};
    for (const cheat of state.cheats) {
      if (state.category !== "All" && cheat.category !== state.category) continue;
      if (q && !cheat.name.toLowerCase().includes(q) && !cheat.category.toLowerCase().includes(q)) continue;
      (groups[cheat.category] ||= []).push(cheat);
    }
    const names = Object.keys(groups);
    results.replaceChildren(...(names.length ? names.flatMap((name) => [el("h3", {}, name), el("div", { class: "grid" }, groups[name].map(cheatCard))])
      : [el("p", { class: "empty" }, "No cheats match. Clear the search, or add one on the Games page.")]));
  };
  const categories = ["All", ...new Set(state.cheats.map((c) => c.category))];
  const search = el("input", { id: "search", type: "search", value: state.query, placeholder: "Search cheats", "aria-label": "Search cheats", oninput: (e) => { state.query = e.target.value; paint(); } });
  paint();
  return el("div", { class: "layout" },
    el("section", { "aria-label": "Cheat list" },
      el("div", { class: "two" },
        el("div", {}, el("label", { for: "game" }, "Game"), select),
        el("div", {}, el("label", { for: "search" }, "Search"), search)),
      game?.notes ? el("p", { class: "help" }, game.notes) : null,
      el("div", { class: "chips" }, categories.map((name) => el("button", { class: "chip", type: "button", "aria-pressed": String(state.category === name), onclick: () => { state.category = name; drawView(); } }, name))),
      results),
    drawCart());
}

/* Games */
function drawGames() {
  const title = el("input", { id: "g-title", placeholder: "Game title" });
  const source = el("input", { id: "g-source", placeholder: "https://…" });
  const addGame = el("form", { class: "card", onsubmit: guarded(async (event) => {
    event.preventDefault();
    const game = await api("/api/games", { body: { title: title.value, source: source.value } });
    state.game = game.id; await loadGames(); drawView(); toast("Game added.");
  }) },
    el("h2", {}, "Add a game"),
    el("div", { class: "field" }, el("label", { for: "g-title" }, "Title"), title),
    el("div", { class: "field" }, el("label", { for: "g-source" }, "Where the codes came from"), source),
    el("button", { class: "ghost", type: "submit" }, "Add game"));

  const name = el("input", { id: "c-name", placeholder: "Full health" });
  const category = el("input", { id: "c-cat", placeholder: "Player" });
  const seqView = el("p", { class: "seq", id: "seq" }, state.editor.join(" ") || "Press the buttons in order.");
  const showSeq = () => { seqView.textContent = state.editor.join(" ") || "Press the buttons in order."; };
  const gameSelect = el("select", { id: "c-game" }, state.games.map((g) => el("option", { value: g.id, selected: g.id === state.game }, g.title)));
  const addCheat = el("form", { class: "card", onsubmit: guarded(async (event) => {
    event.preventDefault();
    await api(`/api/games/${gameSelect.value}/cheats`, { body: { name: name.value, category: category.value, sequence: state.editor } });
    state.editor = []; state.game = gameSelect.value; await loadGames(); drawView(); toast("Cheat added.");
  }) },
    el("h2", {}, "Add a cheat"),
    el("div", { class: "field" }, el("label", { for: "c-game" }, "Game"), gameSelect),
    el("div", { class: "field" }, el("label", { for: "c-name" }, "Name"), name),
    el("div", { class: "field" }, el("label", { for: "c-cat" }, "Category"), category),
    el("label", {}, "Button sequence"),
    el("div", { class: "pad" }, BUTTONS.map((button) => el("button", { type: "button", onclick: () => { state.editor.push(button); showSeq(); } }, button))),
    seqView,
    el("div", { class: "row" }, el("button", { class: "ghost", type: "submit" }, "Save cheat"),
      el("button", { class: "ghost", type: "button", onclick: () => { state.editor.pop(); showSeq(); } }, "Undo"),
      el("button", { class: "ghost", type: "button", onclick: () => { state.editor = []; showSeq(); } }, "Clear")));

  const pack = el("textarea", { id: "pack", placeholder: '{"game": {"title": "My Game"}, "cheats": [{"name": "Health", "sequence": "UP DOWN CROSS"}]}' });
  const importCard = el("form", { class: "card", onsubmit: guarded(async (event) => {
    event.preventDefault();
    let data;
    try { data = JSON.parse(pack.value); } catch { throw new Error("That is not valid JSON."); }
    const result = await api("/api/import", { body: data });
    await loadGames(); drawView(); toast(`Imported ${result.imported} cheats.`);
  }) }, el("h2", {}, "Import a cheat pack"), el("div", { class: "field" }, el("label", { for: "pack" }, "Pack JSON"), pack), el("button", { class: "ghost", type: "submit" }, "Import"));

  const library = el("div", { class: "card" }, el("h2", {}, "Library"),
    state.games.length ? el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Game"), el("th", {}, "Cheats"), el("th", {}, el("span", { class: "muted" }, "Actions")))),
      el("tbody", {}, state.games.map((game) => el("tr", {},
        el("td", {}, game.title, game.source ? el("div", { class: "small" }, el("a", { href: game.source, target: "_blank", rel: "noopener" }, "Source")) : null),
        el("td", {}, String(game.cheat_count)),
        el("td", {}, el("div", { class: "row" },
          el("a", { class: "btn", href: `/api/games/${game.id}/export`, download: `${game.id}.json` }, "Export"),
          el("button", { class: "danger", type: "button", onclick: guarded(async () => {
            if (!confirm(`Delete ${game.title} and its cheats?`)) return;
            await api(`/api/games/${game.id}`, { method: "DELETE" });
            await loadGames(); drawView();
          }) }, "Delete")))))))
      : el("p", { class: "empty" }, "No games yet. Add one below."));
  return el("div", { class: "stack" }, library, el("div", { class: "two" }, addGame, importCard), addCheat);
}

/* MCP */
function copyBlock(text) {
  return el("div", {}, el("pre", {}, el("code", {}, text)),
    el("button", { class: "ghost", type: "button", onclick: guarded(async () => { await navigator.clipboard.writeText(text); toast("Copied."); }) }, "Copy"));
}

function drawMcp() {
  const mcp = state.status?.mcp || {};
  const stdio = JSON.stringify({ mcpServers: { "ps5-cheater": { command: mcp.command, args: mcp.args } } }, null, 2);
  const tools = [["get_status", "Selected console, reachability, pairing"], ["scan_network", "Find consoles on the local network"],
    ["list_games", "Games and cheat counts"], ["list_cheats", "Cheats of a game, with search"], ["add_game", "Add or update a game"],
    ["add_cheat", "Add a button sequence"], ["delete_cheat", "Remove a cheat"], ["import_pack", "Import a whole pack"],
    ["capture_screen", "See the real console screen"], ["run_cheats", "Run cheats in one connection and return the screen"]];
  const toggle = el("input", { type: "checkbox", id: "mcp-on", checked: mcp.enabled, onchange: guarded(async (event) => {
    await api("/api/settings", { body: { mcp_enabled: event.target.checked } });
    await refreshStatus(); drawView();
  }) });
  return el("div", { class: "stack" },
    el("div", { class: "card" },
      el("h2", {}, "Local HTTP endpoint"),
      el("p", { class: "muted small" }, "Lets an AI agent on this computer read the database and run cheats. It is off until you turn it on."),
      el("label", { class: "switch", for: "mcp-on" }, toggle, mcp.enabled ? "Enabled" : "Disabled"),
      mcp.enabled ? el("div", { style: "margin-top:12px" }, el("h3", {}, "Claude Code"), copyBlock(`claude mcp add --transport http ps5-cheater ${mcp.url}`), el("h3", {}, "Other MCP clients"), copyBlock(mcp.url)) : null),
    el("div", { class: "card" }, el("h2", {}, "Stdio"), el("p", { class: "muted small" }, "Works without the toggle: the client starts the app itself. Add this to its MCP config."), copyBlock(stdio)),
    el("div", { class: "card" }, el("h2", {}, "Tools"), el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Tool"), el("th", {}, "What it does"))),
      el("tbody", {}, tools.map(([name, text]) => el("tr", {}, el("td", {}, el("code", {}, name)), el("td", {}, text)))))));
}

/* Docs */
function drawDocs() {
  const section = (title, ...body) => el("details", {}, el("summary", {}, title), el("div", { class: "doc" }, ...body));
  return el("div", { class: "stack doc" },
    el("p", { class: "muted" }, "PS5 Cheater presses a game's own cheat codes for you, over Sony's Remote Play. It needs no jailbreak and changes nothing on the console."),
    section("Getting connected",
      el("ol", {}, el("li", {}, "Turn the PS5 on and connect it to the same network as this computer."), el("li", {}, "Open Connect and press Search network."), el("li", {}, "Enable Remote Play on the PS5, then sign in to PlayStation Network."), el("li", {}, "Enter the 8-digit code from Link Device."), el("li", {}, "Press Check open game to confirm the picture."))),
    section("If the console is not found",
      el("ul", {}, el("li", {}, "Wake the console. It only answers when on or in rest mode with Remote Play allowed."), el("li", {}, "Put both devices on the same network, and avoid guest Wi-Fi."), el("li", {}, "A VPN can block local traffic. If search fails, turn it off."), el("li", {}, "On macOS allow Local Network access in System Settings, Privacy & Security."), el("li", {}, "Enter the console address by hand from Settings, Network, View Connection Status."))),
    section("Running cheats",
      el("ul", {}, el("li", {}, "Load into the game and stay in gameplay, not a menu."), el("li", {}, "Save first. Cheats usually disable trophies on that save."), el("li", {}, "Add cheats to the cart and press Run. The app connects once, sends everything in order, waits, then disconnects once."), el("li", {}, "The game then pauses because its controller left. Press your own controller to continue."))),
    section("Why the first run is slow",
      el("p", {}, "Opening Remote Play takes about 5 seconds, and the console needs 3 more to register the controller. A run right after another can take 10 seconds longer while the console frees the previous session.")),
    section("Open game check",
      el("p", {}, "The PS5 does not report the running title on the local network, so Check open game shows the real screen instead.")),
    section("Adding games",
      el("p", {}, "Use the Games page, or import a pack:"),
      el("pre", {}, el("code", {}, '{\n  "game": {"title": "My Game", "source": "https://example.com"},\n  "cheats": [\n    {"name": "Health", "category": "Player", "sequence": "UP DOWN CROSS"}\n  ]\n}'))),
    section("Limits",
      el("p", {}, "It only sends button presses a player could enter, so it only works in games with built-in cheat codes. It is meant for single-player games. Do not use it online."),
      el("p", {}, `Version ${state.status?.version ?? ""}. Not affiliated with Sony Interactive Entertainment.`)));
}

const VIEWS = { connect: drawConnect, cheats: drawCheats, games: drawGames, mcp: drawMcp, docs: drawDocs };

function drawView() {
  const id = route();
  $("#title").textContent = ROUTES.find(([key]) => key === id)[1];
  document.title = `${$("#title").textContent} · PS5 Cheater`;
  drawNav();
  $("#view").replaceChildren(VIEWS[id]());
}

window.addEventListener("hashchange", async () => {
  await loadGames().catch((error) => toast(error.message));
  drawView();
  $("#title").focus();
});
$("#quit").addEventListener("click", guarded(async () => {
  if (!confirm("Quit PS5 Cheater?")) return;
  await api("/api/quit", { body: {} });
  document.body.replaceChildren(el("p", { class: "empty" }, "PS5 Cheater has stopped. You can close this tab."));
}));

(async () => {
  await refreshStatus();
  if (!state.status?.console && !state.status?.console_ip) await api("/api/scan", { body: {} }).then(refreshStatus).catch(() => {});
  await loadGames().catch((error) => toast(error.message));
  if (!location.hash && state.status?.paired) location.replace("#/cheats");
  drawView();
  setInterval(async () => {
    const key = () => JSON.stringify([state.status?.paired, state.status?.console?.ip, state.status?.accounts, state.status?.network_error]);
    const before = key();
    await refreshStatus();
    if (before !== key() && route() === "connect") drawView();
  }, 5000);
})();
