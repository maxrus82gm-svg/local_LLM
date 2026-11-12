"""Client stream history, retry, cancellation and actual HTTP integration (fake model)."""
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler

import web_client as web
import chat_store
import chat_client


class HistoryStreamTests(unittest.TestCase):
    def test_reasoning_persists_separately_and_instances_do_not_mix(self):
        def reasoning(*args,**kwargs):
            yield {"type":"reasoning","text":"separate"}
            yield {"type":"delta","text":"answer"}
            yield {"type":"done"}
        with patch.object(web,"stream_chat",side_effect=reasoning):
            first=list(web.chat_stream_exchange(self.folder,{**self.payload,"instance_id":"1"*32}))[-1]
        self.assertEqual(first["messages"][-1],{"role":"assistant","content":"answer","reasoning_content":"separate"})
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat",instance_id="2"*32),[])
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat"),[])

    def test_context_omissions_are_observable_and_do_not_delete_history(self):
        messages=[{"role":"user" if i%2==0 else "assistant","content":"x"*100} for i in range(20)]
        selected,info=chat_store.context_for(messages,max_messages=4,max_chars=500,with_info=True)
        self.assertEqual(info["sent_history_messages"],4)
        self.assertEqual(info["omitted_messages"],16)
        self.assertEqual(len(messages),20)

    def test_old_schema_is_migrated_without_losing_legacy_messages(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.folder/"chat_history.sqlite3")) as db:
            db.execute(chat_store._SCHEMA)
            db.execute("INSERT INTO messages(manager_id,slot_id,model_id,role,content) VALUES('m','slot2','kat','user','old')")
            db.commit()
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat"),[{"role":"user","content":"old"}])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.payload={"manager_id":"m","slot_id":"slot2","model_id":"kat",
                      "message":"Hi","request_id":"a"*32}
        self.profiles=patch.object(web,"load_profiles",return_value=[{"manager_id":"m"}])
        self.profiles.start()
        self.addCleanup(self.profiles.stop)
    def events(self,*args,**kwargs):
        yield {"type":"meta"}
        yield {"type":"delta","text":"first "}
        yield {"type":"delta","text":"second"}
        yield {"type":"done","usage":{}}
    def test_stream_persists_one_atomic_exchange_replay_no_generation(self):
        with patch.object(web,"stream_chat",side_effect=self.events) as send:
            result=list(web.chat_stream_exchange(self.folder,self.payload))
            replay=list(web.chat_stream_exchange(self.folder,self.payload))
        self.assertEqual(result[-1]["messages"][-1]["content"],"first second")
        self.assertTrue(replay[-1]["cached"])
        self.assertEqual(send.call_count,1)
        self.assertEqual(len(chat_store.history(self.folder,"m","slot2","kat")),2)
    def test_truncation_and_cancel_never_save_partial_or_retry_automatically(self):
        def broken(*args,**kwargs):
            yield {"type":"delta","text":"partial"}
        with patch.object(web,"stream_chat",side_effect=broken):
            with self.assertRaisesRegex(web.ChatClientError,"stream_truncated"):
                list(web.chat_stream_exchange(self.folder,self.payload))
            with self.assertRaisesRegex(web.ChatClientError,"already_attempted"):
                list(web.chat_stream_exchange(self.folder,self.payload))
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat"),[])
        payload={**self.payload,"request_id":"b"*32}
        with patch.object(web,"stream_chat",side_effect=self.events):
            stream=web.chat_stream_exchange(self.folder,payload)
            next(stream);next(stream)
            stream.close()
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat"),[])
    def test_id_conflict_and_manager_histories_isolated(self):
        with patch.object(web,"stream_chat",side_effect=self.events):
            list(web.chat_stream_exchange(self.folder,self.payload))
            with self.assertRaisesRegex(ValueError,"request_id_conflict"):
                list(web.chat_stream_exchange(self.folder,{**self.payload,"message":"Other"}))
        self.assertEqual(chat_store.history(self.folder,"other","slot2","kat"),[])
    def test_simultaneous_stream_rejected_and_lock_released_on_cancel(self):
        with patch.object(web,"stream_chat",side_effect=self.events):
            first=web.chat_stream_exchange(self.folder,self.payload)
            next(first)
            with self.assertRaisesRegex(web.ChatClientError,"chat_in_progress"):
                list(web.chat_stream_exchange(self.folder,{**self.payload,"request_id":"b"*32}))
            first.close()
            list(web.chat_stream_exchange(self.folder,{**self.payload,"request_id":"c"*32}))
    def test_long_reply_next_context_does_not_break_manager_limit(self):
        messages=[{"role":"user","content":"Hi"},{"role":"assistant","content":"x"*5000}]
        self.assertEqual(chat_store.context_for(messages),messages)
        self.assertEqual(chat_store.context_for(messages,max_chars=4000),[])

    def test_explicit_cancel_prevents_final_sqlite_commit(self):
        with patch.object(web,"stream_chat",side_effect=self.events):
            stream=web.chat_stream_exchange(self.folder,self.payload)
            next(stream)
            active=next(iter(web.ACTIVE_STREAMS.values()))
            active.set()
            with self.assertRaisesRegex(web.ChatClientError,"stream_cancelled"):
                list(stream)
        self.assertEqual(chat_store.history(self.folder,"m","slot2","kat"),[])

    def test_ordinary_mode_idempotent_with_new_request_id_contract(self):
        with patch.object(web,"send_chat",return_value={"reply":"ordinary"}) as send:
            first=web.chat_exchange(self.folder,self.payload)
            second=web.chat_exchange(self.folder,self.payload)
        self.assertEqual(send.call_count,1)
        self.assertTrue(second["cached"])
        self.assertEqual(first["messages"],second["messages"])

    def test_large_history_not_embedded_in_final_stream_frame(self):
        messages=[{"role":"assistant","content":"я"*65536} for _ in range(5)]
        self.assertTrue(web.stream_history_event({"type":"done"},messages)["history_reload"])


class StreamTransportTests(unittest.TestCase):
    def test_identity_mismatch_and_missing_done_refused(self):
        from email.message import Message
        import io
        from contextlib import contextmanager
        headers=Message();headers['Content-Type']='application/x-ndjson'
        @contextmanager
        def response(data):
            r=io.BytesIO(data);r.headers=headers
            yield r
        for data in (b'{"type":"meta","manager_id":"wrong"}\n',
                     b'{"type":"meta","manager_id":"m","slot_id":"s","model_id":"q"}\n'):
            with patch.object(chat_client,"manager_open",return_value=response(data)):
                with self.assertRaises(chat_client.ChatClientError):
                    list(chat_client.stream_chat({"manager_id":"m"},"s","q",[]))


class FullChainTests(unittest.TestCase):
    def test_colibri_manager_client_browser_http_first_fragment_before_done(self):
        # All sockets are ephemeral loopback. TLS helper is replaced ONLY here
        # because production credentials/certificates must remain untouched.
        manager_dir=Path(web.__file__).parent.parent/'Manager_Ultra_LLM'
        sys.path.insert(0,str(manager_dir))
        self.addCleanup(sys.path.remove,str(manager_dir))
        import live_manager
        from pairing_inbox import PairingInbox
        gate=threading.Event()
        self.addCleanup(gate.set)
        class FakeColibri(BaseHTTPRequestHandler):
            def do_POST(h):
                h.rfile.read(int(h.headers['Content-Length']))
                h.send_response(200);h.send_header('Content-Type','text/event-stream');h.end_headers()
                def emit(text):
                    h.wfile.write(('data: '+json.dumps({'choices':[{'delta':{'content':text}}]},ensure_ascii=False)+'\n\n').encode());h.wfile.flush()
                try:
                    emit('первый ');gate.wait(4);emit('второй')
                    h.wfile.write(b'data: [DONE]\n\n');h.wfile.flush()
                except OSError: pass
            def log_message(h,*a):pass
        def serve(handler):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            return server
        upstream=serve(FakeColibri)
        config={'manager_id':'m','display_name':'fake','slots':[{'slot_id':'slot2','api_port':upstream.server_address[1]}]}
        principal={'client_id':'alice','allowed_slots':['slot2']}
        snapshot={'source':'LIVE_HOST','viewer_id':'alice','slots':[{'slot_id':'slot2','instance_id':'legacy-fixture','engine_state':'ready','availability':'ready_unreserved','models':['kat']}]}
        # Keep all validation/select_backend/lock/stream handlers real.
        with patch.object(live_manager,'load_config',return_value=config), \
             patch.object(live_manager,'_authorized_client',return_value=principal), \
             patch.object(live_manager,'chat_snapshot',return_value=snapshot):
            config.update({'bind_host':'127.0.0.1','listen_port':12345,'cert_file':'dummy','key_file':'dummy',
                           'colibri_root':'dummy','models_root':'dummy','allowed_client_ips':['127.0.0.1']})
            manager=serve(live_manager.make_handler(Path('unused'),config,PairingInbox()))
            opener=build_opener(ProxyHandler({}))
            def manager_open(profile,path,payload=None,**kwargs):
                return opener.open(Request(f'http://127.0.0.1:{manager.server_address[1]}'+path,
                    data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=5)
            with tempfile.TemporaryDirectory() as directory, \
                 patch.object(web,'load_profiles',return_value=[{'manager_id':'m'}]), \
                 patch.object(chat_client,'manager_open',side_effect=manager_open):
                holder={'port':0}
                local=serve(web.make_handler(Path(directory),lambda:holder['port'],'TEST-CSRF'))
                holder['port']=local.server_address[1]
                origin=f'http://127.0.0.1:{holder["port"]}'
                payload={'manager_id':'m','slot_id':'slot2','model_id':'kat','message':'Hi','request_id':'d'*32}
                req=Request(origin+'/api/chat/stream',data=json.dumps(payload).encode(),headers={
                    'Content-Type':'application/json','X-Ultra-CSRF':'TEST-CSRF','Origin':origin})
                started=time.monotonic()
                with opener.open(req,timeout=5) as r:
                    self.assertEqual(json.loads(r.readline())['type'],'meta')
                    self.assertEqual(json.loads(r.readline())['text'],'первый ')
                    self.assertFalse(gate.is_set())
                    self.assertLess(time.monotonic()-started,1.5)
                    gate.set()
                    rest=[json.loads(line) for line in r]
                self.assertEqual(rest[-1]['type'],'done')
                self.assertEqual(rest[-1]['messages'][-1]['content'],'первый второй')
                gate.clear()
                payload['request_id']='e'*32
                req=Request(origin+'/api/chat/stream',data=json.dumps(payload).encode(),headers={
                    'Content-Type':'application/json','X-Ultra-CSRF':'TEST-CSRF','Origin':origin})
                with opener.open(req,timeout=5) as r:
                    r.readline();r.readline()  # meta and first real fragment
                    cancel={k:v for k,v in payload.items() if k!='message'}
                    cancel_req=Request(origin+'/api/chat/cancel',data=json.dumps(cancel).encode(),headers={
                        'Content-Type':'application/json','X-Ultra-CSRF':'TEST-CSRF','Origin':origin})
                    started=time.monotonic()
                    with opener.open(cancel_req,timeout=5) as reply:
                        self.assertTrue(json.loads(reply.read())['upstream_cancelled'])
                    events=[json.loads(line) for line in r]
                    self.assertEqual(events[-1]['type'],'error')
                    self.assertLess(time.monotonic()-started,1.5)
                self.assertEqual(len(chat_store.history(Path(directory),'m','slot2','kat')),2)


if __name__=='__main__':unittest.main()
