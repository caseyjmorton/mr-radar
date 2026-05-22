const USER_AGENT = 'mr-radar/0.1 (+https://github.com/user/mr-radar)';
const OSM_TTL_MS = 24 * 60 * 60 * 1000;
const RADAR_TTL_MS = 5 * 60 * 1000;
const MAX_CACHE_ENTRIES = 300;

const cache = new Map();

async function fetchBuffer(url, ttlMs) {
  const entry = cache.get(url);
  if (entry && Date.now() - entry.time < ttlMs) return entry.data;

  const res = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
  const data = Buffer.from(await res.arrayBuffer());

  cache.set(url, { data, time: Date.now() });

  if (cache.size > MAX_CACHE_ENTRIES) {
    // Evict the oldest entry
    const oldest = [...cache.entries()].reduce((a, b) => (a[1].time < b[1].time ? a : b));
    cache.delete(oldest[0]);
  }

  return data;
}

function osmTileUrl(z, x, y) {
  return `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
}

async function fetchOsmTile(z, x, y) {
  return fetchBuffer(osmTileUrl(z, x, y), OSM_TTL_MS);
}

async function fetchRadarTile(url) {
  return fetchBuffer(url, RADAR_TTL_MS);
}

module.exports = { fetchOsmTile, fetchRadarTile };
