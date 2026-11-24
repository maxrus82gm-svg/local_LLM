# CODEX-UL-CHAT-LIVE-STATUS-20261124-001

Baseline: local HEAD #118 `39943ba4a5dda26f2f5a6575abdf2aac10c38858`, clean at preflight. Scope: local Client source, tests, existing documents. No LIVE/deploy/model lifecycle/Git write.

## DONE

**AUTHOR TESTED / REVIEW PENDING.** Компактный `aria-live=polite` индикатор стоит справа от «События чата» вне scroll. Зелёный READY требует свежего точного Manager/slot/model/instance snapshot и подтверждённой привязки. Поддержаны STARTING/STOPPING/STOPPED/ERROR/offline/unknown/pending/rebind, семь секунд stale timeout. Любой отказ status GET, включая прямой `readStatus()` из slot recheck, сразу инвалидирует зелёный. Restart показывает реальные стадии; после READY+complete+refresh+rebind ровно три секунды показывает «Перезапуск завершён», затем проверенный «Запущен». Отмена подтверждения не посылает Restart; неоднозначный сетевой результат остаётся unknown, без повторного POST. Один уже существующий poller при открытом чате использует 2 s cadence; обзор вне чата сохраняет 25 s.

## CHANGED / DIFF

- Client: `web_assets/index.html`, `client.css`, `client.js` — badge, строгая проверка снимка/identity, стадии и таймер; работающие Manager lifecycle/authorization/risk gates/история/stream не менялись.
- Tests: `test_browser_control_stream.mjs` — два Manager, реальные mock стадии, подтверждения, error/timeout, stale/offline/out-of-order, exact rebind, 3 s, cadence; `test_browser_stream_source.mjs` — ожидание фактического конца request и возврата фокуса вместо состояния кнопки «Стоп»; `test_browser_independent_chats.mjs` — status badge в откреплённом окне.
- Docs: №05, №07, №09, №13, №18 и этот отчёт. Предыдущий БЛОК 1.1 проверен по immutable #118 до ротации; БЛОК 4 оставлен координатору.

## TESTS

Все тесты в изолированной локальной SOURCE/synthetic среде. Task-local `TEMP/TMP`, профили Chrome и логи: `Test/CODEX-UL-CHAT-LIVE-STATUS-20261124-001/`. После финального исправления инвалидации status GET повторены все четыре Chrome сценария: PASS.

| Команда | Результат |
| --- | --- |
| `py -3.12 -B -m unittest discover -s Client_Ultra_LLM -p 'test_*.py' -q` | 84 total, 83 PASS, 1 SKIP, 0 FAIL/ERROR; повторный финальный прогон |
| `node Client_Ultra_LLM/test_browser_control_stream.mjs` | PASS; 12 сценариев, 2 GET за 4,3 s при открытом чате, console errors 0 |
| `node Client_Ultra_LLM/test_browser_stream_source.mjs` | PASS; Enter/Shift+Enter, stream/reasoning/cancel/metrics/focus |
| `node Client_Ultra_LLM/test_browser_independent_chats.mjs` | PASS; F5, два чата/история, narrow 780×620/110%, popout с индикатором, mouse resize |
| `node Client_Ultra_LLM/test_browser_slots_source.mjs` | PASS; SOURCE API/SQLite/TLS/Chrome, fake engines/resources, несколько одинаковых моделей |
| `node --check` для изменённых JS; `git diff --check` для task files | PASS |

Исходный тестовый FAIL: fixture включил `control_models` до legacy каталога, сломав старые ожидания; включение перенесено к Restart сценарию, повтор PASS. Stream regression сначала принимал доступную кнопку «Стоп» за конец ответа, затем проверял focus до окончания `waitForSlot`; ожидания усилены до фактического завершения request и восстановления фокуса, полный повтор PASS. Сырые логи сохранены только task-local, без публикации.

## PROBLEMS / QUESTIONS

Новых блокеров source QA нет. Неподтверждённый исход Restart при длительном сбое остаётся «Состояние неизвестно» до нового доверенного решения; автоматического повторного POST нет. Старый Manager без control identity показывает unknown. Hosted CI для этих новых байтов, новый LIVE индикатор и личная OWNER GUI-приёмка **NOT RUN**; предыдущий реальный Restart Qwen относится к старой установке.

## DOC IMPACT / NEXT

№05/09 фиксируют авторский результат, №13 сохраняет OPEN/NEXT, №18 описывает алгоритм, №07 ротирован по регламенту. Независимый review и точный hosted CI после owner publication, затем отдельный OWNER GO на Client rollout и GUI UX. HOME Manager/CUDA, третий Manager, multi-host и WUA LIVE остаются отдельными задачами. WorkEvidence: `Documents/Reports/CODEX-UL-CHAT-LIVE-STATUS-20261124-001/WorkEvidence/` (санитизированный манифест и summary); task-local retained files manifest в `Test/`. Cleanup pending до независимого ACCEPTED и явного OWNER cleanup.
