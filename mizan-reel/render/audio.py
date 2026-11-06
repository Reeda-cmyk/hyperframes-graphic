"""Mix the Darija voice-over with a soft music bed and mux the final reel."""
import json
import os
import subprocess

import numpy as np

import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VO = os.path.join(ROOT, "assets", "vo")
OUT = os.path.join(ROOT, "out")
SR = 48000

FF = imageio_ffmpeg.get_ffmpeg_exe()


def read_wav(path):
    raw = subprocess.run([FF, "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def plan():
    trims = json.load(open(os.path.join(VO, "trim.json")))
    gap = 0.42
    t = 0.55
    plan = []
    for k in ["01_hook", "02_problem", "03_app", "04_progress", "05_minutes", "06_cta"]:
        plan.append((k, t, trims[k]))
        t += trims[k] + gap
    total = t + 1.9
    return plan, total


def music(total, sr=SR):
    """Simple warm bed: soft pad chords + a light plucked arpeggio + pulse."""
    n = int(total * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, np.float32)
    # chord progression (D minor-ish, warm): bars of 4 s
    roots = [146.83, 174.61, 130.81, 164.81]   # D3 F3 C3 E3
    rng = np.random.default_rng(3)
    bar = 4.0
    for i in range(int(np.ceil(total / bar))):
        f0 = roots[i % len(roots)]
        s = i * bar
        e = min(total, s + bar + 0.6)
        sl = slice(int(s * sr), int(e * sr))
        tt = t[sl] - s
        env = np.minimum(1, tt / 0.9) * np.exp(-tt * 0.45)
        for k, amp in [(1, 0.24), (2, 0.10), (3, 0.05), (4, 0.025)]:
            out[sl] += (amp * env * np.sin(2 * np.pi * f0 * k * tt
                                           + 0.35 * rng.standard_normal())).astype(np.float32)
    # sparkle arpeggio (bell-ish) every 0.5 s
    for i in range(int(total / 0.5)):
        s = i * 0.5
        f = roots[(i // 8) % len(roots)] * (4 if i % 4 == 0 else 6 if i % 4 == 1 else 8)
        sl = slice(int(s * sr), int(min(total, s + 1.2) * sr))
        tt = t[sl] - s
        env = np.exp(-tt * 4.2) * 0.055
        out[sl] += (env * np.sin(2 * np.pi * f * tt)).astype(np.float32)
    # soft low pulse on the beat
    for i in range(int(total / 0.75)):
        s = i * 0.75
        sl = slice(int(s * sr), int(min(total, s + 0.5) * sr))
        tt = t[sl] - s
        out[sl] += (0.10 * np.exp(-tt * 9) * np.sin(2 * np.pi * 58 * tt)).astype(np.float32)
    # gentle low-pass
    kernel = np.hanning(40)
    kernel /= kernel.sum()
    out = np.convolve(out, kernel.astype(np.float32), mode="same").astype(np.float32)
    out /= max(1e-6, np.abs(out).max())
    return out


def main():
    p, total = plan()
    n = int(total * SR)
    mix = np.zeros(n, np.float32)
    for k, start, d in p:
        wav = read_wav(os.path.join(VO, "trim", k + ".wav"))
        i0 = int(start * SR)
        mix[i0:i0 + len(wav)] += wav[:max(0, n - i0)]
    # duck the music under the voice
    bed = music(total) * 0.20
    env = np.abs(mix)
    win = int(0.25 * SR)
    k = np.ones(win, np.float32) / win
    smooth = np.convolve(env, k, mode="same")
    duck = np.clip(1.0 - smooth / (np.percentile(smooth, 96) + 1e-6), 0.35, 1.0)
    duck = np.convolve(duck, k, mode="same").astype(np.float32)
    out = mix + bed * duck
    out = out / max(1e-6, np.abs(out).max()) * 0.92
    # fade the very end
    fo = int(0.9 * SR)
    out[-fo:] *= np.linspace(1, 0, fo) ** 1.5
    out = (out * 32767).astype(np.int16)

    wav_path = os.path.join(OUT, "mix.wav")
    import wave
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(out.tobytes())

    final = os.path.join(OUT, "mizan-reel.mp4")
    subprocess.run([FF, "-y", "-i", os.path.join(OUT, "video_raw.mp4"), "-i", wav_path,
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21",
                    "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                    "-af", "loudnorm=I=-14:TP=-1.0:LRA=9",
                    "-movflags", "+faststart", "-shortest", final],
                   check=True)
    print("final:", final, round(total, 2), "s")


if __name__ == "__main__":
    main()
