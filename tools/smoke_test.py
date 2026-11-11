#!/usr/bin/env python3
"""Headless-Chrome smoke test of the customer app with a FAKE camera.

Checks: camera starts, target is recognised, character is tappable, Stop releases
everything, and a second Start works. It proves the code path, not phone behaviour.
Usage: python3 smoke_test.py   (run `npm run build` in frontend/customer first)
"""
import functools, http.server, os, re, sys, threading, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "frontend", "customer", "dist")
Y4M = os.path.join(HERE, "testdata", "fake-camera.y4m")
SHOTS = os.environ.get("SHOT_DIR", HERE)

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=DIST))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/index.html?debug=1"

chrome = next(p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(p))
ok = True
def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS" if cond else "FAIL"), name, extra)

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=chrome, args=[
        "--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-video-capture={Y4M}",
        "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 390, "height": 760}, has_touch=True, is_mobile=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "404" not in m.text else None)

    def run_once(label):
        page.goto(url)
        page.wait_for_selector("#btn-start")
        page.click("#btn-start")
        try:
            page.wait_for_function("() => !document.getElementById('hud').hidden", timeout=90000)
        except Exception:
            print("screens:", page.evaluate("() => [...document.querySelectorAll('.screen')].map(s=>s.id+':'+s.hidden)"),
                  page.inner_text("#error-title"), page.inner_text("#error-body"))
            raise
        check(f"[{label}] AR screen shown (camera + engine started)", True)
        try:
            page.wait_for_function("() => document.getElementById('hint').classList.contains('found')", timeout=60000)
            found = True
        except Exception:
            found = False
        check(f"[{label}] target recognised", found, page.inner_text("#debug").replace("\n", " | ")[:200])
        page.screenshot(path=os.path.join(SHOTS, f"smoke-{label}.png"))
        # tap a grid of points around the centre until the character is hit
        for dx in (0, -40, 40, -80, 80):
            for dy in (0, -60, 60, -120, 120):
                page.mouse.click(195 + dx, 380 + dy)
        time.sleep(0.5)
        dbg = page.inner_text("#debug")
        m = re.search(r"taps hit/total: (\d+)/(\d+)", dbg)
        check(f"[{label}] character tappable", m and int(m.group(1)) > 0, m.group(0) if m else dbg)
        page.screenshot(path=os.path.join(SHOTS, f"smoke-{label}-after-tap.png"))

    run_once("run1")
    page.click("#btn-stop")
    time.sleep(0.5)
    left = page.evaluate("() => document.querySelectorAll('#ar-container video, #ar-container canvas').length")
    check("Stop removes video + canvas elements", left == 0, f"left={left}")
    check("Intro screen shown after Stop", page.evaluate("() => !document.getElementById('screen-intro').hidden"))
    page.click("#btn-start")  # second start without reloading the page
    page.wait_for_function("() => !document.getElementById('hud').hidden", timeout=90000)
    page.wait_for_function("() => document.getElementById('hint').classList.contains('found')", timeout=60000)
    check("Second Start works and recognises again", True)
    check("No page errors", not errors, "; ".join(errors)[:300])
    b.close()
srv.shutdown()
print("RESULT:", "ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
