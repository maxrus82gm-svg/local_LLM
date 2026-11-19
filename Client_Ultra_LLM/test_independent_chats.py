"""SQLite migrations, context privacy and request lifecycle contracts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import chat_store as store
import web_client as web


TARGET = {"manager_id": "m", "slot_id": "slot1", "model_id": "test"}


class IndependentChatTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        profiles = patch.object(web, "selected_profile", return_value={"manager_id": "m"})
        profiles.start()
        self.addCleanup(profiles.stop)

    def chat(self, target=TARGET):
        return web.chat_action(self.folder, {"op": "create", "target": target})["chat_id"]

    def action(self, chat_id, op, **data):
        return web.chat_action(self.folder, {"op": op, "chat_id": chat_id, **data})

    def append(self, chat_id, user="question", reply="answer", reasoning="private reasoning"):
        return store.append_exchange(self.folder, *TARGET.values(), user, reply, chat_id=chat_id, reasoning=reasoning)

    def history(self, chat_id):
        return store.history(self.folder, chat_id=chat_id)

    def payload(self, chat_id, request_id="a"*32, **data):
        return {**TARGET, "chat_id": chat_id, "message": "new", "request_id": request_id, **data}

    def test_v1_migration_checks_backup_and_preserves_all_instance_histories(self):
        path = self.folder / "chat_history.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                PRAGMA user_version=1;
                CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, manager_id TEXT NOT NULL,
                  slot_id TEXT NOT NULL,model_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,
                  instance_id TEXT NOT NULL DEFAULT '', reasoning_content TEXT NOT NULL DEFAULT '');
                CREATE TABLE chat_requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL);
                INSERT INTO messages VALUES(4,'m','slot1','test','user','one','','');
                INSERT INTO messages VALUES(5,'m','slot1','test','assistant','','','thought');
                INSERT INTO messages VALUES(9,'m','slot1','test','user','two','instance','');
            """)
        rows = store.list_chats(self.folder)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["legacy"] and row["created_at"] is None for row in rows))
        old = store.history(self.folder, *TARGET.values())
        self.assertEqual(old[-1]["reasoning_content"], "thought")
        self.assertEqual(store.history(self.folder, *TARGET.values(), instance_id="instance")[0]["content"], "two")
        self.assertEqual(store.list_chats(self.folder), rows)
        backup, = self.folder.glob("chat_history.pre-v2-*.sqlite3")
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT reasoning_content FROM messages WHERE id=5").fetchone()[0], "thought")
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT message_id,content FROM reasoning").fetchall(), [(5, "thought")])
            self.assertNotIn("reasoning_content", [row[1] for row in db.execute("PRAGMA table_info(messages)")])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_reset_clear_restore_delete_and_reassignment_preserve_scope(self):
        a, b = self.chat(), self.chat()
        self.append(a, user="first chat")
        self.append(b, user="second chat")
        self.action(a, "rename", title="Renamed")
        self.action(a, "reset")
        self.assertEqual(len(self.history(a)), 2)
        self.assertEqual(store.history(self.folder, chat_id=a, context=True), [])
        self.append(a, user="after reset")
        self.assertEqual(len(store.history(self.folder, chat_id=a, context=True)), 2)
        self.action(a, "resume")
        self.assertEqual(len(store.history(self.folder, chat_id=a, context=True)), 4)
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.action(a, "clear", confirm=False)
        self.assertTrue(self.action(a, "clear", confirm=True)["can_restore"])
        self.assertEqual(self.history(a), [])
        self.assertEqual(self.history(b)[0]["content"], "second chat")
        self.action(a, "restore")
        self.assertEqual(len(self.history(a)), 4)
        self.assertEqual(store.history(self.folder, chat_id=a, context=True), [])
        self.action(a, "target", target={**TARGET, "model_id": "different"})
        self.assertEqual(self.history(a)[0]["content"], "first chat")
        with self.assertRaisesRegex(web.ChatClientError, "chat_target_changed"):
            web.chat_exchange(self.folder, self.payload(a))
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.action(a, "delete", confirm=1)
        self.action(a, "delete", confirm=True)
        with self.assertRaises(KeyError):
            self.history(a)
        self.assertEqual(len(self.history(b)), 2)

    def test_v2_migration_links_only_unambiguous_measurements(self):
        chat_id, other_chat = self.chat(), self.chat()
        records = [
            (chat_id, 0, 11),
            (chat_id, 2, 22),
            (chat_id, 2, 33),
            (other_chat, 0, 44),
        ]
        for index, (chat, second, tokens) in enumerate(records):
            request_id = f"{index:032x}"
            store.claim_request(self.folder, request_id, (chat,), "question")
            metrics = {"started_at": f"2026-11-19T10:00:0{second}.000+00:00",
                       "finished_at": f"2026-11-19T10:00:0{second+1}.000+00:00",
                       "total_ms": 1000, "usage": {"completion_tokens": tokens}}
            store.append_exchange(self.folder, *TARGET.values(), "question", "answer",
                                  chat_id=chat, request_id=request_id, metrics=metrics)
        self.assertEqual([m["metrics"]["usage"]["completion_tokens"] for m in self.history(chat_id)],
                         [11, 11, 22, 22, 33, 33])

        path = self.folder / "chat_history.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DROP INDEX messages_by_request")
            db.execute("ALTER TABLE messages DROP COLUMN request_id")
            db.execute("PRAGMA user_version=2")

        migrated = self.history(chat_id)
        self.assertEqual([m["metrics"]["usage"]["completion_tokens"] for m in migrated[:2]], [11, 11])
        self.assertTrue(all("metrics" not in m for m in migrated[2:]))
        self.assertEqual([m["metrics"]["usage"]["completion_tokens"] for m in self.history(other_chat)], [44, 44])
        self.assertEqual(len(store.recent_metrics(self.folder, chat_id)), 3)
        backup, = self.folder.glob("chat_history.pre-v3-*.sqlite3")
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM request_metrics").fetchone()[0], 4)
        self.assertEqual(self.history(chat_id), migrated)
        self.action(chat_id, "clear", confirm=True)
        self.assertEqual(self.history(chat_id), [])
        self.action(chat_id, "restore")
        self.assertEqual(self.history(chat_id), migrated)
        self.action(chat_id, "delete", confirm=True)
        self.assertEqual(len(self.history(other_chat)), 2)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_bounds_and_reasoning_only_context(self):
        sample = [{"role": role, "content": f"m{i}", "reasoning_content": "r"*10000}
                  for i in range(100) for role in ("user", "assistant")]
        for limit, expected in ((0, 0), (1, 0), (20, 20), (100, 100)):
            selected, info = store.context_for(sample, max_messages=limit, max_chars=500, with_info=True)
            self.assertEqual(len(selected), expected)
            self.assertEqual(info["omitted_messages"], 200-expected)
            self.assertTrue(all(set(row) == {"role", "content"} for row in selected))
        sample = [{"role": "user", "content": "ask"}, {"role": "assistant", "content": "", "reasoning_content": "archive"}]
        self.assertEqual(store.context_for(sample, max_chars=3), sample[:1])
        with self.assertRaisesRegex(ValueError, "invalid_context"):
            store.context_for([{"role": "tool", "content": "bad"}])
        with self.assertRaisesRegex(ValueError, "invalid_context"):
            store.context_for([], max_chars=True)

    def test_parallel_ids_and_zero_history_do_not_mix(self):
        a, b = self.chat(), self.chat()
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda i: self.append(a if i % 2 else b, user=str(i)), range(32)))
        for chat_id, parity in ((a, 1), (b, 0)):
            rows = self.history(chat_id)
            self.assertEqual(len(rows), 32)
            self.assertTrue(all(int(row["content"]) % 2 == parity for row in rows if row["role"] == "user"))
            self.assertTrue(all(row["created_at"].endswith("+00:00") for row in rows))
        self.action(a, "settings", context={"max_messages": 0, "max_chars": 1000})
        with patch.object(web, "send_chat", return_value={"reply": "answer"}) as sender:
            result = web.chat_exchange(self.folder, self.payload(a))
        self.assertEqual(sender.call_args.args[3], [{"role": "user", "content": "new"}])
        self.assertEqual(result["context"]["omitted_messages"], 32)
        self.assertEqual(len(self.history(a)), 34)
        self.assertEqual(store.get_chat(self.folder, a)["settings"]["max_messages"], 0)

    def test_stream_measurements_failure_and_cancellation(self):
        chat_id = self.chat()
        self.append(chat_id)
        def events(*args, **kwargs):
            yield {"type": "meta", "execution_mode": "cpu"}
            yield {"type": "reasoning", "text": "new thought"}
            yield {"type": "done", "usage": {"prompt_tokens": 13, "completion_tokens": 8, "reasoning_tokens": 5}}
        with patch.object(web, "stream_chat", side_effect=events) as upstream:
            results = list(web.chat_stream_exchange(self.folder, self.payload(chat_id)))
            self.assertEqual(upstream.call_args.args[3], [
                {"role": "user", "content": "question"}, {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "new"}])
            self.assertEqual(results[-1]["messages"][-1]["reasoning_content"], "new thought")
            first, second = results[-1]["messages"][-2:]
            self.assertEqual(first["metrics"], second["metrics"])
            self.assertEqual(first["metrics"]["usage"], {"prompt_tokens": 13, "completion_tokens": 8})
            active = web.chat_stream_exchange(self.folder, self.payload(chat_id, "b"*32))
            next(active)
            with self.assertRaisesRegex(web.ChatClientError, "chat_in_progress"):
                self.action(chat_id, "reset")
            next(active)
            active.close()
        with patch.object(web, "stream_chat", side_effect=web.ChatClientError("stream_deadline", 504)):
            with self.assertRaisesRegex(web.ChatClientError, "stream_deadline"):
                list(web.chat_stream_exchange(self.folder, self.payload(chat_id, "c"*32)))
        runs = {row["state"]: row for row in store.recent_metrics(self.folder, chat_id)}
        self.assertEqual(set(runs), {"complete", "cancelled", "failed"})
        complete = runs["complete"]
        self.assertEqual(complete["usage"], {"prompt_tokens": 13, "completion_tokens": 8})
        self.assertEqual(complete["execution_mode"], "cpu")
        self.assertGreaterEqual(complete["generation_ms"], 0)
        self.assertNotIn("usage", runs["failed"])
        self.assertEqual(runs["failed"]["error"], "stream_deadline")
        self.assertEqual(len(self.history(chat_id)), 4)
        self.assertFalse(web.CHAT_LOCKS)

    def test_two_active_chats_and_byte_bounded_payloads(self):
        a, b = self.chat(), self.chat()
        self.append(a, reply="😀"*1000)
        self.append(b, user="second history")
        synchronized = threading.Barrier(2)

        def upstream(profile, slot, model, messages, **kwargs):
            synchronized.wait(timeout=5)
            return {"reply": messages[0]["content"]}

        with patch.object(web, "send_chat", side_effect=upstream), ThreadPoolExecutor(max_workers=2) as pool:
            send_a = pool.submit(web.chat_exchange, self.folder, self.payload(a, context={"max_bytes": 2400}))
            send_b = pool.submit(web.chat_exchange, self.folder, self.payload(b, "b"*32))
            self.assertEqual(send_a.result()["context"]["sent_history_messages"], 0)
            self.assertEqual(send_b.result()["reply"], "second history")

    def test_corrupt_context_never_reaches_manager(self):
        a = self.chat()
        self.append(a, user="broken\x00entry")
        with patch.object(web, "send_chat") as upstream:
            with self.assertRaisesRegex(ValueError, "invalid_context_message"):
                web.chat_exchange(self.folder, self.payload(a))
            upstream.assert_not_called()
        self.assertEqual(len(self.history(a)), 2)
        self.assertEqual(store.recent_metrics(self.folder, a)[0]["state"], "failed")


if __name__ == "__main__":
    unittest.main()
