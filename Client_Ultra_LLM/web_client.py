"""Ultra LLM Web Client P1: portable local-only browser UI and real HTTPS Manager data.

Security boundary:
- Browser accesses only 127.0.0.1 on an ephemeral port; no LAN HTTP service.
- Only this Python process reads Manager tokens. No secrets in JSON/HTML/JS.
- TLS to Managers is strictly verified via a pinned, user-provided CA file.
- New client credentials are made inside the user's protected profile directory.
- Administrator must still explicitly register the returned SHA-256 with Manager.
- No Start/Stop or reservation is available in this stage.
"""
from __future__ import annotations

import argparse
import ctypes
import time
from urllib.request import build_opener, ProxyHandler
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit
import webbrowser

from live_client import fetch_all, load_profiles
from pairing_client import _require_private_acl, enroll

HERE = Path(__file__).resolve().parent
STATIC = HERE / "web_assets"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,251}$")
MAX_BODY = 48 * 1024
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/client.css": ("client.css", "text/css; charset=utf-8"),
    "/client.js": ("client.js", "application/javascript; charset=utf-8"),
}
PROFILE_LOCK = threading.RLock()


def config_directory() -> Path:
    if os.name != "nt":
        return Path.home() / ".config" / "UltraLLM" / "Client"
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(base) / "UltraLLM" / "Client"


def ensure_private_dir(folder: Path) -> Path:
    folder = folder.expanduser().absolute()
    if folder.is_symlink():
        raise PermissionError("Credential directory cannot be a symlink")
    if not folder.exists():
        if os.name == "nt":
            installer = HERE / "Prepare-ClientPrivate.ps1"
            ps = Path(os.environ.get("SystemRoot") or
                      os.environ.get("WINDIR") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            cmd = [str(ps), "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-File", str(installer)]
            result = subprocess.run(
                cmd, capture_output=True, timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False)
            if result.returncode:
                raise PermissionError("Unable to create protected Client directory")
        else:
            folder.mkdir(parents=True, mode=0o700)
            folder.chmod(0o700)
    if not folder.is_dir() or folder.is_symlink():
        raise PermissionError("Invalid protected Client directory")
    _require_private_acl(folder)
    return folder


def _safe_address(host: object, port: object) -> str:
    if not isinstance(host, str):
        raise ValueError("Enter Manager IP address or DNS name")
    host = host.strip()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not HOSTNAME.fullmatch(host) or ".." in host or host.endswith("."):
            raise ValueError("Invalid Manager address")
        hostname = host
    else:
        if address.is_unspecified or address.is_multicast or address.is_link_local:
            raise ValueError("Invalid Manager IP address")
        hostname = "[" + host + "]" if address.version == 6 else host
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Manager port must be 1024–65535")
    return f"https://{hostname}:{port}"


def config_info(folder: Path) -> dict:
    path = folder / "managers.json"
    if not path.exists():
        return {"configured": False, "profiles": []}
    profiles = load_profiles(path)
    return {"configured": True, "profiles": [
        {"manager_id": x["manager_id"],
         "client_id": x["client_id"],
         "display_name": x["display_name"],
         "endpoint": x["endpoint"]}
        for x in profiles]}


def enroll_profile(folder: Path, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid form")
    mid, cid = payload.get("manager_id"), payload.get("client_id")
    if not isinstance(mid, str) or not IDENTIFIER.fullmatch(mid):
        raise ValueError("Manager ID must contain letters, digits, '.', '-' or '_'")
    if not isinstance(cid, str) or not IDENTIFIER.fullmatch(cid):
        raise ValueError("Client ID must contain letters, digits, '.', '-' or '_'")
    display = payload.get("display_name")
    if not isinstance(display, str) or not 1 <= len(display.strip()) <= 80:
        raise ValueError("Enter a Manager name")
    endpoint = _safe_address(payload.get("host"), payload.get("port"))
    pem = payload.get("certificate")
    if not isinstance(pem, str) or len(pem) > 16000:
        raise ValueError("Manager public certificate required")
    try:
        der = ssl.PEM_cert_to_DER_cert(pem.strip())
    except ValueError as error:
        raise ValueError("Invalid PEM certificate") from error
    if len(der) < 100:
        raise ValueError("Certificate is invalid")
    fingerprint = hashlib.sha256(der).hexdigest()
    # Certificate import must be trusted out-of-band; never silently accept a
    # certificate fetched from an unverified remote endpoint.
    cert_path = None
    with PROFILE_LOCK:
        try:
            with tempfile.NamedTemporaryFile(
                    mode="w", encoding="ascii", dir=folder,
                    prefix=".manager-ca-", suffix=".pem",
                    delete=False) as f:
                cert_path = Path(f.name)
                f.write(pem.strip() + "\n")
            digest = enroll(folder, mid, cid, endpoint, cert_path, display.strip(),
                            announce=False)
        finally:
            if cert_path is not None:
                cert_path.unlink(missing_ok=True)
    return {"manager_id": mid, "client_id": cid, "endpoint": endpoint,
            "registration_sha256": digest,
            "certificate_sha256": fingerprint,
            "state": "awaiting_manager_approval"}


def _secure_host(handler, port: int) -> bool:
    return handler.headers.get("Host", "") == f"127.0.0.1:{port}"


def make_handler(folder: Path, port_getter, csrf: str):
    class WebHandler(BaseHTTPRequestHandler):
        server_version = "UltraLLMWeb/1.0"
        sys_version = ""
        def _headers(self, status, mime, size):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
        def _send_json(self, status, data):
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)
        def _bad_host(self):
            if not _secure_host(self, port_getter()):
                self._send_json(403, {"error": "untrusted_host"})
                return True
            if self.client_address[0] != "127.0.0.1":
                self._send_json(403, {"error": "loopback_only"})
                return True
            return False
        def do_GET(self):
            if self._bad_host():
                return
            path = self.path
            if path in _STATIC_FILES:
                name, mime = _STATIC_FILES[path]
                file = STATIC / name
                if not file.is_file():
                    return self._send_json(503, {"error": "missing_web_assets"})
                raw = file.read_bytes()
                self._headers(200, mime, len(raw))
                return self.wfile.write(raw)
            if path == "/api/session":
                return self._send_json(200, {"csrf": csrf})
            if path == "/api/config":
                try:
                    return self._send_json(200, config_info(folder))
                except (OSError, ValueError, KeyError):
                    return self._send_json(500, {"error": "invalid_private_configuration"})
            if path == "/api/status":
                try:
                    config_path = folder / "managers.json"
                    if not config_path.is_file():
                        return self._send_json(200, {"configured": False, "managers": []})
                    profiles = load_profiles(config_path)
                    return self._send_json(200, {
                        "configured": True, "managers": fetch_all(profiles)})
                except (OSError, ValueError, KeyError):
                    return self._send_json(503, {"error": "manager_config_unavailable"})
            return self._send_json(404, {"error": "not_found"})
        def do_POST(self):
            if self._bad_host():
                return
            origin = self.headers.get("Origin", "")
            expected = f"http://127.0.0.1:{port_getter()}"
            if (origin != expected or
                    not secrets.compare_digest(
                        self.headers.get("X-Ultra-CSRF", ""), csrf)):
                return self._send_json(403, {"error": "request_not_authorised"})
            if self.path not in ("/api/enroll", "/api/shutdown"):
                return self._send_json(404, {"error": "not_found"})
            if self.path == "/api/shutdown":
                self._send_json(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._send_json(415, {"error": "json_only"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    return self._send_json(413, {"error": "invalid_request_size"})
                data = json.loads(self.rfile.read(size))
                response = enroll_profile(folder, data)
                return self._send_json(201, response)
            except (ValueError, KeyError, FileExistsError) as error:
                return self._send_json(400, {"error": str(error)[:200]})
            except (OSError, PermissionError):
                return self._send_json(500, {"error": "private_store_unavailable"})
        def log_message(self, *args):
            # URLs and request bodies may contain private details: never log them.
            pass
    return WebHandler


def _open_existing_instance(folder: Path, open_browser: bool) -> bool:
    """Never open an unverified arbitrary port unless another instance owns
    the named mutex for the exact protected Client profile directory."""
    port_path = folder / ".web-client.port"
    opener = build_opener(ProxyHandler({}))
    for _ in range(20):
        try:
            port = int(port_path.read_text(encoding="ascii").strip())
            if not 1024 <= port <= 65535:
                raise ValueError("Invalid port")
            url = f"http://127.0.0.1:{port}/"
            with opener.open(url + "api/config", timeout=1.2) as response:
                if (response.status == 200 and
                        response.headers.get("Server", "").startswith("UltraLLMWeb/")):
                    if open_browser:
                        webbrowser.open(url)
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("An existing Web Client did not respond; check its process")


def _instance_mutex(folder: Path):
    """Keep one browser server per Windows user/session and profile."""
    if os.name != "nt":
        return None, False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = "Local\\UltraLLM-Web-" + hashlib.sha256(
        str(folder).casefold().encode("utf-8")).hexdigest()[:32]
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise OSError("Cannot create Web Client single-instance mutex")
    return (kernel, handle), (ctypes.get_last_error() == 183)


def run_server(folder: Path, *, port: int = 0, open_browser: bool = True):
    folder = ensure_private_dir(folder)
    handle, duplicate = _instance_mutex(folder)
    if duplicate:
        try:
            _open_existing_instance(folder, open_browser)
        finally:
            if handle:
                handle[0].CloseHandle(ctypes.c_void_p(handle[1]))
        return
    session_key = secrets.token_urlsafe(32)
    holder = {"port": 0}
    port_path = folder / ".web-client.port"
    server = None
    try:
        handler = make_handler(folder, lambda: holder["port"], session_key)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server.daemon_threads = True
        holder["port"] = server.server_address[1]
        address = f"http://127.0.0.1:{holder['port']}/"
        port_path.write_text(str(holder["port"]), encoding="ascii")
        # --windowed/--noconsole PyInstaller sets sys.stdout to None.
        # Diagnostics must never prevent a GUI-only package from starting.
        if sys.stdout is not None:
            print("ULTRA_WEB_CLIENT_READY", address, flush=True)
        if open_browser:
            webbrowser.open(address)
        server.serve_forever(poll_interval=0.25)
    finally:
        if server is not None:
            server.server_close()
        if port_path.is_file() and port_path.read_text(encoding="ascii").strip() == str(holder["port"]):
            port_path.unlink()
        if handle:
            handle[0].CloseHandle(ctypes.c_void_p(handle[1]))


def main():
    parser = argparse.ArgumentParser(description="Ultra LLM browser-only Client")
    parser.add_argument("--config-dir", type=Path, default=config_directory())
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    a = parser.parse_args()
    run_server(a.config_dir, port=a.port, open_browser=not a.no_browser)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # pythonw has no console; surface an actionable error without leaking
        # private paths, credentials, certificate content or HTTP responses.
        if os.name == "nt" and sys.stderr is None:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запустить Ultra LLM Web Client. "
                "Проверьте Python 3.12, права на защищённый каталог и файлы приложения.",
                "Ultra LLM Client — ошибка запуска", 0x10)
        raise
