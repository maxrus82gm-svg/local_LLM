# CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001

12.11.2026. Codex. **BLOCKED / этап C: изолированный packaged Client завершился до HTTP-ready.** Миграция остановлена согласно §6 постановки. OWNER GO не получен и пока не запрашивается: контрольная точка A–C ещё не пройдена. Действующий Client не закрыт, ярлык не изменён, Production не создан. Самопроверка не является независимой приёмкой.

## DONE

Подтверждён домашний компьютер `DESKTOP-SC96D3U`, пользователь `DESKTOP-SC96D3U\REX`. Единственный workspace — `M:\GitHub\local_LLM`. Сверены актуальные локальные №00/000/07/13, FOLLOWUP-UL-ROOT-MIGRATION-20261112-001 в №05, №18 §§18.26–18.27, прежняя R5 TASK в БЛОКЕ 1.1 и перенесённые REPORT/INSTALL/LIFECYCLE/PORTABILITY. Первоначально открытая по прежнему UNC-пути карточка была исторической, её БЛОК 1 WAITING; источником назначения использована актуальная локальная карточка. Серверные runtime не исследовались и не изменялись.

Git HEAD: `03d1cd961fd9ec8216d5281f36bd1b771c43f44b`, текущая ветка `main`. До начала уже изменены `Documents/07_Задачи Codex.md` (назначение владельца) и `Documents/.obsidian/workspace.json`; они не перезаписывались. Новые branch/worktree/clone не создавались. Коммит, push, merge не выполнялись. Задача не завершена; промежуточный коммит запрещён. Номер и место единственного итогового коммита необходимо согласовать с владельцем после успешного продолжения; чужая GPT_2_local не использовалась.

## CHANGED / DIFF

Созданы новые материалы внутри workspace:

- `Backups/Client/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/Installed_Original_68_files` — точная копия фактического старого каталога, **68/68 SHA совпали**.
- Там же `Rollback_R5_Complete` — полный проверенный R5 из ZIP, **73/73 файла с manifest совпали**; копии исходного `.lnk`, карточки №07 и manifest backup.
- `Test/ClientMigration_20261112/R5` — изолированно распакованный ZIP, **73/73 SHA совпали**; отдельные synthetic AppData и Temp. Историческую опубликованную .venv не запускали.
- Данный каталог отчёта: inventory/checks/checkpoint, скрипт воспроизведения изолированной проверки и stdout/stderr 49 тестов.

В своей карточке №07 добавлен factual BLOCKED checkpoint в БЛОК 2; БЛОКИ 1/1.1/4 побайтово сохранены. Исходники Client/Manager, общие нормативные документы, старые установки и действующий ярлык не редактировались. Корневой `.gitignore` уже исключает новые `/Backups/`, `/Test/`, `/Production/`, `/Releases/`; изменения не потребовались. Это не исключает старые tracked артефакты из истории, их privacy cleanup здесь не выполнялся. Отчёт не содержит приватной переписки, Manager credentials или экспортов профиля.

## Инвентаризация и SHA

Постоянная цель: `M:\GitHub\local_LLM\Production\Client` — **отсутствует / не установлено**.

Работающий Client: PID **29492**, parent 27244, EXE `M:\UltraLLM_Client\UltraLLMClient.exe`, creation `2026-11-12T12:49:36.612352Z`, loopback-порт **60720**. После тестов остался только этот исходный Client с тем же PID/path/creation. Его завершение не запрашивалось. Миграция не переносит уже загруженный процесс простым копированием файлов.

Ярлык `C:\Users\REX\Desktop\Ultra LLM Client.lnk` указывает на `C:\Windows\System32\wscript.exe`, arguments `"M:\UltraLLM_Client\Start_Ultra_LLM_Client.vbs"`, working directory `M:\UltraLLM_Client`. Его SHA-256 **658e88888c9bb28791c038c71ce56fcb1e14af35280d47a4f859321cc57ae070**, до/после и в backup совпал.

**Расхождение:** старый каталог содержит лишь EXE + `_internal`, 68 файлов. Все имеющиеся файлы совпадают с оригинальным R5. Отсутствуют пять root-файлов: `Start_Ultra_LLM_Client.vbs`, `Install_Ultra_LLM_Client.vbs`, `PORTABLE_README.txt`, `PYTHON_LICENSE.txt`, `SHA256SUMS.txt`. Таким образом, действующий процесс продолжает работать, но повторный запуск по нынешнему ярлыку нельзя считать исправным: его VBS-target отсутствует. Не пытались нажимать ярлык или восстанавливать внешний каталог. `M:\UltraLLM_Builds` отсутствует. Это отличается от прежнего отчёта о полной установке.

R5 ZIP:

`Releases/Client/Imported_Packages_20261112/CODEX-UL-CLIENT-DEPLOY-20261112-001_20261112_173219/UltraLLM_Client_STREAM_SLOTS_R5_Win64.zip`

SHA-256: **bc37f43f84263da8f42e006ab3e3833e85a3781bfb11858809882a51b34a9d8a** — совпал с постановкой. Все **72 payload hashes** внутри ZIP проверены; с manifest всего 73 файла. Source SHA `132474781e760e463944c76efcd9d3ff192e8f18` взят из R5 deploy evidence, а не из вымышленной embedded FileVersion: у EXE такой версии нет.

Отдельная распакованная копия выпуска в Releases имеет четыре raw SHA mismatch: PYTHON_LICENSE и три web-assets. Проверка показала равенство **только после CRLF→LF нормализации**. Первоначальная строгая проверка этой копии дала AssertionError; её отвергли как byte-exact источник. Копирование для QA/полного rollback выполнялось исключительно из исходного ZIP с правильным SHA, не из нормализованной Git-копии. Сама распакованная копия не исправлялась.

## TESTS / EVIDENCE

Команда: `py -3.12 -B -X utf8 Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/isolated_checks.py` из единственного workspace.

1. **PASS:** текущая/backup установка 68 SHA; ZIP 72 payload; QA и полный rollback по 73 SHA; исходный ярлык/backup совпали. После проверки старые файлы повторно сверены и неизменны.
2. **PASS:** все **49 Client unit tests**, 0 failures/errors, 16.819 s. `PYTHONDONTWRITEBYTECODE=1`; LOCALAPPDATA, TEMP, TMP, TMPDIR направлены в `Test/ClientMigration_20261112`. Логи `unittest.stdout.txt`, `unittest.stderr.txt`. Архивное окружение сборки не использовалось.
3. **FAIL:** frozen EXE запущен с `--no-browser` из QA/R5 с отдельным LOCALAPPDATA, но завершился до HTTP-ready. Harness остановился на строке 45: `AssertionError: Packaged client exited before ready`. Точный exit code EXE первоначальный harness не сохранил; причина **UNRESOLVED**, не объявляется доказанным дефектом сборки или GUI. Повторный запуск, изменение ACL/окружения/сборки после отказа не проводились: соблюдён stop-on-error этапа C. Единственный QA EXE уже завершился, оставшихся QA Client нет.
4. **NOT RUN / не достигнуты:** packaged HTTP/UI assets, два повтора EXE, shutdown/reopen, визуальный browser/VBS, установка в Production, изменение ярлыка, real Manager ONLINE/catalogue, подтверждение 34 сообщений по метаданным после миграции. Наличие 34 сообщений известно только из предыдущего отчёта и сейчас не проверялось. Содержимое настоящей истории/секретов не открывалось и не копировалось.
5. **NOT RUN:** серверные START/STOP, Manager deploy, модели, streaming benchmark, firewall/TLS/службы/Valheim. Действующий Client оставлен работать с прежним профилем; глобальная неизменность сервера не объявляется независимо измеренной, агент серверных runtime-команд не выполнял.

`inventory.json` содержит безопасные file hashes и карту путей. `checks.json` — итоговые проверки и только безопасные process metadata. `checkpoint.json` — точный статус продолжения. Manifest рядом фиксирует SHA отчётных файлов. Тестовые synthetic профили и бинарные backup в Git не добавлялись.

## PROBLEMS / QUESTIONS

Блокер — неуспешный изолированный запуск того же verified ZIP. Требуется отдельная адресная диагностика раннего завершения с сохранением exit code/безопасных локальных QA diagnostics. Причина пока неизвестна; запуск исходников 49/49 не доказывает работоспособности frozen EXE в новом месте. Новая сборка без отдельного изменения scope не допускается.

Второй риск — отсутствующий VBS старой установки. Rollback через простое восстановление исходного ярлыка недостаточен. За пределами workspace восстанавливать старый каталог запрещено; перед переключением необходимо утвердить проверенный rollback через **полный backup R5 внутри workspace**, с прежним защищённым пользовательским профилем. Его фактический запуск ещё не проверен, поэтому безопасный operational rollback пока **NOT VERIFIED**.

## План после устранения блокера — пока НЕ ВЫПОЛНЯТЬ

Сначала добиться успешного отдельного QA startup/HTTP/UI/repeat/shutdown, подтвердить полный runtime и путь загрузки bundled Python. Затем представить владельцу новый checkpoint и точный OWNER GO. Только после него: перепроверить PID/path/creation/порт исходного Client, штатно закрыть именно его через защищённый loopback shutdown; установить byte-exact ZIP payload в Production; проверить 73 SHA; один раз сохранить изменение существующего ярлыка на относительный VBS в Production; проверить один процесс, Manager ONLINE/catalogue, метаданные истории и два повтора/закрытие/повторный запуск. Модели и сервер не переключать.

При разрешённом rollback: закрыть только подтверждённый новый Client; сохранить неуспешную Production-папку внутри workspace; по отдельно согласованному плану перенаправить существующий ярлык на VBS **проверенного полного backup** внутри workspace и проверить единственный процесс с прежним защищённым профилем. Не записывать ничего в старый `M:\UltraLLM_Client`, не удалять его и не заявлять заранее, что он самостоятельно восстанавливается.

## DOC IMPACT для координатора

- №13: NOW — домашний ПК подтверждён, A/B завершены с расхождениями, C BLOCKED, старый PID/ярлык не изменены; причина frozen startup UNRESOLVED.
- №05: FOLLOWUP-UL-ROOT-MIGRATION остаётся OPEN/BLOCKED, Production NOT DEPLOYED.
- №09: сохранить этот TASK, hashes, 49 source PASS и packaged startup FAIL отдельно от предыдущего R5 LIVE evidence.
- №06: нового решения владельца не было; потребуется запись, если изменится согласованный rollback или объём диагностики.
- №18: добавить фактическое отсутствие пяти root-файлов старой установки, authoritative ZIP и расположение verified backup/QA; runtime нового пути ещё не подтверждён.
- №00: постоянная установка ещё не изменена; не объявлять Production рабочим.

Нормативные документы обновляет координатор после независимой проверки. БЛОК 4 не изменён; текущая TASK не ротирована и остаётся активной для продолжения. Итоговый commit отсутствует, промежуточных commit нет.

## NEXT

**BLOCKED.** Передать пакет независимой проверке и согласовать узкую диагностику раннего выхода packaged EXE в изолированном QA. До её PASS запрещены stop действующего Client, переключение ярлыка и объявление STAGED/OWNER-GO-ready. Все новые материалы остаются внутри `M:\GitHub\local_LLM`, backup сохранён.
