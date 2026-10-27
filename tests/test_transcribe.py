import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
from scipy.io import wavfile

from confmerge import transcribe as tr
from confmerge.secrets_store import KeyStore, masked

SEEN = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer good":
            return self._send(401, {"error": {"message": "bad"}})
        self._send(200, {"data": [{"id": tr.MODEL}]})

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        body = self.rfile.read(n)
        SEEN.append((self.headers.get("Authorization"), self.headers.get("User-Agent"), body))
        if self.headers.get("Authorization") != "Bearer good":
            return self._send(401, {})
        self._send(200, {
            "text": "ciao a tutti. questo è un test",
            "segments": [{"start": 0.0, "end": 1.2, "text": " ciao a tutti.", "no_speech_prob": 0.01, "avg_logprob": -0.2},
                         {"start": 1.5, "end": 3.0, "text": " questo è un test", "no_speech_prob": 0.01, "avg_logprob": -0.2},
                         {"start": 4.0, "end": 5.0, "text": " Sottotitoli creati dalla comunità Amara.org"}],
            "words": [{"word": "ciao", "start": 0.0, "end": 0.4}, {"word": "a", "start": 0.4, "end": 0.5},
                      {"word": "tutti.", "start": 0.5, "end": 1.2}, {"word": "questo", "start": 1.5, "end": 1.9},
                      {"word": "è", "start": 1.9, "end": 2.0}, {"word": "un", "start": 2.0, "end": 2.2},
                      {"word": "test", "start": 2.2, "end": 3.0}, {"word": "Sottotitoli", "start": 4.0, "end": 4.5}]})


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_check_key(server):
    assert "funziona" in tr.check_key("good", server)
    with pytest.raises(tr.TranscribeError, match="non è valida"):
        tr.check_key("bad", server)
    with pytest.raises(tr.TranscribeError, match="Incolla"):
        tr.check_key("  ", server)


def test_unreachable():
    with pytest.raises(tr.TranscribeError, match="internet"):
        tr.check_key("good", "http://127.0.0.1:9")


def test_chunk_request_and_parse(server, tmp_path):
    f = tmp_path / "a.flac"
    f.write_bytes(b"fLaC-fake")
    data = tr.transcribe_chunk(f, "good", "it", "Mario Rossi", server)
    auth, ua, body = SEEN[-1]
    assert auth == "Bearer good" and ua.startswith("ConfMerge")
    for needle in (b'name="model"', tr.MODEL.encode(), b"timestamp_granularities[]", b"verbose_json", b"Mario Rossi", b"fLaC-fake"):
        assert needle in body
    words = tr.parse_words(data, offset=10.0)
    assert [w.text for w in words][:3] == ["ciao", "a", "tutti."]
    assert all("Sottotitoli" != w.text for w in words)          # allucinazione scartata
    assert words[0].start == 10.0 and words[-1].end == 13.0


def test_parse_without_word_times():
    words = tr.parse_words({"segments": [{"start": 0, "end": 4, "text": " uno due tre quattro", "no_speech_prob": 0}]}, 5.0)
    assert [w.text for w in words] == ["uno", "due", "tre", "quattro"]
    assert words[0].start == 5.0 and abs(words[-1].end - 9.0) < 1e-6
    assert all(a.end <= b.start + 1e-9 for a, b in zip(words, words[1:]))


def test_build_lines():
    ws = [tr.Word(t, i * 0.4, i * 0.4 + 0.35) for i, t in enumerate("una frase abbastanza lunga da spezzare in due righe. e poi un'altra".split())]
    lines = tr.build_lines(ws, max_chars=30)
    assert len(lines) >= 3 and all(len(ln.text) <= 36 for ln in lines)
    assert all(a.end <= b.start for a, b in zip(lines, lines[1:]))
    pause = [tr.Word("a", 0, 0.3), tr.Word("b", 5, 5.3)]
    assert len(tr.build_lines(pause)) == 2


def test_plan_chunks_cut_in_silence():
    sr = 16000
    x = np.random.default_rng(0).standard_normal(sr * 700).astype(np.float32) * 0.1
    x[sr * 310:sr * 311] = 0                                    # un secondo di silenzio vicino al confine di 300 s
    ch = tr.plan_chunks(x, sr)
    assert ch[0][0] == 0 and abs(ch[-1][1] - 700) < 1e-6 and len(ch) == 3
    assert 310 <= ch[0][1] <= 311
    assert tr.plan_chunks(x[:sr * 100], sr) == [(0.0, 100.0)]


def test_cost():
    assert abs(tr.estimate_cost(3600) - tr.COST_PER_HOUR) < 1e-9
    assert tr.estimate_cost(1) == tr.estimate_cost(10)


def test_key_store(tmp_path, monkeypatch):
    ks = KeyStore(tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not ks.has("groq")
    ks.set("groq", "  gsk_abcdef123456  ")
    assert ks.get("groq") == "gsk_abcdef123456" and KeyStore(tmp_path).get("groq") == "gsk_abcdef123456"
    ks.set("groq", "")
    assert ks.get("groq") == ""
    monkeypatch.setenv("GROQ_API_KEY", "envkey")
    assert ks.get("groq") == "envkey"
    assert masked("gsk_abcdef123456") == "gsk_…3456" and masked("") == ""


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg assente")
def test_transcribe_wav_end_to_end(server, tmp_path):
    sr = 16000
    x = (np.random.default_rng(1).standard_normal(sr * 20) * 0.1 * 32767).astype("<i2")
    wavfile.write(str(tmp_path / "a.wav"), sr, x)
    prog = []
    words = tr.transcribe_wav(tmp_path / "a.wav", "good", tmp_path / "w", "it", "", lambda f, m: prog.append(m), None, server)
    assert words and prog[-1].startswith("Trascrizione completata")
    assert not list((tmp_path / "w").glob("*.flac"))
