"use strict";
// Frontend never receives or stores Manager bearer tokens. All TLS and
// authorization happen inside the local Python Web Client process.
const byId = id => document.getElementById(id);
const dialog = byId("setup");
const adminDialog = byId("admin-dialog");
let csrf = "";
let isRefreshing = false;
let refreshQueued = false;
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
function controlReason(reason) {
  const labels = {
    resource_risk_not_permitted:"На сервере не разрешено подтверждать ресурсные риски",
    requested_output_exceeds_engine_limit:"Запрошенный выход превышает фактический лимит движка; проверьте параметры Colibri",
    colibri_request_rejected:"Движок отклонил параметры или размер контекста",
    risk_ack_required:"Необходимо явно подтвердить ресурсный прогноз",
    risk_confirmation_stale:"Состояние ресурсов изменилось; повторите проверку",
    slot_selection_changed:"Выбор в слоте изменился другим запросом; обновите данные",
    slot_in_use:"В слоте есть действующий или неподтверждённый экземпляр",
    owner_go_required:"Владелец ещё не разрешил управление на сервере",
    control_models_required:"Клиенту не выдано право управления моделями",
    runtime_review_required:"Совместимость runtime и ресурсный профиль ещё не подтверждены",
    runtime_or_model_changed:"Файлы runtime или метаданные модели изменились после проверки",
    resource_telemetry_unknown:"Нет достоверных данных о памяти и процессах сервера",
    vram_telemetry_unknown:"Нет достоверных данных о свободной VRAM",
    insufficient_ram:"Недостаточно свободной RAM с учётом резерва",
    insufficient_vram:"Недостаточно свободной VRAM с учётом резерва",
    cuda_measurement_unverified:"Потребление VRAM этой моделью ещё не измерено",
    model_already_managed:"Для модели уже зарезервирован экземпляр",
    no_free_authorized_slot:"Нет свободного разрешённого слота",
    model_not_authorized:"Эта модель не разрешена клиенту",
    instance_not_authorized:"Экземпляр принадлежит другому клиенту или слот не разрешён",
    runner_action_unconfirmed:"Результат операции не подтверждён; слот защищён от повторного запуска",
    supervisor_unverified:"Владение процессом не подтверждено",
    runtime_or_telemetry_unverified:"Runtime или состояние сервера не подтверждены"
  };
  return labels[reason] ? labels[reason] + " (" + reason + ")" : reason;
}
const slotPending=new Set();
function workspaces(container,manager) {
  const control=manager.data.control;
  const catalog=node("section","slot-catalog");
  catalog.append(node("h3","","КАТАЛОГ МОДЕЛЕЙ"));
  const known=new Set();
  for(const model of control.models || []) {
    if(model.directory_name)known.add(model.directory_name);
    const entry=node("div","catalog-entry");
    entry.append(node("strong","",model.name),node("small","",
      [model.files_present ? "Файлы обнаружены" : "Наличие файлов не подтверждено",
       model.runtime_checked ? "Runtime проверен" : "Совместимость требует проверки",
       "Доступен старт: "+["cpu","cuda"].filter(mode=>model.modes?.[mode]?.available).map(mode=>mode.toUpperCase()).join(" / ")+(Object.values(model.modes || {}).some(m=>m.available) ? "" : "требуется допуск"),
       "Работает экземпляров: "+(model.running_instances || 0)].join(" · ")));
    catalog.append(entry);
  }
  for(const disk of manager.data.models || []) {
    if(known.has(disk.directory_name))continue;
    const entry=node("div","catalog-entry");
    entry.append(node("strong","",disk.directory_name),node("small","","Файлы обнаружены · управляемый профиль не подтверждён"));
    catalog.append(entry);
  }
  container.append(catalog);
  const area=node("section","working-slots");
  const heading=node("div","manager-model-head");
  heading.append(node("h3","","РАБОЧИЕ СЛОТЫ · "+control.slots.length));
  const add=node("button","btn secondary small","＋ Добавить слот");
  add.type="button";add.classList.add("add-slot");add.disabled=!control.can_add_slot;
  add.title=control.can_add_slot ? "Manager назначит слот и свободный порт" : "Необходимо разрешение управления на Manager";
  add.addEventListener("click",async()=>{add.disabled=true;try{
    await pairingPost("/api/control",{manager_id:manager.manager_id,op:"add_slot",request_id:crypto.randomUUID().replaceAll("-","")});
    await refresh(true);
  }catch(e){setNotice(controlReason(e.message));add.disabled=!control.can_add_slot;}});
  heading.append(add);area.append(heading);
  const list=node("div","manager-model-scroll");
  for(const slot of control.slots) {
    const key=manager.manager_id+":"+slot.slot_id;
    const item=(control.instances || []).find(i=>i.slot_id===slot.slot_id&&!i.released);
    const live=(manager.data.slots || []).find(i=>i.slot_id===slot.slot_id)||{};
    const line=node("div","manager-model-row working-slot");line.dataset.slotId=slot.slot_id;
    const info=node("div","manager-model-info");
    info.append(node("strong","",slot.slot_id+(slot.protected ? " · защищённый" : "")));
    const select=node("select","slot-model");select.setAttribute("aria-label","Модель "+slot.slot_id);
    select.append(node("option","","Выберите модель"));select.options[0].value="";
    for(const model of control.models || []){const option=node("option","",model.name);option.value=model.key;select.append(option);}
    if(slot.protected) {
      const names=(live.models || []).join(", ");
      if(names){const option=node("option","",names);option.value="legacy";select.append(option);select.value="legacy";}
    }else select.value=slot.model_key || "";
    select.disabled=slot.protected||!slot.authorized||!control.control_models||!control.enabled||Boolean(item)||slotPending.has(key);
    const status=node("small","slot-state",item ? item.state+" · "+item.mode+" · "+item.instance_id :
      slot.protected ? stateLabel(live.engine_state)+" · внешний экземпляр" : "Остановлен · выбран "+slot.mode);
    info.append(select,status);line.append(info);
    select.addEventListener("change",async()=>{
      if(!select.value)return;
      slotPending.add(key);select.disabled=true;
      try{await pairingPost("/api/control",{manager_id:manager.manager_id,op:"select",slot_id:slot.slot_id,
        model_key:select.value,mode:slot.mode,expected_revision:slot.revision,request_id:crypto.randomUUID().replaceAll("-","")});}
      catch(e){status.textContent=controlReason(e.message);}
      finally{slotPending.delete(key);await refresh(true);}
    });
    for(const title of ["Старт CPU", "Старт CUDA", "Стоп"]) {
      const mode=title==="Старт CPU" ? "cpu" : "cuda";
      const button=node("button","btn secondary small manager-model-action",title);button.type="button";
      const model=(control.models || []).find(m=>m.key===select.value);
      const capability=model?.modes?.[mode];
      button.disabled=slotPending.has(key)||(title==="Стоп" ? !item?.can_stop :
        Boolean(item)||slot.protected||!slot.authorized||!control.control_models||!control.enabled||!model||!capability?.available);
      button.title=title==="Стоп" ? (item?.can_stop ? "Остановить только этот экземпляр" : "Нет собственного управляемого экземпляра") :
        (controlReason(capability?.reason)||"Проверить запуск в этом слоте");
      if(title!=="Стоп" && capability?.forecast) {
        const forecast=capability.forecast;
        button.title+=" · Ожидаемый остаток RAM: "+(forecast.ram_after_gib===null ? "неизвестен" : formatNumber(forecast.ram_after_gib)+" GiB")+
          " · VRAM: "+(forecast.vram_after_gib===null ? "не применяется" : formatNumber(forecast.vram_after_gib)+" GiB")+
          " · Оценка: "+forecast.estimate_evidence;
      }
      button.addEventListener("click",async()=>{
        slotPending.add(key);button.disabled=true;
        for(const input of line.querySelectorAll("select,button"))input.disabled=true;
        try {
          let body;
          if(title==="Стоп")body={op:"stop",instance_id:item.instance_id};
          else {
            const target={slot_id:slot.slot_id,model_key:select.value,mode};
            const checked=await pairingPost("/api/control",{manager_id:manager.manager_id,op:"check",...target,request_id:crypto.randomUUID().replaceAll("-","")});
            let ack=false;
            if(checked.requires_ack) {
              const forecast=checked.forecast;
              const details="Ожидаемый остаток RAM: "+(forecast.ram_after_gib===null ? "неизвестен" : formatNumber(forecast.ram_after_gib)+" GiB")+
                "; VRAM: "+(forecast.vram_after_gib===null ? "не применяется" : formatNumber(forecast.vram_after_gib)+" GiB")+
                ". Достоверность: "+forecast.estimate_evidence+". Предупреждения: "+checked.warnings.join(", ");
              status.textContent=details;
              if(!checked.risk_ack_allowed)throw Error("resource_risk_not_permitted");
              ack=confirm(details+". Возможны замедление других моделей и программ сервера. Подтвердить риск этого запуска?");
              if(!ack)return;
            }
            body={op:"start",...target,...(ack ? {risk_ack:true,risk_token:checked.risk_token} : {})};
          }
          const response=await pairingPost("/api/control",{manager_id:manager.manager_id,...body,request_id:crypto.randomUUID().replaceAll("-","")});
          status.textContent=response.state;
        }catch(e){status.textContent=controlReason(e.message);setNotice(controlReason(e.message));}
        finally{slotPending.delete(key);await refresh(true);}
      });
      line.append(button);
    }
    list.append(line);
  }
  area.append(list);container.append(area);
}
function modelList(container, slots, disk, manager) {
  const control = manager.data.control;
  if (control && Array.isArray(control.slots)) {workspaces(container,manager);return;}
  const wrapper = node("section", "models-list");
  const heading = node("div", "manager-model-head");
  heading.append(node("h3", "", "МОДЕЛИ И УПРАВЛЕНИЕ"),
    node("small", "", "Управление выполняет выбранный Manager"));
  wrapper.append(heading);
  const scroll = node("div", "manager-model-scroll");
  const rows = [];
  const names = new Set();
  if (control && Array.isArray(control.models)) {
    for (const model of control.models) {
      const instances = (control.instances || []).filter(i => i.model_key === model.key);
      const apiIds = [...(model.api_ids || []), ...instances.map(i => i.model_id).filter(x => typeof x === "string")];
      const active = instances.filter(i => !i.released && i.state !== "STOPPED");
      const external = slots.filter(s => (s.models || []).some(m => apiIds.includes(m)));
      for (const name of [model.directory_name, ...apiIds]) {
        if (typeof name === "string") names.add(name.toLowerCase());
      }
      const status = active.map(i => i.state + " · " + i.slot_id + " · " + i.mode +
        (i.reason ? " · " + controlReason(i.reason) : "")).join("; ") ||
        external.map(s => stateLabel(s.engine_state) + " · " + s.slot_id + " · внешний защищённый экземпляр").join("; ") ||
        (instances.length ? instances[instances.length-1].state : "Не запущена");
      rows.push({name:model.name, status, running:active.some(i => i.state === "READY") || external.length > 0,
                 model, active});
    }
  }
  for (const slot of slots) {
    for (const model of (Array.isArray(slot.models) ? slot.models : [])) {
      if (typeof model !== "string" || !model.trim() || names.has(model.toLowerCase())) continue;
      names.add(model.toLowerCase());
      rows.push({name:model, status:stateLabel(slot.engine_state) + " · " +
        slot.slot_id + " · " + stateLabel(slot.availability), running:slot.engine_state === "ready"});
    }
  }
  for (const item of disk) {
    if (!item || typeof item.directory_name !== "string" ||
        !item.directory_name.trim() || names.has(item.directory_name.toLowerCase())) continue;
    names.add(item.directory_name.toLowerCase());
    rows.push({name:item.directory_name, status:"Файлы на диске · совместимость и запуск не проверены",
               running:false});
  }
  if (!rows.length) scroll.append(node("p", "manager-model-empty",
    "Manager пока не сообщил ни одной модели."));
  for (const item of rows) {
    const line = node("div", "manager-model-row");
    const identity = node("div", "manager-model-info");
    identity.append(node("strong", "manager-model-name", item.name),
                    node("small", item.running ? "model-live" : "model-unverified",
                         item.status));
    line.append(identity);
    for (const title of ["Старт CPU", "Старт CUDA", "Стоп"]) {
      const button = node("button", "btn secondary small manager-model-action", title);
      button.type = "button";
      button.disabled = true;
      button.title = "Обновите Manager для управления моделями";
      if (item.model) {
        const mode = title === "Старт CPU" ? "cpu" : "cuda";
        const own = item.active.find(i => i.can_stop);
        const capability = item.model.modes[mode] || {};
        button.disabled = title === "Стоп" ? !own : capability.available !== true;
        button.title = title === "Стоп" ? (own ? "Остановить свой экземпляр " + own.instance_id :
          "Нет собственного управляемого экземпляра") : (controlReason(capability.reason) || "Manager повторно проверит ресурсы");
        button.addEventListener("click", async () => {
          button.disabled = true;
          const body = title === "Стоп" ? {op:"stop",instance_id:own.instance_id} :
            {op:"start",model_key:item.model.key,mode};
          try {
            const result = await pairingPost("/api/control", {manager_id:manager.manager_id,
              request_id:crypto.randomUUID().replaceAll("-", ""), ...body});
            identity.querySelector("small").textContent = result.state + " · " + result.slot_id;
            await refresh();
          } catch (e) {
            identity.querySelector("small").textContent = "Ошибка: " + controlReason(e.message);
          }
        });
      }
      button.setAttribute("aria-label", title + " — " + item.name + (button.disabled ? " (недоступно)" : ""));
      line.append(button);
    }
    scroll.append(line);
  }
  wrapper.append(scroll);
  const note = node("div", "manager-model-policy",
    "CUDA: число одновременных запусков определит Manager по VRAM, модели и текущей нагрузке. " +
    "Файлы на диске ещё не означают готовность модели.");
  wrapper.append(note);
  container.append(wrapper);
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
  const memory = online && row.data ? row.data.memory || {} : {};
  const memoryText = memory.state === "live" ? [
    ["DDR3", "DDR4", "DDR5"].includes(memory.ddr_generation) ?
      memory.ddr_generation : "Тип DDR: не определён",
    typeof memory.installed_gib === "number" && memory.installed_gib > 0 ?
      "Установлено " + formatNumber(memory.installed_gib) + " GiB" :
      "Всего " + formatNumber(memory.total_gib) + " GiB",
    "Свободно " + formatNumber(memory.free_gib) + " GiB"
  ].join(" · ") : "Память: нет подтверждённых данных";
  top.append(node("span", "manager-memory-summary", memoryText));
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
  const available = slots.filter(s => s.availability === "ready_unreserved").length;
  body.append(node("div", "manager-slot-summary",
    "Слотов: " + slots.length + " · Готовы к запросам: " + available +
    " · Свободный слот сам по себе не означает запущенную LLM"));
  modelList(body, slots, Array.isArray(data.models) ? data.models : [], row);
  card.append(body);
  return card;
}
function render(payload) {
  chatSnapshot = payload;
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
  let ready = 0;
  const grid = byId("managers");grid.replaceChildren();
  for (const manager of all) {
    grid.append(makeManager(manager));
    if (manager.status !== "online" || !manager.data) continue;
    const data = manager.data;
    const slots = Array.isArray(data.slots) ? data.slots : [];
    for (const slot of slots) {
      if (slot.engine_state === "ready") {
        for (const model of (slot.models || [])) models.add(manager.manager_id + ":" + model);
      }
      if (slot.availability === "ready_unreserved") ready += 1;
    }
  }
  if (!all.length) grid.append(node("div", "placeholder", "Нет подключённых менеджеров. Нажмите «Подключить сервер», чтобы начать."));
  stat("metric-manager", all.length);
  stat("online-note", online.length + " онлайн из " + all.length);
  stat("metric-models", models.size);
  stat("metric-ready", ready);
  stat("server-count", all.length + " серверов");
  stat("last-update", new Date().toLocaleTimeString("ru-RU", {hour:"2-digit",minute:"2-digit"}));
  setNotice(all.some(m => m.status !== "online") ?
      "Не все Manager доступны. Проверьте сеть, сертификат и регистрацию этого компьютера." : "");
  if (chatOpen) renderChatList(payload);
}
async function refresh(force=false) {
  if (isRefreshing) {if(force===true)refreshQueued=true;return;}
  isRefreshing = true;
  const button = byId("refresh"); button.disabled = true;
  try {
    render(await api("/api/status"));
  } catch (err) {
    setNotice("Не удалось обновить данные: " + err.message);
  } finally {
    isRefreshing = false;
    button.disabled = false;
    if(refreshQueued){refreshQueued=false;await refresh(true);}
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
  const requested = new URLSearchParams(window.location.hash.slice(1)).get("chat");
  if (requested) { chatSelected = requested; showChats(); }
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
setInterval(() => { if (chatSnapshot && chatSnapshot.managers.some(m =>
  m.data && m.data.control && m.data.control.instances.some(i => ["STARTING","STOPPING"].includes(i.state)))) refresh(); }, 2000);

/* CHAT-01: model slots are discovered dynamically from live Manager snapshots.
   They are never predefined as "three" or tied to hard-coded IP addresses. */
let chatSnapshot = null;
let chatOpen = false;
let chatItems = [];
let chatSelected = "";
let chatBusy = false;
let chatAbort = null;
let chatRetry = null;
let activeChatKey = "";

function showOverview(event) {
  if (event) event.preventDefault();
  chatOpen = false;
  byId("overview").classList.remove("hidden");
  byId("chat-view").classList.add("hidden");
  byId("nav-overview").classList.add("selected");
  byId("nav-chats").classList.remove("selected");
}
function showChats() {
  chatOpen = true;
  byId("overview").classList.add("hidden");
  byId("chat-view").classList.remove("hidden");
  byId("nav-overview").classList.remove("selected");
  byId("nav-chats").classList.add("selected");
  renderChatList(chatSnapshot);
  if (currentChat()) loadChatHistory();
}

function chatTargetKey(target) {
  return JSON.stringify([target.manager_id, target.slot_id, target.model_id,
    ...(target.instance_id && !target.instance_id.startsWith("legacy-") ? [target.instance_id] : [])]);
}
function currentChat() {
  return chatItems.find(x => x.key === chatSelected) || null;
}
function chatTitle(target) {
  return target.model_id || target.slot_id + " · модель не запущена";
}
function chatReady(target) {
  return Boolean(target && target.model_id && target.online &&
    target.engine_state === "ready" &&
    target.availability === "ready_unreserved");
}
function setChatNotice(message) {
  const el = byId("chat-notice");
  el.textContent = message || "";
  el.classList.toggle("hidden", !message);
}
function renderChatList(payload) {
  if (!chatOpen) return;
  const list = byId("chat-list");
  const before = chatSelected;
  chatItems = [];
  for (const manager of (payload && Array.isArray(payload.managers) ? payload.managers : [])) {
    if (manager.status !== "online" || !manager.data) continue;
    for (const slot of (manager.data.slots || [])) {
      const names = Array.isArray(slot.models) && slot.models.length ? slot.models : [""];
      for (const model of names) {
        const target = {
          manager_id:manager.manager_id, manager_name:manager.name || manager.manager_id,
          slot_id:slot.slot_id, model_id:model, instance_id:slot.instance_id,
          streaming:manager.data.chat ? manager.data.chat.streaming === true : false, engine_state:slot.engine_state,
          availability:slot.availability, online:true
        };
        target.key = chatTargetKey(target);
        chatItems.push(target);
      }
    }
  }
  if (!chatItems.some(x => x.key === chatSelected)) {
    chatSelected = chatItems.length ? chatItems[0].key : "";
  }
  list.replaceChildren();
  for (const item of chatItems) {
    const card = node("button", "chat-choice" +
      (item.key === chatSelected ? " active" : "") +
      (chatReady(item) ? " is-ready" : ""));
    card.type = "button";
    card.append(node("b", "", chatTitle(item)),
                node("small", "", item.manager_name + " · " + item.slot_id),
                node("span", "chat-status", chatReady(item) ? "● Готова к переписке" :
                   item.availability === "denied" ? "● Нет доступа" :
                   item.engine_state === "not_running" ? "○ Не запущена" :
                   "○ " + stateLabel(item.availability)));
    card.addEventListener("click", () => {
      const old = chatSelected;
      chatSelected = item.key;
      renderChatList(chatSnapshot);
      if (old === item.key) loadChatHistory();
    });
    list.append(card);
  }
  if (!chatItems.length) {
    list.append(node("div", "placeholder", "Пока нет доступных слотов Manager."));
  }
  const selected = currentChat();
  byId("chat-title").textContent = selected ? chatTitle(selected) : "Нет доступных моделей";
  byId("chat-subtitle").textContent = selected ?
    selected.manager_name + " / " + selected.slot_id : "Подключите Manager на вкладке «Обзор»";
  byId("chat-popout").disabled = !selected;
  byId("chat-input").disabled = !chatReady(selected) || chatBusy;
  byId("chat-send").disabled = !chatReady(selected) || chatBusy;
  byId("chat-state").textContent = selected && !chatReady(selected) ?
    "Слот сейчас недоступен. Отправка отключена; Client не запускает LLM автоматически." : "";
  if (chatSelected !== before) {
    loadChatHistory();
  }
}
function reasoningPanel(text) {
  const detail = node("details", "reasoning-panel");
  detail.open = true;
  detail.classList.toggle("hidden", !byId("chat-show-reasoning").checked);
  detail.append(node("summary", "", "Рассуждения · отдельный поток модели"), node("div", "reasoning-text", text || ""));
  return detail;
}
let streamMetrics = {};
function updateMetrics(extra) {
  streamMetrics = {...streamMetrics, ...extra};
  byId("chat-metrics").textContent = JSON.stringify(streamMetrics, null, 2);
}
function targetFields(target, history=false) {
  const result = {manager_id:target.manager_id,slot_id:target.slot_id,model_id:target.model_id};
  if (target.instance_id && (!history || !target.instance_id.startsWith("legacy-"))) result.instance_id=target.instance_id;
  return result;
}
function generationFields() {
  const maximum=byId("chat-max-tokens").value;
  return {options:{thinking:byId("chat-thinking").value,reasoning_effort:byId("chat-effort").value,
    ...(maximum ? {max_output_tokens:Number(maximum)} : {})},
    context:{max_messages:Number(byId("chat-history-messages").value),max_chars:Number(byId("chat-history-chars").value)}};
}
function renderMessages(messages) {
  const holder = byId("chat-messages");
  holder.replaceChildren();
  if (!Array.isArray(messages) || !messages.length) {
    holder.append(node("div", "chat-empty",
       "История пока пуста. Напишите сообщение, когда LLM будет готова."));
  } else {
    for (const message of messages) {
      const bubble = node("div", "chat-bubble" + (message.role === "user" ? " user" : ""));
      bubble.append(node("small", "", message.role === "user" ? "Вы" : "LLM"),
                    node("div", "", message.content || ""));
      if (message.reasoning_content) bubble.prepend(reasoningPanel(message.reasoning_content));
      holder.append(bubble);
    }
  }
  holder.scrollTop = holder.scrollHeight;
}
async function loadChatHistory() {
  const chosen = currentChat();
  const key = chatSelected;
  if (chatBusy && key === activeChatKey) return;
  if (!chosen) { renderMessages([]); return; }
  if (!chosen.model_id) { renderMessages([]); return; }
  const params = new URLSearchParams(targetFields(chosen, true));
  try {
    const result = await api("/api/chat/history?" + params.toString());
    if (chatSelected === key && !(chatBusy && key === activeChatKey)) renderMessages(result.messages);
  } catch (error) {
    if (chatSelected === key) setChatNotice("Не удалось прочитать историю: " + error.message);
  }
}
async function submitChat(event) {
  event.preventDefault();
  if (chatBusy) return;
  const target = currentChat();
  const message = byId("chat-input").value.trim();
  if (!chatReady(target) || !message || message.length > 131072) return;
  chatBusy = true;
  const started=performance.now();
  streamMetrics={browser_request_unix_ms:performance.timeOrigin+started};
  const targetKey = chatSelected;
  activeChatKey = targetKey;
  byId("chat-send").disabled = true;
  byId("chat-input").disabled = true;
  byId("chat-state").textContent = "Запрос выполняется на сервере. Ожидаем настоящий ответ модели…";
  setChatNotice("");
  try {
    const streaming = byId("chat-stream").checked && target.streaming !== false;
    const generation = generationFields();
    if(target.streaming===false)delete generation.options;
    if (!chatRetry || chatRetry.key !== targetKey || chatRetry.message !== message || chatRetry.parameters !== JSON.stringify(generation)) {
      chatRetry = {key:targetKey,message,parameters:JSON.stringify(generation),id:crypto.randomUUID().replaceAll("-", "")};
    }
    let result;
    if (!streaming) {
      result = await pairingPost("/api/chat/send", {
        ...targetFields(target), ...generation, message,
        request_id:chatRetry.id
      });
    } else {
      chatAbort = new AbortController();
      byId("chat-cancel").disabled = false;
      const response = await fetch("/api/chat/stream", {method:"POST", signal:chatAbort.signal,
        headers:{"Content-Type":"application/json","X-Ultra-CSRF":csrf},
        body:JSON.stringify({...targetFields(target), ...generation, message,request_id:chatRetry.id})});
      if (!response.ok) {
        const failure = await response.json();
        throw Error(failure.error || String(response.status));
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8", {fatal:true});
      let pending = "", answer = "", reasoning = "", received = 0, firstVisible = false;
      const bubble = node("div", "chat-bubble");
      const text = node("div", "");
      const reasoningDetail = reasoningPanel("");
      reasoningDetail.classList.add("hidden");
      bubble.append(node("small", "", "LLM · поток"), reasoningDetail, text);
      const holder = byId("chat-messages");
      holder.append(bubble);
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) { pending += decoder.decode(); if (pending.trim()) throw Error("stream_truncated"); break; }
          received += chunk.value.byteLength;
          if (received > 64*1024*1024) throw Error("stream_too_large");
          pending += decoder.decode(chunk.value, {stream:true});
          let end;
          while ((end = pending.indexOf("\n")) >= 0) {
            const event = JSON.parse(pending.slice(0, end));
            pending = pending.slice(end+1);
            if (event.timing) updateMetrics({route:event.timing});
            if (event.type === "meta") {
              updateMetrics({engine_limits:event.engine_limits || {},transport_policy:event.transport_policy || {},context:event.context || {}});
              if (event.context && event.context.omitted_messages) setChatNotice("В контекст не вошло сообщений: " + event.context.omitted_messages + ". Настройки истории доступны выше.");
            }
            if (event.type === "reasoning") {
              reasoning += event.text;
              reasoningDetail.querySelector(".reasoning-text").textContent = reasoning;
              reasoningDetail.classList.toggle("hidden", !byId("chat-show-reasoning").checked);
            }
            if (event.type === "delta") {
              answer += event.text;
              if (chatSelected === targetKey) {
                text.textContent = answer;
                holder.scrollTop = holder.scrollHeight;
                byId("chat-state").textContent = "Получаем ответ модели…";
              }
            }
            if (!firstVisible && chatSelected===targetKey &&
                (event.type==="delta" || (event.type==="reasoning" && byId("chat-show-reasoning").checked))) {
              firstVisible=true;
              updateMetrics({browser_first_dom_update_unix_ms:performance.timeOrigin+performance.now(),browser_first_fragment_ms:performance.now()-started});
              requestAnimationFrame(() => requestAnimationFrame(() => updateMetrics({browser_first_paint_opportunity_unix_ms:performance.timeOrigin+performance.now()})));
            }
            if (event.type === "error") throw Error(event.error);
            if (event.type === "done") { result = event; updateMetrics({usage:event.usage || {},throughput:event.throughput || {},browser_total_ms:performance.now()-started}); }
          }
        }
        if (!result) throw Error("stream_truncated");
      } finally {
        await reader.cancel();
        reader.releaseLock();
      }
    }
    chatRetry = null;
    if (result.history_reload) {
      result = await api("/api/chat/history?" + new URLSearchParams(targetFields(target,true)));
    }
    if (chatSelected === targetKey) {
      byId("chat-input").value = "";
      renderMessages(result.messages);
      byId("chat-state").textContent = "Ответ получен от " + target.model_id;
    }
  } catch (error) {
    byId("chat-state").textContent = "";
    setChatNotice(error.name === "AbortError" ? "Поток отменён; неполный ответ не сохранён." : "Ошибка ответа: " + controlReason(error.message));
  } finally {
    chatBusy = false;
    chatAbort = null;
    byId("chat-cancel").disabled = true;
    renderChatList(chatSnapshot);
  }
}

byId("nav-overview").addEventListener("click", showOverview);
byId("nav-chats").addEventListener("click", showChats);
byId("chat-reload").addEventListener("click", refresh);
byId("chat-form").addEventListener("submit", submitChat);
byId("chat-show-reasoning").addEventListener("change", () => { document.querySelectorAll(".reasoning-panel").forEach(x => x.classList.toggle("hidden", !byId("chat-show-reasoning").checked)); });
byId("chat-cancel").addEventListener("click", async () => {
  if (!chatAbort || !chatRetry) return;
  const abort = chatAbort;
  const [manager_id,slot_id,model_id] = JSON.parse(chatRetry.key);
  try {
    await pairingPost("/api/chat/cancel", {manager_id,slot_id,model_id,request_id:chatRetry.id});
  } finally { abort.abort(); }
});
byId("chat-popout").addEventListener("click", () => {
  const target = currentChat();
  if (!target) return;
  const url = new URL(window.location.href);
  url.hash = "chat=" + encodeURIComponent(target.key);
  window.open(url.toString(), "_blank", "noopener");
});
window.addEventListener("focus", () => { if (chatOpen && !chatBusy) loadChatHistory(); });
