# Slipstream session redesign — design workspace

An evolutionary redesign of the session experience for **TV, desktop and phone**. It keeps the approved language (Saira + JetBrains Mono and the existing palette) and adds the Slipstream mark. It runs on real recordings, and nothing in it is committed to git.

**Start here:** open `design/index.html` in Chrome or Edge. It links every prototype, scenario and document.

## Contents

| Path | What |
|---|---|
| `index.html` | Review hub: links, decisions and scenarios |
| `prototypes/web.html` | Desktop: session page (tower + analysis presets), Driver, Battle and Strategy pages |
| `prototypes/phone.html` | Phone: session-aware tabs, Driver Focus, Compare, sheets, landscape |
| `prototypes/tv.html` | TV: tower + feature stage, toolbar, sync/delay, TIMING view |
| `prototypes/states.html` | Library and downloads, opening, live lifecycle, live vs replay, missing data, results, settings, errors, brand |
| `prototypes/shared/` | Components: rail, tower, track, story, modules, analysis, player, contract, brand |
| `prototypes/data/` | Generated from your recordings by `tools/extract_recordings.py`. Git-ignored. |
| `handoff/review-response.md` | Every review finding with its status |
| `handoff/implementation-notes.md` | Spec for the React build: server semantics, viewer model, story contract, motion, postures, acceptance |
| `handoff/astra-wp1-logic.md` | The logic package given to Astra |
| `REVIEW-BRIEF.md` | Brief for reviewers (first round) |
| `_review/` | Reviews, evidence and captures. Git-ignored: captures show recording data. |
| `tools/capture.py` | Regenerates screenshots, strips and videos into `_review/captures` |

## Useful URL parameters

| Parameter | Effect |
|---|---|
| `s` | Session: `hungaroring-2026-race`, `kl-2026-qualifying` or `kl-2026-practice-2` |
| `t` | Start time in seconds |
| `speed` | Replay speed |
| `play=0` | Start paused |
| `live=1` | Simulated live from the recording |
| `delay=30` | Live delay in seconds |
| `opening=1` | Show the opening animation |
| `reduced=1` | Reduced motion |
| `density=0.75`, `0.8`, `0.9`, `1` | Desktop display size |
| `layout=brief`, `map`, `story` | Desktop analysis preset |
| `tower=timing`, `strategy` | Desktop tower view |
| `view=driver&driver=1`, `view=battle`, `view=strategy` | Desktop page |
| `tab=track` and similar, `focus=1`, `compare=81,3`, `sheet=playback`, `sheet=delay` | Phone |
| `module=timing`, `module=result`, `bar=1`, `sync=1`, `text=1.12`, `clean=1` | TV |
| `map=line`, `map=none` | Capability fallbacks |

## Regenerating

- **Data**, on the machine that has the recordings:

  ```
  python design/tools/extract_recordings.py
  ```

- **Captures** (needs Playwright and Pillow):

  ```
  python design/tools/capture.py [--only tv,web,phone,video,strips]
  ```

Never commit recordings, generated data or captures (see AGENTS.md).
