# Ultra LLM Manager — исходный снимок и офлайн-проверка

## CHAT-01 LIVE на сервере 11.11.2026 — настоящий proxy к Colibri1

После приёмки коммита #18 на сервере `DESKTOP-KT4G5SM` staged-код проверен на существующем private config (MANAGER_CONFIGURATION_OK), затем **только** `UltraLLM_Manager_LIVE` контролируемо остановлен/запущен. Развернуты `live_manager.py` (SHA256 `E15EF6CCEA34FC4A6D7BA2AFC2A4A37D6739D9B48884DCD99D0A9BAA4584DA51`) и `chat_runtime.py` (SHA256 `FC69896CC40A64237FF3125299D21D8E4A49EC0B5F0AE6EC64C1D905B9755466`). Backup: `C:\Server\Ultra_LLM\Manager_Live\.rollback_CHAT01_20261111_018` (четыре прежних Python модуля); staging: `.staging_CHAT01_20261111_018`. Реальные TLS/config/allowed_client_ips/pairing_admin/Firewall и другие службы не изменялись.

**LIVE QA:** из существующего домашнего `home-rex` по проверенному TLS POST `/v1/chat` → реальный Colibri1/8000 с Qwen3.6 ответ `READY` за 4,36 с, usage 20 prompt + 1 completion. Установленный Web Client CHAT01 R2 выполнил два последовательных коротких запроса и сохранил 4 сообщения. Менеджер после установки `Running`, HTTPS 8443; Colibri1 и Valheim продолжают работать. 250/250 offline Manager PASS. `/v1/start` по-прежнему 405; никаких новых LLM не запускали. Colibri2/3 остаются not_running, 2–3 одновременных генерации ещё не проверены. Детали №18 §18.23.


## CHAT-01 — безопасная отправка к уже работающей модели (исходники; 11.11.2026)

Добавлен ограниченный `POST /v1/chat` для клиента с существующим Bearer и allowed_slots. Тело ровно `{"slot_id":"slot1","model_id":"...","messages":[{"role":"user","content":"Привет"}]}`. Manager сверяет реально доступную модель, текущие права, свежий LIVE_HOST snapshot и состояние слота; только после этого отправляет запрос на `http://127.0.0.1:<порт из конфигурации Manager>/v1/chat/completions`. Клиент не может указать произвольный URL, порт или путь. При ошибке сервер возвращает отказ и не имитирует ответ. Для первого этапа одновременно выполняется не более одного запроса чата на один слот; другие слоты могут обслуживаться независимо. START/STOP не добавлены. Для короткой первой проверки задано `max_tokens=512`, `stream=false` и явное отключение thinking; режимы streaming/reasoning позже.

**Статус:** код в `GPT`, тестовый API проходил локальный HTTP roundtrip с фиктивной Colibri, все настоящие веса/процессы не затрагивались. На действующем `UltraLLM_Manager_LIVE` это ещё **НЕ развёрнуто**, до отдельного разрешения владельца и проверенного backup/rollback. Старый `POST /v1/start` по-прежнему возвращает 405.


## WEB-03 действительно установлен на Server77 (11.11.2026)

После приёмки #15 все четыре серверных Python файла pairing взяты из `main`, SHA совпадает, на сервере compile/imports/config PASS. `UltraLLM_Manager_LIVE` на `DESKTOP-KT4G5SM` запущен с новой версией и слушает HTTPS 8443; домашний Client с проверенным CA получает реальный snapshot, admin API без прав — 401, START — 405. Старые `live_manager.py` и `pairing_server.py` сохранены в `C:\Server\Ultra_LLM\Manager_Live\.rollback_WEB03_20261111_015`; staging — `.staging_WEB03_20261111_015`. `manager.json`, TLS, FW/IP allowlist, Colibri1, Valheim не менялись. `pairing_admin` для существующего `home-rex` остаётся false: живое одобрение новой заявки ещё не проверялось и требует отдельного владельческого решения. Подробнее №18 §18.21.

## WEB-03 — подготовлен безопасный Web Pairing (НЕ включён в живом Manager)

Новые серверные модули `pairing_inbox.py` и `pairing_workflow.py`, расширение `live_manager.py` и `pairing_server.py`. Уже авторизованный владелец с отдельной административной ролью `pairing_admin=true` может из своей Web Client панели увидеть новые заявки, проверить ID и фактический IP, выбрать допустимые слоты и подтвердить/отклонить клиента. **Роль по умолчанию false**. Новый Client не может сделать себя администратором. Нет API для START/STOP/lease.

**LAN Manager API после будущего развёртывания:** `POST /v1/pairing/request` — разрешённый IP + клиентский ID + SHA256 собственного токена, ответ `202 pending` и случайный идентификатор заявки. `GET /v1/pairing/status/<ticket>` — статус только для исходного IP при знании квитанции. `GET /v1/pairing/requests`, `POST /v1/pairing/approve` и `POST /v1/pairing/deny` — только с существующим Bearer админа и его `pairing_admin` ролью. Очередь хранится в оперативной памяти (TTL 10 мин, максимум 24, лимит 5 заявок/10 мин с паузой ≥3 сек между принятыми заявками для IP), после рестарта заявки теряются и подаются повторно. Разрешение нового IP требует отдельного решения по Manager allowlist и Firewall: новая функция **не** открывает порты и не расширяет сеть. Manager TLS должен быть доверенным со стороны нового Client.

**Владельческое включение роли, после отдельного разрешения:** `pairing_server.py --config <защищённый manager.json> set-pairing-admin --client-id <существующий client_id> --enable`. Отзыв — `--disable`. Это локальная привилегированная административная операция на хосте Manager, не запускать её до приёмки/разрешения владельца. Подключение к Manager из браузера выполняет локальный Python-прокси, не JavaScript. Перед развёртыванием сервера нужна его резервная копия, независимый smoke и проверка rollback.

**Ресурсные ограничения:** сервер выдаёт только права просмотра разрешённых слотов; отсутствие admission/lease означает, что кнопки START/STOP остаются неактивными. Все административные записи в manager.json защищены существующим ACL + межпроцессным файловым замком + атомарной записью, с повторным чтением роли на каждом запросе. Исходные 16 файлов `manager_dev` не изменялись.

**Состояние тестирования:** на домашнем ПК 246/246 Manager и 28/28 Client тестов PASS, включая локальный синтетический HTTP протокол (не реальный сетевой HTTPS с новым Client), тайм-ауты/отказы/неадминов/гонки grant. `UltraLLM_Manager_LIVE` на сервере продолжает выполнять прежний READ-ONLY код, новая функция в нём **НЕ развёрнута**. После приёмки — отдельное согласованное обновление службы/бэкап, проверка TLS и полномочий админа; затем пользовательский end-to-end. Техническая документация №18 §18.20.



**Статус на 10.11.2026:** исходная разработка `manager_dev`, а не установленная производственная служба. Все 16 оригинальных файлов перенесены побайтово без изменения логики из `C:\Server\Ultra_LLM\Colibri\manager_dev`. Их точные размеры и SHA-256 сохранены в `Documents/18_Техническая_документация.md`, §18.10. Локальный `.gitattributes` отключает конвертацию окончаний строк Git для исходных `.py` и `index.html`, чтобы после принятия в `main` байты оставались идентичными серверному baseline.

Существующие модули специально сохраняют исходные взаимные импорты и серверные host/path guards. **Запускать на домашнем ПК режимы `--colibri2 start/stop` нельзя**; настоящий Colibri2 не запускался. `index.html` — прежний автономный макет UL-MGR-0A, не работающий API/UI сервера.

## Повторение офлайн-тестов

На домашнем компьютере с Python 3.12, PowerShell и доступной локальной исходной Colibri 2.1.0:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify_offline.ps1
```

Проверочный скрипт использует `S:\Ultra_LLM\Engine\Colibri\c\coli` и `version.py`, **временно** копирует их в соседний с этой папкой `c`, выполняет `unittest discover`, затем удаляет временную папку. Он отказывается работать, если `../c` уже существует, чтобы не удалять чужие файлы. При необходимости источник задаётся параметром `-ColibriSource`.

Первый непосредственный прогон тестов после миграции дал 221 PASS / 2 ERROR, потому что исходные тесты ожидают соседнюю папку `../c` (зависимость Colibri, а не модификация Manager). Повтор с точными исходниками Colibri 2.1.0: **223/223 PASS**. Временные зависимости не публиковать.

## Продолжение

Разработка и проверка исходников — на домашнем ПК в Git-репозитории `local_LLM`. Проверенную серверную копию затем доставлять отдельно, с резервной копией, версией и откатом. Не заменять текущую Colibri1, Valheim, системные службы, `setup.json` и секреты. Публичный API, авторизация, реальный Colibri2 START/STOP, служба и LAN — отдельные решения владельца.

Первый клиентский офлайн-макет находится в `../Client_Ultra_LLM`. Он не подключён к этому Manager.


## Live Manager P1 — реальный серверный мониторинг (10.11.2026)

`live_manager.py` — новая, **отдельная** от исходных 16 baseline-файлов серверная программа, стандартная библиотека Python 3.12, Windows. Снимок строится из фактической ОС (Get-CimInstance RAM, Get-NetTCPConnection), локальных `/health` и `/v1/models` каждой Colibri, а также каталогов установленной модели. Сервер `DESKTOP-KT4G5SM`: копия кода уже сверена SHA-256 с `C:\Server\Ultra_LLM\Manager_Live\live_manager.py`; реальная функция `live_snapshot()` там выполнена без запуска моделей.

**Статус запуска:** HTTPS-служба и клиентское подключение **ещё не запущены/не подтверждены**: защищённое создание серверной конфигурации и клиентских credentials через автоматизированный канал было заблокировано. Сертификат и приватный ключ созданы на сервере в `C:\ProgramData\UltraLLM\Manager\private` с закрытым ACL (silver, SYSTEM, Administrators); нельзя публиковать ключ или копировать его в Git. `manager.json` пока не создан, порт 8443 не открывался. Это не production-ready service.

Серверный конфиг `manager.json` задаёт `manager_id`, `display_name`, **явные** `bind_host`/`listen_port`, абсолютные `colibri_root`/`models_root`, `cert_file`/`key_file`, `slots` (slot_id, api_port, protected), `clients` (отдельные client_id, SHA-256 токена, allowed_slots). Эти параметры позволяют независимо развернуть Manager на любом подходящем Windows-компьютере, где установлен Colibri. Рабочие пути не задаются константами в новой программе. Перед запуском потребуется завершить безопасную подготовку этих настроек на конкретной машине и проверить права доступа.

Вызов после защищённой подготовки: `python -B live_manager.py --config <private_absolute_path_to_manager.json>`. API: только `GET /v1/snapshot` по **HTTPS**, для каждого клиента `Authorization: Bearer`, сравнение SHA-256 постоянного времени; любые POST отказываются выполнять управление. Менеджер не выставляет незащищённый HTTP в LAN. Пока нет server host как Windows Service и autorun. WinRM остаётся исключительно административным каналом.

Состояния реальны, но **не дают резервирования**: `ready_unreserved` означает, что Colibri ответила на health и её scheduler по моментному снимку не загружен; `busy`, `not_running`, `unknown`, `denied` — другие состояния. Каталог `files_present_unverified` не означает установленную или совместимую модель. `reservation_granted=false` до реализации атомарной выдачи ресурса в уже существующем серверном ядре. Пока нет реальных START/STOP, аренды слота и межклиентного назначения.

**Обязательное следующее инженерное решение:** после безопасного ввода credentials проверить настоящий HTTPS-обмен со второго компьютера; затем добавить server-side admission/leases/authenticated start только через существующие `manager_core`, `service_core`, `windows_process` и guard запуска. Не строить второй процессный движок.


### 11.11.2026 — защищённый loopback HTTPS, задача CHATGPT-UL-MGR-LAN-20261111-004

Исправлены ошибки fail-closed: при отсутствии или нулевой `scheduler.capacity` больше не сообщается `ready_unreserved` (теперь `unknown`); неавторизованному клиенту не выдаются PID, имена моделей и scheduler, а клиенту без разрешённых слотов — общий каталог моделей. `bind_host` проходит проверку числового IP и запрещает wildcard/multicast/link-local. **Персональные права проверяются только на сервере; статусы не являются бронью.**

Отдельный `test_live_manager.py` проверяет эти границы. Полный прогон существующих и новых тестов — **227/227 PASS** на домашнем ПК с защищённым временным исходным Colibri fixture.

`live_tls_smoke.py` проверен **на настоящем сервере DESKTOP-KT4G5SM**: временный HTTPS-listener на **127.0.0.1:18447** с реальным серверным TLS-сертификатом, реальным `/health` Colibri1 и локальной тестовой учётной записью. Отсутствующий/неверный тестовый token => 401; разрешённый тестовый клиент => 200; клиент без прав => `denied`. TLS certificate validation PASS, Qwen3.6 обнаружена. После теста порт закрыт, постоянная конфигурация и клиентские секреты НЕ созданы. Скрипт содержит только явно тестовый маркер, действующим доступом в LAN он не является. Результат: **PASS LOOPBACK HTTPS; LAN PAIRING NOT RUN / BLOCKED.**

Копия `live_manager.py` на сервере обновлена с сохранением старого файла `live_manager.py.before_TASK004`; SHA-256 домашнего нового кода и серверной копии совпадают. 16 первоначальных файлов Colibri Manager, Colibri1/8000, Valheim и системный firewall не меняли. Переход к рабочему LAN требует безопасного индивидуального credential provisioning вне Git и отдельного подтверждённого клиента.


## Pairing Manager / Client — этап 11.11.2026

`pairing_server.py`: создаёт `manager.json` либо добавляет/отзывает клиентскую запись на **своей** машине. Принимает лишь SHA-256 токена, выданного клиентской программой; исходный bearer-token на сервер не передаётся. `live_manager.py` перечитывает права при каждом запросе, так что `revoke` действует без рестарта. Конфиг сохраняется атомарно вне Git и только в папке с защищёнными ACL. Запуск, установка службы, firewall и управление моделями в pairing-скрипт НЕ входят.

Пример администраторской команды **после** получения 64-символьного SHA-256 от первого клиента (не выполнять с placeholder):

```powershell
$py='C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe'
$src='C:\Server\Ultra_LLM\Manager_Live\pairing_server.py'
& $py -B $src --config 'C:\ProgramData\UltraLLM\Manager\private\manager.json' create `
 --manager-id manager-server77 --name 'Ultra LLM Server 77' `
 --bind 192.168.0.77 --port 8443 `
 --colibri-root 'C:\Server\Ultra_LLM\Colibri' `
 --models-root 'C:\Server\Ultra_LLM\Base_LLM\Models' `
 --cert 'C:\ProgramData\UltraLLM\Manager\private\server-cert.pem' `
 --key 'C:\ProgramData\UltraLLM\Manager\private\server-key.pem' `
 --slot slot1:8000:protected --slot slot2:8001 --slot slot3:8002 `
 --allow-ip 192.168.0.9 --client-id home-rex `
 --token-sha256 '<64_HEX_DIGEST_FROM_CLIENT>' `
 --grant-slot slot1 --grant-slot slot2 --grant-slot slot3
```

Выходные данные: `manager.json` на сервере, не в Git; список разрешённых адресов указывает только на конкретный клиент LAN. При регистрации второго Client использовать `grant --client-id <ID> --token-sha256 <64_HEX> --grant-slot slot1`. Для отзыва `revoke --client-id <ID>`, запрещено отзывать последнего клиента при работающем сервере. Серверный сертификат и приватный ключ остаются на сервере. Порт 8443, firewall, Windows Service и доступ по интернету **пока не активированы**.

На реальном сервере проверены закрытые ACL, TLS и встроенный отзыв токена (401), отказ неизвестному IP (403), наличие действующей Colibri1/8000. Следующий gate — безопасное создание личного токена на домашней машине пользователем, запись его digest на сервере и фактическое соединение через LAN.


## Постоянный LAN Manager через Windows Task Scheduler — задача №7 (11.11.2026)

**Фактически установлен на DESKTOP-KT4G5SM:** отдельная задача `UltraLLM_Manager_LIVE` от `DESKTOP-KT4G5SM\silver` с `S4U / RunLevel Limited` (НЕ SYSTEM), триггер `AtStartup`, `StartWhenAvailable`, до 10 перезапусков с интервалом 1 минута. Код `C:\Server\Ultra_LLM\Manager_Live\live_manager.py`, Python 3.12, `manager.json` в отдельном защищённом каталоге ProgramData. Manager **только читает** Windows/Colibri, не запускает и не останавливает модели. Конфиг/токены/приватный TLS-ключ **не находятся в Git**.

**Контролируемая установка на другом Windows ПК:** скопировать проверенный код Manager на новый хост, создать там отдельную защищённую private-папку, настроить установленную Colibri, порты, менеджерский сертификат и индивидуальные client credentials через предыдущий pairing. На сервере администратор запускает (пример для нашего хоста, все пути и аккаунт подставляются под конкретный ПК):

```powershell
$hostDir = 'C:\Server\Ultra_LLM\Manager_Live'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Install `
    -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json' `
    -PythonExe 'C:\Users\silver\AppData\Local\Programs\Python\Python312\python.exe' `
    -TaskUser 'DESKTOP-KT4G5SM\silver'
```

Скрипт отказывается перезаписывать чужую задачу/firewall-rule, проверяет конфиг и IP, защищает `C:\ProgramData\UltraLLM\Manager\logs` через ACL, создаёт только firewall rule по IP/порту Manager с `RemoteAddress` из `allowed_client_ips` и привязкой к `python.exe`. На текущем сервере: local `192.168.0.77:8443`, единственный remote IP `192.168.0.9`, `Profile Any` обусловлен текущим Public-профилем Ethernet; это **не** открытие для всех LAN или Internet. Никаких правил на роутере нет.

Логи: `C:\ProgramData\UltraLLM\Manager\logs\manager.log`, стандартная ротация 2 MiB × 1 активный и 3 архива. Лог содержит время/IP и событие, не пишет Authorization-header/сырой URL. `--check-config` позволяет валидировать Manager без открытия TCP-порта. Приватные папки и логи не хранить в Workspace/Git.

**Контроль состояния:**

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Status -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json'
```

**Откат при аварии/необходимости отключить Manager** (не удаляет токены, TLS-ключ, логи, Colibri):

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$hostDir\Manage-ManagerTask.ps1" `
    -Action Remove -ConfigPath 'C:\ProgramData\UltraLLM\Manager\private\manager.json'
```

Резервная копия предыдущего файла `live_manager.py.before_TASK007` сохранена рядом с серверным Manager; восстановление файла допустимо **после** остановки задачи и проверки SHA-256. Исходный `Colibri\manager_dev` (16 файлов) не изменён.

**Приёмочное свидетельство:** `Manage-ManagerTask.ps1 Install` → задача Running, S4U, BootTrigger, 1 LAN-listener, firewall remote allowlist `192.168.0.9`. Домашний `live_client.py` вернул ONLINE / exit=0, Qwen3.6 в slot1/8000, slot2/3 not_running. Контролируемый Stop → listener 0, Start → новый PID и listener 1; повторный Client ONLINE. Colibri1 и Valheim остались работающими. Проверка штатного статуса скриптом вернула exit=0. **Перезагрузка Windows и авто-восстановление после искусственного crash НЕ тестировались** (без разрешения сервер не перезагружался).

**Важный долг по безопасности:** `silver` запущен с `RunLevel Limited`, но это всё ещё основная пользовательская учётная запись, а **не выделенный сервисный аккаунт**. Для усиленной эксплуатации рекомендуется отдельная непривилегированная локальная учётная запись с минимальными правами только на Python/Colibri read-only и private TLS key; переход — после отдельной приёмки. Нет автоматического продления TLS (текущий сертификат до 10.03.2027), мониторинг срока действия понадобится до истечения. N:M и персональные ACL поддерживаются на уровне конфигурации, реальный второй Client/Manager ещё не проверен.
