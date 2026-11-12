"""Native Windows client for any number of authorised HTTPS Manager profiles.

Real data only. No embedded credentials and no server process control at P1.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from live_client import load_profiles, fetch_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    profiles = load_profiles(args.config.resolve())
    root = tk.Tk()
    root.title("Ultra LLM Client · LIVE")
    root.geometry("1040x610")
    root.minsize(760, 450)

    top = ttk.Frame(root, padding=12)
    top.pack(fill="x")
    ttk.Label(top, text="Ultra LLM · доступные менеджеры", font=("Segoe UI", 14, "bold")).pack(side="left")
    state_var = tk.StringVar(value="Подключение к менеджерам...")
    ttk.Label(root, textvariable=state_var, padding=(12, 0)).pack(fill="x")
    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)

    cols = ("manager", "host", "slot", "model", "engine", "availability", "ram")
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
    titles = {"manager": "Manager", "host": "Компьютер", "slot": "Слот",
              "model": "Модель", "engine": "Состояние", "availability": "Для клиента", "ram": "Свободно RAM"}
    widths = {"manager": 155, "host": 155, "slot": 72, "model": 250,
              "engine": 110, "availability": 145, "ram": 104}
    for col in cols:
        tree.heading(col, text=titles[col])
        tree.column(col, width=widths[col], minwidth=72, stretch=col in ("manager", "model"))
    tree.pack(side="left", fill="both", expand=True)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    scrollbar.pack(side="right", fill="y")
    tree.configure(yscrollcommand=scrollbar.set)

    foot = ttk.Frame(root, padding=(12, 0, 12, 12))
    foot.pack(fill="x")
    ttk.Label(foot, text="Только реальные данные · Нет прав START/STOP · Свободный слот не резервируется").pack(side="left")
    executor = ThreadPoolExecutor(max_workers=1)
    busy = False
    closing = False

    def render(rows):
        nonlocal busy
        if closing:
            return
        for item in tree.get_children():
            tree.delete(item)
        online = 0
        for row in rows:
            if row["status"] != "online":
                tree.insert("", "end", values=(row["name"], row["endpoint"], "—",
                            "—", "Ошибка", row["error"], "—"))
                continue
            online += 1
            data = row["data"]
            mem = data.get("memory", {})
            ram = str(mem.get("free_gib", "—")) + " GiB" if mem.get("state") == "live" else "?"
            for slot in data["slots"]:
                tree.insert("", "end", values=(
                    row["name"], data.get("host", ""), slot.get("slot_id", "—"),
                    ", ".join(slot.get("models") or []) or "—",
                    slot.get("engine_state", "unknown"),
                    slot.get("availability", "unknown"), ram))
            for model in data.get("models", []):
                tree.insert("", "end", values=(row["name"], data.get("host", ""),
                            "диск", model.get("directory_name", "—"),
                            "не проверена", "в каталоге", ram))
        state_var.set(f"Подключено: {online}/{len(profiles)} Manager · данные с серверов, не имитация")
        busy = False
        refresh_button.configure(state="normal")

    def refresh():
        nonlocal busy
        if busy or closing:
            return
        busy = True
        refresh_button.configure(state="disabled")
        state_var.set("Читаю состояние серверов...")
        future = executor.submit(fetch_all, profiles)
        def poll():
            if closing:
                return
            if future.done():
                try:
                    render(future.result())
                except Exception:
                    state_var.set("Ошибка чтения; проверьте конфигурацию и связь")
                    refresh_button.configure(state="normal")
                return
            root.after(100, poll)
        poll()

    refresh_button = ttk.Button(top, text="Обновить", command=refresh)
    refresh_button.pack(side="right")
    def close():
        nonlocal closing
        closing = True
        executor.shutdown(wait=False, cancel_futures=True)
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
