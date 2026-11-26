"""Ultra LLM Manager: HTTPS monitoring, bounded chat and gated model control.

Inventory comes from THIS server, never a Client-supplied path or SMB.
Control defaults OFF; owner-enabled control reuses the isolated Colibri runner.
Chat requests can only reach a ready,
permitted, currently reported Colibri model on its configured loopback port.
TLS, per-client bearer hashes and distinct model-control permissions apply.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import socket
import ssl
import subprocess
import threading
import time
import math
from urllib.parse import urlsplit, parse_qs
import urllib.error
import urllib.request

from pairing_inbox import PairingInbox
from chat_runtime import ChatError, validate_request, select_backend, proxy_chat, proxy_stream
from control_runtime import ModelControl, ControlError
from chat_settings import policy as chat_policy, upstream_options


def _chat_listener(port):
    """Native selected-port identity; no PowerShell, RAM or other-slot probes."""
    from windows_process import NativeWindows
    native = NativeWindows()
    owners = {row["pid"] for row in native.listeners() if row["port"] == port}
    if len(owners) != 1:
        raise ChatError("slot_process_unverified", 409)
    with native.process(owners.pop()) as handle:
        identity = native.identity(handle)
    encoded = json.dumps(identity, sort_keys=True).encode()
    return identity["pid"], "legacy-" + hashlib.sha256(encoded).hexdigest()[:32]


def chat_snapshot(config, principal, slot_id):
    slots = [s for s in config["slots"] if s["slot_id"] == slot_id]
    if not slots:
        raise ChatError("unknown_slot", 404)
    if slot_id not in principal["allowed_slots"]:
        raise ChatError("slot_not_authorized", 403)
    port = slots[0]["api_port"]
    pid, identity = _chat_listener(port)
    health = _local_api_json(port, "/health")
    models = _local_api_json(port, "/v1/models")
    row = {"slot_id": slot_id, "pid": pid, "instance_id": identity, "models": [],
           "engine_state": "unknown", "availability": "unknown"}
    if isinstance(health, dict) and health.get("status") == "ok":
        row["engine_state"] = "ready"
        q = health.get("scheduler")
        if isinstance(q, dict) and all(type(q.get(k)) is int and q[k] >= 0 for k in ("active","queued","capacity")):
            row["availability"] = "ready_unreserved" if q["capacity"] > q["active"] and q["queued"] == 0 else "busy"
    if isinstance(models, dict) and isinstance(models.get("data"), list):
        row["models"] = [m["id"] for m in models["data"] if isinstance(m,dict) and type(m.get("id")) is str]
    # Verify the same process still owns the port after the metadata reads.
    if _chat_listener(port) != (pid, identity):
        raise ChatError("slot_process_changed", 409)
    return {"source":"LIVE_HOST", "viewer_id":principal["client_id"], "slots":[row],
            "engine_limits": {k:health[k] for k in ("context_tokens","max_tokens")
                              if isinstance(health,dict) and type(health.get(k)) is int}}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LOG = logging.getLogger("ultra-live-manager")
_POWERSHELL = r"powershell.exe"
_API_TIMEOUT = 2
_OS_TIMEOUT = 8
_MAX_REQUESTS = threading.BoundedSemaphore(4)


def live_request_sample(health):
    """Only one active engine request, no text or untrusted arbitrary fields."""
    if not isinstance(health,dict) or health.get("status")!="ok":
        return None
    scheduler=health.get("scheduler")
    items=health.get("live")
    if (not isinstance(scheduler,dict) or scheduler.get("active")!=1 or
            scheduler.get("queued")!=0 or not isinstance(items,list) or len(items)!=1):
        return None
    row=items[0]
    if not isinstance(row,dict) or row.get("state") not in ("reading","writing"):
        return None
    result={"state":row["state"]}
    for key in ("prompt_tokens","tokens","elapsed_s","read_s","tok_s","tok_s_now"):
        value=row.get(key)
        if type(value) not in (int,float) or not 0<=value<=1e12 or not math.isfinite(value):
            continue
        if key in ("prompt_tokens","tokens") and type(value) is not int:
            continue
        result[key]=value
    return result


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def _text_id(value, field):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Invalid " + field)
    return value



# Optional direct VPN ingress: one exact IPv4 peer and a distinct credential.
# The existing primary listener and grants are never expanded by this option.
_VPN_NETWORKS = tuple(ipaddress.ip_network(x) for x in
                      ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _vpn_ip(value):
    if type(value) is not str:
        raise ValueError("VPN requires literal private IPv4 addresses")
    ip = ipaddress.IPv4Address(value)
    if not any(ip in net for net in _VPN_NETWORKS):
        raise ValueError("VPN requires RFC1918 IPv4 addresses")
    return str(ip)


def validate_vpn(raw, known_ids, primary_clients):
    vpn = raw.get("vpn_listener")
    if vpn is None:
        return
    fields = {"enabled", "bind_host", "source_ip", "cert_file", "key_file", "client"}
    if type(vpn) is not dict or set(vpn) != fields or type(vpn["enabled"]) is not bool:
        raise ValueError("Invalid VPN listener fields")
    bind, peer = _vpn_ip(vpn["bind_host"]), _vpn_ip(vpn["source_ip"])
    if bind == peer or bind == str(ipaddress.ip_address(raw["bind_host"])):
        raise ValueError("VPN address must differ from peer and primary listener")
    for field in ("cert_file", "key_file"):
        if type(vpn[field]) is not str or not Path(vpn[field]).is_absolute():
            raise ValueError("VPN certificate and key require absolute local paths")
        if Path(vpn[field]).resolve() in (Path(raw["cert_file"]).resolve(),
                                          Path(raw["key_file"]).resolve()):
            raise ValueError("VPN TLS must not replace primary TLS files")
    if Path(vpn["cert_file"]).resolve() == Path(vpn["key_file"]).resolve():
        raise ValueError("Separate certificate and key files required")
    client = vpn["client"]
    if type(client) is not dict or set(client) != {
            "client_id", "sha256", "allowed_slots", "control_models"}:
        raise ValueError("VPN requires a separate, explicit client grant")
    _text_id(client["client_id"], "VPN client ID")
    if type(client["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", client["sha256"]):
        raise ValueError("VPN requires a client-generated SHA256, never the bearer token")
    if any(client["client_id"] == c["client_id"] or
           client["sha256"] == c["sha256"] for c in primary_clients):
        raise ValueError("VPN client must not reuse primary identity or credential")
    slots = client["allowed_slots"]
    if (type(slots) is not list or any(type(x) is not str or x not in known_ids for x in slots)
            or len(set(slots)) != len(slots) or type(client["control_models"]) is not bool):
        raise ValueError("Invalid VPN client permissions")


def vpn_request_config(current, startup_vpn, source_ip):
    """A saved change invalidates old VPN access until explicit restart."""
    if (not startup_vpn or not startup_vpn.get("enabled") or
            current.get("vpn_listener") != startup_vpn or
            source_ip != startup_vpn["source_ip"]):
        return None
    return {**current, "clients": [{**startup_vpn["client"], "pairing_admin": False}]}


def _vpn_private_file(value, config_file):
    path = Path(value)
    parent = config_file.absolute().parent
    if (not path.is_absolute() or path.parent.resolve() != parent.resolve()
            or path.is_symlink() or not path.is_file()):
        raise ValueError("VPN TLS files must be regular files in Manager private directory")
    for node in (path, *path.parents):
        if node.is_symlink() or node.is_junction():
            raise ValueError("VPN TLS paths may not traverse links or junctions")
    return path


def vpn_tls_context(vpn, config_file):
    from pairing_server import _trusted_parent
    _trusted_parent(config_file)
    cert = _vpn_private_file(vpn["cert_file"], config_file)
    key = _vpn_private_file(vpn["key_file"], config_file)
    if cert.resolve() == key.resolve():
        raise ValueError("Separate TLS files required")
    # A protected parent is necessary but an imported key may have its own
    # explicit broad ACL. Reject those before using it.
    import os
    if os.name == "nt":
        literal = "'" + str(key).replace("'", "''") + "'"
        script = (
            "$ErrorActionPreference='Stop'; $a=Get-Acl -LiteralPath " + literal +
            "; $bad=@('S-1-1-0','S-1-5-11','S-1-5-32-545','S-1-5-2');"
            "foreach($r in $a.Access){if($r.AccessControlType -eq 'Allow'){"
            "if($bad -contains $r.IdentityReference.Translate("
            "[Security.Principal.SecurityIdentifier]).Value){exit 8}}};exit 0")
        result = subprocess.run([_POWERSHELL, "-NoProfile", "-NonInteractive",
                    "-Command", script], capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise PermissionError("VPN private key ACL is not protected")
    elif key.stat().st_mode & 0o077:
        raise PermissionError("VPN private key must not be accessible by group/others")
    details = ssl._ssl._test_decode_cert(str(cert))
    names = details.get("subjectAltName", ())
    if not any(kind == "IP Address" and
               ipaddress.ip_address(value) == ipaddress.ip_address(vpn["bind_host"])
               for kind, value in names):
        raise ValueError("VPN certificate SAN does not match the VPN IP")
    now = time.time()
    if not (ssl.cert_time_to_seconds(details["notBefore"]) <= now <
            ssl.cert_time_to_seconds(details["notAfter"])):
        raise ValueError("VPN certificate is not currently valid")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    return context


def save_vpn_settings(config_file, expected, draft):
    """Local admin operation, guarded by the existing configuration lock.
    No model operation, firewall change, listener mutation or implicit restart.
    """
    from pairing_server import manager_config_lock, _write_config
    with manager_config_lock(config_file):
        current = load_config(config_file)
        if current.get("vpn_listener") != expected:
            raise ValueError("VPN settings changed; reopen settings before saving")
        current["vpn_listener"] = draft
        # Dynamic slot definitions are available even when not in static slots.
        known_ids = {x["slot_id"] for x in current["slots"]}
        options = current.get("control", {})
        if options.get("owner_go"):
            import sqlite3
            from contextlib import closing
            database = Path(options["state_dir"]) / "control.sqlite3"
            with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro",
                                         uri=True, timeout=1)) as db:
                known_ids.update(x[0] for x in db.execute("SELECT slot_id FROM slots"))
        validate_vpn(current, known_ids, current["clients"])
        if draft["enabled"]:
            vpn_tls_context(draft, config_file)
        # Keep the original bytes in the protected folder. Restore only the
        # VPN settings, not the whole config over newer grants, on rollback.
        import uuid
        backup = config_file.parent / ("manager.pre-vpn-" + uuid.uuid4().hex + ".json")
        with backup.open("xb") as stream:
            stream.write(config_file.read_bytes())
        _write_config(config_file, current, new=False)
        if load_config(config_file).get("vpn_listener") != draft:
            raise RuntimeError("VPN configuration readback mismatch")


def open_network_settings(config_file):
    """Local Windows desktop admin dialog; no web/remote administration API."""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from pairing_server import _trusted_parent
    import shutil
    import uuid
    import os
    config_file = _trusted_parent(config_file)
    config = load_config(config_file)
    initial = config.get("vpn_listener")
    saved = initial
    existing = initial or {}
    grant = existing.get("client", {})
    root = tk.Tk()
    root.title("Нейрополис Manager — Сеть и доступ")
    root.minsize(660, 520)
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Основное подключение (не изменяется): "
              + config["bind_host"] + ":" + str(config["listen_port"])).grid(
                  row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
    enabled = tk.BooleanVar(value=existing.get("enabled", False))
    ttk.Checkbutton(frame, text="Разрешить дополнительный VPN-вход",
                    variable=enabled).grid(row=1, column=0, columnspan=3, sticky="w")
    fields = {
        "bind_host": tk.StringVar(value=existing.get("bind_host", "")),
        "source_ip": tk.StringVar(value=existing.get("source_ip", "")),
        "cert_file": tk.StringVar(value=existing.get("cert_file", "")),
        "key_file": tk.StringVar(value=existing.get("key_file", "")),
        "client_id": tk.StringVar(value=grant.get("client_id", "")),
        "sha256": tk.StringVar(),
        "slots": tk.StringVar(value=", ".join(grant.get("allowed_slots", []))),
    }
    names = [("bind_host", "Локальный VPN IP"), ("source_ip", "Разрешённый IP клиента"),
             ("cert_file", "Публичный TLS-сертификат"), ("key_file", "Приватный TLS-ключ (файл)"),
             ("client_id", "Отдельный Client ID"), ("sha256", "SHA-256 регистрации"),
             ("slots", "Разрешённые slot ID (через запятую)")]
    for row, (name, label) in enumerate(names, 2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=fields[name], show="*" if name == "sha256" else "").grid(
            row=row, column=1, sticky="ew", padx=8)
        if name in ("cert_file", "key_file"):
            def browse(field=name):
                value = filedialog.askopenfilename(initialdir=config_file.parent,
                            filetypes=[("PEM", "*.pem"), ("Все файлы", "*.*")])
                if value:
                    fields[field].set(value)
            ttk.Button(frame, text="Выбрать…", command=browse).grid(row=row, column=2)
    control = tk.BooleanVar(value=grant.get("control_models", False))
    ttk.Checkbutton(frame, text="Разрешить запуск и остановку моделей (не администратор)",
                    variable=control).grid(row=9, column=0, columnspan=3, sticky="w", pady=5)
    ttk.Label(frame, text="Порт VPN совпадает с основным: " + str(config["listen_port"]) +
              ". Один отдельный VPN-клиент; локальные права сохраняются.").grid(
                  row=10, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="SHA-256 берётся из мастера регистрации Client. "
              "Пустое поле сохраняет прежний SHA только для того же Client ID.").grid(
                  row=11, column=0, columnspan=3, sticky="w")
    status = tk.StringVar(value="Сохранённые настройки; фактический VPN-доступ не проверен.")
    ttk.Label(frame, textvariable=status, wraplength=740).grid(
        row=15, column=0, columnspan=3, sticky="w", pady=10)

    def draft():
        cid = fields["client_id"].get().strip()
        digest = fields["sha256"].get().strip().lower()
        old_grant = (saved or {}).get("client", {})
        if not digest and old_grant.get("client_id") == cid:
            digest = old_grant.get("sha256", "")
        return {"enabled": bool(enabled.get()), "bind_host": fields["bind_host"].get().strip(),
                "source_ip": fields["source_ip"].get().strip(),
                "cert_file": fields["cert_file"].get().strip(),
                "key_file": fields["key_file"].get().strip(),
                "client": {"client_id": cid, "sha256": digest,
                           "allowed_slots": [v.strip() for v in fields["slots"].get().split(",") if v.strip()],
                           "control_models": bool(control.get())}}

    def guarded(action):
        try:
            action()
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
            # Exception messages from external tools/credentials are not displayed.
            messagebox.showerror("Настройка не выполнена", type(error).__name__ +
                                 ": проверьте поля, права и файлы сертификата.")

    def generate():
        ip = _vpn_ip(fields["bind_host"].get().strip())
        exe = shutil.which("openssl")
        if not exe:
            exe = filedialog.askopenfilename(title="Выберите доверенный openssl.exe",
                                             filetypes=[("OpenSSL", "openssl.exe")])
        if not exe:
            return
        if not messagebox.askyesno("Новый сертификат",
              "Создать отдельный сертификат для " + ip + " в защищённой папке Manager?"):
            return
        ident = uuid.uuid4().hex
        cert = config_file.parent / ("vpn-" + ident + ".cert.pem")
        key = config_file.parent / ("vpn-" + ident + ".key.pem")
        try:
            subprocess.run([exe, "req", "-x509", "-newkey", "rsa:3072", "-nodes",
                "-sha256", "-days", "365", "-subj", "/CN=" + ip,
                "-addext", "subjectAltName=IP:" + ip,
                "-addext", "extendedKeyUsage=serverAuth",
                "-addext", "basicConstraints=critical,CA:FALSE",
                "-keyout", str(key), "-out", str(cert)], check=True, timeout=35,
                capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            vpn_tls_context({"bind_host": ip, "cert_file": str(cert), "key_file": str(key)}, config_file)
        except BaseException:
            cert.unlink(missing_ok=True)
            key.unlink(missing_ok=True)
            raise
        fields["cert_file"].set(str(cert))
        fields["key_file"].set(str(key))
        status.set("Создан новый сертификат; настройки пока не сохранены.")
    def export():
        cert = _vpn_private_file(fields["cert_file"].get(), config_file)
        # Export only a public certificate, never the private key.
        pem = cert.read_text(encoding="ascii").strip()
        if "PRIVATE KEY" in pem:
            raise ValueError("Private key cannot be exported")
        der = ssl.PEM_cert_to_DER_cert(pem)
        dest = filedialog.asksaveasfilename(defaultextension=".pem",
                   initialfile="manager-vpn.cert.pem", filetypes=[("PEM", "*.pem")])
        if dest:
            with Path(dest).open("x", encoding="ascii") as f:
                f.write(pem + "\n")
            status.set("Публичный сертификат экспортирован. SHA-256: " +
                       hashlib.sha256(der).hexdigest())
    def save():
        nonlocal saved
        if not enabled.get() and saved is None:
            status.set("VPN отключён; изменений нет.")
            return
        new = draft()
        if not enabled.get() and saved is not None:
            new = {**saved, "enabled": False}
        if not messagebox.askyesno("Сохранить",
              "Сохранить настройки VPN? Для применения нужен явный перезапуск Manager после остановки моделей."):
            return
        save_vpn_settings(config_file, saved, new)
        saved = new
        fields["sha256"].set("")
        status.set("Сохранено; защищённая резервная копия создана. "
                   "Изменённый VPN-вход закрыт до явного перезапуска Manager.")
    def inspect():
        # Explicit one-shot native OS query, never in a polling loop.
        if os.name != "nt":
            status.set("Проверка слушателей доступна на Windows.")
            return
        command = ("$ErrorActionPreference='Stop'; "
                   "@(Get-NetTCPConnection -State Listen -ErrorAction Stop | "
                   "Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Compress")
        result = subprocess.run([_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=12, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = json.loads(result.stdout or "[]")
        if isinstance(rows, dict):
            rows = [rows]
        if rows is None:
            rows = []
        primary = {r["OwningProcess"] for r in rows if
                   r["LocalAddress"] == config["bind_host"] and r["LocalPort"] == config["listen_port"]}
        vpn = {r["OwningProcess"] for r in rows if
               r["LocalAddress"] == fields["bind_host"].get().strip() and
               r["LocalPort"] == config["listen_port"]}
        status.set("Основной TCP: " + ("есть" if primary else "нет") +
                   "; VPN TCP того же процесса: " + ("есть" if primary & vpn else "нет") +
                   ". TLS и авторизацию проверяйте с разрешённого Client.")
    def firewall():
        # Use the existing elevated Windows Firewall UI; no automatic broad rule.
        ip, peer = _vpn_ip(fields["bind_host"].get().strip()), _vpn_ip(fields["source_ip"].get().strip())
        if ip == peer:
            raise ValueError("VPN peer equals local IP")
        messagebox.showinfo("Брандмауэр Windows", "Создайте входящее правило TCP только для:\n"
            + "Локальный IP: " + ip + "\nУдалённый IP: " + peer +
            "\nЛокальный порт: " + str(config["listen_port"]) +
            "\nПрограмма: python.exe, запускающий Manager.\nНе открывайте порт на роутере. "
            "Проверьте, что нет более широкого разрешающего правила.")
        if os.name == "nt":
            subprocess.Popen(["mmc.exe", "wf.msc"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=12, column=0, columnspan=3, sticky="w", pady=8)
    for label, action in (("Создать TLS", generate), ("Экспорт публичного TLS", export),
                          ("Сохранить", save), ("Проверить TCP", inspect),
                          ("Брандмауэр", firewall)):
        ttk.Button(buttons, text=label, command=lambda a=action: guarded(a)).pack(side="left", padx=3)
    ttk.Label(frame, text="Не меняет WireGuard, основной адрес, историю или модели. "
              "Не запускайте второй Manager.").grid(row=13, column=0, columnspan=3, sticky="w")
    root.mainloop()


def load_config(file: Path):
    raw = _read_json(file)
    if not isinstance(raw, dict):
        raise ValueError("Invalid config")
    _text_id(raw.get("manager_id"), "manager_id")
    name = raw.get("display_name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Invalid display_name")
    for field in ("colibri_root", "models_root", "cert_file", "key_file"):
        value = raw.get(field)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("Missing absolute " + field)
    bind = raw.get("bind_host")
    if not isinstance(bind, str):
        raise ValueError("Explicit IP bind_host required")
    try:
        ip = ipaddress.ip_address(bind)
    except ValueError as error:
        raise ValueError("bind_host must be a numeric interface IP") from error
    if (ip.is_unspecified or ip.is_multicast or ip.is_link_local
            or not (ip.is_private or ip.is_loopback)):
        raise ValueError("Only explicit private/loopback binds allowed at LAN stage")
    port = raw.get("listen_port")
    if type(port) is not int or not (1024 <= port <= 65535):
        raise ValueError("Invalid listen_port")
    slots = raw.get("slots")
    if slots is None:
        from launch_contract import initial_instances
        slots=[{"slot_id":s.slot_id,"api_port":s.port,"protected":s.is_legacy} for s in initial_instances()]
        raw["slots"]=slots
    if not isinstance(slots, list) or not slots:
        raise ValueError("No slots")
    ids, ports = set(), set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("Invalid slot")
        _text_id(slot.get("slot_id"), "slot_id")
        if type(slot.get("protected", False)) is not bool:
            raise ValueError("Invalid slot protection")
        n = slot.get("api_port")
        if type(n) is not int or not 1024 <= n <= 65535:
            raise ValueError("Invalid API port")
        if slot["slot_id"] in ids or n in ports or n == port:
            raise ValueError("Duplicate slot/port")
        ids.add(slot["slot_id"])
        ports.add(n)
    allowed_ips = raw.get("allowed_client_ips")
    if not isinstance(allowed_ips, list) or not allowed_ips:
        raise ValueError("Explicit allowlist of client IPs required")
    normalized = []
    for address in allowed_ips:
        if not isinstance(address, str):
            raise ValueError("Invalid client IP")
        try:
            addr = ipaddress.ip_address(address)
        except ValueError as error:
            raise ValueError("Client allowlist must contain literal IP addresses") from error
        if (addr.is_unspecified or addr.is_multicast or addr.is_link_local
                or not (addr.is_private or addr.is_loopback)):
            raise ValueError("Only explicitly allowed private/loopback client IPs")
        normalized.append(str(addr))
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate allowed client IP")
    raw["allowed_client_ips"] = normalized
    clients = raw.get("clients")
    if not isinstance(clients, list) or not clients:
        raise ValueError("No client credentials")
    client_ids, token_hashes = set(), set()
    # Durable server-issued slot IDs are also valid pairing grants. Definitions
    # and ports stay in the controller DB; no client supplies a port or path.
    known_ids=set(ids)
    control_options=raw.get("control",{})
    if type(control_options) is dict and control_options.get("owner_go") is True:
        import sqlite3
        from contextlib import closing
        state_dir=control_options.get("state_dir")
        if type(state_dir) is str and Path(state_dir).is_absolute():
            database=Path(state_dir)/"control.sqlite3"
            if database.is_file() and not database.is_symlink():
                try:
                    with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=1)) as db:
                        known_ids.update(r[0] for r in db.execute("SELECT slot_id FROM slots") if type(r[0]) is str and _ID.fullmatch(r[0]))
                except sqlite3.Error:
                    raise ValueError("Dynamic slot registry unavailable") from None
    for client in clients:
        if not isinstance(client, dict):
            raise ValueError("Invalid client")
        _text_id(client.get("client_id"), "client_id")
        digest = client.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid client token digest")
        if client["client_id"] in client_ids or digest in token_hashes:
            raise ValueError("Repeated client")
        if type(client.get("pairing_admin", False)) is not bool:
            raise ValueError("Invalid pairing_admin role")
        if type(client.get("control_models", False)) is not bool:
            raise ValueError("Invalid control_models role")
        if client.get("allowed_models") is not None and (type(client["allowed_models"]) is not list
                or any(type(k) is not str or k not in __import__('resource_catalog').initial_catalogue()
                       for k in client["allowed_models"])):
            raise ValueError("Invalid allowed_models")
        client_ids.add(client["client_id"])
        token_hashes.add(digest)
        allowed = client.get("allowed_slots")
        if not isinstance(allowed, list) or any(x not in known_ids for x in allowed):
            raise ValueError("Invalid client access list")
    validate_vpn(raw, known_ids, clients)
    control = raw.get("control", {})
    if type(control) is not dict or type(control.get("owner_go", False)) is not bool:
        raise ValueError("Invalid control configuration")
    if control.get("owner_go"):
        import socket as host_socket
        if control.get("host", "").casefold() != host_socket.gethostname().casefold():
            raise ValueError("Control configured for another host")
        for field in ("state_dir", "instance_root"):
            value = control.get(field)
            if not isinstance(value, str) or not Path(value).is_absolute() or value.startswith("\\\\"):
                raise ValueError("Server-local control paths required")
        if type(control.get("reviews", {})) is not dict:
            raise ValueError("Invalid runtime reviews")
    chat_policy(raw)
    from resource_policy import validate_settings
    validate_settings(raw)
    return raw


_HARDWARE_RAM_CACHE = None
_HARDWARE_RAM_LOCK = threading.Lock()


def _hardware_ram():
    """Optional static DIMM metadata: probe once, hidden, not on every poll."""
    global _HARDWARE_RAM_CACHE
    with _HARDWARE_RAM_LOCK:
        if _HARDWARE_RAM_CACHE is None:
            stable = {}
            script = (
                r"$ErrorActionPreference='Stop';"
                r"$mem=@(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop);"
                r"$generation='';$installed=0.0;"
                r"if($mem.Count -gt 0){$kinds=@($mem|ForEach-Object{[int]$_.SMBIOSMemoryType}|Sort-Object -Unique);"
                r"if($kinds.Count -eq 1 -and $kinds[0] -eq 26){$generation='DDR4'}"
                r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 34){$generation='DDR5'}"
                r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 24){$generation='DDR3'};"
                r"$installed=[double](($mem|Measure-Object -Property Capacity -Sum).Sum)/1GB};"
                r"[pscustomobject]@{ddr_generation=$generation;installed_gib=$installed}|ConvertTo-Json -Compress")
            try:
                cmd = [_POWERSHELL, "-NoProfile", "-NonInteractive",
                       "-EncodedCommand", __import__("base64").b64encode(
                           script.encode("utf-16le")).decode("ascii")]
                result = subprocess.run(cmd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=_OS_TIMEOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    if isinstance(data, dict):
                        if data.get("ddr_generation") in ("DDR3", "DDR4", "DDR5"):
                            stable["ddr_generation"] = data["ddr_generation"]
                        installed = data.get("installed_gib")
                        if type(installed) in (int, float) and 0 < installed < 8192:
                            stable["installed_gib"] = round(float(installed), 2)
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
            # Cache failure as unknown too; never retry each status poll.
            _HARDWARE_RAM_CACHE = stable
        return dict(_HARDWARE_RAM_CACHE)


def _os_telemetry(ports):
    """Regular RAM and listening-PID telemetry via native Windows APIs."""
    from windows_process import NativeWindows
    native = NativeWindows()
    allowed = set(ports)
    data = native.memory()
    data["listeners"] = [row for row in native.listeners() if row["port"] in allowed]
    data.update(_hardware_ram())
    return data


def _local_api_json(port, path):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"Accept": "application/json"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=_API_TIMEOUT) as response:
            if response.status != 200:
                return None
            data = response.read(256 * 1024)
        return json.loads(data)
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return None


def _inventory_models(models_root):
    root = Path(models_root)
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.is_symlink() or len(out) >= 100:
            continue
        # Directory presence does not prove completed downloads or compatibility.
        metadata = any(x.is_file() for x in child.glob("*.gguf")) or any(
            x.is_file() for x in child.glob("*.colibri/config.json"))
        out.append({"directory_name": child.name[:128],
                    "evidence": "files_present_unverified",
                    "metadata_detected": bool(metadata)})
    return out


def _authorized_client(config, authorization):
    if not authorization.startswith("Bearer ") or len(authorization) > 256:
        return None
    token = authorization[7:]
    if len(token) < 32:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    selected = None
    for client in config["clients"]:
        if hmac.compare_digest(digest, client["sha256"]):
            selected = client
    return selected


def _snapshot_performance(health, binding, port, listener_before):
    """Only native decode samples tied to a still-running Manager stream.
    Never expose request/principal IDs or infer a cumulative average."""
    if binding is None or binding[1].is_set() or listener_before != binding[3]:
        return None
    sample = live_request_sample(health)
    if not sample or sample["state"] != "writing":
        return None
    try:
        if _chat_listener(port) != binding[3] or binding[1].is_set():
            return None
    except Exception:
        return None
    return {"instance_id": binding[2], "source": "engine_health",
            "current_tok_s": sample.get("tok_s_now"),
            "request_mean_tok_s": sample.get("tok_s")}


def live_snapshot(config, client, *, performance_bindings=None):
    slots = config["slots"]
    result = {"schema": "ultra.manager.live.v1", "source": "LIVE_HOST",
              "manager_id": config["manager_id"],
              "display_name": config["display_name"],
              "host": socket.gethostname(),
              "generated_at_utc": _utc_now(),
              "viewer_id": client["client_id"],
              "pairing_admin": bool(client.get("pairing_admin", False)),
              "admission_enabled": False,
              "reservation_granted": False,
              "memory": {"state": "unknown"},
              "slots": [],
              "models": _inventory_models(config["models_root"])}
    try:
        evidence = _os_telemetry([s["api_port"] for s in slots])
        result["memory"] = {"state": "live",
                            "total_gib": round(float(evidence["total_gib"]), 2),
                            "free_gib": round(float(evidence["free_gib"]), 2)}
        ddr = evidence.get("ddr_generation")
        if ddr in ("DDR3", "DDR4", "DDR5"):
            result["memory"]["ddr_generation"] = ddr
        installed = evidence.get("installed_gib")
        if type(installed) in (int, float) and 0 < installed < 8192:
            result["memory"]["installed_gib"] = round(float(installed), 2)
        listening = {int(s["port"]): int(s["pid"])
                     for s in evidence["listeners"]
                     if isinstance(s, dict) and isinstance(s.get("port"), int)
                     and isinstance(s.get("pid"), int)}
    except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        _LOG.warning("Host telemetry unavailable: %s", type(error).__name__)
        listening = {}
    for slot in slots:
        slot_id = slot["slot_id"]
        port = slot["api_port"]
        allowed = slot_id in client["allowed_slots"]
        row = {"slot_id": slot_id, "api_port": port,
               "protected": bool(slot.get("protected", False)),
               "pid": listening.get(port),
               "engine_state": "unknown",
               "models": [],
               "scheduler": None,
               "availability": "denied" if not allowed else "unknown",
               "reservation_granted": False}
        if result["memory"]["state"] == "live" and port not in listening:
            row["engine_state"] = "not_running"
            if allowed:
                row["availability"] = "not_running"
        elif port in listening:
            binding = (performance_bindings or {}).get(slot_id) if allowed else None
            listener_before = None
            if binding is not None:
                try:
                    listener_before = _chat_listener(port)
                except Exception:
                    pass
            health = _local_api_json(port, "/health")
            if binding is not None:
                performance = _snapshot_performance(health, binding, port, listener_before)
                if performance is not None:
                    row["live_performance"] = performance
            models = _local_api_json(port, "/v1/models")
            if isinstance(health, dict) and health.get("status") == "ok":
                row["engine_state"] = "ready"
                if allowed and type(health.get("context_tokens")) is int and health["context_tokens"]>0:
                    row["context_tokens"]=health["context_tokens"]
                queue = health.get("scheduler")
                if isinstance(queue, dict):
                    vals = [queue.get(k) for k in ("active", "queued", "capacity")]
                    if all(type(x) is int and x >= 0 for x in vals):
                        row["scheduler"] = dict(zip(("active", "queued", "capacity"), vals))
                if allowed:
                    if row["scheduler"] is None or row["scheduler"]["capacity"] == 0:
                        row["availability"] = "unknown"
                    elif (row["scheduler"]["active"] >= row["scheduler"]["capacity"]
                          or row["scheduler"]["queued"] > 0):
                        row["availability"] = "busy"
                    else:
                        row["availability"] = "ready_unreserved"
            if allowed and isinstance(models, dict) and isinstance(models.get("data"), list):
                row["models"] = [
                    str(m["id"])[:128] for m in models["data"][:30]
                    if isinstance(m, dict) and isinstance(m.get("id"), str)]
        if not allowed:
            # An unauthorised viewer gets no PID, model details or live scheduler.
            row.update(pid=None, models=[], scheduler=None)
        result["slots"].append(row)
    # Never disclose model catalog paths to clients lacking any slot grant.
    if not client["allowed_slots"]:
        result["models"] = []
    return result


def make_handler(config_file, config, inbox, *, controller=None):
    """HTTP handler; live role checks are repeated on every request."""
    chat_locks = {slot["slot_id"]: threading.Lock() for slot in config["slots"]}
    active_streams = {}
    streams_guard = threading.Lock()
    controller = controller or ModelControl(config)

    def restart_gate(slot_id, instance_id, principal):
        # Hold the same slot lock used by all Manager chat requests until READY
        # or ERROR. This is independent of browser tabs and Client instances.
        with streams_guard:
            lock = chat_locks.setdefault(slot_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ControlError("slot_chat_in_progress", 409)

        def verify_idle():
            try:
                current = controller.runtime_config(load_config(config_file))
                slot = next(s for s in current["slots"] if s["slot_id"] == slot_id)
                port = slot["api_port"]
                listener = _chat_listener(port)
                health = _local_api_json(port, "/health")
                queue = health.get("scheduler") if isinstance(health, dict) else None
                if (health.get("status") != "ok" or
                        not isinstance(queue, dict) or
                        any(type(queue.get(k)) is not int for k in ("active", "queued", "capacity")) or
                        queue["active"] != 0 or queue["queued"] != 0 or queue["capacity"] <= 0 or
                        _chat_listener(port) != listener):
                    raise ControlError("restart_activity_unknown", 409)
            except ControlError:
                raise
            except Exception:
                raise ControlError("restart_activity_unknown", 409) from None

        return lock.release, verify_idle

    controller.restart_gate = restart_gate
    class Handler(BaseHTTPRequestHandler):
        server_version = "UltraLLMManager/1.0"
        sys_version = ""
        def _reply(self, status, payload):
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)
        def _current(self):
            # Reload grants on EVERY request: revoke/rotate without a restart.
            # Never trust client-provided identity or X-Forwarded-For.
            try:
                current = load_config(config_file)
                if any(current[field] != config[field] for field in
                       ("manager_id", "bind_host", "listen_port",
                        "cert_file", "key_file", "slots", "colibri_root", "models_root")) or current.get("control") != config.get("control"):
                    self._reply(503, {"error": "manager_config_changed"})
                    return None
            except (OSError, ValueError, TypeError):
                self._reply(503, {"error": "configuration_unavailable"})
                return None
            vpn = getattr(self.server, "vpn_listener", None)
            if vpn is not None:
                current = vpn_request_config(current, vpn, self.client_address[0])
                if current is None:
                    self._reply(403, {"error": "vpn_source_or_config_not_permitted"})
                    return None
                if self.path.startswith("/v1/pairing/"):
                    self._reply(403, {"error": "vpn_local_registration_required"})
                    return None
            elif self.client_address[0] not in current["allowed_client_ips"]:
                self._reply(403, {"error": "source_not_permitted"})
                return None
            return controller.runtime_config(current)

        def _admin(self, current):
            client = _authorized_client(current, self.headers.get("Authorization", ""))
            if client is None:
                self._reply(401, {"error": "unauthorized"})
                return False
            if not client.get("pairing_admin", False):
                self._reply(403, {"error": "pairing_admin_required"})
                return False
            return True

        def _json_post(self, limit=4096):
            if self.headers.get("Transfer-Encoding"):
                self._reply(400, {"error": "unsupported_transfer_encoding"})
                return None
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._reply(415, {"error": "json_required"})
                return None
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= limit:
                    raise ValueError()
                payload = json.loads(self.rfile.read(n))
                if not isinstance(payload, dict):
                    raise ValueError()
                return payload
            except (ValueError, UnicodeDecodeError):
                self._reply(400, {"error": "invalid_json_body"})
                return None

        def do_GET(self):
            current = self._current()
            if current is None:
                return
            if self.path.startswith("/v1/control/restart?"):
                principal = _authorized_client(current, self.headers.get("Authorization", ""))
                if principal is None:
                    return self._reply(401, {"error": "unauthorized"})
                try:
                    q = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if (len(self.path) > 256 or set(q) != {"request_id"}
                            or len(q["request_id"]) != 1):
                        raise ValueError()
                    return self._reply(200, controller.restart_status(principal, q["request_id"][0]))
                except ValueError:
                    return self._reply(400, {"error": "invalid_request_id"})
                except ControlError as error:
                    return self._reply(error.status, {"error": error.reason})
            if self.path.startswith("/v1/control/cuda_status?"):
                principal=_authorized_client(current,self.headers.get("Authorization",""))
                if principal is None:return self._reply(401,{"error":"unauthorized"})
                try:
                    q=parse_qs(urlsplit(self.path).query,strict_parsing=True)
                    if len(self.path)>256 or set(q)!={"slot_id","instance_id"} or any(len(v)!=1 for v in q.values()):
                        raise ValueError()
                    slot_id,identity=q["slot_id"][0],q["instance_id"][0]
                    if not _ID.fullmatch(slot_id) or not re.fullmatch(r"[a-f0-9]{32}",identity):
                        raise ValueError()
                    return self._reply(200,controller.cuda_status(principal,slot_id,identity))
                except ValueError:
                    return self._reply(400,{"error":"invalid_query"})
                except ControlError as error:
                    return self._reply(error.status,{"error":error.reason})
                except Exception:
                    return self._reply(503,{"error":"control_unavailable"})
            if self.path.startswith("/v1/chat/telemetry?"):
                principal=_authorized_client(current,self.headers.get("Authorization",""))
                if principal is None:return self._reply(401,{"error":"unauthorized"})
                try:
                    q=parse_qs(urlsplit(self.path).query,strict_parsing=True)
                    if len(self.path)>512 or set(q)!={"slot_id","instance_id","request_id"} or any(len(v)!=1 for v in q.values()):
                        raise ValueError()
                    slot_id,identity,request_id=(q[k][0] for k in ("slot_id","instance_id","request_id"))
                    if not re.fullmatch(r"[a-f0-9]{32}",request_id) or not re.fullmatch(r"(?:legacy-)?[a-f0-9]{32}",identity):
                        raise ValueError()
                except ValueError:
                    return self._reply(400,{"error":"invalid_query"})
                if slot_id not in principal["allowed_slots"]:
                    return self._reply(403,{"error":"stream_not_authorized"})
                key=(principal["client_id"],request_id)
                empty={"manager_id":current["manager_id"],"slot_id":slot_id,"instance_id":identity,"request_id":request_id,"live":None}
                with streams_guard:item=active_streams.get(key)
                if item is None or item[0]!=slot_id or item[2]!=identity or item[1].is_set():
                    return self._reply(200,empty)
                if not _MAX_REQUESTS.acquire(blocking=False):return self._reply(200,empty)
                try:
                    slot=next(s for s in current["slots"] if s["slot_id"]==slot_id)
                    port=slot["api_port"]
                    if _chat_listener(port)!=item[3]:
                        return self._reply(200,empty)
                    health=_local_api_json(port,"/health")
                    sample=live_request_sample(health)
                    if _chat_listener(port)!=item[3]:sample=None
                    # Recheck managed instance identity and request ownership,
                    # including cancellation/release during the health read.
                    owned=controller.chat_binding(slot_id)
                    if (owned or item[3][1])!=identity:sample=None
                    with streams_guard:
                        if active_streams.get(key) is not item or item[1].is_set():sample=None
                    return self._reply(200,{**empty,"live":sample})
                except Exception:
                    return self._reply(200,empty)
                finally:
                    _MAX_REQUESTS.release()
            if self.path == "/v1/snapshot":
                client = _authorized_client(current, self.headers.get("Authorization", ""))
                if client is None:
                    return self._reply(401, {"error": "unauthorized"})
                if not _MAX_REQUESTS.acquire(blocking=False):
                    return self._reply(503, {"error": "busy"})
                try:
                    with streams_guard:
                        bindings = {item[0]: item for item in active_streams.values()
                                    if item[0] in client["allowed_slots"] and not item[1].is_set()}
                    data = (live_snapshot(current, client, performance_bindings=bindings)
                            if bindings else live_snapshot(current, client))
                    data["control"] = controller.catalog(client)
                    by_slot = {i["slot_id"]:i for i in data["control"].get("instances",[]) if not i.get("released")}
                    for row in data["slots"]:
                        if row["slot_id"] in by_slot:
                            row["instance_id"] = by_slot[row["slot_id"]]["instance_id"]
                        elif row.get("engine_state") == "ready" and row["slot_id"] in client["allowed_slots"]:
                            try:
                                row["instance_id"] = _chat_listener(row["api_port"])[1]
                            except Exception:
                                row["instance_id"] = None
                    # A stream may finish or restart while catalog is being read.
                    with streams_guard:
                        active = {item[0]: item for item in active_streams.values()
                                  if not item[1].is_set()}
                        for row in data["slots"]:
                            sample = row.get("live_performance")
                            if sample is not None and (
                                row["slot_id"] not in client["allowed_slots"]
                                or active.get(row["slot_id"]) is not bindings.get(row["slot_id"])
                                or row.get("instance_id") != sample["instance_id"]
                                or row.get("engine_state") != "ready"
                            ):
                                row.pop("live_performance", None)
                    data["chat"] = {"streaming":True, "reasoning_events":True, "live_telemetry":True,
                                    "transport_policy":chat_policy(current)}
                    self._reply(200, data)
                except Exception as error:
                    _LOG.exception("Snapshot failed: %s", type(error).__name__)
                    self._reply(503, {"error": "temporarily_unavailable"})
                finally:
                    _MAX_REQUESTS.release()
                return
            if self.path == "/v1/control/catalog":
                client = _authorized_client(current, self.headers.get("Authorization", ""))
                if client is None:
                    return self._reply(401, {"error": "unauthorized"})
                try:
                    return self._reply(200, controller.catalog(client))
                except Exception:
                    return self._reply(503, {"error": "control_unavailable"})
            if self.path == "/v1/pairing/requests":
                if not self._admin(current):
                    return
                from pairing_workflow import request_summary
                result = request_summary(current)
                result["requests"] = inbox.pending()
                return self._reply(200, result)
            if self.path.startswith("/v1/pairing/status/"):
                ticket = self.path[len("/v1/pairing/status/"):]
                try:
                    result = inbox.status(ticket, self.client_address[0])
                except ValueError:
                    return self._reply(400, {"error": "invalid_ticket"})
                return self._reply(200, result)
            return self._reply(404, {"error": "not_found"})

        def do_POST(self):
            arrived = time.perf_counter()
            manager_received = round(time.time()*1000, 3)
            current = self._current()
            if current is None:
                return
            if self.path not in ("/v1/control", "/v1/chat", "/v1/chat/stream", "/v1/chat/cancel", "/v1/pairing/request",
                                 "/v1/pairing/approve",
                                 "/v1/pairing/deny"):
                return self._reply(405, {"error": "read_only_stage"})
            if self.path == "/v1/control":
                principal = _authorized_client(current, self.headers.get("Authorization", ""))
                if principal is None:
                    return self._reply(401, {"error": "unauthorized"})
                if principal.get("control_models") is not True:
                    return self._reply(403, {"error": "control_models_required"})
                body = self._json_post(limit=4096)
                if body is None:
                    return
                try:
                    return self._reply(202, controller.handle(principal, body))
                except ControlError as error:
                    return self._reply(error.status, {"error": error.reason})
                except Exception:
                    return self._reply(503, {"error": "control_unavailable"})
            if self.path == "/v1/chat/cancel":
                principal = _authorized_client(current, self.headers.get("Authorization", ""))
                if principal is None:
                    return self._reply(401, {"error": "unauthorized"})
                body = self._json_post(limit=1024)
                if body is None:
                    return
                if (set(body) != {"slot_id", "request_id"} or type(body["request_id"]) is not str
                        or not re.fullmatch(r"[a-f0-9]{32}", body["request_id"])
                        or body["slot_id"] not in principal["allowed_slots"]):
                    return self._reply(403, {"error": "stream_not_authorized"})
                with streams_guard:
                    item = active_streams.get((principal["client_id"], body["request_id"]))
                    found = item is not None and item[0] == body["slot_id"]
                    if found:
                        item[1].set()
                return self._reply(200, {"manager_id": current["manager_id"], "cancelled": found})
            if self.path in ("/v1/chat", "/v1/chat/stream"):
                principal = _authorized_client(
                    current, self.headers.get("Authorization", ""))
                if principal is None:
                    return self._reply(401, {"error": "unauthorized"})
                policy = chat_policy(current)
                body = self._json_post(limit=policy["request_bytes"])
                if body is None:
                    return
                try:
                    request_id = __import__('uuid').uuid4().hex
                    cancelled = threading.Event()
                    if self.path.endswith("/stream") and "request_id" in body:
                        request_id = body["request_id"]
                        if type(request_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", request_id):
                            raise ChatError("invalid_request_id")
                        body = {k:v for k,v in body.items() if k != "request_id"}
                    slot_id, model_id, messages = validate_request(body, policy=policy)
                    if not any(s["slot_id"]==slot_id for s in current["slots"]):
                        raise ChatError("unknown_slot", 404)
                    with streams_guard:
                        lock=chat_locks.setdefault(slot_id,threading.Lock())
                    if not lock.acquire(blocking=False):
                        raise ChatError("slot_chat_in_progress", 409)
                    try:
                        snapshot = chat_snapshot(current, principal, slot_id)
                        port = select_backend(
                            current, principal, snapshot, slot_id, model_id)
                        try:
                            controller.assert_chat_allowed(slot_id)
                            owned, execution_mode = controller.chat_binding(slot_id, with_mode=True)
                        except ControlError as error:
                            raise ChatError(error.reason, error.status) from None
                        identity = owned or snapshot["slots"][0]["instance_id"]
                        expected = body.get("instance_id")
                        if (owned and expected is None) or (expected is not None and expected != identity):
                            raise ChatError("instance_identity_mismatch", 409)
                        try:
                            upstream_options(body.get("options"), thinking_supported=False
                                if "qwen3-coder" in model_id.lower() else None)
                        except ValueError as error:
                            raise ChatError(str(error)) from None
                        requested_output=(body.get("options") or {}).get("max_output_tokens")
                        engine_output=snapshot.get("engine_limits",{}).get("max_tokens")
                        if requested_output is not None and engine_output and requested_output>engine_output:
                            raise ChatError("requested_output_exceeds_engine_limit")
                        timing = {"manager_received_unix_ms": manager_received,
                                  "_manager_perf": arrived,
                                  "manager_preflight_ms": round((time.perf_counter()-arrived)*1000, 3)}
                        if self.path.endswith("/stream"):
                            stream_key = (principal["client_id"], request_id)
                            with streams_guard:
                                if stream_key in active_streams:
                                    raise ChatError("stream_in_progress", 409)
                                active_streams[stream_key] = (slot_id, cancelled, identity,
                                    (snapshot["slots"][0].get("pid"),snapshot["slots"][0]["instance_id"]))
                            try:
                                return self._stream_chat(port, model_id, messages, current, slot_id, cancelled,
                                    instance_id=identity, options=body.get("options"), policy=policy,
                                    timing=timing, engine_limits=snapshot.get("engine_limits", {}),
                                    execution_mode=execution_mode)
                            finally:
                                with streams_guard:
                                    active_streams.pop(stream_key, None)
                        response = proxy_chat(port, model_id, messages, options=body.get("options"),
                                              policy=policy, timeout=policy["nonstream_timeout_seconds"])
                        return self._reply(200, {
                            "schema": "ultra.manager.chat.v1",
                            "manager_id": current["manager_id"],
                            "slot_id": slot_id, "instance_id": identity, "model_id": model_id,
                            "engine_limits":snapshot.get("engine_limits", {}), "transport_policy":policy,
                            "execution_mode":execution_mode, **response})
                    finally:
                        lock.release()
                except ChatError as error:
                    return self._reply(error.status, {"error": error.reason})
                except Exception as error:
                    _LOG.error("Chat failed: %s", type(error).__name__)
                    return self._reply(503, {"error": "chat_temporarily_unavailable"})
            if self.path != "/v1/pairing/request" and not self._admin(current):
                return
            body = self._json_post()
            if body is None:
                return
            if self.path == "/v1/pairing/request":
                if set(body) != {"client_id", "token_sha256"}:
                    return self._reply(400, {"error": "invalid_fields"})
                try:
                    ids = {x["client_id"] for x in current["clients"]}
                    response = inbox.submit(body, self.client_address[0], ids)
                    return self._reply(202, response)
                except OverflowError:
                    return self._reply(429, {"error": "pairing_rate_limited"})
                except ValueError:
                    return self._reply(400, {"error": "invalid_pairing_request"})
            if self.path == "/v1/pairing/approve":
                if set(body) != {"ticket_id", "allowed_slots"}:
                    return self._reply(400, {"error": "invalid_fields"})
                from pairing_workflow import grant_pending
                try:
                    response = inbox.approve(
                        body["ticket_id"], body["allowed_slots"],
                        lambda cid, digest, ip, allowed: grant_pending(
                            config_file, cid, digest, ip, allowed))
                    return self._reply(200, response)
                except (ValueError, PermissionError, OSError) as error:
                    _LOG.warning("Pairing approval refused: %s", type(error).__name__)
                    return self._reply(409, {"error": "grant_not_applied"})
            if set(body) != {"ticket_id"}:
                return self._reply(400, {"error": "invalid_fields"})
            try:
                return self._reply(200, inbox.deny(body["ticket_id"]))
            except ValueError:
                return self._reply(409, {"error": "not_pending"})
        def _stream_chat(self, port, model_id, messages, current, slot_id, cancelled, *, instance_id, options,
                         policy, timing, engine_limits, execution_mode=None):
            events = proxy_stream(port, model_id, messages, cancelled=cancelled, options=options,
                                  policy=policy, timing=timing, timeout=policy["timeout_seconds"])
            try:
                first = next(events)  # failures before headers retain HTTP status
            except StopIteration:
                raise ChatError("empty_stream", 502)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            def emit(event):
                if event.get("type") in ("delta", "reasoning") and "manager_first_forward_unix_ms" not in timing:
                    timing["manager_first_forward_unix_ms"] = round(time.time()*1000, 3)
                    timing["manager_first_forward_delay_ms"] = round((time.perf_counter()-timing["_colibri_first_perf"])*1000,3)
                if event.get("type") == "done":
                    timing["manager_total_ms"] = round((time.perf_counter()-timing["_manager_perf"])*1000,3)
                event["timing"] = {**event.get("timing", {}), **timing,
                    "manager_emit_unix_ms": round(time.time()*1000, 3)}
                event["timing"] = {k:v for k,v in event["timing"].items() if not k.startswith("_")}
                self.wfile.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
                self.wfile.flush()
            try:
                emit({"type": "meta", "schema":"ultra.manager.stream.v2", "manager_id": current["manager_id"],
                      "slot_id": slot_id, "instance_id": instance_id, "model_id": model_id,
                      "transport_policy": policy, "engine_limits":engine_limits, "execution_mode":execution_mode,
                      "options": options or {"thinking":"auto"}})
                emit(first)
                for event in events:
                    emit(event)
            except ChatError as error:
                try:
                    emit({"type": "error", "error": error.reason, "status": error.status})
                except OSError:
                    pass
            except (OSError, TimeoutError):
                pass  # downstream closed; finally closes Colibri, releases slot lock
            finally:
                events.close()

        def log_message(self, fmt, *args):
            # Never log URL paths/query strings or auth headers: they may
            # inadvertently contain secrets, even for rejected requests.
            _LOG.info("HTTPS request from %s", self.client_address[0])

    return Handler


class ShortTimeoutManagerHTTPServer(ThreadingHTTPServer):
    """Bound slow request clients; do not let unauthenticated pairing hang."""
    request_queue_size = 16

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(8)
        return connection, address



class VPNManagerHTTPServer(ShortTimeoutManagerHTTPServer):
    """Separate socket, shared handler/controller, exact source before TLS."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, handler, vpn, context):
        self.vpn_listener = vpn
        self.tls_context = context
        super().__init__(address, handler)
        self.daemon_threads = True
        self.timeout = 0.5

    def get_request(self):
        connection, address = super().get_request()
        try:
            if address[0] != self.vpn_listener["source_ip"]:
                raise PermissionError("VPN peer not permitted")
            # Avoid blocking the listener on a slow TLS handshake.
            return self.tls_context.wrap_socket(connection, server_side=True,
                                do_handshake_on_connect=False), address
        except BaseException:
            connection.close()
            raise


def vpn_listener_loop(config_file, config, handler, stopped):
    vpn = config.get("vpn_listener")
    if not vpn or not vpn["enabled"]:
        return
    try:
        context = vpn_tls_context(vpn, config_file)
    except (OSError, ValueError, ssl.SSLError, subprocess.SubprocessError):
        _LOG.warning("VPN TLS configuration unavailable; primary listener retained")
        return
    warned = False
    while not stopped.is_set():
        try:
            server = VPNManagerHTTPServer((vpn["bind_host"], config["listen_port"]),
                                          handler, vpn, context)
        except OSError:
            if not warned:
                _LOG.warning("VPN listener unavailable; primary retained; retrying")
                warned = True
            stopped.wait(5)
            continue
        try:
            _LOG.info("VPN listener active at %s:%d", vpn["bind_host"], config["listen_port"])
            while not stopped.is_set():
                server.handle_request()
        except OSError:
            _LOG.warning("VPN socket unavailable; primary retained")
        finally:
            server.server_close()
        if stopped.wait(5):
            return


def run(config_file):
    config = load_config(config_file)
    inbox = PairingInbox()
    controller = ModelControl(config)
    handler = make_handler(config_file, config, inbox, controller=controller)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config["cert_file"], config["key_file"])
    server = ShortTimeoutManagerHTTPServer(
        (config["bind_host"], config["listen_port"]), handler)
    server.daemon_threads = True
    server.socket = context.wrap_socket(server.socket, server_side=True)
    _LOG.info("Manager %s listening securely at %s:%d",
              config["manager_id"], config["bind_host"], config["listen_port"])
    stop_watchdog = threading.Event()
    watchdog = None
    if controller.db_path is not None:
        watchdog = threading.Thread(target=controller.watchdog_loop, args=(stop_watchdog,),
                                    name="manager-watchdog", daemon=True)
        watchdog.start()
    vpn_worker = None
    if (config.get("vpn_listener") or {}).get("enabled"):
        vpn_worker = threading.Thread(target=vpn_listener_loop,
            args=(config_file, config, handler, stop_watchdog), name="manager-vpn", daemon=True)
        vpn_worker.start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_watchdog.set()
        if vpn_worker is not None:
            vpn_worker.join(timeout=8)
        if watchdog is not None:
            watchdog.join(timeout=8)
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path,
                        help="Existing ACL-protected directory outside Git")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check-config", action="store_true",
                       help="Validate the configuration without binding a port")
    modes.add_argument("--network-settings", action="store_true",
                       help="Open local owner-only network settings; no server start")
    args = parser.parse_args()
    log_handlers = []
    if args.log_dir:
        log_dir = args.log_dir
        if (not log_dir.is_absolute() or not log_dir.is_dir() or
                log_dir.is_symlink()):
            parser.error("--log-dir must be an existing absolute directory")
        log_handlers.append(RotatingFileHandler(
            log_dir / "manager.log", maxBytes=2 * 1024 * 1024,
            backupCount=3, encoding="utf-8"))
    if not log_handlers:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=log_handlers)
    if args.check_config:
        config = load_config(args.config)
        if not Path(config["cert_file"]).is_file() or not Path(config["key_file"]).is_file():
            parser.error("Missing TLS certificate or key")
        if (config.get("vpn_listener") or {}).get("enabled"):
            vpn_tls_context(config["vpn_listener"], args.config)
        print("MANAGER_CONFIGURATION_OK")
    elif args.network_settings:
        open_network_settings(args.config)
    else:
        run(args.config)
