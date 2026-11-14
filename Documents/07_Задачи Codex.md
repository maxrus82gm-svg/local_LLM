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

# CODEX-UL-R5-F3-BACKUP-PROVENANCE-20261114-001

**Название:** Manager R5 — независимая проверка происхождения и целостности приватных резервных копий (F3)

**Проект:** `maxrus82gm-svg/local_LLM`  
**Исполнитель:** Codex  
**Приоритет:** P0  
**Тип:** OFFLINE SECURITY / REGRESSION / WINDOWS CI  
**Статус:** ASSIGNED после размещения владельцем в №07 БЛОК 1 и отдельной активации.

## 1. Цель

Устранить F3 — пробел в независимой проверке приватных резервных копий Manager.

Существующий `verify_snapshot` проверяет соответствие файлов манифесту. Однако при совместной подмене **и файлов, и манифеста** такая проверка потенциально может дать ложный PASS.

Нужна дополнительная проверка с контрольным SHA-256, полученным из источника **вне проверяемого backup-каталога**.

Важное исходное доказательство: в неизменяемом коммите №51 `c2c1bb84aa83ae6ee4ba7cdd3f0604eeb9f0c7b4` уже присутствует `stage_b_final_handoff.json`, содержащий `server_materials.private_manifest_sha256`. Также SHA отражён в историческом `stage_b_completion.json`.

Сначала установить достоверность и границы доверия к этому значению. Публикация хеша в Git доказывает его сохранность с момента коммита, но сама по себе не доказывает безусловную подлинность изначальной копии.

## 2. Обязательное чтение

- `Documents/00_Старт.md`
    
- `Documents/000_Задачи для агента.md`, §§5.1 и 5.3
    
- `Documents/05_Реестр_задач.md`
    
- `Documents/07_Задачи Codex.md`
    
- `Documents/09_История_задач.md`
    
- `Documents/13_Тактический_контекст.md`
    
- `Documents/18_Техническая_документация.md`, §§18.33–18.34
    
- `Manager_Ultra_LLM/README.md`, отчёты CI-HARDEN и REGRESSION-FIX
    
- `Manager_Ultra_LLM/test_gate2_hardening.py`
    
- `Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_prepare_server.py`
    
- `stage_b_independent_verify.ps1`
    
- `stage_b_complete_readonly.py`
    
- `stage_b_final_handoff.json`, `stage_b_completion.json`
    

Baseline: принятый коммит №57 `6e3f29582a041df6632651ed0743d69c95d667b1`. Перед началом заново проверить Git HEAD.

## 3. Реализация

### A. Анализ доверия

Составить матрицу:

`Источник → доверенная граница → контрольный SHA → проверяемые bytes → возможная подмена → результат`.

Выделить разницу между:

- Самопроверкой manifest ↔ files.
    
- Сравнением manifest с независимо зафиксированным SHA.
    
- Подтверждением подлинности первоначально созданной копии.
    

Если последний уровень доказательств недостижим существующими данными, оставить его `NOT PROVEN`, не выдавать за PASS.

### B. Независимый офлайн-верификатор

Создать проверяемый механизм, который:

1. Принимает **явно заданный доверенный SHA-256 манифеста**, не вычисляя эталон из самого проверяемого backup.
    
2. Проверяет реальные байты манифеста по этому SHA.
    
3. Проверяет приватные файлы по зафиксированным в манифесте хешам, размерам и составу.
    
4. Проверяет отсутствие лишних, недостающих, подменённых или небезопасно перенаправленных файлов.
    
5. Проверяет соответствие task XML, если он входит в охваченный контракт.
    
6. Отказывает при недоступном или недостоверном доверенном эталоне.
    
7. Работает в режиме **read-only**, не изменяя исходные файлы и не экспортируя секреты.
    

Разрешается один новый Python-модуль `Manager_Ultra_LLM/backup_provenance.py` на стандартной библиотеке. Он должен поддерживать изолированные синтетические проверки и иметь явно документированный интерфейс для будущего отдельно разрешённого серверного аудита.

Не делать такой аудит сейчас.

### C. Негативные проверки

Обязательны synthetic-сценарии:

- Подмена одного приватного файла.
    
- Подмена только манифеста.
    
- **Совместная подмена приватных файлов и манифеста** с внутренне корректными SHA.
    
- Несоответствие внешнему эталонному SHA.
    
- Отсутствие trusted pin.
    
- Неполный backup, лишний файл, небезопасный путь, link/junction.
    
- Повреждённый или изменённый task XML.
    
- Ошибка чтения, некорректная схема манифеста и гонка изменения проверяемого файла, насколько её можно безопасно воспроизвести.
    

Ключевой критерий F3: **совместная подмена backup + manifest должна приводить к FAIL, даже когда обычный** `**verify_snapshot**` **принимает их согласованность**.

Для исправной синтетической копии — PASS.

### D. Сохранение обратной совместимости

Не изменять ранее опубликованные Stage B evidence, приватный manifest, старые SHA, ZIP и staged release.

Не менять производственные API Manager, Client, поток генерации или поведение моделей.

## 4. WRITE scope

Разрешается изменять только:

- `Manager_Ultra_LLM/backup_provenance.py` — один новый модуль.
    
- `Manager_Ultra_LLM/test_gate2_hardening.py` — дополнительные регрессионные тесты.
    
- `Manager_Ultra_LLM/README.md` — append-only отчёт.
    

Остальные файлы, включая `.github/workflows/ultra-offline-ci.yml`, исторические скрипты Stage B, JSON evidence, №00/000/05/06/07/09/13/18 и `.obsidian/**`, — **READ ONLY**.

Если существующий Windows CI не обнаруживает новые тесты либо необходим дополнительный write-scope, остановиться и запросить разрешение. Не расширять его самостоятельно.

## 5. Git и безопасность

После отдельного сообщения владельца о запуске TASK разрешён **один итоговый commit/push исключительно в** `**GPT_2_local**` с точным whitelist.

Перед commit обязательно проверить `git status`, `git diff --name-only`, `git diff --cached --name-only` и актуальные удалённые SHA.

Запрещено `git add .`, `git add -A`, прямой push в `main`, reset/rebase/force push и включение посторонних изменений.

**Строгие запреты:** не подключаться к рабочему серверу для выполнения проверок, не читать и не копировать настоящие приватные backup-файлы, не изменять TLS, конфигурацию, задачи Windows, ACL, Qwen, Valheim и Client Production. Не выполнять этапы C/D, server staging, rollback, CPU/CUDA или inference.

## 6. Тестирование и сдача

Codex обязан провести авторскую проверку нового verifier и его позитивных/негативных сценариев, затем полные доступные offline suites Manager и Client, пять negative controls и Chrome legacy/P0/P1.

Запустить существующий GitHub-hosted Windows CI после разрешённой публикации. Сохранить точный SHA, run ID, фактические счётчики PASS/FAIL/SKIP и журналы.

Результат в формате:

`DONE / CHANGED / DIFF / TESTS / NEGATIVE CONTROLS / CI / PROBLEMS / QUESTIONS / DOC IMPACT / NEXT`.

Приложить матрицу доверия, доказательства совместной подмены и перечень ограничений для будущей серверной проверки.

Статус по завершении: `AUTHOR QA READY / INDEPENDENT REVIEW PENDING` либо `PARTIAL / BLOCKED`.

После сдачи остановиться для независимой приёмки ChatGPT. **RELEASE HOLD сохраняется; никаких C/D.**

### БЛОК 1.1 — ПОСЛЕДНЯЯ СДАННАЯ ЗАДАЧА (ДОСЛОВНЫЙ ОРИГИНАЛ)

**CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001 — AUTHOR QA READY / INDEPENDENT SOURCE+CI ACCEPTED / SCOPED TASK CLOSED / RELEASE HOLD.** Дословный полный прежний БЛОК 1 следует ниже; исторический статус `AWAITING OWNER START` внутри оригинала отражает дату назначения и не является текущим. Фактический исходный код в `main` №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, независимый GitHub CI [run `43599309587`, attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2): Manager 337 total = 336 PASS + 1 SKIP, Client49 PASS, negative controls и Chrome PASS. Код и четыре прежних RED-метода проверены координатором, текст всех четырёх методов **совпадает с №54**, README append-only. Real server/packaged release NOT RUN; `USER UX NOT REQUIRED` для внутренней проверки. Предыдущая БЛОК 1.1 `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` с полным текстом сохранена в [immutable №56](https://github.com/maxrus82gm-svg/local_LLM/blob/d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → старая 1.1 и №07.00/09. SAFE-CUTOVER `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` A/B Gate2 и C/D OPEN остаётся в immutable №54. Архивная ротация **не означает релизный GO**.

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

### БЛОК 2 — ПОСЛЕДНИЕ ПЯТЬ ЗАДАЧ (КОРОТКИЙ ИНДЕКС)

- **CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001 / 14.11:** OFFLINE source fix **SCOPED CLOSED / INDEPENDENT TECHNICAL+CI PASS**: №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, [independent CI attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) 336 Manager PASS/1 SKIP, Client49 PASS, Chrome/5 controls PASS. REAL/ZIP rebuild NOT RUN; RELEASE HOLD.
- **CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001 / 14.11:** AUTHOR PARTIAL, independent code/CI review, четыре RED/Windows FAIL; оригинал [immutable №56](https://github.com/maxrus82gm-svg/local_LLM/blob/d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → прежняя БЛОК 1.1; №54/README/№09.
- **CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001 / 13.11:** SOURCE candidate/evidence PASS; immutable №52 оригинал; реальный deploy NOT RUN.
- **CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001 / 13.11:** AUTHOR Client LIVE PASS, independent evidence review, own rerun NOT RUN; №09.
- **CODEX-UL-CLIENT-DEPLOY-20261112-001 / 12.11:** Client deployment and later ROOT migration; история №09, immutable commits.

**Дополнительные OPEN вне завершённой пятёрки:** `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` — A/B SUBMITTED, Stage B Gate2, C/D NOT RUN/OWNER GO absent; полная задача и AMENDMENT immutable №54. F3 backup provenance pin; F4 Chrome first-run; versioned R5 release/re-stage после source fixes. Все ранние задачи остаются в №09/immutable Git.

### БЛОК 3 — OPEN / NEXT

- **Свободен БЛОК 1.** `CODEX-UL-R5-GATE2-REGRESSION-FIX-20261114-001` технически принята и архивирована в БЛОК 1.1, **не** принята как релиз/серверное развертывание. Новая TASK пока не назначена.
- **F1a/F1b/F1c/F2 source закрыты:** №56 `d79e7fb0aeabb49c96cbbb643376ab910b4a6cb5`, независимый Windows [run 43599309587 attempt 2](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43599309587/attempts/2) — Manager `337 total (336 PASS/1 SKIP)`, Client49 PASS, five negative controls/Chrome legacy/P0/P1 PASS, 4 старые RED сохранены и теперь PASS.
- **RELEASE HOLD / NEXT по отдельному OWNER GO:** старый original ZIP и серверное staging 21/21 содержат прежний validator; требуется версия нового release + проверка SHA и безопасное staging (не в этой TASK), независимый physical host preflight, F3 trusted private backup provenance pin, оценка F4 Chrome first-run. C/D `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` не разрешены, Qwen/Valheim не трогать.
- **История/согласование:** №05/07.00/09/13/18 и №00 обновлены одним doc-only №57 в `GPT_2_local`, `main` меняет только владелец. §5.3 publication guard / test protocol продолжают действовать, новых UI изменений нет, OWNER UX NOT REQUIRED.

### БЛОК 4 — НЕЗАВИСИМАЯ ПРОВЕРКА (ТОЛЬКО КООРДИНАТОР)

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
