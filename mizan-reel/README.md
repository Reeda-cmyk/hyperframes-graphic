# Mizan Tracker — Instagram reel (Darija VO)

A 53 s vertical (1080×1920, 30 fps) promo reel for [mizantracker.online](https://mizantracker.online),
with a 100% Moroccan-Darija voiceover.

## Deliverable
- `out/mizan-reel.mp4` — final vertical reel, VO + music bed, burned-in subtitles.

## Beats
| # | time | scene | VO |
|---|------|-------|----|
| 1 | 0:00–0:08 | Hook — man at his desk at night, phone in hand | «شحال من مرة قلتي لراسك: من غدا نبدّل؟» |
| 2 | 0:08–0:14 | Laptop scene, reference framing — the app is **inside the screen**, screenshot captions | «المشكل ماشي فالنية… المشكل فالمتابعة.» |
| 3 | 0:14–0:23 | Same laptop, screen lit + light sweep, no floating UI cards | «هاذي هي ميزان تراكر…» |
| 4 | 0:23–0:34 | Camera tour of the dashboard (ring, prayers, streak) | «كل نهار كيبين ليك فين نتا واصل…» |
| 5 | 0:34–0:44 | 5 minutes on cream editorial, then the monthly competition | «غير خمس دقايق… تربح شهر مجاني ديال ميزان برو.» |
| 6 | 0:44–0:53 | CTA — mizantracker.online + @mizan.tracker | «دخل دابا ل ميزان تراكر دوت أونلاين.» |

## How it is built
Everything is deterministic Python — no browser, no network at render time:

- `render/ui.py` — rebuilds the Mizan Tracker dashboard (as seen in the provided
  screenshot) at 2× with Pillow: layout, palette, type, prayer cards, calendar.
  The live site is not reachable from the sandbox, so the screen is a faithful
  reconstruction rather than a screenshot.
- `render/shape.py` — HarfBuzz shaping + FreeType raster fill for correct Arabic
  joins/RTL (Pillow's basic shaper does not join Cairo/Amiri glyphs).
- `render/gfx.py` — grain, vignette, scrims, star lattice, crescent mark.
- `render/video.py` — scenes, camera keyframes, perspective screen insert
  (homography), kinetic type, cut punches; pipes raw frames into FFmpeg (x264).
- `assets/broll/` — generated cinematic stills for the "real person on a PC" shots.
- `assets/ui/app_screen.png` — the reconstructed dashboard.
- `assets/vo/` — Voice-over clips (Cairo/Inter mix rendered per-line) and their
  trimmed, loudness-normalised wavs.

Rebuild:

```bash
python3 render/ui.py          # dashboard bitmap
python3 render/video.py       # frames -> out/video_raw.mp4
python3 render/audio.py       # VO + music mix -> out/mizan-reel.mp4
```

Requirements: `pillow numpy uharfbuzz freetype-py imageio-ffmpeg`.

Fonts are fetched by `render/fonts_fetch.sh` (Inter, Playfair Display, Cairo, Amiri
via `@fontsource`, converted to TTF) into `assets/fonts/`.
