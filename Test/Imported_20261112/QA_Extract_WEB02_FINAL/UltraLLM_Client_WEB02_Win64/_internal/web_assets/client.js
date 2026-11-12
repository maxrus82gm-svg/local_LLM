"use strict";
// Frontend never receives or stores Manager bearer tokens. All TLS and
// authorization happen inside the local Python Web Client process.
const byId = id => document.getElementById(id);
const dialog = byId("setup");
let csrf = "";
let isRefreshing = false;
let firstSetup = false;

function node(tag, className, text) {
  const x = document.createElement(tag);
  if (className) x.className = className;
  if (text !== undefined && text !== null) x.textContent = String(text);
  return x;
}
function formatNumber(x) { return typeof x === "number" && Number.isFinite(x) ? x.toFixed(1) : "—"; }
function stateLabel(value) {
  const labels = {
    ready: "Работает", not_running: "Не запущена",
    stopped: "Остановлена", unknown: "Неизвестно",
    busy: "Занята", denied: "Нет доступа",
    ready_unreserved: "Возможен запрос", requestable: "Возможен запрос"
  };
  return labels[value] || (typeof value === "string" ? value : "Неизвестно");
}
function severity(value) {
  if (value === "ready" || value === "ready_unreserved") return "ready";
  if (value === "denied") return "denied";
  if (value === "busy") return "busy";
  return "";
}
function labelState(value) {
  return node("span", "state " + severity(value), stateLabel(value));
}
function setNotice(value) {
  const el = byId("notice");
  el.textContent = value || "";
  el.classList.toggle("hidden", !value);
}
async function api(endpoint, options) {
  const response = await fetch(endpoint, Object.assign({cache:"no-store"}, options || {}));
  let data;
  try { data = await response.json(); } catch { throw Error("Некорректный ответ локального клиента"); }
  if (!response.ok) throw Error(data.error || "Ошибка: " + response.status);
  return data;
}
function showSetup() {
  byId("setup-error").classList.add("hidden");
  byId("setup-form").classList.remove("hidden");
  byId("setup-success").classList.add("hidden");
  if (!dialog.open) dialog.showModal();
}
function closeSetup() {
  if (dialog.open) dialog.close();
}
function stat(id, value) { byId(id).textContent = String(value); }
function modelList(container, models, disk) {
  const wrap = node("div", "models-list");
  wrap.append(node("h3", "", "ДОСТУПНЫЕ МОДЕЛИ И КАТАЛОГИ"));
  if (!models.length && !disk.length) {
    wrap.append(node("div", "model-item", "Модели не обнаружены или нет прав"));
    container.append(wrap);
    return;
  }
  for (const model of models) {
    const line = node("div", "model-item");
    line.append(node("span", "model-label", model), node("small", "", "API · подключена"));
    wrap.append(line);
  }
  for (const item of disk) {
    if (!item || typeof item.directory_name !== "string") continue;
    const line = node("div", "model-item");
    line.append(node("span", "model-label", item.directory_name),
                node("small", "", "Файлы на диске · не проверены"));
    wrap.append(line);
  }
  container.append(wrap);
}
function makeManager(row) {
  const online = row.status === "online";
  const card = node("article", "manager");
  const top = node("div", "manager-top");
  top.append(node("span", "server-icon", "▣"));
  const heading = node("div");
  heading.append(node("div", "manager-name", row.name || row.manager_id || "Manager"));
  heading.append(node("div", "manager-host", online ?
      (row.data.host || row.endpoint) : row.endpoint));
  top.append(heading);
  top.append(node("span", "status-pill" + (online ? "" : " offline"), online ? "● ONLINE" : "● OFFLINE"));
  card.append(top);
  const body = node("div", "manager-body");
  if (!online) {
    const err = row.error === "unauthorized" ? "Ожидается регистрация или токен отозван" :
      row.error === "http_403" ? "Этот компьютер не разрешён на Manager" :
      "Нет соединения или ошибка настройки";
    body.append(node("p", "", err));
    card.append(body);
    return card;
  }
  const data = row.data || {};
  const slots = Array.isArray(data.slots) ? data.slots : [];
  const ram = data.memory || {};
  const stats = node("div", "server-stats");
  for (const [name, val] of [
    ["СВОБОДНАЯ RAM", ram.state === "live" ? formatNumber(ram.free_gib) + " GiB" : "—"],
    ["СЛОТОВ", String(slots.length)]]) {
    const cell = node("div");
    cell.append(node("small", "", name), node("strong", "", val));
    stats.append(cell);
  }
  body.append(stats);
  const confirmed = [...new Set(slots.flatMap(s => Array.isArray(s.models) ? s.models : []))];
  modelList(body, confirmed, Array.isArray(data.models) ? data.models : []);
  card.append(body);
  return card;
}
function makeRow(manager, slot) {
  const tr = node("tr");
  for (const value of [manager.name || manager.manager_id,
      slot.slot_id || "—",
      (Array.isArray(slot.models) && slot.models.length ? slot.models.join(", ") : "—")]) {
    tr.append(node("td", "", value));
  }
  const engine = node("td"); engine.append(labelState(slot.engine_state)); tr.append(engine);
  const available = node("td"); available.append(labelState(slot.availability)); tr.append(available);
  const action = node("td");
  const disabled = node("button", "no-actions", "START / STOP скоро");
  disabled.disabled = true; disabled.title = "Управление моделями будет реализовано в следующем этапе";
  action.append(disabled);tr.append(action);
  return tr;
}
function render(payload) {
  const all = Array.isArray(payload.managers) ? payload.managers : [];
  const online = all.filter(x => x.status === "online");
  const models = new Set();
  let ready = 0, ram = 0, ramHosts = 0;
  const grid = byId("managers");grid.replaceChildren();
  const table = byId("slot-table");table.replaceChildren();
  for (const manager of all) {
    grid.append(makeManager(manager));
    if (manager.status !== "online" || !manager.data) continue;
    const data = manager.data;
    const slots = Array.isArray(data.slots) ? data.slots : [];
    for (const slot of slots) {
      table.append(makeRow(manager, slot));
      if (slot.engine_state === "ready") {
        for (const model of (slot.models || [])) models.add(manager.manager_id + ":" + model);
      }
      if (slot.availability === "ready_unreserved") ready += 1;
    }
    if (data.memory && data.memory.state === "live" &&
        typeof data.memory.free_gib === "number") {
      ram += data.memory.free_gib;ramHosts++;
    }
  }
  if (!all.length) grid.append(node("div", "placeholder", "Нет подключённых менеджеров. Нажмите «Подключить сервер», чтобы начать."));
  if (!table.children.length) {
    const tr = node("tr");const td = node("td", "empty", "Нет доступных данных о слотах");
    td.colSpan = 6;tr.append(td);table.append(tr);
  }
  stat("metric-manager", all.length);
  stat("online-note", online.length + " онлайн из " + all.length);
  stat("metric-models", models.size);
  stat("metric-ready", ready);
  stat("metric-ram", ramHosts ? formatNumber(ram) + " GiB" : "—");
  stat("server-count", all.length + " серверов");
  stat("last-update", new Date().toLocaleTimeString("ru-RU", {hour:"2-digit",minute:"2-digit"}));
  setNotice(all.some(m => m.status !== "online") ?
      "Не все Manager доступны. Проверьте сеть, сертификат и регистрацию этого компьютера." : "");
}
async function refresh() {
  if (isRefreshing) return;
  isRefreshing = true;
  const button = byId("refresh"); button.disabled = true;
  try {
    render(await api("/api/status"));
  } catch (err) {
    setNotice("Не удалось обновить данные: " + err.message);
  } finally {
    isRefreshing = false;
    button.disabled = false;
  }
}
async function init() {
  try {
    csrf = (await api("/api/session")).csrf;
    const cfg = await api("/api/config");
    if (!cfg.configured) { firstSetup = true; showSetup(); }
  } catch (e) {
    setNotice("Ошибка первоначальной настройки: " + e.message);
  }
  await refresh();
}

byId("add").addEventListener("click", showSetup);
byId("nav-add").addEventListener("click", showSetup);
byId("refresh").addEventListener("click", refresh);
byId("quit-client").addEventListener("click", async () => {
  if (!confirm("Завершить только локальный Web Client? Работа Manager и Colibri не изменится.")) return;
  try {
    await api("/api/shutdown", {
      method:"POST",headers:{"X-Ultra-CSRF":csrf,"Content-Type":"application/json"}
    });
    document.body.replaceChildren(node("div", "placeholder",
      "Ultra LLM Web Client завершён. Эту вкладку можно закрыть. Manager продолжает работать."));
    document.body.style.padding = "15vh 8vw";
  } catch (err) {
    setNotice("Не удалось завершить клиент: " + err.message);
  }
});
byId("close-setup").addEventListener("click", closeSetup);
byId("cancel-setup").addEventListener("click", closeSetup);
byId("setup-done").addEventListener("click", () => { closeSetup();refresh(); });
byId("cert-file").addEventListener("change", async event => {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  if (file.size > 16000) {
    byId("setup-error").textContent = "Сертификат слишком большой";
    byId("setup-error").classList.remove("hidden");return;
  }
  byId("cert-pem").value = await file.text();
});
byId("copy-digest").addEventListener("click", async () => {
  const value = byId("digest").textContent;
  try {
    await navigator.clipboard.writeText(value);
    byId("copy-digest").textContent = "Скопировано ✓";
  } catch {
    byId("copy-digest").textContent = "Выделите и скопируйте хеш";
  }
});
byId("setup-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  data.port = Number(data.port);
  const submit = byId("setup-save");submit.disabled = true;
  const error = byId("setup-error");error.classList.add("hidden");
  try {
    const result = await api("/api/enroll", {
      method: "POST",
      headers: {"Content-Type":"application/json","X-Ultra-CSRF":csrf},
      body: JSON.stringify(data)
    });
    byId("digest").textContent = result.registration_sha256;
    byId("fingerprint").textContent = result.certificate_sha256;
    byId("client-label").textContent = result.client_id;
    form.classList.add("hidden");
    byId("setup-success").classList.remove("hidden");
    firstSetup = false;
  } catch (e) {
    error.textContent = "Не удалось создать профиль: " + e.message;
    error.classList.remove("hidden");
  } finally { submit.disabled = false; }
});
init();
setInterval(refresh, 25000);
