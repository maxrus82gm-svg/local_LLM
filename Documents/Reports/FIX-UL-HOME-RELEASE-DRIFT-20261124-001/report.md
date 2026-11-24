# FIX-UL-HOME-RELEASE-DRIFT-20261124-001 — отчёт исполнителя

**Вердикт:** `INSTALLED / TECHNICALLY VERIFIED / OWNER MODEL ACCEPTANCE PENDING`.

HOME Manager обновлён полным штатным source-release из программной основы №127 `95503306e32cf334d3c7635795ece9e367a258af`. Текущий документационный HEAD на момент финальной проверки — №135 `2bdb7f249bf593b14a46f1d2793fb97e9a2aa6cd`; `Manager_Ultra_LLM` и `Client_Ultra_LLM` между №127 и №135 не менялись. Реальные Start/Restart/generate/Stop KAT и CUDA не выполнялись: карточка оставляет эти действия владельцу либо требует отдельного явного разрешения.

## DONE

- Выполнен read-only preflight HOME: точные task/process/path/port/config/SQLite/ACL/Client facts, без вывода секретов.
- Подтверждён drift установленного Manager: из 21 payload-файла 13 совпадали с №127, 7 отличались, `restart_runtime.py` отсутствовал; `restart_jobs` отсутствовала.
- До cutover подтверждены `integrity=ok`, 5 исторических `STOPPED/released`, 0 unreleased, 0 активных engine-listener на `8016/18001/18002`, 0 активных соединений Client.
- Штатным `manager_release.py` собран и дважды проверен полный пакет: 21 runtime payload + `RELEASE.json` + `SHA256SUMS.txt`, ZIP SHA256 `a73cdc430229154308271b0d903c4520ed4d146674fa26b18e5efea2a2202884`.
- Созданы защищённые backups runtime/config/TLS/ACL/Task XML/instances/SQLite/Client state с online SQLite backup и manifest pin.
- Выполнен Manager-only scheduled-task cutover; manager ID `home-sc96d3u`, endpoint `192.168.0.9:18443`, task/action/config/TLS/registration/slots/reviews/paths сохранены.
- Штатный startup создал `restart_jobs`; ручного создания таблиц не было.
- Client-процесс оказался запущен в 12:00 ещё на исходниках №117. При отсутствии активных соединений он штатно остановлен через CSRF API и запущен из текущего source на том же порту `50158`, PID `34036→35376`.
- Финально оба Manager видны ONLINE; HOME Manager PID `22224`, 23/23 package members exact, Client history побитно сохранена.

## CHANGED

- HOME runtime: `S:\Ultra_LLM\Menager` теперь содержит полный пакет №127 и установленный `RELEASE.json`.
- HOME Manager SQLite: нативная миграция добавила пустую `restart_jobs`; остальные 5 instance rows сохранены.
- HOME Manager был штатно перезапущен существующей задачей `UltraLLM_Manager_LIVE`.
- HOME Client был штатно перезапущен без изменения source/config/history/порта.
- Документация №05/06/07/09/13/18 и этот отчёт обновлены. Git commit/push/merge не выполнялись.

Не изменялись Server77, WORK, WUA, WireGuard, engine/weights, model runtime reviews, firewall, Scheduled Task definition, TLS/auth, Client registrations, chat content.

## DIFF

| Проверка | До | После |
| --- | --- | --- |
| Manager release payload | 13 match / 7 diff / 1 missing | 23/23 package members exact |
| `restart_runtime.py` | отсутствовал | SHA256 `f31b23ef…e6b35` |
| `restart_jobs` | отсутствовала | создана штатно, 0 rows |
| Manager DB | integrity ok, 5 STOPPED, 0 unreleased | то же + restart schema |
| Manager process | PID 4012, stale runtime | PID 22224, №127 runtime |
| Client process | PID 34036, loaded before №127 | PID 35376, current source |
| Client history | 2 chats / 14 messages / 7 metrics | exact same bytes and counts |
| Client registrations | HOME + Server77 | exact files preserved, оба ONLINE |

## TESTS

| Gate | Фактический результат |
| --- | --- |
| Python/JS syntax | PASS |
| Negative controls | PASS |
| Manager full source suite | `442`, 0 fail/error, 1 expected skip; PASS on rerun |
| Client full source suite | `84`, 0 fail/error, 1 expected skip; PASS on rerun |
| Chrome control/status/restart | PASS |
| Chrome stream/reasoning/usage/composer | PASS |
| Chrome multi-slot/control/context override | PASS; synthetic context override `16384` end-to-end |
| Chrome independent chats/scroll/metrics | PASS |
| Installed release readback | 23/23 SHA256 exact |
| Manager/Client DB | обе `integrity=ok` |
| Restart API | authenticated nonexistent ID → `404 restart_not_found`, PASS |
| Native telemetry process audit | 16 s, 85 samples, 11 status + 11 catalog reads; 0 PowerShell/CMD child, 0 visible shell window; only `conhost.exe` and bounded `nvidia-smi.exe` observed |
| Actual KAT CPU Start/Restart 8192→16384/generation/Stop | `NOT RUN — OWNER ACTION` |
| Actual CUDA | `NOT RUN — runtime_review_required + separate OWNER stage` |

Первый harness-прогон выполнил сами 442/84 теста успешно, но post-test JSON writer упал из-за унаследованного пустого `GIT_CONFIG_VALUE_0`; обе матрицы полностью повторены в очищенном process environment и дали PASS. Первый cutover был автоматически откатан из-за дефекта проверочного скрипта: переменная `$home` конфликтовала с read-only `$HOME`, поэтому реальный ONLINE ошибочно считался timeout. Rollback readback подтвердил старые hashes/schema/ONLINE. Переменная исправлена на `$homeRow`, условие отдельно воспроизведено и полный cutover повторён успешно. Отдельный ad-hoc `chrome --dump-dom` live-smoke завершился ненулевым exit и не засчитан; четыре штатных Chrome harness прошли.

## BACKUP

- Успешный cutover: `S:\Ultra_LLM\Menager\private\release-home-133-20261124-233316`, manifest SHA256 `6bb4e0dd70f9eab2c884b0a8a8b689a0c6ef4646d1293db61230a6c4cd4603b1`.
- Первый fail-closed cutover/rollback: `S:\Ultra_LLM\Menager\private\release-home-133-20261124-233009`, manifest SHA256 `0f8c9d9ae7d7a6621f180c6d4cf789da4339a299eec1c8555c85d1e15af6af13`.
- Оба backup: 110 файлов, Manager/Client SQLite `integrity=ok`, ACL только SYSTEM/Administrators/REX, `bad_aces=0`; `ROLLBACK.txt`, runtime-before, private-before, Client state, instances и Task XML присутствуют.

## PROBLEMS

- Причина release drift устранена технически. Причинная связь с пользовательским симптомом KAT 8192→16384 ещё требует реального owner KAT lifecycle; сейчас честно `NOT RUN`.
- CUDA для KAT и Qwen3.6 остаётся `runtime_review_required`. Исторические 8 GiB/VRAM снимки не считаются свежим review. В текущем readback GPU было 8.0 GiB total / около 5.5 GiB free; это только моментный статус, не бюджет модели.
- У эвристики карточки «22 Manager + 17 Client» нет права подменять packager: действующий Manager packager требует 21 payload + 2 metadata. Client запускается непосредственно из совместимого source №127; portable EXE не перестраивался и не нужен для этого HOME размещения.

## REQUIREMENT MATRIX

| Требование | Статус |
| --- | --- |
| Manager ONLINE / прежний ID/endpoint | PASS |
| HOME + Server77 registrations | PASS |
| Full package / manifest / dependency check | PASS |
| Backup + rollback до stop | PASS |
| Native DB migration / restart API | PASS |
| History/settings/TLS/auth/Task preserved | PASS |
| Busy/engine/ownership preflight | PASS |
| No recurring shell windows | PASS by physical process observation; owner visual confirmation still welcome |
| CPU real lifecycle/context/status/brain/generation/cleanup | NOT RUN — OWNER |
| CUDA preparation | PARTIAL: inventory/budget/status checked; reviews missing, real launch forbidden |
| Permanent procedure | DONE in №18 |

## QUESTIONS

Нужна только OWNER ручная приёмка реальной KAT CPU цепочки ниже. Отдельно решить, выдавать ли явный GO на measured CUDA runtime review/launch после CPU PASS.

## OWNER SAFE CHECK

1. Открыть существующий Client `http://127.0.0.1:50158/`, обновить страницу, выбрать HOME/slot1/KAT CPU.
2. Явно Start с context 8192; подтвердить только показанные текущие warnings. Дождаться READY и записать instance_id/effective context.
3. Создать отдельный QA chat, получить короткий ответ и убедиться, что он сохранён.
4. Выбрать context 16384 и нажать Restart один раз; подтвердить штатные диалоги. Наблюдать STOPPING/WAITING_RELEASE/CHECKING/STARTING/READY без повторного POST.
5. Проверить новый instance_id, effective context 16384, зелёный READY, нейтральный индикатор мозга и сохранённую историю; получить второй короткий ответ.
6. Stop только exact QA instance; подтвердить `STOPPED/released`, отсутствие listener slot1/8016 и принадлежащей ему process chain. QA chat удалять только по желанию владельца.
7. При любом расхождении не запускать CUDA; сохранить статус/скриншот и вернуться к этому TASK evidence.

## DOC IMPACT / NEXT

№07 штатно ротирован: БЛОК 1 освобождён, дословная постановка сохранена в БЛОКЕ 1.1 с amendment; БЛОК 4 не менялся. NEXT — только owner KAT CPU acceptance, затем отдельное решение по CUDA. LOCAL-PLAN-01 финально прочитан `2026-11-24T23:42:50+05:00`, plan `8f2a756a…`, archive `1071b531…`, без изменений.
