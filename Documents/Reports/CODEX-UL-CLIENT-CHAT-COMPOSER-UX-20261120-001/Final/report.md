# CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001 — авторский отчёт

Baseline: №84 `a712c17ce96158e328d89fa65c5e56a057cee477`. Только локальные исходники Client и документы. Manager, модели, Production и Git write не затрагиваются.

## Контрольная точка P1 — PASS

- Реализовано: ввод, выбор модели, поток, параметры, reasoning, измерения и статус объединены в фиксированную нижнюю панель. Поле ввода регулируется по вертикали; панель резервирует высоту в переписке и ограничена высотой viewport.
- Изменены: `Client_Ultra_LLM/web_assets/index.html`, `Client_Ultra_LLM/web_assets/client.css`; этот отчёт и №13.
- Тесты: `node --check` JS и browser test PASS; `test_browser_independent_chats.mjs` Chrome/SOURCE Client/TLS SOURCE Manager/synthetic Colibri PASS (28.09 с), включая одну прокрутку, 780×620, историю/F5, streaming/cancel/reasoning, метрики. `git diff --check` отметил только ранее существовавшие пробелы Markdown в незакоммиченной постановке №07.
- Не завершено: зависимые Manager/модель, карточки чатов, расширенный scroll UX и полная матрица P5.
- Следующее действие: P2 — заменить `#chat-target` двумя зависимыми списками Manager/модель и проверить сохранение назначения после F5.

Статус: **IN PROGRESS**. LIVE/Production не запускались; браузерный тест использовал синтетический Colibri.

## Контрольная точка P2 — PASS

- Реализовано: нижние зависимые списки Manager/модель. Подписи KAT-Coder V2.5 Dev и Qwen 3.6; при одинаковых моделях показываются слот и подтверждённый CPU/CUDA. Служебный instance_id остаётся только во внутренней маршрутизации. Выбор Manager без модели не меняет назначение и блокирует отправку до явного выбора; черновой выбор Manager переживает F5 через sessionStorage. Недоступное назначение сохраняется и отображается как недоступное.
- Исправлен выявленный Chrome defect: изменение геометрии панели ошибочно принималось за ручную прокрутку и отключало автоследование. Теперь намерение прокрутки определяется по пользовательскому вводу. Тест симулирует wheel перед scroll.
- Изменены: `web_assets/index.html`, `client.js`, `client.css`; `test_browser_independent_chats.mjs`, `test_browser_control_stream.mjs`, `test_browser_slots_source.mjs`; отчёт и №13.
- Тесты: `node --check` PASS; после исправления Chrome independent chats PASS (27.52 с), Chrome control stream PASS, Chrome SOURCE API/SQLite/TLS slots PASS (5 слотов, CPU×2/CUDA×2 на fake engines, два чата, F5, сохранение истории). Первый Chrome independent chats FAIL из-за обнаруженного ложного отключения автоследования; повторный полный прогон PASS.
- Не завершено: P3–P5, дополнительная матрица двух Manager с одинаковыми model_id в одном UI и ручная проверка ресайза поля.
- Следующее действие: P3 — удалить верхнее меню действий, добавить шесть SVG-кнопок на каждую карточку и передавать её chat_id в мутации.

## Контрольная точка P3 — PASS

- Реализовано: верхний блок «Управление чатом» удалён. Каждая карточка содержит четыре основные и две отдельно сгруппированные SVG-пиктограммы с русскими `title` и `aria-label`. Восстановление приглушено при отсутствии возможности. Мутация принимает `chat_id` карточки; действия на неактивном чате не переключают активный. Запрос чата во время генерации и глобальная мутация блокируют операции; подтверждения clear/delete сохранены.
- Изменены: `web_assets/index.html`, `client.js`, `client.css`, `test_browser_independent_chats.mjs`, отчёт, №13.
- Тесты: `node --check` PASS; Chrome independent chats повторно PASS (28.11 с). Дополнительно проверены rename/reset/resume/clear/restore/delete на карточке неактивного чата и неизменность активного `chat_id`, подтверждение clear/delete, история и метрики.
- Не завершено: P4–P5.
- Следующее действие: P4 — сделать автопереход к последнему сообщению после открытия/F5 устойчивым к асинхронной загрузке и ресайзу панели, затем проверить ручную прокрутку.

## Контрольная точка P4 — PASS

- Реализовано: переход к абсолютному низу основной страницы при открытии и догрузке истории; ResizeObserver истории отслеживает изменение высоты. Ручная прокрутка вверх по wheel/touch/keyboard/scrollbar не перебивается потоком; изменение геометрии само по себе не считается ручным вводом. Последнее сообщение не закрывается закреплённой панелью.
- Изменены: `web_assets/client.js`, `test_browser_independent_chats.mjs`, отчёт и №13.
- Тесты: Chrome independent chats PASS два последовательных прогона (27.82 с и 29.97 с): F5 и переключение обоих чатов доводят главный scrollbar до низа; 780×620 и 110% сохраняют одну прокрутку; увеличение textarea до 200 px сохраняет composer внизу и видимость истории; ручное чтение вверх, streaming reasoning/answer и кнопка возврата прошли.
- Не завершено: P5 — полная regression/матрица и техническая документация.
- Следующее действие: P5 — добавить сценарий двух Manager с одинаковыми моделями, проверить popout и все заявленные размеры/масштаб, прогнать unit/API/JS/Chrome regression, затем оформить evidence и документацию.

## Контрольная точка P5 — IN PROGRESS

- Реализовано: synthetic Chrome fixture содержит два Manager с одинаковым model_id и два чата с разным назначением. Проверены зависимые списки, явная смена Manager/модели, отсутствие автоматического переназначения и F5. Отдельный CDP popup действительно открывает тот же chat_id.
- Изменены: `test_browser_control_stream.mjs`, `test_browser_independent_chats.mjs`, `browser_qa_helpers.mjs`; отчёт и №13.
- Тесты: Python Client unittest 58/58 PASS; Chrome two Manager/control stream PASS; Chrome independent chats/popout PASS (28.61 с). Первоначальная проверка popout через программный `.click()` была заблокирована popup blocker; CDP mouse event с пользовательской активацией PASS. Это ограничение тестового метода, не Client.
- Не завершено: остальные JS/Chrome regression, финальная проверка размеров/масштаба, статические проверки, №18 и WorkEvidence.
- Следующее действие: прогнать оставшиеся браузерные тесты с task-local логами, проверить HTML/JS/CSS и составить итоговый манифест evidence.

## NOW 20.11.2026 - CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001 / COORDINATOR P5 RESUME

Owner published partial Codex commit 85 fbc16a66ea9515523a5756f1028937481d1618f1; local HEAD verified. P1-P4 implemented, P5 resumed from recorded checkpoint. Independent review found duplicate display names caused by unique runtime model IDs, and form submit not enforcing pending Manager selection. Local Client JS corrected: display duplicates distinguished by slot/mode; all configured Manager choices including idle, empty draft retained; send guard checks pending Manager. Extended fake API Chrome test covers distinct runtime IDs, idle Manager, direct submit rejection and F5. Independent unit 58/58, syntax 6/6, Chrome control stream and independent chats PASS. Initial PowerShell harness stopped on unittest stderr, rerun via Python with captured stdout/stderr and exit codes. NEXT: remaining Chrome suites, final evidence and technical docs; no Git write, no production or Manager changes. QA: Test/CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001/coordinator-final85/.

## NOW 20.11.2026 - CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001 / P5 LOCAL QA PASS

Codex partial publication: 85 fbc16a66ea9515523a5756f1028937481d1618f1. Coordinator resumed P5 and corrected display-name collisions (same model, different generated model_id), Manager list including idle/offline, explicit blank draft persistence, and direct submit guard during pending Manager selection. Client source and test_browser_control_stream.mjs changed; no model/Manager/Production changes. Full final local regression: Python Client 58/58, JS syntax 6/6, Chrome 4/4 (control_stream, independent_chats, slots_source, stream_source), all exit 0; static HTML unique IDs, relocated controls and removal of old menu PASS. Actual running Client HTTP assets /, /client.js, /client.css byte-identical to final working sources; F5 sufficient for OWNER UX. No real inference/destructive user test or current hosted CI on unpublished fixes; source QA only, independent review of coordinator edits and OWNER UX pending. Evidence: Reports/CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001/WorkEvidence/coordinator-qa-summary.json; Test/CODEX-UL-CLIENT-CHAT-COMPOSER-UX-20261120-001/coordinator-final85/retained_manifest.json. NEXT: owner visual smoke (F5, two model selectors, compact icons, textarea resize, opening/switching chat and manual scroll); owner publication of remaining correction/doc package; CI on exact new SHA. No Git write; cleanup pending acceptance.
