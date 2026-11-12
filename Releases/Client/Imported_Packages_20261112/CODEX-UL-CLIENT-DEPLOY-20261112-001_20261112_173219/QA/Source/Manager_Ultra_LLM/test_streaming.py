"""Real loopback HTTP fragmentation with a fake Colibri, no live models/TLS."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from chat_runtime import proxy_stream, ChatError


class StreamingTests(unittest.TestCase):
    def test_combined_delta_order_and_reasoning_only_completion(self):
        combined=b'data: {"choices":[{"delta":{"reasoning_content":"why","content":"answer"}}]}\n\n'
        events=list(proxy_stream(self.upstream([combined,b'data: [DONE]\n\n']),"test",[]))
        self.assertEqual([e["type"] for e in events],["reasoning","delta","done"])
        self.assertEqual([e["sequence"] for e in events[:-1]],[1,2])
        events=list(proxy_stream(self.upstream([self.delta("only","reasoning_content"),b'data: [DONE]\n\n']),"test",[]))
        self.assertEqual(events[-1]["type"],"done")

    def test_generation_options_are_explicit_and_defaults_inherit_engine(self):
        from chat_settings import upstream_options
        self.assertEqual(upstream_options(),{})
        self.assertEqual(upstream_options({"thinking":"on","max_output_tokens":2048}),
                         {"enable_thinking":True,"max_tokens":2048})
        with self.assertRaisesRegex(ValueError,"thinking_not_supported"):
            upstream_options({"thinking":"on"},thinking_supported=False)
        with self.assertRaises(ValueError):
            upstream_options({"executable":"cmd.exe"})

    def test_wrong_upstream_model_rejected(self):
        event=b'data: {"model":"foreign","choices":[{"delta":{"content":"no"}}]}\n\n'
        with self.assertRaisesRegex(ChatError,"identity_mismatch"):
            list(proxy_stream(self.upstream([event]),"test",[]))
    def upstream(self, segments, *, gate=None, content_type="text/event-stream"):
        class Fake(BaseHTTPRequestHandler):
            def do_POST(h):
                payload=json.loads(h.rfile.read(int(h.headers["Content-Length"])))
                self.assertTrue(payload["stream"])
                h.send_response(200)
                h.send_header("Content-Type",content_type)
                h.end_headers()
                try:
                    for index,segment in enumerate(segments):
                        h.wfile.write(segment)
                        h.wfile.flush()
                        if gate and index==0:
                            gate.wait(3)
                except OSError:
                    pass
            def log_message(h,*a): pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Fake)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join,3)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]
    @staticmethod
    def delta(value,field="content"):
        return ("data: "+json.dumps({"choices":[{"delta":{field:value}}]},ensure_ascii=False)+"\n\n").encode()
    def test_first_real_delta_before_upstream_completes(self):
        gate=threading.Event()
        self.addCleanup(gate.set)
        port=self.upstream([self.delta("Привет "),self.delta("мир"),b"data: [DONE]\n\n"],gate=gate)
        events=proxy_stream(port,"test",[{"role":"user","content":"Hi"}])
        started=time.monotonic()
        first=next(events)
        self.assertEqual((first["type"],first["text"],first["sequence"]),("delta","Привет ",1))
        self.assertIn("colibri_first_fragment_unix_ms",first["timing"])
        self.assertFalse(gate.is_set())
        self.assertLess(time.monotonic()-started,1)
        gate.set()
        remaining=list(events)
        self.assertEqual(remaining[0]["text"],"мир")
        self.assertEqual(remaining[-1]["type"],"done")
        self.assertIn("first_fragment_ms",remaining[-1]["timing"])
        self.assertEqual(remaining[-1]["usage"],{})
        self.assertEqual(remaining[-1]["throughput"],{})
    def test_truncated_or_unsupported_or_invalid_sse_fails(self):
        for segments,mime in (([self.delta("partial")],"text/event-stream"),
                              ([b'data: invalid\n\n'],"text/event-stream"),
                              ([b'{}'],"application/json"),
                              ([b'data: [DONE]\n\n'],"text/event-stream")):
            with self.subTest(mime=mime),self.assertRaises(ChatError):
                list(proxy_stream(self.upstream(segments,content_type=mime),"test",[]))
    def test_separate_reasoning_and_measured_usage_only(self):
        usage=b'data: {"choices":[],"usage":{"completion_tokens":2,"prompt_tokens":3,"made_up":99}}\n\n'
        events=list(proxy_stream(self.upstream([self.delta("separate","reasoning_content"),
            self.delta("answer"),usage,b'data: [DONE]\n\n']),"test",[]))
        self.assertEqual(events[0]["type"],"reasoning")
        self.assertEqual(events[1]["type"],"delta")
        self.assertEqual(events[-1]["usage"],{"completion_tokens":2,"prompt_tokens":3})
        throughput=events[-1]["throughput"]
        self.assertIn("including_prefill",throughput["basis"])
        self.assertAlmostEqual(throughput["completion_tokens_per_second"],2000/throughput["window_ms"],delta=1)
    def test_bounded_output(self):
        port=self.upstream([self.delta("x"*40000),self.delta("y"*40000)])
        with self.assertRaisesRegex(ChatError,"stream_too_large"):
            from chat_settings import policy
            list(proxy_stream(port,"test",[],policy={**policy(),"response_chars":65536}))
    def test_deadline(self):
        port=self.upstream([self.delta("first"),b'data: [DONE]\n\n'])
        with self.assertRaisesRegex(ChatError,"stream_deadline"):
            list(proxy_stream(port,"test",[],timeout=0))

    def test_absolute_deadline_interrupts_wait_for_next_fragment(self):
        gate=threading.Event()
        self.addCleanup(gate.set)
        stream=proxy_stream(self.upstream([self.delta("first"),b'data: [DONE]\n\n'],gate=gate),"test",[],timeout=0.25)
        self.assertEqual(next(stream)["text"],"first")
        started=time.monotonic()
        with self.assertRaisesRegex(ChatError,"stream_deadline"):
            list(stream)
        self.assertLess(time.monotonic()-started,1)

    def test_cancel_interrupts_upstream_read_without_waiting_for_next_token(self):
        gate=threading.Event();cancelled=threading.Event()
        self.addCleanup(gate.set)
        stream=proxy_stream(self.upstream([self.delta("first"),b'data: [DONE]\n\n'],gate=gate),"test",[],cancelled=cancelled)
        self.assertEqual(next(stream)["text"],"first")
        timer=threading.Timer(0.1,cancelled.set);timer.start()
        self.addCleanup(timer.cancel)
        started=time.monotonic()
        with self.assertRaisesRegex(ChatError,"stream_cancelled"):
            list(stream)
        self.assertLess(time.monotonic()-started,1)


if __name__=="__main__": unittest.main()
