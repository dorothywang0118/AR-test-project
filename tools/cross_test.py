#!/usr/bin/env python3
"""For every target image: show it to the fake camera and list which targets the engine reports as
visible (should be exactly one). Usage: python3 cross_test.py <img1.png> <img2.png> ..."""
import functools, http.server, os, re, subprocess, sys, tempfile, threading, time
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "frontend", "customer", "dist")
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=DIST))
threading.Thread(target=srv.serve_forever, daemon=True).start()
chrome = next(p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(p))
tmp = tempfile.mkdtemp()
with sync_playwright() as pw:
    for img in sys.argv[1:]:
        y4m = os.path.join(tmp, "cam.y4m")
        subprocess.run([sys.executable, os.path.join(HERE, "make_fake_camera.py"), img, y4m], check=True, capture_output=True)
        b = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox", "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream", f"--use-file-for-fake-video-capture={y4m}", "--use-gl=angle",
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = b.new_context(viewport={"width": 390, "height": 760}, is_mobile=True).new_page()
        page.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html?debug=1")
        page.click("#btn-start")
        page.wait_for_function("() => !document.getElementById('hud').hidden", timeout=120000)
        seen = set()
        for _ in range(14):
            time.sleep(1)
            m = re.search(r"visible: (.*)", page.inner_text("#debug"))
            if m and m.group(1) != "—":
                seen |= set(m.group(1).split(","))
        print(os.path.basename(img), "->", sorted(seen) or "NOT FOUND")
        b.close()
