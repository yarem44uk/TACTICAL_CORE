/* Tactical Core — Offline Operator UI
   Vanilla JavaScript. GET-only. No external libraries, no CDN, no telemetry.
   Consumes only the /api/v1/operator/* read-only API. */

"use strict";

var API = "/api/v1/operator";

/* ---- operator auth (WO-037-05) ------------------------------------------- */
/* The operator token is held in memory for the page session only. It is never
   written to localStorage/sessionStorage, never placed in a URL, and never
   logged. The password input is cleared immediately after Apply. */

var authToken = null;

function getAuthHeaders() {
  return authToken ? { "Authorization": "Bearer " + authToken } : {};
}

function withAuth(opts) {
  opts = opts || {};
  var headers = getAuthHeaders();
  if (opts.headers) {
    headers = Object.assign({}, opts.headers, headers);
  }
  opts.headers = headers;
  return opts;
}

function isAuthFailure(status) {
  return status === 401;
}

function showAuthRequired() {
  el("footer-status").textContent = "Authentication required — enter operator token";
}

function applyToken() {
  var t = el("token-input").value.trim();
  authToken = t || null;
  el("token-input").value = ""; // never leave the token visible in the DOM
  el("auth-btn").hidden = !!authToken;
  el("logout-btn").hidden = !authToken;
  el("footer-status").textContent = authToken
    ? "Authenticated — operator UI connected"
    : "No token — operator requests unauthenticated";
  loadHealth();
  switchView(el("view-events").classList.contains("active") ? "events" : "entities");
}

function logout() {
  authToken = null;
  el("auth-btn").hidden = false;
  el("logout-btn").hidden = true;
  el("footer-status").textContent = "Logged out — enter operator token";
  el("health-content").innerHTML = '<div class="detail-msg">Enter operator token to connect.</div>';
}

/* ---- shared helpers ------------------------------------------------------ */

function el(id) { return document.getElementById(id); }

function fmtTs(value) {
  if (!value) return "—";
  return String(value);
}

function showError(container, status, detail) {
  var msg;
  if (status === 404) msg = "Not found: " + (detail || "resource does not exist");
  else if (status === 503) msg = "Degraded: authoritative read dependency unavailable";
  else if (status === 400) msg = "Invalid request: " + (detail || "bad parameter");
  else if (status === 500) msg = "Server error: " + (detail || "internal operator error");
  else msg = "Request failed (HTTP " + status + ")";
  container.innerHTML = '<div class="detail-msg err">' + escapeHtml(msg) + "</div>";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

/* ---- health -------------------------------------------------------------- */

function loadHealth() {
  fetch(API + "/health", withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      var box = el("health-content");
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      var s = out.data;
      if (out.status !== 200) {
        box.innerHTML =
          '<div class="health-item"><span class="label">API</span>' +
          '<span class="badge err">Unavailable (HTTP ' + out.status + ")</span></div>";
        return;
      }
      var statusBadge = s.status === "ok"
        ? '<span class="badge ok">OK</span>'
        : '<span class="badge warn">' + escapeHtml(String(s.status)) + "</span>";
      box.innerHTML =
        '<div class="health-item"><span class="label">API</span>' + statusBadge + "</div>" +
        '<div class="health-item"><span class="label">Durable events</span>' +
          escapeHtml(String(s.durable_events)) + "</div>" +
        '<div class="health-item"><span class="label">Durable entities</span>' +
          escapeHtml(String(s.durable_entities)) + "</div>" +
        '<div class="health-item"><span class="label">Last ingestion</span>' +
          escapeHtml(String(s.last_ingestion)) + "</div>";
    })
    .catch(function (err) {
      el("health-content").innerHTML =
        '<div class="health-item"><span class="label">API</span>' +
        '<span class="badge err">Unavailable</span></div>';
    });
}

/* ---- events -------------------------------------------------------------- */

var evState = { cursor: null, hasPrev: false, hasNext: false };

function eventRow(ev) {
  return (
    '<div class="feed-item" data-eid="' + escapeHtml(ev.event_id) + '">' +
      '<div class="row-1"><span class="etype">' + escapeHtml(ev.event_type) + "</span>" +
        '<span class="eid">' + escapeHtml(ev.event_id) + "</span>" +
        '<span class="etime">' + fmtTs(ev.timestamp) + "</span></div>" +
      '<div class="row-2">source: ' + escapeHtml(ev.source) +
        " &middot; entity: " + escapeHtml(ev.entity_id || "—") +
        " &middot; status: " + escapeHtml(ev.event_status || "—") +
        " &middot; seq: " + escapeHtml(String(ev.seq !== undefined ? ev.seq : "—")) + "</div>" +
    "</div>"
  );
}

function loadEvents() {
  var params = [];
  var source = el("ev-source").value.trim();
  var type = el("ev-type").value.trim();
  var from = el("ev-from").value.trim();
  var to = el("ev-to").value.trim();
  if (source) params.push("source=" + encodeURIComponent(source));
  if (type) params.push("event_type=" + encodeURIComponent(type));
  if (from) params.push("from_time=" + encodeURIComponent(from));
  if (to) params.push("to_time=" + encodeURIComponent(to));
  params.push("limit=50");
  if (evState.cursor !== null) params.push("cursor=" + evState.cursor);
  fetch(API + "/events?" + params.join("&"), withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      var feed = el("event-feed");
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      if (out.status !== 200) {
        evState.hasNext = false;
        evState.hasPrev = false;
        showError(feed, out.status, out.data.detail);
        updateEventPager();
        return;
      }
      var events = out.data.events || [];
      if (events.length === 0) {
        feed.innerHTML = '<div class="detail-msg">No events.</div>';
      } else {
        feed.innerHTML = events.map(eventRow).join("");
        Array.prototype.forEach.call(feed.querySelectorAll(".feed-item"), function (node) {
          node.addEventListener("click", function () {
            openEventDetail(node.getAttribute("data-eid"));
          });
        });
      }
      var nc = out.data.next_cursor;
      evState.hasNext = nc !== null && nc !== undefined;
      evState.hasPrev = evState.cursor !== null;
      updateEventPager();
    })
    .catch(function () {
      evState.hasNext = false;
      evState.hasPrev = false;
      el("event-feed").innerHTML = '<div class="detail-msg err">Unavailable</div>';
      updateEventPager();
    });
}

function updateEventPager() {
  el("ev-prev").disabled = !evState.hasPrev;
  el("ev-next").disabled = !evState.hasNext;
}

function openEventDetail(eventId) {
  fetch(API + "/events/" + encodeURIComponent(eventId), withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      el("detail-title").textContent = "Event " + eventId;
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      if (out.status === 404) {
        el("detail-body").innerHTML = '<div class="detail-msg err">Not found: event does not exist</div>';
      } else if (out.status !== 200) {
        el("detail-body").innerHTML = '<div class="detail-msg err">Error (HTTP ' + out.status + ")</div>";
      } else {
        el("detail-body").innerHTML = "<pre class=\"json\">" + escapeHtml(JSON.stringify(out.data, null, 2)) + "</pre>";
      }
      el("detail-modal").hidden = false;
    })
    .catch(function () {
      el("detail-title").textContent = "Event " + eventId;
      el("detail-body").innerHTML = '<div class="detail-msg err">Unavailable</div>';
      el("detail-modal").hidden = false;
    });
}

/* ---- entities ------------------------------------------------------------ */

function entityRow(en) {
  return (
    '<div class="feed-item" data-eid="' + escapeHtml(en.entity_id) + '">' +
      '<div class="row-1"><span class="etype">' + escapeHtml(en.entity_type) + "</span>" +
        '<span class="eid">' + escapeHtml(en.entity_id) + "</span></div>" +
      '<div class="row-2">status: ' + escapeHtml(en.status || "—") +
        " &middot; version: " + escapeHtml(String(en.version !== undefined ? en.version : "—")) +
        " &middot; updated: " + fmtTs(en.updated_at) + "</div>" +
    "</div>"
  );
}

function loadEntities() {
  var params = [];
  var type = el("en-type").value.trim();
  if (type) params.push("entity_type=" + encodeURIComponent(type));
  fetch(API + "/entities" + (params.length ? "?" + params.join("&") : ""), withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      var list = el("entity-list");
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      if (out.status !== 200) {
        showError(list, out.status, out.data.detail);
        return;
      }
      var entities = out.data.entities || [];
      if (entities.length === 0) {
        list.innerHTML = '<div class="detail-msg">No entities.</div>';
      } else {
        list.innerHTML = entities.map(entityRow).join("");
        Array.prototype.forEach.call(list.querySelectorAll(".feed-item"), function (node) {
          node.addEventListener("click", function () {
            openEntityDetail(node.getAttribute("data-eid"));
          });
        });
      }
    })
    .catch(function () {
      el("entity-list").innerHTML = '<div class="detail-msg err">Unavailable</div>';
    });
}

function openEntityDetail(entityId) {
  fetch(API + "/entities/" + encodeURIComponent(entityId), withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      if (out.status === 404) {
        el("detail-title").textContent = "Entity " + entityId;
        el("detail-body").innerHTML = '<div class="detail-msg err">Not found: entity does not exist</div>';
        el("detail-modal").hidden = false;
        return;
      }
      if (out.status !== 200) {
        el("detail-title").textContent = "Entity " + entityId;
        el("detail-body").innerHTML = '<div class="detail-msg err">Error (HTTP ' + out.status + ")</div>";
        el("detail-modal").hidden = false;
        return;
      }
      var entity = out.data.entity || {};
      var fields = [
        ["entity_id", entity.entity_id],
        ["entity_type", entity.entity_type],
        ["status", entity.status],
        ["version", entity.version],
        ["created_at", entity.created_at],
        ["updated_at", entity.updated_at]
      ];
      var rows = fields
        .map(function (f) {
          return "<tr><th>" + escapeHtml(f[0]) + "</th><td>" + escapeHtml(String(f[1] !== undefined ? f[1] : "—")) + "</td></tr>";
        })
        .join("");
      el("detail-title").textContent = "Entity " + entityId;
      el("detail-body").innerHTML =
        "<table class=\"table\">" + rows + "</table>" +
        "<h3>Relations</h3><div id=\"entity-relations\">Loading…</div>";
      loadRelations(entityId, entity.entity_type, entity.status, entity.version, entity.created_at, entity.updated_at);
      el("detail-modal").hidden = false;
    })
    .catch(function () {
      el("detail-title").textContent = "Entity " + entityId;
      el("detail-body").innerHTML = '<div class="detail-msg err">Unavailable</div>';
      el("detail-modal").hidden = false;
    });
}

function loadRelations(entityId, etype, status, version, createdAt, updatedAt) {
  fetch(API + "/entities/" + encodeURIComponent(entityId) + "/relations", withAuth({ method: "GET" }))
    .then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    })
    .then(function (out) {
      var box = el("entity-relations");
      if (!box) return;
      if (isAuthFailure(out.status)) { showAuthRequired(); return; }
      if (out.status !== 200) {
        box.innerHTML = '<div class="detail-msg err">Error (HTTP ' + out.status + ")</div>";
        return;
      }
      var rels = out.data.relations || [];
      if (rels.length === 0) {
        box.innerHTML = '<div class="detail-msg">No relations.</div>';
        return;
      }
      var head =
        "<tr><th>relation_id</th><th>relation_type</th><th>source</th><th>target</th>" +
        "<th>confidence</th><th>status</th><th>source_event_id</th><th>created</th></tr>";
      var rows = rels
        .map(function (r) {
          return (
            "<tr><td>" + escapeHtml(r.relation_id) + "</td>" +
            "<td>" + escapeHtml(r.relation_type) + "</td>" +
            "<td>" + escapeHtml(r.source_entity_id) + "</td>" +
            "<td>" + escapeHtml(r.target_entity_id) + "</td>" +
            "<td>" + escapeHtml(String(r.confidence !== undefined ? r.confidence : "—")) + "</td>" +
            "<td>" + escapeHtml(r.status || "—") + "</td>" +
            "<td>" + escapeHtml(r.source_event_id || "—") + "</td>" +
            "<td>" + fmtTs(r.created_at) + "</td></tr>"
          );
        })
        .join("");
      box.innerHTML = "<table class=\"table\">" + head + rows + "</table>";
    })
    .catch(function () {
      var box = el("entity-relations");
      if (box) box.innerHTML = '<div class="detail-msg err">Unavailable</div>';
    });
}

/* ---- navigation / wiring ------------------------------------------------- */

function switchView(name) {
  var events = name === "events";
  el("view-events").classList.toggle("active", events);
  el("view-entities").classList.toggle("active", !events);
  el("tab-events").classList.toggle("active", events);
  el("tab-entities").classList.toggle("active", !events);
  if (events) loadEvents();
  else loadEntities();
}

function wire() {
  el("auth-btn").addEventListener("click", applyToken);
  el("logout-btn").addEventListener("click", logout);
  el("token-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { applyToken(); }
  });
  el("tab-events").addEventListener("click", function () { switchView("events"); });
  el("tab-entities").addEventListener("click", function () { switchView("entities"); });
  el("refresh-btn").addEventListener("click", function () {
    loadHealth();
    if (el("view-events").classList.contains("active")) loadEvents();
    else loadEntities();
  });
  el("ev-apply").addEventListener("click", function () {
    evState.cursor = null;
    loadEvents();
  });
  el("ev-prev").addEventListener("click", function () {
    // Keyset pagination only supports forward (next_cursor). Previous page is
    // not available via the read-only API without offsetting, which is not
    // supported against the durable event table.
  });
  el("ev-next").addEventListener("click", function () {
    if (evState.hasNext) loadEvents();
  });
  el("en-apply").addEventListener("click", function () { loadEntities(); });
  el("detail-close").addEventListener("click", function () {
    el("detail-modal").hidden = true;
  });
  el("detail-modal").addEventListener("click", function (e) {
    if (e.target === el("detail-modal")) el("detail-modal").hidden = true;
  });
}

wire();
loadHealth();
switchView("events");
