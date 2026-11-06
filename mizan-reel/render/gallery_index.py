"""Regenerate the reel gallery index (out/gallery.json + poster thumbs).

Scans out/*.mp4 so every new render shows up next to the others in the gallery.
Optional sidecar per reel: out/<name>.json with title/subtitle/duration/vo.
"""
import json
import os
import subprocess

import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "out")
FF = imageio_ffmpeg.get_ffmpeg_exe()


def probe(path):
    err = subprocess.run([FF, "-i", path], capture_output=True, text=True).stderr
    w = h = 0
    fps = 0
    dur = 0.0
    for line in err.splitlines():
        if "Video:" in line and "1080x1920" in line or ("Video:" in line and "x" in line):
            import re
            m = re.search(r"(\d{3,4})x(\d{3,4})", line)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
            m2 = re.search(r"([\d.]+) fps", line)
            if m2:
                fps = float(m2.group(1))
        if "Duration:" in line:
            import re
            m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", line)
            if m:
                dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return w, h, fps, dur


def main():
    os.makedirs(os.path.join(OUT, "thumbs"), exist_ok=True)
    reels = []
    for name in sorted(os.listdir(OUT)):
        if not name.endswith(".mp4"):
            continue
        path = os.path.join(OUT, name)
        w, h, fps, dur = probe(path)
        stem = name[:-4]
        meta_path = os.path.join(OUT, stem + ".json")
        meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        poster = os.path.join("thumbs", stem + ".jpg")
        if not os.path.exists(os.path.join(OUT, poster)):
            subprocess.run([FF, "-y", "-ss", str(min(3.0, max(0.2, dur * 0.12))), "-i", path,
                            "-frames:v", "1", "-vf", "scale=540:-1",
                            os.path.join(OUT, poster)], capture_output=True)
        reels.append({
            "id": stem,
            "title": meta.get("title", "Mizan Tracker — Reel"),
            "subtitle": meta.get("subtitle", ""),
            "date": meta.get("date", ""),
            "duration": f"{int(dur // 60)}:{int(dur % 60):02d}",
            "ratio": "9:16" if h > w else "16:9",
            "size": f"{w}×{h}",
            "fps": fps,
            "file": name,
            "preview": meta.get("preview", ""),
            "poster": poster,
            "vo": meta.get("vo", ""),
            "notes": meta.get("notes", ""),
        })
    reels.sort(key=lambda r: r["date"] or "", reverse=True)
    json.dump({"project": "Mizan Tracker", "reels": reels},
              open(os.path.join(OUT, "gallery.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(reels)} reel(s) indexed -> out/gallery.json")


if __name__ == "__main__":
    main()
