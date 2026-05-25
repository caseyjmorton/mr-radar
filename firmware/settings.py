import json

_CONFIG = '/config.json'
_DEFAULTS = {
    'wifi_ssid':    '',
    'wifi_password': '',
    'station':      'KILN',
    'renderer_url': 'https://mr-radar.mortons.io',
    'theme':        'vintage',
    'poll_seconds': 60,
    'tz_offset':    0,
    'dst':          False,
}


def _load():
    try:
        with open(_CONFIG) as f:
            d = json.load(f)
        cfg = dict(_DEFAULTS)
        cfg.update(d)
        return cfg
    except Exception:
        return dict(_DEFAULTS)


_c = _load()
WIFI_SSID    = _c['wifi_ssid']
WIFI_PASSWORD = _c['wifi_password']
STATION      = _c['station']
RENDERER_URL = _c['renderer_url']
THEME        = _c['theme']
POLL_SECONDS = _c['poll_seconds']
TZ_OFFSET    = float(_c.get('tz_offset', 0))
DST          = bool(_c.get('dst', False))
