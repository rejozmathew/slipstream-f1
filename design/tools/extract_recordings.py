"""Derive compact prototype timelines from Slipstream normalized recordings (read-only inputs)."""
import json, sys, re, math, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from tsutil import ts

FIELDS = {  # payload key -> short key
 'position':'p','gap_to_leader':'g','interval_to_ahead':'i','last_lap':'l','best_lap':'b','compound':'c','tyre_age':'a',
 'stint_laps':'st','tyre_usage':'u','pit_count':'pc','activity':'ac','source_condition':'sc','lap':'lp','track_position':'tp',
 'sector_1':'s1','sector_2':'s2','sector_3':'s3','classification':'cl','qualifying_results':'qr','qualifying_eliminated':'qe',
 'qualifying_phase_reached':'qp'}
SESSION_KEYS = ['status','control_status','marshal_status','lap','total_laps','qualifying_phase','session_clock','session_clock_running']

def lap_secs(s):
    if not s or not isinstance(s,str): return None
    m = re.match(r'^(?:(\d+):)?(\d+(?:\.\d+)?)$', s.strip())
    if not m: return None
    return (int(m.group(1)) if m.group(1) else 0)*60 + float(m.group(2))

def build(src, kind, out, label, circuit=None, start_hint=None, end_pad=150):
    ev = json.load(open(src))
    ev.sort(key=lambda e: ts(e['occurred_at']))
    ident = {}; meta = {}
    for e in ev:
        if e['kind']=='driver':
            p=e['payload']; ident[p['number']] = [p.get('code'), p.get('name'), p.get('team'), p.get('team_colour')]
        if e['kind']=='session':
            for k in ('key','name','meeting_name','session_kind','circuit','location','started_at','ended_at','gmt_offset','eligible_field_size'):
                if k in e['payload'] and e['payload'][k] is not None: meta[k]=e['payload'][k]
    # reference time t0: first RUNNING (race: actual start)
    t_run = None
    for e in ev:
        if e['kind']=='session' and e['payload'].get('status')=='RUNNING':
            t = ts(e['occurred_at'])
            if start_hint and t < ts(start_hint): continue
            t_run = t; break
    first_t = ts(ev[0]['occurred_at'])
    t0 = t_run if t_run else first_t
    # begin a little before start
    begin = max(first_t, t0 - (90 if kind=='race' else 0))
    state = {}; sess = {}; frames = collections.OrderedDict(); sframes = collections.OrderedDict()
    rc = []; weather = []; pits = []; laps = []
    last_emit = {}  # num -> {short: value}
    lastw = None
    def q(t): return int(math.floor(t - t0))
    for e in ev:
        t = ts(e['occurred_at']); k = e['kind']; p = e.get('payload') or {}
        if k=='timing':
            n = p['number']; st = state.setdefault(n, {})
            for key, short in FIELDS.items():
                if key in p:
                    v = p[key]
                    if key=='track_position' and v is not None: v = round(v, 3)
                    st[short] = v
            if 'pit_observation' in p:
                po = p['pit_observation']
                pits.append([round(t-t0,1), n, po.get('lap'), po.get('previous_compound'), po.get('new_compound'), po.get('pit_lane_duration'), po.get('ordinal')])
            if t < begin: continue
            sec = q(t)
            fr = frames.setdefault(sec, {})
            prev = last_emit.setdefault(n, {})
            ch = {kk: vv for kk, vv in st.items() if prev.get(kk, '__none__') != vv}
            if ch:
                fr.setdefault(n, {}).update(ch); prev.update(ch)
        elif k=='session':
            ch = {kk: p[kk] for kk in SESSION_KEYS if kk in p and sess.get(kk, '__none__') != p[kk]}
            sess.update({kk: p[kk] for kk in SESSION_KEYS if kk in p})
            if ch and t >= begin:
                sframes.setdefault(q(t), {}).update(ch)
                if 'lap' in ch: laps.append([round(t-t0,1), ch['lap']])
        elif k=='race_control':
            rc.append([round(t-t0,1), p.get('category'), p.get('flag'), p.get('scope'), p.get('sector'), p.get('lap'), p.get('driver_number'), p.get('message')])
        elif k=='weather':
            w = [p.get('air_temperature'), p.get('track_temperature'), p.get('humidity'), p.get('rainfall'), p.get('wind_speed'), p.get('wind_direction'), p.get('pressure')]
            if w != lastw:
                weather.append([round(t-t0,1)] + w); lastw = w
    # initial snapshot at begin: emit full state of everyone at first frame
    init_state = {}
    # Recompute: reconstruct state at 'begin' for initial snapshot
    st2 = {}; sess2 = {}
    for e in ev:
        t = ts(e['occurred_at'])
        if t >= begin: break
        if e['kind']=='timing':
            n=e['payload']['number']; d=st2.setdefault(n,{})
            for key, short in FIELDS.items():
                if key in e['payload']:
                    v=e['payload'][key]
                    if key=='track_position' and v is not None: v=round(v,3)
                    d[short]=v
        if e['kind']=='session':
            sess2.update({kk: e['payload'][kk] for kk in SESSION_KEYS if kk in e['payload']})
    tEnd = max(frames.keys()) if frames else 0
    data = {
        'label': label, 'kind': kind, 'source': ev[0].get('source'),
        'meta': meta, 'drivers': ident, 't0': t0, 'begin': round(begin-t0), 'end': tEnd,
        'init': st2, 'initSession': sess2,
        'frames': [[sec, fr] for sec, fr in frames.items()],
        'session': [[sec, ch] for sec, ch in sframes.items()],
        'rc': rc, 'weather': weather, 'pits': pits, 'laps': laps,
    }
    if circuit: data['circuit'] = circuit
    js = 'window.SLIPSTREAM_DATA = window.SLIPSTREAM_DATA || {};\nwindow.SLIPSTREAM_DATA[%s] = %s;\n' % (json.dumps(label), json.dumps(data, separators=(',',':')))
    open(out,'w').write(js)
    print(out, 'frames', len(frames), 'bytes', len(js), 'begin', data['begin'], 'end', tEnd)

if __name__ == '__main__':
    import os
    G = os.environ.get('SLIPSTREAM_GITCLONE', os.path.expanduser('~/mnt/GitClone'))  # e.g. C:/GitClone
    OUT = G + '/slipstream-f1-redesign/design/prototypes/data'
    os.makedirs(OUT, exist_ok=True)
    cat = json.load(open(G+'/slipstream-f1-session-design-baselines/output/recordings/catalog.json'))
    hun = cat['meetings']['1291']['circuit']
    build(G+'/slipstream-f1-session-design-baselines/output/recordings/f1-static-11342.json', 'race', OUT+'/hungaroring-2026-race.js', 'hungaroring-2026-race',
          circuit={'name': hun['name'], 'rotation': hun['rotation'], 'path': hun['path']}, start_hint='2026-07-26T13:00:00Z')
    build(G+'/slipstream-f1-session-design-baselines/output/recordings/live-11730.json', 'qualifying', OUT+'/kl-2026-qualifying.js', 'kl-2026-qualifying', start_hint='2026-10-03T08:18:40Z')
    build(G+'/slipstream-f1/recordings/live-11728.json', 'practice', OUT+'/kl-2026-practice-2.js', 'kl-2026-practice-2', start_hint='2026-10-02T08:35:00Z')
