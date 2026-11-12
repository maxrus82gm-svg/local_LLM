"use strict";
// Frontend never receives or stores Manager bearer tokens. All TLS and
// authorization happen inside the local Python Web Client process.
const byId = id => document.getElementById(id);
const dialog = byId("setup");
const adminDialog = byId("admin-dialog");
let csrf = "";
let isRefreshing = false;
let firstSetup = false;
let lastEnrolledManagerId = "";
let adminManagers = [];

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
    const states = {
      pending: "Заявка отправлена — ожидает подтверждения администратора",
      approved: "Заявка подтверждена; обновите соединение",
      denied: "Администратор отклонил заявку",
      expired: "Срок действия заявки истёк",
      unknown: "Статус заявки пока неизвестен"
    };
    if (row.pairing_state) body.append(node("p", "manager-pairing-note",
      states[row.pairing_state] || "Требуется подтверждение"));
    if (row.pairing_state !== "pending" && row.error !== "http_403") {
      const retry = node("button", "btn secondary manager-pairing-retry", "↻ Отправить заявку снова");
      retry.type = "button";
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        try {
          const result = await pairingPost("/api/pairing/retry",
            {manager_id: row.manager_id});
          setNotice(result.state === "pending" ?
            "Заявка отправлена. Теперь администратор Manager должен её одобрить." :
            "Не удалось подтвердить отправку");
          await refresh();
        } catch (error) {
          setNotice("Заявка не отправлена: " + pairingError(error.message));
        } finally { retry.disabled = false; }
      });
      body.append(retry);
    }
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
  adminManagers = online.filter(x => x.data && x.data.pairing_admin === true)
                        .map(x => ({manager_id:x.manager_id,
                                    name:x.name || x.manager_id}));
  const adminButton = byId("nav-pairing-admin");
  adminButton.classList.toggle("hidden", !adminManagers.length);
  const adminSelect = byId("admin-manager");
  const selected = adminSelect.value;
  adminSelect.replaceChildren();
  for (const item of adminManagers) {
    const option = node("option", "", item.name);
    option.value = item.manager_id;
    adminSelect.append(option);
  }
  if (adminManagers.some(x => x.manager_id === selected)) adminSelect.value = selected;
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

function pairingError(error) {
  const hints = {
    manager_upgrade_required: "На сервере пока старая версия Manager без веб-регистрации",
    manager_unreachable_or_untrusted: "Нет доверенного HTTPS-соединения с Manager",
    access_denied: "IP этого компьютера пока не разрешён администратором",
    rate_limited: "Слишком много запросов. Попробуйте позже",
    request_conflict: "Такая заявка уже есть. Дождитесь решения или истечения срока",
    pairing_admin_required_or_offline: "Этот клиент не имеет административных прав на Manager",
    grant_not_applied: "Разрешение не применено. Проверьте права и IP/слоты на Manager"
  };
  return hints[error] || error;
}
function pairingPost(url, body) {
  return api(url, {
    method:"POST",
    headers:{"Content-Type":"application/json","X-Ultra-CSRF":csrf},
    body:JSON.stringify(body)
  });
}
async function showAdmin() {
  if (!adminManagers.length) return;
  if (!adminDialog.open) adminDialog.showModal();
  await refreshAdmin();
}
async function refreshAdmin() {
  const mid = byId("admin-manager").value;
  const list = byId("admin-requests");
  list.replaceChildren(node("div", "placeholder", "Получаем заявки…"));
  const notice = byId("admin-error");
  notice.classList.add("hidden");
  if (!mid) return;
  try {
    const data = await api("/api/pairing/admin?manager_id="+encodeURIComponent(mid));
    const slots = Array.isArray(data.slots) ? data.slots : [];
    const requests = Array.isArray(data.requests) ? data.requests : [];
    list.replaceChildren();
    if (!requests.length) list.append(node("div", "placeholder", "Новых заявок пока нет."));
    for (const item of requests) {
      const card = node("div", "request-card");
      const title = node("div", "request-header");
      title.append(node("b", "", item.client_id), node("span", "state busy", "Ожидает"));
      card.append(title);
      const meta = node("div", "request-meta",
        "Источник: " + item.source_ip + " · осталось " +
        Math.max(0, Math.floor(Number(item.expires_in_seconds) / 60)) + " мин.");
      card.append(meta);
      const group = node("div", "request-options");
      for (const slot of slots) {
        const label = node("label", "slot-checkbox");
        const cb = node("input");
        cb.type = "checkbox";
        cb.value = slot.slot_id;
        label.append(cb, node("span", "", slot.slot_id +
          (slot.protected ? " · защищённый" : "")));
        group.append(label);
      }
      card.append(node("div", "eyebrow", "РАЗРЕШИТЬ СЛОТЫ"));
      card.append(group);
      const warning = node("p", "request-warning",
        "Одобрение даёт только доступ к просмотру разрешённых слотов — START/STOP пока отключены.");
      card.append(warning);
      const actions = node("div", "request-actions");
      const approve = node("button", "btn primary", "✓ Разрешить");
      const deny = node("button", "btn secondary", "✕ Отклонить");
      approve.type = deny.type = "button";
      approve.addEventListener("click", async () => {
        const chosen = [...group.querySelectorAll("input:checked")].map(x => x.value);
        if (!confirm("Одобрить " + item.client_id + " с доступом к: " +
              (chosen.join(", ") || "без слотов") + "?")) return;
        approve.disabled = deny.disabled = true;
        try {
          await pairingPost("/api/pairing/approve",
            {manager_id:mid,ticket_id:item.ticket_id,allowed_slots:chosen});
          await refreshAdmin();
        } catch (error) {
          notice.textContent = "Не удалось одобрить: " + pairingError(error.message);
          notice.classList.remove("hidden");
          approve.disabled = deny.disabled = false;
        }
      });
      deny.addEventListener("click", async () => {
        if (!confirm("Отклонить заявку " + item.client_id + "?")) return;
        approve.disabled = deny.disabled = true;
        try {
          await pairingPost("/api/pairing/deny",
            {manager_id:mid,ticket_id:item.ticket_id});
          await refreshAdmin();
        } catch (error) {
          notice.textContent = pairingError(error.message);
          notice.classList.remove("hidden");
          approve.disabled = deny.disabled = false;
        }
      });
      actions.append(approve, deny);
      card.append(actions);
      list.append(card);
    }
  } catch (error) {
    list.replaceChildren();
    notice.textContent = pairingError(error.message);
    notice.classList.remove("hidden");
  }
}

byId("nav-pairing-admin").addEventListener("click", showAdmin);
byId("close-admin").addEventListener("click", () => adminDialog.close());
byId("admin-done").addEventListener("click", () => adminDialog.close());
byId("admin-manager").addEventListener("change", refreshAdmin);
byId("refresh-admin").addEventListener("click", refreshAdmin);
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
byId("retry-pairing").addEventListener("click", async () => {
  const button = byId("retry-pairing");
  if (!lastEnrolledManagerId) return;
  button.disabled = true;
  try {
    const result = await pairingPost("/api/pairing/retry",
      {manager_id:lastEnrolledManagerId});
    if (result.state === "pending") {
      byId("setup-state").textContent =
        "Заявка доставлена Manager и ожидает подтверждения администратора.";
      byId("legacy-digest").classList.add("hidden");
    }
  } catch (error) {
    byId("setup-state").textContent = pairingError(error.message);
  } finally {button.disabled = false;}
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
    lastEnrolledManagerId = result.manager_id;
    byId("digest").textContent = result.registration_sha256;
    byId("fingerprint").textContent = result.certificate_sha256;
    byId("client-label").textContent = result.client_id;
    const sent = result.state === "pending";
    byId("setup-state").textContent = sent ?
      "Заявка по HTTPS отправлена Manager. Ожидайте подтверждения администратора." :
      "Профиль создан, но заявка пока не доставлена: " +
      pairingError(result.reason || "manager_unreachable_or_untrusted") +
      ". Повторите отправку после настройки Manager.";
    byId("legacy-digest").classList.toggle("hidden", sent);
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
