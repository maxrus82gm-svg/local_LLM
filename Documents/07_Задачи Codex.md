# Задачи Codex — рабочая карточка исполнителя Ultra LLM

**Постоянная приёмка:** `TEST-FULL-CYCLE-01` (№000 §5.1, №18 §18.31) — самостоятельный инженерный разбор и тесты, GitHub CI по применимости, REAL APP и обязательный OWNER UX при значимых внешних изменениях. Действующий БЛОК 1, БЛОК 4, история и OWNER GO не меняются этой записью.


**Назначение:** здесь Codex получает конкретную утверждённую TASK, узнаёт разрешённые границы и сдаёт подтверждаемый отчёт. Карточка — оперативный документ, не личный архив и не разрешение на весь сервер.

**Редакция:** 2026-11-12; после сдачи БЛОК 1 освобождается независимо от приёмки. Указания другого проекта (Web Alarm Ultra) — только примеры, не правила или TASK этого проекта.

[[07.00_История_задач_Codex|История задач Codex]]

[[000_Задачи для агента|Общая координация задач]]

## 1. Рабочие правила Codex

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

**CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001 / AWAITING OWNER START.** Владелец примет документный №55, затем отдельно активирует Codex.

# CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001

**Приоритет P0 · исполнитель Codex · дата 14.11.2026 · статус ASSIGNED / AWAITING OWNER START.** Владелец сначала принимает документный №55 из `GPT_2_local`, после этого отдельно активирует Codex. Это отдельная OFFLINE regression-fix TASK, не разрешение на Stage C/D.

## 1. Истина и цель

`main` №54 `f324513cac5a270ac620acdf2466c0f27efb6593` уже содержит исходный результат `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` с пятью разрешёнными test/CI-файлами плюс вне scope `Documents/.obsidian/workspace.json`. Изучить авторский handoff `Manager_Ultra_LLM/README.md` начиная с раздела `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` (примерно строка 1028), четыре RED-теста и `TEST-FULL-CYCLE-01` №000 §5.1–5.3. **Не публиковать прежние файлы повторно.**

В [Windows CI №54](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43581579523) Manager **330 = 325 PASS + 4 FAIL + 1 SKIP**, Client 49 PASS, Chrome legacy/P0/P1 и negative controls PASS. Эти четыре FAIL воспроизводимы; `RELEASE HOLD` действует. Исправить ТОЛЬКО подтверждённые F1a/F1b/F1c/F2 без реального обновления Manager и без ослабления существующих тестов.

## 2. Read matrix

`Documents/{00_Старт.md,000_Задачи для агента.md,05_Реестр_задач.md,07_Задачи Codex.md,07.00_История_задач_Codex.md,09_История_задач.md,13_Тактический_контекст.md,18_Техническая_документация.md}` — актуальные вводные, §18.33, №000 §5.1/5.3; `Manager_Ultra_LLM/{README.md,test_gate2_hardening.py,test_manager_release.py,test_control_runtime.py,manager_release.py}`; `Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_complete_readonly.py`; `.github/workflows/ultra-offline-ci.yml`; исходный GitHub [run №54](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43581579523). Проверять текущие Git HEAD и diff перед работой, не использовать старый №53 как источник актуальных тестов.

## 3. Четыре исправления (без live execution)

1. **F1a — listener:** в offline `stage_b_complete_readonly.py` отказывать при противоречии `manager_listener` с manager PID и baseline. Проверять PID, адрес, порт, отсутствие полей, несоответствие источников и относительную идентичность. Не полагаться лишь на равенство объектов `post.manager == baseline.manager`.
2. **F1b — flags:** все ожидаемые 24 guard-проверки должны быть строго `bool True`, а не truthy `'false'`, `1` или произвольное значение. Пустой/лишний/недостающий/inconsistent набор — FAIL; не оставлять security-guards только через оптимизируемые `assert` при `python -O`.
3. **F1c — HTTP:** принимать только строго заданное `unauth_snapshot_http=403` и `unauth_snapshot_error='source_not_permitted'` при согласованном baseline. Произвольная 403 reason, другие status, отсутствие reason и несогласованность — FAIL; использовать synthetic evidence, не обращаться к live серверу.
4. **F2 — import closure:** в `manager_release.py` безопасным статическим AST-анализом выявлять константные `__import__('missing')` и `importlib.import_module('missing')` в консистентном package manifest и блокировать неупакованные/non-stdlib зависимости без исполнения недоверенного кода. Динамические неизвестные expression — явная, документированная fail-closed policy. Не ломать разрешённые stdlib/локальные imports.

**Критерий:** исходные четыре RED-теста проходят только благодаря правильным изменениям валидаторов. Добавить ограниченные negative/positive cases (listener address/port/missing/PID, type `1`, HTTP bad reason, importlib expression, stdlib imports). Запрещено `skip`, `expectedFailure`, исключение из discovery, подмена fixture, маскировка traceback, удаление FAIL evidence.

## 4. Точный WRITE и Git scope

Разрешены ТОЛЬКО:
- `Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_complete_readonly.py` (офлайн checker; опубликованные JSON доказательства не менять);
- `Manager_Ultra_LLM/manager_release.py`;
- `Manager_Ultra_LLM/test_gate2_hardening.py`;
- `Manager_Ultra_LLM/test_manager_release.py`;
- `Manager_Ultra_LLM/README.md` (только append author handoff).

Всё прочее **READ ONLY**, включая `.github/workflows/ultra-offline-ci.yml`, `test_control_runtime.py`, `Documents/.obsidian/**`, документы №00/000/05/06/07/09/13/18, client/installer и private backups. Если scope недостаточен — `BLOCKED / ASK OWNER`, не расширять самому.

После явного стартового сообщения владельца разрешён **ровно один финальный commit/push только в `GPT_2_local`** этих пяти разрешённых файлов, если текущая ветка и ancestor/HEAD корректны. Перед публикацией проверить `git status`, `git diff --name-only`, `git diff --cached --name-only` и строгое совпадение с whitelist; запрещено `git add .`, `git add -A`, force push, reset/rebase/merge самостоятельно и любые commits напрямую в `main`. Если там ещё чужой staged `workspace.json` — остановиться, не удалять чужие изменения и не включать файл в commit.

**Запрещено:** live Manager, server/WinRM/SMB execution, real auth/TLS, task/firewall/ACL, Qwen/Valheim, модельные запуски/LLM inference, Client Production, изменение ZIP/staged 21 files, rollback/backup, Stage C/D и работа вне согласованного source scope.

## 5. Проверка и handoff

Автор должен реально проверить Manager suite **не меньше 330**, Client **не меньше 49**, 5 негативных контролей, Chrome legacy/P0/P1, synthetic backup/ACL/identity, ZIP/source policy. Дать матрицу `F1a/F1b/F1c/F2 → до FAIL → после PASS`, команды, exit codes, counts, первый FAIL, новых FAIL нет, отчёт. Пуш в `GPT_2_local` запускает существующий hosted Windows CI; зафиксировать **новый** SHA и run ID, JUnit/JSON, не выдавать старый `43581579523` за новый PASS. Если CI недоступен — `NOT RUN`, если FAIL — честно `PARTIAL`.

`DONE / CHANGED / DIFF / TESTS / CI / PROBLEMS / QUESTIONS / DOC IMPACT / NEXT`, точные изменённые файлы, сохраняемые F3 trusted private backup provenance и F4 flaky first Chrome (отдельные FOLLOWUP). Статус `AUTHOR QA READY / INDEPENDENT REVIEW PENDING` либо `PARTIAL/BLOCKED`; по сдаче остановиться. Координатор независимо проверяет код/CI и ведёт №05/07/09/13/18. **USER UX NOT REQUIRED** для внутреннего фикса, `RELEASE HOLD` и отдельный GO для C/D сохраняются даже при зелёном CI.


### БЛОК 1.1 — ПОСЛЕДНЯЯ СДАННАЯ ЗАДАЧА (ДОСЛОВНЫЙ ОРИГИНАЛ)

**CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001: AUTHOR TESTED / PARTIAL / WINDOWS CI FAIL 4 / RELEASE HOLD / ITERATION ARCHIVED.** Дословный текст прежнего БЛОКА 1 следует ниже (включая историческую метку `AWAITING OWNER START`, которая относилась лишь к моменту постановки). Позднее единственный commit №54 `f324513cac5a270ac620acdf2466c0f27efb6593` уже был опубликован прямо в `main`. [Windows run `43581579523`](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43581579523) подтвердил четыре RED; повторная публикация не требуется. Independent code+CI log review подтвердил регрессии, но fresh own test run не выполнялся. Предшествующая полная `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` с AMENDMENT/стадиями A/B заархивирована в [immutable №54](https://github.com/maxrus82gm-svg/local_LLM/blob/f324513cac5a270ac620acdf2466c0f27efb6593/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → предыдущий БЛОК 1.1, остаётся OPEN C/D.

**CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001 — AWAITING OWNER START.** Исключение на запись в GitHub выдано владельцем 14.11.2026; Codex пока не запускать.

# CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001

**Задача:** усилить инженерные и CI-проверки Manager R5 перед разрешением обновления сервера  
**Исполнитель:** Codex; **приоритет:** P0; **дата:** 14.11.2026  
**Статус:** ASSIGNED IN CARD / **AWAITING OWNER START**. Владелец отдельно запустит задачу после обновления GitHub Desktop. Это ещё не исполнение.

## 1. Цель и baseline

Подготовить воспроизводимый offline source/Windows CI gate для `R5-compat-20261113.1`, исправить пробелы **в тестах**, а не переписать готовый Manager. Предыдущая `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` завершила только A/B (Stage B backup/staging и Gate 2); C/D всё ещё OPEN и не разрешены.

**Git baseline:** на момент постановки `main` и `GPT_2_local` совпадали на `f50336a74a9e8929bc6999dd4a4bd77f9ced23d0` (№52). Проверить HEAD заново перед началом. **Существующий Windows CI:** `43572399891`, исходный SHA №52, Manager `Ran 311 tests / OK (skipped=1)`, Client `Ran 49 tests / OK`, Chrome legacy/P0/P1 PASS. Это source/mock tests, не real inference, настоящий ZIP SHA или live server.

## 2. Матрица чтения

Обязательно читать относящиеся разделы:
- `Documents/00_Старт.md`; `Documents/000_Задачи для агента.md` §§3–5.1 `TEST-FULL-CYCLE-01`;
- `Documents/07_Задачи Codex.md` БЛОКИ 1, 1.1, 3–4; `Documents/07.00_История_задач_Codex.md`;
- `Documents/05_Реестр_задач.md`, `Documents/09_История_задач.md`, `Documents/13_Тактический_контекст.md`, `Documents/18_Техническая_документация.md` §§18.30–18.32;
- `.github/workflows/ultra-offline-ci.yml`;
- `Manager_Ultra_LLM/manager_release.py`, `test_manager_release.py`, `README.md`, связанные preflight/rollback/security/HTTP tests;
- опубликованные evidence `Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/` и `Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/` по необходимости.

Перед любой правкой проверить actual HEAD, локальный diff, отсутствие чужих изменений, scope и ранее закрытое покрытие. Не дублировать тесты.

## 3. Работа и тесты

**A. Coverage matrix:** `изменение → риск → старый тест → пробел → новый тест/оракул`. Разделять AUTHOR, независимые проверки, FAIL, SKIP, NOT RUN.

**B. Синтетические негативные/регрессионные сценарии, только недостающее покрытие:**
1. Release ZIP 21 файл, allowlist, manifest/SHA, приватные/лишние файлы, опасные пути/link/junction, отсутствующие зависимости. *Созданный синтетический ZIP ≠ оригинальный авторитетный ZIP.* Если исходный ZIP недоступен в CI — `EXACT ZIP CI NOT RUN`.
2. Manager guard: неожиданно изменившиеся PID/creation time/owner/Task XML/listener; отсутствующие или изменившиеся Qwen и Valheim — **fail-closed** на synthetic snapshots, без касания реальных процессов.
3. Backup/restore/rollback: повреждённый, неполный, чужой, stale backup/TLS/auth/config, сбой restore/неполная транзакция — ожидаемый RED. Никакого реального cutover.
4. ACL: равнозначные перестановки Allow ACE разрешены; новый посторонний SID/изменённый owner или права, небезопасное расширение — RED.
5. HTTP/auth: ожидаемый `401` и точно `403 source_not_permitted` различать; произвольный 403, пропавший grant или пустой вывод не являются успехом.
6. Негативные контроли должны реально обнаруживать ошибку; пустая test collection, любое исключение или просто exit 0 — не PASS. Сохранять первый FAIL.

**C. Existing Windows CI:** использовать **тот же** `.github/workflows/ultra-offline-ci.yml`, не создавать второй workflow. При необходимости улучшить `windows-latest`, timeout, минимальные permissions, `persist-credentials: false`, fixed Python/Node/dependency versions, script exit codes, непустые suites, независимые negative controls. Инструменты и тестируемые данные — изолированные, без секретов и внешнего API. Hosted CI на точном SHA с run ID только если действительно запущен; старый run или YAML без выполнения не считать новым PASS.

**D. Авторские проверки:** повторить уместные offline suites/negative tests по разрешённым правам, зафиксировать команды, фактические PASS/FAIL/ERROR/SKIP, regressions. Если найден production-defect — воспроизвести и оформить FOLLOWUP; **не менять production-код ради зелёных тестов**.

## 4. Write scope и запреты

Разрешены правки существующих адресных тестов в `Manager_Ultra_LLM/`, при необходимости один новый `test_*.py` в этой папке, существующий `.github/workflows/ultra-offline-ci.yml` и относящаяся авторская часть `Manager_Ultra_LLM/README.md`. Временные тестовые файлы — только в согласованном workspace `M:\GitHub\local_LLM`. Не создавать другие новые документы/отчёты/CI workflow без отдельного GO.

Git-чтение разрешено; commit/push и изменения чужих веток, особенно `main`, **не разрешены автоматически**. Для публикации CI/test изменений запросить отдельное согласование; общий регламент — один итоговый коммит на TASK. Не выполнять команды с реальными auth/секретами.

**Запрет:** изменения live/production Manager или Client, `Production/Client`, TLS/auth/config/ACL, Scheduled Task, firewall, Qwen/Colibri, Valheim, API charges, LLM inference, CPU/CUDA START/STOP, серверный backup/staging или переключение; C/D и физический rollback — только по отдельному OWNER GO.

## 5. Критерий сдачи

`DONE / CHANGED / DIFF / PROBLEMS / QUESTIONS / DOC IMPACT / NEXT`, точный исходный SHA, матрица рисков, пути правок, команды/exit codes/counts, отдельно ожидаемые RED и реальные FAIL, доказательства и CI run ID/SHA или честное NOT RUN, проверка оригинального ZIP или NOT RUN, список безопасных followups. Не объявлять собственный `INDEPENDENT PASS` или `LIVE PASS`.

Подробный авторский handoff — в **существующем** `Manager_Ultra_LLM/README.md` (не создавать новые permanent reports без разрешения). Итог `AUTHOR QA READY / INDEPENDENT REVIEW PENDING` либо `PARTIAL/BLOCKED`. После сдачи **остановиться**, дальнейшую независимую проверку выполняет ChatGPT по №000 §5.1. Для сугубо внутреннего QA OWNER UX `NOT REQUIRED`. Никакого C/D.

### БЛОК 2 — ПОСЛЕДНИЕ ПЯТЬ ЗАДАЧ (КОРОТКИЙ ИНДЕКС)

- **CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001 / 14.11** — AUTHOR PARTIAL / CODE+CI LOG REVIEW / 4 reproduced FAIL / RELEASE HOLD; полный оригинал в БЛОКЕ 1.1, источник `main` №54, Windows run `43581579523`, handoff `Manager_Ultra_LLM/README.md`.
- **CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001 / 13.11** — SOURCE candidate, independent evidence review, LIVE NOT RUN; immutable №52 → №07 БЛОК 1.1, №07.00/09.
- **CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001 / 13.11** — AUTHOR Client LIVE PASS / independent evidence, host rerun NOT RUN; №09.
- **CODEX-UL-CLIENT-DEPLOY-20261112-001 / 12.11** — Client deploy, later root migration; архив №09/immutable №54.
- **CODEX-UL-STREAM-SLOTS-20261112-001 / 12.11** — SOURCE/mock CI PASS / LIVE NOT RUN; №09.

**Отдельно OPEN (не пятый закрытый результат):** `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` A/B Gate 2, C/D NOT RUN, original+AMENDMENT [immutable №54](https://github.com/maxrus82gm-svg/local_LLM/blob/f324513cac5a270ac620acdf2466c0f27efb6593/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → прежний БЛОК 1.1. Новая `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` — в БЛОКЕ 1, AWAITING OWNER START.

### БЛОК 3 — OPEN / NEXT

- **ACTIVE / NEXT:** `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` — P0 offline исправление F1a listener, F1b boolean flags, F1c точный `403/source_not_permitted`, F2 dynamic import; сейчас `AWAITING OWNER START`. Только после разрешённой активации один scoped commit/push в `GPT_2_local`.
- **Уже опубликовано:** `main` №54 `f324513cac5a270ac620acdf2466c0f27efb6593`, [Actions 43581579523](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43581579523) `FAIL`, Manager `325 PASS / 4 FAIL / 1 SKIP`, Client 49 PASS, negative controls/Chrome PASS. Это не «ожидает публикации», повторный commit тех же тестов запрещён.
- **SAFE-CUTOVER `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001`:** A/B SUBMITTED, Gate 2, полная TASK OPEN, C/D без GO; оригинал архивирован по SHA №54. Реальный сервер/Qwen/Valheim не менялись по evidence; OWN host rerun NOT RUN.
- **F3/F4:** trusted private backup provenance COVERAGE GAP, legacy first Chrome failure/second pass HYPOTHESIS — separate OPEN, не смешивать с 4 FAIL.
- **Публикация:** №55 документный child №54 только в `GPT_2_local`, owner принимает в main. Проверять Git SHA, task/README/CI run до каждого повторного предложения commit; строго whitelist, `.obsidian/**` запрещён.

### БЛОК 4 — НЕЗАВИСИМАЯ ПРОВЕРКА (ТОЛЬКО КООРДИНАТОР)

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
