# Задачи Codex — рабочая карточка исполнителя Ultra LLM

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

Свободен. Готов к получению следующей задачи от владельца.

### БЛОК 1.1 — ПОСЛЕДНЯЯ СДАННАЯ ЗАДАЧА (ДОСЛОВНЫЙ ОРИГИНАЛ)

**SUBMITTED / REVIEW PENDING · LOCAL QA PASS · LIVE NOT RUN.** Дословная TASK перенесена из БЛОКА 1. Локальное evidence: `Test/CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001/WorkEvidence/summary.json`; итоги и OWNER GO — №05/№13.

# CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001

**TASK ID:** `CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001`  
**Дата:** 20.11.2026  
**Проект:** Ultra LLM Client / Manager R5 / Colibri  
**Workspace:** `M:\GitHub\local_LLM`  
**Репозиторий:** `maxrus82gm-svg/local_LLM`  
**Baseline GitHub:** №82 `a89ac1352db07c3b553252867836efca14b4c4ad`. Сверить актуальный локальный HEAD и незакоммиченные изменения.

**Цель:** пользователь из Ultra LLM Client самостоятельно выбирает установленную и разрешённую LLM, назначает её в слот, запускает на CPU или CUDA, общается с ней и останавливает без ручных команд и вмешательства в другие модели.

## 1. Preflight и источники

Перед реализацией изучить релевантные части:

- `AGENTS.md`, `Documents/000_Задачи для агента.md`, `Documents/07_Задачи Codex.md`.
- `Documents/00_Старт.md`, №13 (актуальный контекст), №05 (реестр), №18 (Client/Manager/control).
- `Client_Ultra_LLM/` — интерфейс, настройки чата, выбор модели, API.
- `Manager_Ultra_LLM/control_runtime.py`, `resource_catalog.py`, `slot_registry.py`, `live_manager.py`, `colibri2_runner.py` и связанные тесты.

Выявить, что уже работает, что отключено политикой доступа и чего действительно не хватает.

**Важно:** локально остались изменения интерфейса чатов и документации после №82. Не перезаписывать, не откатывать и не включать чужие изменения в собственную работу. Перед началом изменений сверить их сохранение и согласовать базовый снимок с владельцем.

## 2. Реализовать полный сценарий управления LLM

Пользователь должен иметь возможность выполнить последовательность:

**Manager → каталог моделей → выбор модели → выбор слота → CPU/CUDA → Start → READY → назначение модели чату → переписка → Stop.**

Требования:

1. Показывать актуальный каталог установленных моделей, подтверждённый Manager. Не отображать произвольные файлы как готовые к запуску модели.
2. Показывать три начальных слота и кнопку добавления новых слотов, если Manager это разрешает.
3. Позволить выбрать модель и CPU/CUDA для каждого слота.
4. Отображать состояние модели: не запущена, запускается, готова, занята, останавливается, ошибка.
5. Корректно реализовать Start и Stop через существующий авторизованный API Manager.
6. После запуска модель становится доступной для назначения любому независимому чату.
7. При остановке модели история чатов остаётся доступной.
8. Несколько экземпляров одной модели либо разные модели не должны мешать друг другу.
9. При нехватке предполагаемой RAM/VRAM показывать предупреждения и реальные причины ограничений; не обходить обязательные защитные проверки Manager.
10. При отсутствии прав показывать понятную причину и способ штатного предоставления разрешения владельцем, без скрытого обхода авторизации.

Приоритет — **полностью рабочее управление**, а не косметическое обновление интерфейса.

## 3. Разобраться с разрешениями Manager

Проверить в реальной установленной конфигурации, почему могут быть выключены:

- `control.enabled`;
- `control_models`;
- `can_add_slot`;
- Start CPU / CUDA / Stop.

Отличать отсутствие серверного механизма, отключённую конфигурацию, недостаточные права Client и ресурсные ограничения.

Подготовить точную, минимальную и обратимую процедуру предоставления разрешений конкретному Client.

**Запрещено самостоятельно менять LIVE-разрешения Manager, перезапускать сервер или запускать реальные LLM без отдельного OWNER GO.**

## 4. Проверки

Codex самостоятельно проводит:

- Unit и интеграционные тесты Manager/Client.
- Chrome: выбор модели, добавление слота, Start, Ready, чат, Stop.
- Отрицательные сценарии: недостаточно прав, занятый слот, модель отсутствует, нехватка ресурсов, обрыв Manager, двойной Start, ошибочная остановка.
- Два параллельных экземпляра: STOP одного не влияет на второй.
- Сохранение чатов, привязки моделей и истории после F5 и перезапуска.
- Контроль совместимости с новой прокруткой, закреплённым вводом и статистикой.
- Полный доступный regression suite и GitHub CI после публикации владельцем.

Если выявлена ошибка — исправлять и повторять проверки, а не сдавать после первого PASS.

**LIVE-этап:** после успешной автономной проверки подготовить один конкретный запрос OWNER GO на безопасный тест реальных моделей с backup, rollback и проверкой защиты Qwen и Valheim. Выполнить только после разрешения.

Не считать synthetic PASS доказательством реального управления несколькими LLM.

## 5. Самостоятельность

Codex получает свободу выбирать минимальную архитектурную реализацию в Client/Manager и тестах внутри разрешённого Workspace.

Не создавать новые рабочие ветки, дополнительные Markdown-документы или узлы Obsidian. Не выполнять Git write.

Не изменять чужие незакоммиченные файлы без согласования.

Не менять работающие Manager, Qwen, Colibri, Valheim, системные службы, сертификаты, сетевые разрешения и Production без отдельного OWNER GO.

Сохранять только необходимый task-local QA evidence, не содержащий секретов и пользовательской переписки.

## 6. Документооборот

Обязательно обновлять:

- **№13 — Тактический контекст:** фактический прогресс, тесты, проблемы, следующий шаг.
- **№05 — Реестр задач:** TASK ID, состояние, результаты и OPEN.
- №18 и №06 — только если изменены технические контракты или принято архитектурное решение.
- №07 — сдача и ротация по регламенту.

Без самовольного `report.md` и без лишних связей Obsidian.

Итоговый ответ: `DONE / CHANGED / TESTS / DIFF / PROBLEMS / OWNER GO / NEXT`.

**Критерий завершения:** в тестовой среде весь путь от выбора модели до Stop доказан. Реальная эксплуатационная приёмка проводится отдельно с разрешения владельца. Невыполненные LIVE-проверки обозначаются `NOT RUN`, а не `PASS`.

### БЛОК 2 — ПОСЛЕДНИЕ ПЯТЬ ЗАДАЧ (КОРОТКИЙ ИНДЕКС)

- **CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001 / 20.11:** AUTHOR LOCAL QA PASS, три regression-цикла Manager 354/Client 58/Chrome, LIVE/CI/OWNER UX OPEN; дословная TASK в БЛОКЕ 1.1, evidence в task-local Test, детали №05/№13.

- **CODEX-UL-R5-CHROME-STABILITY-20261117-001 / 18.11:** OWNER №63 CI P1 FAIL → №64 fix → INDEPENDENT OFFLINE SOURCE ACCEPTED / Windows CI PASS twice; REAL RELEASE HOLD; DOC-UL-R5-CHROME-INDEPENDENT-20261118-001. Original in BLOCK1.1.

- **CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001 / 14.11:** OFFLINE source fix **SCOPED CLOSED / INDEPENDENT TECHNICAL+CI PASS**: №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, [independent CI attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) 336 Manager PASS/1 SKIP, Client49 PASS, Chrome/5 controls PASS. REAL/ZIP rebuild NOT RUN; RELEASE HOLD.
- **CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001 / 14.11:** AUTHOR PARTIAL, independent code/CI review, четыре RED/Windows FAIL; оригинал [immutable №56](https://github.com/maxrus82gm-svg/local_LLM/blob/d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → прежняя БЛОК 1.1; №54/README/№09.
- **CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001 / 13.11:** SOURCE candidate/evidence PASS; immutable №52 оригинал; реальный deploy NOT RUN.

**Дополнительные OPEN вне завершённой пятёрки:** `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` — A/B SUBMITTED, Stage B Gate2, C/D NOT RUN/OWNER GO absent; полная задача и AMENDMENT immutable №54. F3 backup provenance pin; F4 Chrome first-run; versioned R5 release/re-stage после source fixes. Все ранние задачи остаются в №09/immutable Git.

### БЛОК 3 — OPEN / NEXT

- **NOW 20.11 / CODEX-UL-R5-MODEL-CONTROL-UI-LIVE-GATE-20261120-001:** source/Chrome локально проверены; installed Manager `owner_go=false`, `home-rex.control_models=false`, reviews отсутствуют. Owner публикация и новый hosted Windows CI, затем отдельный OWNER GO на full Manager package/cutover, private control config и bounded реальный CPU/CUDA/две LLM, защита Qwen/Valheim. До этого LIVE NOT RUN, RELEASE HOLD. Процедура №13.

- **NOW 18.11 / DOC-UL-R5-CHROME-INDEPENDENT-20261118-001:** Chrome F4/P1 test-harness scoped accepted on owner №64, independent [CI attempt2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/44321179202/attempts/2) PASS (Manager350/1 SKIP, Client49, Chrome legacy/P0/P1 and negatives). Historic upstream `data:null` root UNKNOWN; real ZIP/backup/server C/D still OPEN, RELEASE HOLD. NEXT separate Manager R5 restage + GO → multiple real LLM → Web Alarm bridge; Electron later.

- **Свободен БЛОК 1.** `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` технически принята и архивирована в БЛОК 1.1, **не** принята как релиз/серверное развертывание. Новая TASK пока не назначена.
- **F1a/F1b/F1c/F2 source закрыты:** №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, независимый Windows [run 43599309587 attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) — Manager `337 total (336 PASS/1 SKIP)`, Client49 PASS, five negative controls/Chrome legacy/P0/P1 PASS, 4 старые RED сохранены и теперь PASS.
- **RELEASE HOLD / NEXT по отдельному OWNER GO:** старый original ZIP и серверное staging 21/21 содержат прежний validator; требуется версия нового release + проверка SHA и безопасное staging (не в этой TASK), независимый physical host preflight, F3 trusted private backup provenance pin, оценка F4 Chrome first-run. C/D `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` не разрешены, Qwen/Valheim не трогать.
- **История/согласование:** №05/07.00/09/13/18 и №00 обновлены одним doc-only №57 в `GPT_2_local`, `main` меняет только владелец. §5.3 publication guard / test protocol продолжают действовать, новых UI изменений нет, OWNER UX NOT REQUIRED.

### БЛОК 4 — НЕЗАВИСИМАЯ ПРОВЕРКА (ТОЛЬКО КООРДИНАТОР)

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
