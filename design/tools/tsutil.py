import re, datetime as dt
_rx = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?$')
def ts(s):
    m = _rx.match(s)
    if not m: raise ValueError(s)
    base, frac, tz = m.groups()
    frac = (frac or '0')[:6].ljust(6, '0')
    tz = '+00:00' if (tz is None or tz == 'Z') else tz
    return dt.datetime.fromisoformat(f"{base}.{frac}{tz}").timestamp()
def hm(t): return dt.datetime.utcfromtimestamp(t).strftime('%H:%M:%S')
