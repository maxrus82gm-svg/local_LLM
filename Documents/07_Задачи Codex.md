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


### БЛОК 1.1 — ПОСЛЕДНЯЯ СДАННАЯ ЗАДАЧА (ДОСЛОВНЫЙ ОРИГИНАЛ)

**CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001 — A/B SUBMITTED / INDEPENDENT EVIDENCE REVIEW / FULL TASK OPEN / Gate 2 / C-D NOT AUTHORIZED.** Ниже — **дословный полный предыдущий БЛОК 1**, включая первоначальную TASK, AMENDMENT и checkpoints. Перенос не закрывает задачу. Предыдущий БЛОК 1.1 `CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001` сохранён дословно в [immutable Git №52](https://github.com/maxrus82gm-svg/local_LLM/blob/f50336a74a9e8929bc6999dd4a4bd77f9ced23d0/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → БЛОК 1.1; запись в №07.00 и №09.

**CHECKPOINT A — SUBMITTED / REVIEW PENDING, 13.11.2026. PREFLIGHT PREPARED / A TESTS PASS / OWNER GO REQUIRED.**
Повторный offline QA/ZIP и анализ invalid_messages завершены; B/C/D NOT RUN. Полный отчёт: Manager_Ultra_LLM/README.md → SAFE-CUTOVER / этап A. Evidence: Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/handoff.json. Задача остаётся в БЛОКЕ 1 до последующих адресно разрешённых стадий; checkpoint не означает завершение всей TASK. Commit/push не выполнялись.

**AMENDMENT / OWNER GO — ЭТАП B / GATE 1, 13.11.2026 (чат владельца):** разрешены исключительно защищённый preflight, полный protected backup и отдельный staging R5. C/D, остановка/перезапуск служб, изменение config/TLS/auth/firewall/task/grants, переключение runtime и inference запрещены. При неизвестном состоянии процессов или проблеме backup — BLOCKED.
**CHECKPOINT B — BLOCKED / REVIEW PENDING:** SMB доступен; Desktop Commander не содержит сервер, WinRM ExplicitCredentialsRequired, CIM/DCOM timeout. Свежие PID/task/Qwen/Valheim не подтверждены; server backup/staging NOT RUN. Gate 2 не достигнут. Отчёт: Manager_Ultra_LLM/README.md → этап B; evidence: Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_handoff.json. C/D не выполнялись.

**УТОЧНЕНИЕ OWNER / CHECKPOINT B, 14.11.2026:** WinRM по IP 192.168.0.77 с текущим TrustedHosts/Negotiate подтверждён на DESKTOP-KT4G5SM/silver, настройки не менялись. Manager PID 209432/task/listener подтверждены. Новый preflight остановлен: Valheim не обнаружен (0 процессов/служб/задач по имени), владелец подтвердил «Нет, Valheim должен работать на этом сервере». **B BLOCKED / backup-staging NOT RUN / Gate 2 не достигнут / C-D запрещены**. Evidence: Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_ip_handoff.json; предложения №22 ag_llm/№18 local_LLM подготовлены отдельно, не применены.

**ПРОДОЛЖЕНИЕ OWNER / CHECKPOINT B — 14.11.2026:** владелец уточнил, что прежний Valheim завершался, затем был вручную заново запущен. Свежий preflight подтвердил Valheim PID 248800/UDP2456-2457 и независимость от Manager, Qwen health=ok. **B PASS / BACKUP VERIFIED / R5 STAGING READY / GATE 2 / REVIEW PENDING.** Создан только новый protected серверный каталог C:\ProgramData\UltraLLM\Manager_R5_STAGEB_20261114T063715Z_685df77d: code backup26/state4/task XML, staging21/21, restore readback/import/TLS/ACL PASS. Manager PID209432/Qwen138268+139516/Valheim248800, task/config/TLS неизменны; службы не перезапускались. C/D и inference НЕ ВЫПОЛНЯЛИСЬ, отдельный OWNER GO C ещё нужен. Отчёт: Manager_Ultra_LLM/README.md → этап B завершён/Gate2; evidence: Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/stage_b_final_handoff.json.

# CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001

**Проект:** Ultra LLM / local_LLM  
**Исполнитель:** Codex  
**Приоритет:** P0  
**Тип:** подготовка и контролируемое переключение Server Manager R5 с обязательными OWNER GO  
**Дата:** 13.11.2026  
**Статус:** ASSIGNED после вставки владельцем

## 1. Цель

Подготовить и, только после отдельных явных разрешений владельца, выполнить безопасное обновление действующего Server Manager до релиза `R5-compat-20261113.1`.

Основные требования:

- Сохранить работающую Qwen через Colibri1.
    
- Не нарушить работу Valheim и других сервисов.
    
- Сохранить все настройки Manager, TLS, авторизации, регистрации клиентов, историю и серверное состояние.
    
- Обеспечить проверенный план возврата прежней версии.
    
- После обновления подтвердить доступность новых API для streaming, reasoning, catalog и управления экземплярами.
    
- Не запускать новые модели автоматически.
    

**ВНИМАНИЕ: назначение этой TASK само по себе НЕ является OWNER GO на изменение реального сервера.**

Работа разделена на этапы с обязательными остановками.

## 2. Репозиторий и обязательные документы

Репозиторий: `maxrus82gm-svg/local_LLM`

Единственный домашний workspace:

`M:\GitHub\local_LLM`

Сначала прочитать актуальные версии:

- `Documents/00_Старт.md`
    
- `Documents/000_Задачи для агента.md`
    
- `Documents/05_Реестр_задач.md`
    
- `Documents/06_Журнал_решений.md`
    
- `Documents/07_Задачи Codex.md`
    
- `Documents/09_История_задач.md`
    
- `Documents/13_Тактический_контекст.md`
    
- `Documents/18_Техническая_документация.md`, особенно §18.29–18.30
    
- `Manager_Ultra_LLM/README.md`
    
- `Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/`
    

Изучить:

- `acceptance.json`, `qa.json`, `qa_regression.json`
    
- `release.json`, `release_manifest.json`, `baseline.json`
    
- `rollback_qa.py`, `rollback_qa.json`
    
- `manager_release.py`, `test_manager_release.py`
    
- соответствующие Client R5 и Manager API исходники.
    

На момент выдачи задания `main` и `GPT_2_local` синхронизированы на коммите №47 `d51b22f2c2abcc6411a09400e7046d777261519f`.

Перед работой заново проверить реальные HEAD, рабочую ветку, локальный diff и наличие чужих изменений.

**Не повторять выполненную работу:** совместимый исходный пакет Manager уже создан. Новая архитектура и переписывание CONTROL-01/P0/P1 не входят в задачу.

## 3. ЭТАП A — независимая повторная проверка релиза

Выполняется на домашнем компьютере в безопасной тестовой среде.

### A1. Проверка пакета

Авторитетный пакет:

`Releases/Manager/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/UltraLLM_Manager_R5_compat_Win64.zip`

Ожидаемый SHA-256 по предыдущему отчёту:

`ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2`

Проверить:

1. Фактический SHA-256 ZIP.
    
2. Все 21 файла и manifest.
    
3. Соответствие `RELEASE.json` и `SHA256SUMS.txt`.
    
4. Отсутствие неизвестных зависимостей, секретов и приватных данных.
    
5. Переносимость исходников.
    
6. Отсутствие неожиданного расхождения с принятым исходным кодом.
    

Использовать существующий `manager_release.py verify`.

При любом несовпадении — **BLOCKED**, без автоматической пересборки или подмены эталонного ZIP.

### A2. Повторные тесты

Повторить доступные безопасные проверки:

- Manager Python tests.
    
- Client Python tests.
    
- Chrome legacy.
    
- Chrome P0 streaming/reasoning.
    
- Chrome P1 slots/multi-instance.
    
- Проверки безопасности и прав.
    
- Rollback QA.
    
- Проверку сохранности конфигурации.
    

Использовать существующий `run_qa.py` с новым уникальным output. Не перезаписывать прошлые evidence.

Все временные файлы создавать только внутри `M:\GitHub\local_LLM\Test`.

Зафиксировать точные команды, exit codes, PASS/FAIL/SKIP и время выполнения. Отличать synthetic tests от настоящего inference.

### A3. Открытая ошибка `invalid_messages`

Владелец вручную проверил установленный Client R5:

- При обычной настройке истории возникала ошибка `invalid_messages`.
    
- После установки **«Сообщений истории = 0»** реальная Qwen стала отвечать.
    
- Переписка сохранилась; ответ стал субъективно быстрее.
    
- Причина ошибки при ненулевой истории пока не доказана.
    

В изолированных тестах проверить формирование `messages`, старую историю, ограничения размеров, `reasoning_content`, последовательность ролей и совместимость со старым/новым Manager.

Не удалять и не изменять рабочую SQLite-историю пользователя.

Подготовить диагностику и рекомендации. Исправлять код только при воспроизводимом дефекте и только в пределах согласованного scope. Если исправление затрагивает установленный Client R5, не устанавливать его автоматически.

## 4. ЭТАП B — серверный preflight

**STOP / GATE 1:** перед любой диагностикой защищённых серверных процессов, задач, конфигураций, созданием резервных копий на сервере или staging получить отдельный OWNER GO с точным разрешённым scope.

До него допустимы только уже разрешённая публичная read-only инвентаризация и локальные QA-тесты.

Целевой сервер по прежней документации:

- Хост: `DESKTOP-KT4G5SM`, Server 77.
    
- Manager: `C:\Server\Ultra_LLM\Manager_Live`.
    
- Scheduled Task: `UltraLLM_Manager_LIVE`.
    
- HTTPS: 8443.
    
- Colibri1/Qwen: ранее 8000.
    
- Valheim: отдельный работающий сервис.
    

Не принимать исторические PID, пути и состояния за текущие без свежей проверки.

После получения адресного OWNER GO:

1. Определить реальные PID, creation time, executable, owner, command line, task XML и HTTPS listener.
    
2. Убедиться, что найден ровно один правильный Manager, а его task action соответствует существующему runtime.
    
3. Проверить актуальные identities и health Qwen/Colibri1 и Valheim без их остановки.
    
4. Проверить Python 3.12 x64, ACL, свободное место, существующие зависимости и блокировки файлов.
    
5. Проверить текущие server configuration, permissions, control gates и наличие активных owned instances, не раскрывая секретов.
    
6. Создать полную резервную копию старой серверной установки, включая неизвестные файлы.
    
7. Создать отдельно защищённую резервную копию task XML, конфигурации, auth, TLS и SQLite/WAL при наличии.
    
8. Проверить сохранность backup, SHA и возможность восстановления.
    
9. Разместить новый пакет в отдельный staging на том же серверном томе, сверить 21 файл и выполнить безопасные import/config checks без запуска listener.
    
10. Зафиксировать исходное состояние Qwen и Valheim.
    

Private backup должен оставаться на сервере с корректными ACL. Не отправлять его в GitHub, LAN-readable папки или обычные отчёты.

**Любая неизвестная принадлежность процесса, несовпадение task action, незавершённый backup, активные owned jobs, проблема ACL/SQLite/TLS или невозможность отката = BLOCKED.**

## 5. ЭТАП C — контролируемое переключение Manager

**STOP / GATE 2:** выполнять только после независимой приёмки этапов A/B и отдельного прямого OWNER GO владельца именно на `Manager-only switch + rollback`.

До получения разрешения нельзя останавливать или перезапускать Manager.

После GO использовать существующий план из `Manager_Ultra_LLM/README.md`, без самовольной замены процедуры.

Контролируемый маршрут:

1. Повторно сверить актуальные PID, task, listener, Qwen, Valheim и резервную копию.
    
2. Штатно остановить исключительно подтверждённую задачу `UltraLLM_Manager_LIVE`.
    
3. Дождаться выхода нужного Manager и освобождения порта.
    
4. Убедиться, что служба не перезапустилась автоматически.
    
5. Сохранить старую папку как retained rollback.
    
6. Переключить только подготовленную staging-папку Manager на прежний runtime-путь.
    
7. Запустить прежний scheduled task с неизменёнными настройками.
    
8. Проверить HTTPS/TLS, authenticated snapshot, catalog, заявленные capabilities и доступность Manager через Client.
    
9. Сравнить hashes конфигурации, task и identities Qwen/Valheim с baseline.
    

Две операции переименования каталогов не считать одной атомарной операцией.

**Никаких массовых** `**taskkill**`**, Stop-Process по имени, изменений firewall, TLS, учётных записей или task settings.**

Не включать `owner_go`, `control_models` либо pairing permissions автоматически.

### C1. Rollback

Использовать существующие критерии `rollback_qa.py` и проверенные observations.

При недостоверном health, ошибке TLS/auth, неверном PID, нарушении работы Qwen/Valheim, невыполненном guard или превышении deadline — остановка процедуры и согласованный возврат прежнего Manager.

Не удалять retained backup и failed candidate. Не восстанавливать изменившуюся SQLite вслепую.

Если безопасный rollback невозможен, остановиться в статусе **BLOCKED**, сохранить доказательства и запросить решение владельца. Не пытаться самостоятельно «починить всё» вмешательством в другие сервисы.

## 6. ЭТАП D — реальная проверка функций

**STOP / GATE 3:** реальные запросы к Qwen, streaming/reasoning/cancel и любые изменения model-control требуют отдельного явного разрешения владельца.

После разрешения проверить сначала уже работающую Qwen, без запуска второй LLM:

- Обычный запрос «Привет».
    
- Потоковую выдачу текста и время до первого фрагмента.
    
- Наличие отдельных `reasoning` событий, только если Colibri/Qwen их действительно возвращает.
    
- Настройки `Thinking = Auto / On / Off` с проверкой поддерживаемости.
    
- Отображение панели «Рассуждения» в Client, если upstream отдаёт соответствующие данные.
    
- Сохранение истории и отправку с лимитами `0`, `5`, `10` сообщений.
    
- Корректную отмену генерации, только в отдельно разрешённом сценарии.
    
- Сохранение работы Qwen и Valheim после испытаний.
    

Фиксировать реальную статистику отдельно от synthetic QA.

**Важно:** наличие нового API не гарантирует, что модель передаёт `reasoning_content`. Если поддержка отсутствует, так и указать, не создавать искусственные рассуждения.

START/STOP CPU/CUDA, запуск KAT-Coder и нескольких экземпляров **не входят в автоматическое продолжение**. Для них требуется следующее согласованное разрешение.

## 7. Общие запреты и безопасность

Без отдельного OWNER GO:

- Не менять серверную конфигурацию.
    
- Не останавливать и не перезапускать серверные службы.
    
- Не изменять Colibri1/Qwen, KAT-Coder, Valheim или сеть.
    
- Не трогать пользовательскую историю и персональные файлы.
    
- Не удалять старые версии, backup и failed staging.
    
- Не включать права управления моделями.
    
- Не изменять установленный Client и ярлык.
    
- Не публиковать секреты, полные приватные логи и пользовательские данные.
    
- Не создавать дополнительные рабочие корни или новую документационную структуру без разрешения.
    

Соблюдать принцип **одна TASK — один итоговый коммит**, без промежуточных коммитов. До независимой проверки координатором сохранить локальный diff и evidence; commit/push и любые изменения удалённых веток отдельно согласовать. Не изменять БЛОК 4 карточки №07.

## 8. Отчёт и критерии результата

В каждой контрольной точке сообщать:

- `DONE` — реально выполнено.
    
- `CHANGED` — изменённые файлы и настройки.
    
- `DIFF` — что отличается от принятого R5.
    
- `TESTS` — команды, PASS/FAIL/SKIP/NOT RUN.
    
- `PRE/POST` — подтверждённые состояния Server Manager, Client, Qwen, Valheim, если соответствующий этап был разрешён.
    
- `BACKUP/ROLLBACK` — точные результаты и ограничения, без раскрытия приватных данных.
    
- `PROBLEMS` — найденные неисправности.
    
- `QUESTIONS` — необходимые решения владельца.
    
- `DOC IMPACT` — изменения для №05/06/07/09/13/18.
    
- `NEXT` — следующая контрольная точка, не самовольное продолжение.
    

Использовать существующие документы и каталог evidence внутри workspace. Не перезаписывать предыдущие отчёты.

**Первый обязательный результат:** `PREFLIGHT PREPARED / A TESTS PASS|PARTIAL|BLOCKED / OWNER GO REQUIRED`.

После этапа A остановиться, передать отчёт координатору и дождаться независимой проверки.

Если последующие этапы будут адресно разрешены, продолжать только в утверждённом scope, с отдельным отчётом и STOP на каждом gate.

**Главный принцип: работоспособность Qwen и Valheim важнее скорости обновления Manager.**

### БЛОК 2 — ПОСЛЕДНИЕ ПЯТЬ ЗАДАЧ (КОРОТКИЙ ИНДЕКС)

- **CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001 / 13.11:** SOURCE candidate, code/evidence review, original `main` `f50336a74a9e8929bc6999dd4a4bd77f9ced23d0` → №07 БЛОК 1.1; live NOT RUN. См. №07.00/№09.
- **CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001 / 13.11:** AUTHOR LIVE PASS / independent EVIDENCE REVIEW / HOST NOT RE-RUN; №09, main №45.
- **CODEX-UL-CLIENT-DEPLOY-20261112-001 / 12.11:** AUTHOR Client deployment; старый оригинальный краткий отчёт в [№07 immutable snapshot](https://github.com/maxrus82gm-svg/local_LLM/blob/f50336a74a9e8929bc6999dd4a4bd77f9ced23d0/Documents/07_%D0%97%D0%B0%D0%B4%D0%B0%D1%87%D0%B8%20Codex.md) → БЛОК 2, №09 архивный указатель.
- **CODEX-UL-STREAM-SLOTS-20261112-001 / 12.11:** SOURCE P0/P1 mock Windows CI PASS, LIVE NOT RUN; №09, commit 9900ccd.
- **CODEX-UL-CONTROL-01-STREAM-20261111-001 / 11.11:** SOURCE PARTIAL, LIVE NOT RUN; №09, commit 6c74edd.

**Отдельный незавершённый checkpoint:** `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` A/B SUBMITTED, C/D OPEN и Gate 2; полная постановка в 1.1, **не** закрытая целиком задача. Новая `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` в БЛОКЕ 1 **AWAITING OWNER START**. Прежняя пятёрка сохранена через immutable №52 и историю №09.

### БЛОК 3 — OPEN / NEXT

- **Текущая новая постановка:** `CODEX-UL-R5-CI-GATE2-HARDEN-20261114-001` — offline CI/negative tests; напрямую помещена координатором по разовому поручению владельца, **AWAITING OWNER START**, авторских результатов по ней ещё нет.
- **SAFE-CUTOVER `CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001` остаётся OPEN:** A/B сданы, Stage B Gate 2 по авторским evidence (backup 26 code+4 state+Task XML, staging R5 21), C/D не выполнялись и не разрешены. Полная TASK+AMENDMENT в БЛОКЕ 1.1.
- **Windows source CI** №52 run `43572399891`: Manager 311, 1 SKIP, Client 49, Chrome legacy/P0/P1 PASS; независимый физический серверный повтор и SHA оригинального ZIP NOT RUN. Внедрение и owner UX позже по отдельному GO.
- **History/WinRM:** №05/09/13/18 сохраняют evidence и OPEN. Предложения WinRM для №22 `ag_llm` и №18 `local_LLM` остаются отдельно без внедрения.
- После технической сдачи новой TASK координатор выполняет собственные тесты/CI и обновляет БЛОК 4, реестр, общую историю и тактический контекст.

### БЛОК 4 — НЕЗАВИСИМАЯ ПРОВЕРКА (ТОЛЬКО КООРДИНАТОР)

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
