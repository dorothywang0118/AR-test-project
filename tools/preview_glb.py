#!/usr/bin/env python3
"""Render a contact sheet (every character x every clip) of the chibi GLBs with headless Chrome.
Usage: python3 preview_glb.py <glb_dir> <out.png> [clip ...]"""
import http.server, json, os, shutil, sys, tempfile, threading
from functools import partial
from playwright.sync_api import sync_playwright

glb_dir, out = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
THREE = os.path.join(HERE, "..", "frontend", "customer", "node_modules", "three")
CLIPS = {"Cheer": 1.0, "FiveR": 1.3, "FiveL": 1.3, "PatShoulderR": 1.3, "PatShoulderL": 1.3, "Shy": 1.5, "Idle": 0.5, "Pat": 1.6, "HighFive": 1.3, "Cry": 1.5, "Sway": 0.35, "Angry": 1.0, "Think": 1.6, "Flop": 2.0}
if len(sys.argv) > 3:
    CLIPS = {k: v for k, v in CLIPS.items() if k in sys.argv[3:]}
work = tempfile.mkdtemp(prefix="glbprev-")
os.symlink(os.path.abspath(THREE), os.path.join(work, "three"))
for f in os.listdir(glb_dir):
    if f.endswith(".glb"):
        shutil.copy(os.path.join(glb_dir, f), work)
html = """<!doctype html><body style="margin:0;background:#fffaf0"><canvas id=c></canvas>
<script type=importmap>{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
<script type=module>
import * as T from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
const CLIPS = %s, IDS = ['a','b','c','d','e'];
const CW=300, CH=300, names=Object.keys(CLIPS);
const cv=document.getElementById('c'); cv.width=CW*IDS.length; cv.height=CH*names.length;
const r=new T.WebGLRenderer({canvas:cv,antialias:true,preserveDrawingBuffer:true}); r.setScissorTest(true); r.setClearColor(0xfffaf0,1);
const cam=new T.PerspectiveCamera(30,1,0.1,50); cam.position.set(0,0.62,3.4); cam.lookAt(0,0.55,0);
const gl=new GLTFLoader();
const errs=[];
for (let ci=0; ci<IDS.length; ci++){
  const g=await gl.loadAsync('/char-'+IDS[ci]+'.glb');
  const sc=new T.Scene(); sc.add(new T.AmbientLight(0xffffff,1.1)); const d=new T.DirectionalLight(0xffffff,1.6); d.position.set(.5,1,1.5); sc.add(d);
  sc.add(g.scene); const mx=new T.AnimationMixer(g.scene);
  for (let ri=0; ri<names.length; ri++){
    mx.stopAllAction(); mx.update(0);
    const clip=g.animations.find(a=>a.name===names[ri]); if(!clip){errs.push('missing '+names[ri]);continue;}
    const a=mx.clipAction(clip); a.play(); a.time=CLIPS[names[ri]]; mx.update(0);
    r.setViewport(ci*CW,(names.length-1-ri)*CH,CW,CH); r.setScissor(ci*CW,(names.length-1-ri)*CH,CW,CH);
    r.render(sc,cam);
  }
}
window.__done=errs;
</script>""" % json.dumps(CLIPS)
open(os.path.join(work, "index.html"), "w").write(html)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Q, directory=work))
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"])
    pg = b.new_page(viewport={"width": 1500, "height": 300 * len(CLIPS)})
    pg.on("console", lambda m: print("[browser]", m.type, m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: print("[pageerror]", e))
    pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/index.html")
    pg.wait_for_function("() => window.__done !== undefined", timeout=90000)
    print("errors:", pg.evaluate("window.__done"))
    pg.locator("canvas").screenshot(path=out)
    b.close()
shutil.rmtree(work, ignore_errors=True)
print("wrote", out)
