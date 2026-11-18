# Задачи Codex — рабочая карточка исполнителя Ultra LLM

**Постоянная приёмка:** `TEST-FULL-CYCLE-01` (№000 §5.1, №18 §18.31) — самостоятельный инженерный разбор и тесты, GitHub CI по применимости, REAL APP и обязательный OWNER UX при значимых внешних изменениях. Действующий БЛОК 1, БЛОК 4, история и OWNER GO не меняются этой записью.


**Назначение:** здесь Codex получает конкретную утверждённую TASK, узнаёт разрешённые границы и сдаёт подтверждаемый отчёт. Карточка — оперативный документ, не личный архив и не разрешение на весь сервер.

**Редакция:** 2026-11-12; после сдачи БЛОК 1 освобождается независимо от приёмки. Указания другого проекта (Web Alarm Ultra) — только примеры, не правила или TASK этого проекта.

[[07.00_История_задач_Codex|История задач Codex]]

[[000_Задачи для агента|Общая координация задач]]

## 1. Рабочие правила Codex

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

**CODEX-UL-R5-CHROME-STABILITY-20261117-001 — PARTIAL / REVIEW PENDING.**
Авторская offline/synthetic диагностика и минимальный test-harness diff готовы;
точная причина исходного P1 transient и старой F4 задержки не доказана,
новый GitHub CI NOT RUN, REAL APP NOT RUN, RELEASE HOLD.
Отчёт: Manager_Ultra_LLM/README.md, секция TASK-ID; evidence: Test/CODEX-UL-R5-CHROME-STABILITY-20261117-001/.
Прежняя F3 БЛОК 1.1 побайтово сверена с immutable №60 и отражена в №09.
Ниже — полный дословный оригинал новой сданной постановки.

# CODEX-UL-R5-CHROME-STABILITY-20261117-001

**TASK ID:** `CODEX-UL-R5-CHROME-STABILITY-20261117-001`  
**Название:** F4 Chrome cold-start + P1 post-STOP intermittent status — диагностика, минимальный fix, регрессии  
**Дата:** 17.11.2026  
**Проект:** `maxrus82gm-svg/local_LLM`, локальный root `M:\GitHub\local_LLM`  
**Исполнитель:** Codex; приоритет P0; **OFFLINE SOURCE/CHROME QA ONLY**  
**Статус:** ASSIGNED IN BLOCK1 / AWAITING OWNER LOCAL SYNC + ACTIVATION. Размещение в GitHub само не синхронизирует локальный Codex.

## 1. Цель и доказательства

Исследовать две **пока не доказано связанные** нестабильности.

**P1:** [Windows Actions FAIL №43634294641](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43634294641), job `132567585813` на source SHA №60 `de6a96ba78f53685e85a49b5f49d7fa870f4f187`. Manager 350 PASS/1 SKIP, Client49 PASS, Chrome legacy и P0 PASS; P1 `Client_Ultra_LLM/test_browser_slots_source.mjs:65` после `Stop slot2` вызвал `api("/api/status").then(x=>x.managers[0].data.control.instances...)` при `data=null`: `TypeError: Cannot read properties of null (reading 'control')`. Причина NULL в статусе неизвестна.

**Контроль:** [Actions PASS №43635620449](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/43635620449), job `132571644874` — тот же exact source SHA, все этапы PASS. Это указывает на непостоянный сбой, а НЕ доказывает его безвредность.

**F4:** ранее первый запуск Chrome legacy завершился FAIL, затем без изменения исходников повторился PASS; прежний `FOLLOWUP-UL-R5-CHROME-FIRST-LOAD-20261114-001` открыт. Не считать F4 и P1 одной причиной без подтверждения.

**Итог задачи:** документированная первопричина/границы для каждого случая, безопасное воспроизведение, минимальное обоснованное исправление в whitelist либо честный PARTIAL/BLOCKED при неизвестной причине/выходе за scope, усиленные offline regression/negative controls.

## 2. READ MATRIX

Сначала: `Documents/07_Задачи Codex.md` §§1–3 и БЛОК1; `Documents/000_Задачи для агента.md` OWNER RULE, §§4,5.1,5.3–5.4; текущие NOW `Documents/00_Старт.md`, `Documents/05_Реестр_задач.md`, `Documents/13_Тактический_контекст.md`; `Documents/18_Техническая_документация.md` §§18.31,18.35–18.36. Изучить указанные два GitHub run с логами и доступные прошлые F4 evidence; если F4 evidence недоступен — SOURCE UNAVAILABLE, не домысливать.

Изучить `Client_Ultra_LLM/test_browser_control_stream.mjs`, `test_browser_slots_source.mjs`, `test_browser_stream_source.mjs`, `browser_qa_helpers.mjs`, `offline_stream_host.py`, `web_client.py`, `web_assets/client.js`, `.github/workflows/ultra-offline-ci.yml`. При необходимости **READ-ONLY** `Manager_Ultra_LLM/live_manager.py`, `control_runtime.py`, `chat_runtime.py`, `service_core.py`, соответствующие тесты, `Manager_Ultra_LLM/README.md`.

## 3. WRITE / TEST SCOPE — ТОЛЬКО whitelist

Допустимы минимальные локальные правки в следующих существующих файлах:
- `Client_Ultra_LLM/test_browser_control_stream.mjs`
- `Client_Ultra_LLM/test_browser_slots_source.mjs`
- `Client_Ultra_LLM/test_browser_stream_source.mjs`
- `Client_Ultra_LLM/browser_qa_helpers.mjs`
- `Client_Ultra_LLM/offline_stream_host.py`
- `Client_Ultra_LLM/web_client.py`
- `Client_Ultra_LLM/web_assets/client.js`
- `.github/workflows/ultra-offline-ci.yml` — только конечные offline диагностики/проверки без удаления прежних steps
- `Manager_Ultra_LLM/README.md` — append-only отчёт о TASK
- `Documents/07_Задачи Codex.md` — только штатная ротация после содержательной сдачи.

**Manager source/runtime, release/backup code, Production Client, любые другие документы и `Documents/.obsidian/**`, tracked screenshot `Client_Ultra_LLM/stream_slots_browser.png` — READ ONLY.** Если доказанная причина требует Manager code или расширенного write scope — остановиться с root-cause evidence и запросом отдельного OWNER AMENDMENT. Не создавать новые документы/узлы Obsidian, не добавлять зависимости. Временные артефакты хранить только локально в разрешённом ignored scratch/Test, затем очистить.

## 4. Запреты и границы прав

**Codex НИКОГДА не выполняет Git write**: `git add/commit/push/merge/rebase/reset/checkout/cherry-pick`, создание веток и изменения GitHub. Допустимы read-only `git status/diff/log/show`. Синхронизацию локального репозитория и один итоговый commit/push выполняет владелец; ChatGPT публикует документное назначение только в удалённую `GPT_2_local`, выполняет независимую приёмку после owner push. Перед началом проверить локальные source/HEAD после синхронизации ВЛАДЕЛЬЦЕМ; несовпадение — STOP, не чинить Git самостоятельно.

Никаких действий на рабочем Server Manager/UNC, real Colibri/Qwen/KAT/Valheim, CPU/CUDA START/STOP, Windows Tasks, Firewall, TLS, ACL, live API, release ZIP, backup, `Production/Client`, Client EXE, SAFE-CUTOVER C/D. Только synthetic loopback fixtures, временный Chrome профиль, никакие приватные ключи или пользовательские сообщения в evidence. **Manager R5 RELEASE HOLD**, F3 initial real backup provenance NOT PROVEN, exact ZIP CI NOT RUN.

Не допускать `catch{ return true }`, безусловных sleep как fix, отключения P1/legacy, бесконечных retries, умышленного PASS при `data=null`, удаления negative/security checks. Деградированное состояние должно приводить к bounded ожиданию с диагностикой либо честному FAIL, не false READY.

## 5. План и проверяемые результаты

1. **Baseline:** read-only git status/HEAD/diff, Chrome/Node/Python versions; точные шаги обоих run и исторические логи F4. Отдельные incident timelines.
2. **Диагностика:** безопасно логировать `fixture → Chrome cold page → /api/status → start → stop slot2 → poll/refresh/reload`; timestamps, HTTP status/error class, sanitized структуру `data`, latency/transition, JS/CDP/fixture exceptions; не публиковать raw snapshot, секреты или персональную историю. Найти точку происхождения `data=null` (Manager/Client/fixture/browser).
3. **Повторения:** минимум **10 чистых cold-start legacy** и **10 изолированных P1 STOP/status/reload cycles**, с реальным числом PASS/FAIL и контролем завершения Chrome/fixture и очистки временных данных. Если невозможно — явно сколько RUN, что BLOCKED. Добавить негативные инъекции `data:null`, частичный ответ, HTTP 503/connection failure, задержки, race `refresh()`/STOP; проверить длительность ожиданий и отсутствие false positive.
4. **Классификация:** для F4 и P1 отдельно `CONFIRMED / REPRODUCED / HYPOTHESIS / NOT RUN`. Не выдавать «flaky runner» за установленную причину. Если всё воспроизводится только через injection — назвать границу честно. По доказанному корню сделать **минимальный** diff в whitelist: bounded ожидания допустимого transient, строгий null/error guard, предсказуемый teardown, информативные ошибки на deadline, без ослабления assertions. Если требуется Manager backend — STOP/OWNER AMENDMENT.
5. **Тесты:** после изменений прогнать Chrome legacy, P0, P1, 10+ повторов, Python/JS syntax, имеющийся полный Manager suite (база 350 PASS/1 SKIP), Client suite (база 49 PASS), 5 negative controls; не выключать ни один тест. Проверить slot isolation, STOP только одного, сохранение истории, reload, отсутствие зависших процессов. Сохранить изначальный FAIL и сравнительные цифры.
6. **Отчёт:** append-only в существующий `Manager_Ultra_LLM/README.md`, секция TASK-ID; команды, даты/версии, run counts, PASS/FAIL/SKIP/NOT RUN, объяснение каждой правки и F4/P1 статус, ограничения, sanitized evidence. До owner commit **GitHub Windows CI NOT RUN** для нового source; не приписывать себе independent PASS.
7. **Ротация:** только после содержательной сдачи DONE/PARTIAL и проверки immutable хранения прежней F3 БЛОК1.1 в №60 `de6a96ba...` + №09; перенести весь оригинал БЛОК1 и AMENDMENT дословно в 1.1, освободить БЛОК1, оставить предыдущую F3 immutable. Если archive unverified — `ARCHIVE BLOCKED`, не очищать. При preflight STOP без результата не ротировать.

## 6. Acceptance и формат сдачи

Критерии: P1 и F4 не смешаны без доказательств; negative `data:null` и 503 не дают ложного READY; повторяемость и bounded fail-closed подтверждены; старые security guards F1/F2/F3 и P0/P1/legacy не ослаблены; точный whitelist соблюдён; старый RED сохранён. Если источник не найден — сдача PARTIAL с конкретным дальнейшим планом, не фиктивное DONE.

После публикации владельцем координатор независимо изучает diff, выполняет Windows GitHub CI на новом SHA и отдельно фиксирует AUTHOR/TECHNICAL/CI/REAL/OWNER UX/RELEASE. Offline тесты не являются реальным продуктом или разрешением на Manager R5 C/D; при изменении видимого UI нужен OWNER UX smoke.

**Ответ Codex:** `DONE / CHANGED / DIFF / TESTS / NEGATIVE CONTROLS / CI / PROBLEMS / QUESTIONS / DOC IMPACT / NEXT`; фактический статус, README evidence и результат ротации. Дальше остановиться для независимой приёмки.

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
