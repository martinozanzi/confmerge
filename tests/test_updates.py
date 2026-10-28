import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from confmerge import updates


def test_parse_and_compare_versions():
    assert updates.parse_version("v1.2.0") == (1, 2, 0)
    assert updates.parse_version("1.10") == (1, 10)
    assert updates.parse_version("beta") == ()
    assert updates.is_newer((1, 2), (1, 1, 0)) and updates.is_newer((1, 10), (1, 9, 9))
    assert not updates.is_newer((1, 1), (1, 1, 0)) and not updates.is_newer((1, 0, 9), (1, 1, 0)) and not updates.is_newer(())


@pytest.fixture
def server():
    state = {"code": 200, "body": {}}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            raw = json.dumps(state["body"]).encode()
            self.send_response(state["code"])
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{srv.server_port}/latest"
    srv.shutdown()


def test_latest_release_picks_exe_asset(server):
    state, url = server
    state["body"] = {"tag_name": "v9.0.0", "html_url": "https://example/r", "body": "Novità",
                     "assets": [{"name": "ConfMerge-cartella.zip", "browser_download_url": "https://example/zip"},
                                {"name": "ConfMerge.exe", "browser_download_url": "https://example/exe"}]}
    rel = updates.latest_release(url)
    assert rel.version == (9, 0, 0) and rel.download == "https://example/exe" and rel.page == "https://example/r"
    state["body"]["assets"] = []
    assert updates.latest_release(url).download == "https://example/r"        # senza file: porta alla pagina della release


def test_no_release_and_errors(server):
    state, url = server
    state["code"] = 404
    assert updates.latest_release(url) is None
    state["code"] = 500
    with pytest.raises(updates.UpdateError):
        updates.latest_release(url)
    with pytest.raises(updates.UpdateError, match="internet"):
        updates.latest_release("http://127.0.0.1:1/x", timeout=1)
