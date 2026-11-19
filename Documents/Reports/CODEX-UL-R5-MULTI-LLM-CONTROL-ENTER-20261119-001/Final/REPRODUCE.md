# Воспроизведение локального QA

Исходная точка — №79 `9023f3fdf485a120d05b2d4554612fa655a679f0`. Сверить публикуемый patch и нормализованные SHA в [source-pins.json](source-pins.json). Доказательства относятся к Windows x64, Python 3.12.10, Node 22.20.0, Chrome 157.0.8103.79, PowerShell 7.6.9 и Windows PowerShell 5.1 для ACL. Источники сверены с байтами тестовой копии до запуска. Запуски под Windows hosted CI выполняются независимо на опубликованном SHA.

1. Для свежего прогона создать новый подкаталог в `Test/<TASK-ID>/scratch/`. Сверить разрешённый корень и отсутствие reparse points в компонентах пути. В копию перенести отслеживаемые открытые файлы `Client_Ultra_LLM/` и `Manager_Ultra_LLM/` с расширениями исходников, тестов и assets. Сохранить имена обоих соседних подкаталогов. Направить TEMP/TMP/LOCALAPPDATA/APPDATA текущего процесса в новые подкаталоги scratch; выставить PYTHONDONTWRITEBYTECODE и PYTHONUTF8. Chrome тесты поддерживают отдельные профили. Оригинал executable и Production профили не требуются.
2. Для существующего Gate 2 harness в тестовой копии создать `Test/` для результатов и скопировать три открытых фикстуры из `Documents/Reports/CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001/` в ту же относительную папку копии. Используются `stage_b_complete_readonly.py`, `stage_b_server_preflight_v3.ps1` и `stage_b_prepare_server.py`. Тесты используют их как synthetic fixture и статический текст. Работать из корня копии, для каждого QA выбрать новую папку результата. Команды:

```powershell
py -3.12 -B Manager_Ultra_LLM/test_gate2_hardening.py --suite Manager_Ultra_LLM --minimum 330 --output Test/qa-manager/result.json
py -3.12 -B Manager_Ultra_LLM/test_gate2_hardening.py --suite Client_Ultra_LLM --minimum 50 --output Test/qa-client/result.json
py -3.12 -B Manager_Ultra_LLM/test_gate2_hardening.py --negative-controls --output Test/qa-controls/result.json
node --check Client_Ultra_LLM/web_assets/client.js
node Client_Ultra_LLM/test_browser_control_stream.mjs
node Client_Ultra_LLM/test_browser_stream_source.mjs
node Client_Ultra_LLM/test_browser_slots_source.mjs
```

3. Для проверки чувствительности на №79 в новой временной копии оставить старый `client.js` и запустить обновлённый P0 Chrome тест. Он падает при первом Enter на пробельном черновике. Со старым `control_runtime.py` запустить два новых метода `AdmissionTests` в `test_control_runtime.py`. Оба должны падать на проверках принятия преждевременного STOP и перезаписи STOPPING. Эти RED входят в evidence, включая реальные exit codes.
4. Собрать portable через существующий `Client_Ultra_LLM/Build-Portable.ps1 -BuilderPython <task-local-python.exe> -OutputRoot <task-local-build> -ReleaseName <new-unique-name>`. Python 3.12 x64, PyInstaller 6.16.0, Process TEMP/TMP и PYINSTALLER_CONFIG_DIR в scratch. Хэши wheelhouse и сборки находятся в WorkEvidence до очистки. Сверить все 72 SHA payload и количество 73 файлов, JS в `_internal/web_assets` сопоставить с исходником. Пересборка может дать другой ZIP SHA, поэтому SHA в отчёте относится к сохранённому `_002`.
5. Для изолированного EXE QA использовать [portable-bootstrap.mjs](../WorkEvidence/portable-bootstrap.mjs) в копии рядом с браузерным тестом. Тестовый P0 использует тот же Manager/Colibri fixture. После `await ready` вызывается `bootstrapPortable(root)`, `host.url` заменяется на возвращённый локальный URL. В секции `finally` закрываются Chrome и EXE, затем fixture. Передать `UL_QA_TASK_ROOT`, `UL_QA_PORTABLE_EXE` и пустой task-local `LOCALAPPDATA`. Вспомогательный код принимает только candidate EXE из `build/Client` задачи, проверяет выход дубля и проверяет аутентифицированный фиктивный Manager. Реальный системный буфер обмена не используется, вставка текста проверяется через CDP.

Для независимой приёмки нужны новый Windows CI run ID и проверка diff владельца на том же SHA. Представленные локальные тесты уже завершены. На сервере допуск для реальной генерации выдаёт владелец на отдельный точный путь. Старые и новые диагностические запуски относятся к одной задаче.
