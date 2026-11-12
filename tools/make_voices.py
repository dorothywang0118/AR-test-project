#!/usr/bin/env python3
"""Pre-record every character line with a free offline neural TTS (Kokoro v1.1-zh via sherpa-onnx).
Usage: python3 tools/make_voices.py <kokoro-multi-lang-v1_1 dir>
Writes frontend/customer/public/campaign/voice/<x>/<n>.mp3 + voice/manifest.json ({characterId: {line: url}})."""
import json, os, re, subprocess, sys, tempfile
import sherpa_onnx, soundfile as sf

M = sys.argv[1].rstrip("/") + "/"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "customer", "public", "campaign")
# speaker id (3-57 female, 58-102 male) and speed per character
# 店長: 40s woman, medium pace / 羽辰: 25 man, mid pitch, fast / 峻亘: 27 man, low and slow /
# 小逸文: 30 woman, lower pitch, fast and decisive / 佳韻: 28 woman, gentle "big sister", medium pace
VOICES = {"CHAR-CHIBI-A": (13, 1.0), "CHAR-CHIBI-B": (92, 1.15), "CHAR-CHIBI-C": (68, 0.85),
          "CHAR-CHIBI-D": (57, 1.15), "CHAR-CHIBI-E": (25, 1.0)}


def speakable(t):
    t = re.sub(r"(\d+)\s*%", r"百分之\1", t)
    t = re.sub(r"（[^）]*）", "", t).replace("～", "").replace("…", "，").replace("QQ", "")
    return t.strip("，") + "。"


cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
    model=M + "model.onnx", voices=M + "voices.bin", tokens=M + "tokens.txt", lexicon=f"{M}lexicon-us-en.txt,{M}lexicon-zh.txt",
    data_dir=M + "espeak-ng-data", dict_dir=M + "dict"), num_threads=2),
    rule_fsts=f"{M}phone-zh.fst,{M}date-zh.fst,{M}number-zh.fst")
tts = sherpa_onnx.OfflineTts(cfg)
camp = json.load(open(os.path.join(ROOT, "campaign.json")))
manifest = {}
tmp = tempfile.mkdtemp()
for ch in camp["characters"]:
    sid, speed = VOICES[ch["id"]]
    short = ch["id"][-1].lower()
    os.makedirs(os.path.join(ROOT, "voice", short), exist_ok=True)
    lines = sorted({l for v in ch["phrases"].values() for l in v})
    manifest[ch["id"]] = {}
    for i, line in enumerate(lines):
        a = tts.generate(speakable(line), sid=sid, speed=speed)
        wav = os.path.join(tmp, "x.wav")
        sf.write(wav, a.samples, a.sample_rate)
        rel = f"voice/{short}/{i:02d}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "loudnorm=I=-16:TP=-1.5", "-ar", "24000",
                        "-ac", "1", "-b:a", "48k", os.path.join(ROOT, rel)], check=True)
        manifest[ch["id"]][line] = "campaign/" + rel + "?v=" + camp["version"]
    print(ch["id"], len(lines), flush=True)
json.dump(manifest, open(os.path.join(ROOT, "voice", "manifest.json"), "w"), ensure_ascii=False)
