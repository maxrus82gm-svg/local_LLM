from pathlib import Path
import subprocess
root=Path(r"M:\GitHub\local_LLM_GPT_docs")
changes={
"Client_Ultra_LLM/README.md": r"""## PERMANENT LAUNCH POLICY — единый ярлык и рабочая папка (11.11.2026)

**Постоянная инсталляция:** \`M:\UltraLLM_Client\` (программа \`UltraLLMClient.exe\`, штатный \`Start_Ultra_LLM_Client.vbs\`). **Один существующий значок** \`C:\Users\REX\Desktop\Ultra LLM Client.lnk\` ссылается на \`wscript.exe "M:\UltraLLM_Client\Start_Ultra_LLM_Client.vbs"\` и **больше не перенастраивается при выпуске новых версий**. Версионные папки \`M:\UltraLLM_Client_CHAT01_R2\`, \`M:\UltraLLM_Client_UI01_R3\`, архивы \`M:\UltraLLM_Builds\Release\` — staging/история, не цели ярлыка.

**Обязательный цикл будущих обновлений:** (1) собрать выпуск в отдельную версионную папку и проверить полный SHA256SUMS; (2) только по согласованию штатно закрыть локальный Client, **не** Manager/Colibri; (3) перенести текущую \`M:\UltraLLM_Client\` в уникальную резервную папку; (4) скопировать новый выпуск на тот же постоянный адрес, сверить 100% SHA256 и проверить интерфейс/менеджеров; (5) открыть через **прежний, неизменённый ярлык**; при проблеме вернуть резервную папку. Никогда не заменять только EXE: нужен весь \`_internal\`. Секреты, профили Manager и история хранятся отдельно в \`%LOCALAPPDATA%\UltraLLM\Client\` и не переносятся в пакет.

**Выполнено 11.11:** после однократного возвращения ярлыка на постоянный адрес R3 установлена в \`M:\UltraLLM_Client\`; прежний WEB02 из этой папки сохранён в \`M:\UltraLLM_Builds\Stable_Backups\UltraLLM_Client_before_UI01_R3_20261111\`; прежний ярлык — в \`M:\UltraLLM_Builds\Shortcut_Backups\Ultra LLM Client_before_STABLE_UI01_R3_20261111.lnk\`. R2 завершён штатным /api/shutdown. Новый Client стартовал **через тот же ярлык**, localhost HTTP 200, новый UI с CPU/CUDA, старой таблицы нет; Manager server77 ONLINE, 3 слота, профиль сохранён. Серверный Manager LIVE не менялся: DDR-поля появятся после отдельного обновления Manager. Новую привязку ярлыка к версиям **не делать**.

""",
"Documents/00_Старт.md": r"""## Правило запуска — постоянная точка Client (11.11.2026)

**ВСЕГДА запускать с существующего ярлыка \`Ultra LLM Client\` → \`M:\UltraLLM_Client\Start_Ultra_LLM_Client.vbs\`.** Версионные сборки и ZIP хранятся отдельно и **никогда** не прописываются в ярлык. При следующем релизе сохранять старую рабочую папку и заменять содержимое \`M:\UltraLLM_Client\` целым проверенным portable-пакетом после согласованного завершения только локального Client. Настройки, токены и история в \`%LOCALAPPDATA%\UltraLLM\Client\` не затрагиваются. R3 через постоянный путь уже LIVE, Manager server77 ONLINE / 3 слота, R2 сохранён отдельно. Полный протокол в \`Client_Ultra_LLM/README.md\`.

""",
"Documents/13_Тактический_контекст.md": r"""## NOW 11.11.2026 — постоянный рабочий путь Client, новая UI01_R3 LIVE

Владелец повторно подтвердил неизменяемый ярлык на рабочем столе. **Фиксированный путь:** \`M:\UltraLLM_Client\Start_Ultra_LLM_Client.vbs\`, действующий \`M:\UltraLLM_Client\UltraLLMClient.exe\`. Однократная коррекция существующего ярлыка выполнена; **в следующих задачах запрещено переносить ссылку на CHATxx/WEBxx/Rx-каталоги**. Обновлять только целую рабочую папку с предыдущей в \`M:\UltraLLM_Builds\Stable_Backups\`, проверками SHA256 и обратимой заменой. История/доверенные профили остаются в личной защищённой папке.

**Live:** запущена именно UI01_R3 из постоянной папки через тот же значок; localhost 200, интерфейс показывает колонки START CPU/CUDA/STOP (disabled до CONTROL-01), старой таблицы слотов нет; \`manager-server77 ONLINE\`, слотов 3, существующий профиль не потерян. Переключение выполнено без остановки Manager, Colibri1 и Valheim. DDR4/48 GiB для Server77 ранее подтверждены ручной CIM-проверкой, но поле DDR в UI появится **после отдельной выкладки серверной версии Manager**. Не путать готовый UI с функциональными START/STOP.

""",
"Documents/06_Журнал_решений.md": r"""### 2026-11-11 — DEC-ULTRA-STABLE-LAUNCH-20261111-017 — ярлык не менять при релизах

- **Источник:** владелец Ultra LLM прямо потребовал вернуться к одному изначальному ярлыку, который при обновлениях не перенастраивается на разные версионные папки.
- **Принято:** постоянный домашний рабочий путь \`M:\UltraLLM_Client\`, запускаемый прежним ярлыком через \`Start_Ultra_LLM_Client.vbs\`. Версионные ZIP/папки — staging, не путь запуска. С каждого следующего релиза требуются backup текущей рабочей папки, проверка хешей всего пакета, согласованное завершение локального Client, копирование нового выпуска в постоянный путь, QA и rollback. Не менять существующий desktop shortcut ни на очередной R4, ни на любой будущий релиз.
- **Факт 11.11:** постоянная папка успешно обновлена до UI01_R3; исходная папка и прежний ярлык сохранены в backups; R2 завершён штатно; R3 стартовала через тот же ярлык, HTTP 200, новая разметка + Manager ONLINE + 3 слота подтверждены. Личные токены и чат-история сохранены вне установки. Live Manager, Colibri и Valheim не менялись.
- **Статус:** APPROVED AND VERIFIED; будущее обновление серверного Manager для новых read-only DDR-полей остаётся OPEN.

"""
}
assert subprocess.check_output(["git","-C",str(root),"branch","--show-current"]).decode().strip()=="GPT"
assert not subprocess.check_output(["git","-C",str(root),"status","--porcelain"]).strip()
for name,section in changes.items():
 p=root/name
 txt=p.read_text(encoding="utf-8-sig")
 if name.startswith("Documents/06_"):
  marker="## Согласованные решения\n\n"
  assert marker in txt and txt.count(marker)==1
  txt=txt.replace(marker,marker+section,1)
 else:
  end=txt.index("\n\n")+2
  txt=txt[:end]+section+txt[end:]
 p.write_text(txt,encoding="utf-8",newline="\n")
 print("DOCUMENTED",name)
