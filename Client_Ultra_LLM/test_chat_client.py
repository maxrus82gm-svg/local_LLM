"""CHAT-01 Web Client: local HTTP, private history, CSRF and isolation tests."""
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import chat_store
import web_client


class ChatWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        holder = {"port": 0}
        handler = web_client.make_handler(
            self.folder, lambda: holder["port"], "TEST-CSRF")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        holder["port"] = self.server.server_address[1]
        self.origin = f"http://127.0.0.1:{holder['port']}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener = build_opener(ProxyHandler({}))
        self.target = {"manager_id": "manager-a", "slot_id": "slot1",
                       "model_id": "qwen36"}
        self.profile = {"manager_id": "manager-a"}

    def req(self, url, *, post=None, csrf=None, origin=None):
        headers = {}
        if post is not None:
            headers["Content-Type"] = "application/json"
        if csrf is not None:
            headers["X-Ultra-CSRF"] = csrf
        if origin is not None:
            headers["Origin"] = origin
        request = Request(self.origin + url, headers=headers,
                          data=json.dumps(post).encode() if post is not None else None,
                          method="POST" if post is not None else "GET")
        try:
            with self.opener.open(request, timeout=5) as r:
                return r.status, json.loads(r.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def send(self, text, **changes):
        return self.req("/api/chat/send",
                        post={**self.target, "message": text, **changes},
                        csrf="TEST-CSRF", origin=self.origin)

    def test_history_persists_and_isolates_manager_slot_model(self):
        with patch.object(web_client, "load_profiles", return_value=[self.profile]), \
             patch.object(web_client, "send_chat", return_value={
                 "reply": "Реальный ответ (только mock)", "usage": {}}) as send:
            status, result = self.send("Привет!")
        self.assertEqual(status, 200)
        self.assertEqual([x["role"] for x in result["messages"]],
                         ["user", "assistant"])
        self.assertEqual(send.call_args.args[1:3], ("slot1", "qwen36"))
        self.assertEqual(send.call_args.args[3][-1]["content"], "Привет!")
        url = "/api/chat/history?manager_id=manager-a&slot_id=slot1&model_id=qwen36"
        status, result = self.req(url)
        self.assertEqual(status, 200)
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(self.req(url.replace("slot1", "slot2"))[1]["messages"], [])
        self.assertEqual(self.req(url.replace("manager-a", "manager-b"))[1]["messages"], [])
        self.assertEqual(self.req(url.replace("qwen36", "other"))[1]["messages"], [])
        self.assertTrue((self.folder / "chat_history.sqlite3").is_file())

    def test_rejection_before_network_and_csrf(self):
        status, _ = self.req("/api/chat/send", post={**self.target, "message": "Hi"})
        self.assertEqual(status, 403)
        with patch.object(web_client, "load_profiles",
                          return_value=[self.profile]), \
             patch.object(web_client, "send_chat") as outbound:
            self.assertEqual(self.send("x", manager_id="other-manager")[0], 404)
            self.assertEqual(self.send("x", slot_id="../bad")[0], 400)
            self.assertEqual(self.send("")[0], 400)
            outbound.assert_not_called()
        self.assertFalse((self.folder / "chat_history.sqlite3").exists())

    def test_failed_server_send_does_not_add_phantom_reply(self):
        with patch.object(web_client, "load_profiles", return_value=[self.profile]), \
             patch.object(web_client, "send_chat", side_effect=web_client.ChatClientError(
                 "manager_chat_update_required", 503)):
            status, body = self.send("Hi")
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "manager_chat_update_required")
        self.assertFalse((self.folder / "chat_history.sqlite3").exists())

    def test_layout_and_history_input_validation(self):
        root = (Path(web_client.__file__).parent / "web_assets")
        js = (root / "client.js").read_text(encoding="utf-8")
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="chat-view"', html)
        self.assertIn('id="nav-chats"', html)
        self.assertIn('id="chat-popout"', html)
        self.assertIn('manager.data.slots', js)
        self.assertNotIn("maxChats = 3", js)
        # A detached chat uses a URL fragment. A query on "/" would be
        # rejected by the local Client router before the web page could load.
        self.assertIn('window.location.hash.slice(1)', js)
        self.assertIn('url.hash = "chat=" + encodeURIComponent(target.key)', js)
        self.assertNotIn('url.searchParams.set("chat"', js)
        self.assertIn('if (currentChat()) loadChatHistory();', js)
        self.assertNotIn('stateLabel(item.availability).textContent', js)
        self.assertEqual(self.req("/api/chat/history?manager_id=../etc&slot_id=s&model_id=m")[0], 400)
        with self.assertRaises(ValueError):
            chat_store.validate_key("../folder", "s", "m")

    def test_turn_context_is_bounded(self):
        messages = [{"role": "user" if i % 2 == 0 else "assistant",
                     "content": "x" * 1800} for i in range(40)]
        context = chat_store.context_for(messages)
        self.assertLessEqual(len(context), 14)
        self.assertLessEqual(sum(len(m["content"]) for m in context), 18000)


if __name__ == "__main__":
    unittest.main()
