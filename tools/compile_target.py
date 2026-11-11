#!/usr/bin/env python3
"""Compile target image(s) into a MindAR .mind file using a headless browser.

Why a browser: MindAR's compiler is designed to run in a browser (the official
online compiler does the same). Its Node.js variant needs a native `canvas`
package that failed to build in our environment, so this tool drives Chrome.
This is also the prototype of the future admin "compile on upload" step (F09).

Usage:
  python3 compile_target.py <out.mind> <image1.png> [image2.png ...]
Order of images == targetIndex order used by the customer app.
Requires: python3 + playwright (pip) and Google Chrome / Chromium.
"""
import base64
import http.server
import os
import shutil
import sys
import tempfile
import threading
from functools import partial

from playwright.sync_api import sync_playwright

if len(sys.argv) < 3:
    sys.exit(__doc__)
out_path, images = sys.argv[1], sys.argv[2:]

HERE = os.path.dirname(os.path.abspath(__file__))
MINDAR_DIST = os.path.join(HERE, "..", "frontend", "customer", "node_modules",
                           "mind-ar", "dist")

work = tempfile.mkdtemp(prefix="mind-compile-")
# The dist files are ES modules split into chunks, so copy the whole folder.
for fn in os.listdir(MINDAR_DIST):
    shutil.copy(os.path.join(MINDAR_DIST, fn), os.path.join(work, fn))
names = []
for i, p in enumerate(images):
    n = f"img{i}{os.path.splitext(p)[1]}"
    shutil.copy(p, os.path.join(work, n))
    names.append(n)
with open(os.path.join(work, "index.html"), "w") as f:
    f.write("<!doctype html><script type='module' src='mindar-image.prod.js'></script><body>ok</body>")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=work))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

JS = """
async (names) => {
  const loadImg = (src) => new Promise((res, rej) => {
    const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = src;
  });
  const imgs = await Promise.all(names.map(loadImg));
  const compiler = new window.MINDAR.IMAGE.Compiler();
  let last = 0;
  await compiler.compileImageTargets(imgs, (p) => { last = p; });
  const buf = await compiler.exportData();
  let bin = ''; const u8 = new Uint8Array(buf);
  for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(bin);
}
"""

chrome = next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser")
               if os.path.exists(p)), None)
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
    page = browser.new_page()
    page.on("console", lambda m: print("[browser]", m.text) if m.type == "error" else None)
    page.goto(f"http://127.0.0.1:{port}/index.html")
    page.wait_for_function("() => !!(window.MINDAR && window.MINDAR.IMAGE && window.MINDAR.IMAGE.Compiler)")
    b64 = page.evaluate(JS, [f"http://127.0.0.1:{port}/{n}" for n in names])
    browser.close()
srv.shutdown()
shutil.rmtree(work, ignore_errors=True)

data = base64.b64decode(b64)
with open(out_path, "wb") as f:
    f.write(data)
print(f"wrote {out_path} ({len(data)} bytes) from {len(images)} image(s)")
