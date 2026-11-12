# CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001

13.11.2026, Asia/Yekaterinburg. **LIVE PASS — миграция Client R5 в единый workspace. Независимая приёмка: SUBMITTED / REVIEW PENDING.**

## DONE

Выполнен прямой OWNER GO на этап D. R5 установлена в `M:/GitHub/local_LLM/Production/Client`, все **73 файла** сверены с authoritative ZIP. Существующий ярлык переключён **однократно** на VBS новой папки. Client реально открыт через него в обычном видимом Chrome, а не только в headless QA.

Последний проверенный процесс — **PID 2580**, EXE `M:\GitHub\local_LLM\Production\Client\UltraLLMClient.exe`, creation UTC `2026-11-12T19:38:19.9296760Z`, listener **127.0.0.1:50783**. Программа оставлена работающей. Старый PID 29492 штатно завершён только после preflight и успешной функциональной репетиции rollback. Старый каталог `M:/UltraLLM_Client` и все backup сохранены.

Реальный **manager-server77 ONLINE**, три слота, две записи инвентаризации моделей, три строки каталога в UI. Сохранены **34 сообщения**, min/max id 1/34, schema 1, integrity_check=ok. SHA файла истории и aggregate SHA шести файлов профиля/секретов совпали до/после. Текст сообщений, токены и конфигурация в evidence не экспортировались.

Это LIVE PASS только домашнего Client deployment. **MANAGER VERSION GATE остаётся:** сервер не предоставляет stream v2/control.slots; реальные streaming/reasoning/dynamic slots/KAT/второй LLM не проверялись и не включались.

## CHANGED / DIFF

- Создан полный runtime `Production/Client` из byte-exact проверенного R5; не пересборка и не loose-копия Git с CRLF-отличиями.
- Исходный `.lnk` на Desktop изменён один раз: target `C:/Windows/System32/wscript.exe`, arguments `"M:\GitHub\local_LLM\Production\Client\Start_Ultra_LLM_Client.vbs"`, working directory `M:/GitHub/local_LLM/Production/Client`. Description/icon/hotkey/window style сохранены.
- Исходная конфигурация и байты ярлыка сохранены ещё раз внутри Backups; старые резервные копии не удалялись.
- В каталоге отчёта добавлены `stage_d.py`, `stage_d_lifecycle.py`, `stage_d_ui.mjs`, авторизация/metadata/evidence и screenshot. Предыдущий полный диагностический report/checks/checkpoint/manifest сохранён в `pre_stage_d`, SHA — `stage_d_originals.json`.
- Обновлены существующие report.md, checks.json, checkpoint.json, manifest и предусмотренный checkpoint карточки при сдаче. Независимый БЛОК 4 сохраняется побайтово.
- Client/Manager source и ZIP/backup не менялись; архивную .venv не использовали. Не создавались новые рабочие корни или ветки. Runtime/Test/Backups не должны попадать в Git.

## PREFLIGHT — ДО ЗАВЕРШЕНИЯ CLIENT

Подтверждены домашний **DESKTOP-SC96D3U** и единственный workspace `M:/GitHub/local_LLM`. Начальное Git-состояние чистое, ветка main, HEAD **d72bbb68be463f2410168d51cdea95bff988fe08**, коммит №44. Прежний 29492 подтверждён по owner, executable, creation `2026-11-12T12:49:36.6123520Z`, адресу/порту 127.0.0.1:60720. Нельзя подменять эту проверку kill по имени; глобального/принудительного kill не было.

`Production/Client` отсутствовал: неизвестных пользовательских файлов не было. Перед cutover прочитана реальная сводка, scheduler active/queued=0. Основной профиль находился в прежнем защищённом каталоге LOCALAPPDATA; он не переносился в репозиторий. Проверен read-only metadata snapshot и SQLite integrity.

### SHA / резервные копии

- ZIP: `Releases/Client/Imported_Packages_20261112/CODEX-UL-CLIENT-DEPLOY-20261112-001_20261112_173219/UltraLLM_Client_STREAM_SLOTS_R5_Win64.zip`.
- **ZIP SHA-256: `bc37f43f84263da8f42e006ab3e3833e85a3781bfb11858809882a51b34a9d8a`**.
- **EXE SHA-256: `7614aecc6f97a5a8c1b126b745aa7d17e9dc8679774ba870ee68f18690c649df`**.
- 72 payload hashes + SHA256SUMS = **73/73** в QA, полном backup и Production.
- `Backups/Client/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/Installed_Original_68_files`: **68/68** к фактическому исходному каталогу.
- Там же `Rollback_R5_Complete`: **73/73**, полный запускаемый R5 с VBS. Исходная partial-установка имеет только 68 файлов и не содержит пяти root-файлов, включая VBS; она не объявляется рабочим rollback.
- SHA исходного ярлыка **658e88888c9bb28791c038c71ce56fcb1e14af35280d47a4f859321cc57ae070**; SHA нового **71d3d17a96a0afce724683ed6cc4cd148e25463c011ba927b65c56c282669e3d**. Точный новый дополнительный backup `.lnk` — `stage_d_shortcut_backup.json`.
- SHA истории до и после: **6e38fdfcbe1f17159ea3be2349557d2c06009d73b96d611a41e9f9266d3ea3aa**. Это opaque checksum, содержимое переписки не публикуется.

## ROLLBACK — ПОДГОТОВЛЕН И ФУНКЦИОНАЛЬНО ПРОВЕРЕН ДО CUTOVER

Один и тот же `recovery()` в stage_d.py используется для репетиции и аварийного возврата. На изолированном synthetic AppData и QA `.lnk` выполнено:

1. Запуск sandbox Client из тестового ярлыка.
2. Штатное закрытие только его подтверждённого PID 32140.
3. Переназначение **тестового**, а не Desktop ярлыка на полный `Rollback_R5_Complete/Start_Ultra_LLM_Client.vbs`.
4. Реальный запуск backup Client PID 24956 через QA ярлык; configured=false/managers=[], HTTP и точный JS hash PASS.
5. Штатное закрытие QA backup. Старый PID 29492 и Desktop .lnk остались неизменны.
6. Backup EXE с настоящим существующим профилем и `--no-browser`: exit **0**, корректное присоединение к уже работающему single-instance без остановки/смены его PID. Подтверждены profile/secret/history checksums до/после.

Репетиция завершилась **PASS до shutdown старого Client**; полный backup был повторно хеширован. Это проверка работоспособного возврата к полному R5 внутри workspace, не попытка запускать отсутствующий старый VBS. Полный runtime остаётся доступным для recovery.

В рабочем cutover исключение автоматически вызывает только этот проверенный recovery: остановить только проверенный собственный новый Client, направить тот же Desktop .lnk на полный workspace backup и запустить с прежним профилем. Неизвестные/конкурирующие процессы не убиваются, файлы Production и личные данные не удаляются и не откатываются. Байт-в-байт восстановление старого `.lnk` сохранено для forensic, но не является функциональным путём возврата, поскольку старый VBS отсутствует.

**На рабочей установке rollback не потребовался и не выполнялся.** Нельзя выдавать QA-репетицию за реальный аварийный возврат с настоящим профилем. Он подготовлен и испытан в названных границах. Сбой диска/ОС или последующее стороннее удаление backup не могут гарантироваться программой; при потере verified backup recovery отказывает до рискованных действий.

## STAGE D / LIVE TESTS

| Проверка | Результат |
|---|---|
| Home host, PID/path/creation/owner/port | PASS |
| ZIP, source QA, оба runtime backup, `.lnk` backup | PASS |
| Target до установки | отсутствует, неизвестных файлов 0 |
| Функциональная репетиция rollback | PASS |
| Штатное завершение исходного 29492 | PASS, только локальный CSRF shutdown |
| Production hash set | **73/73 PASS** |
| Desktop `.lnk` | однократное переключение, конфигурация проверена |
| Первый Production Client | PID 25856 / 127.0.0.1:55627, обычный Chrome |
| Два повторных запуска `.lnk` | тот же PID/creation/port; Client count=1 |
| Штатное завершение нового Client | **actual exit code 0** через retained process handle |
| Повторный запуск через тот же `.lnk` | PID 2580 / 127.0.0.1:50783, один Client |
| Manager и каталог | ONLINE, 3 слота, 2 disk entries, 3 DOM rows |
| History/profile | **34 сообщения; полный DB SHA и 6-file aggregate совпали** |
| Browser runtime | **0 JavaScript errors** в завершающей реальной DOM-проверке |
| Старые файлы/backup | сохранены и повторно сверены |
| Server mutation / LLM START/STOP / inference | **NOT RUN / 0 действий** |
| Production rollback | NOT NEEDED / NOT RUN |

`stage_d_native_chrome.json` и computer-use наблюдение подтверждают обычный видимый Chrome, открытый VBS после запуска рабочего .lnk. `stage_d_ui.json` и `stage_d_live_overview.png` получены отдельным headless Chrome из **реального Production Client / настоящего Manager**, не из fake fixture. На screenshot только overview; чаты и личная история не открывались для экспорта. Метаданные истории читались напрямую SQLite в режиме read-only, без SELECT content.

Старая серверная версия распознана корректно: все реальные START CPU/CUDA/STOP disabled, stream v2 и dynamic slots false. Новые функции не имитировались. Проверенный TLS и прежние credentials сохранены, новых прав/токенов не создавали.

## COMMANDS / EVIDENCE

```text
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/stage_d.py --prepare
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/stage_d.py --execute
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/stage_d_lifecycle.py
node Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/stage_d_ui.mjs
```

Не повторять mutation-команды без нового scope: --execute требует всё ещё работающий исходный PID и не является updater для повторной установки. Реальный POST разрешён только для подтверждённого loopback Client `/api/shutdown`; Manager/model POST в этих скриптах отсутствует.

- `stage_d_result.json`: итог LIVE PASS, source/runtime paths, SHA, old/final identities, проверенные ограничения.
- `stage_d_preflight.json`: snapshot до старого shutdown, file map 73, backup/meta/профиль.
- `stage_d_rollback_rehearsal.json`: результаты функционального recovery QA.
- `stage_d_transaction.json`: временные события cutover и единственное изменение Desktop .lnk.
- `stage_d_lifecycle.json`: два повтора, exit 0, restart, проверка профиля/истории/Manager.
- `stage_d_ui.json`, PNG и native Chrome metadata: реальный UI.
- `stage_d_prepare_failures.json`, `stage_d_ui_attempts.json`: отрицательные результаты harness, сохранены без сокрытия.
- `manifest.json`: хеши текущих и сохранённых evidence. Test/Backups/Production runtime не включаются в Git.

## PROBLEMS / ОГРАНИЧЕНИЯ

1. В первом **тестовом** ярлыке репетиции мной был неверно рассчитан путь WScript (`Windows/wscript.exe` вместо `Windows/System32/wscript.exe`). Start-Process отказал до запуска sandbox. Ошибка исправлена в harness, добавлена проверка существования системного файла. Desktop .lnk и исходный Client до успешного повтора не трогались; отрицательный результат сохранён.
2. Первая headless UI-проба прочла `chatSnapshot` раньше загрузки JS и получила ReferenceError от самого диагностического выражения. Добавлен `typeof` guard; повторный итоговый DOM прогон PASS/0 errors. Это не исключение приложения и не повод выполнять rollback исправно работающего Client.
3. Browser connector к Chrome отсутствует; обычное видимое окно подтверждено native Windows skill, отдельный DOM test использует существующий Chrome QA helper. Настройки браузера/безопасности не менялись.
4. Из AMENDMENT 01 сохранён child-only сброс `PSMODULEPATH` в launch harness; это не изменение system/user env. Binary Client не менялся и не пересобирался.
5. Actual server streaming/reasoning/slots/другая LLM по-прежнему **MANAGER VERSION GATE / NOT RUN**, вне этой задачи. Вторая физическая машина также NOT RUN.
6. Independent verdict остаётся REVIEW PENDING. Сохранён полный предыдущий диагностический report и исходный FAIL exit=1, не заменён фиктивным PASS.

Дополнительная проверка launcher после lifecycle: существующий Desktop .lnk выполнен с ожиданием WScript, **exit 0**, тот же production PID 2580, профиль/ярлык неизменны (`stage_d_launcher_exit.json`). Старые вкладки после смены ephemeral порта могут сохранять прежний адрес 55627 и Failed to fetch; их не удаляли. В существующем обычном Chrome затем подтверждён текущий **50783** и ONLINE Server 77 (`stage_d_native_chrome.json`, after_restart).

Попытка дополнительного нового окна Chrome через CLI была отклонена автоматической проверкой: `blocked by policy`. Запуск не выполнялся, ограничение не обходилось; вместо этого проверено уже открытое окно браузера на правильном адресе. Это не отказ установленного Client и не повод откатывать успешную миграцию.

Проверка diff: raw `git diff --check` отмечает исходные Markdown hardbreak/trailing spaces в дословно восстановленных TASK/AMENDMENT. Их не удаляли ради сохранения оригинала. Check кода/отчёта PASS; однократный Markdown-check с `-c core.whitespace=-blank-at-eol` PASS без изменения Git settings. Подробности `stage_d_format_checks.json`.

## GIT / QUESTIONS

На старте main №44, других допустимых локальных веток нет: только запрещённая для этой работы GPT_2_local. Порядок публикации единственного итогового коммита **не согласован**. Поэтому промежуточных/итоговых commits, push/merge/rebase, новых веток и изменений refs main/GPT_2_local не выполнялось. Все безопасные изменения подготовлены в рабочем дереве для review. Следующий сквозной номер по текущему локальному журналу — 45, но он не присваивается без решения владельца и повторной сверки HEAD.

Для единственного итогового коммита требуется определить разрешённую ветку/порядок. Это единственный организационный OPEN; он не превращает подтверждённый Client LIVE PASS в разрешение писать main. Ветка GPT_2_local не используется. Runtime/QA profiles/backup/ZIP/history/secrets не должны попасть в индекс.

## DOC IMPACT / NEXT

Ротация своей карточки №07 выполнена: БЛОК 1 свободен, 1.1 содержит полный оригинал Root TASK из Git 3121066, AMENDMENT 01 и дословный OWNER GO. Предыдущая полная CLIENT-DEPLOY TASK сверена с immutable bad9835e8753dad1498a568627a8f6b000e0d3f9, зарегистрированным в №05. БЛОК 2 — пять кратких ID, БЛОК 3 — действующие OPEN. Независимый БЛОК 4 побайтово не изменился. Доказательство — stage_d_rotation.json. Координатору обновить №00/05/09/13/18: постоянный Client теперь **Production/Client**, старый каталог сохранён; operational rollback — полный workspace R5 backup; новое состояние ярлыка и LIVE metadata подтверждены. Предыдущий Stage C blocker закрыт; server Manager gate остаётся OPEN.

**Остановиться на независимой приёмке и согласовании одного финального коммита. Не обновлять Manager, не запускать вторую LLM.**
