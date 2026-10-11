"""Regenerate the review captures for the Slipstream redesign prototypes.

Screens, filmstrips and short videos of TV mode over time, plus desktop and phone screens.
Requires: python -m pip install playwright pillow && python -m playwright install chromium
Usage:    python design/tools/capture.py [--out design/_review/captures] [--only tv,web,phone,video,strips]

Captures are written under design/_review/ (git-ignored): they show data from your recordings.
"""
import argparse
import pathlib
import shutil
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PROTO = HERE.parent / 'prototypes'
BASE = PROTO.as_uri() + '/'

RACE, QUALI, PRAC = 'hungaroring-2026-race', 'kl-2026-qualifying', 'kl-2026-practice-2'

# name, page, query, wait ms (wall clock before the shot)[, (w, h)][, js run before the shot]
TV_SHOTS = [
    ('tv-race-start', 'tv.html', f's={RACE}&clean=1&t=-25&speed=5', 6500),
    ('tv-race-pit-cycle', 'tv.html', f's={RACE}&clean=1&t=1101&speed=10', 4500),
    ('tv-race-lead-change', 'tv.html', f's={RACE}&clean=1&t=3893&speed=2', 3600),
    ('tv-race-battle', 'tv.html', f's={RACE}&clean=1&t=3912&speed=2&module=battle', 1500),
    ('tv-race-vsc', 'tv.html', f's={RACE}&clean=1&t=4772&speed=2', 3400),
    ('tv-race-stopped', 'tv.html', f's={RACE}&clean=1&t=4824&speed=2', 4000),
    ('tv-race-result', 'tv.html', f's={RACE}&clean=1&t=6100&play=0', 1500),
    ('tv-race-result-pinned-midrace', 'tv.html', f's={RACE}&clean=1&t=2400&play=0&module=result', 1500),
    ('tv-race-timing-view', 'tv.html', f's={RACE}&clean=1&t=2400&play=0&module=timing', 1500),
    ('tv-race-toolbar-live-delay', 'tv.html', f's={RACE}&clean=1&t=2400&live=1&delay=30&bar=1&sync=1', 2500),
    ('tv-race-toolbar-replay-sync', 'tv.html', f's={RACE}&clean=1&t=2400&play=0&bar=1&sync=1', 2000),
    ('tv-race-pit-board', 'tv.html', f's={RACE}&clean=1&t=1240&speed=2&module=pits', 1500),
    ('tv-race-track-line', 'tv.html', f's={RACE}&clean=1&t=1500&speed=5&map=line&module=track', 2000),
    ('tv-race-no-positions', 'tv.html', f's={RACE}&clean=1&t=1500&speed=5&map=none&module=track', 2000),
    ('tv-race-following-no-positions', 'tv.html', f's={RACE}&clean=1&t=2400&play=0&map=none&module=driver&follow=1', 1500),
    ('tv-race-1366x768', 'tv.html', f's={RACE}&clean=1&t=2400&play=0', 1500, (1366, 768)),
    ('tv-race-16x10', 'tv.html', f's={RACE}&clean=1&t=2400&play=0', 1500, (1920, 1200)),
    ('tv-phone-sized-window', 'tv.html', f's={RACE}&clean=1&t=2400&play=0', 1200, (390, 844)),
    ('tv-quali-drop-zone', 'tv.html', f's={QUALI}&clean=1&t=1336&speed=2', 4500),
    ('tv-quali-q1-out', 'tv.html', f's={QUALI}&clean=1&t=146&speed=2', 5500),
    ('tv-quali-pole', 'tv.html', f's={QUALI}&clean=1&t=2612&speed=2', 5200),
    ('tv-quali-timing-view', 'tv.html', f's={QUALI}&clean=1&t=1336&play=0&module=timing', 1500),
    ('tv-practice-spread', 'tv.html', f's={PRAC}&clean=1&speed=10', 2500),
    ('tv-practice-timing-view', 'tv.html', f's={PRAC}&clean=1&play=0&module=timing', 1500),
    ('tv-race-reduced-motion', 'tv.html', f's={RACE}&clean=1&t=4774&speed=2&reduced=1', 3500),
]
WEB_SHOTS = [
    ('web-race-session-1440', 'web.html', f's={RACE}&t=2400&play=0', 1800),
    ('web-race-session-1440-100pct', 'web.html', f's={RACE}&t=2400&play=0&density=1', 1800),
    ('web-race-timing-1280', 'web.html', f's={RACE}&t=2400&play=0&tower=timing', 1800, (1280, 800)),
    ('web-race-timing-1024', 'web.html', f's={RACE}&t=2400&play=0&tower=timing', 1800, (1024, 768)),
    ('web-race-strategy-tower', 'web.html', f's={RACE}&t=2400&play=0&tower=strategy', 1800),
    ('web-race-map-preset', 'web.html', f's={RACE}&t=2400&play=0&layout=map', 1800),
    ('web-race-driver', 'web.html', f's={RACE}&t=2400&play=0&view=driver&driver=1', 1800),
    ('web-race-battle-pinned-nonadjacent', 'web.html', f's={RACE}&t=2400&play=0&view=battle&battle=pinned&pair=81,3', 1800),
    ('web-race-strategy', 'web.html', f's={RACE}&t=2400&play=0&view=strategy', 1800),
    ('web-race-live-delay', 'web.html', f's={RACE}&t=2400&live=1&delay=30', 2500),
    ('web-race-opening', 'web.html', f's={RACE}&t=2400&opening=1', 900),
    ('web-quali', 'web.html', f's={QUALI}&t=1330&play=0', 1800),
    ('web-practice', 'web.html', f's={PRAC}&play=0', 1800),
]
PHONE_SHOTS = [
    ('ph-race-timing', 'phone.html', f's={RACE}&t=1101&play=0&follow=44', 1500),
    ('ph-race-driver-focus', 'phone.html', f's={RACE}&t=2400&play=0&focus=1&follow=1', 1500),
    ('ph-race-compare', 'phone.html', f's={RACE}&t=2400&play=0&compare=81,3', 1500),
    ('ph-race-track', 'phone.html', f's={RACE}&t=2400&play=0&tab=track&follow=44', 1500),
    ('ph-race-strategy', 'phone.html', f's={RACE}&t=2400&play=0&tab=strategy', 1500),
    ('ph-race-activity-inspect', 'phone.html', f's={RACE}&t=3930&play=0&tab=activity', 1500, None, 'document.querySelector("#feed .fd-item").click()'),
    ('ph-race-race-control', 'phone.html', f's={RACE}&t=3930&play=0&tab=activity&act=rc', 1500),
    ('ph-race-playback-sheet', 'phone.html', f's={RACE}&t=2400&play=0&sheet=playback', 1500),
    ('ph-race-live-delay-sheet', 'phone.html', f's={RACE}&t=2400&live=1&delay=30&sheet=delay', 1800),
    ('ph-race-vsc-banner', 'phone.html', f's={RACE}&t=4770&speed=2', 5200),
    ('ph-race-320', 'phone.html', f's={RACE}&t=1101&play=0', 1500, (320, 640)),
    ('ph-race-landscape', 'phone.html', f's={RACE}&t=2400&play=0', 1500, (844, 390)),
    ('ph-quali-timing', 'phone.html', f's={QUALI}&t=1336&play=0', 1500),
    ('ph-quali-cut-line', 'phone.html', f's={QUALI}&t=1336&play=0&tab=session', 1500),
    ('ph-practice-timing', 'phone.html', f's={PRAC}&play=0', 1500),
]
# name, query, seconds of video, optional JS to run after load
VIDEOS = [
    ('tv-race-start', f's={RACE}&clean=1&t=-25&speed=5', 16, None),
    ('tv-pit-cycle', f's={RACE}&clean=1&t=1101&speed=10', 16, None),
    ('tv-lead-change', f's={RACE}&clean=1&t=3880&speed=2', 22, None),
    ('tv-vsc-and-stop', f's={RACE}&clean=1&t=4766&speed=3', 26, None),
    ('tv-chequered-flag', f's={RACE}&clean=1&t=5960&speed=3', 24, None),
    ('tv-quali-after-the-flag', f's={QUALI}&clean=1&t=1262&speed=3', 34, None),
    ('tv-live-feed-drop', f's={RACE}&clean=1&live=1&t=2400', 18, '() => setTimeout(() => __tv.player.simulateStale(7), 2500)'),
    ('tv-reduced-motion', f's={RACE}&clean=1&t=4766&speed=3&reduced=1', 14, None),
]
STRIPS = [
    ('strip-race-start', f's={RACE}&clean=1&t=-25&speed=5', 3000, 6, 1100),
    ('strip-pit-cycle', f's={RACE}&clean=1&t=1101&speed=10', 2000, 6, 1300),
    ('strip-vsc', f's={RACE}&clean=1&t=4772&speed=2', 2000, 6, 380),
    ('strip-quali-flag', f's={QUALI}&clean=1&t=1290&speed=3', 1500, 6, 2500),
]


def shoot(p, out, shots, size, dpr=1):
    b = p.chromium.launch()
    for shot in shots:
        name, page, q, wait = shot[:4]
        sz = shot[4] if len(shot) > 4 and shot[4] else size
        js = shot[5] if len(shot) > 5 else None
        ctx = b.new_context(viewport={'width': sz[0], 'height': sz[1]}, device_scale_factor=dpr)
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + page + '?' + q)
        pg.wait_for_timeout(wait)
        if js:
            pg.evaluate(js)
            pg.wait_for_timeout(500)
        pg.screenshot(path=str(out / f'{name}.png'))
        ctx.close()
        print('shot', name, ('ERRORS ' + '; '.join(errs)) if errs else '')
    b.close()


def strips(p, out):
    from PIL import Image
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1920, 'height': 1080})
    for name, q, wait, n, every in STRIPS:
        pg = ctx.new_page()
        pg.goto(BASE + 'tv.html?' + q)
        pg.wait_for_timeout(wait)
        frames = []
        for i in range(n):
            f = out / f'_{name}_{i}.png'
            pg.screenshot(path=str(f))
            frames.append(f)
            pg.wait_for_timeout(every)
        pg.close()
        ims = [Image.open(f).convert('RGB') for f in frames]
        w, h = ims[0].size
        sw, sh = w // 3, h // 3
        sheet = Image.new('RGB', (sw * 3 + 12, sh * 2 + 6), (30, 30, 30))
        for i, im in enumerate(ims):
            sheet.paste(im.resize((sw, sh), Image.LANCZOS), ((i % 3) * (sw + 6), (i // 3) * (sh + 6)))
        sheet.save(out / f'{name}.png')
        for f in frames:
            f.unlink()
        print('strip', name)
    b.close()


def videos(p, out):
    tmp = out / '_video_tmp'
    tmp.mkdir(exist_ok=True)
    for name, q, secs, js in VIDEOS:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1920, 'height': 1080}, record_video_dir=str(tmp), record_video_size={'width': 1920, 'height': 1080})
        pg = ctx.new_page()
        pg.goto(BASE + 'tv.html?' + q)
        if js:
            pg.wait_for_timeout(400)
            pg.evaluate(js)
        pg.wait_for_timeout(secs * 1000)
        v = pg.video
        ctx.close()
        src = pathlib.Path(v.path())
        shutil.move(str(src), str(out / f'{name}.webm'))
        b.close()
        print('video', name)
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(HERE.parent / '_review' / 'captures'))
    ap.add_argument('--only', default='tv,web,phone,strips,video')
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(','))
    with sync_playwright() as p:
        if 'tv' in only: shoot(p, out, TV_SHOTS, (1920, 1080))
        if 'web' in only: shoot(p, out, WEB_SHOTS, (1440, 900))
        if 'phone' in only: shoot(p, out, PHONE_SHOTS, (390, 844), dpr=2)
        if 'strips' in only: strips(p, out)
        if 'video' in only: videos(p, out)


if __name__ == '__main__':
    sys.exit(main())
