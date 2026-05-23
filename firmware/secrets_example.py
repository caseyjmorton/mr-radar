# Copy this file to secrets.py and fill in your values.
# secrets.py is gitignored - never commit real credentials.

WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

# Nearest NEXRAD station ID (see the renderer's /stations or weather.gov/ridge).
STATION = "KILN"

# Renderer base URL. For local bring-up, use your computer's LAN IP and the
# renderer port (default 3000) - it must be reachable from the device's WiFi.
# HTTPS is not supported by this loop yet; use http:// for now.
RENDERER_URL = "http://192.168.1.50:3000"

THEME = "modern"      # "modern" | "vintage"
POLL_SECONDS = 60     # how often to fetch a new frame
