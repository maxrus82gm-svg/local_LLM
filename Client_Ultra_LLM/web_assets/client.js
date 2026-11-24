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
let statusReadsInFlight = 0;
let firstSetup = false;
let lastEnrolledManagerId = "";
let adminManagers = [];
let controlError = "";

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
    model_files_unverified:"Файлы и метаданные установленной модели не подтверждены Manager",
    runtime_or_model_changed:"Файлы runtime или метаданные модели изменились после проверки",
    resource_telemetry_unknown:"Нет достоверных данных о памяти и процессах сервера",
    vram_telemetry_unknown:"Нет достоверных данных о свободной VRAM",
    insufficient_ram:"Недостаточно свободной RAM с учётом резерва",
    low_vram_forecast:"Прогноз: возможна нехватка VRAM (запуск разрешён)",
    vram_estimate_unknown:"Оценка VRAM неизвестна",
    vram_reservation_unknown:"Оценка VRAM ожидающего запуска неизвестна",
    insufficient_vram:"Недостаточно свободной VRAM с учётом резерва",
    ram_estimate_unknown:"Оценка потребления RAM неизвестна",
    ram_estimate_unmeasured:"Оценка потребления RAM ещё не измерена",
    low_ram_forecast:"После запуска останется мало свободной RAM",
    job_cap_below_estimate:"Лимит процесса ниже оценки потребления",
    cuda_measurement_unverified:"Потребление VRAM этой моделью ещё не измерено",
    model_already_managed:"Для модели уже зарезервирован экземпляр",
    no_free_authorized_slot:"Нет свободного разрешённого слота",
    invalid_context_tokens:"Введите положительное целое число до шести цифр",
    invalid_cuda_profile:"Проверьте числа CUDA: положительный бюджет и порог либо пустое поле, блок 1–8192 или Auto",
    context_capacity_exceeded:"Контекст превышает заявленную ёмкость модели",
    context_capacity_unknown:"Максимальный контекст модели не подтверждён",
    context_override_unavailable:"Обновите Manager для управления контекстом из Client",
    context_length_exceeded:"Модель отклонила длину контекста. Уменьшите историю или сбросьте контекст этого чата",
    colibri_context_length_exceeded:"Модель отклонила длину контекста. Уменьшите историю или сбросьте контекст этого чата",
    chat_target_occupied:"Этот слот уже назначен другому чату",
    chat_target_not_assigned:"Назначьте этому чату свободный слот",
    slot_chat_in_progress:"Слот занят запросом",
    model_not_authorized:"Эта модель не разрешена клиенту",
    instance_not_authorized:"Экземпляр принадлежит другому клиенту или слот не разрешён",
    instance_not_stoppable:"Остановка недоступна до подтверждения состояния экземпляра",
    runner_action_unconfirmed:"Результат операции не подтверждён; слот защищён от повторного запуска",
    supervisor_unverified:"Владение процессом не подтверждено",
    state_file_winerror_5:"Windows заблокировала запись файла состояния",
    state_file_winerror_32:"Файл состояния занят другим процессом",
    state_file_winerror_33:"Файл состояния заблокирован",
    readiness_lost:"Потеря готовности движка",
    gateway_exited:"Процесс Gateway завершился",
    load_timeout:"Превышено время загрузки модели",
    stream_idle_timeout:"Нет новых фрагментов ответа в течение тайм-аута бездействия",
    runtime_or_telemetry_unverified:"Runtime или состояние сервера не подтверждены",
    restart_activity_unknown:"Нельзя подтвердить, что слот свободен",
    restart_guard_unavailable:"Manager ещё не поддерживает Restart",
    restart_port_not_free:"Порт модели не освободился",
    restart_resources_changed:"Ресурсы изменились после остановки",
    restart_stop_timeout:"Остановка модели не подтвердилась",
    restart_start_timeout:"Запуск модели не подтвердился",
    restart_interrupted:"Операция была прервана; автоматического повтора нет",
    restart_identity_changed:"Изменился экземпляр — повторный запуск запрещён",
    restart_not_found:"Операция Restart не найдена",
    restart_preflight_failed:"Проверка запуска не пройдена",
    runner_action_unconfirmed:"Результат операции не подтверждён"
  };
  return labels[reason] ? labels[reason] + " (" + reason + ")" : reason;
}
const slotPending=new Set();
function modelInstalled(model) { return model?.installation_checked === true && model?.files_present === true; }
function workspaces(container,manager) {
  const control=manager.data.control;
  const catalog=node("section","slot-catalog");
  catalog.append(node("h3","","МОДЕЛИ ИЗ ПРОФИЛЕЙ MANAGER"));
  for(const model of control.models || []) {
    const entry=node("div","catalog-entry");
    entry.append(node("strong","",model.name),node("small","",
      [modelInstalled(model) ? "Файлы и метаданные подтверждены" :
       model.installation_checked === true ? "Установка модели не подтверждена" : "Manager не подтвердил установку; требуется обновление Manager",
       model.runtime_checked ? "Предыдущая проверка runtime пройдена" : "Совместимость требует проверки",
       "Доступен старт: "+["cpu","cuda"].filter(mode=>model.modes?.[mode]?.available).map(mode=>mode.toUpperCase()).join(" / ")+(Object.values(model.modes || {}).some(m=>m.available) ? "" : "требуется допуск"),
       "Работает экземпляров: "+(model.running_instances || 0)].join(" · ")));
    catalog.append(entry);
  }
  if(!(control.models || []).length)catalog.append(node("p","manager-model-empty","Нет установленных моделей, разрешённых этому Client в Manager."));
  container.append(catalog);
  const area=node("section","working-slots");
  if (control.control_models === false || control.enabled === false) {
    area.append(node("p","manager-pairing-note",control.control_models === false ?
      "Просмотр разрешён. Для Start/Stop владелец Manager выдаёт этому зарегистрированному Client право control_models штатной командой set-control-models." :
      "Управление отключено на Manager: владелец проверяет control.owner_go, защищённый журнал и resource reviews перед штатным включением."));
  }
  const heading=node("div","manager-model-head");
  heading.append(node("h3","","РАБОЧИЕ СЛОТЫ · "+control.slots.length));
  const add=node("button","btn secondary small","＋ Добавить слот");
  add.type="button";add.classList.add("add-slot");add.disabled=!control.can_add_slot;
  add.dataset.tip=control.can_add_slot ? "Manager назначит слот и свободный порт" : "Необходимо разрешение управления на Manager";
  add.addEventListener("click",async()=>{add.disabled=true;try{
    await pairingPost("/api/control",{manager_id:manager.manager_id,op:"add_slot",request_id:crypto.randomUUID().replaceAll("-","")});
    controlError="";
    await refresh(true);
  }catch(e){controlError=controlReason(e.message);setNotice(controlError);add.disabled=!control.can_add_slot;}});
  heading.append(add);area.append(heading);
  const list=node("div","manager-model-scroll");
  for(const slot of control.slots) {
    const key=manager.manager_id+":"+slot.slot_id;
    const item=(control.instances || []).find(i=>i.slot_id===slot.slot_id&&!i.released);
    const previous=(control.instances || []).find(i=>i.slot_id===slot.slot_id&&i.released);
    const live=(manager.data.slots || []).find(i=>i.slot_id===slot.slot_id)||{};
    const line=node("div","manager-model-row working-slot");line.dataset.slotId=slot.slot_id;
    const info=node("div","manager-model-info");
    info.append(node("strong","",slot.slot_id+(slot.protected ? " · защищённый" : "")));
    const select=node("select","slot-model");select.setAttribute("aria-label","Модель "+slot.slot_id);
    select.append(node("option","","Выберите модель"));select.options[0].value="";
    for(const model of control.models || []){const option=node("option","",model.name+(modelInstalled(model) ? "" : " · не подтверждена"));option.value=model.key;option.disabled=!modelInstalled(model);select.append(option);}
    if(slot.protected) {
      const names=(live.models || []).join(", ");
      if(names){const option=node("option","",names);option.value="legacy";select.append(option);select.value="legacy";}
    }else select.value=slot.model_key || "";
    select.disabled=slot.protected||!slot.authorized||!control.control_models||!control.enabled||Boolean(item)||slotPending.has(key);
    const shown=item || (previous?.state==="ERROR" ? previous : null);
    // A saved mode is a preference, not a running backend. Only show a
    // running mode when READY agrees with live telemetry and instance identity.
    const confirmedReady=item?.state==="READY" && live.engine_state==="ready" &&
      Boolean(item.instance_id) && live.instance_id===item.instance_id;
    const running=confirmedReady || (slot.protected && live.engine_state==="ready");
    const stopped=!item && !shown && live.engine_state==="not_running";
    const slotState=running ? "running" : stopped ? "stopped" :
      shown?.state==="ERROR" ? "error" : shown?.state==="STARTING" ? "starting" :
      shown?.state==="STOPPING" ? "stopping" : "unknown";
    const stateNames={running:"Запущен",stopped:"Остановлен",error:"Ошибка",starting:"Запускается",stopping:"Останавливается",unknown:"Не подтверждён"};
    const status=node("span","slot-state "+slotState,stateNames[slotState]);
    status.dataset.tip=shown?.reason ? controlReason(shown.reason) : running && live.availability==="busy" ? "Запущен · выполняет запрос" :
      slot.protected ? "Внешний экземпляр" : slotState==="unknown" ? "Состояние процесса требует проверки" : stateNames[slotState];
    const activeMode=confirmedReady && ["cpu","cuda"].includes(item.mode) ? item.mode.toUpperCase() : "";
    const modeLabel=node("span","slot-active-mode"+(activeMode ? " active" : ""),activeMode || (running ? "?" : "—"));
    modeLabel.dataset.tip=activeMode ? "Фактический режим: "+activeMode : running ? "Режим работы не подтверждён" : "Нет подтверждённого активного режима";
    info.append(select);line.append(info);
    select.addEventListener("change",async()=>{
      if(!select.value)return;
      slotPending.add(key);select.disabled=true;
      try{await pairingPost("/api/control",{manager_id:manager.manager_id,op:"select",slot_id:slot.slot_id,
        model_key:select.value,mode:slot.mode,expected_revision:slot.revision,request_id:crypto.randomUUID().replaceAll("-","")});controlError="";}
      catch(e){controlError=controlReason(e.message);status.textContent="Ошибка";status.dataset.tip=controlError;setNotice(controlError);}
      finally{slotPending.delete(key);await refresh(true);}
    });
    const canStop=item?.can_stop===true && ["STARTING","READY"].includes(item.state);
    const selectedModel=(control.models || []).find(m=>m.key===slot.model_key);
    if(control.cuda_profiles===true && !item && !slot.protected && slot.authorized &&
        control.control_models && control.enabled && modelInstalled(selectedModel) && selectedModel?.modes?.cuda) {
      const settings=node("button","btn secondary small slot-cuda-config","⚙");
      settings.type="button";settings.disabled=slotPending.has(key);
      settings.dataset.tip="Настройки CUDA перед запуском "+slot.slot_id;
      settings.setAttribute("aria-label",settings.dataset.tip);
      settings.addEventListener("click",()=>openPrelaunchCuda(manager,slot));
      info.append(settings);
    }
    for(const title of ["Старт CPU", "Старт CUDA", "Стоп"]) {
      const mode=title==="Старт CPU" ? "cpu" : "cuda";
      const button=node("button","btn secondary small manager-model-action",title);button.type="button";
      const model=(control.models || []).find(m=>m.key===select.value);
      const capability=model?.modes?.[mode];
      button.disabled=slotPending.has(key)||(title==="Стоп" ? !canStop :
        Boolean(item)||slot.protected||!slot.authorized||!control.control_models||!control.enabled||!modelInstalled(model)||!capability?.available||live.engine_state!=="not_running");
      if(title!=="Стоп" && activeMode===mode.toUpperCase())button.classList.add("slot-mode-running");
      button.dataset.tip=title==="Стоп" ? (canStop ? "Остановить только этот экземпляр" : "Остановка недоступна в текущем состоянии экземпляра") :
        (!modelInstalled(model) ? "Установка модели не подтверждена Manager" : controlReason(capability?.reason)||"Проверить запуск в этом слоте");
      if(title!=="Стоп" && capability?.forecast) {
        const forecast=capability.forecast;
        button.dataset.tip+=" · Ожидаемый остаток RAM: "+(forecast.ram_after_gib===null ? "неизвестен" : formatNumber(forecast.ram_after_gib)+" GiB")+
          " · VRAM: "+(forecast.vram_after_gib===null ? "неизвестен" : formatNumber(forecast.vram_after_gib)+" GiB")+
          " · Оценка: "+forecast.estimate_evidence;
      }
      if(title!=="Стоп" && capability?.warnings?.length)button.dataset.tip+=" · "+capability.warnings.map(controlReason).join("; ");
      button.addEventListener("click",async()=>{
        slotPending.add(key);button.disabled=true;
        for(const input of line.querySelectorAll("select,button"))input.disabled=true;
        try {
          let body;
          if(title==="Стоп")body={op:"stop",instance_id:item.instance_id};
          else {
            const target={slot_id:slot.slot_id,model_key:select.value,mode};
            // Read persisted ownership immediately before the explicit slot start.
            const owners=(await api("/api/chats")).chats;
            const owner=[...owners].reverse().find(c=>!c.legacy && c.model_id &&
              c.manager_id===manager.manager_id && c.slot_id===slot.slot_id);
            if(owner?.context_tokens!=null) {
              if(control.context_override!==true)throw Error("context_override_unavailable");
              target.context_tokens=owner.context_tokens;
            }
            const checked=await pairingPost("/api/control",{manager_id:manager.manager_id,op:"check",...target,request_id:crypto.randomUUID().replaceAll("-","")});
            let ack=false;
            if(checked.requires_ack) {
              const forecast=checked.forecast;
              const details="Ожидаемый остаток RAM: "+(forecast.ram_after_gib===null ? "неизвестен" : formatNumber(forecast.ram_after_gib)+" GiB")+
                "; VRAM: "+(forecast.vram_after_gib===null ? "неизвестен" : formatNumber(forecast.vram_after_gib)+" GiB")+
                ". Достоверность: "+forecast.estimate_evidence+". Предупреждения: "+checked.warnings.join(", ");
              status.dataset.tip=details;
              if(!checked.risk_ack_allowed)throw Error("resource_risk_not_permitted");
              ack=confirm(details+". Возможны замедление других моделей и программ сервера. Подтвердить риск этого запуска?");
              if(!ack)return;
            }
            body={op:"start",...target,...(ack ? {risk_ack:true,risk_token:checked.risk_token} : {})};
          }
          const response=await pairingPost("/api/control",{manager_id:manager.manager_id,...body,request_id:crypto.randomUUID().replaceAll("-","")});
          controlError="";
          status.textContent=({STARTING:"Запускается",STOPPING:"Останавливается",READY:"Запущен",STOPPED:"Остановлен"})[response.state] || "Проверка";
        }catch(e){controlError=controlReason(e.message);status.textContent="Ошибка";status.dataset.tip=controlError;setNotice(controlError);}
        finally{slotPending.delete(key);await refresh(true);}
      });
      line.append(button);
    }
    const measured=item?.memory;
    const validMemory=Boolean(measured && Number.isFinite(measured.ram_gib) && measured.ram_gib>=0);
    const memoryLabel=node("span","slot-memory",item ?
      (validMemory ? "RAM "+measured.ram_gib.toFixed(1)+" ГиБ"+(item.mode==="cuda" ?
        " · VRAM "+(Number.isFinite(measured.vram_gib) ? measured.vram_gib.toFixed(1)+" ГиБ" : "—") : "") : "RAM —") : "—");
    memoryLabel.dataset.tip=validMemory ?
      "RAM: сумма рабочих наборов процессов экземпляра; общие страницы могут учитываться несколько раз. "+
      "Private commit: "+(Number.isFinite(measured.private_commit_gib)?measured.private_commit_gib.toFixed(1)+" ГиБ":"—")+
      ". VRAM — только данные драйвера; — означает нет данных." : "Нет подтверждённого измерения памяти этого экземпляра";
    const actualContext=running && Number.isSafeInteger(live.context_tokens) && live.context_tokens>0 ? live.context_tokens : null;
    const contextLabel=node("span","slot-context","Контекст "+(actualContext!=null ? actualContext.toLocaleString("ru-RU")+" ток." : "—"));
    contextLabel.dataset.tip=actualContext!=null ?
      "Фактическая ёмкость контекста работающего экземпляра по health. Не объём RAM/VRAM KV-кэша." :
      "Фактический контекст не подтверждён. Значение появится после готовности экземпляра и получения health.";
    line.append(status,modeLabel,memoryLabel,contextLabel);
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
      button.dataset.tip = "Обновите Manager для управления моделями";
      if (item.model) {
        const mode = title === "Старт CPU" ? "cpu" : "cuda";
        const own = item.active.find(i => i.can_stop);
        const capability = item.model.modes[mode] || {};
        button.disabled = title === "Стоп" ? !own : capability.available !== true;
        button.dataset.tip = title === "Стоп" ? (own ? "Остановить свой экземпляр " + own.instance_id :
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
  statusSampleTime=performance.now();
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
      "Не все Manager доступны. Проверьте сеть, сертификат и регистрацию этого компьютера." : controlError);
  if (chatOpen) renderChatList(payload);
}
async function refresh(force=false) {
  if (isRefreshing) {if(force===true)refreshQueued=true;return;}
  isRefreshing = true;
  const button = byId("refresh"); button.disabled = true;
  try {
    await readStatus();
  } catch (err) {
    // A late failed refresh must not invalidate a newer successful sample.
    if (!statusSampleTime) setNotice("Не удалось обновить данные: " + err.message);
  } finally {
    isRefreshing = false;
    button.disabled = false;
    if(refreshQueued){refreshQueued=false;await refresh(true);}
  }
}
async function readStatus(options) {
  const id = ++statusRequest;
  statusReadsInFlight++;
  try {
    const status = await api("/api/status", options);
    // Order completed outcomes, not requests that have merely been issued.
    // A newer pending GET must not discard a useful completed foreground read.
    if (id > appliedStatusRequest) {
      appliedStatusRequest = id;
      render(status);
    }
    // A later completed failure is also a watermark; do not use old READY.
    return statusSampleTime > 0 && performance.now()-statusSampleTime <= 7000;
  } catch (error) {
    if (id >= appliedStatusRequest) {
      appliedStatusRequest=id;
      statusSampleTime=0;
      if (chatOpen) renderChatControls();
      else renderLiveStatus();
    }
    throw error;
  } finally {
    statusReadsInFlight--;
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
// Foreground reads already refresh the full TLS Manager snapshot. Avoid
// adding periodic work while they or a slot-release check are in flight.
function backgroundStatus() {
  if (statusReadsInFlight || chatMutation || releasingSlots.size) return;
  void refresh();
}
setInterval(backgroundStatus, 25000);
setInterval(() => {
  if (chatOpen) {
    if (statusSampleTime && performance.now()-statusSampleTime > 7000) {
      statusSampleTime=0;
      renderChatControls();
    } else renderLiveStatus();
  }
  if (chatOpen || chatSnapshot?.managers?.some(m =>
    m.data?.control?.instances?.some(i => ["STARTING","STOPPING"].includes(i.state)))) backgroundStatus();
}, 2000);

/* CHAT-01: model slots are discovered dynamically from live Manager snapshots.
   They are never predefined as "three" or tied to hard-coded IP addresses. */
let chatSnapshot = null;
let statusSampleTime = 0;
let chatOpen = false;
let chatItems = [];
let chatSelected = "";
let chatTargets = [];
let streamMetrics = {};
let historyRevision = 0;
let chatMutation = false;
let chatRestartJob = null;
let chatRestartSuccess = null;
let chatRestartHold = null;
const RESTART_STAGE = {
  PENDING:"Ожидает подтверждения",
  RISK_CONFIRMATION_REQUIRED:"Ожидает подтверждения",
  STOPPING:"Остановка модели…",
  WAITING_RELEASE:"Ожидание освобождения…",
  CHECKING:"Проверка перед запуском…",
  STARTING:"Запуск модели…",
  READY:"Модель перезапущена",
  ERROR:"Ошибка Restart",
  UNKNOWN:"Состояние неизвестно"
};
function renderLiveStatus() {
  const badge=byId("chat-live-status");
  if (!badge) return;
  const chat=currentChat();
  let text="Не назначена",tone="neutral";
  if (chat?.manager_id && chat?.slot_id && chat?.model_id) {
    const manager=(chatSnapshot?.managers || []).find(m=>m.manager_id===chat.manager_id);
    const job=chatRestartJob?.chatId===chat.chat_id && chatRestartJob.managerId===chat.manager_id && chatRestartJob.slotId===chat.slot_id && chatRestartJob.modelId===chat.model_id ? chatRestartJob : null;
    const hold=chatRestartHold?.chatId===chat.chat_id && chatRestartHold.managerId===chat.manager_id && chatRestartHold.slotId===chat.slot_id && chatRestartHold.modelId===chat.model_id ? chatRestartHold : null;
    if (!manager || manager.status!=="online") {text="Нет связи";tone="neutral";}
    else if (!statusSampleTime || performance.now()-statusSampleTime>7000) {text="Состояние неизвестно";tone="neutral";}
    else if (job) {
      text=RESTART_STAGE[job.stage] || "Состояние неизвестно";
      tone=job.stage==="ERROR"?"error":job.stage==="UNKNOWN"?"neutral":
        ["PENDING","RISK_CONFIRMATION_REQUIRED"].includes(job.stage)?"pending":"progress";
    } else if (hold) {text=hold.type==="unknown"?"Состояние неизвестно":"Ошибка";tone=hold.type==="unknown"?"neutral":"error";}
    else {
      const slot=manager.data?.slots?.find(s=>s.slot_id===chat.slot_id);
      const control=manager.data?.control;
      const instances=Array.isArray(control?.instances)?control.instances:[];
      const current=instances.find(i=>i.slot_id===chat.slot_id && i.released===false);
      const exact=current && current.model_id===chat.model_id && slot?.instance_id===current.instance_id;
      const identityInModel=exact && chat.model_id.endsWith(current.instance_id);
      const pinKey="ultra.chat.instance."+chat.chat_id;
      const pinned=localStorage.getItem(pinKey);
      const knownIdentity=current && current.model_id===chat.model_id &&
        (chat.model_id.endsWith(current.instance_id) || pinned===current.instance_id);
      if (!slot || !control || !Array.isArray(control.instances) || chat.target_conflict) {text="Состояние неизвестно";}
      else if (current?.state==="ERROR" && knownIdentity) {text="Ошибка";tone="error";}
      else if (current?.state==="STOPPING" && knownIdentity) {text="Останавливается";tone="progress";}
      else if (current?.state==="STARTING" && knownIdentity) {text="Запускается";tone="progress";}
      else if (current && !exact) {text="Перепривяжите модель";tone="pending";}
      else if (current?.state==="ERROR") {text="Ошибка";tone="error";}
      else if (current?.state==="READY" && slot.engine_state==="ready" && exact && (identityInModel || pinned===current.instance_id)) {
        if (!pinned && identityInModel) localStorage.setItem(pinKey,current.instance_id);
        if (chatRestartSuccess?.chatId===chat.chat_id && chatRestartSuccess.managerId===chat.manager_id &&
            chatRestartSuccess.slotId===chat.slot_id && chatRestartSuccess.modelId===chat.model_id && chatRestartSuccess.instanceId===current.instance_id &&
            performance.now()<chatRestartSuccess.expiresAt) text="Перезапуск завершён";
        else text="Запущен";
        tone="ready";
      } else if (current?.state==="READY" && exact) {text="Перепривяжите модель";tone="pending";}
      else if (slot.engine_state==="not_running" && !current) {text="Остановлен";tone="stopped";}
      else if (instances.some(i=>i.slot_id===chat.slot_id && i.state==="ERROR")) {text="Ошибка";tone="error";}
      else {text="Состояние неизвестно";}
    }
  }
  if (badge.textContent!==text) badge.textContent=text;
  if (!badge.classList.contains(tone)) badge.className="chat-live-status "+tone;
}
function restartSelection(chat) {
  if (!chat || chat.legacy || chat.target_conflict) return null;
  const manager = (chatSnapshot?.managers || []).find(m => m.manager_id === chat.manager_id && m.status === "online");
  const control = manager?.data?.control;
  const slot = control?.slots?.find(s => s.slot_id === chat.slot_id);
  const instance = control?.instances?.find(i => i.slot_id === chat.slot_id &&
    i.model_id === chat.model_id && i.state === "READY" && i.released === false &&
    i.can_stop === true && ["cpu","cuda"].includes(i.mode));
  if (!control?.control_models || !slot || !Number.isInteger(slot.revision) || !instance) return null;
  return {instance_id:instance.instance_id, expected_revision:slot.revision};
}
async function restartState(job) {
  return api("/api/chat/restart?" + new URLSearchParams({
    chat_id:job.chatId, manager_id:job.managerId, request_id:job.requestId
  }), {signal:AbortSignal.timeout(9000)});
}
async function restartSelectedChat() {
  if (chatRestartJob || chatMutation) return;
  const chat = currentChat();
  const target = liveTarget(chat);
  const selection = restartSelection(chat);
  if (!selection || !assignedChatOwnsTarget(chat,target) || !chatReady(target) ||
      conversation(chat.chat_id).request || selectedManagerId(chat) !== chat.manager_id) return;
  if (!confirm("Перезапустить выбранную модель? Она будет остановлена и запущена снова с сохранёнными настройками.")) return;
  const job = {chatId:chat.chat_id,managerId:chat.manager_id,
    slotId:chat.slot_id,modelId:chat.model_id,requestId:crypto.randomUUID().replaceAll("-",""),stage:"PENDING"};
  chatRestartJob=job;
  chatRestartHold=null;
  renderChatControls();
  const body={chat_id:chat.chat_id,...targetFields(chat),...selection,request_id:job.requestId};
  let result;
  try {
    try { result=await pairingPost("/api/chat/restart",body); }
    catch(error){
      // Lost response may mean the operation was accepted. Never retry blindly.
      try { result=await restartState(job); }
      catch { throw Error("Невозможно подтвердить Restart: "+controlReason(error.message)); }
    }
    if(result.stage==="RISK_CONFIRMATION_REQUIRED"){
      job.stage="RISK_CONFIRMATION_REQUIRED";
      renderChatControls();
      const reasons=Array.isArray(result.warnings) ? result.warnings.map(controlReason).join(", ") : "";
      if(!confirm("Ресурсный прогноз требует отдельного подтверждения. "+
          (reasons ? reasons+". " : "")+"Продолжить?")) return;
      try { result=await pairingPost("/api/chat/restart",{...body,risk_ack:true,risk_token:result.risk_token}); }
      catch(error) {
        try { result=await restartState(job); }
        catch { throw Error("Состояние Restart неизвестно: "+controlReason(error.message)); }
      }
    }
    if(!["STOPPING","WAITING_RELEASE","CHECKING","STARTING","READY","ERROR"].includes(result.stage))
      throw Error("Manager не подтвердил запуск операции Restart");
    for(let attempt=0;attempt<450;attempt++){
      job.stage=result.stage;
      renderChatControls();
      if(result.stage==="READY"){
        // Mutating the chat binding is a CSRF-protected POST, never a GET poll.
        const complete=await pairingPost("/api/chat/restart/complete",{
          chat_id:job.chatId,manager_id:job.managerId,request_id:job.requestId
        });
        if(complete.stage!=="READY" || !complete.new_instance_id)
          throw Error("Менеджер не подтвердил новую привязку");
        await refresh(true);
        await syncChatBindings();
        chatRestartSuccess={chatId:job.chatId,managerId:job.managerId,slotId:job.slotId,
          modelId:chatItems.find(item=>item.chat_id===job.chatId)?.model_id || job.modelId,
          requestId:job.requestId,instanceId:complete.new_instance_id,expiresAt:performance.now()+3000};
        localStorage.setItem("ultra.chat.instance."+job.chatId,complete.new_instance_id);
        const success=chatRestartSuccess;
        setTimeout(()=>{if(chatRestartSuccess===success){chatRestartSuccess=null;renderLiveStatus();}},3000);
        if(chatSelected===job.chatId)setChatNotice("Модель перезапущена. История чата сохранена.");
        return;
      }
      if(result.stage==="ERROR")throw Error(controlReason(result.reason || "runner_action_unconfirmed"));
      await new Promise(resolve=>setTimeout(resolve,1000));
      try { result=await restartState(job); }
      catch(error){
        // Allow transient network loss, but never claim success without READY.
        if(attempt>=5)throw Error("Нет подтверждённого результата: "+controlReason(error.message));
      }
    }
    throw Error("Время ожидания истекло. Повторный запуск не выполнялся.");
  } catch(error) {
    chatRestartHold={chatId:job.chatId,managerId:job.managerId,slotId:job.slotId,modelId:job.modelId,
      requestId:job.requestId,type:/неизвестно|подтвердить|подтверждённого результата/i.test(error.message)?"unknown":"error"};
    if(chatSelected===job.chatId)setChatNotice("Restart: "+error.message);
  } finally {
    if(chatRestartJob===job)chatRestartJob=null;
    renderChatControls();
  }
}
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
  requestAnimationFrame(updateComposerPosition);
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
function modelName(id) {
  if (/kat[-_ ]?coder|(^|[-_ ])kat($|[-_ ])/i.test(id || "")) return "KAT-Coder V2.5 Dev";
  if (/qwen[-_ ]?3[._-]?6|qwen36/i.test(id || "")) return "Qwen 3.6";
  return /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(id || "") ? "Модель" : String(id || "Модель").slice(0, 40);
}
function modelLabel(target) {
  return modelName(target.model_id) + (target.slot_id ? ` · ${target.slot_id}` : "");
}
function actualChatMode(target) {
  return target?.engine_state === "ready" && ["cpu","cuda"].includes(target.mode) ? target.mode.toUpperCase() : "";
}
function selectedManagerId(chat) {
  if (!chat) return "";
  return sessionStorage.getItem("ultra.chat.manager." + chat.chat_id) ?? chat.manager_id ?? "";
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
function slotChatOwner(target) {
  if (!target?.manager_id || !target?.slot_id) return null;
  return [...chatItems].reverse().find(c => !c.legacy && c.model_id && slotKey(c)===slotKey(target)) || null;
}
function assignedChatOwnsTarget(chat, target) {
  return Boolean(chat && target && !chat.legacy && !chat.target_conflict &&
    targetKey(chat)===targetKey(target) && slotChatOwner(target)?.chat_id===chat.chat_id);
}
function targetAvailableToChat(target, chat) {
  if (target?.engine_state !== "ready" || target.availability === "denied") return false;
  const owner = slotChatOwner(target);
  return owner ? owner.chat_id===chat?.chat_id : chatReady(target);
}
// Only new chats receive automatic assignments. Keep the ordering from the
// overview (Manager order, then its slot order), never sort by model name.
function automaticChatPlan() {
  const managers = (chatSnapshot?.managers || []).filter(m => m.status === "online" && typeof m.manager_id === "string");
  const candidates = managers.flatMap(m => chatTargets.filter(t =>
    t.manager_id === m.manager_id && !slotChatOwner(t) && chatReady(t)));
  return {managerId:candidates[0]?.manager_id || managers[0]?.manager_id || "", candidates};
}
async function createAutomatically(values) {
  // Refresh the stored assignments, then live state; stale requests may not
  // override a newer snapshot. The SQLite owner gate is the final arbiter.
  chatItems = (await api("/api/chats")).chats;
  let plan;
  try {
    if (!await readStatus()) throw Error("status_not_current");
    plan = automaticChatPlan();
  } catch {
    plan = {managerId:"", candidates:[]};
  }
  const attempted = new Set();
  for (const target of plan.candidates) {
    const key = slotKey(target);
    if (attempted.has(key) || slotChatOwner(target) || !chatReady(target)) continue;
    attempted.add(key);
    try {
      const row = await pairingPost("/api/chats", {op:"create", ...values, target:targetFields(target)});
      return {row, managerId:target.manager_id};
    } catch (error) {
      if (error.message !== "chat_target_occupied") throw error;
      // This 409 means no chat was created. Do not retry ambiguous failures.
      chatItems = (await api("/api/chats")).chats;
    }
  }
  const row = await pairingPost("/api/chats", {op:"create", ...values});
  return {row, managerId:plan.managerId};
}
function chatReady(target) {
  return statusSampleTime > 0 && performance.now()-statusSampleTime <= 7000 &&
    target?.engine_state === "ready" && target.availability === "ready_unreserved" &&
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
const chatActionIcons = {
  rename:'<path d="m3 17 1 4 4-1L19 9l-4-4L4 16l-1 1Z"/><path d="m13 7 4 4"/>',
  reset:'<path d="M3 11a9 9 0 1 1 2.6 6.4"/><path d="M3 4v7h7"/>',
  clear:'<path d="m4 16 9-12 7 6-9 12H5l-1-6Z"/><path d="m8 11 8 6"/>',
  delete:'<path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6"/>',
  resume:'<path d="M20 12H6m0 0 5-5m-5 5 5 5"/><path d="M3 5v14"/>',
  restore:'<path d="M3 12a9 9 0 1 0 2.6-6.4"/><path d="M3 4v7h7"/><path d="M12 7v5l3 2"/>'
};
const chatActionNames = {
  rename:"Переименовать чат",reset:"Сбросить контекст",clear:"Очистить переписку",
  delete:"Удалить чат",resume:"Вернуть полный контекст",restore:"Восстановить переписку"
};
function chatActionButton(op, chat) {
  const button = node("button", "chat-action chat-action-" + op);
  button.type = "button";
  button.dataset.tip = chatActionNames[op];
  button.setAttribute("aria-label", chatActionNames[op]);
  button.dataset.action = op;
  button.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${chatActionIcons[op]}</svg>`;
  button.disabled = chatMutation || Boolean(conversation(chat.chat_id).request) ||
    (op === "resume" && !chat.context_after) || (op === "restore" && !chat.can_restore);
  button.addEventListener("click", () => runChatAction(op, chat.chat_id));
  return button;
}
function runChatAction(op, id) {
  const chat = chatItems.find(item => item.chat_id === id);
  if (!chat || chatMutation || conversation(id).request) return;
  if (op === "resume" && !chat.context_after || op === "restore" && !chat.can_restore) return;
  if (op === "rename") {
    const title = prompt("Название чата", chat.title);
    if (title?.trim()) changeChat(op, {title}, id);
  } else if (op === "clear") {
    if (confirm(`Очистить переписку чата «${chat.title}»? Её можно вернуть через «Восстановить переписку».`))
      changeChat(op, {confirm:true}, id);
  } else if (op === "delete") {
    if (confirm(`Удалить чат «${chat.title}», всю его переписку и измерения? Восстановить чат через Client нельзя.`))
      changeChat(op, {confirm:true}, id);
  } else changeChat(op, {}, id);
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
          mode:slot.engine_state === "ready" && slot.instance_id ? (manager.data.control?.instances?.find(row => !row.released && row.state === "READY" && row.instance_id === slot.instance_id)?.mode || "") : "",
          streaming:manager.data.chat?.streaming === true, engine_state:slot.engine_state,
          availability:slot.availability, transport:manager.data.chat?.transport_policy,
          context_tokens:slot.context_tokens, live_telemetry:manager.data.chat?.live_telemetry===true
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
    const card = node("div", "chat-choice" + (chat.chat_id === chatSelected ? " active" : "") +
      (assignedChatOwnsTarget(chat,liveTarget(chat)) && chatReady(liveTarget(chat)) ? " is-ready" : ""));
    card.dataset.chatId = chat.chat_id;
    const select = node("button", "chat-choice-select");
    select.type = "button";
    select.setAttribute("aria-label", "Открыть чат " + chat.title);
    const target = liveTarget(chat);
    const model = node("small", "chat-card-model", chat.model_id ?
      (target ? modelLabel(target) : modelLabel(chat) + " · недоступна") : "");
    const mode = assignedChatOwnsTarget(chat,target) ? actualChatMode(target) : "";
    if (mode) model.append(chatModeBadge(mode));
    select.append(node("b", "", chat.title), model);
    if (view.request) card.append(node("small", "", "Модель отвечает"));
    select.addEventListener("click", () => selectChat(chat.chat_id));
    const actions = node("div", "chat-action-row");
    const primary = node("div", "chat-action-group");
    const recovery = node("div", "chat-action-group chat-action-recovery");
    for (const op of ["rename","reset","clear","delete"]) primary.append(chatActionButton(op, chat));
    for (const op of ["resume","restore"]) recovery.append(chatActionButton(op, chat));
    actions.append(primary, recovery);
    card.append(select, actions);
    list.append(card);
  }
  list.scrollTop = scroll;
  renderChatControls();
}
function renderChatControls() {
  const chat = currentChat();
  const target = liveTarget(chat);
  const active = chat && conversation(chat.chat_id).request;
  const restarting = Boolean(chat && chatRestartJob?.chatId===chat.chat_id);
  const restartOption = restartSelection(chat);
  const managerSelector = byId("chat-manager");
  const modelSelector = byId("chat-model");
  const managerId = selectedManagerId(chat);
  const owns = assignedChatOwnsTarget(chat,target);
  const value = owns && managerId === chat.manager_id ? targetKey(chat) : "";
  const choices = chatTargets.filter(item => targetAvailableToChat(item,chat));
  const managers = new Map((Array.isArray(chatSnapshot?.managers) ? chatSnapshot.managers : [])
    .filter(item => typeof item.manager_id === "string")
    .map(item => [item.manager_id, (item.name || item.manager_id) +
      (item.status === "online" ? "" : " \u00b7 offline")]));
  if (managerId && !managers.has(managerId)) managers.set(managerId, managerId + " · недоступен");
  managerSelector.replaceChildren(new Option("Выберите Manager", ""),
    ...[...managers].map(([id, name]) => new Option(name, id)));
  managerSelector.value = managerId;
  managerSelector.disabled = !chat || Boolean(active) || restarting || chatMutation;
  const options = [];
  for (const item of choices.filter(item => item.manager_id === managerId && item.engine_state === "ready")) {
    options.push(new Option(modelLabel(item), targetKey(item)));
  }
  modelSelector.replaceChildren(...options);
  modelSelector.value = value;
  modelSelector.disabled = !chat || !managerId || !options.length || Boolean(active) || restarting || chatMutation;
  byId("chat-detach-model").classList.toggle("hidden", !chat?.model_id);
  byId("chat-detach-model").disabled = !chat || Boolean(active) || restarting || chatMutation;
  const mode = owns && managerId === chat?.manager_id ? actualChatMode(target) : "";
  byId("chat-active-mode").replaceChildren(...(mode ? [chatModeBadge(mode)] : []));
  byId("chat-title").textContent = chat?.title || "Выберите чат";
  byId("chat-subtitle").textContent = chat?.context_after ? "Контекст начинается после сброса" : "";
  byId("chat-popout").disabled = !chat;
  byId("chat-new").disabled = chatMutation || loadingChats;
  byId("chat-input").disabled = !chat || Boolean(active) || restarting;
  const send = byId("chat-send");
  send.type = active ? "button" : "submit";
  const canCancel = Boolean(active?.controller);
  const icon = canCancel ? "stop" : "enter";
  if (send.dataset.icon !== icon) {
    send.dataset.icon = icon;
    send.innerHTML = icon === "stop" ? '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>' : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 5v9H5m6-6-6 6 6 6"/></svg>';
  }
  const sendLabel = canCancel ? (active.cancelling ? "Остановка…" : "Стоп") : "Отправить (Enter)";
  send.dataset.tip = sendLabel;
  send.setAttribute("aria-label", sendLabel);
  send.disabled = active ? !active.controller || Boolean(active.cancelling) :
    !owns || !chatReady(target) || restarting || chatMutation || managerId !== chat.manager_id;
  byId("chat-stream").disabled = !chat || Boolean(active) || restarting || chatMutation || Boolean(target && !target.streaming);
  byId("chat-thinking").disabled = !chat || Boolean(active) || restarting || chatMutation || Boolean(target && !target.streaming);
  byId("chat-thinking-tip").dataset.tip = target && !target.streaming ? "Этот Manager не сообщает поддержку параметров генерации." : "Включает режим рассуждения у поддерживаемых моделей.";
  byId("chat-effort").disabled = !chat || Boolean(active) || restarting || chatMutation || !byId("chat-thinking").checked || Boolean(target && !target.streaming);
  renderContextSize(chat,target,!chat || Boolean(active) || restarting || chatMutation || Boolean(chat?.legacy));
  const restartButton=byId("chat-restart");
  restartButton.disabled = !owns || !chatReady(target) || !restartOption ||
    Boolean(active) || Boolean(chatRestartJob) || chatMutation || managerId!==chat?.manager_id;
  restartButton.dataset.tip = restarting ? RESTART_STAGE[chatRestartJob.stage] :
    "Применить сохранённые настройки: перезапустить модель";
  renderCudaPanel(chat,target);
  const status = byId("chat-state");
  if (active) status.textContent = active.cancelling ? "Отменяем запрос…" : "Модель отвечает";
  else if (restarting) status.textContent = RESTART_STAGE[chatRestartJob.stage] || "Перезапуск…";
  else if (!chat) status.textContent = "";
  else if (managerId !== chat.manager_id || !chat.model_id || chat.legacy) status.textContent = "";
  else if (slotChatOwner(chat)?.chat_id!==chat.chat_id) status.textContent = "Слот уже назначен другому чату.";
  else if (target && (releasingSlots.has(slotKey(target)) || target.availability === "busy" || localSlotActive(target))) {
    status.textContent = "Модель занята. Ожидаем освобождения слота.";
  } else status.textContent = chatReady(target) ? "" : "Назначенная модель сейчас недоступна.";
  renderLiveStatus();
}
const CONTEXT_PRESETS = ["2048","4096","8192","16384","32768","65536"];
let contextCustomDraft = false;
function showContextCustom(show) {
  byId("chat-context-preset").classList.toggle("hidden",show);
  byId("chat-context-custom").classList.toggle("hidden",!show);
  byId("chat-context-list").classList.toggle("hidden",!show);
}
function syncContextSize(chat) {
  const actual=liveTarget(chat)?.context_tokens;
  const value=String(chat?.context_tokens ?? (Number.isInteger(actual) && actual>0 ? actual : 65536));
  const preset=CONTEXT_PRESETS.includes(value);
  contextCustomDraft=false;
  byId("chat-context-preset").value=preset ? value : "custom";
  byId("chat-context-custom").value=preset ? "" : value;
  showContextCustom(!preset);
}
function contextPending(chat,target) {
  return Boolean(chat?.context_tokens!=null && target?.engine_state==="ready" &&
    target.context_tokens!==chat.context_tokens);
}
function renderContextSize(chat,target,disabled) {
  for(const id of ["chat-context-preset","chat-context-custom","chat-context-list"])byId(id).disabled=disabled;
  // A chat without an explicit preference follows the confirmed running size.
  if(!contextCustomDraft && chat?.context_tokens==null && Number.isInteger(target?.context_tokens) &&
     document.activeElement!==byId("chat-context-custom"))syncContextSize(chat);
  const tip=byId("chat-context-tip");
  const actual=Number.isInteger(target?.context_tokens) ? target.context_tokens : "не подтверждён";
  const pending=contextPending(chat,target);
  tip.classList.toggle("pending",pending);
  tip.dataset.tip="Контекст модели (токены), не история сообщений. Фактически: "+actual+
    ". Изменение применяется после ручного Стоп и Старт назначенного слота; затем выберите новый экземпляр в этом чате.";
  renderChatContextSummary(chat,target,pending);
}
function renderChatContextSummary(chat,target,pending) {
  const actual=chat && target?.engine_state==="ready" && Number.isInteger(target.context_tokens) && target.context_tokens>0 ? target.context_tokens : null;
  const desired=chat?.context_tokens ?? null;
  const values={
    "chat-context-actual":actual!=null ? actual+" ток." : "Нет данных",
    "chat-context-desired":desired!=null ? desired+" ток." : chat ? "По профилю" : "—",
    "chat-context-kv":"Нет данных"
  };
  for(const [id,value] of Object.entries(values)) {
    const el=byId(id);
    if(el.textContent!==value) el.textContent=value;
  }
  const warning=byId("chat-context-pending");
  const message=pending ? (actual==null ?
    "Фактический размер не подтверждён. Для применения выбранного контекста требуется перезапуск LLM." :
    "Требуется перезапуск LLM: Стоп → Старт назначенного слота, затем выберите новый экземпляр в этом чате. Manager перезапускать не нужно.") : "";
  if(warning.textContent!==message) warning.textContent=message;
  warning.classList.toggle("hidden",!message);
}
/* Settings belong to the Manager's slot/model, not a browser chat draft. */
let cudaFormKey="", cudaRevision=null, cudaDirty=false, cudaSaving=false, cudaStatusText="";
let cudaSample=null, cudaPollBusy=false;
const cudaInputIds=["cuda-budget","cuda-chain","cuda-rows","cuda-target"];
function cudaBinding(chat,target) {
  if (!chat?.manager_id || chat.legacy || selectedManagerId(chat)!==chat.manager_id ||
      slotChatOwner(chat)?.chat_id!==chat.chat_id) return null;
  const manager=chatSnapshot?.managers?.find(m=>m.manager_id===chat.manager_id&&m.status==="online");
  const control=manager?.data?.control;
  if (control?.cuda_profiles!==true) return null;
  const slot=control.slots?.find(s=>s.slot_id===chat.slot_id&&s.authorized&&!s.protected&&s.mode==="cuda");
  const instance=control.instances?.find(i=>i.slot_id===chat.slot_id&&i.model_id===chat.model_id&&i.mode==="cuda");
  if(!slot || !instance || instance.model_key!==slot.model_key) return null;
  return {manager,control,slot,instance,key:JSON.stringify([chat.manager_id,slot.slot_id,slot.model_key])};
}
function put(id,value) {
  const el=byId(id),text=String(value);
  if(el.textContent!==text)el.textContent=text;
}
function gib(x) {return Number.isFinite(x) ? x.toFixed(2)+" ГиБ" : "—";}
function readCudaProfile(budget,chain,rows,target) {
  return {budget_gib:budget.value===""?null:Number(budget.value),chain:chain.value==="on",
          rows:rows.value===""?null:Number(rows.value),target_gib:target.value===""?null:Number(target.value)};
}
function validCudaProfile(profile,inputs) {
  return !inputs.some(input=>input.validity.badInput)&&
    (profile.target_gib===null||(Number.isFinite(profile.target_gib)&&profile.target_gib>0&&profile.target_gib<=1024))&&
    (profile.budget_gib===null||(Number.isFinite(profile.budget_gib)&&profile.budget_gib>0&&profile.budget_gib<=1024))&&
    (profile.rows===null||(Number.isInteger(profile.rows)&&profile.rows>=1&&profile.rows<=8192));
}
function cudaProfileFromForm() {
  return readCudaProfile(byId("cuda-budget"),byId("cuda-chain"),byId("cuda-rows"),byId("cuda-target"));
}
function openPrelaunchCuda(manager,slot) {
  if(byId("cuda-prelaunch-dialog"))return;
  const control=manager.data.control;
  const profile=slot.cuda_profile||control.cuda_defaults;
  const dialog=node("dialog","");
  dialog.id="cuda-prelaunch-dialog";
  dialog.setAttribute("aria-label","Настройки CUDA "+slot.slot_id);
  const panel=node("div","dialog-content");
  panel.append(node("h3","","Настройки CUDA · "+slot.slot_id),node("p","manager-pairing-note",
    "Для следующего явного запуска CUDA. CPU и текущие экземпляры не изменяются. Порог VRAM — предупреждение, не ограничитель."));
  const form=node("form","");
  const fields=node("div","form-grid");
  function field(title,input) {
    const label=node("label","field");label.append(node("span","",title),input);fields.append(label);
    return input;
  }
  function num(id,value,min,max,step,placeholder="") {
    const input=node("input","");input.id=id;input.type="number";input.min=min;input.max=max;
    input.step=step;input.placeholder=placeholder;input.value=value??"";return input;
  }
  const budget=field("Бюджет весов, ГиБ",num("pre-cuda-budget",profile.budget_gib,0.1,1024,0.1,"Auto"));
  const chain=node("select","slot-model");chain.id="pre-cuda-chain";
  chain.append(new Option("Выкл.","off"),new Option("Вкл.","on"));chain.value=profile.chain?"on":"off";
  field("CUDA Chain",chain);
  const rows=field("Блок чтения",num("pre-cuda-rows",profile.rows,1,8192,1,"Auto"));
  rows.disabled=chain.value==="off";chain.addEventListener("change",()=>{rows.disabled=chain.value==="off";});
  const target=field("Порог VRAM, ГиБ",num("pre-cuda-target",profile.target_gib,0.1,1024,0.1,"Без порога"));
  const preview=node("p","manager-pairing-note");
  function previewMemory(){
    const gpu=performance.now()-statusSampleTime<20000?control.gpu:null;
    const free=Number.isFinite(gpu?.free_gib)?gpu.free_gib:null;
    const total=Number.isFinite(gpu?.total_gib)?gpu.total_gib:null;
    const b=budget.value===""?null:Number(budget.value);
    preview.textContent="GPU 0: свободно "+gib(free)+" из "+gib(total)+
      ". Бюджет весов: "+(b===null?"Auto":gib(b))+
      ". Полное потребление (включая KV/Chain и буферы) до замера неизвестно."+
      (free!==null&&Number.isFinite(b)&&b>free?" Внимание: бюджет выше текущей свободной VRAM; сохранение разрешено.":"");
  }
  budget.addEventListener("input",previewMemory);previewMemory();
  const error=node("div","form-error hidden");error.setAttribute("role","status");
  const actions=node("div","dialog-actions");
  const cancel=node("button","btn secondary","Отмена");cancel.type="button";
  const save=node("button","btn primary","Сохранить");save.type="submit";
  save.id="pre-cuda-save";
  actions.append(cancel,save);form.append(fields,preview,error,actions);panel.append(form);dialog.append(panel);
  let saving=false;
  cancel.addEventListener("click",()=>dialog.close());
  dialog.addEventListener("cancel",event=>{if(saving)event.preventDefault();});
  dialog.addEventListener("close",()=>dialog.remove());
  form.addEventListener("submit",async event=>{
    event.preventDefault();if(saving)return;
    const next=readCudaProfile(budget,chain,rows,target);
    if(!validCudaProfile(next,[budget,chain,rows,target])){
      error.textContent=controlReason("invalid_cuda_profile");error.classList.remove("hidden");return;
    }
    saving=true;save.disabled=cancel.disabled=true;error.classList.add("hidden");
    try {
      const saved=await pairingPost("/api/control",{manager_id:manager.manager_id,op:"cuda_settings",
        slot_id:slot.slot_id,model_key:slot.model_key,expected_revision:slot.revision,cuda_profile:next,
        request_id:crypto.randomUUID().replaceAll("-","")});
      if(saved.state!=="CUDA_SETTINGS_SAVED"||saved.slot_id!==slot.slot_id||saved.model_key!==slot.model_key)
        throw Error("invalid_control_response");
      dialog.close();await refresh(true);
    }catch(e){error.textContent=controlReason(e.message);error.classList.remove("hidden");}
    finally{saving=false;save.disabled=cancel.disabled=false;}
  });
  document.body.append(dialog);dialog.showModal();
}
function setCudaInputs(profile) {
  byId("cuda-budget").value=profile.budget_gib ?? "";
  byId("cuda-chain").value=profile.chain?"on":"off";
  byId("cuda-rows").value=profile.rows ?? "";
  byId("cuda-target").value=profile.target_gib ?? "";
}
function sameLaunchProfile(a,b) {
  return Boolean(a&&b&&a.budget_gib===b.budget_gib&&a.chain===b.chain&&a.rows===b.rows);
}
function renderCudaPanel(chat,target) {
  const binding=cudaBinding(chat,target), panel=byId("chat-cuda-panel");
  panel.classList.toggle("hidden",!binding);
  if(!binding){cudaFormKey="";cudaDirty=false;cudaSample=null;return;}
  const {control,slot,instance,key}=binding;
  if(cudaFormKey!==key){cudaFormKey=key;cudaDirty=false;cudaStatusText="";cudaSample=null;}
  if(!cudaDirty&&!cudaSaving) {
    setCudaInputs(slot.cuda_profile || control.cuda_defaults);
    cudaRevision=slot.revision;
  }
  const mayEdit=control.control_models===true && (instance.released||instance.can_stop);
  for(const id of cudaInputIds)byId(id).disabled=!mayEdit||cudaSaving;
  byId("cuda-rows").disabled=!mayEdit||cudaSaving||byId("cuda-chain").value==="off";
  byId("cuda-save").disabled=!mayEdit||cudaSaving||Boolean(chatRestartJob && chatRestartJob.chatId===chat?.chat_id);
  byId("cuda-reset").disabled=!cudaDirty||cudaSaving;
  put("cuda-slot-label",slot.slot_id);
  const applied=instance.cuda_profile;
  let message=slot.cuda_profile ? (!instance.released&&!sameLaunchProfile(slot.cuda_profile,applied) ?
    "Сохранено: для бюджета/Chain/блока нужен Стоп → Старт LLM." :
    (instance.released?"Сохранено для следующего запуска.":"Профиль запуска применён.")) :
    "Профиль по умолчанию для следующего запуска. Действующий экземпляр не изменён.";
  if(applied&&!instance.released)message+=" Сейчас: "+(applied.budget_gib??"Auto")+" ГиБ · Chain "+(applied.chain?"вкл.":"выкл.") +
    (applied.chain?" · блок "+(applied.rows??"Auto"):"")+".";
  if(cudaDirty)message="Есть несохранённые изменения. "+message;
  put("cuda-save-status",cudaStatusText||message);
  const sample=cudaSample?.identity===instance.instance_id&&performance.now()-cudaSample.at<8000?cudaSample.data:null;
  const snapshotAge=performance.now()-statusSampleTime;
  const gpu=sample?sample.gpu:snapshotAge<20000?control.gpu:null;
  const mem=instance.released?null:sample?sample.memory:snapshotAge<20000?instance.memory:null;
  const total=Number.isFinite(gpu?.total_gib)&&gpu.total_gib>0?gpu.total_gib:null;
  const used=Number.isFinite(gpu?.used_gib)?gpu.used_gib:null;
  put("cuda-total",used!=null&&total!=null?used.toFixed(2)+" / "+gib(total):"Нет данных");
  put("cuda-dedicated",gib(mem?.vram_gib));
  put("cuda-shared",gib(mem?.vram_shared_gib));
  put("cuda-ram",gib(mem?.ram_gib));
  const threshold=(slot.cuda_profile || control.cuda_defaults)?.target_gib;
  const over=used!=null&&Number.isFinite(threshold)&&used>=threshold;
  byId("cuda-meter-fill").style.width=total&&used!=null?Math.max(0,Math.min(100,used/total*100))+"%":"0%";
  byId("cuda-meter-fill").classList.toggle("warning",over);
  const free=Number.isFinite(gpu?.free_gib)?gpu.free_gib:null;
  const draftBudget=cudaProfileFromForm().budget_gib;
  const memoryHint=" Свободно: "+gib(free)+". Полное потребление нового профиля неизвестно до замера."+(free!==null&&Number.isFinite(draftBudget)&&draftBudget>free?" Бюджет выше текущей свободной VRAM; сохранение разрешено.":"");
  put("cuda-telemetry-warning",(over?"Внимание: GPU достиг порога "+gib(threshold)+". Модель не остановлена автоматически.":
    used==null?"Измерение GPU сейчас недоступно.":
    total!=null&&threshold>total?"Порог выше физической VRAM.":threshold==null?"Последний замер GPU 0; ручной порог отключён.":"Последний замер GPU 0; порог — "+gib(threshold)+".")+memoryHint);
}
for(const id of cudaInputIds)byId(id).addEventListener("input",()=>{
  cudaDirty=true;cudaStatusText="";renderCudaPanel(currentChat(),liveTarget(currentChat()));
});
byId("cuda-reset").addEventListener("click",()=>{
  cudaDirty=false;cudaStatusText="";renderCudaPanel(currentChat(),liveTarget(currentChat()));
});
byId("cuda-save").addEventListener("click",async()=>{
  const binding=cudaBinding(currentChat(),liveTarget(currentChat()));
  if(!binding||cudaSaving)return;
  const {manager,slot,key}=binding, profile=cudaProfileFromForm();
  if(!validCudaProfile(profile,cudaInputIds.map(id=>byId(id)))) {
    cudaStatusText=controlReason("invalid_cuda_profile");renderCudaPanel(currentChat(),liveTarget(currentChat()));return;
  }
  cudaSaving=true;cudaStatusText="Сохраняем на Manager…";renderCudaPanel(currentChat(),liveTarget(currentChat()));
  try{
    const saved=await pairingPost("/api/control",{manager_id:manager.manager_id,op:"cuda_settings",slot_id:slot.slot_id,
      model_key:slot.model_key,expected_revision:cudaRevision,cuda_profile:profile,request_id:crypto.randomUUID().replaceAll("-","")});
    if(saved.state!=="CUDA_SETTINGS_SAVED"||saved.slot_id!==slot.slot_id||saved.model_key!==slot.model_key)throw Error("invalid_control_response");
    if(cudaFormKey===key){cudaDirty=false;cudaStatusText="";}
    slot.cuda_profile=saved.cuda_profile;slot.revision=saved.revision;
    await refresh(true);
  }catch(error){if(cudaFormKey===key)cudaStatusText="Ошибка: "+controlReason(error.message);}
  finally{cudaSaving=false;renderCudaPanel(currentChat(),liveTarget(currentChat()));}
});
async function pollCuda() {
  if(!chatOpen||cudaPollBusy)return;
  const b=cudaBinding(currentChat(),liveTarget(currentChat()));
  if(!b||b.instance.released)return;
  cudaPollBusy=true;
  try{
    const values={manager_id:b.manager.manager_id,slot_id:b.slot.slot_id,instance_id:b.instance.instance_id};
    const data=await api("/api/control/cuda_status?"+new URLSearchParams(values),{signal:AbortSignal.timeout(6500)});
    if(cudaFormKey===b.key&&data.instance_id===b.instance.instance_id)
      cudaSample={identity:data.instance_id,data,at:performance.now()};
  }catch{
    if(cudaFormKey===b.key)cudaSample={identity:b.instance.instance_id,data:{gpu:null,memory:null},at:performance.now()};
  }finally{
    cudaPollBusy=false;
    if(chatOpen)renderCudaPanel(currentChat(),liveTarget(currentChat()));
  }
}
function applyChatPreferences(chat) {
  byId("chat-stream").checked = chat?.preferences?.stream ?? true;
  byId("chat-thinking").checked = chat?.preferences?.thinking ?? true;
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
  applyChatPreferences(chat);
  syncContextSize(chat);
  let effort = "auto";
  if (chat) {
    try { effort = localStorage.getItem("ultra.chat.effort." + chat.chat_id) || "auto"; } catch {}
  }
  byId("chat-effort").value = ["auto","low","medium","high","xhigh"].includes(effort) ? effort : "auto";
  byId("chat-history-messages").value = chat?.settings.max_messages ?? 100;
  byId("chat-history-chars").value = chat?.settings.max_chars ?? 200000;
  setChatNotice(view.notice);
  followStream = true;
  updateComposerPosition();
  renderMessages(view.messages, view.request);
  byId("chat-latest").classList.add("hidden");
  renderChatList(chatSnapshot);
  updateMetrics(view);
  renderTimer();
  renderStatistics([]);
  if (chat && !view.request) loadChatHistory();
  if (chat) loadStatistics(id);
}
async function changeChat(op, values = {}, id = chatSelected) {
  if (chatMutation || (chatRestartJob?.chatId===id && op!=="create") ||
      (op !== "create" && (!chatItems.some(item => item.chat_id === id) || conversation(id).request))) return;
  chatMutation = true;
  renderChatList(chatSnapshot);
  try {
    const automatic = op === "create" && !Object.prototype.hasOwnProperty.call(values,"target");
    const created = automatic ? await createAutomatically(values) : null;
    const row = created ? created.row :
      await pairingPost("/api/chats", {op, ...(op === "create" ? {} : {chat_id:id}), ...values});
    if (op === "create") {
      chatItems.unshift(row);
      if (created && !row.manager_id && created.managerId) {
        sessionStorage.setItem("ultra.chat.manager." + row.chat_id, created.managerId);
      }
      selectChat(row.chat_id);
    } else if (op === "delete") {
      chatItems = chatItems.filter(item => item.chat_id !== id);
      conversations.delete(id);
      sessionStorage.removeItem("ultra.chat.manager." + id);
      localStorage.removeItem("ultra.chat.instance." + id);
      try { localStorage.removeItem("ultra.chat.effort." + id); } catch {}
      if (chatSelected === id) selectChat(chatItems[0]?.chat_id || "");
    } else {
      chatItems = chatItems.map(item => item.chat_id === id ? row : item);
      if (op === "target") {
        localStorage.removeItem("ultra.chat.instance." + id);
        if (chatRestartHold?.chatId===id) chatRestartHold=null;
        if (chatRestartSuccess?.chatId===id) chatRestartSuccess=null;
        const bound=liveTarget(row);
        const manager=chatSnapshot?.managers?.find(item=>item.manager_id===row.manager_id && item.status==="online");
        if (bound?.engine_state==="ready" && bound.instance_id &&
            manager?.data?.control?.instances?.some(item=>item.instance_id===bound.instance_id &&
              item.slot_id===row.slot_id && item.model_id===row.model_id && item.state==="READY" && item.released===false))
          localStorage.setItem("ultra.chat.instance."+id,bound.instance_id);
      }
      if (chatSelected !== id && ["clear", "restore"].includes(op)) conversation(id).messages = [];
      if (chatSelected === id && ["clear", "restore"].includes(op)) await loadChatHistory();
      if (chatSelected === id && op === "target" && conversation(id).messages.length) {
        setChatNotice("Для новой модели будут использованы текстовые реплики этого чата. При несовместимости сбросьте контекст или уменьшите историю.");
      }
    }
  } catch (error) {
    if (error.message === "chat_target_occupied") {
      try { chatItems = (await api("/api/chats")).chats; } catch {}
    }
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
    if (op==="preferences" && chatSelected===id) applyChatPreferences(currentChat());
    if (op==="context_tokens" && chatSelected===id) syncContextSize(currentChat());
    renderChatList(chatSnapshot);
    chatBindingChannel?.postMessage("changed");
  }
}
const chatBindingChannel = typeof BroadcastChannel === "function" ? new BroadcastChannel("ultra-chat-bindings") : null;
let bindingSyncVersion = 0;
async function syncChatBindings() {
  if (!chatOpen || loadingChats || chatMutation) return;
  const version = ++bindingSyncVersion;
  try {
    const rows = (await api("/api/chats")).chats;
    if (!chatOpen || loadingChats || chatMutation || version !== bindingSyncVersion) return;
    chatItems = rows;
    if (chatSelected && !currentChat()) selectChat(rows[0]?.chat_id || "");
    else {
      if (!currentChat() || !conversation(chatSelected).request) applyChatPreferences(currentChat());
      renderChatList(chatSnapshot);
    }
  } catch {}
}
if (chatBindingChannel) chatBindingChannel.onmessage = () => syncChatBindings();
window.addEventListener("focus", syncChatBindings);
const COPY_ICON='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h1"/></svg>';
const COPIED_ICON='<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg>';
function copyButton(source,kind) {
  const btn=node("button","message-copy");
  btn.type="button";
  btn.dataset.copyKind=kind;
  btn.title="Копировать";
  btn.setAttribute("aria-label",kind==="reasoning"?"Копировать рассуждение":"Копировать сообщение");
  btn.innerHTML=COPY_ICON;
  btn.disabled=!source.textContent;
  let timer;
  btn.addEventListener("click",async event=>{
    event.stopPropagation();
    const value=source.textContent;
    if(!value)return;
    try {
      await navigator.clipboard.writeText(value);
      btn.title="Скопировано";
      btn.innerHTML=COPIED_ICON;
    } catch {
      btn.title="Не удалось скопировать. Выделите текст вручную.";
      btn.setAttribute("aria-label",btn.title);
    }
    clearTimeout(timer);
    timer=setTimeout(()=>{
      btn.title="Копировать";btn.innerHTML=COPY_ICON;
      btn.setAttribute("aria-label",kind==="reasoning"?"Копировать рассуждение":"Копировать сообщение");
    },1600);
  });
  return btn;
}
function updateCopyButtons(bubble) {
  for(const btn of bubble.querySelectorAll(".message-copy")){
    const text=bubble.querySelector(btn.dataset.copyKind==="reasoning"?".reasoning-text":".chat-text");
    btn.disabled=!text?.textContent;
  }
}
function reasoningPanel(text, open) {
  const detail = node("details", "reasoning-panel");
  detail.open = open;
  detail.classList.toggle("hidden", !byId("chat-show-reasoning").checked);
  const content=node("div","reasoning-text",text||"");
  detail.append(node("summary", "", "Рассуждения"),content,copyButton(content,"reasoning"));
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
function messageFooter(message) {
  const footer = node("div", "chat-message-footer");
  footer.append(timestamp(message.created_at));
  if (!message.pending) {
    const details = node("small", "chat-message-metrics", message.metrics ?
      requestMetricsLabel(message.metrics) : "Замеры запроса недоступны");
    details.dataset.tip = "Сохранённые замеры Client для этой пары сообщений";
    footer.append(details);
  }
  return footer;
}
function messageBubble(message, live = false) {
  const bubble = node("div", "chat-bubble" + (message.role === "user" ? " user" : ""));
  const label = node("small", "", message.role === "user" ? "Вы" : "LLM");
  if (message.reasoning_content || live) {
    const reasoning = reasoningPanel(message.reasoning_content, live);
    if (!message.reasoning_content) reasoning.classList.add("hidden");
    bubble.append(label, reasoning);
  } else bubble.append(label);
  const content=node("div","chat-text",message.content||"");
  bubble.append(content,copyButton(content,"answer"));
  if (!live) bubble.append(messageFooter(message));
  return bubble;
}
const chatHolder = byId("chat-messages");
const chatPanel = document.querySelector("#chat-view .chat-panel");
const chatComposer = byId("chat-form");
let followStream = true;
let scrollFrame = 0;
let lastScrollTop = window.scrollY;
let userScrollIntentUntil = 0;
window.addEventListener("wheel", event => {
  if (event.target instanceof Element && event.target.closest(".chat-inspector")) return;
  if (event.deltaY < 0) userScrollIntentUntil = performance.now() + 700;
}, {passive:true});
window.addEventListener("touchmove", () => { userScrollIntentUntil = performance.now() + 700; }, {passive:true});
window.addEventListener("keydown", event => {
  if (["ArrowUp", "PageUp", "Home"].includes(event.key)) userScrollIntentUntil = performance.now() + 700;
});
window.addEventListener("pointerdown", event => {
  if (event.clientX >= document.documentElement.clientWidth - 18)
    userScrollIntentUntil = performance.now() + 1500;
}, {passive:true});
function composerHeight() {
  return chatComposer.getBoundingClientRect().height || 126;
}
// The conversation uses the browser's ONLY main scrollbar. The composer
// stays at the viewport bottom and follows the chat panel's real width.
function updateComposerPosition() {
  if (!chatOpen || byId("chat-view").classList.contains("hidden")) return;
  const box = chatPanel.getBoundingClientRect();
  if (!box.width) return;
  // CSS zoom scales DOMRect but also scales fixed-position CSS lengths.
  // Divide visual geometry by that scale before writing CSS custom properties.
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1;
  const left = Math.max(0, box.left / zoom);
  const width = Math.max(0, Math.min(box.width / zoom, window.innerWidth / zoom - left));
  const height = Math.ceil(composerHeight() / zoom);
  const view = byId("chat-view");
  view.style.setProperty("--chat-composer-left", left + "px");
  view.style.setProperty("--chat-composer-width", width + "px");
  view.style.setProperty("--chat-composer-right", Math.max(10, window.innerWidth-left-width+12) + "px");
  view.style.setProperty("--chat-composer-height", height + "px");
}
function lastConversationEdge() {
  const latest = chatHolder.querySelector(".chat-bubble:last-of-type") || chatHolder.lastElementChild || chatHolder;
  return latest.getBoundingClientRect().bottom;
}
function scrollDistance() {
  return lastConversationEdge() - (window.innerHeight - composerHeight() - 18);
}
function pinToBottom() {
  if (!chatOpen) return;
  updateComposerPosition();
  const desired = Math.max(window.scrollY + scrollDistance(),
    document.documentElement.scrollHeight - window.innerHeight);
  window.scrollTo({top:Math.max(0,desired),behavior:"instant"});
  lastScrollTop = window.scrollY;
}
function updateFollow() {
  if (!chatOpen) return;
  const top = window.scrollY;
  if (performance.now() < userScrollIntentUntil) {
    if (top < lastScrollTop - 4) followStream = false;
    else if (top > lastScrollTop + 1) followStream = scrollDistance() <= 64;
  }
  byId("chat-latest").classList.toggle("hidden", followStream);
  lastScrollTop = top;
}
function followBottom() {
  if (!followStream || scrollFrame || !chatOpen) return;
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0;
    if (followStream) pinToBottom();
  });
}
window.addEventListener("scroll", updateFollow, {passive:true});
window.addEventListener("resize", () => { updateComposerPosition(); followBottom(); }, {passive:true});
if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(updateComposerPosition).observe(chatPanel);
  new ResizeObserver(() => { updateComposerPosition(); followBottom(); }).observe(chatComposer);
  new ResizeObserver(followBottom).observe(chatHolder);
}
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
  if (followStream) {
    pinToBottom();
    requestAnimationFrame(pinToBottom);
  }
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
  // Raw telemetry remains in view.metrics and persistent request records; it is not rendered as JSON.
}
function seconds(ms) {
  return Number.isFinite(ms) ? (ms/1000).toFixed(2) + " с" : "нет данных";
}
function requestMetricsLabel(metrics) {
  const usage = metrics.usage || {};
  const rate = metrics.throughput?.completion_tokens_per_second;
  return "Первый фрагмент " + seconds(metrics.first_fragment_ms) + " · Генерация " + seconds(metrics.generation_ms) +
    " · Всего " + seconds(metrics.total_ms) +
    " · Токены вход / выход " + (usage.prompt_tokens ?? "нет данных") + " / " + (usage.completion_tokens ?? "нет данных") +
    (Number.isFinite(rate) ? " · Маршрут Colibri " + rate.toFixed(2) + " токенов/с с подготовкой prompt" : "");
}
let livePollBusy=false;
function codepoints(text) {let n=0;for(const _ of text||"")n++;return n;}
function chatNumber(n) {return Number.isFinite(n)?n.toLocaleString("ru-RU"):"—";}
function liveRate(n) {return Number.isFinite(n)?n.toFixed(2):"—";}
function renderChatTelemetry() {
  const view=chatSelected?conversation(chatSelected):null;
  const request=view?.request;
  if(view&&view.countedMessages!==view.messages) {
    view.countedMessages=view.messages;
    view.historyChars=view.messages.reduce((n,m)=>n+codepoints(m.content),0);
    view.lastMessageMetrics=view.messages.slice().reverse().find(m=>m.role==="assistant"&&m.metrics)?.metrics;
  }
  const chars=view?(view.historyChars||0)+(request&&!request.completed?(request.userChars||0)+(request.answerChars||0):0):null;
  const saved=view?.metrics?.saved;
  const completed=saved?.state==="complete"||saved?.usage&&!saved?.error ? saved:view?.lastMessageMetrics;
  const sample=request?.telemetry&&performance.now()-request.telemetry.at<6500?request.telemetry.data:null;
  const live=sample?.live;
  const writing=live?.state==="writing";
  let phase=request?(request.cancelling?"Отмена…":live?.state==="reading"?"Чтение контекста":
      writing?"Генерация":"Ожидание данных модели"):completed?"Последний завершённый запрос":"Нет активного запроса";
  if(request&&Number.isFinite(live?.elapsed_s))phase+=" · "+live.elapsed_s.toFixed(1)+" с";
  put("chat-live-phase",phase);
  put("chat-live-chars",chatNumber(chars));
  const input=request?live?.prompt_tokens:completed?.usage?.prompt_tokens;
  const output=request?live?.tokens:completed?.usage?.completion_tokens;
  put("chat-live-tokens",chatNumber(input)+" / "+chatNumber(output));
  put("chat-live-speed",writing?liveRate(live.tok_s_now):"—");
  const avg=!request&&Number.isFinite(completed?.usage?.completion_tokens)&&completed?.generation_ms>0?
    completed.usage.completion_tokens/(completed.generation_ms/1000):null;
  put("chat-live-average",request?(writing?liveRate(live.tok_s):"—"):liveRate(avg));
  put("chat-live-context-chars",chatNumber(request?(sample?.sent_chars??view.metrics?.context?.sent_chars):
    completed?.context?.sent_chars));
}
async function pollChatTelemetry() {
  if(!chatOpen||livePollBusy||!chatSelected)return;
  const view=conversation(chatSelected),request=view.request;
  if(!request?.controller||request.cancelling||!request.target.live_telemetry||!request.target.instance_id)return;
  livePollBusy=true;
  try{
    const data=await api("/api/chat/telemetry?"+new URLSearchParams({...targetFields(request.target),
      instance_id:request.target.instance_id,request_id:request.id}),{signal:AbortSignal.timeout(6500)});
    if(view.request===request&&data.request_id===request.id&&data.instance_id===request.target.instance_id)
      request.telemetry={data,at:performance.now()};
  }catch{if(view.request===request)request.telemetry=null;}
  finally{livePollBusy=false;if(chatOpen)renderChatTelemetry();}
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
    label = (data.error || snapshot?.state === "failed" ? "Ошибка · " :
      snapshot?.state === "cancelled" || data.cancelled ? "Отменён · " : "") + requestMetricsLabel({
        first_fragment_ms:data.browser_first_fragment_ms ?? snapshot?.first_fragment_ms,
        generation_ms:data.browser_generation_ms ?? snapshot?.generation_ms,
        total_ms:data.browser_total_ms ?? snapshot?.total_ms,
        usage:data.usage || snapshot?.usage,
        throughput:data.throughput || snapshot?.throughput
      });
  }
  byId("chat-timer").textContent = label;
  renderChatTelemetry();
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
  models.replaceChildren(new Option("Все", ""), ...names.map(name => new Option(modelName(name), name)));
  if (names.includes(previous)) models.value = previous;
  filterStatistics();
}
function filterStatistics() {
  const model = byId("chat-stat-model").value;
  const mode = byId("chat-stat-mode").value;
  const results = stats.filter(row => (!model || row.target.model_id === model) && (!mode || (row.execution_mode || "unknown") === mode));
  byId("chat-stat-results").replaceChildren(...results.map(row => node("div", "chat-stat-row",
    timestamp(row.finished_at).textContent + " · " + modelName(row.target.model_id) + " · " +
    (row.execution_mode?.toUpperCase() || "режим неизвестен") + " · " +
    ({complete:"Завершён", failed:"Ошибка", cancelled:"Отменён"}[row.state]) + " · " + seconds(row.total_ms) + " · " +
    (row.usage?.prompt_tokens ?? "нет данных") + " / " + (row.usage?.completion_tokens ?? "нет данных") + " токенов")));
}

function generationFields(target) {
  const maximum = byId("chat-max-tokens").value;
  const policy = target.transport || {};
  const thinking = byId("chat-thinking").checked;
  return {options:{thinking:thinking ? "on" : "off", reasoning_effort:thinking ? byId("chat-effort").value : "auto",
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
  } else {
    request.assistant.querySelector(".chat-text").textContent += event.text;
    request.answerChars=(request.answerChars||0)+codepoints(event.text);
  }
  updateCopyButtons(request.assistant);
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
      try {
        if (!await readStatus({signal:AbortSignal.timeout(1800)})) {
          checks.push("unknown");
          continue;
        }
      } catch {
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
  if (!assignedChatOwnsTarget(chat,target) || !chatReady(target) || chatMutation ||
      chatRestartJob?.chatId===chat?.chat_id || selectedManagerId(chat) !== chat.manager_id ||
      !message || message.length > 131072) return;
  const id = chat.chat_id;
  const view = conversation(id);
  if (view.request) return;
  const streaming = byId("chat-stream").checked && target.streaming;
  const generation = generationFields(target);
  if (!target.streaming) delete generation.options;
  const parameters = JSON.stringify([targetKey(target), target.instance_id, message, generation, streaming]);
  const requestId = view.retry?.parameters === parameters ? view.retry.id : crypto.randomUUID().replaceAll("-", "");
  const request = {chatId:id, target, id:requestId, started:performance.now(),userChars:codepoints(message),answerChars:0,
    controller:streaming ? new AbortController() : null,
    user:messageBubble({role:"user", content:message, created_at:new Date().toISOString(), pending:true}),
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
    if(streaming)void pollChatTelemetry();
    let result = streaming ? await readChatStream(body, request, frame => renderFragment(view, request, frame)) :
      await pairingPost("/api/chat/send", body);
    const total = performance.now()-request.started;
    updateMetrics(view, {usage:result.usage || {}, throughput:result.throughput || {}, context:result.context || view.metrics.context,
      saved:result.metrics, browser_total_ms:total, browser_generation_ms:request.first == null ? null : total-request.first});
    const inlineExchange = !result.cached && !result.history_reload;
    if (result.history_reload) result = await api("/api/chat/history?" + new URLSearchParams({chat_id:id}));
    view.messages = result.messages;
    view.draft = "";
    completed = true;
    request.completed=true;
    view.retry = null;
    if (chatSelected === id) {
      input.value = "";
      const rendered = chatHolder.querySelectorAll(".chat-bubble");
      if (inlineExchange && rendered.length === view.messages.length && view.messages.length >= 2) {
        const [user, assistant] = view.messages.slice(-2);
        request.user.querySelector(".chat-message-footer").replaceWith(messageFooter(user));
        request.assistant.append(messageFooter(assistant));
        request.assistant.querySelector(".chat-text").textContent = assistant.content;
        const detail = request.assistant.querySelector(".reasoning-panel");
        detail.querySelector(".reasoning-text").textContent = assistant.reasoning_content || "";
        detail.classList.toggle("hidden", !assistant.reasoning_content || !byId("chat-show-reasoning").checked);
        updateCopyButtons(request.assistant);
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
byId("chat-restart").addEventListener("click",restartSelectedChat);
byId("chat-new").addEventListener("click", () => {
  changeChat("create");
});
byId("chat-manager").addEventListener("change", event => {
  if (!chatSelected) return;
  sessionStorage.setItem("ultra.chat.manager." + chatSelected, event.target.value);
  renderChatControls();
});
byId("chat-model").addEventListener("change", event => {
  if (!event.target.value) return;
  const target = chatTargets.find(item => targetKey(item) === event.target.value);
  if (target && targetAvailableToChat(target,currentChat())) changeChat("target", {target:targetFields(target)});
});
byId("chat-detach-model").addEventListener("click", () => {
  if (currentChat()?.model_id) changeChat("target", {target:null});
});
for (const field of ["chat-stream","chat-thinking"]) byId(field).addEventListener("change", () => {
  if (!currentChat()) return;
  changeChat("preferences", {preferences:{stream:byId("chat-stream").checked, thinking:byId("chat-thinking").checked}});
});
byId("chat-effort").addEventListener("change", () => {
  if (!currentChat()) return;
  try { localStorage.setItem("ultra.chat.effort." + chatSelected, byId("chat-effort").value); } catch {}
});
byId("chat-context-preset").addEventListener("change",event=>{
  if(!currentChat())return;
  if(event.target.value==="custom"){
    contextCustomDraft=true;
    showContextCustom(true);
    byId("chat-context-custom").value="";
    byId("chat-context-custom").focus();
  }else changeChat("context_tokens",{context_tokens:Number(event.target.value)});
});
const customContextInput=byId("chat-context-custom");
customContextInput.addEventListener("input",()=>{contextCustomDraft=true;customContextInput.value=customContextInput.value.replace(/[^0-9]/g,"").slice(0,6);});
function saveCustomContext(){
  if(!contextCustomDraft || !currentChat())return;
  const value=Number(customContextInput.value);
  if(!Number.isInteger(value) || value<1 || value>999999){
    setChatNotice(controlReason("invalid_context_tokens"));return;
  }
  contextCustomDraft=false;
  changeChat("context_tokens",{context_tokens:value});
}
customContextInput.addEventListener("change",saveCustomContext);
customContextInput.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();event.stopPropagation();saveCustomContext();}});
byId("chat-context-list").addEventListener("click",()=>{
  contextCustomDraft=true;showContextCustom(false);
  byId("chat-context-preset").selectedIndex=-1;
  byId("chat-context-preset").focus();
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
setInterval(pollChatTelemetry,2000);
setInterval(pollCuda,3000);
byId("chat-form").addEventListener("submit", submitChat);
byId("chat-input").addEventListener("input", event => {
  if (chatSelected) conversation(chatSelected).draft = event.target.value;
});
const inputResizeHandle = byId("chat-input-resize");
let inputResizeStart = null;
function resizeChatInput(height) {
  const input = byId("chat-input");
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1;
  const maxHeight = Math.min(280, window.innerHeight * 0.42 / zoom);
  input.style.height = Math.round(Math.max(52, Math.min(maxHeight, height))) + "px";
  updateComposerPosition();
  followBottom();
}
inputResizeHandle.addEventListener("pointerdown", event => {
  if (event.button !== 0) return;
  event.preventDefault();
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1;
  inputResizeStart = {y:event.clientY, height:byId("chat-input").getBoundingClientRect().height / zoom};
  inputResizeHandle.setPointerCapture(event.pointerId);
});
inputResizeHandle.addEventListener("pointermove", event => {
  if (!inputResizeStart) return;
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1;
  resizeChatInput(inputResizeStart.height + (inputResizeStart.y - event.clientY) / zoom);
});
for (const eventName of ["pointerup", "pointercancel"]) inputResizeHandle.addEventListener(eventName, () => {
  inputResizeStart = null;
});
inputResizeHandle.addEventListener("keydown", event => {
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  resizeChatInput(byId("chat-input").getBoundingClientRect().height /
    (Number.parseFloat(getComputedStyle(document.body).zoom) || 1) + (event.key === "ArrowUp" ? 16 : -16));
});
byId("chat-input").addEventListener("keydown", event => {
  if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey ||
      event.metaKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (event.repeat || byId("chat-send").disabled || byId("chat-send").type !== "submit" || !event.currentTarget.value.trim()) return;
  event.currentTarget.form.requestSubmit();
});
byId("chat-show-reasoning").addEventListener("change", () => {
  document.querySelectorAll(".reasoning-panel").forEach(detail => detail.classList.toggle("hidden",
    !byId("chat-show-reasoning").checked || !detail.querySelector(".reasoning-text").textContent));
  followBottom();
});
byId("chat-send").addEventListener("click", async () => {
  if (byId("chat-send").type !== "button") return;
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

{
  const promptDialog = byId("global-prompt-dialog");
  const field = byId("global-prompt-text");
  const save = byId("global-prompt-save");
  const error = byId("global-prompt-error");
  function showError(message) {
    error.textContent = message;
    error.classList.toggle("hidden", !message);
  }
  byId("global-prompt-open").addEventListener("click", async () => {
    showError("");
    field.value = "";
    field.disabled = save.disabled = true;
    promptDialog.showModal();
    try {
      const result = await api("/api/global-prompt");
      field.value = result.prompt;
      field.disabled = save.disabled = false;
      field.focus();
    } catch (e) { showError("Не удалось загрузить Global Prompt: " + e.message); }
  });
  for (const id of ["global-prompt-close", "global-prompt-cancel"])
    byId(id).addEventListener("click", () => promptDialog.close());
  byId("global-prompt-form").addEventListener("submit", async e => {
    e.preventDefault();
    showError("");
    save.disabled = true;
    try {
      // Refresh the local session in case Client was restarted while this tab was open.
      csrf = (await api("/api/session")).csrf;
      await api("/api/global-prompt", {method:"POST", headers:{"Content-Type":"application/json","X-Ultra-CSRF":csrf}, body:JSON.stringify({prompt:field.value})});
      promptDialog.close();
    } catch (e) { showError("Не удалось сохранить Global Prompt: " + e.message); }
    finally { save.disabled = false; }
  });
}

// One shared tooltip in the browser top layer, outside every scroll container.
function chatModeBadge(mode) {
  const label = node("span", "chat-mode-confirmed", mode);
  label.dataset.tip = mode === "CPU" ? "Модель работает на процессоре (CPU)." :
    mode === "CUDA" ? "Модель работает на видеокарте (CUDA)." : "Режим выполнения: " + mode;
  return label;
}
{
  const tip = node("div", "", "");
  tip.id = "chat-floating-tip";
  tip.setAttribute("role", "tooltip");
  tip.setAttribute("popover", "manual");
  const topLayer = typeof tip.showPopover === "function";
  if (!topLayer) tip.hidden = true;
  document.body.append(tip);
  let owner = null, timer = 0;
  function hideTip() {
    clearTimeout(timer);
    if (owner) {
      const ids = (owner.getAttribute("aria-describedby") || "").split(/\s+/).filter(x => x && x !== tip.id);
      if (ids.length) owner.setAttribute("aria-describedby", ids.join(" "));
      else owner.removeAttribute("aria-describedby");
    }
    owner = null;
    if (topLayer && tip.matches(":popover-open")) tip.hidePopover();
    else if (!topLayer) tip.hidden = true;
  }
  function showTip(el) {
    if (!el || !el.dataset.tip || owner === el) return;
    hideTip();
    owner = el;
    timer = setTimeout(() => {
      if (owner !== el || !el.isConnected || !el.getClientRects().length || !el.dataset.tip) return hideTip();
      tip.textContent = el.dataset.tip;
      tip.style.left = "0px"; tip.style.top = "0px";
      if (topLayer) tip.showPopover();
      else tip.hidden = false;
      const b = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
      const zoom = t.width / tip.offsetWidth || 1;
      const x = Math.max(8, Math.min(b.left+(b.width-t.width)/2, innerWidth-t.width-8));
      const y = Math.max(4, b.top-t.height-7);
      tip.style.left = x/zoom+"px"; tip.style.top = y/zoom+"px";
      const ids = new Set((el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
      ids.add(tip.id);
      el.setAttribute("aria-describedby",[...ids].join(" "));
    }, 200);
  }
  const find = target => target instanceof Element ? target.closest("[data-tip]") : null;
  document.addEventListener("pointerover", e => {
    const el = find(e.target);
    if (el) showTip(el);
  }, true);
  document.addEventListener("pointerout", e => {
    if (owner && find(e.target) === owner && !(e.relatedTarget instanceof Node && owner.contains(e.relatedTarget))) hideTip();
  }, true);
  document.addEventListener("focusin", e => { const el = find(e.target); if (el) showTip(el); });
  document.addEventListener("focusout", e => {
    if (owner && owner.contains(e.target) && !(e.relatedTarget instanceof Node && owner.contains(e.relatedTarget))) hideTip();
  });
  document.addEventListener("pointerdown",hideTip,true);
  document.addEventListener("keydown", e => { if (e.key === "Escape") hideTip(); });
  window.addEventListener("scroll",hideTip,true);
  window.addEventListener("resize",hideTip);
  window.addEventListener("blur",hideTip);
  // A live refresh can replace a slot/card while its hint is on screen.
  new MutationObserver(() => { if (owner && (!owner.isConnected || !owner.getClientRects().length)) hideTip(); })
    .observe(document.body,{childList:true,subtree:true});
}
