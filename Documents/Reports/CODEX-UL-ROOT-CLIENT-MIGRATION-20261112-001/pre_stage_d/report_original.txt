# CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001

## AMENDMENT 01 — диагностический checkpoint

Отчёт актуализирован 13.11.2026 (Asia/Yekaterinburg); исходные TASK и AMENDMENT от 12.11.2026. Время запусков сохранено с UTC offset.

**STAGED / OWNER GO REQUIRED. Stage C — PASS в изолированном QA. Stage D — NOT RUN.**

Причина преждевременного выхода доказательно локализована в окружении диагностического harness, без изменения Client или сборки. Контролируемое воспроизведение завершилось с **exit code 1 (`0x00000001`)**. После удаления только унаследованного `PSMODULEPATH` из окружения дочерних QA-процессов тот же проверенный EXE прошёл два цикла startup/HTTP/assets/single-instance/shutdown; коды выхода всех шести успешных процессов — **0**.

Это авторская диагностическая проверка, не независимая приёмка и не LIVE PASS. Переключение не выполнялось. OWNER GO не получен; дальнейшие действия остановлены перед этапом D.

### DONE / точная причина

1. EXE из `Test/ClientMigration_20261112/R5` воспроизвёл `PermissionError: Unable to create protected Client directory` в `web_client.py:80`, вызванном из `run_server:642` и `main:684`. Traceback сохранён из stderr и независимо прочитан в собственном QA error dialog. Другие окна/рабочий Client не закрывались.
2. `ensure_private_dir` запускает bundled `Prepare-ClientPrivate.ps1` через системный **Windows PowerShell 5.1.26100.9711**, с имеющимся в Client `-ExecutionPolicy Bypass`. Helper успевает создать пустую директорию и настроить её ACL, затем падает на **строке 18: Get-Acl**. Его exit code — **1**; Client превращает это в общий PermissionError. Это не доказательство отказа файловой системы в создании каталога: каталог реально создан, ACL protected=true, три правила.
3. Harness наследовал `PSMODULEPATH` из Codex PowerShell 7. Сначала в нём обнаруживается `Microsoft.PowerShell.Security` **7.0.0.0** из `%USERPROFILE%/.cache/codex-runtimes/.../powershell/Modules`, а не системный модуль **3.0.0.0** Windows PowerShell. Ошибка автозагрузки: **CouldNotAutoloadMatchingModule**. Явный import при той же процессной ExecutionPolicy даёт `FormatXmlUpdateException`: дублируются члены TypeData `AuditToString`, `AccessToString`, `Sddl`, `Access`, `Group`, `Owner`, `Path`.
4. A/B на одном синтетическом профиле и одном bundled helper: inherited PSMODULEPATH → helper/ACL/import exit 1; исключён только этот ключ в дочернем окружении → helper/ACL/import exit 0, загружен системный модуль. Бинарные файлы, helper, профиль и параметры политики не менялись между этими сопоставлениями.
5. С этим единственным исправлением окружения в harness свежий профиль создан самим frozen EXE. Полный повтор Stage C — PASS.

### EXIT CODE / время / первичное доказательство

- Воспроизведение: PID **3536**, EXE `M:/GitHub/local_LLM/Test/ClientMigration_20261112/R5/UltraLLMClient.exe`, аргумент `--no-browser`.
- Запуск UTC: `2026-11-12T18:49:45.007554+00:00`.
- Код: **1 / 0x00000001**.
- Выход наблюдён UTC: `2026-11-12T18:51:05.451303+00:00`; Asia/Yekaterinburg: `2026-11-12T23:51:05.451303+05:00`.
- Наблюдаемая длительность: **80443.156 ms**, включая ожидание закрытия traceback-диалога. Это не время inference и не startup benchmark. Метка — время наблюдения exit, не Windows kernel event timestamp.
- Точный код самого первого запуска до AMENDMENT 01 ретроспективно восстановить нельзя: старый harness его не записал. Код 1 относится именно к контролируемому воспроизведению; первоначальный пробел в evidence не скрывается.
- Все предыдущие report/checks/checkpoint/manifest/harness/failure/unit logs сохранены с SHA в `pre_amendment_01`; карта — `amendment_01_originals.json`.

```text
Traceback (most recent call last):
  File "web_client.py", line 689, in <module>
  File "web_client.py", line 684, in main
  File "web_client.py", line 642, in run_server
  File "web_client.py", line 80, in ensure_private_dir
PermissionError: Unable to create protected Client directory
```

### CHANGED / DIFF

Только внутри разрешённого каталога отчёта:

- `isolated_checks.py` стал коротким entry point в `startup_diagnostics.py`; исходный файл сохранён как `pre_amendment_01/isolated_checks.py`.
- Новый диагностический harness сохраняет PID, команду, UTC startup/exit, actual returncode и hex, lifetime, безопасные stdout/stderr, readiness и состояния до/после. Ошибка больше не теряется за голым AssertionError.
- Каждый запуск получает новый synthetic AppData/Temp внутри `Test/ClientMigration_20261112/Amendment01`. Старый пустой профиль после отказа сохранён. Ничего не удалялось и не переносилось в Production.
- Контроль среды исключает PYTHONHOME/PYTHONPATH как раньше и дополнительно PSMODULEPATH только в дочернем QA env. Системные/user environment, execution-policy registry, ACL настоящего профиля не менялись.
- Добавлены защита home-host/workspace, проверка всех 72 payload SHA, native DLL/listener, distinct mutex и read-only сравнение старой установки/ярлыка/PID до и после.
- Обновлены этот существующий report.md, checks.json, checkpoint.json, isolated_failure.txt и manifest. Клиентские/серверные исходники, EXE, общий №07 и другие нормативные документы не редактировались. Новых веток, корней, коммитов/push нет. Видимые пользовательские изменения №07 и внешнее изменение Obsidian workspace.json не редактировались и не откатывались этим harness.

Текущий проверенный HEAD workspace: `312106680ae60b72243132bfc0710857127f3b72`. Исходный Stage A имел другой HEAD, `03d1cd9...`; исторические значения не подменяются. Испытывается существующая R5 из authoritative ZIP, без пересборки и без архивной .venv.

### TESTS / EVIDENCE

| Проверка | Результат |
|---|---|
| Authoritative ZIP SHA | PASS: `bc37f43f84263da8f42e006ab3e3833e85a3781bfb11858809882a51b34a9d8a` |
| QA R5 | PASS: 72 payload SHA, 73 файла с manifest |
| Bundled helper vs текущий source helper | PASS: byte-exact |
| Original backup | PASS: 68/68 файлов повторно сверены |
| Полный rollback R5 backup | PASS: 73/73 файлов повторно сверены |
| Failure reproduction | CONFIRMED: EXE exit 1, traceback `ensure_private_dir:80` |
| Helper A/B со штатным ExecutionPolicy Bypass | Inherited env FAIL/1 → system-default module env PASS/0 |
| Client unit | **49/49 PASS**, 17.092 s, отдельные новые stdout/stderr |
| Два цикла первого запуска/закрытия | PASS, PID 17664/17976; оба shutdown exit 0 |
| Четыре duplicate EXE | PASS, все exit 0; основной PID/port не изменились |
| HTTP /api/config и /api/status | PASS: configured=false, managers=[] |
| HTML/CSS/JS | PASS: три ответа byte-exact к frozen payload в обоих циклах |
| Bundled Python | PASS: QA `R5/_internal/python312.dll` |
| Loopback listener | PASS: только 127.0.0.1; QA порты 52207/51217, старый 60720 не использован |
| Visual browser / запуск VBS | NOT RUN в этой диагностике; старый ярлык ни разу не запускался |
| Windows Event Log | SKIP: первичная ошибка уже установлена без чтения посторонних журналов |
| Stage D / Production / LIVE migration | **NOT RUN / OWNER GO ABSENT** |
| Real Manager calls / inference / server control | **0 / NOT RUN** |

Первый ручной helper-probe был вызван без штатного процессного `-ExecutionPolicy Bypass` и поэтому дал PSSecurityException в обеих ветках. Это ошибка диагностической пробы, а не причина реального frozen failure. Проба сохранена отдельно как `amendment_01_environment_without_startup_policy.json`; вывод сделан по исправленному сопоставлению со штатным параметром в `amendment_01_environment.json`. Никакая глобальная политика выполнения не изменялась.

Команды из домашнего workspace:

```text
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/startup_diagnostics.py --diagnose
py -3.12 -X utf8 -B Documents/Reports/CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001/isolated_checks.py
```

Первая команда намеренно воспроизводит плохую среду и может показать диагностическое окно. Её controller exit 0 означает «ошибка успешно воспроизведена», **не** успех EXE; actual child returncode=1 записан отдельно. Повторять без необходимости не нужно.

Основные доказательства:

- `amendment_01_reproduction.json` — actual failure exit/times/stderr и неизменность baseline.
- `amendment_01_environment.json` — контролируемый helper/import/ACL A/B с теми же параметрами запуска.
- `amendment_01_dialog.json` — текст окна только QA EXE и его process-backed app path; точный traceback без личной истории.
- `isolated_result.json` — текущий PASS Stage C со всеми шестью exit codes и native metadata.
- `amendment_01_unittest.stderr.txt` — полный 49-test прогон.
- `checks.json`, `checkpoint.json`, `manifest.json` — текущий статус и SHA.

### Проверенные гипотезы

- Повреждённый/неполный EXE: исключено SHA ZIP/payload; используется проверенный ZIP, а не loose-копия с CRLF-расхождениями.
- Отсутствующий helper: исключено, он есть в bundle и совпадает с source.
- Неверный LOCALAPPDATA/настоящий профиль: исключено явной изоляцией fresh AppData в QA и configured=false. Реальные profiles/history/secrets не читались и не копировались.
- Отсутствие прав на директорию: не является причиной этого сбоя; directory/ACL созданы, отказ возникает при импорте команды проверки ACL. С system module теми же правами запуск проходит.
- Занятый production port: исключено; ошибка возникает до bind, а успешные QA listeners имеют другие порты.
- Конфликт single-instance mutex: исключено и distinct path hash, и успешной параллельной работой QA с неизменным старым PID. Отказ helper происходит до `_instance_mutex`.
- Глобальная ExecutionPolicy: не первопричина, штатный process Bypass сохранён в причинном A/B.
- Contaminated PSMODULEPATH: **подтверждено** отрицательным/положительным helper и frozen startup контролями.

### Сохранность защищённых объектов

Старый процесс **29492** с прежними exe path/creation продолжает работать; старые 68 файлов и SHA ярлыка совпали до/после. Пять отсутствующих root-файлов старой установки, включая VBS, **не восстанавливались**. Ярлык не менялся и не запускался. `Production/Client` не создан.

Серверных runtime-команд, запросов Manager из QA, START/STOP, операций Colibri/Qwen/Valheim, WinRM/firewall/TLS/secrets не выполнялось. Глобальная побайтовая неизменность сервера независимо не измерялась: сервер не исследовался. Подтверждается отсутствие действий агента, а не вымышленный remote audit. Настоящая история/профиль не открывались; её число сообщений в этой диагностике не перепроверялось.

### PROBLEMS / QUESTIONS

Диагностический startup blocker устранён в harness. Сам Client по-прежнему не защищает свой PowerShell child от произвольного несовместимого PSMODULEPATH внешней оболочки; изменение Client для общего hardening — отдельное возможное предложение, **не выполнено и не требуется для текущего QA PASS**.

Неразрешённый operational риск сохраняется: старый ярлык ссылается на отсутствующий VBS. Возврат простым восстановлением .lnk на старый каталог не доказан и не предлагается как надёжный rollback. Полный workspace backup R5 byte-exact к успешно испытанному комплекту; фактический запуск backup с настоящим профилем и LIVE rollback здесь NOT RUN. Удаление QA-каталогов не требуется, они оставлены как диагностические evidence.

Технических вопросов для диагностики нет. OWNER GO на переключение отсутствует. Задача миграции остаётся активной; карточка/архив не ротируются, итоговый или промежуточный коммит не создаётся.

### Подготовленный объём будущего OWNER GO — НЕ ВЫПОЛНЕН

1. Повторно проверить current PID/path/creation/owner/listener, backup и protected profile availability; не закрывать PID по имени или устаревшему номеру.
2. Штатно завершить только подтверждённый пользовательский Client. На этом шаге требуется отдельное явное разрешение владельца.
3. Скопировать полный verified ZIP payload в `M:/GitHub/local_LLM/Production/Client`, проверить все 73 файла. Старый `M:/UltraLLM_Client` не восстанавливать и не изменять.
4. После проверки backup .lnk один раз изменить существующий ярлык: target системный wscript.exe, argument VBS внутри Production/Client, working directory тот же новый каталог. Не создавать ещё один основной ярлык.
5. Запустить один новый Client с прежним защищённым профилем, проверить ONLINE/catalogue/метаданные истории, два повтора и штатное закрытие/повторный запуск. Использовать совместимое дочернее окружение; не менять системные настройки. Сервер/модели не переключать.
6. Согласовать rollback через **полный R5 backup внутри workspace**, а не через отсутствующий старый VBS. При отказе сохранять неуспешную Production-папку и диагностические данные, закрывать только собственный подтверждённый новый процесс и после разрешения направлять тот же .lnk на verified backup VBS. Личные данные не откатывать/не переносить. Это план для утверждения, не разрешение и не выполненная операция.

### DOC IMPACT / NEXT

Координатору: №13/05/09 — заменить текущий UNRESOLVED Stage C blocker на **AMENDMENT 01: причина установлена, isolated Stage C PASS, STAGED / OWNER GO REQUIRED**; сохранить исходный FAIL и отсутствие его exit code как исторический факт. №18 — child PSMODULEPATH/Windows PowerShell module mismatch и готовность workspace QA/backup; отсутствие старого VBS и невыполненный LIVE rollback оставить OPEN. №00 — Production не установлена. №06 — нового OWNER GO не было.

Обновлены только разрешённые checkpoint/checks/report/evidence внутри каталога задачи. Нормативные документы и БЛОК 4 не редактировались. **NEXT: независимая проверка диагностического пакета; этап D только по отдельному решению владельца.**

---

## Исторический checkpoint до AMENDMENT 01

Исходный report сохранён дословно в `pre_amendment_01/report_original.txt` (SHA в `amendment_01_originals.json`); первоначальные checks/checkpoint/manifest/failure/unit logs рядом. Исходный Stage C имел BLOCKED, 49 source PASS, packaged startup FAIL с незафиксированным exit code. Новые данные выше не присваивают старому запуску вымышленный код или успешный результат.
