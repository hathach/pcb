"""Minimal CDP driver for the JLC order session (Chrome on :9222).

Usage:
  cdpenv/bin/python cdp.py eval  '<js expression>'          # evaluate in page
  cdpenv/bin/python cdp.py nav   '<url>'
  cdpenv/bin/python cdp.py shot  out.png [quality]          # viewport screenshot
  cdpenv/bin/python cdp.py click <css-x> <css-y>            # real input click
  cdpenv/bin/python cdp.py type  '<text>'
  cdpenv/bin/python cdp.py files '<css selector>' /path/a [/path/b ...]  # attach to <input type=file>
  cdpenv/bin/python cdp.py tabs
All commands target the first page tab whose URL contains 'jlcpcb' (else first page).
"""
import base64
import json
import sys
import urllib.request

import websocket

DEBUG_HTTP = "http://localhost:9222"


def pages():
    with urllib.request.urlopen(DEBUG_HTTP + "/json/list") as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def target():
    ts = pages()
    for t in ts:
        if "jlcpcb" in t.get("url", ""):
            return t
    assert ts, "no page targets"
    return ts[0]


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True,
                                              max_size=50 * 1024 * 1024)
        self.mid = 0

    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


def main():
    op = sys.argv[1]
    if op == "tabs":
        for t in pages():
            print(t["id"], "|", t.get("title", "")[:50], "|", t.get("url", "")[:90])
        return
    t = target()
    c = CDP(t["webSocketDebuggerUrl"])
    if op == "eval":
        r = c.cmd("Runtime.evaluate", expression=sys.argv[2], returnByValue=True,
                  awaitPromise=True, userGesture=True)
        res = r.get("result", {})
        if res.get("subtype") == "error" or r.get("exceptionDetails"):
            print("JS ERROR:", json.dumps(r.get("exceptionDetails", res))[:800])
        else:
            v = res.get("value")
            print(json.dumps(v) if not isinstance(v, str) else v)
    elif op == "nav":
        c.cmd("Page.enable")
        c.cmd("Page.navigate", url=sys.argv[2])
        print("navigated")
    elif op == "shot":
        path = sys.argv[2]
        q = int(sys.argv[3]) if len(sys.argv) > 3 else 70
        r = c.cmd("Page.captureScreenshot", format="jpeg", quality=q)
        open(path, "wb").write(base64.b64decode(r["data"]))
        print("saved", path)
    elif op == "click":
        x, y = float(sys.argv[2]), float(sys.argv[3])
        for typ in ("mousePressed", "mouseReleased"):
            c.cmd("Input.dispatchMouseEvent", type=typ, x=x, y=y,
                  button="left", clickCount=1)
        print("clicked", x, y)
    elif op == "type":
        for ch in sys.argv[2]:
            c.cmd("Input.dispatchKeyEvent", type="char", text=ch)
        print("typed")
    elif op == "files":
        sel = sys.argv[2]
        paths = sys.argv[3:]
        doc = c.cmd("DOM.getDocument")
        node = c.cmd("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=sel)
        assert node.get("nodeId"), f"selector not found: {sel}"
        c.cmd("DOM.setFileInputFiles", files=paths, nodeId=node["nodeId"])
        print("files attached:", paths)
    else:
        raise SystemExit("unknown op")


if __name__ == "__main__":
    main()
