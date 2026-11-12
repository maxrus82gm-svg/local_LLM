"""Transient HTTPS pairing requests; server owner grants access separately.

Only hashes of client-generated tokens enter this queue. Requests are bound to
their actual TCP source IP, time limited, rate limited and never self-approve.
No firewall, process, engine or model operation exists in this module.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import ipaddress
import re
import secrets
import threading
import time

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TICKET = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


@dataclass
class _Ticket:
    ticket_id: str
    client_id: str
    token_sha256: str
    source_ip: str
    created_at: float
    expires_at: float
    state: str = "pending"


class PairingInbox:
    def __init__(self, *, clock=time.monotonic, ttl=600, maximum=24):
        self._clock = clock
        self._ttl = ttl
        self._maximum = maximum
        self._lock = threading.RLock()
        self._tickets: dict[str, _Ticket] = {}
        self._rate: dict[str, deque] = defaultdict(deque)

    def _clean(self, now):
        for item in self._tickets.values():
            if item.state == "pending" and item.expires_at <= now:
                item.state = "expired"
        self._tickets = {
            k: v for k, v in self._tickets.items()
            if v.expires_at + 300 > now
        }
        self._rate = defaultdict(deque, {
            ip: deque(t for t in values if t > now - 600)
            for ip, values in self._rate.items()
            if any(t > now - 600 for t in values)
        })

    def submit(self, payload, actual_source_ip, known_clients):
        if not isinstance(payload, dict):
            raise ValueError("Invalid pairing request")
        client_id = payload.get("client_id")
        digest = payload.get("token_sha256")
        if not isinstance(client_id, str) or not _ID.fullmatch(client_id):
            raise ValueError("Invalid client_id")
        if not isinstance(digest, str) or not _SHA.fullmatch(digest):
            raise ValueError("Invalid token SHA-256")
        if not isinstance(known_clients, set):
            raise ValueError("Invalid known clients")
        address = str(ipaddress.ip_address(actual_source_ip))
        with self._lock:
            now = self._clock()
            self._clean(now)
            if client_id in known_clients:
                raise ValueError("Client already registered")
            if any(x.state == "pending" and
                   (x.client_id == client_id or x.token_sha256 == digest)
                   for x in self._tickets.values()):
                raise ValueError("A request for this client already awaits approval")
            recent = self._rate[address]
            if len(recent) >= 5 or (recent and now - recent[-1] < 3):
                raise OverflowError("Pairing requests are rate limited")
            if sum(x.state == "pending" for x in self._tickets.values()) >= self._maximum:
                raise OverflowError("Pairing inbox is full")
            ticket = _Ticket(
                ticket_id=secrets.token_urlsafe(24),
                client_id=client_id, token_sha256=digest, source_ip=address,
                created_at=now, expires_at=now + self._ttl)
            self._tickets[ticket.ticket_id] = ticket
            recent.append(now)
            return {"ticket_id": ticket.ticket_id, "state": "pending",
                    "expires_in_seconds": self._ttl}

    def status(self, ticket_id, actual_source_ip):
        if not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id):
            raise ValueError("Invalid ticket ID")
        source = str(ipaddress.ip_address(actual_source_ip))
        with self._lock:
            self._clean(self._clock())
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.source_ip != source:
                return {"state": "unknown"}
            return {"state": ticket.state}

    def pending(self):
        with self._lock:
            now = self._clock()
            self._clean(now)
            return [{"ticket_id": x.ticket_id, "client_id": x.client_id,
                     "source_ip": x.source_ip,
                     "expires_in_seconds": max(0, int(x.expires_at - now))}
                    for x in self._tickets.values() if x.state == "pending"]

    def approve(self, ticket_id, allowed_slots, apply):
        if not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id):
            raise ValueError("Invalid ticket ID")
        if not isinstance(allowed_slots, list) or len(allowed_slots) > 64 or any(
                not isinstance(x, str) or not _ID.fullmatch(x) for x in allowed_slots):
            raise ValueError("Invalid allowed_slots")
        if len(set(allowed_slots)) != len(allowed_slots):
            raise ValueError("Repeated slot permission")
        with self._lock:
            self._clean(self._clock())
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.state != "pending":
                raise ValueError("Request not pending")
            # Callback persists an explicit admin grant and must raise on
            # any error; ticket state only changes AFTER persistence succeeds.
            apply(ticket.client_id, ticket.token_sha256,
                  ticket.source_ip, allowed_slots)
            ticket.state = "approved"
            return {"state": "approved", "client_id": ticket.client_id}

    def deny(self, ticket_id):
        if not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id):
            raise ValueError("Invalid ticket ID")
        with self._lock:
            self._clean(self._clock())
            ticket = self._tickets.get(ticket_id)
            if ticket is None or ticket.state != "pending":
                raise ValueError("Request not pending")
            ticket.state = "denied"
            return {"state": "denied"}
