# Задачи Codex — рабочая карточка исполнителя Ultra LLM

## OWNER RULE 24.11.2026 — NATIVE-TELEMETRY-01 / фоновая телеметрия без окон

Обязательный постоянный регламент Client/Manager: периодический polling, мониторинг RAM/VRAM, TCP и состояния процессов не должен создавать видимые окна, перехватывать фокус или запускать PowerShell/CMD в цикле. Использовать in-process Windows API (GlobalMemoryStatusEx, GetExtendedTcpTable, PDH для WDDM); статические сведения кэшировать, включая неудачный результат. Исключение только для обоснованного однократного скрытого запроса метаданных/штатной операции, с тайм-аутом и CREATE_NO_WINDOW; NVIDIA utility пока скрытый bounded probe, не PowerShell. Не отключать мониторинг ради скрытия окна и не подменять неизвестные значения нулём. Любые новые фоновые subprocess вызовы проверять на частоту, отсутствие окон и утечек; GUI/UX регрессия и проверка дочерних процессов на реальном Windows обязательны при приёмке изменений телеметрии (TEST-FULL-CYCLE-01, REFERENCE-RELEASE-01). CI с mock не доказывает отсутствие окон на физическом ПК. Повторное появление окон — дефект/HOLD. Источник решения: FIX-UL-NATIVE-TELEMETRY-20261124-001, #127; детали и evidence в №18.

**OWNER RULE 24.11.2026 — REFERENCE-RELEASE-01:** полный совместимый release candidate, exact SHA/manifest, тесты и evidence для координатора обязательны для Client/Manager. Не оставлять принятую доработку только локально; никаких смешанных эталонов, Git write/LIVE без полномочий. №000/18, DOC-UL-REFERENCE-RELEASE-20261124-001. БЛОКИ 1/1.1 не изменяются.

**Постоянная приёмка:** `TEST-FULL-CYCLE-01` (№000 §5.1, №18 §18.31) — самостоятельный инженерный разбор и тесты, GitHub CI по применимости, REAL APP и обязательный OWNER UX при значимых внешних изменениях. Действующий БЛОК 1, БЛОК 4, история и OWNER GO не меняются этой записью.


**Назначение:** здесь Codex получает конкретную утверждённую TASK, узнаёт разрешённые границы и сдаёт подтверждаемый отчёт. Карточка — оперативный документ, не личный архив и не разрешение на весь сервер.

**Редакция:** 2026-11-12; после сдачи БЛОК 1 освобождается независимо от приёмки. Указания другого проекта (Web Alarm Ultra) — только примеры, не правила или TASK этого проекта.

[[07.00_История_задач_Codex|История задач Codex]]

[[000_Задачи для агента|Общая координация задач]]

## 1. Рабочие правила Codex


**Workspace / evidence (DEC-UL-20261119-WORKSPACE-EVIDENCE-ENTER-015).** Каноническое правило — [№000, «Не выходить за корень Workspace»](000_Задачи%20для%20агента.md). Для всех проектных записей, TEMP/TMP, профилей и сборок использовать назначенный корень и проверенное место внутри него. Любая внешняя запись требует личного разрешения владельца с точным путём и операцией. Артефакты задачи хранятся в task-local `Test/<TASK-ID>/`; локальный манифест и санитизированный `WorkEvidence/` доступны для независимой проверки. Публикация и удаление в Git выполняются владельцем или уполномоченным координатором. Очистка только после независимого ACCEPTED, сохранения итогового отчёта и явного OWNER cleanup.
**OWNER RULE 15.11:** Codex работает **ТОЛЬКО ЛОКАЛЬНО**, любые `git add/commit/push` и иные Git write запрещены даже при ошибочном старом разрешении. Владелец делает локальный commit/push, ChatGPT только по отдельному поручению меняет `GPT_2_local`, независимо проверяет и пишет БЛОК 4. При сдаче DONE/PARTIAL Codex архивирует старую БЛОК 1.1 и переносит полный БЛОК 1 с AMENDMENT в 1.1, освобождает БЛОК 1. Входной STOP без работы не ротировать. №000/№06.



1. **Источник работы:** только БЛОК 1 с задачей, назначенной владельцем, либо его прямое адресное поручение с указанными границами. План, NEXT, сообщение «можно будет» или отсутствие задач — не назначение. Поправки после назначения фиксировать как AMENDMENT с датой, не заменяя первоначальный текст.
2. **Вход:** изучить этот раздел, БЛОК 1, разрешённые источники из read matrix постановки, нужные узкие фрагменты `00_Старт.md`, `02_Назначение_проекта.md`, `03_Архитектура.md` и `13_Тактический_контекст.md` **только когда это прямо предусмотрено scope**. Не читать автоматически чужие карточки, общие архивы или весь реестр. Если источник недоступен — сообщить `SOURCE UNAVAILABLE`.
3. **Границы:** выполнять только перечисленные read/write/test-действия. Без отдельного разрешения не трогать Git/GitHub, системные настройки, работающие процессы/загрузки, модели и веса, сеть, чужие файлы и рабочее хранилище. Техническая доступность не означает разрешения. Особое согласование требуется для остановки загрузок и любых установок/удалений.
4. **Инженерный подход:** сначала установить существующее состояние, проверить переиспользование и соседние ограничения; выбрать минимальное достаточное решение. Делать проверяемые изменения, фиксировать подтверждённые факты и отдельно гипотезы. Не расширять TASK из-за попутной находки.
5. **Проверки:** выполнять оговорённые тесты в разрешённой среде, указывать команды/результаты и `PASS / FAIL / SKIP / NOT RUN`; для документации проверять содержимое, ссылки, отсутствие потерянных записей и граф Obsidian. Самопроверка Codex — доказательство исполнителя, **не** независимая приёмка.
6. **Сдача:** сохранить полный отчёт и, когда согласовано, manifest/evidence в постоянном разрешённом месте. Ответ в чате содержит `DONE / CHANGED / DIFF / PROBLEMS / QUESTIONS`, фактический статус, тесты, риски, DOC IMPACT, адрес отчёта и предложенный NEXT. Не выдавать черновик за завершённый отчёт.
7. **Приёмка и история:** ChatGPT-координатор отдельно проверяет результат, сохраняет полную исходную постановку и отчёты, заполняет персональную историю, общий реестр/хронологию и тактический контекст. Codex **не пишет себе independent PASS** и не изменяет личный архив.
8. **Ротация:** после отчёта/evidence Codex переносит дословную TASK из БЛОКА 1 в 1.1 со статусом SUBMITTED / REVIEW PENDING и освобождает БЛОК 1. Независимая приёмка не требуется для ротации. Перед заменой прежнего 1.1 его полный оригинал и AMENDMENT должны иметь проверенный постоянный адрес (Git SHA + №05/09); иначе ARCHIVE BLOCKED. БЛОК 4 и архивы меняет только координатор.

### Среда Codex/Desktop — обязательная проверка путей

Codex работает **на компьютере владельца**, поэтому обращается к файлам Ultra LLM по сетевому корню `\\192.168.0.77\Server\Ultra_LLM` (например, к `Documents`, `Colibri`, `Base_LLM\Models`). Путь `C:\Server\Ultra_LLM` — локальный **на сервере**, не предполагаемый диск Codex. Он допустим внутри BAT, который будет исполняться на сервере, но файл BAT агент редактирует через UNC. Запуск BAT с UNC на компьютере агента не запускает его на сервере. Указать фактическую машину, путь, доступ, права, место выполнения и тестовый scope; если нет права удалённого запуска — `NOT RUN`. Правило — `000_Задачи для агента.md` → §3.1.

## 2. Что должна содержать назначенная TASK

- **TASK ID / дата / исполнитель / цель и критерий результата.**
- **Read matrix:** точные пути, разделы и необходимость чтения.
- **Write scope:** перечисление разрешённых каталогов/файлов; что менять нельзя.
- **Ограничения/разрешения:** процессы, сеть, Git, модели, личные данные и системные действия отдельно.
- **План доказательств:** тесты, критерии приёмки, обработка ошибок и границы проверки.
- **Отчётность:** место постоянного отчёта, минимальный состав `DONE/CHANGED/DIFF/PROBLEMS/QUESTIONS`.
- **Границы завершения:** что считается результатом, что требует нового решения владельца.

**Если TASK неполная или противоречит правилам:** уточнить только блокирующие вопросы; не расширять разрешения предположением.

## 3. Рабочие блоки

**БЛОК 1** — действующая дословная постановка (её сюда помещает владелец); **БЛОК 1.1** — последняя сданная дословная постановка для проверки, только после сохранения предыдущих материалов; **БЛОК 2** — краткий фактический результат; **БЛОК 3** — реальные OPEN и предложения NEXT; **БЛОК 4** — отдельное заключение независимого координатора. Это **структура Markdown**, не автоматизированная система переключения слотов.

### БЛОК 1 — ТЕКУЩАЯ ЗАДАЧА

**TASK ID:** `CODEX-UL-MODEL-METRICS-PANELS-20261126-001`  
**Дата:** 26.11.2026. **Исполнитель:** Codex / Sol, координатор Colibri Ultra 18. **Статус:** OWNER GO / ASSIGNED, локальный старт после синхронизации владельцем. **Приоритет:** P1, параллельно только в изолированном SOURCE/OFFLINE scope; первый M1-10 WEB35 остаётся главным и не блокируется этой задачей.

**Owner acceptance direction:** три скриншота владельца 26.11: (1) обзор серверов — справа от «Контекст» в каждой строке slot; (2) выпадающий выбор модели в чате — после model/slot, а также выбранное значение; (3) новая отдельная карточка «Статистика модели» над «Настройки CUDA» в правой колонке. Все правые карточки должны иметь прокрутку, регулируемую высоту, желательно перестановку. Существующий стиль, названия, история, кнопки и layout сохраняются. CPU/CUDA одной модели различать обязательно.

**Baseline / PLAN_READ:** Colibri GPT_2_local #148 13f6f6b8b246fa490b7b3a10b509fb06c6d88d64, main 8df5b5ec5cb363b1ad522516865fc7f4d2a8ebbe (HOME main clean на момент чтения; три main-only Obsidian файла, №148 ещё не принят). WEB GPT #678 44bfd80396d46307140bd6b04a60101340405e95, [проект требований WEB35](https://github.com/maxrus82gm-svg/ag_llm/blob/44bfd80396d46307140bd6b04a60101340405e95/Документация/Локальные%20LLM%20—%20подключение%20и%20статистика.md). LOCAL-PLAN-01 прочитан заново через штатный helper на HOME 26.11.2026 при постановке: SHA256 b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee; архив прочитан; COLIBRI MVP1 SUBMITTED / WUA IN_PROGRESS / M1-10 HOLD; общий план не меняется. Перед стартом проверить HEAD, чистоту, отсутствие параллельной работы над теми же файлами и фактический БЛОК 1. Owner merge/pull №148 и этой карточки, no Git write Codex. Если source не соответствует — STOP.

#### A. Producer / P0 внутри задачи
1. Аудит существующей Manager DB/telemetry, engine adapters, request journal, /v1/snapshot, Client history/polling и Bridge. Найти уже существующие counters, measurement provenance и фактические возможности CPU/CUDA. Не создавать параллельный источник. Coordinator source observation: Client_Ultra_LLM/bridge_runtime.py terminal telemetry содержит engine_decode_tokens_per_second=None; это не доказательство отсутствия метрик в Manager. Сопоставить source/tests. Переиспользовать существующее storage; если необходимо, согласованная additive SQLite migration в приватной Manager DB, без записи в рабочую DB в тестах. Новый постоянный source file только если действительно необходим и явно выделен в отчёте; существующие модули предпочтительны.
2. Manager — единственный источник постоянной статистики. Series key: manager_id + стабильная model_key/verified model revision + execution_mode CPU/CUDA + существенные фактические config/engine/hardware параметры (threads, device, context, offload, precision и т.п.). instance_id/request_id — для LIVE, не для долговременной серии. Разные слоты и перезапуски одинаковой серии объединять; разные хосты, модели, CPU/CUDA, конфиги не смешивать. Неизвестная идентичность/параметры — явно unknown, не присваивать чужую серию.
3. Измерять фактический decode tok/s (native предпочтительно, derived только при корректных счётчиках и decode-only интервале с provenance). Не делить tokens на полное время запроса, не считать символы токенами, не смешивать TTFT/prefill/network. LIVE per-instance/request, AVG arithmetic mean завершённых достоверных per-request samples; sample count, last measured timestamp, source, config; max только при подтверждённых измерениях. Один terminal success sample на уникальный запрос/серии, идемпотентность при duplicate/replay/restart, failed/cancelled/unknown отдельно, не искажают AVG. Не сохранять prompt/answer ради метрик. Persist across model stop/Manager restart, safe transactional migration/recovery; no synthetic historic backfill; missing value — «—», stale marked timestamp. Статистика read-only для Client, с действующими auth/ACL/slot scope; no launch/stop.
4. Client получает bounded current live and historical aggregate from all authorized Managers, не пересчитывает накопление; отсутствие/старый Manager graceful UNKNOWN, no additional load on inference. Использовать существующие poll/stream где возможно; bounded cadence/cache, race guards by selected manager/model/instance/request. NATIVE-TELEMETRY-01: no periodic shell/windows, no focus theft. Согласовать additive producer API/schema и compat с WEB35; Bridge v1.0.0 strict schema не расширять односторонне, отдельный read-only wire proposal/test matrix в отчёте; actual Bridge/WUA wire change only after joint approval. WUA consumer/UI вне scope. Если native decode unavailable, показать unknown and report exact limitation, не fabricate numbers.

#### B. Web Client / UX (три owner screenshot anchors)
- Обзор серверов: в каждой строке slot после «Контекст» компактно CPU/CUDA (если не видно) и «LIVE … ток/с» для действительно генерирующего instance; «AVG … ток/с» для idle/stop при известной серии. Для stopped slot с невыбранным режимом не угадывать последний CPU/CUDA: показать отдельные CPU AVG и CUDA AVG при известных совместимых сериях либо «—»; для error/offline отличить stale/unknown. Tooltip/details: число samples, дата, provenance/config. Не менять ширины обязательных Start/Stop controls, responsive wrap без перекрытия.
- Чат, модель selector: отображать model/slot + CPU/CUDA и соответствующую скорость для каждого доступного экземпляра, также в выбранном значении. Не выбирать только по display name, use stable IDs. Пример формата (иллюстрация, не реальные данные): «Qwen 3.6 · slot1 · CUDA · AVG 16.4 т/с», «Qwen 3.6 · slot2 · CPU · LIVE 5.2 т/с». При длинном label сохранять видимость mode; доступный native select/keyboard/focus, без лишнего переписывания. Смена Manager/slot/instance/config обновляет сведения, no wrong-slot metric. Не менять chat identity/history/selection semantics.
- Правая колонка чата: отдельная карточка «Статистика модели», по умолчанию над «Настройки CUDA» (и над событиями/настройками чата при CPU). Выбранная model, Manager, mode/instance/status, LIVE, AVG, samples, last measured, source, actual context/threads/device/config если подтверждены. LIVE только при active generation and fresh valid sample, AVG сохраняется после Stop; selected chat independent. Отделить «События чата» (конкретный запрос) от накопительных model stats.
- Общая переиспользуемая механика правых карточек «Статистика модели», «Настройки CUDA», «События чата», «Настройки чата» и других существующих секций: внутренний вертикальный scrollbar, возможность drag ручки resize высоты вверх/вниз, минимальные и разумные максимальные размеры, прокрутка всей колонки при нехватке места, видимые ручки и keyboard alternative; независимый resize каждого окна. Порядок карточек перемещаемый вертикально за заголовок/drag handle (не за кнопки/scrollbar/inputs), fallback move up/down; сохранение порядка/высоты в локальных UI preferences, reset default, backward-compatible, не трогать chat data. Drag cancel, pointer capture, no overflow, responsive narrow layout, detached existing chat preserve; не создавать отдельные OS окна или менять always-on-top в этой задаче. Если перестановка конфликтует с существующим detached layout, реализовать resize+scroll и отдельно PARTIAL с причиной и тестом, не ломать управление. Не менять левый sidebar/composer, не мигрировать history, не трогать глобальный CSS без необходимости.

#### C. Scope / read matrix / acceptance
Read: AGENTS.md if present, Documents/00_Старт.md, 000_Задачи для агента.md (current rules), 07 block 1, 13 current §5–6, 18 relevant metrics/telemetry/DB/REFERENCE-RELEASE, 23 owner guide; WUA #678 linked design read-only. Existing Manager source/API/storage/adapters and tests, Client_Ultra_LLM/web_client.py, web_assets/index.html/client.js/styles, test_web_client.py, existing Chrome harness and bridge_runtime.py for audit. Write: relevant existing Manager/Client source and tests only, task-local Test/<TASK-ID> and approved report; owner guide #23 update relevant fields, no unapproved docs rewrite. No WUA repo edits, no live profiles/DB/weights/network/production deployments/restarts/inference or other real calls; only isolated scratch/mock fixtures and isolated Chrome. No Git write by Codex. Existing #147 Windows CI failure baseline known: report separately, do not weaken tests or count baseline failure as PASS. Full relevant Manager/Client unit and Chrome regression (legacy/P0/P1/independent chats), bridge v1 regression and isolated migration test; verify valid/missing/stale/live transitions, duplicate terminal, cancel/fail, restart persistence, same-name CPU vs CUDA/host/slot, config change, no old response overwriting, auth negative, UI resize/scroll/drag persistence/F5/reset and no clipped controls/focus/input loss. Test data must clearly be synthetic, never injected into running app. Include screenshots of all 3 UI locations from isolated build and explicit NOT RUN for physical telemetry/OWNER UX; CI exact source and independent review by coordinator, actual deploy only separate owner GO per REFERENCE-RELEASE-01. Keep old metrics/session history, preserve existing Bridge/registration. No task activation for WEB35 or shared plan change.

**Deliverable:** DONE/CHANGED/DIFF/PROBLEMS/QUESTIONS; exact source paths, audited metrics/store/API mapping, series/dedup calculation and test evidence, isolated screenshots, config/UI guide impact, safe wire handoff draft for WEB35, candidate version/manifest per release rules; use existing report convention and `Test/CODEX-UL-MODEL-METRICS-PANELS-20261126-001/`. If producer actual speed cannot be confirmed, no fake values; distinguish PARTIAL vs PASS. On author submission follow existing BLOCK 1→1.1 rotation only with prior archive verified, not independent acceptance. Coordinator updates #05/09/06/13/18 after evidence; no claim of installation or LIVE.

### БЛОК 1.1 — ПОСЛЕДНЯЯ СДАННАЯ ЗАДАЧА (ДОСЛОВНЫЙ ОРИГИНАЛ)

# БЛОК 1 — Восстановление и обновление домашнего Manager

**TASK ID:** `FIX-UL-HOME-RELEASE-DRIFT-20261124-001`

**Дата:** 24.11.2026  
**Исполнитель:** ChatGPT / Sol  
**Приоритет:** P0  
**Статус:** ASSIGNED после подтверждения владельцем.

## 1. Цель задачи

Восстановить полноценную работу Manager на домашнем компьютере, привести установленную версию в соответствие с актуальным Client, проверить совместимость компонентов, работу Restart, изменение контекста, статусы и освобождение ресурсов.

Подготовить воспроизводимую процедуру установки и обновления Manager на других компьютерах.

Работать непосредственно на домашнем компьютере средствами локального исполнителя, максимально экономя Desktop Commander.

## 2. Обязательные документы для чтения

Корень проекта:

`M:\GitHub\local_LLM`

Репозиторий:

`https://github.com/maxrus82gm-svg/local_LLM`

Рабочая ветка разработки: `GPT_2_local`.

Перед выполнением ознакомиться:

- `AGENTS.md` — при наличии.
    
- `Documents/00_Старт.md`
    
- `Documents/000_Задачи для агента.md`
    
- `Documents/07_Задачи Codex.md` — регламент и текущий БЛОК 1.
    
- `Documents/13_Тактический_контекст.md`
    
- `Documents/05_Реестр_задач.md`
    
- `Documents/09_История_задач.md`
    
- `Documents/18_Техническая_документация.md`
    
- `Documents/06_Журнал_решений.md`
    

В больших документах читать прежде всего записи по следующим TASK ID:

- `FIX-UL-HOME-RELEASE-DRIFT-20261124-001`
    
- `DOC-UL-REFERENCE-RELEASE-20261124-001`
    
- `FIX-UL-NATIVE-TELEMETRY-20261124-001`
    
- `FIX-UL-CUDA-OWNER-BUDGET-20261124-001`
    

Особое внимание регламентам `REFERENCE-RELEASE-01`, `TEST-FULL-CYCLE-01`, `NATIVE-TELEMETRY-01` и `LOCAL-PLAN-01`.

## 3. Актуальное состояние GitHub

Последний подтверждённый коммит координатора:

**№133**

`9dfb5de6c2c10494e43d493deb50c824f837fa86`

Ссылка:

[https://github.com/maxrus82gm-svg/local_LLM/commit/9dfb5de6c2c10494e43d493deb50c824f837fa86](https://github.com/maxrus82gm-svg/local_LLM/commit/9dfb5de6c2c10494e43d493deb50c824f837fa86)

Проверенная программная основа:

**№127**

`95503306e32cf334d3c7635795ece9e367a258af`

GitHub Actions:

`45387011418` — SUCCESS.

Между №127 и №133 изменялась только документация. Координатор подтвердил это сравнением GitHub.

Перед началом проверить фактический HEAD, состояние рабочего дерева, наличие конфликтов и соответствие исходников.

Не выполнять Git write-операции. Commit, push и merge осуществляет владелец.

## 4. Фактическое расположение компонентов HOME

Компьютер:

`DESKTOP-SC96D3U`

Локальный IP:

`192.168.0.9`

### Установленный Manager

`S:\Ultra_LLM\Menager`

Конфигурация:

`S:\Ultra_LLM\Menager\private\manager.json`

База управления экземплярами:

`S:\Ultra_LLM\Menager\private\control_state\control.sqlite3`

Каталог экземпляров:

`S:\Ultra_LLM\Menager\instances`

Задача Windows Task Scheduler:

`UltraLLM_Manager_LIVE`

Manager ID:

`home-sc96d3u`

Адрес Manager:

`https://192.168.0.9:18443`

### Исходники Manager

`M:\GitHub\local_LLM\Manager_Ultra_LLM`

### Исходники Client

`M:\GitHub\local_LLM\Client_Ultra_LLM`

Пользовательские настройки Client:

`%LOCALAPPDATA%\UltraLLM\Client\managers.json`

История чатов:

`%LOCALAPPDATA%\UltraLLM\Client\chat_history.sqlite3`

Фактический порт Client при последней проверке:

`127.0.0.1:50158`

Проверить актуальность всех путей и процессов перед действиями. Не путать Git-репозиторий с реально установленным Manager.

### Движок и модели

Известные пути домашней установки:

`S:\Ultra_LLM\Engine\Colibri`

`S:\Ultra_LLM\Engine\colibri-v2.1.0-windows-x86_64-cuda`

`S:\Ultra_LLM\Base_LLM\Models`

Фактические пути и параметры брать из проверенной локальной конфигурации Manager. Не заменять движок и веса моделей.

## 5. Уже установленная причина неисправности

Координатор провёл физическую диагностику домашнего компьютера.

Обнаружено:

- Установленный Manager устарел относительно актуального Client.
    
- Установленные `live_manager.py`, `control_runtime.py`, `colibri2_runner.py` отличаются от актуальных исходников.
    
- В установленном Manager отсутствует `restart_runtime.py`.
    
- В SQLite отсутствует таблица `restart_jobs`.
    
- Client содержит актуальную реализацию Restart, но установленный Manager не обеспечивает соответствующий функционал.
    

Симптомы:

- После перезапуска LLM некорректно обновляется статус.
    
- Значок контекста остаётся жёлтым.
    
- Выбранный контекст 16384, фактический — 8192.
    
- На Server77 аналогичная операция работает правильно.
    

Основной подтверждённый дефект — несовместимость установленных версий. Причинную связь с симптомами окончательно подтвердить повторным тестом после обновления.

Не начинать переписывать механизм Restart без доказательства необходимости.

## 6. Важное уточнение по Qwen

Первоначально предполагалось, что после остановки Qwen остаётся процесс `qwen36.exe`.

Диагностика установила, что PID 35356 принадлежал активному экземпляру KAT-Coder CPU:

`516385156ac64cb5bbe8708fda3cad9d`

Цепочка процессов на момент диагностики:

Manager → Supervisor → Gateway → `qwen36.exe`.

Исполняемый файл `qwen36.exe` используется движком Colibri для разных моделей, включая KAT-Coder.

Поэтому имя процесса не является доказательством запуска Qwen.

Четыре предыдущих экземпляра KAT имели STOPPED, released=1 и подтверждённую очистку.

Владелец впоследствии штатно остановил KAT-Coder. Перед обновлением подтвердить это фактически.

Запрещено завершать процессы только по имени или историческому PID.

## 7. Этап A — Предварительная проверка

Проверить:

1. Фактические версии установленного Manager и Client.
    
2. Полный состав runtime-файлов и зависимостей.
    
3. Отличия от проверенного релиза №127/№133.
    
4. Конфигурацию, текущие слоты, модели, режимы CPU/CUDA.
    
5. Отсутствие активных экземпляров и запросов.
    
6. Состояние процессов, Supervisor, Gateway, TCP-портов.
    
7. Совместимость схемы SQLite и предусмотренные миграции.
    

Не выводить токены, ключи, содержимое личных чатов или другие секреты.

Если обнаружится активная генерация, неоднозначная принадлежность процесса или недостаток прав — HOLD с объяснением владельцу.

## 8. Этап B — Резервное копирование

Перед обновлением создать защищённую резервную копию в отдельном каталоге внутри:

`S:\Ultra_LLM\Menager\private`

Например:

`release-home-133-YYYYMMDD-HHMMSS`

Сохранить:

- Полный текущий runtime Manager.
    
- Конфигурацию и локальные настройки.
    
- SQLite с проверкой целостности.
    
- TLS-сертификаты и действующие разрешения.
    
- Состав файлов и контрольные суммы.
    
- Параметры задачи Task Scheduler.
    
- Необходимые настройки и состояние Client перед обновлением.
    

Не менять историю чатов и регистрацию Manager. Не публиковать резервные копии и секреты в Git.

Подготовить и проверить процедуру отката до остановки Manager.

## 9. Этап C — Обновление Manager

Применять регламент `REFERENCE-RELEASE-01`.

Подготовить полный совместимый комплект runtime Manager и Client из единого проверенного Git SHA.

Ориентир полного комплекта — 39 runtime-файлов: 22 Manager и 17 Client. Точный состав сверить с действующим манифестом и кодом упаковки.

Использовать существующие механизмы подготовки релизов, проверки зависимостей и конфигурации.

Не заменять произвольные отдельные файлы поверх несовместимой старой установки.

Если Client уже соответствует совместимому релизу, не переустанавливать его без необходимости.

После подтверждения idle-состояния и резервного копирования выполнить согласованное владельцем обновление HOME Manager.

Сохранить:

- Manager ID.
    
- HTTPS-адрес и порт.
    
- Существующую регистрацию Client.
    
- TLS и авторизацию.
    
- Историю чатов.
    
- Настройки слотов.
    
- Индивидуальные профили моделей.
    
- Пути движка и моделей.
    

Проверить миграции БД штатным механизмом приложения. Не создавать таблицы вручную для имитации совместимости.

Если необходимы административные права, использовать штатное подтверждение владельца. Не обходить UAC.

## 10. Этап D — Проверка после обновления

Обязательная матрица приёмки:

|Проверка|Критерий|
|---|---|
|Manager ONLINE|Подтверждён|
|Client видит HOME|Прежний Manager ID|
|Client видит Server77|Подключение сохранено|
|Файлы релиза|Проверены по манифесту|
|База данных|Целостность подтверждена|
|Restart API|Доступен|
|Схема restart_jobs|Штатно создана|
|История чатов|Сохранена|
|Запуск KAT CPU|READY|
|Изменение контекста|8192 → 16384|
|Restart|Подтверждён новый instance_id|
|Статус чата|Зелёный «Запущен»|
|Значок мозга|Нейтральный после применения|
|Генерация ответа|Успешная|
|Stop|Подтверждено завершение экземпляра|
|Освобождение ресурсов|Проверены процессы и порт|
|Фоновые окна PowerShell|Не появляются|

Владелец самостоятельно выполняет реальные Start/Restart/Stop моделей либо даёт отдельное явное разрешение исполнителю.

Если тест не проведён, указывать NOT RUN. Не выдавать предполагаемый результат за PASS.

## 11. Этап E — Подготовка CUDA

Домашний компьютер:

- NVIDIA GeForce RTX 3070 Ti.
    
- Физическая VRAM: 8 ГиБ.
    
- Драйвер NVIDIA: 610.88.
    
- Последнее измерение владельца: 1614 МиБ занято из 8192 МиБ.
    

Эти значения являются историческим снимком. Перед запуском измерять актуальные RAM и VRAM.

После успешной проверки CPU:

- Проверить поддержку CUDA установленным движком.
    
- Проверить runtime review и разрешения моделей.
    
- Проверить корректность путей и библиотек.
    
- Проверить отсутствие искусственных ограничений, не согласованных владельцем.
    
- Проверить актуальные настройки бюджета CUDA и порога предупреждения.
    

Не отключать защитные механизмы без обоснования.

Фактическое включение CUDA и запуск модели — отдельный этап после подтверждения владельцем.

## 12. Постоянное требование к развёртыванию

Необходимо исключить повторение ситуации, когда Git-репозиторий обновлён, а реально установленный Manager продолжает работать со старым кодом.

В документации сформировать воспроизводимую процедуру:

- Первичная установка Manager.
    
- Первичная установка Client.
    
- Обновление обоих компонентов.
    
- Проверка совместимости версий.
    
- Проверка путей реально запущенных процессов.
    
- Проверка API и схемы БД.
    
- Резервное копирование.
    
- Миграция настроек.
    
- Приёмочные тесты.
    
- Откат.
    

Предложения по автоматическому контролю совместимости версий и установщику описать отдельно. Не расширять исходную задачу необоснованными архитектурными изменениями.

## 13. Запрещённые действия

- Изменять Server77 и его модели.
    
- Изменять рабочий компьютер DESKTOP-43PAEBO.
    
- Продолжать настройку WireGuard в рамках данной задачи.
    
- Изменять Web Alarm Ultra.
    
- Удалять веса моделей.
    
- Удалять историю чатов.
    
- Перезаписывать ключи и токены.
    
- Выполнять Git commit/push/merge.
    
- Создавать новые постоянные документы без разрешения владельца.
    
- Самостоятельно назначать следующую TASK.
    

## 14. Документация и отчётность

Обновить существующие документы:

- №05 — статус TASK и результаты.
    
- №09 — подробная история выполнения.
    
- №06 — подтверждённые инженерные решения.
    
- №13 — актуальное состояние, OPEN и NEXT. Не превышать 30 000 символов.
    
- №18 — техническая процедура установки, обновления, проверки и отката.
    
- №07 — результат, OPEN и штатная ротация Блока 1 после сдачи.
    

Сохранить оригинальную постановку и историю предыдущих задач.

БЛОК 4 заполняет только независимый координатор.

Последнее подтверждённое чтение LOCAL-PLAN-01 координатором: 24.11.2026, 22:46:34+05.

SHA общего плана:

`8f2a756a79ccbf200228c9df0ac4e466547ff28a4f83dc62a5e187536a26514f`

SHA архива:

`1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102`

Совместный план WUA не изменять. Перед официальным назначением/изменением задачи выполнить обязательную актуальную сверку по регламенту координатора.

## 15. Формат сдачи

**DONE** — выполненные действия.

**CHANGED** — изменённые файлы и компоненты.

**DIFF** — состояние до и после.

**TESTS** — команды, фактические результаты, PASS/FAIL/SKIP/NOT RUN.

**BACKUP** — расположение резервной копии и процедура отката.

**PROBLEMS** — обнаруженные проблемы.

**QUESTIONS** — необходимые решения владельца.

**DOC IMPACT** — изменения документации.

**NEXT** — рекомендуемое продолжение.

Не называть собственную проверку независимой приёмкой.

Главная цель — получить исправный, совместимый и воспроизводимо устанавливаемый HOME Manager, а не просто формально обновить несколько файлов.

## AMENDMENT 24.11.2026 — авторская сдача FIX-UL-HOME-RELEASE-DRIFT-20261124-001

**INSTALLED / TECHNICALLY VERIFIED / OWNER MODEL ACCEPTANCE PENDING.** Full report: `Documents/Reports/FIX-UL-HOME-RELEASE-DRIFT-20261124-001/report.md`; sanitized evidence: `evidence.json`. HOME full Manager release #127 installed 23/23 exact, native restart_jobs migration PASS, Manager22224 and Client35376 ONLINE, same IDs/ports/config/TLS/registrations/history. Manager442/1skip, Client84/1skip, negative controls and four Chrome harness PASS; physical 85 samples/11+11 reads found 0 PS/CMD child/visible shell. Backups `release-home-133-20261124-233316` pin `6bb4e0dd…603b1` and fail-closed rollback checkpoint `...233009` pin `0f8c9d9a…6af13`. KAT CPU real Start/Restart 8192→16384/generate/Stop and CUDA NOT RUN by owner gate. №18 has permanent deployment/rollback procedure. LOCAL-PLAN-01 23:42:50+05 unchanged. БЛОК 4 не изменён.

Прежний БЛОК 1.1 `CODEX-UL-CHAT-LIVE-STATUS-20261124-001` дословно сохранён ниже и в immutable owner #135 `2bdb7f249bf593b14a46f1d2793fb97e9a2aa6cd`, `Documents/07_Задачи Codex.md`, строки 538–567 до этой ротации.

### АРХИВ ПРЕДЫДУЩЕГО БЛОКА 1.1 — ДОСЛОВНЫЙ ОРИГИНАЛ

# CODEX-UL-CHAT-LIVE-STATUS-20261124-001

**TASK ID:** `CODEX-UL-CHAT-LIVE-STATUS-20261124-001`
**Дата:** 24.11.2026
**Исполнитель:** Codex. **Статус:** ASSIGNED / AWAITING OWNER START.
**Цель:** добавить компактный живой индикатор состояния выбранного экземпляра LLM справа от заголовка «События чата», в отмеченной владельцем области, вне прокрутки. Ориентир — зелёный «Запущен» в обзоре Manager; остальной интерфейс сохранить.

**Baseline:** #117 `07029bd3e4fa3498f124d64ba3ceb7e07afb8abd` (Restart Manager77 + Client deployed, LIVE API PASS), main #116 `5e2fe7610f122dfc86822bcf2f4d58a792acf713` при постановке. Owner принимает #118 и синхронизирует рабочий клон до старта; Codex проверяет фактический workspace/HEAD/dirty без Git write. OWNER 24.11: Qwen CUDA в slot1 реально перезапущена из чата на ctx16384, после Restart ответила; read-only Server77 подтвердил новый runner PID25964 и gateway PID7508 (12:08:52/53+05), соседний KAT CPU slot3 PID27164/21548 не затронут. Функциональная OWNER UX приёмка Restart PASS в этом объёме; недостаток — состояние перезапуска плохо видно в чате.

**LOCAL-PLAN-01:** координатор прочитал локальный №34.1 и архив №34.1.1 2026-11-24T12:15:34+05:00. PLAN_SHA256 `8f2a756a79ccbf200228c9df0ac4e466547ff28a4f83dc62a5e187536a26514f`; archive `1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102`. Задача не меняет совместный план/Bridge. OWNER: Desktop Commander пока не использовать; работа Codex локальная в утверждённом workspace.

**Read matrix:** AGENTS.md, №000 §4–5, №07 правила и текущая TASK, №13 NOW/OPEN, №05/09/18 по Restart #113–117 (точные ID `CHATGPT-UL-CHAT-RESTART-20261124-001`, `LIVE-UL-CHAT-RESTART-ROLLOUT-20261124-001`). Client_Ultra_LLM/web_assets/index.html (chat-events-panel, заголовок, restart), client.js (chatSnapshot, refresh, restartSelection/restartSelectedChat, RESTART_STAGE, renderChatControls, syncChatBindings, telemetry), client.css (events panel/status). Client web_client.py/chat_client.py и Manager live/control/restart runtime только для проверки существующего контракта; не читать весь архив.

**Требования:**
1. Компактная цветная текстовая индикация: зелёный «Запущен» только для подтверждённого READY соответствующего экземпляра; жёлтые «Останавливается», «Запускается» (допустима ненавязчивая анимация), серый «Остановлен» только при подтверждённой остановке; красный «Ошибка», оранжевый «Ожидает подтверждения», «Нет связи»/«Состояние неизвестно» при соответствующем состоянии. Для непривязанного чата — нейтральное «Не назначена» либо пусто. Не показывать зелёный по устаревшим данным. Видимость заголовка вне scroll, narrow/popout, aria-live polite без повторного озвучивания неизменного статуса.
2. Restart: отображать фактические стадии STOPPING, WAITING_RELEASE, CHECKING, STARTING, READY, ERROR осмысленными надписями; при ожидании запроса/подтверждения — честный pending, не имитировать пройденные стадии. Отмена первого/ресурсного подтверждения возвращает реальное состояние без лишнего действия. Не менять risk gates/ownership/authorization. После подтверждённого READY, successful rebind к new_instance_id и refresh — зелёное «Перезапуск завершён» ровно 3 секунды, затем «Запущен» только если фактически READY. Timer по chat+manager+slot+operation, без сброса при каждом render, без утечки при смене чата. Ошибка/offline/stop/смена target приоритетнее success. Не скрывать неизвестный результат и не повторять Restart автоматически.
3. Автоматическое обновление из существующих Manager snapshot/control/restart API и текущих refresh/sync, в том числе при Start/Stop из обзора серверов/другого окна. Учитывать точную identity manager_id+slot_id+instance_id, request_id; не угадывать по имени модели. Для внешней замены экземпляра показать необходимость перепривязки без скрытого назначения. Разумная bounded cadence (ориентир <=2 с при переходах и открытом чате, обосновать нагрузку; не плодить тяжёлые pollers). Stale/out-of-order/error/offline — не зелёный. При F5 и старом Manager без нового Restart API — честный fallback, никакого скрытого действия. Сохранить независимые чаты/историю/эксклюзивную привязку, контекст, поток/отмену. Новый журнал событий НЕ делать.
4. Не менять layout за рамками заголовка, контекстные пресеты, настройки моделей, RAM/VRAM gates, Manager lifecycle, Bridge v1. HOME Manager, Server77, работающие KAT/Qwen, Ollama, Valheim, WUA STANDARD не трогать. HOME CUDA и третий рабочий Manager — отдельные следующие TASK после этой.

**Write/test scope:** локальный `M:\GitHub\local_LLM` (проверить реальный workspace), Client_Ultra_LLM/web_assets/index.html, client.js, client.css и относящиеся Client tests; только при доказанной необходимости минимальный read-only Client adapter в web_client.py/chat_client.py + tests, без Manager lifecycle changes. Evidence `Test/CODEX-UL-CHAT-LIVE-STATUS-20261124-001/`; документы существующие №05/07/09/13/18. Не создавать новые Obsidian документы. Codex no Git write (add/commit/push), no LIVE/deploy, no remote/external writes. Локальные synthetic/mock/изолированные test app/профиль/порты, не перезапускать действующий Client. OWNER LIVE/GUI deployment отдельный GO.

**Приёмка/tests:** реальный DOM заголовка справа/scroll/narrow, не только grep. Existing Chrome harness test_browser_control_stream.mjs, test_browser_independent_chats.mjs, test_browser_slots_source.mjs, test_browser_stream_source.mjs + focused scenario. Матрица READY/STOPPED/STARTING/STOPPING/ERROR/unknown/offline, точное соответствие разных Manager/slot/instance и одинаковых имён, внешний Start/Stop, реальные mock stages Restart, 3 секунды success до/после, отмена обоих confirm, потеря связи/ошибка/тайм-аут, смена чата/повтор/F5/старый backend, stale/out-of-order, busy stream/no duplicate, 2 независимых чата и история. Проверить отсутствие лишних мутаций, измерить cadence. JS syntax, относящиеся Python tests, полный существующий Client/Chrome regression; NOT RUN/BLOCKED честно при невозможности. TEST-FULL-CYCLE-01. Hosted CI после owner publication; mock != LIVE/independent/OWNER UX.

**Отчёт:** DONE / CHANGED / DIFF / TESTS (команды, counts, FAIL/SKIP, evidence) / PROBLEMS / QUESTIONS / DOC IMPACT / NEXT. Записать checkpoints №05/09/13/18, сохранить исходные FAIL, task-local logs. При сдаче штатная ротация полного оригинала с AMENDMENT в 1.1 только после проверки неизменяемого адреса прежней 1.1; освободить 1. БЛОК 4 — только координатор. Публикация владельцем. Следующий этап — independent review/CI и отдельный OWNER rollout/UX.

## AMENDMENT 24.11.2026 — авторская сдача

**AUTHOR TESTED / REVIEW PENDING.** Полный отчёт: `Documents/Reports/CODEX-UL-CHAT-LIVE-STATUS-20261124-001/Final/report.md`. Прежний БЛОК 1.1 дословно сохранён в immutable owner #118 `39943ba4a5dda26f2f5a6575abdf2aac10c38858`, `Documents/07_Задачи Codex.md`, строки 78–99; сравнение текущего текста прежнего БЛОКА 1.1 с #118 до ротации — exact PASS. БЛОК 4 не изменён.

### БЛОК 2 — ПОСЛЕДНИЕ ПЯТЬ ЗАДАЧ (КОРОТКИЙ ИНДЕКС)

- **FIX-UL-HOME-RELEASE-DRIFT-20261124-001 / 24.11:** HOME Manager №127 installed 23/23, restart schema/API/history/registrations/native telemetry PASS; Manager442, Client84, Chrome4 PASS. OWNER real KAT lifecycle/context/UX and CUDA NOT RUN. Оригинал в БЛОКЕ 1.1, report/evidence `Documents/Reports/FIX-UL-HOME-RELEASE-DRIFT-20261124-001/`.

- **CODEX-UL-CHAT-LIVE-STATUS-20261124-001 / 24.11:** AUTHOR TESTED / REVIEW PENDING; Client Python 84 (1 SKIP), Chrome control/stream/independent/slots PASS. Exact identity/stale/offline/Restart success 3 s; LIVE badge/CI/OWNER UX NOT RUN. Оригинал в БЛОКЕ 1.1, отчёт в `Documents/Reports/CODEX-UL-CHAT-LIVE-STATUS-20261124-001/Final/report.md`.

- **CODEX-UL-COLIBRI-CUDA-LIVE-20261120-001 / 21.11:** ITERATION CLOSED PARTIAL; real standalone GPU KAT/Qwen PASS, CONFIG LIVE PASS, owner observed responses PASS, cold latency/VRAM forecast/independent review OPEN; original BLOCK 1.1; №05/09/13/18.

- **CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001 / 20.11:** P1-P5 LOCAL QA PASS, Client 58/58, Chrome 4/4, local asset readback PASS; OWNER UX / final owner publication / CI OPEN. Original in immutable commit 86f0656ad2d58cb5c864587b166fc6a92999a6c9 / Documents/07 (then BLOCK 1.1).


- **CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001 / 20.11:** AUTHOR LOCAL QA PASS, три regression-цикла Manager 354/Client 58/Chrome, LIVE/CI/OWNER UX OPEN; дословная TASK в БЛОКЕ 1.1, evidence в task-local Test, детали №05/№13. Original in immutable commit 85 / Documents/07 (prior BLOCK 1.1).

**Дополнительные OPEN вне завершённой пятёрки:** `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` — A/B SUBMITTED, Stage B Gate2, C/D NOT RUN/OWNER GO absent; полная задача и AMENDMENT immutable №54. F3 backup provenance pin; F4 Chrome first-run; versioned R5 release/re-stage после source fixes. Все ранние задачи остаются в №09/immutable Git.

### БЛОК 3 — OPEN / NEXT

**26.11.2026 — DOC-UL-CONTINUITY-20261126-001:** WEB35 integration preparation per OWNER; no new assignment. #147 visible brand accepted visually by OWNER (running build not independently verified), Windows CI45689521300 FAILURE: Client unit PASS, Manager unit/Chrome legacy/streaming FAIL; root cause UNKNOWN. Separate triage task only after OWNER and fresh LOCAL-PLAN-01. Bridge readiness matrix in №13 §5, M1-10 HOLD at last plan. No runtime/Manager/model changes; BLOCK1/1.1 unchanged. WireGuard and CPU/multi-GPU work deferred.

**ISSUE-UL-CLIENT-CLOSE-RELEASE-20261125-001 — OWNER CLARIFIED / OPEN / OBSERVE ONLY.** 25.11.2026: предыдущая трактовка требования закрытия Client отменена владельцем. Закрытие браузера/Client НЕ останавливает работающие LLM: независимые Manager/instances продолжают работу, другие авторизованные клиенты могут подключаться. Проблема: после явного Stop всех экземпляров интерфейс показывает «Остановлен», счётчик работающих экземпляров 0, но по наблюдению владельца остаются процессы или занятая VRAM. Скриншот WORK (Colibri Work PC, три слота «Остановлен», 0 работающих экземпляров) подтверждает только UI, не остаточные процессы или фактическую VRAM. При повторении сопоставить штатный Stop, точные instance/session/PID, released, Supervisor/runner и дочерние процессы, порты и VRAM конкретного GPU/процесса до/после; отличать нормальное использование GPU другими приложениями и задержку освобождения от настоящего остаточного процесса. Причина ещё UNKNOWN; никаких heartbeat/lease/auto-stop по закрытию Client. Пока наблюдение, короткие скрытые проверки только при воспроизведении, без долгого фонового мониторинга, без новых активных задач, кода или LIVE изменений. История исходной трактовки сохранена в Git #145, но не действует. LOCAL-PLAN-01 недоступен (HOME offline при предыдущей попытке), новая задача не активируется; только уточнение записи.


**DEFERRED / DESIGN — multi-GPU instance placement:** Multi-GPU owner direction, 25.11.2026 (future design, not assigned or validated): WORK RTX4070 Ti SUPER 16 GiB potentially hosts two independent CUDA LLMs; owner considers additional GPU, likely WORK, possibly HOME. Target 3–4 concurrent CUDA instances on expanded WORK if memory, compute, PCIe, PSU and cooling permit, plus distributed CPU/GPU collaboration. Current HOME8 + Server77 8 + WORK16 = 32 GiB across independent devices; example additional 8 GiB gives 40 GiB distributed, not pooled, not confirmed hardware choice. Manager discovers all devices with stable identity, per-GPU VRAM/usage/availability, explicit instance→device selection and launch mapping (verify actual engine/device binding, no assumption of support beyond current --gpu 0); independent budgets, resource collision warnings, optional auto-placement only within permissions/constraints. Same capability schema and UI across hosts; unavailable hardware is explicit, no host-specific build. Multi-GPU and concurrency tests separately after CPU threads/UI task and owner authorization. No new GPU installed/tested, no claim two/four simultaneous instances proven, no WUA integration stage change.


**NEXT / DRAFT — Events panel UX:** OWNER requests token metrics in «События чата» (existing current/average visible in screenshot; audit missing fields, distinguish first fragment/decode/overall, reasoning/output if supported); resizable panel; detachable movable panels including events, remember size/location/docked state per Client, restore on reopen/monitor changes. Verify current feature before adding, no duplicate metrics, preserve chat history and state, no implementation/assignment yet. CPU thread actual measurement remains part of CODEX-UL-CPU-THREADS-20261125-001.



#### NEXT / DRAFT — CPU threads: native discovery, sync and measurements

OWNER benchmark checkpoint: №18 HOME/Server77 compact tables. Verify Colibri actual worker team and engine-specific overrides, phase-specific CPU utilization during inference; test matched thread counts, VRAM budgets and Chain settings separately. Multi-instance goal per №13/18; not part of immediate implementation acceptance.

**TASK ID:** `CODEX-UL-CPU-THREADS-20261125-001` — DRAFT / AWAITING OWNER START; P1 (next performance/UI task). Base #139 doc-only, source #127. Full source work only after OWNER activation in BLOCK 1; use existing test harnesses, no new permanent files without OWNER. Scope: hardware CPU topology/capacity + threads selection/save/sync + native measurement + bounded test design. Do not perform LIVE update/real launch, touch active Qwen, Server77, WORK, WUA, weights, network or change legacy profile defaults; owner real benchmarks separately.

1. **Inventory & discovery.** Verify installed Colibri launch/env paths and engine capabilities; distinguish physical cores, logical CPUs, usable process CPU sets/affinity/job restrictions and groups, topology/P/E hints when reliably available. In-process native Windows APIs, cached static data, no recurrent PS/CMD (NATIVE-TELEMETRY-01). Manager returns host hardware and permitted launch range from verified effective constraints; unknown explicit, never hard-code 12/28/1024 as host capacity. Separate hardware maximum from engine-supported maximum and remaining shared resources; no fake affinity or exclusivity.
2. **Contract & UI.** Common schema Auto (engine selects; omit override and report unknown effective until verified), Manual 1..verified supported/available logical count, Max (resolve to verified maximum at launch, not automatic optimum). Same feature on all machines and both CPU/hybrid CUDA, availability reason where engine cannot support. Per Manager/model/mode/slot launch setting with revision and role/slot permission checks; preserve existing review settings/default/inheritance (2 or unset) unless user explicitly changes. Server authoritative, immediate saved readback and other Client sync via existing refresh/event mechanism, stale revisions rejected, no Client-only duplicate. Desired, applied-at-launch, effective/observed distinct. Live edits save pending, require explicit model Restart; no silent restart. Preserve history, Restart/context/CUDA profiles and auth/ACK.
3. **Runtime verification.** Map explicit resolved value to supported engine launch settings (current four env vars); verify child env/engine contract and startup logs when available. Do not claim all OS threads are compute threads. Add bounded native per-process/job CPU-time delta, observed active-thread CPU-time where safe/supported and actual core-equivalent utilization, separate total thread count; engine-reported team size only if trustworthy. Unknown not zero. No sampling loops that spawn visible shell or leak process data; per-instance identity and stale sample indicators. Tests for native topology, group/affinity edge cases, permission/unknown states, changes during restart and concurrent models; advisory oversubscription, no hard global reservations without design.
4. **Source QA.** Existing full Manager/Client/Chrome/negative suite, tests for 6/12, 20/28, >64 processor groups, restricted/unknown hosts; manual validation, Auto/unset, Max resolution, exact launch env, legacy migration/no changes, two clients concurrent revisions, two managers distinct topology, CPU & CUDA, desired vs actual, restart and cleanup, no recurring windows. Test no accepted function regression and update feature documentation/REFERENCE-RELEASE-01/CONFIG-UI-PARITY-01. Exact Windows CI and separate owner release GO required. No new standalone checker files yet (FEATURE-REGISTRY-01 remains separate).
5. **Owner benchmark after accepted full release.** One model at a time, identical fresh chat/prompt, context (8192 first), thinking, engine and model, CUDA budget5/chain on/rows1024 only when safe and same across CUDA trials. Compare 2, physical core count, logical maximum, Auto, then intermediate if needed. At least three repeat runs per condition when feasible, distinguish cold start/warm prompt, TTFT and decode tok/s, prompt tokens/output, RAM/VRAM peaks, CPU time and CPU-equivalent utilization, disk bytes/read-write paths and pagefile only if relevant. Report median/range and unknowns, stop/release after every trial. No assumption SSD throughput implies faster decode, no promise 6x improvement. User performs actual live tests after separate GO. Pass only with measured, repeatable evidence, not just UI or process thread count.

**Expected submission:** schema/UI and supported launch values/actual-vs-desired, tests and exact evidence, known limitations, no live changes; full task original archived per №07 when executed. Read-only inventory: HOME i5-12400F 6 physical/12 logical, all four CPU/CUDA review launch.threads=2 (earlier direct readback); WORK DESKTOP-43PAEBO i7-14700KF 20 physical/28 logical, both CPU reviews threads absent/null (engine default, effective unknown), both CUDA threads=2 (fresh Win32_Processor/config readback). Server77 unavailable in DC device list, i9 identity and current thread count UNKNOWN. #127 runner sets OMP_NUM_THREADS/OMP_THREAD_LIMIT/OPENBLAS_NUM_THREADS/MKL_NUM_THREADS for explicit threads and removes them for omitted launch.threads; Colibri c/coli explicitly respects OMP_NUM_THREADS via setdefault on reviewed paths. Actual engine compute team, effective CPU affinity and optimal throughput not measured. Native thread count alone does not equal active compute threads. LOCAL-PLAN-01 25.11.2026 00:36:11+05 helper read PASS SHA256 b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee, archive read PASS SHA256 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102; COLIBRI MVP1 SUBMITTED, WUA IN_PROGRESS, M1-10 HOLD, no plan write. Local checkout main clean, local and GitHub №07 BLOCK1 free. HOME latest Qwen CUDA READY/unreleased, engine 18001 PID14884, no pending restart; KAT all released. Do not stop/restart it. No config/runtime/source change.



- **NOW 24.11 — FIX-UL-HOME-RELEASE-DRIFT-20261124-001:** technical rollout PASS, owner model acceptance OPEN. OWNER вручную выполняет KAT CPU Start8192→answer→Restart16384/new instance/effective context/status/brain/history→second answer→exact Stop/cleanup по процедуре report. До CPU PASS CUDA не запускать; KAT/Qwen CUDA сейчас `runtime_review_required`, отдельный OWNER decision/GO. БЛОК 1 свободен, NEXT не является новой назначенной TASK.
- **NOW 24.11 — CODEX-UL-CHAT-LIVE-STATUS-20261124-001:** AUTHOR TESTED / REVIEW PENDING, индикатор состояния в «События чата» source/Chrome PASS; GitHub CI и LIVE badge/OWNER GUI NOT RUN. Следующее: owner publication → independent review/CI → отдельный OWNER GO на Client rollout.
- **SUSPENDED / PARTIAL, не закрыта:** `CODEX-UL-MANAGER-UI-PROFILES-20261121-001` по явной смене приоритета владельцем освобождена из БЛОКА 1. Полный дословный оригинал со всеми AMENDMENT и checkpoint сохранён [immutable #117, №07 БЛОК 1](https://github.com/maxrus82gm-svg/local_LLM/blob/07029bd3e4fa3498f124d64ba3ceb7e07afb8abd/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md#L51-L114); №05/09 сохраняют TASK ID, незавершённые native Manager UI, HOME CUDA/profile review, global multi-client assignment, средние/пики telemetry и прочие OPEN. Не объявлять DONE и не возобновлять без назначения. Старый БЛОК 1.1 оставлен неизменным.
- **Порядок владельца:** индикатор → HOME Manager update / CPU+CUDA review → третий Manager рабочий ПК → full multi-host Start/Stop/Restart → совместный WUA LIVE после отдельного GO. Скорость Qwen отдельно.



- **Deferred:** CODEX-UL-LLAMACPP-INTEGRATION-20261121-001; P1 OPEN, не текущий БЛОК 1.


- **NOW 20.11 / CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001:** local P5 full QA PASS; owner F5 visual acceptance, publish remaining corrections, exact-SHA CI; release/cleanup pending.


- **NOW 20.11 / CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001:** source/Chrome локально проверены; installed Manager `owner_go=false`, `home-rex.control_models=false`, reviews отсутствуют. Owner публикация и новый hosted Windows CI, затем отдельный OWNER GO на full Manager package/cutover, private control config и bounded реальный CPU/CUDA/две LLM, защита Qwen/Valheim. До этого LIVE NOT RUN, RELEASE HOLD. Процедура №13.

- **NOW 18.11 / DOC-UL-R5-CHROME-INDEPENDENT-20261118-001:** Chrome F4/P1 test-harness scoped accepted on owner №64, independent [CI attempt2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/44321179202/attempts/2) PASS (Manager350/1 SKIP, Client49, Chrome legacy/P0/P1 and negatives). Historic upstream `data:null` root UNKNOWN; real ZIP/backup/server C/D still OPEN, RELEASE HOLD. NEXT separate Manager R5 restage + GO → multiple real LLM → Web Alarm bridge; Electron later.

- **F1a/F1b/F1c/F2 source закрыты:** №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, независимый Windows [run 43599309587 attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) — Manager `337 total (336 PASS/1 SKIP)`, Client49 PASS, five negative controls/Chrome legacy/P0/P1 PASS, 4 старые RED сохранены и теперь PASS.
- **RELEASE HOLD / NEXT по отдельному OWNER GO:** старый original ZIP и серверное staging 21/21 содержат прежний validator; требуется версия нового release + проверка SHA и безопасное staging (не в этой TASK), независимый physical host preflight, F3 trusted private backup provenance pin, оценка F4 Chrome first-run. C/D `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` не разрешены, Qwen/Valheim не трогать.
- **История/согласование:** №05/07.00/09/13/18 и №00 обновлены одним doc-only №57 в `GPT_2_local`, `main` меняет только владелец. §5.3 publication guard / test protocol продолжают действовать, новых UI изменений нет, OWNER UX NOT REQUIRED.

### БЛОК 4 — НЕЗАВИСИМАЯ ПРОВЕРКА (ТОЛЬКО КООРДИНАТОР)

**25.11.2026 — FIX-UL-HOME-RELEASE-DRIFT-20261124-001 / independent installed readback + OWNER CPU UX acceptance.** OWNER сообщает, что самостоятельно проверил HOME CPU в нескольких сценариях: Restart/изменение контекста, молния, индикатор мозга и освобождение памяти работают правильно. OWNER CPU/UX PASS (устный отчёт); точные instance IDs, токены, размеры памяти, трасса I/O и полный повтор lifecycle координатором NOT RUN. Независимая проверка до OWNER trial: Manager PID22224/18443; 21 payload exact #127, отдельный Manage-ManagerTask.ps1 совпадает после CRLF normalization; Client PID35376/50158, 17 source files LF-normalized exact #127 (не raw byte exact), SQLite quick_check ok, 5 STOPPED/0 unreleased, restart_jobs exists/0 rows, 8016/18001/18002 listeners absent, backup MANIFEST SHA256 exact 6bb4e0dd70f9eab2c884b0a8a8b689a0c6ef4646d1293db61230a6c4cd4603b1. Авторские 442/84 tests totals incl. 1 skip each, four Chrome PASS; full independent rerun NOT RUN. Main #136 published author report; #127→#136 docs-only. HOME release drift fixed / OWNER CPU accepted, CUDA remains separate runtime_review_required / NOT RUN. No new launch/stop or config change by coordinator. LOCAL-PLAN-01 25.11.2026 00:07:08+05: helper read PASS, SHA256 e104b9d12d5775374e556d38ad9addb8335ab080b92660a60cde83b206a6f30f; archive read PASS SHA256 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102. COLIBRI MVP1 SUBMITTED / WUA IN_PROGRESS; M1-10 HOLD; no plan write. Canonical procedure №18 DEPLOYMENT-01. CUDA / full independent lifecycle / exact client raw manifest / disk I/O NOT RUN; no new assignment, no rotation, no source changes.


**24.11.2026 — DOC-UL-COORDINATOR-RESUME-20261124-001:** owner #119 `1b4e31b32687ffd06ed2228aa229df18d2179bd6` report/diff + exact hosted CI verified, OWNER GUI PASS reported by owner. Manager 436 PASS+1 SKIP, Client 83 PASS+1 SKIP, Chrome control/legacy/P0/independent PASS; P1 DOM deadline second chat FAIL, cause unknown. **INDEPENDENT PARTIAL / CI FAIL**, no LIVE repeat. Coordinator resumes implementation; Codex paused, BLOCK1 free, BLOCK1.1 unchanged. Next FIX-UL-CHAT-STATUS-P1-20261124-001; preserve original report. №05/06/09/13/18.


**20.11.2026 - CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001:** coordinator reviewed owner commit 85 and resumed P5; corrected model-label collisions and pending Manager submit/draft guards; 58 Python tests, 6 JS syntax checks and 4 Chrome regressions PASS. Local running Client HTML/CSS/JS byte match. Own corrections self-tested, not independent acceptance; user UX and final hosted CI NOT RUN. No production/Manager changes. Verdict: LOCAL SOURCE QA PASS / REVIEW PENDING / OWNER UX PENDING.


**19.11.2026 — DOC-UL-R5-INDEPENDENT-LIVE-PARTIAL-CLOSEOUT-20261119-001 — independent R5 final acceptance.**

**Проверка координатора 19.11.2026, 08:31 +05:** самостоятельно прочитана реальная Windows Scheduled Task `UltraLLM_Manager_LIVE` на `DESKTOP-KT4G5SM`: Running, Manager R5 PID `342152`, listener `192.168.0.77:8443` принадлежит ему, запущен из `C:\Server\Ultra_LLM\Manager_Live`; SHA256 установленного `live_manager.py` = `7dee682ad4fa5cf692a637d3b3a334b74a67dd5707273f9183a095a58e5a406e`. Удержанный прежний Manager SHA256 `e15ef6ccea34fc4a6d7ba2afc2a4a37d6739d9b48884dcd99d0a9baa4584da51`. Qwen gateway/engine PIDs `138268/139516`, Valheim PID `248800`, UDP `2456/2457` сохранялись. Только READ-ONLY, никаких серверных изменений координатором.
**Client independently:** PID `35708`, listener `127.0.0.1:61761`, `/api/status`: manager `online`, `LIVE_HOST`, schema `ultra.manager.live.v1`, streaming/reasoning_events=true, 3 slots.
**Собственные offline QA:** authorization `40/40 PASS` в PS 7.6.9, Stop/WaitFree `31/31 PASS` в PS 7.6.9 и `31/31 PASS` в Windows PS 5.1; **102/102 PASS**. Это не hosted CI и не повторный LIVE cutover.
**S6 по авторскому evidence:** реальная Qwen через Chrome→изолированный Web Client→Manager R5→Colibri: 15 completion tokens / 15 fragments, Chrome TTFT `9057.1 ms`, Colibri first fragment `8601.04 ms`, cancel/reasoning/history-reload PASS. Сам координатор реальную генерацию повторно НЕ запускал. `control_models=false`: новые CPU/CUDA instances, две независимые LLM, parallel chats и stop-one **NOT RUN**. 
**Технический caveat:** первый launcher после удачного switch дал `FAIL:wire_invariants` из-за HTTP 403 `source_not_permitted` вместо ожидавшегося 401. Подтверждённый LIVE read-back показал работающий R5, rollback не выполнялся. Postflight фиксы HTTP/часов recovery прошли 12/12 offline только по авторскому QA, LIVE повторно не проверялись. 
**Документы:** опубликованный owner №77 `cc961accd2907439d015c24af1f9831045cd3cec` менял №07/№13/README. Полный оригинал TASK с amendment №76 дословно перенесён в БЛОК1.1; БЛОК1 свободен. Авторский локальный `Test/CODEX-UL-R5-RELEASE-ROLLOUT-20261118-001/s5-autonomous-review/` проигнорирован Git, координатор прочитал его напрямую; доказательства НЕ опубликованы в Git. Исходный ZIP SHA256 `9759b25689776f3e05698c4e821de71d130712ab17fe2ea2c1610bb854690b17`.
**VERDICT:** `S5 LIVE PASS (INDEPENDENT HOST CHECK) / S6 PARTIAL (real Qwen evidence; multi-model NOT RUN) / S7 ARCHIVE ACCEPTED / TASK CLOSED AS PARTIAL`. HOLD для самого Manager R5 снят, модельные control-разрешения не включались и не подразумеваются.

---


**18.11.2026 — DOC-UL-R5-CHROME-INDEPENDENT-20261118-001: independent review `CODEX-UL-R5-CHROME-STABILITY-20261117-001`.** Owner №63 `7a3f7355` introduced synthetic FIFO fault misdelivery, P1 [run 44309630442 FAIL](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/44309630442); owner №64 `1fa6ea9bbfcc` repairs only offline fixture/P1 and append-only README with addressed probe/409 replay. Coordinator reviewed exact diff and personally reran [CI attempt2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/44321179202/attempts/2) on same SHA: first/second CI PASS, Manager 351=350 PASS/1 SKIP, Client 49 PASS, Chrome legacy/P0/P1/5 negatives PASS. **OFFLINE SOURCE ACCEPTED / INDEPENDENT WINDOWS CI PASS / REAL NOT RUN / RELEASE HOLD**. Original P1 upstream transient reason UNKNOWN; original F4 delay unproven; no product/GUI changes, OWNER UX NOT REQUIRED. No live Manager/Client or SAFE-CUTOVER GO. БЛОК1 свободен, 1.1 original preserved.


**15.11.2026 — F3 independent source+CI review:** опубликован владельцем `main` №59 `e8f001cb` с четырьмя файлами (`backup_provenance.py`, +14 F3 methods в `test_gate2_hardening.py`, README append-only, локальная ротация №07). Полный оригинал F3+OWNER AMENDMENT сохранён 1.1, БЛОК1 свободен. Verifier принимает explicit trusted SHA raw manifest, проверяет файлы/size/hash, tree inventory, task XML, links/reparse/junctions/hardlinks и observed races. Joint substitution backup+manifest: legacy PASS, new `trusted_manifest_mismatch`. ChatGPT самостоятельно вызвал Windows CI rerun job `132561640722` → `132562679546`, [attempt2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43632378345/attempts/2) `completed/success`: Manager351=350 PASS/1 SKIP, Client49 PASS, Chrome/controls PASS. Локальные Test evidence напрямую не читались (Desktop Commander offline), собственных новых методов reviewer не добавлял. **TECHNICAL OFFLINE SOURCE PASS / CI WINDOWS PASS / REAL BACKUP NOT RUN / INITIAL AUTHENTICITY NOT PROVEN / USER UX NOT REQUIRED / RELEASE HOLD**. F4, ZIP/re-stage, физический server/SAFE-CUTOVER C/D OPEN.


**14.11.2026 — независимая приёмка `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` (№56):** лично проверены Git diff №55→№56 и точный whitelist 5/5 файлов (никакого `.obsidian/**`), source `stage_b_complete_readonly.py` и `manager_release.py` по F1a/F1b/F1c/F2, тесты, README append-only. Все четыре оригинальные regression test methods **дословно равны №54**, без `skip`/`expectedFailure`; новые positive/negative и Python `-O` checks присутствуют. Авторский hosted [CI run 43599309587 attempt 1](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587) PASS. **Координатор лично инициировал повтор GitHub Actions job `132460435835` → новый job `132547140934`, [attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) на том же SHA `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5` — `completed/success`, `Ran 337 tests OK (skipped=1)`, Client `Ran 49 tests`, negative controls, Chrome legacy/P0/P1 PASS, failure/error 0.** Отдельного собственного нового test-файла не добавлялось; независимый повторяет уже опубликованные suites на новом hosted runner. Вердикт: `AUTHOR QA READY / INDEPENDENT TECHNICAL PASS (SOURCE SCOPE) / CI WINDOWS PASS (ATTEMPT 2) / REAL APPLICATION NOT RUN / USER UX NOT REQUIRED / SOURCE TASK CLOSED / RELEASE HOLD`. **Релизный ZIP оригинал проверен автором локально, hosted exact ZIP NOT RUN; сервер/стадии C/D запрещены и не проверялись.** F3/F4 и rebuild/re-stage отдельно OPEN.

**14.11.2026 — `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001`: независимая инженерная приёмка PARTIAL.** Прочитаны код и настоящий GitHub-hosted Windows CI `43581579523` на №54 `f324513cac5a270ac620acdf2466c0f27efb6593`: 330 Manager (325 PASS, 4 FAIL, 1 SKIP), 49 Client PASS, Chrome legacy/P0/P1 и 5 negative controls PASS. Подтверждены F1a listener PID mismatch, F1b truthy `'false'`, F1c чужая 403 reason, F2 `__import__('qa_unavailable_dependency')` в корректном synthetic manifest. Это **INDEPENDENT CODE + CI LOG REVIEW CONFIRMED / CI WINDOWS FAIL / TECHNICAL PARTIAL / OWN FRESH TEST RUN NOT RUN / LIVE NOT RUN / RELEASE HOLD**. Авторский exact ZIP SHA+21 PASS, hosted exact ZIP NOT RUN. `main` №54 уже содержит единственную test-публикацию, но среди шести файлов был вне scope `Documents/.obsidian/workspace.json` (ранее изменён, входил также в №48–51); точный инициатор staging неизвестен. Ротация в БЛОК 1.1 не равна PRODUCT PASS. Новая `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` ожидает старта владельцем.

**14.11.2026 — CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001, checkpoint B:** независимый code/evidence review авторских pre/post 24/24, SHA, TLS/ACL/backup/staging, защищённых Manager/Qwen/Valheim: `EVIDENCE REVIEW PASS / OWN PHYSICAL SERVER RERUN NOT RUN`. Самостоятельно изучен Windows Actions run `43572399891` (№52: 311 Manager, 1 SKIP; 49 Client; Chrome SOURCE P0/P1 PASS). Это **CI WINDOWS SOURCE PASS**, не LIVE cutover/rollback/real Qwen; этап C/D не разрешён. Ротация в БЛОК 1.1 не закрывает SAFE-CUTOVER. Новая `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` пока **AWAITING OWNER START**, её тесты ещё NOT RUN.

**13.11.2026 — CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001: INDEPENDENT CODE/EVIDENCE REVIEW PASS / OWN WINDOWS+ZIP RERUN NOT RUN / LIVE DEPLOY NOT RUN.** Координатор независимо прочитал `main` `b484bd67f4ff6506390860efd87731cced328cad`, `Manager_Ultra_LLM/manager_release.py` (21 член/allowlist/sha/depcheck, отказ от path traversal, symlink, injected/private files, staging только в новый каталог), `test_manager_release.py`, `Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/{qa.json,qa_regression.json,acceptance.json,rollback_qa.json,release_manifest.json}`, README и рабочую Git-историю. По авторским evidence: Manager 310 PASS+1 SKIP, Client 49 PASS, Chrome legacy/P0/P1 PASS, rollback 66/2 PASS. Первые QA ошибки synthetic config и отсутствующего VBS в тестовой копии сохранены в `qa.json`, повторные тесты прошли в `qa_regression.json`. **Повторный прогон координатора и байтовая SHA ZIP НЕ ВЫПОЛНЕНЫ**: Desktop Commander после начального чтения локальных отчётов перестал отвечать; новый hosted CI также NOT RUN. Реальный LIVE Manager/API/TLS/LLM/rollback NOT RUN. Verdict касается подготовленного SOURCE кандидата, **не** самостоятельной runtime-проверки и не разрешает серверные изменения. `main` уже содержит код/evidence `b484bd6`; не создавать дублирующий Codex-коммит. Независимый runner и SERVER OWNER GO — отдельные открытые этапы, см. №05/09/13/18 §18.30.



**13.11.2026 — CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001: INDEPENDENT EVIDENCE REVIEW PASS / HOST NOT RE-RUN.** Прочитаны `main` №45 `71462bd` и `Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/` (report, Stage D JSON preflight/transaction/rollback/lifecycle/UI/integrity). Подтверждены согласованные 73/73 SHA в `M:\GitHub\local_LLM\Production\Client`, одно переключение ярлыка, Chrome/Manager ONLINE, 34 сообщения и SHA профиля без изменений, однократный процесс и exit 0; старые пути и backups сохранены, сервер не менялся. Домашний ПК в Desktop Commander OFFLINE: независимый запуск на нём NOT RUN. `AUTHOR LIVE PASS` не является повторной runtime-проверкой ChatGPT. Область приёмки — миграция Client; server streaming/dynamic slots/CPU-CUDA/вторая LLM, второй ПК и privacy cleanup OPEN. Итоговый Codex-коммит №45 уже есть в `main`, координатор оформляет отдельный документный №46 в `GPT_2_local`. См. №05/09/13/18 §18.29.

**CI UPDATE 12.11.2026:** Windows hosted GitHub Actions run 43173172619 SUCCESS; независимые P0+P1 Chrome SOURCE mocks PASS (включая two same-model CPU, two same-model CUDA, STOP one preserves other), Client 49/49 и JS/Python syntax PASS. С учетом ранее независимого Windows Manager 302/302: **P0/P1 SOURCE OFFLINE PASS**, но **PRODUCT LIVE NOT RUN**. Full Manager suite в hosted CI NOT RUN из-за S: fixture. https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43173172619 . Не разрешает самовольную установку или runtime START/STOP.



**12.11.2026, CODEX-UL-STREAM-SLOTS-20261112-001: P0 SOURCE OFFLINE PASS / P1 SOURCE PARTIAL / LIVE NOT RUN.** Прочитаны SOURCE commit 9900ccd, отчёт и evidence. На DESKTOP-SC96D3U независимо из этого HEAD: Manager verify_offline.ps1 **302/302 PASS**; Client unittest **49/49 PASS**; Chrome test_browser_stream_source.mjs **PASS** (SOURCE Client → TLS Manager → fake Colibri, первый фрагмент до DONE, reasoning отдельно, сохранение); node --check client.js **PASS**, общий exit 0. Для P1 Chrome только авторские mock evidence. Реальный GPU/KAT/Colibri/START/STOP и LIVE latency НЕ проверены. Никакого PROD PASS/OWNER GO из этого вердикта не следует.

Исторические старые БЛОКИ 2–4 сохранены дословно в №09, чтобы не терять прежние независимые проверки.







## 4. Отчёт исполнителя — минимальная форма

```text
TASK ID:
RESULT: RESULT READY / PARTIAL / BLOCKED / DRAFT
DONE: что фактически получилось
CHANGED: точные изменённые файлы
DIFF: краткая суть изменений / адрес diff
TESTS: PASS / FAIL / SKIP / NOT RUN + evidence
PROBLEMS: ошибки, ограничения и неподтверждённое
QUESTIONS: блокирующие вопросы, если остались
DOC IMPACT: что требуется обновить в документации
REPORT: постоянный проверяемый путь
NEXT: предложение, не новая назначенная TASK
```

**Правило передачи между чатами:** живое состояние и подтверждённые NEXT сохраняет ChatGPT в `13_Тактический_контекст.md` после каждого результата или значимого решения; переписка и память исполнителя не являются постоянным архивом.
