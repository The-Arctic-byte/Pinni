// Pinni editor page (C4). Talks only to the backend's /v1 API; no build step.
"use strict";

const $ = (sel) => document.querySelector(sel);
const STAFF = ["editor", "admin"];
const KIND_LABEL = { agentDraft: "Agent draft", communityReport: "Community report", readerFlag: "Reader flag" };

let token = null;
let selected = null;

function store(key, value) {
  try {
    if (value === undefined) return sessionStorage.getItem(key);
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch { /* storage blocked: stay signed in for this page only */ }
  return null;
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && token) signOut();
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.message || `${res.status} ${res.statusText}`);
  return data;
}

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

const RTL = ["fa", "ar", "he", "ur"];

// Like replaceChildren, but skips the nulls left by optional sections.
function fill(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c != null));
}

const when = (iso) => new Date(iso).toLocaleString();
const badge = (text, cls = "") => el("span", { class: `badge ${cls}` }, text);

function localized(title, text) {
  if (!text) return null;
  return el("div", {},
    title ? el("h3", {}, title) : null,
    Object.entries(text).map(([lang, value]) =>
      el("p", { class: "lang", dir: RTL.includes(lang) ? "rtl" : "ltr" }, el("b", {}, lang), value)));
}

// ---- Sign in ----

async function signIn(event) {
  event.preventDefault();
  const form = new FormData(event.target);
  $("#login-error").textContent = "";
  try {
    const session = await api("POST", "/v1/auth/login", { email: form.get("email"), password: form.get("password") });
    if (!STAFF.includes(session.user.role)) throw new Error("Only editors and admins can sign in here.");
    token = session.token;
    store("pinni-token", token);
    start(session.user);
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
}

function signOut() {
  token = null;
  store("pinni-token", null);
  $("#app").hidden = true;
  $("#login").hidden = false;
}

function start(user) {
  $("#who").textContent = `${user.displayName || user.id} · ${user.role}`;
  $("#login").hidden = true;
  $("#app").hidden = false;
  loadQueue();
  // The queue only holds the editor's categories; say which.
  api("GET", "/v1/admin/editors/me").then((me) => {
    const desk = me.role === "admin" || !me.categories ? "all categories" : me.categories.join(", ");
    $("#who").textContent = `${user.displayName || user.id} · ${user.role} · ${desk}`;
  }).catch(() => {});
}

// ---- Queue ----

async function loadQueue() {
  const list = $("#queue");
  list.replaceChildren();
  let items;
  try {
    items = await api("GET", "/v1/admin/queue");
  } catch (err) {
    list.append(el("li", { class: "error" }, err.message));
    return;
  }
  $("#queue-count").textContent = items.length ? `${items.length} waiting` : "Nothing waiting";
  for (const item of items) {
    const li = el("li", { onclick: () => open(item, li) },
      el("span", { class: "title" }, item.id),
      el("span", { class: "badges" }, badge(KIND_LABEL[item.kind]), item.risk !== "none" ? badge(`${item.risk} risk`, item.risk) : null),
      el("span", { class: "muted" }, when(item.createdAt)));
    if (selected && selected.id === item.id) li.classList.add("selected");
    list.append(li);
  }
}

async function open(item, li) {
  selected = item;
  document.querySelectorAll(".queue li").forEach((n) => n.classList.remove("selected"));
  li?.classList.add("selected");
  const detail = $("#detail");
  fill(detail, el("p", { class: "muted" }, "Loading…"));
  try {
    if (item.kind === "agentDraft") {
      showStory(await api("GET", `/v1/stories/${item.id}`), item);
    } else {
      const report = await api("GET", `/v1/admin/reports/${item.id}`);
      const story = report.storyId ? await api("GET", `/v1/stories/${report.storyId}`).catch(() => null) : null;
      showReport(report, story, item);
    }
  } catch (err) {
    fill(detail, el("p", { class: "error" }, err.message));
  }
}

function trail(item) {
  if (!item.trail?.length) return null;
  return el("div", {}, el("h3", {}, "What happened so far"),
    el("ul", { class: "trail" }, item.trail.map((t) =>
      el("li", {}, el("span", { class: "muted" }, `${when(t.at)} · ${t.actor} · ${t.step}: `), t.message))));
}

function decision(actions, onDecide) {
  const box = $("#decision-template").content.firstElementChild.cloneNode(true);
  const note = box.querySelector("textarea");
  const error = box.querySelector(".error");
  for (const [action, label, cls] of actions.filter(Boolean)) {
    box.querySelector(".actions").append(el("button", {
      class: cls || "",
      onclick: async () => {
        error.textContent = "";
        try {
          await onDecide(action, note.value.trim() || undefined);
          selected = null;
          fill($("#detail"), el("p", { class: "muted" }, `Done: ${label.toLowerCase()}.`));
          loadQueue();
        } catch (err) {
          error.textContent = err.message;
        }
      },
    }, label));
  }
  return box;
}

function showStory(story, item) {
  const e = story.explanation;
  const tiers = story.translations.map((t) => badge(`${t.language} · tier ${t.tier}`, t.tier === 3 ? "tier3" : ""));
  const editor = el("textarea", { spellcheck: "false" });
  editor.value = JSON.stringify(story, null, 2);
  const editError = el("p", { class: "error" });

  fill($("#detail"), 
    el("h2", { dir: "auto" }, story.title.en),
    el("div", { class: "meta" },
      badge(story.status), badge(story.category), badge(story.scale), badge(story.placeId),
      story.risk !== "none" ? badge(`${story.risk} risk`, story.risk) : null,
      story.isOpinion ? badge("opinion") : null),
    el("div", { class: "meta" }, tiers),
    story.risk === "red" && story.translations.some((t) => t.tier === 3)
      ? el("p", { class: "error" }, "Red-risk: every tier-3 translation must be checked before this can be published.") : null,
    localized("For you", e.forYou),
    localized("What happened", e.happened),
    (e.known || []).length ? el("div", {}, el("h3", {}, "What is known"), e.known.map((k) => localized(null, k))) : null,
    localized("Not known yet", e.notKnown),
    el("h3", {}, "Sources"),
    el("ul", {}, story.sources.map((s) => el("li", {}, s.url ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.name) : s.name))),
    trail(item),
    decision([["approve", "Approve and publish", "primary"], ["sendBack", "Send back to agent"], ["reject", "Reject", "danger"]],
      (action, note) => api("POST", `/v1/admin/stories/${story.id}/decision`, { action, note })),
    el("details", { class: "json" },
      el("summary", {}, "Edit story (JSON)"),
      el("label", {}, "Full story, as in contract/schemas/story.schema.json", editor),
      el("button", {
        onclick: async () => {
          editError.textContent = "";
          try {
            const saved = await api("PATCH", `/v1/admin/stories/${story.id}`, JSON.parse(editor.value));
            showStory(saved, item);
          } catch (err) {
            editError.textContent = err.message;
          }
        },
      }, "Save changes"),
      editError),
  );
}

function showReport(report, story, item) {
  const loc = report.location;
  fill($("#detail"), 
    el("h2", {}, report.kind === "problem" ? "Reader flag on a story" : "News tip from a reader"),
    el("div", { class: "meta" },
      badge(report.status), badge(report.category),
      report.sensitive ? badge("sensitive", "red") : null,
      badge(`from ${report.reporterId}`)),
    el("h3", {}, "Report"),
    el("p", { class: "lang", dir: "auto" }, report.text),
    loc ? el("p", { class: "muted" },
      `Location: ${loc.coordinate.lat.toFixed(3)}, ${loc.coordinate.lon.toFixed(3)} (±${loc.radiusMeters} m) `,
      el("a", { href: `https://www.openstreetmap.org/?mlat=${loc.coordinate.lat}&mlon=${loc.coordinate.lon}#map=16/${loc.coordinate.lat}/${loc.coordinate.lon}`, target: "_blank", rel: "noopener" }, "map")) : null,
    story ? el("div", {}, el("h3", {}, "About this story"), el("p", { dir: "auto" }, `${story.title.en} (${story.id})`)) : null,
    report.sensitive ? el("p", { class: "error" }, "Sensitive: check with an official source before publishing.") : null,
    trail(item),
    decision([
      // Sensitive reports are never published: approving one only keeps it as a lead.
      report.sensitive ? null : ["approve", report.kind === "problem" ? "Mark story as fixed" : "Publish", "primary"],
      ["keepAsLead", "Keep as editor lead"],
      ["sendBack", "Send to agent"],
      ["reject", "Reject", "danger"],
    ], (action, note) => api("POST", `/v1/admin/reports/${report.id}/decision`, { action, note })),
  );
}

// ---- Audit ----

async function loadAudit() {
  const body = $("#audit");
  body.replaceChildren();
  try {
    for (const a of await api("GET", "/v1/admin/audit?limit=200")) {
      body.append(el("tr", {}, el("td", {}, when(a.at)), el("td", {}, a.actor), el("td", {}, a.step),
        el("td", {}, a.message), el("td", {}, a.storyId || a.reportId || "")));
    }
  } catch (err) {
    body.append(el("tr", {}, el("td", { colspan: "5", class: "error" }, err.message)));
  }
}

function show(view) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === view));
  $("#queue-view").hidden = view !== "queue";
  $("#audit-view").hidden = view !== "audit";
  if (view === "audit") loadAudit(); else loadQueue();
}

// ---- Start ----

$("#login-form").addEventListener("submit", signIn);
$("#sign-out").addEventListener("click", signOut);
$("#refresh").addEventListener("click", loadQueue);
$("#run-agent").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const r = await api("POST", "/v1/admin/agent/run");
    await loadQueue();
    $("#queue-count").textContent += ` · agent: ${r.queued} new drafts, ${r.published} published`;
  } catch (err) {
    $("#queue-count").textContent = err.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.view)));

(async () => {
  token = store("pinni-token");
  if (token) {
    try {
      const me = await api("GET", "/v1/me");
      if (STAFF.includes(me.role)) return start(me);
    } catch { /* fall through to sign in */ }
  }
  signOut();
})();
