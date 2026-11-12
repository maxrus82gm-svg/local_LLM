from pathlib import Path
import re

root = Path(r"M:\GitHub\local_LLM_GPT_docs")
js_path = root / "Client_Ultra_LLM/web_assets/client.js"
html_path = root / "Client_Ultra_LLM/web_assets/index.html"
css_path = root / "Client_Ultra_LLM/web_assets/client.css"
manager_path = root / "Manager_Ultra_LLM/live_manager.py"
tests_path = root / "Client_Ultra_LLM/test_chat_client.py"
manager_tests_path = root / "Manager_Ultra_LLM/test_live_manager.py"

def replace_once(s, old, new, label):
    n = s.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected exactly one match, got {n}")
    return s.replace(old, new, 1)

js = js_path.read_text(encoding="utf-8-sig")
a, b = js.index("function modelList("), js.index("function makeManager(")
new_models = r'''function modelList(container, slots, disk) {
  const wrapper = node("section", "models-list");
  const heading = node("div", "manager-model-head");
  heading.append(node("h3", "", "МОДЕЛИ И УПРАВЛЕНИЕ"),
    node("small", "", "Запуск и остановка будут доступны после подключения управления Manager"));
  wrapper.append(heading);
  const scroll = node("div", "manager-model-scroll");
  const rows = [];
  const names = new Set();
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
      button.title = "Управление START/STOP через Manager ещё не реализовано";
      button.setAttribute("aria-label", title + " — " + item.name + " (пока недоступно)");
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
'''
js = js[:a] + new_models + js[b:]
old_top = '''  top.append(heading);
  top.append(node("span", "status-pill" + (online ? "" : " offline"), online ? "● ONLINE" : "● OFFLINE"));
'''
new_top = '''  top.append(heading);
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
'''
js = replace_once(js, old_top, new_top, "top metadata")
begin = js.index("  const ram = data.memory || {};", js.index("function makeManager("))
end = js.index("  card.append(body);", begin)
js = js[:begin] + '''  const available = slots.filter(s => s.availability === "ready_unreserved").length;
  body.append(node("div", "manager-slot-summary",
    "Слотов: " + slots.length + " · Готовы к запросам: " + available +
    " · Свободный слот сам по себе не означает запущенную LLM"));
  modelList(body, slots, Array.isArray(data.models) ? data.models : []);
''' + js[end:]
a, b = js.index("function makeRow("), js.index("function render(")
js = js[:a] + js[b:]
js = replace_once(js, "  let ready = 0, ram = 0, ramHosts = 0;", "  let ready = 0;", "render counters")
js = replace_once(js, '''  const table = byId("slot-table");table.replaceChildren();
''', "", "remove slot-table access")
js = replace_once(js, '''      table.append(makeRow(manager, slot));
''', "", "remove rows")
a = js.index('    if (data.memory && data.memory.state === "live" &&')
b = js.index('  }\n  if (!all.length)', a)
js = js[:a] + js[b:]
a = js.index('  if (!table.children.length)')
b = js.index('  stat("metric-manager"', a)
js = js[:a] + js[b:]
js = replace_once(js, '''  stat("metric-ram", ramHosts ? formatNumber(ram) + " GiB" : "—");
''', "", "remove aggregated RAM")
js_path.write_text(js, encoding="utf-8", newline="\n")

html = html_path.read_text(encoding="utf-8-sig")
html, n = re.subn(r'    <article class="metric"><small>СВОБОДНАЯ RAM</small>.*?</article>\s*\n',
                  '', html, count=1, flags=re.S)
if n != 1: raise RuntimeError("global RAM metric not found")
begin = html.index('  <section class="section"><div class="section-head"><div><div class="eyebrow">РЕСУРСЫ И СЕССИИ</div>')
end = html.index('  </section><footer>', begin) + len('  </section>')
html = html[:begin] + html[end:]
html_path.write_text(html, encoding="utf-8", newline="\n")

css = css_path.read_text(encoding="utf-8-sig")
css += """
/* Manager-centred overview: hardware in each header, one scrollable model list. */
.metrics{grid-template-columns:repeat(3,minmax(0,1fr))}
.manager-grid{grid-template-columns:minmax(0,1fr)}
.manager-top{flex-wrap:wrap;gap:14px}
.manager-memory-summary{margin-left:auto;color:#b0c4dc;font-size:11px;font-variant-numeric:tabular-nums;text-align:right}
.manager-top .status-pill{margin-left:0;align-self:center}
.manager-body{padding:13px 21px 17px}
.manager-slot-summary{font-size:11px;color:#8ca0b6;margin-bottom:10px}
.manager-model-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin:0 0 8px}
.manager-model-head h3{margin:0;font-size:10px;letter-spacing:1.1px;color:#a7b4cb}
.manager-model-head small{color:#798ca5;font-size:10px}
.manager-model-scroll{max-height:390px;overflow:auto;scrollbar-width:thin;scrollbar-color:#586680 #1d2736;border:1px solid #28394d;border-radius:10px}
.manager-model-row{display:grid;grid-template-columns:minmax(0,1fr) repeat(3,105px);align-items:center;gap:10px;padding:11px 13px;border-bottom:1px solid #263445;min-width:635px}
.manager-model-row:last-child{border-bottom:0}
.manager-model-row:hover{background:#1d2938}
.manager-model-info{min-width:0;display:grid;gap:5px}
.manager-model-name{font-size:12px;color:#e4edfa;overflow-wrap:anywhere}
.manager-model-info small{font-size:10px;color:#8da1b8;line-height:1.45}
.manager-model-info .model-live{color:#67dab5}
.manager-model-action{width:105px;padding:9px 6px;white-space:nowrap}
.manager-model-policy{margin-top:10px;color:#7f96b1;font-size:10px;line-height:1.6}
.manager-model-empty{padding:15px;color:#8a9cb3;font-size:12px}
.chat-list{max-height:65vh;overflow-y:auto;scrollbar-width:thin;scrollbar-color:#586680 #1d2736;padding-right:4px}
@media(max-width:900px){.manager-memory-summary{margin-left:0;text-align:left;flex:1 1 250px}}
@media(max-width:730px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
"""
css_path.write_text(css, encoding="utf-8", newline="\n")

manager = manager_path.read_text(encoding="utf-8-sig")
manager = replace_once(manager,
 '''              r"$os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop;" +''',
 '''              r"$os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop;" +
              r"$mem=@();try{$mem=@(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop)}catch{$mem=@()};" +
              r"$generation='';$installed=0.0;" +
              r"if($mem.Count -gt 0){$kinds=@($mem|ForEach-Object{[int]$_.SMBIOSMemoryType}|Sort-Object -Unique);" +
              r"if($kinds.Count -eq 1 -and $kinds[0] -eq 26){$generation='DDR4'}" +
              r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 34){$generation='DDR5'}" +
              r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 24){$generation='DDR3'};" +
              r"$installed=[double](($mem|Measure-Object -Property Capacity -Sum).Sum)/1GB};" +''', "optional RAM hardware")
manager = replace_once(manager,
 '''              r"free_gib=[double]$os.FreePhysicalMemory/1048576;" +''',
 '''              r"free_gib=[double]$os.FreePhysicalMemory/1048576;" +
              r"ddr_generation=$generation;installed_gib=$installed;" +''',
 "PS result hardware fields")
manager = replace_once(manager,
 '''                            "free_gib": round(float(evidence["free_gib"]), 2)}
        listening =''',
 '''                            "free_gib": round(float(evidence["free_gib"]), 2)}
        ddr = evidence.get("ddr_generation")
        if ddr in ("DDR3", "DDR4", "DDR5"):
            result["memory"]["ddr_generation"] = ddr
        installed = evidence.get("installed_gib")
        if type(installed) in (int, float) and 0 < installed < 8192:
            result["memory"]["installed_gib"] = round(float(installed), 2)
        listening =''', "Manager snapshot RAM optional fields")
manager_path.write_text(manager, encoding="utf-8", newline="\n")

tests = tests_path.read_text(encoding="utf-8-sig")
needle = '''        self.assertIn('id="chat-popout"', html)
'''
replacement = '''        self.assertIn('id="chat-popout"', html)
        self.assertNotIn('id="slot-table"', html)
        self.assertNotIn('id="metric-ram"', html)
        self.assertIn('id="metric-ready"', html)
        self.assertIn('manager-model-scroll', js)
        self.assertIn('["Старт CPU", "Старт CUDA", "Стоп"]', js)
        self.assertIn("button.disabled = true", js)
        self.assertIn("manager-memory-summary", js)
'''
tests = replace_once(tests, needle, replacement, "HTML redesign asserts")
tests_path.write_text(tests, encoding="utf-8", newline="\n")

tests = manager_tests_path.read_text(encoding="utf-8-sig")
needle = '''    def test_token_digest_and_missing_bearer_fail_closed(self):
'''
replacement = '''    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_local_api_json", return_value=None)
    def test_snapshot_shows_verified_optional_ddr_and_installed_capacity(self, api, dirs):
        evidence = dict(MEM, ddr_generation="DDR4", installed_gib=48.0)
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertEqual(result["memory"]["ddr_generation"], "DDR4")
        self.assertEqual(result["memory"]["installed_gib"], 48.0)
        self.assertEqual(result["memory"]["free_gib"], 30.0)
        evidence["ddr_generation"] = "UNKNOWN"
        evidence["installed_gib"] = 0
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertNotIn("ddr_generation", result["memory"])
        self.assertNotIn("installed_gib", result["memory"])

    def test_token_digest_and_missing_bearer_fail_closed(self):
'''
tests = replace_once(tests, needle, replacement, "Manager RAM regressions")
manager_tests_path.write_text(tests, encoding="utf-8", newline="\n")
print("CHANGED: web_assets/index.html, client.js, client.css, Manager_Ultra_LLM/live_manager.py, two tests")
print("No live runtime, security settings or model processes touched.")
