const WEATHER_MAPS_URL = 'https://api.rainviewer.com/public/weather-maps.json';
const CACHE_TTL_MS = 2 * 60 * 1000;

let cachedFrame = null;
let cacheTime = 0;

async function getLatestFrame() {
  const now = Date.now();
  if (cachedFrame && now - cacheTime < CACHE_TTL_MS) return cachedFrame;

  const res = await fetch(WEATHER_MAPS_URL, {
    headers: { 'User-Agent': 'mr-radar/0.1 (+https://github.com/user/mr-radar)' },
  });
  if (!res.ok) throw new Error(`RainViewer API ${res.status}`);
  const data = await res.json();

  const past = data.radar?.past;
  if (!past?.length) throw new Error('No past radar frames in RainViewer response');

  const latest = past[past.length - 1];
  cachedFrame = { host: data.host, path: latest.path, timestamp: latest.time };
  cacheTime = now;
  return cachedFrame;
}

// Universal Blue color scheme (2), smooth=1, snow=1
function radarTileUrl(host, path, z, x, y) {
  return `${host}${path}/256/${z}/${x}/${y}/2/1_1.png`;
}

module.exports = { getLatestFrame, radarTileUrl };
