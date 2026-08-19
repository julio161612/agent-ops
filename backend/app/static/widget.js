/**
 * Agent Ops embeddable chat widget — standalone vanilla JS, no build step.
 *
 * Usage (paste on any page):
 *   <script src="https://<your-agent-ops-host>/widget.js"
 *           data-api-key="ao_pk_..."
 *           data-api-url="https://<your-agent-ops-host>"></script>
 *
 * data-api-key MUST be a WIDGET-type key (prefix ao_pk_) — it ends up in
 * public page source, so it is deliberately restricted server-side to only
 * ever be able to send messages (see require_send_message_key /
 * require_server_key in app/api/deps.py). Never put a server key (ao_sk_)
 * here.
 *
 * Not styled beyond "functional and legible" — Phase 11 (frontend) is where
 * this gets a real design pass. This phase's bar is: it actually talks to
 * the real backend and works.
 */
(function () {
  "use strict";

  var scriptTag = document.currentScript;
  var apiKey = scriptTag.getAttribute("data-api-key");
  var apiUrl = (scriptTag.getAttribute("data-api-url") || "").replace(/\/+$/, "");
  var title = scriptTag.getAttribute("data-title") || "Chat";

  if (!apiKey) {
    console.error("[agentops-widget] missing data-api-key on the <script> tag — widget disabled.");
    return;
  }
  if (!apiUrl) {
    console.error("[agentops-widget] missing data-api-url on the <script> tag — widget disabled.");
    return;
  }

  var STORAGE_SESSION_KEY = "agentops_widget_session_id";
  var STORAGE_USER_KEY = "agentops_widget_external_user_id";
  var STORAGE_HISTORY_KEY = "agentops_widget_history";

  function uuid4() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getExternalUserId() {
    var id = localStorage.getItem(STORAGE_USER_KEY);
    if (!id) {
      id = "widget-" + uuid4();
      localStorage.setItem(STORAGE_USER_KEY, id);
    }
    return id;
  }

  function getSessionId() {
    return localStorage.getItem(STORAGE_SESSION_KEY) || null;
  }

  function setSessionId(sessionId) {
    localStorage.setItem(STORAGE_SESSION_KEY, sessionId);
  }

  function loadHistory() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_HISTORY_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function saveHistory(history) {
    localStorage.setItem(STORAGE_HISTORY_KEY, JSON.stringify(history));
  }

  // --- UI ---------------------------------------------------------------

  var bubble = document.createElement("button");
  bubble.textContent = "💬";
  bubble.setAttribute("aria-label", "Open chat");
  Object.assign(bubble.style, {
    position: "fixed",
    bottom: "20px",
    right: "20px",
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    border: "none",
    background: "#4f46e5",
    color: "#fff",
    fontSize: "24px",
    cursor: "pointer",
    boxShadow: "0 2px 10px rgba(0,0,0,0.25)",
    zIndex: 999999,
  });

  var panel = document.createElement("div");
  Object.assign(panel.style, {
    position: "fixed",
    bottom: "88px",
    right: "20px",
    width: "320px",
    height: "440px",
    background: "#fff",
    border: "1px solid #ddd",
    borderRadius: "8px",
    boxShadow: "0 4px 20px rgba(0,0,0,0.25)",
    display: "none",
    flexDirection: "column",
    fontFamily: "system-ui, sans-serif",
    fontSize: "14px",
    overflow: "hidden",
    zIndex: 999999,
  });

  var header = document.createElement("div");
  header.textContent = title;
  Object.assign(header.style, {
    background: "#4f46e5",
    color: "#fff",
    padding: "10px 12px",
    fontWeight: "600",
  });

  var messagesEl = document.createElement("div");
  Object.assign(messagesEl.style, {
    flex: "1",
    overflowY: "auto",
    padding: "10px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  });

  var statusEl = document.createElement("div");
  Object.assign(statusEl.style, {
    padding: "0 10px",
    color: "#b91c1c",
    fontSize: "12px",
    minHeight: "16px",
  });

  var inputRow = document.createElement("div");
  Object.assign(inputRow.style, {
    display: "flex",
    borderTop: "1px solid #eee",
    padding: "8px",
    gap: "6px",
  });

  var input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Escribe un mensaje...";
  Object.assign(input.style, {
    flex: "1",
    border: "1px solid #ccc",
    borderRadius: "4px",
    padding: "8px",
  });

  var sendBtn = document.createElement("button");
  sendBtn.textContent = "Enviar";
  Object.assign(sendBtn.style, {
    background: "#4f46e5",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    padding: "8px 12px",
    cursor: "pointer",
  });

  inputRow.appendChild(input);
  inputRow.appendChild(sendBtn);
  panel.appendChild(header);
  panel.appendChild(messagesEl);
  panel.appendChild(statusEl);
  panel.appendChild(inputRow);

  document.body.appendChild(bubble);
  document.body.appendChild(panel);

  function renderMessage(role, content) {
    var row = document.createElement("div");
    Object.assign(row.style, {
      alignSelf: role === "user" ? "flex-end" : "flex-start",
      background: role === "user" ? "#4f46e5" : "#f1f1f1",
      color: role === "user" ? "#fff" : "#111",
      borderRadius: "10px",
      padding: "8px 10px",
      maxWidth: "80%",
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
    });
    row.textContent = content;
    messagesEl.appendChild(row);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function renderHistory() {
    messagesEl.innerHTML = "";
    loadHistory().forEach(function (m) {
      renderMessage(m.role, m.content);
    });
  }

  var open = false;
  bubble.addEventListener("click", function () {
    open = !open;
    panel.style.display = open ? "flex" : "none";
  });

  async function sendMessage(content) {
    statusEl.textContent = "";
    sendBtn.disabled = true;

    var history = loadHistory();
    history.push({ role: "user", content: content });
    saveHistory(history);
    renderMessage("user", content);

    try {
      var response = await fetch(apiUrl + "/public/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify({
          content: content,
          session_id: getSessionId(),
          external_user_id: getExternalUserId(),
        }),
      });

      if (!response.ok) {
        var errBody = await response.json().catch(function () {
          return {};
        });
        statusEl.textContent = "Error: " + (errBody.detail || response.status);
        return;
      }

      var data = await response.json();
      setSessionId(data.session_id);

      if (data.reply) {
        var updated = loadHistory();
        updated.push({ role: "assistant", content: data.reply });
        saveHistory(updated);
        renderMessage("assistant", data.reply);
      } else {
        statusEl.textContent = "Sin agente disponible todavía — un humano revisará tu mensaje.";
      }
    } catch (err) {
      statusEl.textContent = "No se pudo conectar con el servidor.";
    } finally {
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", function () {
    var content = input.value.trim();
    if (!content) return;
    input.value = "";
    sendMessage(content);
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      sendBtn.click();
    }
  });

  renderHistory();
})();
