"""Mix the Darija voice-over with music and a full sound-FX layer.

Everything is synthesised with numpy (no external samples), then levelled:
VO -16 LUFS-ish, music ~-30 dB under it, SFX punched to taste, master -14 LUFS.
"""
import json
import os
import subprocess
import wave

import numpy as np
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VO = os.path.join(ROOT, "assets", "vo")
OUT = os.path.join(ROOT, "out")
SR = 48000
FF = imageio_ffmpeg.get_ffmpeg_exe()

VO_KEYS = ["01_hook", "02_problem", "03_app", "04_progress", "05_minutes", "06_cta"]
GAP = 0.42


# ------------------------------------------------------------------ helpers
def read_wav(path):
    raw = subprocess.run([FF, "-v", "quiet", "-i", path, "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def envelope(n, attack=0.005, decay=0.25):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return (a * np.exp(-t / max(decay, 1e-4))).astype(np.float32)


def lpf(x, cutoff_hz):
    """One-pole low-pass, cheap and smooth."""
    if cutoff_hz >= SR / 2:
        return x
    a = np.exp(-2 * np.pi * cutoff_hz / SR)
    y = np.empty_like(x)
    acc = 0.0
    # vectorised IIR via lfilter-free trick: use scipy-free loop on decimated? keep simple loop
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def noise(n, rng):
    return rng.standard_normal(n).astype(np.float32)


# ------------------------------------------------------------------ SFX
def sfx_whoosh(dur=0.55, rng=None):
    """Filtered noise sweep for cuts / camera moves."""
    rng = rng or np.random.default_rng(1)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = noise(n, rng)
    # sweep a resonant band by modulating a comb-ish filter with a sweeping delay
    out = np.zeros(n, np.float32)
    for k in range(1, 7):
        d = (0.0006 + 0.0016 * (t / dur) * k / 6)
        idx = np.clip(np.arange(n) - (d * SR).astype(int), 0, n - 1)
        out += 0.35 / k * x[idx]
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    out = out * env
    out = lpf(out, 5200)
    return out / (np.abs(out).max() + 1e-9)


def sfx_impact(dur=0.75, rng=None):
    """Low sub boom for punchlines / big cuts."""
    rng = rng or np.random.default_rng(2)
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = np.linspace(88, 38, n)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(phase) * np.exp(-t * 3.4)
    click = noise(n, rng) * np.exp(-t * 55) * 0.35
    out = (body + click).astype(np.float32)
    return out / (np.abs(out).max() + 1e-9)


def sfx_click(dur=0.09, bright=0.55, rng=None):
    """UI tap / mouse click."""
    rng = rng or np.random.default_rng(3)
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 1750 * t) * np.exp(-t * 90)
    body2 = np.sin(2 * np.pi * 900 * t) * np.exp(-t * 60) * 0.5
    nz = noise(n, rng) * np.exp(-t * 260) * bright
    out = (body + body2 + nz).astype(np.float32)
    return out / (np.abs(out).max() + 1e-9)


def sfx_keyboard(dur=1.0, rng=None, rate=9.0):
    """Soft mechanical keyboard bed."""
    rng = rng or np.random.default_rng(4)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    t = 0.0
    while t < dur:
        l = int(0.05 * SR)
        i0 = int(t * SR)
        if i0 + l >= n:
            break
        tap = sfx_click(0.05, bright=0.9, rng=rng) * rng.uniform(0.25, 0.55)
        jitter = rng.uniform(0.85, 1.15)
        out[i0:i0 + l] += (tap * jitter)[:min(l, len(tap))]
        t += (1.0 / rate) * rng.uniform(0.6, 1.5)
    out = lpf(out, 3800)
    return out / (np.abs(out).max() + 1e-9)


def sfx_riser(dur=1.4, rng=None):
    """Tension riser into the competition beat."""
    rng = rng or np.random.default_rng(5)
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = noise(n, rng)
    out = np.zeros(n, np.float32)
    for k in range(1, 5):
        d = (0.0008 * k + 0.0025 * (t / dur) ** 2 * k)
        idx = np.clip(np.arange(n) - (d * SR).astype(int), 0, n - 1)
        out += nz[idx] / k
    tone_f = np.linspace(220, 880, n)
    tone = np.sin(2 * np.pi * np.cumsum(tone_f) / SR) * 0.18
    env = (t / dur) ** 2.2
    out = (out * 0.6 + tone) * env
    out = lpf(out, 7000)
    return out / (np.abs(out).max() + 1e-9)


def sfx_chime(base=880.0, dur=1.1, notes=(1.0, 1.5, 2.0)):
    """Sparkle chime for reveals / the prize card."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    for i, m in enumerate(notes):
        off = int(i * 0.055 * SR)
        seg = out[off:]
        tt = np.arange(len(seg)) / SR
        f = base * m
        w = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * f * 2 * tt)
             + 0.15 * np.sin(2 * np.pi * f * 3.01 * tt))
        seg += (w * np.exp(-tt * 3.1)).astype(np.float32)
    return out / (np.abs(out).max() + 1e-9)


def sfx_swipe(dur=0.4, rng=None):
    """Short upward swipe for text reveals."""
    rng = rng or np.random.default_rng(6)
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = noise(n, rng) * np.sin(np.pi * (t / dur)) ** 2
    for k in range(1, 5):
        d = (0.0004 * k + 0.0012 * (t / dur) * k)
        idx = np.clip(np.arange(n) - (d * SR).astype(int), 0, n - 1)
        out += 0.3 * noise(n, rng)[idx]
    out = lpf(out, 6500)
    return out / (np.abs(out).max() + 1e-9)


# ------------------------------------------------------------------ music
def music(total, sr=SR):
    """Warm pad + plucked arp + soft pulse, with a light build in the middle."""
    n = int(total * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, np.float32)
    roots = [146.83, 174.61, 130.81, 164.81]
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
    for i in range(int(total / 0.5)):
        s = i * 0.5
        f = roots[(i // 8) % len(roots)] * (4 if i % 4 == 0 else 6 if i % 4 == 1 else 8)
        sl = slice(int(s * sr), int(min(total, s + 1.2) * sr))
        tt = t[sl] - s
        env = np.exp(-tt * 4.2) * 0.05
        out[sl] += (env * np.sin(2 * np.pi * f * tt)).astype(np.float32)
    # pulse: soft kick through the middle section, stops before the CTA
    for i in range(int(total / 0.75)):
        s = i * 0.75
        if s < 6.0 or s > total - 9.0:
            continue
        sl = slice(int(s * sr), int(min(total, s + 0.5) * sr))
        tt = t[sl] - s
        out[sl] += (0.12 * np.exp(-tt * 9) * np.sin(2 * np.pi * 58 * tt)).astype(np.float32)
    kernel = np.hanning(40)
    kernel /= kernel.sum()
    out = np.convolve(out, kernel.astype(np.float32), mode="same").astype(np.float32)
    return out / max(1e-6, np.abs(out).max())


# ------------------------------------------------------------------ plan / cues
def vo_plan():
    trims = json.load(open(os.path.join(VO, "trim.json")))
    t = 0.55
    plan = []
    for k in VO_KEYS:
        plan.append((k, t, trims[k]))
        t += trims[k] + GAP
    total = t + 1.9
    return plan, total


def cue_sheet(vo, total):
    """(time, name, gain) SFX cues wired to the picture edit."""
    cuts = [vo[i][1] - 0.30 for i in range(1, len(vo))]
    c = []
    # cut whooshes + small impacts on every scene change
    for i, t in enumerate(cuts):
        c.append((t - 0.16, "whoosh", 0.42))
        c.append((t, "impact", 0.30 if i < 3 else 0.24))
    # hook punches
    c += [(1.30, "impact", 0.55), (1.35, "swipe", 0.28),
          (3.30, "swipe", 0.2), (4.50, "impact", 0.34),
          (5.40, "chime", 0.10)]
    # problem beat: the "break" of the progress bar
    c += [(11.30, "swipe", 0.18), (12.60, "impact", 0.30)]
    # laptop screen powers on
    c += [(14.75, "click", 0.55), (14.95, "chime", 0.22), (18.4, "whoosh", 0.18)]
    # in-app tour: UI taps per beat + camera whooshes
    for tt in [23.4, 25.5, 27.9, 30.6, 32.4]:
        c.append((tt, "click", 0.32))
    for tt in [24.6, 27.0, 30.2, 33.2]:
        c.append((tt, "whoosh", 0.20))
    # 5-minutes + competition
    c += [(34.4, "chime", 0.26), (36.0, "click", 0.34), (37.2, "click", 0.30),
          (38.6, "riser", 0.34), (39.9, "impact", 0.4), (40.2, "chime", 0.30),
          (42.2, "chime", 0.22)]
    # CTA
    c += [(44.1, "whoosh", 0.32), (44.6, "chime", 0.30), (46.3, "click", 0.30),
          (48.0, "impact", 0.22)]
    return [x for x in c if 0 <= x[0] < total]


def main():
    vo, total = vo_plan()
    n = int(total * SR)
    voice = np.zeros(n, np.float32)
    for k, start, d in vo:
        wav = read_wav(os.path.join(VO, "trim", k + ".wav"))
        i0 = int(start * SR)
        voice[i0:i0 + len(wav)] += wav[:max(0, n - i0)]

    # keyboard bed under the two laptop scenes
    rng = np.random.default_rng(21)
    typing = np.zeros(n, np.float32)
    for t0, dur in [(8.3, 5.0), (14.1, 8.6), (23.6, 9.6)]:
        kb = sfx_keyboard(dur, rng=rng, rate=7.5) * 0.045
        i0 = int(t0 * SR)
        typing[i0:i0 + len(kb)] += kb[:max(0, n - i0)]

    sfx = np.zeros(n, np.float32)
    makers = {"whoosh": sfx_whoosh, "impact": sfx_impact, "click": sfx_click,
              "riser": sfx_riser, "chime": sfx_chime, "swipe": sfx_swipe}
    for t0, name, gain in cue_sheet(vo, total):
        snd = makers[name]()
        i0 = max(0, int(t0 * SR))
        seg = snd[:max(0, n - i0)]
        sfx[i0:i0 + len(seg)] += seg * gain

    bed = music(total) * 0.20

    # side-chain: duck music + typing + sfx a touch under the voice
    win = int(0.25 * SR)
    k = np.ones(win, np.float32) / win
    smooth = np.convolve(np.abs(voice), k, mode="same")
    duck = np.clip(1.0 - smooth / (np.percentile(smooth, 96) + 1e-6), 0.40, 1.0)
    duck = np.convolve(duck, k, mode="same").astype(np.float32)

    out = voice + bed * duck + (typing * 0.9 + sfx * 0.85) * (0.55 + 0.45 * duck)
    out = out / max(1e-6, np.abs(out).max()) * 0.92
    fo = int(0.9 * SR)
    out[-fo:] *= np.linspace(1, 0, fo) ** 1.5

    wav_path = os.path.join(OUT, "mix.wav")
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((out * 32767).clip(-32768, 32767).astype(np.int16).tobytes())

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
