"use strict";
// Frontend never receives or stores Manager bearer tokens. All TLS and
// authorization happen inside the local Python Web Client process.
const byId = id => document.getElementById(id);
const dialog = byId("setup");
const adminDialog = byId("admin-dialog");
let csrf = "";
let isRefreshing = false;
let refreshQueued = false;
let statusRequest = 0;
let appliedStatusRequest = 0;
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
    context_length_exceeded:"Модель отклонила длину контекста. Уменьшите историю или сбросьте контекст этого чата",
    colibri_context_length_exceeded:"Модель отклонила длину контекста. Уменьшите историю или сбросьте контекст этого чата",
    slot_chat_in_progress:"Слот занят запросом",
    model_not_authorized:"Эта модель не разрешена клиенту",
    instance_not_authorized:"Экземпляр принадлежит другому клиенту или слот не разрешён",
    instance_not_stoppable:"Остановка недоступна до подтверждения состояния экземпляра",
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
  if (control.control_models === false || control.enabled === false) {
    area.append(node("p","manager-pairing-note",control.control_models === false ?
      "Manager разрешает просмотр слотов. Для управления моделями нужно отдельное разрешение." :
      "Управление моделями выключено на Manager."));
  }
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
  unknownSlots.clear();
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
    await readStatus();
  } catch (err) {
    setNotice("Не удалось обновить данные: " + err.message);
  } finally {
    isRefreshing = false;
    button.disabled = false;
    if(refreshQueued){refreshQueued=false;await refresh(true);}
  }
}
async function readStatus(options) {
  const id = ++statusRequest;
  const status = await api("/api/status", options);
  if (id > appliedStatusRequest) {
    appliedStatusRequest = id;
    render(status);
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
setInterval(() => { if (chatSnapshot?.managers?.some(m =>
  m.data?.control?.instances?.some(i => ["STARTING","STOPPING"].includes(i.state)))) refresh(); }, 2000);

/* CHAT-01: model slots are discovered dynamically from live Manager snapshots.
   They are never predefined as "three" or tied to hard-coded IP addresses. */
let chatSnapshot = null;
let chatOpen = false;
let chatItems = [];
let chatSelected = "";
let chatTargets = [];
let streamMetrics = {};
let historyRevision = 0;
let chatMutation = false;
let loadingChats = false;
const conversations = new Map();
const releasingSlots = new Map();
const unknownSlots = new Set();

function conversation(id) {
  if (!conversations.has(id)) conversations.set(id, {messages:[], draft:"", notice:"", metrics:{}});
  return conversations.get(id);
}
function showOverview(event) {
  if (event) event.preventDefault();
  chatOpen = false;
  byId("overview").classList.remove("hidden");
  byId("chat-view").classList.add("hidden");
  byId("nav-overview").classList.add("selected");
  byId("nav-chats").classList.remove("selected");
}
async function showChats() {
  chatOpen = true;
  byId("overview").classList.add("hidden");
  byId("chat-view").classList.remove("hidden");
  byId("nav-overview").classList.remove("selected");
  byId("nav-chats").classList.add("selected");
  if (loadingChats) return;
  loadingChats = true;
  renderChatList(chatSnapshot);
  try {
    chatItems = (await api("/api/chats")).chats;
    const saved = sessionStorage.getItem("ultra.chat");
    selectChat([chatSelected, saved].find(id => chatItems.some(row => row.chat_id === id)) || chatItems[0]?.chat_id || "");
  } catch (error) {
    setChatNotice("Не удалось загрузить чаты: " + error.message);
  } finally {
    loadingChats = false;
    renderChatControls();
  }
}
function targetFields(target) {
  return {manager_id:target.manager_id, slot_id:target.slot_id, model_id:target.model_id};
}
function targetKey(target) {
  return JSON.stringify(Object.values(targetFields(target)));
}
function slotKey(target) {
  return JSON.stringify([target.manager_id, target.slot_id]);
}
function currentChat() {
  return chatItems.find(row => row.chat_id === chatSelected);
}
function liveTarget(chat) {
  return chat && chatTargets.find(target => targetKey(target) === targetKey(chat));
}
function chatReady(target) {
  return target?.engine_state === "ready" && target.availability === "ready_unreserved" &&
    !releasingSlots.has(slotKey(target)) && !unknownSlots.has(slotKey(target)) && !localSlotActive(target);
}
function localSlotActive(target) {
  return [...conversations.values()].some(view => view.request && slotKey(view.request.target) === slotKey(target));
}
function setChatNotice(message) {
  const el = byId("chat-notice");
  el.textContent = message || "";
  el.classList.toggle("hidden", !message);
}
function renderChatList(payload) {
  chatTargets = [];
  for (const manager of (Array.isArray(payload?.managers) ? payload.managers : [])) {
    if (manager.status !== "online" || !Array.isArray(manager.data?.slots)) continue;
    for (const slot of manager.data.slots) {
      for (const model of (Array.isArray(slot.models) ? slot.models : [])) {
        chatTargets.push({
          manager_id:manager.manager_id, manager_name:manager.name || manager.manager_id,
          slot_id:slot.slot_id, model_id:model, instance_id:slot.instance_id,
          streaming:manager.data.chat?.streaming === true, engine_state:slot.engine_state,
          availability:slot.availability, transport:manager.data.chat?.transport_policy
        });
      }
    }
  }
  if (!chatOpen) return;
  const list = byId("chat-list");
  const scroll = list.scrollTop;
  list.replaceChildren();
  for (const chat of chatItems) {
    const view = conversation(chat.chat_id);
    const card = node("button", "chat-choice" + (chat.chat_id === chatSelected ? " active" : "") +
      (chatReady(liveTarget(chat)) ? " is-ready" : ""));
    card.type = "button";
    card.dataset.chatId = chat.chat_id;
    card.append(node("b", "", chat.title), node("small", "", chat.model_id || "Без назначения"));
    if (view.request) card.append(node("small", "", "Модель отвечает"));
    card.addEventListener("click", () => selectChat(chat.chat_id));
    list.append(card);
  }
  list.scrollTop = scroll;
  renderChatControls();
}
function renderChatControls() {
  const chat = currentChat();
  const target = liveTarget(chat);
  const active = chat && conversation(chat.chat_id).request;
  const selector = byId("chat-target");
  const value = chat?.model_id ? targetKey(chat) : "";
  const choices = chatTargets.filter(item => item.availability !== "denied");
  const options = [new Option("Без назначения", "")];
  if (value && !choices.some(item => targetKey(item) === value)) {
    options.push(new Option(chat.manager_id + " / " + chat.slot_id + " / " + chat.model_id + " · недоступна", value));
  }
  for (const item of choices) options.push(new Option(item.manager_name + " / " + item.slot_id + " / " + item.model_id, targetKey(item)));
  selector.replaceChildren(...options);
  selector.value = value;
  selector.disabled = !chat || Boolean(active) || chatMutation;
  byId("chat-title").textContent = chat?.title || "Выберите чат";
  byId("chat-subtitle").textContent = chat?.context_after ? "Контекст начинается после сброса" : "";
  byId("chat-popout").disabled = !chat;
  byId("chat-new").disabled = chatMutation || loadingChats;
  byId("chat-input").disabled = !chat || Boolean(active);
  byId("chat-send").disabled = !chatReady(target) || Boolean(active) || chatMutation;
  byId("chat-cancel").disabled = !active?.controller || active.cancelling;
  for (const op of ["rename","reset","resume","clear","restore","delete"]) {
    byId("chat-"+op).disabled = !chat || Boolean(active) || chatMutation ||
      (op === "restore" && !chat.can_restore) || (op === "resume" && !chat.context_after);
  }
  const status = byId("chat-state");
  if (active) status.textContent = active.cancelling ? "Отменяем запрос…" : "Модель отвечает";
  else if (!chat) status.textContent = "";
  else if (!chat.model_id) status.textContent = "Выберите Manager, слот и модель.";
  else if (target && (releasingSlots.has(slotKey(target)) || target.availability === "busy" || localSlotActive(target))) {
    status.textContent = "Модель занята. Ожидаем освобождения слота.";
  } else status.textContent = chatReady(target) ? "" : "Назначенная модель сейчас недоступна.";
}
function selectChat(id) {
  chatSelected = id;
  sessionStorage.setItem("ultra.chat", id);
  if (location.hash.startsWith("#chat=")) {
    window.history.replaceState(null, "", id ? "#chat=" + encodeURIComponent(id) : location.pathname);
  }
  const chat = currentChat();
  const view = chat ? conversation(id) : {messages:[], draft:"", metrics:{}};
  byId("chat-input").value = view.draft;
  byId("chat-history-messages").value = chat?.settings.max_messages ?? 100;
  byId("chat-history-chars").value = chat?.settings.max_chars ?? 200000;
  setChatNotice(view.notice);
  followStream = true;
  renderMessages(view.messages, view.request);
  byId("chat-latest").classList.add("hidden");
  renderChatList(chatSnapshot);
  updateMetrics(view);
  renderTimer();
  renderStatistics([]);
  if (chat && !view.request) loadChatHistory();
  if (chat) loadStatistics(id);
}
async function changeChat(op, values = {}) {
  if (chatMutation) return;
  const id = chatSelected;
  chatMutation = true;
  renderChatControls();
  try {
    const row = await pairingPost("/api/chats", {op, ...(op === "create" ? {} : {chat_id:id}), ...values});
    if (op === "create") {
      chatItems.unshift(row);
      selectChat(row.chat_id);
    } else if (op === "delete") {
      chatItems = chatItems.filter(item => item.chat_id !== id);
      conversations.delete(id);
      if (chatSelected === id) selectChat(chatItems[0]?.chat_id || "");
    } else {
      chatItems = chatItems.map(item => item.chat_id === id ? row : item);
      if (chatSelected === id && ["clear", "restore"].includes(op)) await loadChatHistory();
      if (chatSelected === id && op === "target" && conversation(id).messages.length) {
        setChatNotice("Для новой модели будут использованы текстовые реплики этого чата. При несовместимости сбросьте контекст или уменьшите историю.");
      }
    }
  } catch (error) {
    if (chatSelected === id) {
      setChatNotice("Не удалось изменить чат: " + controlReason(error.message));
      const chat = currentChat();
      if (op === "settings" && chat) {
        byId("chat-history-messages").value = chat.settings.max_messages;
        byId("chat-history-chars").value = chat.settings.max_chars;
      }
    }
  } finally {
    chatMutation = false;
    renderChatList(chatSnapshot);
  }
}
function reasoningPanel(text, open) {
  const detail = node("details", "reasoning-panel");
  detail.open = open;
  detail.classList.toggle("hidden", !byId("chat-show-reasoning").checked);
  detail.append(node("summary", "", "Рассуждения"), node("div", "reasoning-text", text || ""));
  detail.addEventListener("toggle", followBottom);
  return detail;
}
const dateFormat = new Intl.DateTimeFormat("ru-RU", {day:"2-digit", month:"2-digit", year:"numeric"});
const timeFormat = new Intl.DateTimeFormat("ru-RU", {hour:"2-digit", minute:"2-digit"});
function timestamp(raw) {
  const date = raw && new Date(raw);
  const label = node("time", "chat-time", date && Number.isFinite(+date) ?
    dateFormat.format(date) + " · " + timeFormat.format(date) : "Время неизвестно");
  if (date && Number.isFinite(+date)) label.dateTime = date.toISOString();
  return label;
}
function messageBubble(message, live = false) {
  const bubble = node("div", "chat-bubble" + (message.role === "user" ? " user" : ""));
  const label = node("small", "", message.role === "user" ? "Вы" : "LLM");
  if (message.reasoning_content || live) {
    const reasoning = reasoningPanel(message.reasoning_content, live);
    if (!message.reasoning_content) reasoning.classList.add("hidden");
    bubble.append(label, reasoning);
  } else bubble.append(label);
  bubble.append(node("div", "chat-text", message.content || ""));
  if (!live) bubble.append(timestamp(message.created_at));
  return bubble;
}
const chatHolder = byId("chat-messages");
let followStream = true;
let scrollFrame = 0;
let lastScrollTop = 0;
function scrollDistance() {
  return chatHolder.scrollHeight - chatHolder.clientHeight - chatHolder.scrollTop;
}
function pinToBottom() {
  chatHolder.scrollTop = chatHolder.scrollHeight;
  lastScrollTop = chatHolder.scrollTop;
}
function updateFollow() {
  const top = chatHolder.scrollTop;
  // DOM growth changes scrollHeight without moving scrollTop. A delayed
  // notification from our own scroll must not be treated as user movement.
  if (Math.abs(top - lastScrollTop) > 0.5) {
    followStream = scrollDistance() <= 48;
    byId("chat-latest").classList.toggle("hidden", followStream);
  }
  lastScrollTop = top;
}
function followBottom() {
  if (!followStream || scrollFrame) return;
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0;
    updateFollow();
    if (followStream) pinToBottom();
  });
}
chatHolder.addEventListener("scroll", updateFollow, {passive:true});
byId("chat-latest").addEventListener("click", () => {
  followStream = true;
  byId("chat-latest").classList.add("hidden");
  pinToBottom();
});
function renderMessages(messages, active) {
  chatHolder.replaceChildren(...messages.map(message => messageBubble(message)));
  if (active) chatHolder.append(active.user, active.assistant);
  else if (!messages.length) chatHolder.append(node("div", "chat-empty",
    currentChat() ? "История пока пуста." : "Выберите или создайте чат."));
  if (followStream) pinToBottom();
}
async function loadChatHistory() {
  const id = chatSelected;
  if (!id || conversation(id).request) return;
  const revision = ++historyRevision;
  try {
    const result = await api("/api/chat/history?" + new URLSearchParams({chat_id:id}));
    if (chatSelected !== id || revision !== historyRevision || conversation(id).request) return;
    const view = conversation(id);
    if (JSON.stringify(view.messages) === JSON.stringify(result.messages)) return;
    view.messages = result.messages;
    renderMessages(view.messages);
  } catch (error) {
    if (chatSelected === id && revision === historyRevision) setChatNotice("Не удалось прочитать историю: " + error.message);
  }
}
function updateMetrics(view, extra = {}) {
  view.metrics = {...view.metrics, ...extra};
  if (!chatSelected || view !== conversation(chatSelected)) return;
  streamMetrics = view.metrics;
  byId("chat-metrics").textContent = Object.keys(streamMetrics).length ? JSON.stringify(streamMetrics, null, 2) : "Ещё нет измерений";
}
function seconds(ms) {
  return Number.isFinite(ms) ? (ms/1000).toFixed(2) + " с" : "нет данных";
}
function renderTimer() {
  const view = chatSelected && conversation(chatSelected);
  const active = view?.request;
  const snapshot = view?.metrics?.saved;
  const data = view?.metrics || {};
  let label = "";
  if (active) {
    const total = performance.now() - active.started;
    label = active.first == null ? "Ожидание первого фрагмента " + seconds(total) :
      "Первый фрагмент " + seconds(active.first) + " · Генерация " + seconds(total-active.first) + " · Всего " + seconds(total);
  } else if (snapshot || data.browser_total_ms != null) {
    const usage = data.usage || snapshot?.usage || {};
    const first = data.browser_first_fragment_ms ?? snapshot?.first_fragment_ms;
    const rate = (data.throughput || snapshot?.throughput)?.completion_tokens_per_second;
    label = (data.error || snapshot?.state === "failed" ? "Ошибка · " :
      snapshot?.state === "cancelled" || data.cancelled ? "Отменён · " : "") +
      "Первый фрагмент " + seconds(first) + " · Генерация " + seconds(data.browser_generation_ms ?? snapshot?.generation_ms) +
      " · Всего " + seconds(data.browser_total_ms ?? snapshot?.total_ms) +
      " · Токены вход / выход " + (usage.prompt_tokens ?? "нет данных") + " / " + (usage.completion_tokens ?? "нет данных") +
      (Number.isFinite(rate) ? " · Маршрут Colibri " + rate.toFixed(2) + " токенов/с с подготовкой prompt" : "");
  }
  byId("chat-timer").textContent = label;
}
let stats = [];
async function loadStatistics(id) {
  try {
    const result = await api("/api/chat/metrics?" + new URLSearchParams({chat_id:id}));
    if (chatSelected !== id) return;
    renderStatistics(result.results);
    const view = conversation(id);
    if (!view.request && !Object.keys(view.metrics).length && result.results[0]) {
      updateMetrics(view, {saved:result.results[0]});
      renderTimer();
    }
  } catch (error) {
    if (chatSelected === id) byId("chat-stat-results").textContent = "Не удалось загрузить измерения: " + error.message;
  }
}
function renderStatistics(results) {
  stats = results;
  const models = byId("chat-stat-model");
  const previous = models.value;
  const names = [...new Set(results.map(row => row.target.model_id))];
  models.replaceChildren(new Option("Все", ""), ...names.map(name => new Option(name, name)));
  if (names.includes(previous)) models.value = previous;
  filterStatistics();
}
function filterStatistics() {
  const model = byId("chat-stat-model").value;
  const mode = byId("chat-stat-mode").value;
  const results = stats.filter(row => (!model || row.target.model_id === model) && (!mode || (row.execution_mode || "unknown") === mode));
  byId("chat-stat-results").replaceChildren(...results.map(row => node("div", "chat-stat-row",
    timestamp(row.finished_at).textContent + " · " + row.target.model_id + " · " +
    (row.execution_mode?.toUpperCase() || "режим неизвестен") + " · " +
    ({complete:"Завершён", failed:"Ошибка", cancelled:"Отменён"}[row.state]) + " · " + seconds(row.total_ms) + " · " +
    (row.usage?.prompt_tokens ?? "нет данных") + " / " + (row.usage?.completion_tokens ?? "нет данных") + " токенов")));
}

function generationFields(target) {
  const maximum = byId("chat-max-tokens").value;
  const policy = target.transport || {};
  return {options:{thinking:byId("chat-thinking").value, reasoning_effort:byId("chat-effort").value,
      ...(maximum ? {max_output_tokens:Number(maximum)} : {})},
    context:{max_bytes:Math.min(policy.request_bytes || 1048576, 1048576),
      max_messages:Math.min(Number(byId("chat-history-messages").value), (policy.history_messages || 1024)-1),
      max_chars:Math.min(Number(byId("chat-history-chars").value),
        Math.max(0, (policy.history_chars || 1048576)-byId("chat-input").value.trim().length))}};
}
async function readChatStream(body, request, onEvent) {
  const response = await fetch("/api/chat/stream", {method:"POST", signal:request.controller.signal,
    headers:{"Content-Type":"application/json","X-Ultra-CSRF":csrf}, body:JSON.stringify(body)});
  if (!response.ok) throw Error((await response.json()).error || String(response.status));
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", {fatal:true});
  let pending = "", received = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) throw Error("stream_truncated");
      received += chunk.value.byteLength;
      if (received > 64*1024*1024) throw Error("stream_too_large");
      pending += decoder.decode(chunk.value, {stream:true});
      let end;
      while ((end = pending.indexOf("\n")) >= 0) {
        const event = JSON.parse(pending.slice(0, end));
        pending = pending.slice(end+1);
        if (event.type === "error") throw Error(event.error);
        onEvent(event);
        if (event.type === "done") return event;
      }
      if (pending.length > 2*1024*1024) throw Error("stream_frame_too_large");
    }
  } finally {
    try { await reader.cancel(); } finally { reader.releaseLock(); }
  }
}
function renderFragment(view, request, event) {
  if (event.timing) updateMetrics(view, {route:event.timing});
  if (event.type === "meta") {
    updateMetrics(view, {engine_limits:event.engine_limits || {}, transport_policy:event.transport_policy || {}, context:event.context || {}});
    if (event.context?.omitted_messages) {
      view.notice = "В контекст не вошло сообщений: " + event.context.omitted_messages;
      if (view === conversation(chatSelected)) setChatNotice(view.notice);
    }
  }
  if (!["delta", "reasoning"].includes(event.type) || !event.text) return;
  if (request.first == null) {
    request.first = performance.now() - request.started;
    updateMetrics(view, {browser_first_fragment_ms:request.first, browser_first_dom_update_unix_ms:performance.timeOrigin+performance.now()});
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (view.request === request || view.metrics.browser_request_unix_ms === performance.timeOrigin+request.started) {
        updateMetrics(view, {browser_first_paint_opportunity_unix_ms:performance.timeOrigin+performance.now()});
      }
    }));
  }
  if (event.type === "reasoning") {
    const detail = request.assistant.querySelector(".reasoning-panel");
    detail.querySelector(".reasoning-text").textContent += event.text;
    detail.classList.toggle("hidden", !byId("chat-show-reasoning").checked);
  } else request.assistant.querySelector(".chat-text").textContent += event.text;
  if (chatSelected === request.chatId) followBottom();
}
async function waitForSlot(target, view, request) {
  const key = slotKey(target);
  const release = {};
  releasingSlots.set(key, release);
  renderChatList(chatSnapshot);
  let observed = false;
  const checks = [];
  try {
    for (const pause of [0, 120, 300, 650, 1250]) {
      if (pause) await new Promise(resolve => setTimeout(resolve, pause));
      try { await readStatus({signal:AbortSignal.timeout(1800)}); } catch {
        checks.push("unknown");
        continue;
      }
      if (releasingSlots.get(key) !== release) return;
      observed = true;
      const live = liveTarget(target);
      checks.push(live?.availability || "offline");
      if (live?.availability === "ready_unreserved" && live.engine_state === "ready") {
        if (view.metrics.browser_request_unix_ms === performance.timeOrigin+request.started) {
          updateMetrics(view, {browser_slot_ready_ms:performance.now()-request.started});
        }
        break;
      }
      if (live && !["busy", "ready_unreserved"].includes(live.availability)) break;
    }
  } finally {
    if (!observed) unknownSlots.add(key);
    updateMetrics(view, {browser_slot_checks:checks});
    if (releasingSlots.get(key) === release) releasingSlots.delete(key);
    renderChatList(chatSnapshot);
  }
}
async function submitChat(event) {
  event.preventDefault();
  const chat = currentChat();
  const target = liveTarget(chat);
  const input = byId("chat-input");
  const message = input.value.trim();
  if (!chatReady(target) || chatMutation || !message || message.length > 131072) return;
  const id = chat.chat_id;
  const view = conversation(id);
  if (view.request) return;
  const streaming = byId("chat-stream").checked && target.streaming;
  const generation = generationFields(target);
  if (!target.streaming) delete generation.options;
  const parameters = JSON.stringify([targetKey(target), target.instance_id, message, generation, streaming]);
  const requestId = view.retry?.parameters === parameters ? view.retry.id : crypto.randomUUID().replaceAll("-", "");
  const request = {chatId:id, target, id:requestId, started:performance.now(),
    controller:streaming ? new AbortController() : null,
    user:messageBubble({role:"user", content:message, created_at:new Date().toISOString()}),
    assistant:messageBubble({role:"assistant"}, true)};
  const restoreFocus = document.activeElement === input;
  view.draft = input.value;
  view.retry = {parameters, id:requestId};
  view.notice = "";
  view.request = request;
  view.metrics = {};
  setChatNotice("");
  updateMetrics(view, {browser_request_unix_ms:performance.timeOrigin+request.started});
  chatHolder.querySelector(".chat-empty")?.remove();
  chatHolder.append(request.user, request.assistant);
  followBottom();
  renderChatControls();
  renderTimer();
  let completed = false;
  try {
    const body = {...targetFields(target), ...generation, chat_id:id, message, request_id:requestId,
      ...(target.instance_id ? {instance_id:target.instance_id} : {})};
    let result = streaming ? await readChatStream(body, request, frame => renderFragment(view, request, frame)) :
      await pairingPost("/api/chat/send", body);
    const total = performance.now()-request.started;
    updateMetrics(view, {usage:result.usage || {}, throughput:result.throughput || {}, context:result.context || view.metrics.context,
      saved:result.metrics, browser_total_ms:total, browser_generation_ms:request.first == null ? null : total-request.first});
    if (result.history_reload) result = await api("/api/chat/history?" + new URLSearchParams({chat_id:id}));
    view.messages = result.messages;
    view.draft = "";
    completed = true;
    view.retry = null;
    if (chatSelected === id) {
      input.value = "";
      const rendered = chatHolder.querySelectorAll(".chat-bubble");
      if (!result.cached && rendered.length === view.messages.length && view.messages.length >= 2) {
        const [user, assistant] = view.messages.slice(-2);
        request.user.querySelector("time").replaceWith(timestamp(user.created_at));
        request.assistant.append(timestamp(assistant.created_at));
        request.assistant.querySelector(".chat-text").textContent = assistant.content;
        const detail = request.assistant.querySelector(".reasoning-panel");
        detail.querySelector(".reasoning-text").textContent = assistant.reasoning_content || "";
        detail.classList.toggle("hidden", !assistant.reasoning_content || !byId("chat-show-reasoning").checked);
        followBottom();
      } else renderMessages(view.messages);
    }
  } catch (error) {
    const cancelled = request.cancelling || error.name === "AbortError";
    if (error.name !== "TypeError" || cancelled) view.retry = null;
    view.notice = cancelled ? "Запрос отменён." : "Ошибка ответа: " + controlReason(error.message);
    updateMetrics(view, {error:cancelled ? undefined : error.message, cancelled, browser_total_ms:performance.now()-request.started});
    if (chatSelected === id) setChatNotice(view.notice);
  } finally {
    view.request = null;
    if (!completed) {
      request.user.remove();
      request.assistant.remove();
      if (chatSelected === id && !chatHolder.children.length) renderMessages(view.messages);
    }
    const recheck = waitForSlot(target, view, request);
    renderTimer();
    if (chatSelected === id && byId("chat-statistics").open) loadStatistics(id);
    await recheck;
    if (restoreFocus && chatOpen && chatSelected === id && document.activeElement === document.body && !input.disabled) {
      input.focus({preventScroll:true});
    }
  }
}

byId("nav-overview").addEventListener("click", showOverview);
byId("nav-chats").addEventListener("click", showChats);
byId("chat-reload").addEventListener("click", () => refresh(true));
byId("chat-new").addEventListener("click", () => {
  const target = liveTarget(currentChat()) || (chatTargets.length === 1 ? chatTargets[0] : null);
  changeChat("create", target ? {target:targetFields(target)} : {});
});
byId("chat-target").addEventListener("change", event => {
  const target = chatTargets.find(item => targetKey(item) === event.target.value);
  changeChat("target", {target:target ? targetFields(target) : null});
});
byId("chat-rename").addEventListener("click", () => {
  const title = prompt("Название чата", currentChat()?.title);
  if (title?.trim()) changeChat("rename", {title});
});
for (const op of ["reset","resume","restore"]) byId("chat-"+op).addEventListener("click", () => changeChat(op));
byId("chat-clear").addEventListener("click", () => {
  if (confirm("Очистить переписку этого чата? Её можно вернуть через «Восстановить переписку».")) changeChat("clear", {confirm:true});
});
byId("chat-delete").addEventListener("click", () => {
  if (confirm("Удалить выбранный чат, всю его переписку и измерения? Восстановить чат через Client нельзя.")) changeChat("delete", {confirm:true});
});
for (const field of ["chat-history-messages","chat-history-chars"]) byId(field).addEventListener("change", () => {
  changeChat("settings", {context:{max_messages:Number(byId("chat-history-messages").value),
                                   max_chars:Number(byId("chat-history-chars").value)}});
});
byId("chat-statistics").addEventListener("toggle", event => {
  if (event.target.open && chatSelected) loadStatistics(chatSelected);
});
byId("chat-stat-model").addEventListener("change", filterStatistics);
byId("chat-stat-mode").addEventListener("change", filterStatistics);
setInterval(() => { if (chatOpen) renderTimer(); }, 150);
byId("chat-form").addEventListener("submit", submitChat);
byId("chat-input").addEventListener("input", event => {
  if (chatSelected) conversation(chatSelected).draft = event.target.value;
});
byId("chat-input").addEventListener("keydown", event => {
  if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey ||
      event.metaKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (event.repeat || byId("chat-send").disabled || !event.currentTarget.value.trim()) return;
  event.currentTarget.form.requestSubmit();
});
byId("chat-show-reasoning").addEventListener("change", () => {
  document.querySelectorAll(".reasoning-panel").forEach(detail => detail.classList.toggle("hidden",
    !byId("chat-show-reasoning").checked || !detail.querySelector(".reasoning-text").textContent));
  followBottom();
});
byId("chat-cancel").addEventListener("click", async () => {
  const request = chatSelected && conversation(chatSelected).request;
  if (!request?.controller || request.cancelling) return;
  request.cancelling = true;
  renderChatControls();
  try {
    await api("/api/chat/cancel", {method:"POST", signal:AbortSignal.timeout(5500),
      headers:{"Content-Type":"application/json","X-Ultra-CSRF":csrf},
      body:JSON.stringify({...targetFields(request.target), request_id:request.id})});
  } catch {
    // Closing the local stream also signals disconnection to the relay.
  } finally {
    request.controller.abort();
  }
});
byId("chat-popout").addEventListener("click", () => {
  if (!chatSelected) return;
  const url = new URL(window.location.href);
  url.hash = "chat=" + encodeURIComponent(chatSelected);
  window.open(url.toString(), "_blank", "noopener");
});
window.addEventListener("focus", () => { if (chatOpen) loadChatHistory(); });
