#!/usr/bin/env python3
"""Headless-Chrome check of one scan target: fake camera shows <target.png>, then we take
screenshots every 2 s so the animations / group show can be inspected.
Usage: python3 show_test.py <target.png> <out_prefix> [seconds]  (run `npm run build` first)"""
import functools, http.server, os, subprocess, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "frontend", "customer", "dist")
target, prefix = sys.argv[1], sys.argv[2]
secs = int(sys.argv[3]) if len(sys.argv) > 3 else 24
y4m = os.path.join(tempfile.mkdtemp(), "cam.y4m")
subprocess.run([sys.executable, os.path.join(HERE, "make_fake_camera.py"), target, y4m], check=True, capture_output=True)

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=DIST))
threading.Thread(target=srv.serve_forever, daemon=True).start()
chrome = next(p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(p))
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox", "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={y4m}", "--use-gl=angle",
        "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    page = b.new_context(viewport={"width": 390, "height": 760}, is_mobile=True, has_touch=True).new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" and "404" not in m.text else None)
    page.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html" + ("?debug=1" if os.environ.get("DEBUG") else ""))
    page.click("#btn-start")
    page.wait_for_function("() => !document.getElementById('hud').hidden", timeout=120000)
    page.wait_for_function("() => document.getElementById('hint').classList.contains('found')", timeout=90000)
    print("found")
    if os.environ.get("TAP"):
        for dx in (0, -30, 30):
            for dy in (0, -60, 60, -110, 40):
                page.mouse.click(195 + dx, 330 + dy)
    for i in range(secs // 2):
        page.screenshot(path=f"{prefix}-{i:02d}.png")
        time.sleep(2)
    if os.environ.get("DEBUG"):
        print(page.inner_text("#debug"))
    print("errors:", errs)
    b.close()
