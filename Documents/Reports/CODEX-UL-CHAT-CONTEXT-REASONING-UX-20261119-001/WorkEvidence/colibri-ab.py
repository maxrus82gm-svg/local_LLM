"""Render with deployed Colibri Python source and optionally tokenize before model init."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace


def probe(source, inputs=None):
    sys.path.insert(0, str(source))
    import openai_server as api

    api.ARCH = "qwen36"
    os.environ["COLI_COMPACT"] = "1"

    class Boundary:
        server = SimpleNamespace()

        def expand_images(self, messages):
            return messages, None

        def generation(self, body, prompt, *args, **kwargs):
            self.prompt = prompt

    boundary = Boundary()

    def render(messages, thinking=True):
        started = time.perf_counter()
        api.APIHandler.chat_completion(boundary, {
            "messages": messages, "enable_thinking": thinking, "context_compaction": "off"}, "offline-probe")
        return boundary.prompt, round((time.perf_counter() - started)*1000, 3)

    def tokenize(prompt, tag):
        if inputs is None:
            return None
        # The workspace snapshot contains the tokenizer and executable/DLLs only.
        # TOK_ONLY takes the source's early return before model initialization.
        with tempfile.NamedTemporaryFile(dir=inputs, prefix=tag+"-", suffix=".txt", delete=False) as f:
            f.write(prompt.encode("utf-8"))
        keep = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA"}
        env = {k: v for k, v in os.environ.items() if k.upper() in keep}
        env.update(SNAP=str(inputs), TOK=str(inputs/"tokenizer.json"), TOK_ONLY="1",
                   CUDA_VISIBLE_DEVICES="-1", OMP_NUM_THREADS="1")
        result = subprocess.run([str(inputs/"qwen36.exe"), "0", "4", f.name], env=env, cwd=inputs,
            text=True, encoding="utf-8", errors="replace", capture_output=True, check=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return [int(token) for token in result.stdout.split()]

    current = [{"role": "user", "content": "SYNTHETIC_CURRENT"}]
    history = [{"role": role, "content": f"SYNTHETIC_{i}"}
               for i in range(10) for role in ("user", "assistant")]
    reasoning = [dict(m, reasoning_content="SYNTHETIC_REASON "*64) if m["role"] == "assistant" else m for m in history]
    for attempt in range(2):
        a = render(current)
        render(history)
        b = render(current)
        c = render(history + current)
        d = render(reasoning + current)
        e = render(current)
        f = render(current, False)
        cases = dict(A=a, B=b, C=c, D=d, E=e, F=f)
        tokens = {tag: tokenize(prompt, tag) for tag, (prompt, _) in cases.items()}
        assert a[0] == b[0] == e[0] and tokens["A"] == tokens["B"] == tokens["E"]
        assert c[0] != d[0] and "SYNTHETIC_REASON" in d[0] and a[0] != f[0]
        if inputs is not None:
            assert len(tokens["D"]) > len(tokens["C"])
        print(json.dumps({"attempt":attempt+1, "scope":"deployed gateway source; optional copied native tokenizer; no inference",
              "cases":{tag:{"prompt_chars":len(prompt), "gateway_render_ms":ms,
                            "native_token_count":len(tokens[tag]) if tokens[tag] is not None else None,
                            "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest()}
                       for tag, (prompt, ms) in cases.items()}}))


if __name__ == "__main__":
    probe(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else None)
