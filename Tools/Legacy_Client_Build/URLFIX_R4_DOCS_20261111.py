from pathlib import Path
root=Path(r"M:\GitHub\local_LLM_GPT_docs")
def doc(prefix):
    hits=list((root/"Documents").glob(prefix+"*.md"))
    assert len(hits)==1, prefix
    return hits[0]
def prepend(p, note):
    text=p.read_text(encoding="utf-8-sig")
    a=text.index("\n\n")+2
    p.write_text(text[:a]+note+text[a:],encoding="utf-8",newline="\n")
note=r"""## URLFIX-R4 LIVE — исправление локального 404 и повторного ярлыка (11.11.2026)

Причина: ссылка на локальный Client была дополнена ?utm_source=chatgpt.com. До R4 роутер сравнивал полный URL с /, поэтому отвечал 404 not_found. Теперь домашняя страница допускает query, но API и POST/CSRF остались строго защищены. Отдельно устранена зависимость открытия браузера от фонового Python: Start_Ultra_LLM_Client.vbs запускает EXE с --no-browser, проверяет localhost HTTP 200, Server: UltraLLMWeb/ через прямой WinHTTP и открывает системный браузер через ShellExecute.

QA: 35/35 Client PASS; изолированный R4 EXE GET / и /?utm_source=chatgpt.com HTTP 200, запросы с query к служебному API 404; CScript VBS exit 0. Сборка 69/69 файлов SHA256 PASS. R4 установлена в постоянную M:\UltraLLM_Client и запущена старым ярлыком. R3 сохранена в M:\UltraLLM_Builds\Stable_Backups\UltraLLM_Client_before_URLFIX_R4_20261111. Повторный запуск VBS exit0, Client остаётся одним экземпляром. Manager server77 ONLINE, 3 слота, истории/профили остались в защищённой пользовательской папке. Серверный Manager, Colibri и Valheim не изменены.

"""
prepend(root/"Client_Ultra_LLM/README.md",note)
prepend(doc("00_"),note.replace("## URLFIX-R4 LIVE","## NOW 11.11.2026 — URLFIX-R4 LIVE"))
prepend(doc("13_"),note.replace("## URLFIX-R4 LIVE","## NOW 11.11.2026 — URLFIX-R4 LIVE"))
j=doc("06_")
s=j.read_text(encoding="utf-8-sig")
marker="## Согласованные решения\n\n"
assert s.count(marker)==1
decision=r"""### 2026-11-11 — DEC-ULTRA-URLFIX-R4-018 — восстановление страницы и ярлыка

- Владелец показал 404 not_found по адресу Client с query и сообщил о неоткрывающемся ярлыке.
- Исправление: принимать tracking query только для корня /, оставить API защищёнными; VBS самостоятельно открывает подтверждённый локальный браузерный URL.
- Один постоянный ярлык, один Client, установка в M:\UltraLLM_Client. Новая R4 LIVE после полного backup R3 и 69/69 SHA256.
- Проверено: 35 Client tests PASS, изолированный EXE HTTP 200, реальный Client после установки HTTP 200 на адресе с ?utm_source, Manager77 ONLINE, 3 слота; повторный VBS exit 0. Работающие Colibri и Valheim не тронуты.
- Статус: CLIENT FIX LIVE PASS; окончательную видимость браузерной вкладки подтверждает пользователь.

"""
j.write_text(s.replace(marker,marker+decision,1),encoding="utf-8",newline="\n")
hist=doc("09_")
hist.write_text(hist.read_text(encoding="utf-8-sig").rstrip()+"\n\n"+note,encoding="utf-8",newline="\n")
print("DOC_UPDATE_SUCCESS",5)
