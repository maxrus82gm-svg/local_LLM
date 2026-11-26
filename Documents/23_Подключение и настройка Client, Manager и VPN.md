# 23 — Нейрополис: подключение и настройка Client, Manager и VPN

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

## 5. VPN HOME ↔ WORK: действующий план, пока не завершён

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

### 5.2. Подключение Manager через VPN — отдельная задача разработки

**Важное ограничение:** WORK Manager сейчас слушает 127.0.0.1:18443. Если просто заменить адрес на VPN, существующий локальный WORK Client потеряет подключение. Нельзя запускать второй Manager с общей DB. Предложение (не реализовано): один Manager с двумя точными HTTPS listeners, primary прежний + optional VPN, общий handler/admission/DB, независимое восстановление VPN при позднем старте, единое завершение. HOME Manager аналогично сохраняет LAN bind и добавляет VPN listener только если WORK Client должен подключаться к нему. Ни wildcard, ни public bind.

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
