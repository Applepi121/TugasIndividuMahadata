import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


class _State:
    def __init__(self):
        self.dbs = {}
        self.lock = threading.Lock()


def make_server():
    st = _State()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def _parts(self):
            u = urlparse(self.path)
            return [unquote(p) for p in u.path.strip("/").split("/") if p], parse_qs(u.query)

        def do_GET(self):
            parts, q = self._parts()
            with st.lock:
                if not parts:
                    return self._send(200, {"couchdb": "Welcome", "version": "fake-1.0"})
                db = st.dbs.get(parts[0])
                if db is None:
                    return self._send(404, {"error": "not_found"})
                if len(parts) == 2 and parts[1] == "_all_docs":
                    start = json.loads(q["startkey"][0]) if "startkey" in q else ""
                    limit = int(q.get("limit", ["1000000"])[0])
                    keys = sorted(k for k in db if k >= start)[:limit]
                    return self._send(200, {"rows": [{"id": k, "doc": db[k]} for k in keys]})
                doc = db.get(parts[1])
                if doc is None:
                    return self._send(404, {"error": "not_found"})
                return self._send(200, doc)

        def do_PUT(self):
            parts, _ = self._parts()
            data = self._body()
            with st.lock:
                if len(parts) == 1:
                    st.dbs[parts[0]] = {}
                    return self._send(201, {"ok": True})
                db = st.dbs.get(parts[0])
                if db is None:
                    return self._send(404, {"error": "not_found"})
                key = parts[1]
                cur = db.get(key)
                if cur is not None and data.get("_rev") != cur["_rev"]:
                    return self._send(409, {"error": "conflict"})
                rev = int(cur["_rev"].split("-")[0]) + 1 if cur else 1
                db[key] = {**data, "_id": key, "_rev": f"{rev}-x"}
                return self._send(201, {"ok": True, "rev": f"{rev}-x"})

        def do_DELETE(self):
            parts, _ = self._parts()
            with st.lock:
                if parts[0] in st.dbs:
                    del st.dbs[parts[0]]
                    return self._send(200, {"ok": True})
                return self._send(404, {"error": "not_found"})

        def do_POST(self):
            parts, _ = self._parts()
            data = self._body()
            with st.lock:
                db = st.dbs[parts[0]]
                for d in data["docs"]:
                    db[d["_id"]] = {**d, "_rev": "1-x"}
                return self._send(201, [{"ok": True, "id": d["_id"]} for d in data["docs"]])

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv