"""Owner-only real HTTPS loopback smoke. No LAN listener or persistent token.

Run on the actual Manager host with a certificate/key already provisioned.
This tests real TLS+authentication+Colibri telemetry but NOT LAN pairing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time

import live_manager


def _fetch(port, context, server_name, authorization=None):
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    with context.wrap_socket(sock, server_hostname=server_name) as tls:
        request = f"GET /v1/snapshot HTTP/1.0\r\nHost: {server_name}\r\n"
        if authorization:
            request += "Authorization: Bearer " + authorization + "\r\n"
        request += "Connection: close\r\n\r\n"
        tls.sendall(request.encode("ascii"))
        chunks = []
        while True:
            data = tls.recv(32768)
            if not data:
                break
            chunks.append(data)
    status, body = b"".join(chunks).split(b"\r\n\r\n", 1)
    return int(status.split(b" ")[1]), json.loads(body)


def check(cert: Path, key: Path, models_root: Path, colibri_root: Path, server_name: str, port: int):
    # Throwaway loopback-only credential, never accepted by production LAN.
    marker = "LOCAL-LOOPBACK-TEST-ONLY-NOT-A-REAL-CREDENTIAL-000001"
    with tempfile.TemporaryDirectory(prefix="ultra-tls-loopback-") as td:
        config = {
            "manager_id": "loopback-only",
            "display_name": "Local HTTPS smoke",
            "bind_host": "127.0.0.1",
            "listen_port": port,
            "colibri_root": str(colibri_root),
            "models_root": str(models_root),
            "cert_file": str(cert),
            "key_file": str(key),
            "slots": [
                {"slot_id": "slot1", "api_port": 8000, "protected": True},
                {"slot_id": "slot2", "api_port": 8001, "protected": False}],
            "clients": [
                {"client_id": "smoke-client",
                 "sha256": hashlib.sha256(marker.encode()).hexdigest(),
                 "allowed_slots": ["slot1", "slot2"]},
                {"client_id": "denied-viewer",
                 "sha256": hashlib.sha256((marker + "-denied").encode()).hexdigest(),
                 "allowed_slots": []}]}
        conf = Path(td) / "manager.json"
        conf.write_text(json.dumps(config), encoding="utf-8")
        daemon = threading.Thread(target=live_manager.run, args=(conf,), daemon=True)
        daemon.start()
        time.sleep(0.8)
        tls_context = ssl.create_default_context(cafile=str(cert))
        code, response = _fetch(port, tls_context, server_name)
        assert code == 401, f"Missing auth accepted: {code}"
        code, response = _fetch(port, tls_context, server_name, "wrong")
        assert code == 401, f"Wrong auth accepted: {code}"
        code, response = _fetch(port, tls_context, server_name, marker)
        assert code == 200, f"Authorised read failed: {code}"
        assert response["source"] == "LIVE_HOST"
        assert response["manager_id"] == "loopback-only"
        assert response["viewer_id"] == "smoke-client"
        assert response["reservation_granted"] is False
        assert response["slots"][0]["engine_state"] == "ready"
        code, denied = _fetch(port, tls_context, server_name, marker + "-denied")
        assert code == 200
        assert denied["viewer_id"] == "denied-viewer"
        assert all(x["availability"] == "denied" for x in denied["slots"])
        assert all(x["models"] == [] and x["pid"] is None for x in denied["slots"])
        print(json.dumps({
            "result": "PASS_LOOPBACK_TLS_REAL_HOST",
            "host": response["host"],
            "real_slot1": response["slots"][0]["engine_state"],
            "visible_models": response["slots"][0]["models"],
            "missing_token": 401,
            "invalid_token": 401,
            "valid_token": 200,
            "limited_client": "denied",
            "certificate_verified": True,
            "interface": "127.0.0.1",
            "lan_opened": False}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--colibri-root", type=Path, required=True)
    parser.add_argument("--verify-host", required=True)
    parser.add_argument("--port", type=int, default=18447)
    args = parser.parse_args()
    check(args.cert, args.key, args.models_root, args.colibri_root, args.verify_host, args.port)
