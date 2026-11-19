# Независимая проверка — Production Client R5 Enter

**Дата:** 19.11.2026  
**Задача:** `CODEX-UL-R5-MULTI-LLM-CONTROL-ENTER-20261119-001`  
**Проверял:** ChatGPT coordinator, через Desktop Commander на `DESKTOP-SC96D3U` и GitHub.  
**Статус:** `DEPLOY + AUTHENTICATED ONLINE PASS / OWNER UX PENDING`.  
**Публикация:** локальный документ; Git commit/push выполняет владелец. `CLEANUP PENDING`.

## Исходная точка и CI

- GitHub `main`: commit 80, `b553445eed7127998261c2cb67b333bdd8bcb69e`.
- GitHub Windows CI на том же SHA: `44560709070`, SUCCESS; Manager/Client/Chrome P0/P1 и negative controls PASS.
- Прежний Product Client: PID `35708`, exe SHA-256 `7614aecc6f97a5a8c1b126b745aa7d17e9dc8679774ba870ee68f18690c649df`, JS SHA-256 `193b21ddca48d39d3b0af4cf1ce0c95831a25757db8c1985476fb313af17f3b7`; live port `61761`.
- До переключения один Manager `online`; `slot1` `ready/ready_unreserved`, `slot2` и `slot3` `not_running`. Данные чатов и Manager-настройки существуют в отдельном пользовательском профиле, вне каталога EXE.

## Пакет и резервирование

- Проверен ZIP `UltraLLM_Client_R5_Enter_20261119_002.zip`: SHA-256 `ee89df4ae6c200d5ad3fe65a36a61a1b3c3958722491067cfc9215dd89f85263`.
- Проверен новый EXE: SHA-256 `715dd701d1ed6fdd2dac297cad82f9841bb5c6f4823698810cf2751236ec8ee7`.
- Проверен JS: SHA-256 `85eec8af97fb236a0f57c0466329da9ed2b08f1dbf29369ad0dd6658451e3856`.
- Все 72 записи `SHA256SUMS.txt` совпали; 73 файла в пакете.
- Резервная копия старой сборки: `Backups/Client_R5_before_Enter_20261119_01/`, все 73 файла проверены SHA-256.
- Вторая неизменённая старая копия: `Production/Client_R5_PREVIOUS_20261119_01/`, 73 файла. Отдельная staging-копия новой сборки до переключения также сверена, 73 файла.
- Приватные токены, сертификаты и историю чатов не копировали в репозиторий или отчёт и не меняли.

## LIVE переключение

1. Штатный `POST /api/shutdown` с CSRF остановил только старый Client PID `35708`; проверено освобождение порта `61761`.
2. Папка `Production/Client` заменена уже сверенной сборкой с сохранением старой папки `Production/Client_R5_PREVIOUS_20261119_01`.
3. Новый Client запущен из прежнего пути; PID `35768`, динамический loopback-порт `53979` на момент теста.
4. GET `/api/status`: Manager `online`, `slot1` `ready/ready_unreserved`; `slot2`, `slot3` `not_running`.
5. `/client.js`, действительно отдаваемый HTTP новым Client, имеет SHA-256 `85eec8af97fb236a0f57c0466329da9ed2b08f1dbf29369ad0dd6658451e3856`.
6. Профиль конфигурации и файл истории остаются на месте; history SQLite 36 864 байт, `managers.json` 311 байт. Текущие рабочие службы Manager R5, Qwen, Valheim не останавливали и не меняли.

## OPEN / OWNER UX

- Владелец должен открыть **новый** Client через штатный ярлык или актуальный loopback-порт, выбрать `slot1`, послать короткое сообщение кнопкой и Enter, проверить Shift+Enter, reasoning/stream и сохранение истории после F5.
- Проверка реального пользовательского чата и подтверждение USER UX до этого момента **NOT RUN**. Не выдавать запуск UI за доказательство генерации модели.
- В рабочей конфигурации Model Control по-прежнему выключен; эта операция обновила только Client, не включала CPU/CUDA control на рабочем Manager.
- Временные каталоги, обе резервные копии и `WorkEvidence` сохранять. Очистка только после независимой приёмки и явного разрешения владельца.
- Файл является черновиком координатора для публикации владельцем; Git write не выполнялся.
