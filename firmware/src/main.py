import json


def _need_setup():
    try:
        with open('/config.json') as f:
            return not json.load(f).get('wifi_ssid')
    except Exception:
        return True


if _need_setup():
    import portal
    portal.run()
else:
    import radar
    radar.main()
