#!/usr/bin/env bash
# Trim silence + normalise the raw VO mp3s into assets/vo/trim/*.wav and write
# assets/vo/trim.json (durations used by the timeline).
set -e
cd "$(dirname "$0")/.."
FF=${FF:-ffmpeg}
mkdir -p assets/vo/trim
for k in 01_hook 02_problem 03_app 04_progress 05_minutes 06_cta; do
  "$FF" -y -i "assets/vo/$k.mp3" -af \
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,\
areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse,\
loudnorm=I=-16:TP=-1.5:LRA=7" \
    -ar 48000 -ac 1 "assets/vo/trim/$k.wav"
done
python3 - <<'PY'
import json, re, subprocess, os
ff = os.environ.get("FF", "ffmpeg")
d = {}
for k in ["01_hook","02_problem","03_app","04_progress","05_minutes","06_cta"]:
    p = f"assets/vo/trim/{k}.wav"
    e = subprocess.run([ff, "-i", p, "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", e)
    d[k] = round(int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3)), 3)
json.dump(d, open("assets/vo/trim.json", "w"), indent=1)
print(d)
PY
