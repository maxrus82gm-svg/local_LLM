# 23 — Нейрополис: подключение и настройка Client, Manager и VPN

## P2 — индивидуальный резерв GPU (кандидат исходников, не установлен)

В настройках CUDA слота выбрать Auto/Full/Вручную, включить «Приоритет выбранных GPU и индивидуальный резерв (бюджет весов)», отметить разрешённые GPU и задать резерв каждой. Резерв — дополнительная свободная память сверх уже занятой Windows; Manager вычитает также 2 ГиБ служебного запаса и ограничивает числовой бюджет весов консервативным минимумом выбранных карт. Это не жёсткая квота драйвера: полное потребление не гарантировано. Если GPU занята или резерва недостаточно, Full не подменяет группу. Сохранение профиля не останавливает модель. В кандидате #164 при поддержке Manager можно использовать молнию «Перезапуск»: отдельное подтверждение группы, подтверждённая остановка, новая проверка резерва и старт того же слота; если память не освобождена или резерва недостаточно, запуск не повторяется. До установки проверенного #164 используйте явный Стоп → Старт только по согласованию. Старые профили остаются без изменений. Для дополнительных слотов WORK использовать существующее окно «Сеть и доступ», явный список slot ID, сохранить текущий Client ID/сертификат/права локального подключения; безопасный restart Manager только после backup/idle. Qwen CPU/CUDA и остальные права проверить отдельным LIVE тестом после merge/CI. 

## 26.11.2026 — LIVE-UL-WORK-RELEASE160-20261126-001 / VPN-HOME-WORK-01 — KAT CUDA LIVE PASS

OWNER GO в чате: запустить текущий KAT slot1, принять предупреждение unknown RAM/VRAM forecast, получить реальный ответ через HOME Client → WORK Manager по WireGuard и остановить только тестовый экземпляр. #160 runtime, без изменения профилей/прав/туннеля/служб. Первый START принят, instance 10f930acdcf641a2a82d0598f557ee30; диагностический канал потерял session, проверка ошибочно ожидала постоянный model_id вместо instance-specific ID; точная причина выхода скрипта не сохранена. Независимо STOPPED/released=1, тестовый чат не создан. Повтор с правильным ID и локальным журналом: instance f291b286cc0048f79f2f5ad3b6aacfb2, START request ae2d977c6c5f4e29aa7d012106734c3e, READY 65.609 s, KAT CUDA сохранённый профиль budget 11 GiB / target 7 GiB / chain=true / rows=1024, GPU0 RTX4070 Ti SUPER, VRAM экземпляра 9.079 GiB; GPU1 не задействована. Реальный NDJSON stream через HOME Client API, chat e0131988a5c249e39702efeb71ebcb97, request 3d71ea00301a4b9db87a607bb30376ac: ответ “Test message received.”, 4 delta, 0 reasoning (thinking off), first fragment 4.344 s, total 4.906 s, provider usage 27 prompt / 4 completion, throughput 0.84 token/s включая prefill (не чистая скорость декодирования), history readback 2 messages. Explicit Stop → STOPPED/released=true, оба экземпляра освобождены, WORK DB unreleased=0; независимый nvidia-smi после остановки GPU0 2423 MiB и GPU1 0 MiB, совпадает с preflight, HOME catalog также 2.366 GiB / 0; Manager PID33392, local 127.0.0.1:18443 + VPN 10.253.77.3:18443, WORK Client PID34164 port56686 сохранены. Evidence: HOME protected client backup, live-kat-vpn-attempt2.jsonl, WORK SQLite/readback. LOCAL-PLAN-01 до/после PASS, plan SHA b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee, archive 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102. Студия/Bridge не активированы, M1-10 HOLD. Первая обычная HOME→WORK генерация/Stop/release — PASS; длительная генерация, multi-GPU Full, VPN reconnect, visual UX owner, joint Studio acceptance — OPEN. Следующий этап согласовать отдельно; не запускать модели автоматически. #161 docs CI 45873457153 SUCCESS.

## 26.11.2026 — LIVE-UL-WORK-RELEASE160-20261126-001 / VPN-HOME-WORK-01 — CONNECTION PASS / INFERENCE OPEN

**Актуальная инструкция (проверена на HOME/WORK).** Эта запись заменяет прежние статусы «VPN не реализован/не проверен» в исторических разделах ниже. Подключение уже настроено; не повторять создание сертификата или регистрации поверх работающего профиля. Туннель уже существует. Это соединение Manager, не Bridge и не тест LLM.

| Параметр | Значение на текущих ПК |
| --- | --- |
| HOME WireGuard IP | 10.253.77.2 |
| WORK WireGuard IP | 10.253.77.3 |
| Manager ID | work-43paebo |
| Прежний локальный WORK endpoint | https://127.0.0.1:18443 |
| Новый HOME→WORK endpoint | https://10.253.77.3:18443 |
| Client ID (VPN) | home-rex-work-vpn |
| VPN права P0 | slot1, запуск/остановка; не администратор |
| Тайм-аут проверки процессов | 30 с (10–120 с) |
| Firewall | Neuropolis-Manager-WireGuard-HOME-WORK-18443, только TCP .2→.3:18443, интерфейс NeyropoliWork, фактический python.exe |
| Публичный TLS SHA-256 | 1753c4d5baa3ab0f997735d845491c0a9d6343fb17b2ec343c8bb14c8ed2a270 |

**Как открыть настройки WORK:** в PowerShell на рабочем ПК из обычной Windows-сессии выполнить (действующий Manager не запускается второй раз):

```powershell
& 'C:\Users\Gamedev\AppData\Local\Programs\Python\Python312\python.exe' -B 'D:\Neyro\Menager\live_manager.py' --config 'D:\Neyro\Menager\private\manager.json' --network-settings
```

1. «Разрешить дополнительный VPN-вход» → локальный IP .3, разрешённый IP клиента .2. Основной адрес 127.0.0.1:18443 оставить. Для нового хоста сверить реальные адреса, не использовать wildcard.
2. Для новой установки «Создать TLS» → доверенный OpenSSL, на WORK найден `C:\Program Files\Git\usr\bin\openssl.exe`. SAN = VPN IP; приватный ключ остаётся в private. «Экспорт публичного TLS» → только публичный PEM, сверить отпечаток независимым каналом. Для текущего подключения пара уже создана.
3. HOME Client → «Обзор серверов» → «Подключить Manager», заполнить Manager ID, отдельный Client ID, IP .3, порт 18443, импортировать публичный сертификат. Мастер создаёт токен на HOME; на WORK переносить только SHA-256 регистрации, не токен. Первое not_submitted до появления listener ожидаемо, профиль остаётся.
4. WORK → указать отдельный Client ID, SHA-256 регистрации, разрешённые slot ID, «Разрешить запуск и остановку моделей» для нужного пользователя; «Сохранить». В существующей регистрации пустой SHA сохраняет его для того же ID. Тайм-аут → 30 → «Сохранить тайм-аут». Явный restart Manager только после остановки активных моделей и проверки backup/idle. UI сам не перезапускает Manager и не создаёт firewall-rule.
5. «Брандмауэр» → штатный Windows Firewall: входящее разрешение на точный TCP port, local/remote IP, приложение, WG interface; не открывать WAN/роутер и не отключать firewall. Проверить ActiveStore. На WORK правило уже создано штатным PowerShell API, совпадение фильтров проверено.
6. «Проверить TCP» → основной и VPN TCP одного процесса есть. HOME Client → «Обновить», WORK ONLINE. Проверить TLS/auth и доступ к каталогу, не считать ping или TCP достаточными. Нельзя заменять прежний профиль или сертификат. При изменении сети не отключать TLS/ACL.

**Фактическая процедура координатора:** файлы и состояние резервированы до переключения. Установлены точные исходники main #160; настройки сохранены через штатные функции save_vpn_settings/save_process_inventory_timeout и /api/enroll, не редактированием JSON; окно Tk программно открыто и поля/кнопка TCP проверены. Визуальная приёмка человеком не выполнена. BACKUP WORK `D:\Neyro\Menager\private\release-160-20261126\backup`, manifest, RESULT.json и VPN_RESULT.json в родительском каталоге; HOME прежний managers.json и consistent SQLite в защищённом backup-before-work-vpn-160-20261126 под Client private. Не публиковать секреты и не восстанавливать старые DB поверх новых чатов. При VPN rollback отключить только дополнительный вход через UI, сохранить и безопасно перезапустить, удалить только собственное scoped firewall-rule; прежние HOME/Server77 и локальный WORK оставить.

| Попытка | Факт / причина | Результат |
| --- | --- | --- |
| #160 main CI attempt1 | P1 не дождался DOM статуса «Стоп → Старт», 10 s, строка 329; причина задержки UNKNOWN, не VPN | Повтор на том же SHA attempt2 SUCCESS |
| WORK preflight | Вначале ошибка quoting PowerShell/Python диагностической команды (SyntaxError), не продукт | Python stdin корректно прочитал БД, active instances=0 |
| WORK cutover attempt1 | Пустой список освобождённых портов вызвал ненулевой exit Get-NetTCPConnection -LocalPort | Автоматический rollback, local ONLINE, runtime не заменён; исправлена проверка пустого списка |
| WORK cutover attempt2 | 39 exact blobs, проверенный ZIP, protected backup 49, config PASS | №160 technical install PASS; Client local ONLINE |
| HOME enrollment до listener | not_submitted/manager_unreachable_or_untrusted, ожидаемый недоступный порт | Новый профиль сохранён, прежние неизменны |
| WORK TLS/firewall/settings | SAN, key ACL, отдельный grant, ActiveStore rule, 30 с, два TCP одного PID | PASS |
| HOME TLS/auth | HTTP 200 identity work-43paebo/home-rex-work-vpn; без/неверный token 401 | PASS; чужой источник .3 прерван до TLS |
| HOME статус Client | HOME, Server77, WORK ONLINE; видит обе GPU WORK | CONNECTION PASS. Не inference PASS |
| Реальная LLM | KAT/Qwen требуют risk acknowledgement (unknown RAM/VRAM estimate), активных экземпляров нет | NOT RUN, требуется явное подтверждение владельца; не менять профиль без согласования |

OWNER GO: WORK #160 установлен из принятого main `ed47e88299bea6152bd5212e7a6778101756ce5b` (source #160 `02faba224aa91e10a5e9f518ac3d40585cb2db62`). [CI source 45868584541](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45868584541) SUCCESS attempt1; [CI main 45869830813](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45869830813) attempt1 FAIL Chrome P1 DOM deadline при сохранении CUDA (строка 329), остальные suites PASS; attempt2 job 140084451402 SUCCESS, тот же SHA, причина первого сбоя UNKNOWN. PowerShell 30 s установлен, диапазон UI 10–120 s; Chrome QA 30 s. Сетевые профили и восстановление стрима OPEN.

WORK: 39 source blobs exact Git SHA/size, Manager ZIP 23 entries SHA256 1223e21a99416aa67014208f74f90b959d3846fcf68f3d70ecff00c3c3d1dfd6; 49 backup records, включая consistent SQLite обеих программ, manifest SHA256 505f55e74c74cdeffd2ebb3cd24b84b4710c5263f3fd35f56b75891de4734c12. Первая попытка переключения остановилась на собственной проверке освобождённых портов (Get-NetTCPConnection -LocalPort при пустом результате exit1), rollback LOCAL ONLINE, код не заменён. Повтор после исправления проверки: INSTALL PASS, 5 runtime + 2 metadata, все 39 blobs readback; private config/auth/TLS неизменны при обновлении. WORK Manager #160 после VPN restart PID 33392, Client PID 34164, ordinary session1. One Manager, 127.0.0.1:18443 и 10.253.77.3:18443; WORK Client 127.0.0.1:56686 ONLINE.

VPN LIVE: HOME .2 → WORK .3, существующий WireGuard 16 ms, конфигурация туннеля/маршруты/службы не менялись. Отдельный TLS SAN .3, доверенный Git OpenSSL 3.2.3, проверка ACL/key/validity PASS. HOME Client enrollment через штатный /api/enroll, initial not_submitted ожидаем до listener, старые HOME/Server77 профили сохранены, новый work-43paebo / home-rex-work-vpn. Ограничение P0: только slot1 + control_models, без pairing_admin. Сохранено через те же валидируемые функции UI (не ручной JSON); отдельное узкое правило Windows Firewall local .3, remote .2, TCP18443, interface NeyropoliWork, python.exe; ActiveStore readback PASS. Настоящее локальное Tk окно программно проверено, «Проверить TCP» PASS и timeout 30, secret digest не показывается; визуальная приёмка владельцем OPEN. HOME HTTPS verified/auth 200, no token/wrong token 401, wrong source WORK .3 abort before TLS. HOME Client видит HOME/Server77/WORK ONLINE, WORK local ONLINE. Две GPU WORK видны из HOME (4070 Ti SUPER 16 GiB + 3060 Ti 8 GiB), объединение VRAM и реальная генерация NOT RUN.

**NEXT:** slot1 KAT CUDA уже выбран, RAM/VRAM estimate unknown, UI requires_ack=true (оба KAT/Qwen CPU/CUDA). Не подтверждать риск за владельца. После явного GO запустить KAT текущим профилем, проверить реальный поток, usage/TPS, Stop и VRAM release; затем тест reconnect/изоляции, расширение доступа только согласованно. HOME Manager/Server77/Студия не обновлялись, HOME Client добавлен только профиль, его процесс не перезапускался. Не включать Bridge/фоновые службы/сон, M1-10 HOLD. LOCAL-PLAN-01 read до и после PASS, SHA b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee; archive 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102, общий план не изменён. Подробная практическая инструкция и журнал проб — №23.

## 26.11.2026 — VPN-HOME-WORK-01 / TIMEOUT-POLICY-01 — SOURCE CANDIDATE

[CI 45862810802](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45862810802): Manager ERROR — Get-CimInstance Win32_Process из локального PowerShell, deadline 4 s; Chrome legacy ERROR — локальный DevToolsActivePort не появился в ~10 s. Остальные Chrome сценарии и Client PASS. Это не задержка WireGuard; причина медленного запуска хостового процесса UNKNOWN. #159 повтор ранее PASS; предыдущие ошибки не считать доказанно устранёнными до нового CI.

P0: Manager process_inventory_timeout_seconds default 30 s, integer 10–120, сохраняется отдельной кнопкой в локальном окне «Сеть и доступ» (существующий --network-settings), независимый CAS/защищённая резервная копия/readback; вступает в силу после явного безопасного перезапуска Manager. При превышении лимита проверка принадлежности остаётся UNKNOWN/ERROR, освобождение не подтверждается; проверки безопасности не отменяются. Chrome QA: единое ожидание готового DevTools-порта, default 30 s, переменная окружения UL_QA_CHROME_STARTUP_SECONDS (10–120) только для автотестов, диагностика ошибки запуска/раннего выхода/истечения лимита. Остальные PowerShell/сетевые/LLM лимиты не менялись. Тесты границ, применения параметра и сохранения добавлены; CI PENDING, реальный Windows UI и HOME→WORK LIVE NOT RUN. WORK #156, другие машины, main и Студия не изменены; M1-10 HOLD. Следующее: зелёный CI точного HEAD, owner merge, затем Windows UI/readback и VPN LIVE по №23.

**Настройка:** Manager → «Сеть и доступ» → «PowerShell: проверка процессов, с» → 30 (при необходимости 60) → «Сохранить тайм-аут»; после остановки активных моделей явно перезапустить Manager и сверить сохранённое значение. Chrome — только QA, не поле рабочего Client.

## 26.11.2026 — VPN-HOME-WORK-01-P0: журнал проб, ошибок и проверок

**Регламент:** при каждой попытке подключения записывать условия, проверенный build/SHA, симптом, точный тест/лог, установленную причину (или UNKNOWN), изменение, повторную проверку, результат и следующие действия. Не записывать приватные ключи, bearer-токены, содержимое личных чатов. Различать OFFLINE CI и реальный LIVE.

| Попытка | Наблюдение и причина | Действие / результат |
| --- | --- | --- |
| WORK #156, до VPN-настроек | WireGuard ping HOME .2 ↔ WORK .3 PASS (16–17 мс), Manager слушает только 127.0.0.1:18443; первичный TLS SAN localhost/127.0.0.1 | IP-транспорт подтверждён, но HTTPS через VPN NOT RUN. Отдельный точный VPN listener, отдельный сертификат и клиентская регистрация, сохранить loopback. |
| #158, [CI 45858531232](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45858531232) | Manager 460: 1 FAIL, 1 skip; ошибочное сравнение `current.pop("vpn_listener")` с primary в `test_vpn_save_preserves_primary_and_requires_expected_state`. TLS negative SAN test PASS, ожидаемый отказ неправильному адресу. | #159 исправил assertion: отдельно VPN-блок и остаток primary, добавил проверки копий и CAS/disable; production source не менялся. |
| #159, [CI 45861189797](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45861189797), attempt 1, job 140052339517 | VPN save test PASS. Manager 460: 1 ERROR, 1 skip; `test_job_recovery_never_touches_neighbor_and_requires_anchor`, `windows_process.py:350`, subprocess.TimeoutExpired при Get-CimInstance Win32_Process (4 s). Client 86, 1 skip, Chrome 4/4 PASS. Это не ошибка установления WireGuard/TLS. | Запущен повтор failed job без изменений исходников; повторяемость тайм-аута фиксировать, первопричина UNKNOWN. Не ослаблять проверку принадлежности процессов, не убивать соседние процессы, не обходить тесты. |
| #159, attempt 2, job 140055099969 | attempt 2: Manager/Client unit PASS, финальный CI IN_PROGRESS; итог PENDING. | Повтор Manager PASS: тайм-аут в этой попытке не воспроизведён, но дефект задержки не объявлять устранённым. Точный CI SHA d4b759fcab04243eaac042a456b76f6e4f6ba527. |

**Следующие LIVE записи:** проверка наличия доверенного OpenSSL на WORK; проверка отдельного SAN и отпечатка публичного TLS; точный peer firewall; HOME Client registration/ONLINE; отрицательные проверки адреса/credential; поток ответа с WORK, измеренные токены/с, явный Stop и освобождение ресурсов, сохранение прежнего локального подключения; отключение/возврат VPN. На каждом шаге фиксировать команду или действие интерфейса, фактический результат, ошибки/исправления и rollback. Сейчас эти шаги NOT RUN. Сначала обычный Windows-сеанс, без proxy, сервисов, сна или reboot. Студия Нейрополис (WEB36) ожидает успешного сквозного теста; совместная приёмка ещё не проводилась. M1-10 HOLD.

## 26.11.2026 — VPN-HOME-WORK-01-P0: окно сети Manager (кандидат, LIVE ещё не принят)

**Что есть в исходниках:** отдельное локальное окно администратора, а не удалённый Web UI. Открыть через установленный Python 3.12 на хосте Manager: `python -B live_manager.py --config "<абсолютный путь к private\manager.json>" --network-settings`. Это окно не запускает второй Manager. Для WORK использовать существующий runtime, не копировать путь на другие ПК. Основной bind/порт показаны только для чтения, VPN использует тот же порт; первичные сертификат/ACL не заменяются. В P0 разрешён один точный peer и отдельная регистрация.

1. На WORK открыть окно, отметить «Разрешить дополнительный VPN-вход». Указать точный локальный WireGuard IP, разрешённый IP домашнего клиента. Для текущих узлов это 10.253.77.3 и 10.253.77.2; не 0.0.0.0, не подсеть. В других установках выбрать фактические адреса, сверить с WireGuard/Windows.
2. В «Создать TLS» выбрать установленный доверенный OpenSSL (если его нет в PATH, диалог выбора executable; наличие на WORK ещё не доказано). Сертификат SAN = локальный VPN IP, отдельный приватный ключ в защищённой папке Manager; либо выбрать заранее подготовленную пару файлов именно из этой папки. Экспортировать **только** публичный сертификат, сверить SHA-256 с получателем вне VPN. Не заменять прежний loopback сертификат. Генерация/импорт не сохраняет настройки автоматически.
3. HOME Client → мастер добавления Manager: точный Manager ID WORK, новое отдельное Client ID, VPN IP и тот же HTTPS порт, импорт доверенного публичного сертификата. Мастер создаёт секрет локально, показывает registration SHA-256. До разрешения сервером статус может быть not_submitted/OFFLINE — это ожидаемо; VPN удалённую саморегистрацию не принимает. Не передавать исходный токен.
4. На WORK ввести ID и SHA-256, точные разрешённые слоты, при необходимости отдельный флаг запуска/остановки моделей. Пустой SHA только для неизменного уже сохранённого ID. Никакого pairing_admin через VPN. «Сохранить» создаёт защищённую резервную копию и атомарно сохраняет настройки под общей блокировкой; явный перезапуск после idle/backup, не во время генерации. При изменении старый VPN-вход отказывает до restart; первичный сохраняется.
5. «Брандмауэр» открывает штатную оснастку Windows и показывает точный local/remote IP/порт. Администратор создаёт входящее TCP правило на соответствующую программу Manager, адреса и порт; по возможности ограничить интерфейсом WireGuard. Проверить активные профили и отсутствие более широких разрешений, не отключать firewall и не пробрасывать HTTPS на роутере. Само окно правило не устанавливает.
6. После явного безопасного перезапуска «Проверить TCP» показывает наличие основного и VPN слушателя одного PID (не доказательство TLS/auth). С HOME проверить соединение Client → WORK ONLINE, TLS/авторизацию; Client теперь различает ошибки сертификата, TLS, TCP refusal, timeout, DNS и конфигурации. Проверить отказ чужому источнику/credential и доступ локального WORK Client, реальный ответ только после GO. Не применять insecure TLS или proxy.

Отключение: снять флаг и сохранить, старый VPN admission закрывается для новых запросов; явный restart освобождает listener. Удалить только своё scoped правило в Windows Firewall. Откат настроек — в UI вернуть прежний набор VPN полей; резервную копию читать под защитой, не заменять весь manager.json поверх новых регистраций. Не трогать первичный профиль. При отсутствии адаптера secondary bind повторяется, primary работает; реальное выключение/включение WireGuard проверить отдельно. Работу без входа Windows и сон не тестировать в P0. Фактическая инструкция кнопок и screenshots уточняются после Windows UI/LIVE; source candidate, не утверждённый релиз.

## 26.11.2026 — Практический контроль HOME → WORK (VPN-HOME-WORK-01)

**Факт:** рабочий ПК DESKTOP-43PAEBO обновлён до #156; Manager работает на 127.0.0.1:18443, Client на 127.0.0.1:56686. Оба компонента в обычной пользовательской сессии. WireGuard HOME 10.253.77.2, WORK 10.253.77.3; двусторонний ping проверен, 16–17 мс, автозапуск обеих служб подтверждён. Это проверка IP-транспорта, не успешное подключение Manager. Рабочий Manager пока не слушает VPN IP, поэтому удалённая регистрация, TLS и генерация не подтверждены. Настройки сети на этом этапе не изменялись.

### Варианты подключения и диагностика

- Локально на WORK: прежний профиль Client и HTTPS 127.0.0.1:18443 сохраняются; локальный статус ONLINE подтверждён после обновления. Не заменять существующий профиль/сертификат.
- LAN: использовать только назначенный Manager LAN endpoint, разрешённый исходный IP и доверенный сертификат; наличие LAN-пинга не подтверждает API. Не расширять существующие LAN разрешения.
- HOME → WORK через WireGuard: сначала обе службы WireGuard Running, IP .2/.3, ping на противоположный адрес; далее после реализации выделенного HTTPS listener и ограниченного firewall проверить `Test-NetConnection 10.253.77.3 -Port 18443` на HOME. Никакого прокси для этого точного адреса, никакого открытия TCP18443 на роутере.
- Если ping не проходит — проверить handshake, peer /32 AllowedIPs, доступность UDP, маршруты и состояние сна; ключи не публиковать. Если ping проходит, TCP нет — сверить адрес прослушивания Manager и точное правило firewall. Если TCP есть, HTTPS нет — проверить SAN сертификата и доверие (не отключать проверку TLS). Если HTTPS отвечает 401/403 — сверить отдельную регистрацию, allowed_client_ips, client identity и разрешения. Не выдавать чужие токены и не открывать Manager всем.
- После появления защищённого UI Manager: разрешить именно VPN listener 10.253.77.3:18443 дополнительно к loopback, источник HOME 10.253.77.2; показать фактический bind/статус, port, TLS, ACL, изменения и необходимость restart. Client: отдельное согласованное подключение WORK VPN с доверенным публичным сертификатом и авторизацией, проверка ONLINE. Эти элементы реализованы как source candidate #158/#159, но ещё не установлены и не приняты на Windows; точные шаги кнопок подтвердить после CI/LIVE.
- Приёмка: обычная пользовательская сессия, авторизованный HOME Client получает реальный ответ от WORK, контрольная остановка освобождает ресурсы; проверка отказа постороннему источнику/неверному credential, прежний локальный профиль работает. Только после этого — тест Win+L, запуск без логина и отдельный Wake-on-LAN.

Сетевые поля обязаны быть доступны через UI, секреты защищены, OS-настройки либо статус, либо явное привилегированное действие. Не менять VPN/Manager вручную как окончательное решение. При отказе нового listener сохранить прежний доступ и выполнить проверенный rollback конфигурации; не восстанавливать устаревшую БД поверх новых чатов. История обновления: LIVE-UL-WORK-RELEASE156-20261126-001, №18/13.

## 26.11.2026 — MULTI-GPU-01 / P1 Client UI

OWNER GO: finish GitHub source and automatic tests first; then update WORK full compatible pair (two GPUs), check real Multi-GPU, HOME full pair and one-GPU regression, and explicitly add HOME ↔ WORK tunnel to the follow-up sequence. #155 exact CI [45779147345](https://github.com/maxrus82gm-svg/local_LLM/actions/runs/45779147345) SUCCESS, attempt1, Manager 454 tests (1 skip), Client 85 (1 skip), synthetic multi-GPU tests and Chrome PASS, LIVE NOT RUN. OWNER merged #155 into main 0a03a54cab91072a5494c4be018ceafcc44ce51a (only Obsidian diff above tested SHA). P1 SOURCE CANDIDATE: Manager catalogue returns authorized hardware inventory and anonymous global managed reservation flags, without new poll loops. Client prelaunch ⚙ and chat CUDA settings provide legacy GPU 0, CUDA Auto (one free compatible GPU), Full (all free compatible GPUs), Manual (UUID checkbox group); per-device name, free/used/total, utilization and reservation, missing-device preservation, estimated group budget and assigned group summary. Existing legacy profiles/default remain unchanged. Saves per slot/model, no implicit stop/start; explicit GPU group requires Stop → Start and rebind chat, automatic GPU restart remains OPEN. Group usage shows total device load, not model-specific usage per card; per-instance aggregate retained. Existing numeric weight budget is not OS quota. Tests authored: real Client→TLS Manager→SQLite→Chrome with synthetic two-GPU inventory, legacy compatibility, explicit Full save from chat without restarting, both GPUs assigned to one fake model, manual and Auto on separate GPUs, stop isolation, missing inventory/invalid empty manual negative controls. CI PENDING, actual hardware NOT RUN; no deployment. Sharing one GPU between explicit managed groups remains OPEN (exclusive groups for first verified release), no hard per-card quota or guaranteed speed. WORK installation and real acceptance only after exact CI, owner merge, idle/backup and approved scope; HOME single GPU regression, no other host updates until acceptance. LOCAL-PLAN-01 14:39:19+05 SHA b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee; archive 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102. Shared M1-10 HOLD unchanged. [P1 report](../Test/MULTI-GPU-01/p1-ui-report.md).

**NEXT — VPN-HOME-WORK-01 (OWNER requested, PLANNED, not configured):** resume existing №23 §5 WireGuard HOME ↔ WORK plan after Multi-GPU WORK/HOME verification. First read-only inventory of both endpoints, router/UDP, existing tunnel, routes/DNS, current TLS/listeners and privileges; no private keys in reports. Preserve existing LAN, loopback, registrations, VPN/V2Ray and internet. Prefer existing WireGuard direct split-tunnel with only peer /32 routes; verify static public IP and UDP reachability rather than assume. One Manager per host; optional specific VPN HTTPS listener with same admission/DB, preserve existing bind, validate certificate SAN/trust and firewall limited to peer. Separate source/CI task if listener needed. Verify handshake, routes, TLS/auth, both Client directions, local service unchanged, VPN off/on recovery; no external TCP exposure, no firewall disable, no blanket routing, no installation before local preflight/idle gates. Current tunnel connectivity NOT VERIFIED; this is an explicit follow-up, not a shared integration stage change.


## 26.11.2026 — MULTI-GPU-01 / P0 backend

OWNER GO: GitHub First, no deployment on HOME/WORK/other hosts; no Codex. #154 exact CI 45774620663 attempt2 SUCCESS; first attempt failed on 4s PowerShell process query, historical failure retained. OWNER merged #154 into main 264fc7195826f4b5a205f02731678abd04dd1dfa (additional Obsidian-only diff). P0 SOURCE CANDIDATE: typed optional per-slot/model CUDA profile gpu_mode (auto/full/manual) and gpu_ids (physical NVIDIA UUIDs); legacy profile unchanged. Hidden bounded GPU inventory with per-card VRAM/utilization/PCI/compute capability, no extra poll loop. Server resolves and reserves exclusive managed GPU groups under existing SQLite admission transaction; rejects unknown/legacy overlaps, confirms selected UUIDs in risk token, uses CUDA_VISIBLE_DEVICES + remapped Colibri --gpu ordinals, existing --vram total group budget. GPU budget is advisory, no OS quota; external/legacy unmanaged usage not reserved. Stock Windows CUDA package candidate CC>=8.0, actual driver/runtime/physical device NOT RUN. Budget reserve hint 2 GiB per card (not actual measured headroom); engine may clamp and additional buffers may be needed. Explicit GPU restart temporarily requires Stop/Start (before stopping), no automatic restart/CPU fallback. Legacy profile/API/Bridge retained. Tests authored: synthetic 16+8, manual 2+2, auto, full, invalid/missing/overlap, admission+CLI and stop isolation; execution CI PENDING. P1 OPEN: Client controls (prelaunch/chat), auto default migration, per-card desired/assigned/observed telemetry and status attribution, safe explicit shared-card reservations with multiple models, atomic GPU restart path, hardware tests including KAT/Qwen on 4070Ti SUPER+3070. No claims of installed functionality or actual VRAM pooled. LOCAL-PLAN-01 12:53:05+05, SHA b215ef9882542d5e38590965b8635b8c8039320eaf87f7626f9c7137c97831ee; archive 1071b531a3985ecb08d474651f73cedaf5aeb73cec1108b19daf764848fb4102. M1-10 HOLD unchanged. Evidence: [P0 report](../Test/MULTI-GPU-01/report.md).


**Примечание о бренде:** правильное публичное название «Нейрополис» / Neuropolis. До обновления установленной версии #150 в интерфейсе может оставаться прежнее ошибочное написание; технические пути и ярлык не переименовываются.


**WORK, 26.11.2026 — установка #150 подтверждена технически.** На рабочем ПК Client и Manager обновлены совместимой парой, Manager ONLINE, Client на http://127.0.0.1:55139/ обслуживает новые ресурсы. История/подключение сохранены. Визуальная проверка и реальная генерация владельцем ещё не выполнены. LIVE доступен при достоверном активном измерении; AVG пока «—». Автозапуск Manager после перезагрузки не настроен. HOME и Server77 этой установкой не обновлялись.


## Статистика модели и панели — source candidate, не установленная функция

В исходниках предусмотрены LIVE в строке слота, в списке выбора модели и в карточке «Статистика модели», режим CPU/CUDA и среднее текущего запроса. Накопительная AVG пока отображает «—»: постоянное хранилище и финальная достоверная метрика ещё не реализованы. Для регулировки высоты тянуть нижнюю ручку или пользоваться стрелками клавиатуры; порядок менять перетаскиванием верхней ручки или кнопками ↑/↓; размеры и порядок сохраняются локально, кнопка сброса восстанавливает исходное расположение. CI, установка и пользовательская проверка ещё не подтверждены.


**Инструкция владельца / администратора, 26.11.2026.** Не требует знания Python. Состояние интерфейса сверено по исходникам #147 `aa78b3498d64f4d3601d192afc3cbfa178969e5a`; установленные версии могут отличаться. Разделы «Предложение» ещё не реализованы. Настройки из примеров не применять поверх работающей установки без проверки и отдельного разрешения. Техническая процедура установки и отката: [[18_Техническая_документация]], DEPLOYMENT-01. Текущий статус: [[13_Тактический_контекст]].

## 1. Как всё связано

```text
Браузер → локальный Web Client (127.0.0.1)
             │ HTTPS + проверка сертификата + личный токен
             ├─ HOME Manager → CPU/CUDA модели
             ├─ Server77 Manager → CPU/CUDA модели
             └─ WORK Manager → CPU/CUDA модели (через VPN после приёмки)
Студия Нейрополис → локальный Client Bridge v1 → тот же Client/Manager
```

Client — рабочее место пользователя: список серверов, подключение, чаты, управление разрешёнными слотами. Manager — серверная сторона: права, модели, экземпляры, ресурсы, фактические параметры запуска. Один Client может работать с несколькими Manager; один Manager — с несколькими отдельно зарегистрированными Client. Закрытие браузера/Client не останавливает модели. Явный Stop в слоте — отдельная операция. История Client хранится локально. Bridge — отдельный защищённый интерфейс уже существующего Client, не заменяет Manager и не нужен для обычного подключения Client к Manager.

## 2. Что узнать перед подключением

Сохранить паспорт каждого узла в **личном защищённом хранилище**, не в GitHub. Для нового соединения нужны: имя, неизменный Manager ID, фактический IP/DNS и HTTPS-порт, доверенный публичный сертификат/CA и его SHA-256, уникальный Client ID, IP источника, разрешённые слоты/модели/роли. Узнать, какая версия реально запущена. Не копировать чужую регистрацию, токен или приватный TLS-ключ.

| Узел | Известный ранее endpoint | Что проверить сейчас |
| --- | --- | --- |
| HOME | LAN 192.168.0.9:18443 | HOME Manager ID и фактический bind/cert/права |
| Server77 | LAN 192.168.0.77:8443, manager-server77 | Текущая доступность и права |
| WORK | локальный 127.0.0.1:18443, work-43paebo | LAN/VPN listener пока не принят; будущий 10.253.77.3:18443 |
| Web Client | локальный 127.0.0.1, порт назначается при запуске | Не путать порт браузера с HTTPS Manager |

Адреса — известные ранее частные адреса данного проекта, не универсальные значения; перед применением сверить с действующим узлом. Никаких секретов и публичного IP HOME в документе.

## 3. Подключение через существующий интерфейс

1. Запустить штатный Web Client. В «Обзор серверов» нажать «Подключить сервер» или «Подключить Manager».
2. Ввести название сервера (произвольная подпись), точный ID Manager, собственный ID Client, IP/DNS, HTTPS-порт. Импортировать публичный сертификат .pem/.crt, полученный от администратора доверенным способом. Сверить отпечаток SHA-256 по независимому каналу. Если адрес другой, сертификат должен подтверждать этот адрес/имя.
3. Нажать «Создать профиль →». Client сам создаёт отдельный секретный токен, сохраняет профиль и пробует отправить заявку через HTTPS. Токен не копировать, не вставлять в браузер/чат. Для старой версии Manager может быть предложен SHA-256 регистрации — это не исходный токен. Профиль может сохраниться даже при недоступном Manager.
4. На стороне Manager администратор предварительно разрешает точный IP Client, затем одобряет его Client ID и доступные слоты. В уже авторизованном Client с ролью pairing_admin доступно «Заявки на доступ»: выбрать Manager, проверить заявку, источник и нужные слоты, подтвердить. Первый административный доступ назначает владелец на Manager, не сам новый Client. При необходимости отдельно разрешить управление моделями. Для нового IP заявка может быть отклонена до предварительного разрешения.
5. Вернуться в новый Client, «Повторить заявку» при необходимости, затем «Обновить». Проверить ONLINE, верный Manager ID, видимые разрешённые слоты и фактический статус. Для простого подключения модели не запускать. Доступ к чату и управление Start/Stop — отдельные права/действия.
6. Если Manager уже зарегистрирован, мастер откажется заменять существующие credentials. Не удалять профиль/историю или токен ради смены endpoint. Изменение существующего адреса/сертификата выполняется через согласованную процедуру backup/validation; полноценный редактор профиля — предложение ниже.

## 4. Карта параметров подключения — где они сейчас

На Client по умолчанию Windows хранит настройки в `%LOCALAPPDATA%\UltraLLM\Client\managers.json`; сертификаты и отдельные *.token рядом в защищённой папке. Может быть задан другой --config-dir. На Manager файл private\manager.json: HOME `S:\Ultra_LLM\Menager\private\manager.json`; Server77 `C:\ProgramData\UltraLLM\Manager\private\manager.json`; WORK проверять фактическую конфигурацию task под `D:\Neyro\Menager`. Не раскрывать содержимое приватных файлов.

| Понятие | Client (сейчас) | Manager (сейчас) | Правило |
| --- | --- | --- | --- |
| Название | мастер, display_name | display_name | подпись может отличаться; не идентификатор |
| ID Manager | мастер, manager_id | manager_id | точное совпадение, стабильный |
| ID Client | мастер, client_id | clients[].client_id | отдельная регистрация для клиента |
| Адрес | мастер host + port → endpoint | bind_host, listen_port | endpoint доступен клиенту, bind — локальный IP сервера |
| HTTPS-порт | мастер port | listen_port | совпадает; диапазон 1024–65535 |
| Сертификат | мастер; ca_cert | cert_file, key_file | публичное доверие на Client; приватный ключ только Manager; TLS не отключать |
| Токен | создаётся автоматически, token_file | clients[].sha256 | SHA-256 токена, не токен; отдельно от сертификата |
| IP доступа | реальный IP источника | allowed_client_ips | только точные literal private/loopback IP, не CIDR; firewall отдельно |
| Доступ к слотам | видимость/выбор разрешённых | clients[].allowed_slots | администратор выдаёт минимум |
| Модели и операции | разрешённый каталог/кнопки | clients[].allowed_models, control_models | Manager авторитетен; отсутствие права не обходить |
| Администрирование | «Заявки на доступ» при праве | clients[].pairing_admin | только владелец/уполномоченный администратор |
| Порт экземпляра | не вводится пользователем | slots[].api_port, slot_id | внутренний engine port, не HTTPS Manager |
| Веса и движок | каталог, доступные модели | colibri_root, models_root, control.reviews | пути и проверенные launch profiles — Manager |

Manager сейчас допускает один числовой private/loopback bind_host. 0.0.0.0 не допускается. Смена bind/port/TLS требует согласованной проверки конфигурации и перезапуска, не простой правки на работающем сервере. Операции pairing не заменяют firewall или TLS. См. исходники `Manager_Ultra_LLM/live_manager.py` (load_config), `Client_Ultra_LLM/web_client.py` (enroll_profile), `Client_Ultra_LLM/pairing_client.py` и [мастер #147](https://github.com/maxrus82gm-svg/local_LLM/blob/aa78b3498d64f4d3601d192afc3cbfa178969e5a/Client_Ultra_LLM/web_assets/index.html).

## 5. VPN HOME ↔ WORK: исторический план настройки (фактическое состояние — верхняя запись CONNECTION PASS)

Цель: обе машины видят друг друга по отдельной защищённой сети, обычный интернет/DNS/локальная сеть остаются без изменений. Прямая схема без VPS: HOME имеет статический публичный IPv4 (по сообщению владельца), принимает UDP 51820; WORK инициирует соединение. После handshake трафик двусторонний в разрешённых пределах. HOME WireGuard установлен, туннель/ключи и проброс UDP 51820 на HOME сообщены владельцем; фактическая конфигурация, WORK peer, handshake и HTTPS не подтверждены. Доступ к WORK был недоступен после сна/ожидания удалённого подтверждения; VPN отложен на время WEB35 интеграции. Не менять рабочую сеть без разрешения её администратора.

### 5.1. Настройка WireGuard (когда владелец возобновит задачу)

Скачать официальный клиент Windows: https://www.wireguard.com/install/. Установить штатно с правами администратора. Проверить, что адреса 10.253.77.2/32 и .3/32 не конфликтуют с существующими VPN/маршрутами. На каждой машине создать новый туннель и свой ключ; обменять только публичные ключи. Сохранить существующие конфигурации и правила. Шаблоны ниже — кандидаты, не готовые активные конфиги:

**HOME**

```ini
[Interface]
PrivateKey = <HOME_PRIVATE_KEY>
Address = 10.253.77.2/32
ListenPort = 51820

[Peer]
PublicKey = <WORK_PUBLIC_KEY>
AllowedIPs = 10.253.77.3/32
```

**WORK**

```ini
[Interface]
PrivateKey = <WORK_PRIVATE_KEY>
Address = 10.253.77.3/32

[Peer]
PublicKey = <HOME_PUBLIC_KEY>
AllowedIPs = 10.253.77.2/32
Endpoint = <HOME_STATIC_PUBLIC_IP>:51820
PersistentKeepalive = 25
```

На HOME роутере только UDP 51820 → закреплённый LAN IP HOME:51820; Windows firewall разрешает этот UDP для WireGuard. На WORK роутере проброс не нужен. Не указывать AllowedIPs=0.0.0.0/0, ::/0, DNS, маршруты физических LAN, не включать ICS/forwarding/NAT; не менять V2Ray/3X-UI. Не открывать TCP18443/8443 или engine порты наружу. Активировать HOME, затем WORK. В WireGuard сверить latest handshake и счётчики Rx/Tx на обоих. Ping — дополнительная проверка, ICMP может блокироваться. Сверить прежние маршруты/DNS и работоспособность обычной сети; не отключать firewall ради диагностики.

### 5.2. Подключение Manager через VPN — историческое проектное решение; реализовано #158–160 и установлено на WORK

**Историческое ограничение #156:** WORK Manager слушал 127.0.0.1:18443. Замена адреса потеряла бы локальное подключение. Не запускать второй Manager с общей DB. Реализованное решение #160: один Manager с двумя точными HTTPS listeners, primary прежний + optional VPN, общий handler/admission/DB, независимое восстановление VPN при позднем старте, единое завершение. HOME Manager аналогично сохраняет LAN bind и добавляет VPN listener только если WORK Client должен подключаться к нему. Ни wildcard, ни public bind.

| Направление | endpoint после реализации | source allowlist/firewall |
| --- | --- | --- |
| HOME Client → WORK Manager | https://10.253.77.3:18443 | WORK разрешает 10.253.77.2 → .3 TCP18443 |
| WORK Client → HOME Manager | https://10.253.77.2:18443 | HOME разрешает 10.253.77.3 → .2 TCP18443 |
| WORK Client → локальный WORK | https://127.0.0.1:18443 | существующее право, не менять |
| HOME Client → прежний HOME LAN | существующий endpoint | существующее право, не менять |

Перед подключением обоих направлений: exact CI, backup/idle gate, проверка сертификата SAN для используемого VPN IP/имени и доверия, отдельные регистрации/права на каждом Manager, scoped firewall. Только после появления реальных listeners проверять в PowerShell на HOME `Test-NetConnection 10.253.77.3 -Port 18443`, на WORK аналогично .2. Успешный TCP не подтверждает TLS/auth; затем wizard или согласованное обновление существующего профиля и ONLINE. Проверить оба направления, VPN off/on и что локальные Client продолжают работать. Reboot/autostart только после PASS; Start/Stop/генерация отдельно. Откат — отключить только новые WG-туннели, удалить только добавленные правила/port-forward; восстановить Manager из backup при безопасном idle, не сбрасывать сеть целиком. Полные технические gates и исторический план VPS — №18, актуален только DIRECT HOME↔WORK.

## 6. Диагностика подключения без перезапуска моделей

| Симптом | С чего начать |
| --- | --- |
| OFFLINE / timeout | питание/сон, сеть, WG handshake, точный endpoint, наличие Manager listener, scoped firewall |
| TCP есть, TLS error | SAN/имя/IP, срок действия, правильный публичный CA, отпечаток; не отключать проверки |
| 401 | регистрация/token mismatch, правильный профиль, не копировать чужие токены |
| 403 / access_denied | allowed_client_ips, slot/model permissions, роль; уточнить у администратора |
| Заявка сохранена, но не отправлена | pre-allow IP, доступность/версия Manager, повторить заявку |
| ONLINE, но нет модели | доступные слоты/права, engine/instance status; READY не означает отсутствие запросов |
| VPN handshake есть, но HTTPS недоступен | проверить optional listener; не открывать WAN и не менять primary bind |
| После Stop занята VRAM | проверить точный экземпляр/PID/released, порты и другие приложения; не убивать процессы по имени |

## 7. Предложение по размещению настроек в будущем UI (на утверждение)

**Web Client → Настройки → Подключения Manager.** Карточка каждого Manager: имя, стабильный ID, список разрешённых endpoint (локальный/LAN/VPN), Client ID, сертификат (fingerprint/срок/SAN), статус TCP/TLS/Auth/API, время последней проверки, доступные роли. Действия: добавить, проверка соединения без генерации, изменить endpoint с проверкой identity и backup, запросить/отозвать регистрацию с подтверждением. Секреты не показывать; ротация отдельным действием. Не менять права Manager из обычного Client.

**Manager → Настройки → Сеть и доступ.** В будущем собственный локальный административный UI Manager: идентификация узла, primary и optional VPN bind/port, сертификат и срок, IP allowlist, заявки и список Client (кто, какие слоты/модели/права), роли, журнал изменений. Смена сети/TLS/порта: показать текущие и ожидаемые настройки, выполнить validate/dry-run, сохранить backup, явное применение и уведомление о необходимости Restart, rollback при ошибке. Никакого silent restart. Удалённое администрирование через Client только по специальной роли/API и в разрешённом объёме; Manager остаётся источником истины.

**Manager → Настройки → Модели и ресурсы.** Пути engine/weights, CPU threads Auto/Manual/Max (будущее), CUDA/GPU mapping (будущее), контекст и лимиты, RAM/VRAM budget, Chain, слоты и профили. Client показывает поддерживаемые/разрешённые launch settings выбранного Manager, синхронизирует их по API, не хранит независимую «истину»; различать default / desired / applied / effective / observed. Изменение текущего чата (thinking, stream, reasoning, история) — в Client, не глобальная настройка Manager. Точные поля и значения модели сверять с текущей схемой, а не дублировать в этой инструкции.

**VPN** — отдельный транспорт ОС (WireGuard). В UI можно показывать его статус и разрешённый endpoint, но не хранить private keys в Client/Manager и не менять системные маршруты автоматически. Для настройки WireGuard использовать эту инструкцию и штатный WireGuard. Сохранить одинаковые возможности UI на всех машинах (FEATURE-REGISTRY-01), отсутствующее оборудование/права явно показывать как недоступное, CONFIG-UI-PARITY-01. Реализация, интерфейс, размещение пунктов и расширение API требуют отдельного согласования; это предложение, не готовая функция.

## 8. Ссылки

- [[00_Старт]] — вход в проект; [[13_Тактический_контекст]] — текущий статус и приоритет.
- [[18_Техническая_документация]] — DEPLOYMENT-01, конфигурация, безопасность, VPN, откат.
- [[07_Задачи Codex]] — только назначенные задачи; [[05_Реестр_задач]] — история статусов.
- [GitHub local_LLM](https://github.com/maxrus82gm-svg/local_LLM), [официальный WireGuard](https://www.wireguard.com/).
