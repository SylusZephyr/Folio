import json
import random
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from conftest import make_pdf, page_ids
from folio import server


@pytest.fixture
def base(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(server, "WORK", work)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = server.make_handler(server.State(), port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()


def call(base, path, data=None, headers=None):
    """(status, body) for a request; JSON bodies are decoded."""
    req = urllib.request.Request(base + path, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req) as r:
            status, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        status, body, ctype = e.code, e.read(), e.headers.get("Content-Type", "")
    return status, json.loads(body) if "json" in ctype else body


def upload(base, path, name=None):
    return call(base, f"/api/upload?name={name or path.name}", path.read_bytes())


def test_upload_merge_download_in_custom_order(base, tmp_path):
    files = [make_pdf(tmp_path / f"{i}.pdf", 100 + i, i % 4 + 1) for i in range(60)]
    ids = {}
    for f in files:
        status, res = upload(base, f)
        assert status == 200 and res["pages"] == int(f.stem) % 4 + 1
        ids[f] = res["id"]
    random.Random(1).shuffle(files)
    items = [{"id": ids[f], "range": ""} for f in files]
    items[0]["range"] = "1"  # first file: first page only
    status, res = call(base, "/api/merge", json.dumps({"items": items, "name": "My: Book", "bookmarks": True}).encode())
    assert status == 200, res
    assert res["name"] == "My_ Book.pdf"  # characters Windows can't use in a filename are replaced

    status, pdf = call(base, f"/api/file/{res['id']}?download=1")
    assert status == 200
    out = tmp_path / "result.pdf"
    out.write_bytes(pdf)
    expected = page_ids(files[0])[:1] + [p for f in files[1:] for p in page_ids(f)]
    assert page_ids(out) == expected
    assert res["pages"] == len(expected)


def test_bad_uploads_are_rejected_with_reason(base, tmp_path):
    junk = tmp_path / "scan.pdf"
    junk.write_bytes(b"definitely not a pdf")
    status, res = upload(base, junk)
    assert status == 422 and "scan.pdf is damaged" in res["error"]
    status, res = upload(base, make_pdf(tmp_path / "locked.pdf", 100, password="pw"))
    assert status == 422 and "password-protected" in res["error"]


def test_merge_validation(base, tmp_path):
    _, res = upload(base, make_pdf(tmp_path / "a.pdf", 100, 3))
    status, err = call(base, "/api/merge", json.dumps({"items": [{"id": res["id"], "range": "2-9"}]}).encode())
    assert status == 400 and "page 9 doesn't exist" in err["error"]
    status, err = call(base, "/api/merge", json.dumps({"items": [{"id": "f" * 32}]}).encode())
    assert status == 400 and "no longer available" in err["error"]
    status, err = call(base, "/api/merge", b"not json")
    assert status == 400


def test_discard_removes_upload(base, tmp_path):
    _, res = upload(base, make_pdf(tmp_path / "a.pdf", 100))
    assert call(base, "/api/discard", json.dumps([res["id"]]).encode())[0] == 200
    assert not (server.WORK / f"in_{res['id']}.pdf").exists()
    status, err = call(base, "/api/merge", json.dumps({"items": [{"id": res["id"]}]}).encode())
    assert status == 400


def test_other_websites_cannot_use_the_server(base):
    assert call(base, "/api/ping", b"", {"Origin": "https://evil.example"})[0] == 403
    port = base.rsplit(":", 1)[1]
    assert call(base, "/", headers={"Host": f"evil.example:{port}"})[0] == 403  # DNS rebinding
    assert call(base, "/api/ping", b"", {"Origin": base})[0] == 200


def test_static_files_cannot_escape_web_folder(base):
    assert call(base, "/static/app.js")[0] == 200
    assert call(base, "/static/../server.py")[0] == 404
    assert call(base, "/static/..%2Fserver.py")[0] == 404
