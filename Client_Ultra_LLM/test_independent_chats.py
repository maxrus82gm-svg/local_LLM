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
TARGET2 = {"manager_id": "m", "slot_id": "slot2", "model_id": "test"}


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
        row = store.get_chat(self.folder, chat_id)
        return store.append_exchange(self.folder, *(row[k] for k in TARGET), user, reply, chat_id=chat_id, reasoning=reasoning)

    def history(self, chat_id):
        return store.history(self.folder, chat_id=chat_id)

    def payload(self, chat_id, request_id="a"*32, **data):
        row = store.get_chat(self.folder, chat_id)
        return {**{k:row[k] for k in TARGET}, "chat_id": chat_id, "message": "new", "request_id": request_id, **data}

    def test_context_tokens_are_independent_and_survive_other_preferences(self):
        a, b = self.chat(None), self.chat(None)
        self.assertEqual(store.get_chat(self.folder,a)["context_tokens"],65536)
        self.assertEqual(store.get_chat(self.folder,b)["context_tokens"],65536)
        self.action(a,"context_tokens",context_tokens=16384)
        self.action(b,"context_tokens",context_tokens=123456)
        self.action(a,"settings",context={"max_messages":0,"max_chars":100})
        self.action(a,"preferences",preferences={"stream":False,"thinking":True})
        self.action(a,"target",target=TARGET)
        self.append(a)
        self.action(a,"target",target=None)
        self.assertEqual(store.get_chat(self.folder,a)["context_tokens"],16384)
        self.assertEqual(store.get_chat(self.folder,b)["context_tokens"],123456)
        self.assertEqual(store.get_chat(self.folder,a)["settings"]["max_messages"],0)
        self.assertEqual(len(self.history(a)),2)
        for bad in (0,-1,1000000,True,2.5,"8192",None):
            with self.subTest(bad=bad),self.assertRaisesRegex(ValueError,"invalid_context_tokens"):
                self.action(a,"context_tokens",context_tokens=bad)
        self.assertEqual(store.get_chat(self.folder,a)["context_tokens"],16384)

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

    def test_slot_claim_is_atomic_and_released_without_losing_history(self):
        a, b = self.chat(None), self.chat(None)
        barrier = threading.Barrier(2)
        alias = {**TARGET, "model_id":"different-alias"}
        def claim(item):
            chat, target = item
            barrier.wait(timeout=5)
            try:
                self.action(chat, "target", target=target)
                return chat
            except web.ChatClientError as exc:
                self.assertEqual((exc.reason,exc.status),("chat_target_occupied",409))
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            owners = [x for x in pool.map(claim, [(a,TARGET),(b,alias)]) if x]
        self.assertEqual(len(owners),1)
        owner = owners[0]
        other = b if owner == a else a
        self.append(owner)
        with self.assertRaisesRegex(web.ChatClientError,"chat_target_occupied"):
            self.chat(alias)
        with patch.object(web,"send_chat") as upstream:
            with self.assertRaisesRegex(web.ChatClientError,"chat_target_occupied"):
                web.chat_exchange(self.folder,{**TARGET,"message":"legacy"})
            upstream.assert_not_called()
        self.action(owner,"target",target=None)
        self.action(other,"target",target=TARGET)
        self.assertEqual(len(self.history(owner)),2)
        self.assertIsNone(store.get_chat(self.folder,owner)["model_id"])
        self.action(other,"delete",confirm=True)
        self.action(owner,"target",target=TARGET)
        self.assertEqual(len(self.history(owner)),2)
        self.assertFalse(store.get_chat(self.folder,owner)["target_conflict"])

    def test_stream_and_thinking_preferences_persist_per_chat_and_keep_context(self):
        a,b = self.chat(),self.chat(TARGET2)
        self.append(a)
        self.assertEqual(store.get_chat(self.folder,a)["preferences"],{"stream":True,"thinking":True})
        self.action(a,"preferences",preferences={"stream":False,"thinking":False})
        self.action(a,"settings",context={"max_messages":24,"max_chars":10000})
        self.assertEqual(store.get_chat(self.folder,a)["preferences"],{"stream":False,"thinking":False})
        self.assertEqual(store.get_chat(self.folder,a)["settings"],{"max_messages":24,"max_chars":10000})
        self.assertEqual(store.get_chat(self.folder,b)["preferences"],{"stream":True,"thinking":True})
        self.assertEqual(len(self.history(a)),2)
        for bad in ({"stream":1,"thinking":False},{"stream":True}, {"stream":True,"thinking":True,"auto":True}):
            with self.assertRaisesRegex(ValueError,"invalid_chat_preferences"):
                self.action(a,"preferences",preferences=bad)
        self.assertEqual(store.get_chat(self.folder,a)["preferences"],{"stream":False,"thinking":False})

    def test_existing_duplicate_binding_is_retained_but_cannot_send(self):
        a,b = self.chat(),self.chat(None)
        self.append(a)
        path=self.folder/"chat_history.sqlite3"
        with closing(sqlite3.connect(path)) as db,db:
            db.execute("UPDATE chats SET manager_id=?,slot_id=?,model_id=? WHERE chat_id=?",(*TARGET.values(),b))
        self.assertFalse(store.get_chat(self.folder,a)["target_conflict"])
        self.assertTrue(store.get_chat(self.folder,b)["target_conflict"])
        with patch.object(web,"send_chat") as upstream:
            with self.assertRaisesRegex(web.ChatClientError,"chat_target_occupied"):
                web.chat_exchange(self.folder,self.payload(b))
            upstream.assert_not_called()
        self.action(b,"target",target=TARGET2)
        self.assertFalse(store.get_chat(self.folder,b)["target_conflict"])
        self.assertEqual(len(self.history(a)),2)

    def test_reset_clear_restore_delete_and_reassignment_preserve_scope(self):
        a, b = self.chat(), self.chat(TARGET2)
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
            web.chat_exchange(self.folder, self.payload(a, **TARGET))
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.action(a, "delete", confirm=1)
        self.action(a, "delete", confirm=True)
        with self.assertRaises(KeyError):
            self.history(a)
        self.assertEqual(len(self.history(b)), 2)

    def test_v2_migration_links_only_unambiguous_measurements(self):
        chat_id, other_chat = self.chat(), self.chat(TARGET2)
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
            binding = store.get_chat(self.folder, chat)
            store.append_exchange(self.folder, *(binding[k] for k in TARGET), "question", "answer",
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
        a, b = self.chat(), self.chat(TARGET2)
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
        a, b = self.chat(), self.chat(TARGET2)
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
