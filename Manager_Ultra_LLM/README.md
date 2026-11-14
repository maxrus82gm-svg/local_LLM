# Ultra LLM Manager — исходный снимок и офлайн-проверка

## CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001 — сдача 13.11.2026

**RESULT: RELEASE CANDIDATE READY / LIVE DEPLOY NOT RUN; SUBMITTED / REVIEW PENDING.**
Это отчёт исполнителя, не независимая приёмка. Работа выполнена на домашнем
`DESKTOP-SC96D3U`, внутри `M:\GitHub\local_LLM`. Работающий Manager, модели,
службы, Client, ярлык, firewall и TLS не изменялись. Все приведённые ниже команды
серверного переключения — план следующего этапа, **НЕ выполненные действия**.

### DONE

Подготовлен переносимый **source bundle** `R5-compat-20261113.1`: 19 разрешённых
файлов runtime/проверки + `RELEASE.json` + `SHA256SUMS.txt` = **21 файл**.
Требуется уже установленный Windows x64 / CPython 3.12 x64; Python не включён,
новые pip-зависимости не нужны. Это не отдельный EXE и не установщик службы.
Сохраняются готовые CONTROL-01/P0/P1: SSE→NDJSON, reasoning, cancel, привязка
instance_id, каталог, сохраняемые слоты, изолированные экземпляры, scoped STOP.
Производственные механизмы управления моделями не переписывались.

Локальные refs до работы: `main` №45
`71462bde1f245f96180bec351e0f1ea7ecdd8b50`; `GPT_2_local` №44
`73dec62a1e0eda4a7846fa7a67bfb0e29ab39615`, расхождение 2/2.
Удалённые refs не сверялись, fetch/pull не выполнялись.
**AMENDMENT владельца в чате 13.11: коммитить не надо, только локальная работа.**
Поэтому ветки не переключались, commit/push/pull не выполнены, номер/SHA нового
коммита **N/A**. Base HEAD указан для происхождения; сам кандидат закреплён SHA
каждого файла, а не выдан за immutable task commit.

### CHANGED / DIFF

- `manager_release.py`: allowlist, проверка зависимости только от stdlib,
  воспроизводимый ZIP, manifest, проверка целостности, staging в новую папку.
  Не принимает неизвестные/повторные ZIP entries, traversal, symlink/junction,
  приватную конфигурацию в пакете и существующую целевую папку.
- `test_manager_release.py`: проверка подмены/небезопасных архивов, переносимости
  импортов и детерминизма, сохранности legacy config/auth и закрытых owner gates.
- `test_colibri2_runner.py`: явно синтетический AST-контракт и отрицательные
  проверки; отдельный optional installed-source audit, без исполнения Colibri.
- `verify_offline.ps1`: больше не требует S: и не создаёт `../c`.
  `-ColibriSource` добровольно включает read-only проверку реального исходника.
- `.github/workflows/ultra-offline-ci.yml`: добавлен полный Manager suite в
  существующий Windows job. Публикация и hosted-run в этой задаче **NOT RUN**.
- Этот существующий README содержит полный отчёт/план; новая Markdown-
  документация не создана. №07 дополнен сдачей и ограничением ротации.
- Скрипты и JSON evidence:
  `Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001`.

Изменения пользователя в `Documents/.obsidian/appearance.json` и `workspace.json`
не относятся к задаче; не редактировались. SOURCE Client и installed Client
сохранены. Проверяемый локальный diff: `git diff -- .github/workflows/ultra-offline-ci.yml
Manager_Ultra_LLM Documents/07_Задачи Codex.md`; новые файлы/evidence отдельно
видны в `git status --short`. Index не использовался.

### Матрица совместимости

Для колонки установленного Manager проверены **публичные файлы по SMB**, а не
живые HTTP-ответы или provenance процесса. В новом кандидате ниже — SOURCE/QA.

| Контракт Client R5 | Установленный Manager | Кандидат R5 / условия |
| --- | --- | --- |
| TLS, bearer SHA, IP allowlist, allowed_slots | Реализованы в старом коде | Сохранены; pairing_admin не даёт control_models; отказ без прав проверен |
| GET `/v1/snapshot` | Старый snapshot | Совместим, additive chat/control capabilities; изоляция слотов |
| POST `/v1/chat` | Есть, ordinary | Сохранён; ordinary и streaming независимы, параметры явные |
| POST `/v1/chat/stream` | Нет в установленном коде | Настоящий incremental SSE→NDJSON v2, sequence/meta/delta/reasoning/done/error; TLS Chrome PASS с fake Colibri |
| POST `/v1/chat/cancel` | Нет в установленном коде | Scope request/client/slot, разрыв чтения upstream; отмена и чужой cancel проверены unit-тестами |
| GET `/v1/control/catalog` | Нет в установленном коде | Есть каталог, статусы/причины недоступности, слоты/экземпляры; доступ через существующую авторизацию |
| POST `/v1/control` | Нет в установленном коде | CONTROL-01 check/select/add_slot/start/stop; реальные START/STOP здесь не выполнялись |
| Динамические слоты / «+» | Старые фиксированные слоты | 3 по умолчанию; QA 3→5, уникальные порты, durable SQLite; мутации требуют owner_go + control_models |
| Несколько экземпляров одинаковой LLM | Нет нового контракта | QA 2 CPU + 2 CUDA **fake**; разные UUID/порты/сессии, stop-one сохраняет второй |
| Чаты и reasoning | Legacy история | instance binding, durable история/reasoning; QA reload/recovery PASS; реальная история не читалась |
| Существующая конфигурация | Legacy config | При отсутствии control нет DB/init моделей; файл config/auth не переписывается; 3 fallback слота |
| Контроль выключен / нет прав | Legacy запреты | owner_go по умолчанию false; одних client rights недостаточно; 503/403 по существующему контракту |
| Каталог любых будущих моделей | Текущая инвентаризация | Используется существующий curated catalogue/profiles; неизвестная архитектура не становится разрешённой автоматически |

Замена кода **не** выдаёт control_models, не включает owner_go, не назначает RAM/
VRAM reviews и не начинает inference. Динамическая мутация и запуск останутся
закрытыми при legacy config. Включение control — отдельное владельческое решение.
История Client и pairing/TLS миграции не требуют. При включении control готовая
реализация создаёт/additively расширяет серверный SQLite registry, не принимает
от Client произвольный path/port и не усыновляет legacy slot1.

### TESTS / QA

Воспроизводимый запуск из workspace:

```powershell
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/run_qa.py --output qa_repeat.json
```

Нужен **новый** путь evidence; предыдущие результаты не затираются. Runner
копирует исходники в `Test`, направляет TEMP/TMP/LOCALAPPDATA туда же; Chrome
использует отдельный профиль. Для дочернего Windows PowerShell удаляется только
унаследованный PSModulePath, чтобы не подхватить несовместимый модуль PowerShell7.
Настройки системы/пользователя при этом не меняются.

Финальные результаты: **Manager 310 PASS + 1 SKIP (311 total)**,
**Client 49 PASS**, Python/JS syntax PASS, Chrome legacy/P0/P1 PASS.
SKIP — явно optional аудит реального исходника Colibri, не синтетическая замена
доказательства установленного движка. Полный PowerShell entrypoint также проверен.
Все exit codes, команды и stderr/stdout сохранены в `qa.json` и
`qa_regression.json`. Первоначальные FAIL в `qa.json` относятся к подготовке QA:
ошибка имени поля синтетического config (`token_sha256` вместо `sha256`) и
пропущенный VBS при копировании Client. Исправлены; повторены затронутые suites.
Успешные browser results сохранены без повторного бессмысленного прогона.

P0: первый DOM до DONE, UTF-8/JSON fragmentation, thinking controls, reasoning
отдельно и сохранён, identical direct/routed upstream payload. В этом **fake**
прогоне Manager first-forward delay 0.382 ms (warm 0.365), preflight 52.980 ms
(warm 48.587); browser first fragment 1364 ms cold / 435 ms warm. Client durable
SQLite claim 1273.868 / 284.264 ms — заметная часть задержки, это измеренный
локальный overhead, а не время генерации реальной LLM. Числа одного QA прогона
не являются SLA, TPS Qwen или замером серверной CUDA.

P1: 3→5 persisted slots, concurrent chats isolated, 2 одинаковых CPU и 2 CUDA
fake, stop-one, перезапуск controller/browser, история и риск cancel/confirm PASS.
Manager regression покрывает auth/owner_go, cancel, ошибки и quarantine recovery,
native job/identity/cleanup только на принадлежащих тесту dummy Python процессах.

Release QA: deterministic ZIP, relocated imports, tampering, traversal/duplicates/
link/junction/private-extra/existing target rejection PASS. Rollback QA: **66**
decision cases и **2** filesystem сценария PASS, старые runtime импорты exit 0;
восстановлены точные hashes, неизвестный sentinel и синтетические private bytes.
Никакого service restart или гарантии серверных file-locks из этого не следует.

### Релиз и rollback материалы

- ZIP: `Releases/Manager/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/UltraLLM_Manager_R5_compat_Win64.zip`.
- ZIP SHA-256: `ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2`.
- Распакованная папка рядом с ZIP, внутри полный `SHA256SUMS.txt` и `RELEASE.json`.
- Безопасная локальная копия **5 публичных runtime-файлов** старого сервера:
  `Backups/Manager/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/public_code`.
  Это **не** полный production backup: private config/auth/TLS/DB/task не копировались.
- `baseline.json` — исходные refs, файлы сервера, Client EXE SHA, пути, BLOCK4 hash.
- `rollback_qa.py`, `rollback_qa.json` — guard и репетиция; ничего не исполняют на LIVE.
- `release.json`, `qa.json`, `qa_regression.json`, `acceptance.json` — evidence.

Повторная сборка в **новое** имя, проверка и staging (на домашнем ПК только Test):

```powershell
py -3.12 -B Manager_Ultra_LLM/manager_release.py build --output M:\GitHub\local_LLM\Releases\Manager\NEW_BUILD --base-head 71462bde1f245f96180bec351e0f1ea7ecdd8b50
py -3.12 -B Manager_Ultra_LLM/manager_release.py verify M:\GitHub\local_LLM\Releases\Manager\CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001\UltraLLM_Manager_R5_compat_Win64.zip
py -3.12 -B Manager_Ultra_LLM/manager_release.py stage M:\GitHub\local_LLM\Releases\Manager\CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001\UltraLLM_Manager_R5_compat_Win64.zip --target M:\GitHub\local_LLM\Test\NEW_STAGE
```

ZIP/manifest дают целостность при сравнении с **внешним известным SHA выше**;
это не цифровая подпись. Имя staging должно отсутствовать. Прерванные папки
сохраняются для диагностики, никакого автоматического удаления/перезаписи.
`Manage-ManagerTask.ps1 Install/Remove` не используется для upgrade: он меняет
task/firewall и не является безопасным заменителем переключения существующей службы.

### План OWNER GO: preflight, установка и откат (НЕ ИСПОЛНЕН)

1. На **сервере DESKTOP-KT4G5SM**, отдельным явно разрешённым этапом, снять свежий
   PID/creation-time/exe/owner/command line Manager и listener HTTPS8443, XML и
   action/principal/restart policy `UltraLLM_Manager_LIVE`. Подтвердить совпадение
   действующего action с `C:\Server\Ultra_LLM\Manager_Live\live_manager.py`.
   Зафиксировать Qwen gateway/engine identities + health/models на 8000 и identity
   Valheim. Ничего не выводить из bearer/config/TLS key. Неизвестная identity,
   неоднозначный PID/порт/путь, активный upgrade или stale baseline → BLOCKED.
2. До остановки проверить hashes всех старых файлов относительно **свежего**
   snapshot, свободное место, ACL, runtime Python x64/3.12 и отсутствие зависимых
   процессов, использующих папку Manager как своё исполняемое место. Текущие SMB
   SHA не заменяют повторную серверную проверку. Если owner_go уже включён или
   есть незавершённые owned instances, не останавливать их и не продолжать upgrade:
   отдельное разрешение/план безопасного состояния обязательны.
3. Создать уникальный полный backup **всей** старой папки Manager (с неизвестными
   файлами) и protected backup исходного task XML, private config/auth/TLS и
   control SQLite, если существует. Сохранить ACL/owner и SHA, проверить readback.
   Для живой SQLite нужен согласованный SQLite backup API, не копия одного DB
   без WAL. Private backup остаётся на сервере под исходными private ACL, не в
   Git, не в LAN-readable staging. Непроверенный backup/restore → BLOCKED.
4. Проверить SHA ZIP, доставить **только** публичный пакет в новую sibling staging
   папку на том же server volume, сравнить все 21 файла и проверить imports `-B`.
   `PythonExe staged\live_manager.py --config ExistingPrivateConfig --check-config`
   выполнить под **тем же пользователем task** без `--log-dir`: это не создаёт
   listener и не выполняет run/ModelControl. Config/TLS/права не менять.
   Не включать owner_go для прохождения проверки. Проверка private ACL/ключа и
   реальной TLS загрузки дополнительно нужна перед переключением; --check-config
   сам по себе проверяет наличие, а не полный TLS handshake.
5. Только после отдельного OWNER GO на **Manager-only switch + rollback**:
   штатно `Stop-ScheduledTask -TaskName UltraLLM_Manager_LIVE`. Дождаться выхода
   именно подтверждённого Manager и освобождения его listener (до 30 s), снова
   сверить Qwen/Valheim identities/health. Не применять taskkill/Stop-Process по
   имени, не останавливать Python/Colibri/Valheim, не менять task/firewall.
   Проверить, что restart policy не подняла Manager повторно; иначе BLOCKED и
   отдельное согласование authority, а не самовольное изменение task settings.
6. Переименовать весь `Manager_Live` в уникальную retained rollback папку,
   затем staging в `Manager_Live` (две операции, **не** единая атомарная операция).
   При сбое второй операции немедленно вернуть прежнее имя первой папке.
   Обе операции исполнять native PowerShell `Move-Item -LiteralPath` с заранее
   проверенными абсолютными путями на server volume. Не удалять неизвестные
   файлы, старые каталоги, backups; private пути остаются прежними.
   `Start-ScheduledTask -TaskName UltraLLM_Manager_LIVE` сохраняет прежний action.
7. За bounded окно 30 s подтвердить один правильный Manager PID/listener, TLS pin,
   authenticated snapshot, capabilities streaming и GET catalogue, Client ONLINE,
   неизменность config/auth/TLS hashes и task settings, прежний Qwen health/identity,
   неизменный Valheim, отсутствие новых моделей/owned instances. Не выполнять
   POST chat/control/cancel против реальной модели без отдельного разрешения.
   Самопроверка новых API здесь — advertised capabilities + разрешённые GET;
   inference/reasoning/cancel/CPU/CUDA/stop-one требуют дальнейшего OWNER GO.
8. Любой недостоверный/отсутствующий результат, deadline, ошибка Manager/TLS/auth/
   catalogue/Client, изменение защищённых identities или config/task →
   **ROLLBACK_REQUIRED**, без ожидания "само восстановится". Перечень полей guard
   в `rollback_qa.py REQUIRED`; JSON с подтверждёнными свежими observations
   проверяется `py -3.12 -B .../rollback_qa.py --observations Observations.json`.
   Это evaluator, **не** установленный автоматический watchdog/remote executor.
9. В рамках того же отдельно согласованного Manager-only rollback: остановить
   только новый подтверждённый Manager, проверить освобождение его listener и
   отсутствие owned instances. При невозможности подтвердить эти условия —
   BLOCKED, не угадывать PID/не расширять STOP. Сохранить failed candidate целиком
   под новым именем; вернуть прежнюю retained папку в Manager_Live. Config/auth/
   TLS при неизменных SHA не трогать. Если state мог измениться, не откатывать
   живую SQLite вслепую: только согласованная consistent backup/restore при
   отсутствии owned jobs; несовпадение конфигурации/прав требует владельца.
10. Запустить прежний task, проверить прежние hashes, PID/listener/TLS/snapshot,
    Qwen и Valheim, доступ Client, config/task hashes. Не переустанавливать
    службу и не создавать новые модели для проверки. Backup/candidate/evidence
    сохранить. Если старый Manager не восстановлен — BLOCKED и остановка этапа,
    никакого самостоятельного ремонта системных настроек.

### Реальный сервер / QA / OWNER GO

**На реальном сервере только SMB read-only:** список верхнего уровня и SHA пяти
публичных runtime-файлов. `live_manager.py`:
`e15ef6ccea34fc4a6d7ba2afc2a4a37d6739d9b48884dcd99d0a9baa4584da51`;
`chat_runtime.py`:
`fc69896cc40a64237ff3125299d21d8e4a49ec0b5f0ae6ec64c1d905b9755466`.
Installed Client EXE read-only SHA:
`7614aecc6f97a5a8c1b126b745aa7d17e9dc8679774ba870ee68f18690c649df`.
При инвентаризации процесс Client отсутствовал; он не запускался. Поэтому real
Manager ONLINE/HTTP API/TLS/PID, Qwen health, Valheim identity и история в этой
задаче **NOT RUN**. Старый отчёт LIVE PASS не переносится на новый момент времени.

**Только QA:** полный регрессионный suite, TLS Chrome mock streaming/reasoning,
слоты, cancel, CPU/CUDA mock, dummy Windows jobs, package и rollback rehearsal.
**OWNER GO нужен:** реальная серверная диагностика процессов/закрытого task,
protected full backup, доставка/staging на сервер, Manager-only switch/restart/
rollback; отдельно control configuration/grants и любые реальные LLM запросы,
START CPU/CUDA/STOP. Текущая задача их не разрешает.

### PROBLEMS / QUESTIONS / DOC IMPACT / NEXT

**PROBLEMS:** §18.29 отсутствует в текущем №18 (`SOURCE UNAVAILABLE`); №13 и часть
реестра содержат устаревший migration NOW. Новые docs/историю самостоятельно не
создавал. Ротация №07 **ARCHIVE BLOCKED**: прежний БЛОК1.1 с ROOT migration и
AMENDMENT/OWNER GO сохранён в immutable main №45, но отсутствует требуемая точная
индексная запись этой TASK в №05/09. Прежний 1.1 не вытеснен, текущий оригинал
оставлен в БЛОК1 со статусом сдачи; БЛОК4 сохранён дословно. Это не препятствует
подготовленному кандидату, но ротацию нельзя назвать завершённой.
Проверка `git diff --check` исходников PASS; для №07 она сообщает о trailing
whitespace в дословной пользовательской постановке, уже присутствовавшей при
входе. Эти строки не нормализовались ради сохранения оригинала; точные номера
сохранены в `acceptance.json`. Других whitespace-ошибок задачи нет.

**QUESTIONS:** блокирующих инженерных вопросов для офлайн-кандидата нет.
Не запрашивается разрешение на LIVE. Координатору требуется проиндексировать
прежнюю TASK/AMENDMENT, затем безопасно завершить ротацию; commit отменён владельцем.

**DOC IMPACT:** координатору синхронизировать №05/09/13 и §18.25, решить отсутствие
§18.29; независимый verdict БЛОКА4 остаётся его ответственностью. Старые отчёты,
архивы и пользовательские Obsidian изменения сохранены.

**NEXT:** независимая приёмка этого локального diff, manifest и evidence. После
приёмки отдельная задача/OWNER GO на серверный preflight и Manager-only rollout
с protected backup/rollback; затем отдельные разрешённые реальные P0/P1 тесты.
На этой границе исполнитель остановился.

## UI-01 — read-only аппаратные поля для карточек Manager (SOURCE, 11.11.2026)

К `memory` live snapshot добавлены *необязательные* `ddr_generation` (DDR3/DDR4/DDR5 только при однозначной системной информации) и `installed_gib` (сумма ёмкостей Win32_PhysicalMemory). Существующие `total_gib` и `free_gib` сохранены. Если BIOS/CIM не дают достоверных сведений, поля опускаются; Client отображает «не определён». Чтение аппаратного типа выполняется только при первом обращении и кэшируется на срок работы Manager, чтобы не ухудшать каждый последующий запрос. Сервер Server77 read-only вручную подтвердил DDR4/48 GiB (модули 8+16+8+16), это **не** зашито в код.

**Статус:** 251 Manager regression PASS, первый/кэшированный опрос локальной Windows подтверждён. Действующая служба не обновлялась; новый snapshot требует отдельной live-выкладки, без вмешательства в Colibri1 или Valheim. Права, TLS, модели, firewall не менялись; кнопки START/STOP в UI пока disabled.

## CHAT-01 LIVE на сервере 11.11.2026 — настоящий proxy к Colibri1

После приёмки коммита #18 на сервере `DESKTOP-KT4G5SM` staged-код проверен на существующем private config (MANAGER_CONFIGURATION_OK), затем **только** `UltraLLM_Manager_LIVE` контролируемо остановлен/запущен. Развернуты `live_manager.py` (SHA256 `E15EF6CCEA34FC4A6D7BA2AFC2A4A37D6739D9B48884DCD99D0A9BAA4584DA51`) и `chat_runtime.py` (SHA256 `FC69896CC40A64237FF3125299D21D8E4A49EC0B5F0AE6EC64C1D905B9755466`). Backup: `C:\Server\Ultra_LLM\Manager_Live\.rollback_CHAT01_20261111_018` (четыре прежних Python модуля); staging: `.staging_CHAT01_20261111_018`. Реальные TLS/config/allowed_client_ips/pairing_admin/Firewall и другие службы не изменялись.

**LIVE QA:** из существующего домашнего `home-rex` по проверенному TLS POST `/v1/chat` → реальный Colibri1/8000 с Qwen3.6 ответ `READY` за 4,36 с, usage 20 prompt + 1 completion. Установленный Web Client CHAT01 R2 выполнил два последовательных коротких запроса и сохранил 4 сообщения. Менеджер после установки `Running`, HTTPS 8443; Colibri1 и Valheim продолжают работать. 250/250 offline Manager PASS. `/v1/start` по-прежнему 405; никаких новых LLM не запускали. Colibri2/3 остаются not_running, 2–3 одновременных генерации ещё не проверены. Детали №18 §18.23.


## CHAT-01 — безопасная отправка к уже работающей модели (исходники; 11.11.2026)

Добавлен ограниченный `POST /v1/chat` для клиента с существующим Bearer и allowed_slots. Тело ровно `{"slot_id":"slot1","model_id":"...","messages":[{"role":"user","content":"Привет"}]}`. Manager сверяет реально доступную модель, текущие права, свежий LIVE_HOST snapshot и состояние слота; только после этого отправляет запрос на `http://127.0.0.1:<порт из конфигурации Manager>/v1/chat/completions`. Клиент не может указать произвольный URL, порт или путь. При ошибке сервер возвращает отказ и не имитирует ответ. Для первого этапа одновременно выполняется не более одного запроса чата на один слот; другие слоты могут обслуживаться независимо. START/STOP не добавлены. Для короткой первой проверки задано `max_tokens=512`, `stream=false` и явное отключение thinking; режимы streaming/reasoning позже.

**Статус:** код в `GPT`, тестовый API проходил локальный HTTP roundtrip с фиктивной Colibri, все настоящие веса/процессы не затрагивались. На действующем `UltraLLM_Manager_LIVE` это ещё **НЕ развёрнуто**, до отдельного разрешения владельца и проверенного backup/rollback. Старый `POST /v1/start` по-прежнему возвращает 405.


## WEB-03 действительно установлен на Server77 (11.11.2026)

После приёмки #15 все четыре серверных Python файла pairing взяты из `main`, SHA совпадает, на сервере compile/imports/config PASS. `UltraLLM_Manager_LIVE` на `DESKTOP-KT4G5SM` запущен с новой версией и слушает HTTPS 8443; домашний Client с проверенным CA получает реальный snapshot, admin API без прав — 401, START — 405. Старые `live_manager.py` и `pairing_server.py` сохранены в `C:\Server\Ultra_LLM\Manager_Live\.rollback_WEB03_20261111_015`; staging — `.staging_WEB03_20261111_015`. `manager.json`, TLS, FW/IP allowlist, Colibri1, Valheim не менялись. `pairing_admin` для существующего `home-rex` остаётся false: живое одобрение новой заявки ещё не проверялось и требует отдельного владельческого решения. Подробнее №18 §18.21.

## WEB-03 — подготовлен безопасный Web Pairing (НЕ включён в живом Manager)

Новые серверные модули `pairing_inbox.py` и `pairing_workflow.py`, расширение `live_manager.py` и `pairing_server.py`. Уже авторизованный владелец с отдельной административной ролью `pairing_admin=true` может из своей Web Client панели увидеть новые заявки, проверить ID и фактический IP, выбрать допустимые слоты и подтвердить/отклонить клиента. **Роль по умолчанию false**. Новый Client не может сделать себя администратором. Нет API для START/STOP/lease.

**LAN Manager API после будущего развёртывания:** `POST /v1/pairing/request` — разрешённый IP + клиентский ID + SHA256 собственного токена, ответ `202 pending` и случайный идентификатор заявки. `GET /v1/pairing/status/<ticket>` — статус только для исходного IP при знании квитанции. `GET /v1/pairing/requests`, `POST /v1/pairing/approve` и `POST /v1/pairing/deny` — только с существующим Bearer админа и его `pairing_admin` ролью. Очередь хранится в оперативной памяти (TTL 10 мин, максимум 24, лимит 5 заявок/10 мин с паузой ≥3 сек между принятыми заявками для IP), после рестарта заявки теряются и подаются повторно. Разрешение нового IP требует отдельного решения по Manager allowlist и Firewall: новая функция **не** открывает порты и не расширяет сеть. Manager TLS должен быть доверенным со стороны нового Client.

**Владельческое включение роли, после отдельного разрешения:** `pairing_server.py --config <защищённый manager.json> set-pairing-admin --client-id <существующий client_id> --enable`. Отзыв — `--disable`. Это локальная привилегированная административная операция на хосте Manager, не запускать её до приёмки/разрешения владельца. Подключение к Manager из браузера выполняет локальный Python-прокси, не JavaScript. Перед развёртыванием сервера нужна его резервная копия, независимый smoke и проверка rollback.

**Ресурсные ограничения:** сервер выдаёт только права просмотра разрешённых слотов; отсутствие admission/lease означает, что кнопки START/STOP остаются неактивными. Все административные записи в manager.json защищены существующим ACL + межпроцессным файловым замком + атомарной записью, с повторным чтением роли на каждом запросе. Исходные 16 файлов `manager_dev` не изменялись.

**Состояние тестирования:** на домашнем ПК 246/246 Manager и 28/28 Client тестов PASS, включая локальный синтетический HTTP протокол (не реальный сетевой HTTPS с новым Client), тайм-ауты/отказы/неадминов/гонки grant. `UltraLLM_Manager_LIVE` на сервере продолжает выполнять прежний READ-ONLY код, новая функция в нём **НЕ развёрнута**. После приёмки — отдельное согласованное обновление службы/бэкап, проверка TLS и полномочий админа; затем пользовательский end-to-end. Техническая документация №18 §18.20.



**Статус на 10.11.2026:** исходная разработка `manager_dev`, а не установленная производственная служба. Все 16 оригинальных файлов перенесены побайтово без изменения логики из `C:\Server\Ultra_LLM\Colibri\manager_dev`. Их точные размеры и SHA-256 сохранены в `Documents/18_Техническая_документация.md`, §18.10. Локальный `.gitattributes` отключает конвертацию окончаний строк Git для исходных `.py` и `index.html`, чтобы после принятия в `main` байты оставались идентичными серверному baseline.

Существующие модули специально сохраняют исходные взаимные импорты и серверные host/path guards. **Запускать на домашнем ПК режимы `--colibri2 start/stop` нельзя**; настоящий Colibri2 не запускался. `index.html` — прежний автономный макет UL-MGR-0A, не работающий API/UI сервера.

## Повторение офлайн-тестов

На домашнем компьютере с Python 3.12, PowerShell и доступной локальной исходной Colibri 2.1.0:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify_offline.ps1
```

Проверочный скрипт использует `S:\Ultra_LLM\Engine\Colibri\c\coli` и `version.py`, **временно** копирует их в соседний с этой папкой `c`, выполняет `unittest discover`, затем удаляет временную папку. Он отказывается работать, если `../c` уже существует, чтобы не удалять чужие файлы. При необходимости источник задаётся параметром `-ColibriSource`.

Первый непосредственный прогон тестов после миграции дал 221 PASS / 2 ERROR, потому что исходные тесты ожидают соседнюю папку `../c` (зависимость Colibri, а не модификация Manager). Повтор с точными исходниками Colibri 2.1.0: **223/223 PASS**. Временные зависимости не публиковать.

## Продолжение

Разработка и проверка исходников — на домашнем ПК в Git-репозитории `local_LLM`. Проверенную серверную копию затем доставлять отдельно, с резервной копией, версией и откатом. Не заменять текущую Colibri1, Valheim, системные службы, `setup.json` и секреты. Публичный API, авторизация, реальный Colibri2 START/STOP, служба и LAN — отдельные решения владельца.

Первый клиентский офлайн-макет находится в `../Client_Ultra_LLM`. Он не подключён к этому Manager.


## Live Manager P1 — реальный серверный мониторинг (10.11.2026)

`live_manager.py` — новая, **отдельная** от исходных 16 baseline-файлов серверная программа, стандартная библиотека Python 3.12, Windows. Снимок строится из фактической ОС (Get-CimInstance RAM, Get-NetTCPConnection), локальных `/health` и `/v1/models` каждой Colibri, а также каталогов установленной модели. Сервер `DESKTOP-KT4G5SM`: копия кода уже сверена SHA-256 с `C:\Server\Ultra_LLM\Manager_Live\live_manager.py`; реальная функция `live_snapshot()` там выполнена без запуска моделей.

**Статус запуска:** HTTPS-служба и клиентское подключение **ещё не запущены/не подтверждены**: защищённое создание серверной конфигурации и клиентских credentials через автоматизированный канал было заблокировано. Сертификат и приватный ключ созданы на сервере в `C:\ProgramData\UltraLLM\Manager\private` с закрытым ACL (silver, SYSTEM, Administrators); нельзя публиковать ключ или копировать его в Git. `manager.json` пока не создан, порт 8443 не открывался. Это не production-ready service.

Серверный конфиг `manager.json` задаёт `manager_id`, `display_name`, **явные** `bind_host`/`listen_port`, абсолютные `colibri_root`/`models_root`, `cert_file`/`key_file`, `slots` (slot_id, api_port, protected), `clients` (отдельные client_id, SHA-256 токена, allowed_slots). Эти параметры позволяют независимо развернуть Manager на любом подходящем Windows-компьютере, где установлен Colibri. Рабочие пути не задаются константами в новой программе. Перед запуском потребуется завершить безопасную подготовку этих настроек на конкретной машине и проверить права доступа.

Вызов после защищённой подготовки: `python -B live_manager.py --config <private_absolute_path_to_manager.json>`. API: только `GET /v1/snapshot` по **HTTPS**, для каждого клиента `Authorization: Bearer`, сравнение SHA-256 постоянного времени; любые POST отказываются выполнять управление. Менеджер не выставляет незащищённый HTTP в LAN. Пока нет server host как Windows Service и autorun. WinRM остаётся исключительно административным каналом.

Состояния реальны, но **не дают резервирования**: `ready_unreserved` означает, что Colibri ответила на health и её scheduler по моментному снимку не загружен; `busy`, `not_running`, `unknown`, `denied` — другие состояния. Каталог `files_present_unverified` не означает установленную или совместимую модель. `reservation_granted=false` до реализации атомарной выдачи ресурса в уже существующем серверном ядре. Пока нет реальных START/STOP, аренды слота и межклиентного назначения.

**Обязательное следующее инженерное решение:** после безопасного ввода credentials проверить настоящий HTTPS-обмен со второго компьютера; затем добавить server-side admission/leases/authenticated start только через существующие `manager_core`, `service_core`, `windows_process` и guard запуска. Не строить второй процессный движок.


### 11.11.2026 — защищённый loopback HTTPS, задача CHATGPT-UL-MGR-LAN-20261111-004

Исправлены ошибки fail-closed: при отсутствии или нулевой `scheduler.capacity` больше не сообщается `ready_unreserved` (теперь `unknown`); неавторизованному клиенту не выдаются PID, имена моделей и scheduler, а клиенту без разрешённых слотов — общий каталог моделей. `bind_host` проходит проверку числового IP и запрещает wildcard/multicast/link-local. **Персональные права проверяются только на сервере; статусы не являются бронью.**

Отдельный `test_live_manager.py` проверяет эти границы. Полный прогон существующих и новых тестов — **227/227 PASS** на домашнем ПК с защищённым временным исходным Colibri fixture.

`live_tls_smoke.py` проверен **на настоящем сервере DESKTOP-KT4G5SM**: временный HTTPS-listener на **127.0.0.1:18447** с реальным серверным TLS-сертификатом, реальным `/health` Colibri1 и локальной тестовой учётной записью. Отсутствующий/неверный тестовый token => 401; разрешённый тестовый клиент => 200; клиент без прав => `denied`. TLS certificate validation PASS, Qwen3.6 обнаружена. После теста порт закрыт, постоянная конфигурация и клиентские секреты НЕ созданы. Скрипт содержит только явно тестовый маркер, действующим доступом в LAN он не является. Результат: **PASS LOOPBACK HTTPS; LAN PAIRING NOT RUN / BLOCKED.**

Копия `live_manager.py` на сервере обновлена с сохранением старого файла `live_manager.py.before_TASK004`; SHA-256 домашнего нового кода и серверной копии совпадают. 16 первоначальных файлов Colibri Manager, Colibri1/8000, Valheim и системный firewall не меняли. Переход к рабочему LAN требует безопасного индивидуального credential provisioning вне Git и отдельного подтверждённого клиента.


## Pairing Manager / Client — этап 11.11.2026

`pairing_server.py`: создаёт `manager.json` либо добавляет/отзывает клиентскую запись на **своей** машине. Принимает лишь SHA-256 токена, выданного клиентской программой; исходный bearer-token на сервер не передаётся. `live_manager.py` перечитывает права при каждом запросе, так что `revoke` действует без рестарта. Конфиг сохраняется атомарно вне Git и только в папке с защищёнными ACL. Запуск, установка службы, firewall и управление моделями в pairing-скрипт НЕ входят.

Пример администраторской команды **после** получения 64-символьного SHA-256 от первого клиента (не выполнять с placeholder):

```powershell
$py='C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe'
$src='C:\Server\Ultra_LLM\Manager_Live\pairing_server.py'
& $py -B $src --config 'C:\ProgramData\UltraLLM\Manager\private\manager.json' create `
 --manager-id manager-server77 --name 'Ultra LLM Server 77' `
 --bind 192.168.0.77 --port 8443 `
 --colibri-root 'C:\Server\Ultra_LLM\Colibri' `
 --models-root 'C:\Server\Ultra_LLM\Base_LLM\Models' `
 --cert 'C:\ProgramData\UltraLLM\Manager\private\server-cert.pem' `
 --key 'C:\ProgramData\UltraLLM\Manager\private\server-key.pem' `
 --slot slot1:8000:protected --slot slot2:8001 --slot slot3:8002 `
 --allow-ip 192.168.0.9 --client-id home-rex `
 --token-sha256 '<64_HEX_DIGEST_FROM_CLIENT>' `
 --grant-slot slot1 --grant-slot slot2 --grant-slot slot3
```

Выходные данные: `manager.json` на сервере, не в Git; список разрешённых адресов указывает только на конкретный клиент LAN. При регистрации второго Client использовать `grant --client-id <ID> --token-sha256 <64_HEX> --grant-slot slot1`. Для отзыва `revoke --client-id <ID>`, запрещено отзывать последнего клиента при работающем сервере. Серверный сертификат и приватный ключ остаются на сервере. Порт 8443, firewall, Windows Service и доступ по интернету **пока не активированы**.

На реальном сервере проверены закрытые ACL, TLS и встроенный отзыв токена (401), отказ неизвестному IP (403), наличие действующей Colibri1/8000. Следующий gate — безопасное создание личного токена на домашней машине пользователем, запись его digest на сервере и фактическое соединение через LAN.


## Постоянный LAN Manager через Windows Task Scheduler — задача №7 (11.11.2026)

**Фактически установлен на DESKTOP-KT4G5SM:** отдельная задача `UltraLLM_Manager_LIVE` от `DESKTOP-KT4G5SM\silver` с `S4U / RunLevel Limited` (НЕ SYSTEM), триггер `AtStartup`, `StartWhenAvailable`, до 10 перезапусков с интервалом 1 минута. Код `C:\Server\Ultra_LLM\Manager_Live\live_manager.py`, Python 3.12, `manager.json` в отдельном защищённом каталоге ProgramData. Manager **только читает** Windows/Colibri, не запускает и не останавливает модели. Конфиг/токены/приватный TLS-ключ **не находятся в Git**.

**Контролируемая установка на другом Windows ПК:** скопировать проверенный код Manager на новый хост, создать там отдельную защищённую private-папку, настроить установленную Colibri, порты, менеджерский сертификат и индивидуальные client credentials через предыдущий pairing. На сервере администратор запускает (пример для нашего хоста, все пути и аккаунт подставляются под конкретный ПК):

```powershell
$hostDir = 'C:\Server\Ultra_LLM\Manager_Live'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Install `
    -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json' `
    -PythonExe 'C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe' `
    -TaskUser 'DESKTOP-KT4G5SM\silver'
```

Скрипт отказывается перезаписывать чужую задачу/firewall-rule, проверяет конфиг и IP, защищает `C:\ProgramData\UltraLLM\Manager\logs` через ACL, создаёт только firewall rule по IP/порту Manager с `RemoteAddress` из `allowed_client_ips` и привязкой к `python.exe`. На текущем сервере: local `192.168.0.77:8443`, единственный remote IP `192.168.0.9`, `Profile Any` обусловлен текущим Public-профилем Ethernet; это **не** открытие для всех LAN или Internet. Никаких правил на роутере нет.

Логи: `C:\ProgramData\UltraLLM\Manager\logs\manager.log`, стандартная ротация 2 MiB × 1 активный и 3 архива. Лог содержит время/IP и событие, не пишет Authorization-header/сырой URL. `--check-config` позволяет валидировать Manager без открытия TCP-порта. Приватные папки и логи не хранить в Workspace/Git.

**Контроль состояния:**

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Status -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json'
```

**Откат при аварии/необходимости отключить Manager** (не удаляет токены, TLS-ключ, логи, Colibri):

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Remove -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json'
```

Резервная копия предыдущего файла `live_manager.py.before_TASK007` сохранена рядом с серверным Manager; восстановление файла допустимо **после** остановки задачи и проверки SHA-256. Исходный `Colibri\manager_dev` (16 файлов) не изменён.

**Приёмочное свидетельство:** `Manage-ManagerTask.ps1 Install` → задача Running, S4U, BootTrigger, 1 LAN-listener, firewall remote allowlist `192.168.0.9`. Домашний `live_client.py` вернул ONLINE / exit=0, Qwen3.6 в slot1/8000, slot2/3 not_running. Контролируемый Stop → listener 0, Start → новый PID и listener 1; повторный Client ONLINE. Colibri1 и Valheim остались работающими. Проверка штатного статуса скриптом вернула exit=0. **Перезагрузка Windows и авто-восстановление после искусственного crash НЕ тестировались** (без разрешения сервер не перезагружался).

**Важный долг по безопасности:** `silver` запущен с `RunLevel Limited`, но это всё ещё основная пользовательская учётная запись, а **не выделенный сервисный аккаунт**. Для усиленной эксплуатации рекомендуется отдельная непривилегированная локальная учётная запись с минимальными правами только на Python/Colibri read-only и private TLS key; переход — после отдельной приёмки. Нет автоматического продления TLS (текущий сертификат до 10.03.2027), мониторинг срока действия понадобится до истечения. N:M и персональные ACL поддерживаются на уровне конфигурации, реальный второй Client/Manager ещё не проверен.


## CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001 — контрольная точка A, 13.11.2026

**PREFLIGHT PREPARED / A TESTS PASS / OWNER GO REQUIRED.** Выполнен только A на
DESKTOP-SC96D3U. B/C/D **NOT RUN**, никаких действий на реальном сервере, Client,
его ярлыке или приватной истории. Это новый повтор тестов исполнителем; итоговый
независимый verdict остаётся за координатором. Никакого LIVE PASS не объявляется.

### DONE

Заново прочитаны №00/000/05/06/07/09/13, §18.29–18.30, предыдущий README и evidence
release/QA/baseline/rollback. Ветки main и GPT_2_local совпали на №47
`d51b22f2c2abcc6411a09400e7046d777261519f` (0/0). При входе уже изменены №07
(назначение этой TASK) и `.obsidian/workspace.json`; чужие изменения сохранены.

A1: авторитетный ZIP SHA-256 независимо пересчитан Python hashlib и Windows
PowerShell Get-FileHash, затем выполнен существующий `manager_release.py verify`.
Ожидаемый и фактический SHA:
`ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2`.
Все 21 файла совпадают с SHA256SUMS/RELEASE.json/прошлым release_manifest; 19 файлов
payload побайтово совпадают с рабочими исходниками и по тексту с принятым
`b484bd67f4ff6506390860efd87731cced328cad` (Git EOL нормализованы при сравнении).
Версия `R5-compat-20261113.1`, stdlib dependency closure PASS. В пакете только
разрешённые code/html и публичные метаданные/SHA: private config, bearer/TLS keys,
SQLite/WAL, история, веса и логи отсутствуют. ZIP не пересобирался и не подменялся.

A2: существующий `run_qa.py` использован без переписывания. Через Python import
изменён только OUT на namespace этой TASK, поэтому новый уникальный a2_qa.json
и все Test-каталоги изолированы от прошлых evidence. Manager/Client source
копировались в Test; TEMP/TMP/LOCALAPPDATA и временный профиль Chrome — там же.
Это повтор существующих тестов с новым запуском, а не перенос прошлых PASS.

### CHANGED / DIFF

Производственные исходники Manager/Client, установленный Client, ZIP и manifest
не изменены. В существующий README **добавлен** этот отчёт, старый текст сохранён.
В №07 добавлена только контрольная точка A вне дословной TASK; все стадии и
оригинал остаются в БЛОК1, задача не ротируется как целиком завершённая. БЛОК4
сохранён побайтово. Общие журналы/архивы и Obsidian settings не редактировались.

Новые скрипты/evidence находятся в стандартном каталоге
`Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/`:
`stage_a.py`, `diagnose_invalid_messages.py`, baseline/A1/A2/A3 JSON,
`preflight_plan.json`, `rollback_observations_template.json`, `handoff.json`,
`evidence_manifest.json`, `review.diff`. Все scratch-файлы только в Test.
Новая архитектура или новая документационная структура не создавались.

### TESTS

| Проверка | Результат | Exit | Время, s |
| --- | --- | --- | --- |
| Manager Python | 310 PASS + 1 SKIP, всего 311 | 0 | 64.000 |
| Client Python | 49 PASS | 0 | 20.063 |
| Python / JS syntax | PASS / PASS | 0 / 0 | 0.312 / 0.063 |
| Chrome legacy | PASS | 0 | 7.906 |
| Chrome P0 TLS/fake Colibri | PASS | 0 | 10.922 |
| Chrome P1 slots/fake engines | PASS | 0 | 51.265 |
| PowerShell entrypoint / Manager suite | PASS, тот же optional SKIP | 0 | 78.532 |
| Rollback decision / filesystem | 66 cases + 2 scenarios PASS | 0 | ≤1.69, см. оговорку ниже |
| A3 messages | 24 validator + 32 Client/SQLite cases PASS | 0 | 54.116 |

Для rollback инструмент измерил 1.6873353 s всей shell-команды, включавшей затем
read-only вывод evidence; отдельный внутренний timer не снимался. Поэтому это
верхняя граница, а не выдуманная точная длительность rollback. Происхождение
измерения сохранено в `execution_records.json`.

SKIP — optional реальный Colibri AST audit, без разрешённого fixture. Нативные
Windows jobs тестируются только на принадлежащих тесту dummy Python, CPU/CUDA
в Chrome — fake, настоящий inference NOT RUN. Права/owner_go/TLS и config
preservation входят в повторный Manager suite; миграция старого schema-0 SQLite
и отсутствие удаления истории дополнительно проверены синтетически в A3.

P0 подтвердил первый DOM до DONE, отдельный reasoning и сохранение. В новом
**fake** прогоне browser first fragment 1968.1 ms, Manager first-forward delay
0.304 ms; cold durable SQLite claim 1875.213 ms занимает основную часть. Это
измеренный локальный QA overhead, не серверная latency/TPS Qwen и не обещание SLA.
P1 подтвердил три default/pять persistent slots, одинаковые модели в независимых
CPU/CUDA mock instances, stop-one и reload/history isolation.

Точные команды, stdout/stderr, durations и exit codes — в JSON. Основные команды:

```powershell
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_a.py check
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_a.py qa
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_a.py rollback
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/diagnose_invalid_messages.py --output a3_diagnostics_final.json
```

Эти имена evidence уже заняты: повтор требует нового namespace/уникального
имени, старые отчёты не перезаписывать. Оригинальные run_qa.py/rollback_qa.py
исполнялись повторно с перенаправленными ROOT/OUT исключительно внутри Test;
прошлые evidence и публичный baseline backup проверены на сохранность.

### A3 — invalid_messages: доказанное и границы вывода

Старый валидатор загружен только из локального публичного backup с проверенным
SHA `fc69896cc40a64237ff3125299d21d8e4a49ec0b5f0ae6ec64c1d905b9755466`.
Новый — из принятого R5. Никаких обращений к живому серверу/личной SQLite.

| Контракт messages | Старый Manager | R5 defaults |
| --- | --- | --- |
| Всего сообщений, включая новый user | 1–16 | 1–128 |
| content одного сообщения | 1–4000 символов | до 131072; пустой content только для assistant с reasoning |
| Суммарный content + reasoning | content до 24000 | до 240000 |
| reasoning_content key | отвергается даже пустой | строка; непустая — только для assistant |
| Роли | user/assistant, последний user | то же; строгая alternation не проверяется |
| options / instance_id на верхнем уровне | invalid_fields | расширенный контракт |

Client по умолчанию выбирает до 100 старых сообщений/200000 символов и затем
добавляет новый user. На 34 **синтетических** старых строках запрос содержит
35 messages: старый валидатор возвращает invalid_messages, R5 принимает.
При истории 0 отправляется только новый запрос: оба валидатора принимают,
старые строки сохраняются. Это воспроизводит наблюдаемый владельцем тип сбоя
без чтения его данных. **Причина конкретного LIVE сбоя остаётся НЕ ДОКАЗАНА**:
нет разрешённого metadata snapshot отказавшего запроса или текущего процесса
сервера. Наиболее согласованная гипотеза — лимит старого Manager; есть и другие
независимо воспроизведённые механизмы ниже.

Длинный старый ответ >4000, сумма >24000 или reasoning_content в истории также
вызывают старый invalid_messages при ненулевой истории. Лимиты 5/10 уменьшают
count, но не гарантируют прохождение длинного content/reasoning. Нечётный budget
5 может выбрать 4 старых сообщения, поскольку context_for удаляет ведущий
assistant; это ожидаемое поведение, не потеря данных. Роли и пустые/невалидные
сообщения проверены отдельно. Правила Colibri об alternation без inference
не проверялись и не выдумывались.

Проверялось фактическое формирование body через chat_exchange → send_chat;
только manager_open заменён вызовом реального валидатора и fake ответом.
Все 32 Client кейса помещаются в старый body limit 48 KiB и имеют ровно три
legacy поля, поэтому отказы не спутаны с invalid_json_body/invalid_fields.
Для больших прямых boundary-кейсов тестируется именно валидатор; при настоящем
HTTP body может быть отклонён раньше. Реальный TLS roundtrip старого сервера
или ответ Qwen здесь не имитируется как LIVE.

Браузер SOURCE при target.streaming=false удаляет generation.options перед
ordinary запросом. Поэтому отдельные extra-field отказы воспроизведены как
отличие контрактов, но не объявлены причиной пользовательского invalid_messages.

R5 не даёт безлимитную историю: 129 total messages или превышение его явных
ceilings всё ещё отклоняются. Пока до обновления сохранён ранее выбранный
владельцем режим history=0, это workaround формирования запроса, не очистка
истории. Сам исполнитель пользовательские настройки не менял. После отдельного
GO на D — проверить history 0/5/10 и метаданные negotiated limits, без публикации
content/reasoning. Не снимать транспортные ceilings и не обрезать приватные
данные молча. Исправления/установка Client и замена принятого ZIP не выполнялись.

### PRE/POST / BACKUP/ROLLBACK

В этой контрольной точке состояние работающих Server Manager, Client, Qwen и
Valheim **NOT RUN**: защищённые процессы/task/TLS/config и история не читались,
даже публичный SMB не требовался. Исторические PID/ONLINE не выданы за текущие.
Production Client не запускался/не закрывался, ярлык не читался/не менялся.

Rollback повторён существующим кодом на Test-копии пяти публичных runtime-файлов
старого Manager; старый backup не изменён. Сценарии failed health/failed second
rename восстанавливают все hashes/unknown sentinel/private synthetic bytes,
старые runtime imports exit 0. Это не полноценный production backup и не
проверенный настоящий service rollback; protected backup остаётся будущим B.

Подготовлены `preflight_plan.json` и шаблон 16 rollback observations (все null).
Пустой шаблон даёт ROLLBACK_REQUIRED, никакого фиктивного baseline PASS.
План ссылается на прежнюю процедуру README и НЕ меняет её. Добавлено явное
preflight требование подтвердить, что Qwen/Valheim не принадлежат task/tree
Manager; иначе BLOCKED до остановки. Команды в JSON — неисполненные templates.

Gate 1: отдельный GO на B — свежие identity/task/listener/Qwen/Valheim baseline,
Python/ACL/space/owned instances, полный backup неизвестных файлов и protected
config/auth/TLS/consistent SQLite+WAL, server staging 21 SHA/import/config/TLS.
Private backup остаётся на сервере под private ACL, не Git/LAN staging.
Gate 2: после независимой приёмки A/B отдельный GO на Manager-only switch+rollback,
без изменения task/firewall/TLS/grants. Два rename не единая транзакция; сохранить
старую и failed папки. Guard/identity/config/health/deadline unknown → rollback
или BLOCKED при неподтверждённой authority; никаких broad process kills.
Gate 3: отдельный GO на реальные Qwen запросы/stream/reasoning/cancel/history.
Запуск KAT, новых моделей, CPU/CUDA START/STOP в этот этап не входит.

### PROBLEMS / QUESTIONS / DOC IMPACT / NEXT

В evidence сохранены первоначальные ошибки QA-подготовки: Get-FileHash не нашёлся
из-за унаследованного PSModulePath PowerShell7 в дочернем Windows PowerShell5.1
(exit 1); очищено только окружение дочернего процесса, после чего независимый
SHA PASS. ZIP ни разу не расходился. В A3 первоначальное ожидание отказа для
large_total/history=5 оказалось неверным: фактически выбрано 4 сообщения и
сумма допустима. Ожидание исправлено; исходный FAIL сохранён. Это не исправление
производственного кода и не скрытый test failure релиза.

Вопросов для завершения A нет. OWNER GO не предполагается и здесь не запрашивается:
сначала независимая проверка координатором. Реальная причина пользовательского
сбоя и серверная готовность требуют соответствующих отдельных разрешений.

DOC IMPACT: координатору зафиксировать свежий Windows+ZIP rerun в №05/09/13 и
§18.30, анализ invalid_messages и сохранённые gates; №06 менять только при новом
решении. №07 получил checkpoint A без переписывания TASK/БЛОК4 и без ротации
незавершённой многоэтапной задачи. Предыдущая архивная проблема из старого отчёта
уже решена координатором в №47, здесь не повторяется как действующий BLOCKED.

NEXT: независимая приёмка A и этого evidence. B/C/D не начаты; дальнейшая работа
только после адресного OWNER GO соответствующего этапа. На Gate 1 остановлено.
Commit/push/pull и изменения веток не выполнялись; текущая TASK до приёмки
остаётся локальным diff. Номер/SHA нового коммита N/A, HEAD по-прежнему №47.


## CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001 — этап B / Gate 1, 13.11.2026

**RESULT: B BLOCKED / BACKUP NOT RUN / STAGING NOT RUN / C-D NOT RUN.**
OWNER GO на B получен прямо в чате. Разрешение C/D не получено. Gate 2 ещё не
достигнут: обязательный серверный preflight не завершён. Работоспособность
процессов не предполагается по историческим PID или доступности SMB.

### DONE

На домашнем DESKTOP-SC96D3U заново сверены действующая TASK, границы B, отчёт A,
preflight plan и предыдущие evidence. Локальная main теперь №48
`b8ab83b9a11f8c8b6c6a187a1e90813d597283b6`, GPT_2_local — №47 `d51b22f`.
Это принятый владельцем результат A, не новый коммит исполнителя. Рабочее дерево
при начале B было чистым. Никаких pull/fetch, смены ветки или commit/push в B.

Проверены существующие способы серверного доступа:

| Проверка | Фактический результат |
| --- | --- |
| Desktop Commander inventory | 3 зарегистрированных устройства offline; DESKTOP-KT4G5SM отсутствует |
| SMB public Manager_Live | Папка доступна через 192.168.0.77; это только файловый доступ, не server execution |
| WinRM к DESKTOP-KT4G5SM, existing Negotiate credentials | UNAVAILABLE: ExplicitCredentialsRequired / PSSessionStateBroken |
| CIM/DCOM к 192.168.0.77, existing credentials | UNAVAILABLE: NewCimSession timeout, HRESULT 0x40004 |

WinRM сообщил, что текущие credentials для Negotiate over HTTP без TrustedHosts
или разрешения implicit credentials не могут использоваться. Эти параметры,
политики доверия, аутентификация, firewall и учётные данные **не менялись**;
пароли/сохранённые секреты не читались. CIM session не была установлена.

Транспортный probe исполнялся 8.207 s, общий exit 0 означает только корректную
выдачу JSON: обе защищённые транспортные проверки внутри него UNAVAILABLE.
Нельзя трактовать exit 0 как PASS этапа B. По условию OWNER GO о неизвестном
состоянии процессов дальнейшие серверные действия прекращены.

### CHANGED / DIFF

Добавлены только локальный read-only `stage_b_access_probe.ps1` и безопасные
JSON evidence в прежнем каталоге этой TASK. В этот существующий README добавлен
отчёт B, предыдущие отчёты сохранены. №07 дополнен отдельным checkpoint B/OWNER
GO вне исходного текста TASK; БЛОК 4 не изменён. Manager/Client runtime, ZIP,
старые backups и stage A evidence не редактировались.

Диагностика использует существующие credentials, без создания remote task,
запуска вспомогательного процесса на сервере через WMI или изменения каналов
доступа. На сервер не записывался никакой скрипт, backup или staging. Команды
C/D, Install/Remove и любые process/model START/STOP не выполнялись.

### TESTS

Точный скрипт и результаты:
`Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/`:

- `stage_b_access.json`: исходный локальный запуск через Windows PowerShell
  `-File` завершился exit 1 за 0.643 s: scripts disabled. Серверные команды этого
  запуска не исполнились. ExecutionPolicy не изменялась.
- `stage_b_access_retry.json`: те же read-only команды переданы штатным
  `powershell.exe -NoProfile -NonInteractive -Command <verbatim script>`;
  exit 0, 8.207 s; внутри WinRM unavailable и CIM timeout.
- Для дочернего Windows PowerShell исключён унаследованный PSModulePath
  PowerShell7, без изменения системного/пользовательского окружения.
- `stage_b_device_inventory.json`: наблюдённый inventory Desktop Commander;
  server device отсутствует, remote execution не производилось.
- `stage_b_owner_go_baseline.json`, `stage_b_handoff.json`,
  `stage_b_evidence_manifest.json`: границы разрешения, целостность и итог.
- `stage_b_review.diff`: локальный diff для координатора.

A-tests и SHA принятого ZIP не повторялись без необходимости; их предыдущие
артефакты проверены на неизменность. Локальная финальная проверка удостоверяет
сохранность runtime, исходной TASK/БЛОКА4/прошлых отчётов и отсутствие Git commit.

### PRE/POST

Свежие PID/creation-time/exe/owner/command line Manager, Scheduled Task XML/action,
HTTPS listener и TLS/authenticated API — **NOT VERIFIED**. Qwen gateway/engine
identities и health, Valheim и его принадлежность — **NOT VERIFIED**.

ACL, private config/auth/TLS/control gates/owned instances, Python server runtime,
место и файловые блокировки — **NOT RUN**. Никакие private файлы или логи не
читались/не выгружались. Доступность public SMB не доказывает безопасное состояние
процессов и не даёт права пропустить server-side preflight.

Прямые stop/restart/change-команды к действующему Manager, Qwen/Colibri, Valheim,
Client и другим службам отсутствовали. Их текущее здоровье не объявляется PASS,
поскольку подтвердить его не удалось.

### BACKUP/ROLLBACK

Полный серверный backup Manager и неизвестных файлов — **NOT RUN**.
Protected backup task/config/auth/TLS/SQLite+WAL — **NOT RUN**.
Серверный staging R5, сверка 21 файла, imports/config/TLS check — **NOT RUN**.
Готовность реального rollback — **NOT VERIFIED**. Ранее успешный offline rollback
QA не заменяет эту проверку. Рабочие каталоги не переключались, rollback не
требовался и не запускался. Никаких private данных в Git/workspace не копировалось.

### PROBLEMS

Обязательная identity/authority проверка сервера невозможна через доступные
авторизованные каналы. Это BLOCKED этапа B до любых server writes. Новых попыток
изменить доверие, RPC/WinRM/firewall, подбирать credentials или устанавливать
remote agent исполнитель не предпринимает.

### QUESTIONS

Дополнительное OWNER GO на уже разрешённый scope B не требуется. Нужен рабочий
авторизованный канал исполнения именно на DESKTOP-KT4G5SM либо согласованное
выполнение владельцем preflight на самом сервере с безопасным metadata evidence.
Перед возобновлением заново сверить свежие identities/доступ; не принимать
исторические PID/состояния за текущие. Секреты/пароли в чат не передавать.

### DOC IMPACT / NEXT

Координатору зафиксировать B BLOCKED из-за доступа; не отмечать backup/staging
или Gate 2 ready. Stage A PASS остаётся отдельным ранее выполненным результатом.
№05/06/09/13/18 и независимый БЛОК 4 исполнитель не менял.

Остановлено до server backup/staging. После устранения препятствия можно
возобновить только B в уже разрешённых границах с полным preflight; C и D
остаются запрещёнными до отдельных OWNER GO. Commit/push не выполнены.


## CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001 — WinRM по IP / повтор B, 14.11.2026

**ACCESS RESTORED / B BLOCKED: VALHEIM BASELINE MISMATCH / C-D NOT RUN.**
Исполнение на сервере подтверждено, прежнее препятствие WinRM по имени устранено
правильным адресованием. Однако Gate 2 не достигнут: ожидаемый владельцем
работающий Valheim не обнаружен серверными запросами. Backup/staging не начаты.

### DONE / TESTS

На домашнем **DESKTOP-SC96D3U** фактически прочитан
`WSMan:\localhost\Client\TrustedHosts`: ровно **192.168.0.77**.
`Test-WSMan -ComputerName 192.168.0.77` — REACHABLE.
`Invoke-Command -ComputerName 192.168.0.77 -Authentication Negotiate` с существующей
авторизацией — PASS. Подтверждены удалённые hostname и MachineName
**DESKTOP-KT4G5SM**, контекст **silver**, аутентификация **NTLM**, Windows
PowerShell 5.1.19041.6456. PID диагностического remoting-процесса 250388 — это
**не** PID Manager. Серверный C:\Server\Ultra_LLM\Manager_Live действительно
существует именно в удалённом контексте. Probe exit 0, 1.016 s.

Предыдущий probe обращался по имени DESKTOP-KT4G5SM, отсутствующему в TrustedHosts.
Его ExplicitCredentialsRequired не доказывал недоступность WinRM по доверенному
IP. Это упущение предыдущей диагностики исправлено без изменения настроек.
Нельзя считать hostname автоматически эквивалентным IP для TrustedHosts.

По сохранённому OWNER GO B выполнен новый **read-only** серверный preflight:

| Наблюдение | Проверенный результат |
| --- | --- |
| Remote host/context | DESKTOP-KT4G5SM / silver, administrative read/backup authority |
| UltraLLM_Manager_LIVE | Running; один Exec action, S4U/Limited, IgnoreNew |
| Task executable | C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe |
| Manager PID / creation UTC | **209432**, **2026-11-11T15:01:00.2472210Z** |
| Manager listener | ровно один **192.168.0.77:8443**, принадлежит PID 209432 |
| Process / task identity | executable, SID и аргументы процесса совпадают с task action |
| Task XML SHA-256, in memory | `b797430c62f7ef5c2e7bbdfa64283ae8739b83ede3a5fa0d9b8740e67f7b6884` |
| Runtime/config paths | ожидаемые server-local пути, reparse ancestor не найден |
| Control owner_go | выключен; значения прав не менялись |
| TLS file paths | проверены как server-local private paths; ключи не экспортировались |
| Qwen | ровно один loopback listener **127.0.0.1:8000**, один дочерний **qwen36.exe** |
| Valheim | preflight не обнаружил единственный ожидаемый процесс; безопасная запись/backup ещё не начаты |

Preflight exit 0 / 3.112 s — это выдача JSON со статусом **BLOCKED**, не PASS B.
После неуспешного Valheim predicate сделано только уточнение read-only для точного
отчёта, без попытки обхода защитного условия:

- Win32_Process Name LIKE '%valheim%': **0**;
- Win32_Service Name/DisplayName LIKE '%valheim%': **0**;
- Scheduled Tasks с Valheim в имени: **0**.

Уточнение подтверждает DESKTOP-KT4G5SM, exit 0 / 1.423 s. Command lines с игровыми
паролями не читались и не экспортировались. На вопрос о baseline владелец ответил:
**«Нет, Valheim должен работать на этом сервере»**. Поэтому отсутствие Valheim
не принимается за согласованное штатное состояние. Причина и возможность запуска
в контейнере/иной схеме этими запросами не установлены; нельзя выдавать результат
за полную диагностику/ремонт Valheim или самовольно его запускать.

### CHANGED / DIFF

Добавлены локальные read-only scripts `stage_b_ip_access.ps1`,
`stage_b_server_preflight.ps1`, новые JSON evidence и данный отчёт в существующий
README. Оригинальные отчёты A/B и source/evidence сохранены. №07 дополнен новым
checkpoint после уточнения владельца, исходная TASK и БЛОК 4 не менялись.

Никаких изменений TrustedHosts, firewall, Basic/AllowUnencrypted, credentials,
Scheduled Task, config/auth/TLS, model grants или runtime. Секреты не извлекались;
не создавались server-side скрипты, private backup, staging или новый listener.
Защищённый config прочитан **только на сервере в память** для проверки paths и
owner_go; raw JSON, токены/hash grants и TLS-ключи не передавались в workspace.
Task XML вычислен в память для SHA, файл не сохранялся и task не изменялась.

### PRE/POST / BACKUP/ROLLBACK

Новыми являются факты доступа/identity Manager и наличие gateway/engine Qwen.
Полные Qwen identity SID/health/models, TLS handshake, Python bitness, private
ACL, свободное место, DB/owned instances и файл-lock checks **не завершены**:
preflight прекратился на Valheim, следующие команды скрипта не выполнялись.
Не принимать ненаступившие проверки из текста скрипта за исполненные.

На сервере **0 записей со стороны исполнителя**, никаких service/model
START/STOP/restart, inference и переключения папок. Серверные backup и staging
**NOT RUN**, реальный rollback **NOT VERIFIED**. C/D **NOT RUN / NOT AUTHORIZED**.
Состояние здоровья Qwen и Valheim не объявляется PASS; команды управления ими
отсутствовали. Старая рабочая установка Manager остаётся без изменений.

### PROBLEMS / QUESTIONS

Доступ восстановлен, актуальный blocker теперь иной: ожидаемый работающий
Valheim не обнаружен разрешёнными запросами, и владелец подтвердил, что должен
работать. Требуется независимое выяснение корректного protected baseline
владельцем/координатором; текущая задача не даёт разрешения исправлять или
перезапускать Valheim. Дополнительный OWNER GO на тот же B не запрашивается.
После разрешения этого отклонения и подтверждения baseline продолжить только B
с новой свежей проверкой, затем protected backup/staging. C/D — отдельно.

### DOC IMPACT / NEXT

В `documentation_proposals_20261114.json` отдельно подготовлены короткие
проверенные формулировки для **№22 ag_llm** и уточнения **№18 local_LLM**.
**Это предложения, не применённые изменения.** ag_llm не открывался и не менялся;
точный путь №22 не проверялся. Сам №18 также оставлен без правок. Предложения
содержат только доказанный способ IP/Negotiate, проверку удалённого host/context
и запрет расширять доверие/включать небезопасную аутентификацию. Доступ по WinRM
не трактуется как разрешение на cutover или LLM inference.

Полные команды/exit codes/timings: `stage_b_ip_access.json`,
`stage_b_server_preflight.json`, `stage_b_valheim_clarification.json`.
Ответ владельца/baseline: `stage_b_ip_owner_clarification.json`.
Итог и SHA материалов: `stage_b_ip_handoff.json`, `stage_b_ip_evidence_manifest.json`.

Остановлено на B до backup/staging, **Gate 2 не достигнут**. Текущий main №49
`b15d5eabd3ec8325109d9c37b8f81085ab997076` сохранён, это принятый ранее владельцем
коммит. Новые commit/push/pull, смена ветки и изменения индекса не выполнялись.


## CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001 — этап B завершён, Gate 2 (14.11.2026)

**B PASS / BACKUP VERIFIED / R5 STAGING READY / GATE 2 / REVIEW PENDING.**
Выполнен только разрешённый B. Действующий Manager остаётся прежней версии.
**C/D, переключение каталогов, stop/restart сервисов и inference НЕ выполнялись.**
Это отчёт исполнителя; независимый verdict и отдельный OWNER GO C ещё требуются.

### DONE

После уточнения владельца о штатном завершении и ручном повторном запуске Valheim
сделан свежий server-side preflight через существующий WinRM **192.168.0.77 /
Negotiate**, на **DESKTOP-KT4G5SM / silver / NTLM**. Доступ/credentials/TrustedHosts
не перенастраивались. Актуальные процессы зафиксированы до и после B:

| Компонент | PID | Creation UTC | Подтверждение |
| --- | --- | --- | --- |
| Manager | 209432 | 2026-11-11T15:01:00.2472210Z | Task Running, один listener 192.168.0.77:8443, exe/SID/args совпадают с action |
| Colibri gateway | 138268 | 2026-11-08T07:13:36.7596450Z | один loopback listener 127.0.0.1:8000 |
| Qwen engine | 139516 | 2026-11-08T07:13:36.9946200Z | qwen36.exe, дочерний gateway; health=ok, qwen3.6-35b-a3b-colibri |
| Valheim | 248800 | 2026-11-13T19:14:58.4652220Z | C:\Server\New_Valhelm\Valheim dedicated server\valheim_server.exe; UDP 2456/2457 |

Qwen и Valheim находятся **вне дерева Manager**. В дереве Manager обнаружен
обычный conhost.exe, а не модельный job: отсутствие ВСЕХ дочерних процессов не
требуется и не подменяется отсутствием owned LLM instances. Идентичности,
включая creation/exe/SID, до/после совпали. Функциональный игровой тест/игроки
Valheim не проверялись; зафиксированы процесс и UDP endpoints, без вмешательства.

Python сервера 3.12.10 x64, private ACL защищён (silver/SYSTEM/Administrators),
свободно более 152 GB на C:, installed Manager соответствует прежним SHA.
owner_go=false, control_models=0, pairing_admin=0, один клиент/три слота.
SQLite/WAL/owned state DB не обнаружены до/после. TLS keypair загружается,
существующее HTTPS соединение проверено по сертификату. Серверный запрос без
авторизации отклонён **403 source_not_permitted** — ожидаемый IP allowlist gate;
это не выдаётся за проверку bearer-аутентификации/Client roundtrip.

### BACKUP/ROLLBACK — реальные серверные материалы

Создан единственный новый защищённый каталог **на сервере DESKTOP-KT4G5SM**:

`C:\ProgramData\UltraLLM\Manager_R5_STAGEB_20261114T063715Z_685df77d`

Это серверный путь, не домашний C:. Существующие каталоги не переносились и не
перезаписывались. Внутри:

- `backups\code` — **все 26 файлов / 6 каталогов** прежнего Manager, включая
  неизвестные/исторические файлы, старые .rollback/.staging и cache; SHA readback PASS.
- `backups\state` — **все 4 файла / 3 каталога** Manager ProgramData: private
  config/auth/TLS и журнал. Raw содержимое осталось исключительно на сервере.
- `backups\task_original.xml` — исходный Scheduled Task XML в UTF-16; parse и
  readback/canonical UTF-8 SHA проверены, task не перерегистрировался.
- `backups\backup_manifest_PRIVATE.json` — полный private manifest с SHA и
  исходными owner/group/DACL SDDL. SHA этого manifest:
  `aae98df0cc3a0bd7514d4d76ede8083c9268001788aab082ddaf86e66326977b`.
- `rollback_rehearsal` — **новая** копия backup старого кода/private файлов:
  все исходные bytes сохранены, old runtime imports и TLS pair load PASS.
- `rollback_acl_probe` — только новые синтетические объекты для репетиции
  возврата owner/group/DACL; действующие права не изменялись.
- `package`, `incoming`, `package_tools` — проверенный публичный ZIP и инструменты.
- `staging` — **R5-compat-20261113.1, 21/21 файлов**, ещё НЕ рабочий runtime.

Новый root защищён до копирования private данных. Все **112 объектов** нового
дерева проверены: 0 reparse и 0 посторонних Allow-SID; доступ только silver,
SYSTEM и Administrators. Исходные ACL сохранены в private manifest, а не
применены поверх backup с широкими source grants. Для репетиции private ACL
применён только к новым синтетическим объектам и затем проверен чтением.
Аудит-политика/SACL не менялась; записаны owner/group/DACL.

Старый runtime импортирован из восстановленной копии в isolated Python с -B и
отдельным несуществующим pycache_prefix: существующий legacy .pyc не исполнялся,
новые cache-файлы не создавались. Private bytes и восстановленная cert/key пара
проверены на сервере, не передавались домой. Новая папка на том же C: volume;
реальные rename/rollback рабочей установки и restart task **NOT RUN**.

Для работающего журнала сохранена проверенная копия заданной длины на момент
чтения, допускающая штатное дописывание оригинала. Это не глобальный атомарный
снимок всех логов. Non-log config/auth/TLS/code должны быть и остались byte-exact.
SQLite/WAL backup — **N/A: файлов нет**, а не тест условной/synthetic БД. Если БД
появится при будущем preflight, нужен отдельный consistent SQLite backup, без
слепого копирования одного DB или восстановления поверх работающих jobs.

### STAGING / TESTS

Использован прежний авторитетный ZIP, без пересборки:
`ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2`.
Публичные файлы переданы Copy-Item -ToSession через тот же IP/Negotiate канал;
private параметры/Task XML сформированы на сервере и не возвращались клиенту.
Helper и ZIP проверены SHA до исполнения. Штатный manager_release.py из этого
ZIP использован для verify/stage; неизвестные extras и reparse не допускаются.

На staging:

- все 21 файла/manifest/stdlib import closure — PASS;
- isolated source imports — **R5_IMPORT_OK**;
- существующий private config, без --log-dir/listener — **MANAGER_CONFIGURATION_OK**;
- после imports/config-check состав staging всё ещё ровно 21, никаких DB/cache/log;
- model-control не включался, новый listener/модель не запускались.

Новые проверки помощника на домашнем Test: 6 сценариев PASS (полнота копии,
неперезапись backup, повреждение, log append, junction refusal, host guard) и
отдельный 1 PASS на игнорирование подменённого legacy bytecode. Это offline QA,
не тест LLM. Полные A suites не повторялись без изменения продукта.

Read-only preflight v3 — **24/24 PASS**, exit 0, 4.267 s; post-check — 24/24 PASS.
Первый локальный stdin driver вернул пустой вывод: это **не** было принято за
успех; отдельная серверная read-only проверка подтвердила отсутствие новых
каталогов. Затем тот же сохранённый scriptblock исполнен штатным -Command без
изменения ExecutionPolicy. Транзакция backup/staging заняла 11.825 s и дошла до
ошибки собственного точного строкового ACL self-test; последующее read-only
уточнение/post-check — 4.942 s. Все исходные exit codes/stdout сохранены.

### PROBLEMS — почему промежуточный BLOCKED не скрыт

1. Исходная проверка ожидала только HTTP 401. Существующий source IP filter
   закономерно возвращает 403 source_not_permitted на локальный server request.
   Принят только подтверждённый 401/unauthorized либо 403/source_not_permitted;
   произвольный 403 не маскируется под PASS. TLS и auth/config не менялись.
2. Directory ACL restore PASS, file self-test сравнивал SDDL как строку. Windows
   переставила два наследуемых **Allow FullControl** ACE (SYSTEM/Administrators).
   Owner/group/protected/canonical и все SID/rights/inheritance/propagation
   совпали; Deny/object ACE отсутствуют. Read-only semantic comparison + 8
   отрицательных проверок подтвердили эквивалентность. Никакие live/backup права
   ради PASS не исправлялись. Начальный exit 2 сохранён, prepare не повторялся.

Это исправления оценки собственных проверок, а не ослабление защитных условий
или ремонт живой системы. Итог B основан на реальных backup/stage readback,
проверке прав и неизменных post identities/config/task/TLS. В независимую приёмку
переданы и промежуточные ошибки, и окончательная проверка.

### PRE/POST / CHANGED / DIFF

Task XML canonical SHA **до/после**:
`b797430c62f7ef5c2e7bbdfa64283ae8739b83ede3a5fa0d9b8740e67f7b6884`.
Private config SHA:
`87e91f7a02dc697964356e0e9ca71d28e1b41eb2954b0b0186cd08d1af313d86`.
TLS peer SHA:
`6ffd03d256372ca5a96d47719e2d5bb48e58a0d49c377e3ca326b46fe756fef1`.
Рабочие code/state non-log bytes и права, task action/settings, owner_go/grants,
сеть/firewall/TrustedHosts не изменялись. Manager/Qwen/Valheim не останавливались
и не перезапускались. Client/ярлык/его приватная история не открывались.

Изменения на сервере ограничены **новым защищённым maintenance-каталогом**.
Локально добавлены stage_b_* скрипты/evidence и этот append к существующему README,
checkpoint в №07 вне оригинальной TASK. БЛОК4 и прежние evidence сохранены.
Рабочие исходники Manager/Client и прежний ZIP не менялись. Git HEAD main №50
`35fbd14744b3d2f99788bd021e85e484ddceae1a` сохранён; новых commit/push/pull нет.

### QUESTIONS / DOC IMPACT / NEXT

Технических блокеров B не осталось. **Остановлено на Gate 2.** Требуется
независимая приёмка координатором, затем отдельный OWNER GO именно на C / Manager-
only switch + rollback. Новое разрешение не предполагается из команды «продолжай».

Независимый read-only шаблон: `stage_b_independent_verify.ps1` (после B автором
не исполнялся). Он возвращает только booleans, private данные остаются серверными.
Основные evidence: `stage_b_completion.json`, `stage_b_backup_staging_result.json`,
`stage_b_acl_readonly_diagnostic.json`, `stage_b_server_preflight_ready.json`,
`stage_b_final_handoff.json`, `stage_b_resume_evidence_manifest.json`.

Координатору актуализировать №05/09/13/18 по B, не переносить source/mock PASS
в реальный streaming PASS. Ранее подготовленные предложения №22 ag_llm и №18
local_LLM остаются отдельными предложениями; ag_llm и сам №18 здесь не изменялись.

До C заново сверить свежие PID/creation/task/config/TLS, состояние protected
процессов, backup/staging hashes и возможные новые DB/owned jobs. Доступность
rename после выхода Manager, гонка restart и настоящий service rollback ещё
не тестировались — это C, не гарантия из копирования. C/D, inference, cancel,
CPU/CUDA START/STOP и KAT не выполняются автоматически. Backup и staged/failed
материалы не удалять. Вся многоэтапная TASK пока остаётся активной в БЛОКЕ 1.


## CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001 — авторский handoff, 14.11.2026

**RESULT: PARTIAL / AUTHOR TESTED / INDEPENDENT REVIEW PENDING / RELEASE HOLD.**
Прямой активатор владельца запустил TASK после документного AWAITING OWNER START.
Это исключительно тесты/CI. Production Manager/Client, Production/Client,
сервер/WinRM/SMB/backup/staging, Qwen/Colibri/Valheim и C/D не использовались.
Никакого INDEPENDENT PASS или LIVE PASS автор себе не выдаёт.

### DONE — baseline и границы

Прочитана полная TASK БЛОКА1, относящиеся №00/000 §§3–5.1 TEST-FULL-CYCLE-01,
№05/07/07.00/09/13/18 §§18.30–18.32, workflow и существующие tests/evidence A/B.
Исходный main и GPT_2_local: №53
`12aa17c7462f3a5b492a65481d549c5ad0ad65ce`. Исполнение на DESKTOP-SC96D3U.
При входе чужое изменение только `Documents/.obsidian/workspace.json`; оно не
редактировалось и в предлагаемый diff не входит. Branch/ref/index не менялись.

Предыдущий hosted run 43572399891 на №52 — только baseline 311 Manager/49 Client
и fake Chrome. **Новый CI WINDOWS NOT RUN**: изменения ещё не опубликованы,
отдельного согласования commit/push нет. Старый run не является результатом этой
TASK. Локальные результаты относятся к №53 + working diff, закреплённому SHA
тестового файла и списками проверенных исходников в evidence, не к новому commit.

### Матрица изменение → риск → старый тест → пробел → дополнительный оракул

| Изменение/риск | Уже покрыто / переиспользовано | Пробел / добавленная проверка | Результат автора |
| --- | --- | --- | --- |
| ZIP allowlist, чужие/private entries, traversal | Старые release tests: лишний 22-й entry, symlink, junction, tamper, isolated imports | 21 entry с заменой разрешённого имени на private/traversal, отсутствующий member; проверяется отсутствие stage/escape | PASS |
| Manifest/SHA/dependency closure | Старый tamper был rejected по SHA | Согласованный manifest с новой статической lazy dependency, metadata/checksum-only tamper; build не используется вместо проверки original ZIP | PASS |
| Динамическая недоступная dependency | AST проверяет Import/ImportFrom | Согласованный synthetic payload с __import__('qa_unavailable_dependency') должен быть RED | **FAIL F2**, текущий validator принимает |
| PID/creation/exe/SID, Qwen/Valheim, Task XML | В B реальные snapshots, существующий rollback boolean evaluator | Синтетические изменения каждого identity-поля/процесса, отсутствующий protected role, task/config/TLS/grant drift; точные AssertionError/KeyError + отсутствие ready artifact | PASS |
| Listener и непротиворечивость snapshot | B live probe проверяет listener; offline completion доверяет coarse flags | Изменён только listener PID при прежнем manager/checks; приёмка должна отвергнуть | **FAIL F1a** |
| Тип guard/check и HTTP error | B coarse status/flags, live source gate различает 401/403 | Строка 'false' не boolean; 403 с произвольной причиной не разрешён | **FAIL F1b/F1c** |
| Backup TLS/auth/config bytes | B helper копирует/readback; old corruption менял длину | Равная длина, изменённые bytes, отсутствующий файл; manifest/inventory/hash — независимый файловый оракул | PASS |
| Restore failure / partial transaction | B failed-health/second-rename rehearsal | Известный OSError в записи TLS synthetic file, копия неполна, verify отвергает, source bytes неизменны | PASS |
| Foreign/stale evidence | B recorded hashes/Git, без новых LIVE действий | Подмена привязанного public evidence record и stale git head отвергаются; full re-signed private backup не выдаётся за проверенный | PASS / F3 GAP |
| ACL | Готовый acl_equivalent и его 8 негативных проверок переиспользованы | Перестановка Allow ACE — PASS, добавленный SID/права/owner/Deny — RED | PASS |
| HTTP/auth | Существующие 401/control_models/owner_go/cancel tests | Один реальный loopback HTTP сценарий: token 200 → IP denial 403 source_not_permitted → grant revoked 401 unauthorized | PASS |
| Пустой/сломанный runner, exit 0/exception | Старый bare unittest мог вернуть 0 на пустой набор | Minimum 330/49, typed FAIL/ERROR/collection controls, JSON + полный JUnit, запрет маскировать expectedFailure | PASS |
| Windows workflow | Существующий source/mock job | Тот же workflow, pinned actions/runtime, credential persistence OFF, ограниченные artifacts, независимые diagnostic steps | LOCAL STATIC PASS / HOSTED NOT RUN |

Новые тесты вызывают **готовые** Python-функции Gate2 checker/backup helper, но
ROOT/OUT направлены на Test, Git — на детерминированный fake. Ни один remote
ScriptBlock, host prepare entry point, настоящий профиль или серверный путь не
выполняется. Fixtures содержат явно SYNTHETIC PID/SID/paths/data. Оракулы основаны
на bytes/metadata/error/status и наличии файлов, а не на тексте «PASS» в stdout.

### CHANGED / DIFF — только разрешённые 5 файлов

1. `Manager_Ultra_LLM/test_manager_release.py`: четыре недостающих release tests,
   включая настоящий RED на dynamic dependency. Production manager_release.py
   не изменён; требование не ослаблено ради зелёного результата.
2. `Manager_Ultra_LLM/test_control_runtime.py`: source-denial vs revoked-grant HTTP.
3. **Единственный новый test_*.py**: `Manager_Ultra_LLM/test_gate2_hardening.py`:
   14 unit methods, synthetic snapshots/ACL/backup/restore и CI runner/controls.
4. Существующий `.github/workflows/ultra-offline-ci.yml`; второй workflow не создан.
5. Авторский append в этот существующий README; предыдущие отчёты сохранены.

Новые permanent Reports/Markdown не создавались. Детальные временные evidence
только в игнорируемом `Test/CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001`.
№07/БЛОК4, архивы, №05/06/09/13/18 не менялись: конкретный write-scope разрешает
только tests/workflow/README. Ротация/документный closeout — координатору, не
самовольная правка карточки поверх назначенной TASK.

### TESTS — ожидаемые RED отдельно от настоящих FAIL

Финальный Manager: **330 total = 325 PASS, 4 FAIL, 0 ERROR, 1 SKIP**, exit **1**,
49.911 s. Все 311 baseline cases сохраняются; добавлено 19 test methods.
SKIP — optional installed Colibri AST fixture, не отсутствие нового теста.
**Не** expectedFailure/skip: все четыре регрессионных требования остаются RED
в обычной discovery и блокируют будущий CI. Финальный JUnit содержит все 330
case entries, включая pass/skip, и корректные failures/errors/skipped поля.

Client **49 PASS**, exit 0; Python/JS syntax PASS. P0 SOURCE TLS/fake Colibri
PASS, P1 SOURCE slots/multi-instance PASS. Client и runtime bytes не изменены,
поэтому успешные P0/P1 не гонялись заново после чисто test-runner/Manager changes.

Негативные controls: **5 проверок PASS как проверки наблюдаемого результата**:
один positive exit0; deliberate assertion FAIL exit1; deliberate RuntimeError
ERROR exit1; empty collection CollectionError exit3; wrong exact ZIP exit1 с
точной причиной SHA mismatch и без output PASS artifact. Это ожидаемые RED
контроли, **не** четыре выявленных незакрытых requirement FAIL.

Legacy Chrome: первый запуск **FAIL exit1** (DOM deadline: 2 Manager cards),
9.233 s; повтор **без изменения исходников** PASS exit0, 6.810 s, console errors0.
Первый FAIL сохранён и не стёрт. F4 — нестабильность/недостаточная диагностика
first-load readiness, причина **HYPOTHESIS**, не доказанный production UI defect.
Тест Client вне write-scope не исправлялся; автоматический retry в workflow
не добавлялся, чтобы не прятать реальный FAIL.

Первые source tests: Manager329/4FAIL/1SKIP, Client49, controls, exact ZIP,
syntax, P0/P1 и первый legacy FAIL сохранены в author-first.json. Далее улучшена
полнота JUnit/provenance; full suites повторены, добавлен физический restore
fault test и выполнен финальный полный Manager330. Исходные failed logs сохранены.
Статический checker workflow первоначально ошибочно ожидал 10 run blocks вместо
9: отдельная ошибка ожидания checker сохранена, к продукту/hosted run не отнесена.

### Воспроизведение и пути evidence

Из workspace, с **новыми уникальными output именами** (повтор поверх evidence
запрещён, runner проверяет FileExists):

```powershell
py -3.12 -X utf8 -B Manager_Ultra_LLM/test_gate2_hardening.py --suite Manager_Ultra_LLM --minimum 330 --output Test/CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001/review-new/manager.json
py -3.12 -X utf8 -B Manager_Ultra_LLM/test_gate2_hardening.py --suite Client_Ultra_LLM --minimum 49 --output Test/CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001/review-new/client.json
py -3.12 -X utf8 -B Manager_Ultra_LLM/test_gate2_hardening.py --negative-controls --output Test/CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001/review-new/controls.json
```

Все TEMP/TMP/LOCALAPPDATA и новые fixtures — Test, новые suites проходят в
source COPY. Chrome запускать в такой Test-копии, а не рабочем Client/Production.
Точные команды/cwd, exit codes, timings/stdout/stderr и SHA inputs сохранены:

- `Test/CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001/baseline.json`;
- `author-first.json`, `author-final.json`, `manager-final330.json`;
- `manager-first.stderr.log`, `manager-final.stderr.log` и полные связанные stdout;
- `legacy-rerun.json`, `workflow-static-checks.json`;
- `summary.json`, `review.diff`, `evidence-manifest.json` — итоговый локальный handoff.

QA roots берутся из JSON: source_20261114_134948 и отдельный source_final_*;
в них Test/results/*.json/*.xml. Первые artifacts не заменялись финальными.
Их нет в предлагаемом Git-коммите по scope/privacy; README содержит сводку,
а новые CI artifacts появятся только после разрешённой публикации/запуска.

**Оригинальный локальный ZIP проверен чтением**: 21 файл, exact SHA
`ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2`, exit0.
Rebuild/подмена original ZIP не выполнялись. Synthetic ZIP tests не выдаются за
оригинал. **EXACT ZIP CI NOT RUN**: оригинального архива нет в sparse source
checkout, workflow явно записывает NOT RUN, не воссоздаёт его вместо проверки.

### CI / TEST-FULL-CYCLE-01

Один существующий windows-latest job, timeout25m, contents:read,
persist-credentials:false, sparse checkout разрешённых исходников/готовых safe
helper scripts, Python **3.12.10**, Node **22.20.0**. Actions закреплены полными
SHA официальных repos (проверены read-only git ls-remote, без credential helper):
checkout 11bd71901bbe5b1630ceea73d27597364c9af683;
setup-python a26af69be951a213d495a4c3e4e4022e16d87065;
setup-node 49933ea5288caeca8642d1e84afbd3f7d6820020;
upload-artifact ea165f8d65b6e75b540449e92b4886f43607fa02.
Chrome/OpenSSL image versions записываются при запуске, неизменность hosted image
не заявляется. Продуктовые тесты используют loopback/fake, нет secrets/real auth,
server access/paid API. Setup toolchain не разрешает app выполнять LIVE вызовы.

Native exit codes явно возвращаются из всех run-блоков; независимые diagnostic
steps выполняются после предыдущего FAIL, но итог job остаётся FAIL. Минимальная
collection330/49 и typed negative controls не позволяют пустому runner дать PASS.
Artifacts ограничены только JSON/XML **верхнего уровня results** + fake screenshot;
не публикуются temp/profiles/cert keys/SQLite/synthetic private folders.

PowerShell AST parse **9/9 run blocks PASS**, refs/permissions/static safety PASS.
Полная YAML schema/actionlint **NOT RUN**: такого parser/tool здесь не установлено,
новые зависимости не устанавливались. Текст вручную проверен, новый GitHub run
и проверка GitHub parser **NOT RUN** до отдельного publish GO. Новый run ID/SHA
не выдумываются. Нельзя использовать старый run43572399891 вместо этого.

### PROBLEMS / FOLLOWUP — без production-исправлений

- **F1 / CONFIRMED / Gate2 delivery acceptance:** stage_b_complete_readonly.main
  доверяет all(checks.values()) и status без строгого schema/type/relationship
  контроля. Synthetic post с прежним manager и чужим listener PID; строка 'false'
  вместо bool; 403/unrelated_forbidden при coarse PASS — принимаются и создают
  ready artifact. Нужен отдельный scope на hardened validator и регрессии. Это
  воспроизведённый дефект acceptance checker, не заявленный сбой live Manager.
- **F2 / CONFIRMED / release dependency validator:** согласованный synthetic
  manifest скрывает недоступный constant dynamic __import__. Static AST-only
  closure его не видит. Literal lazy import отвергается. Нужен отдельный scope
  на guarded dynamic import policy/validation, без произвольного исполнения
  недоверенного кода. Текущий original ZIP не содержит внесённой missing module,
  его SHA/bytes правильны; продуктовая генерация не проверялась.
- **F3 / COVERAGE GAP / private-backup provenance:** generic verify_snapshot
  проверяет соответствие данным своего manifest, а independent_verify template
  не сравнивает private manifest digest с внешним trusted expected value. Новый
  тест отвергает подмену привязанного public record/stale HEAD, но совместная
  замена private backup+его manifest не объявлена проверенным RED. Нужен отдельный
  тест/контракт trusted provenance pin в reviewer; физический сервер не трогать.
- **F4 / HYPOTHESIS:** legacy Chrome first-load deadline FAIL→PASS при тех же
  bytes. Нужны диагностика readiness/console/network при первом FAIL и отдельный
  scope на Client harness; продление timeout/retry без доказательства не сделано.

### QUESTIONS / DOC IMPACT / NEXT

Нужно адресное согласование **публикации этих пяти файлов**: единственный итоговый
commit в разрешённой GPT_2_local и push. Прямой body TASK §4 требует отдельного
согласования commit/push; верхняя отметка про исключение GitHub не трактуется как
безусловное право Codex публиковать код в main. Нового commit/SHA пока **N/A**,
перед возможной публикацией вновь сверить refs/общий номер; номер не резервируется.
Push запустит тот же workflow, и четыре незакрытых regression FAIL должны дать
красный CI. Дополнительный production-fix scope не запрашивается как скрытая часть
этой TASK; F1/F2/F3 передаются координатору как отдельные FOLLOWUP.

DOC IMPACT: координатору занести TASK/FAIL/FOLLOWUP/статусы в №05/09/13 и технику
в №18; при необходимости решения №06 и карточка №07. Конкретный write-scope
этого задания не разрешает самому редактировать эти документы, независимый
БЛОК4 или архивы. Требование TEST-FULL-CYCLE-01 не отменяется — DOC UPDATE OWNER /
COORDINATOR PENDING, а не фиктивное выполненное закрытие.

**Раздельные verdicts:** AUTHOR TESTED; TECHNICAL **PARTIAL / FAIL gate**;
CI WINDOWS **NOT RUN** (новая TASK); REAL APPLICATION **NOT RUN / forbidden**;
USER UX **NOT REQUIRED** (внутренние тесты/CI, пользовательское поведение не
изменено); RELEASE **HOLD**; INDEPENDENT REVIEW **PENDING**.

Остановиться для независимой проверки координатором и согласования публикации.
Никакого server cutover/нового backup/staging, C/D, реального inference/START/STOP,
изменения Client/ярлыка/истории/секретов. Предыдущие Gate2 материалы не изменены.
