const USER_AGENT = 'mr-radar/0.1 (+https://github.com/user/mr-radar)';
const OSM_TTL_MS = 24 * 60 * 60 * 1000;
const RADAR_TTL_MS = 5 * 60 * 1000;
const MAX_CACHE_ENTRIES = 300;

const cache = new Map();

// Strip the CARTO key out of anything that might reach a log or an error
// response. The key travels as a query parameter, so a bare `${url}` in a
// thrown Error would otherwise publish it to the renderer's logs.
function redactUrl(url) {
  return url.replace(/([?&]key=)[^&]*/gi, '$1REDACTED');
}

async function fetchBuffer(url, ttlMs) {
  const entry = cache.get(url);
  if (entry && Date.now() - entry.time < ttlMs) return entry.data;

  const res = await fetch(url, { headers: { 'User-Agent': USER_AGENT } });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${redactUrl(url)}`);
  const data = Buffer.from(await res.arrayBuffer());

  cache.set(url, { data, time: Date.now() });

  if (cache.size > MAX_CACHE_ENTRIES) {
    // Evict the oldest entry
    const oldest = [...cache.entries()].reduce((a, b) => (a[1].time < b[1].time ? a : b));
    cache.delete(oldest[0]);
  }

  return data;
}

// ---------------------------------------------------------------------------
// Base map attribution — REQUIRED, do not drop.
//
//   Map data © OpenStreetMap contributors (Open Database License).
//   Base map tiles © CARTO (https://carto.com/), built on OpenStreetMap data.
//
// Keeping these credits visible is a condition of both licences, not a
// courtesy: CARTO grants its free basemap tier explicitly in exchange for
// them, and the ODbL requires the same for OSM data. The device renders to a
// 240x240 round display with no room for map chrome, so the credit lives in
// the project README and CLAUDE.md instead. If you fork, self-host, or swap
// providers here, carry the attribution across.
//
// Note: unkeyed CARTO requests still return HTTP 200, but the tiles come back
// stamped "API KEY REQUIRED". That watermark is an enforcement notice, not
// attribution -- it names no rights holder and disappears once a key is
// supplied, so it does not discharge the requirement above. Free keys (5M
// tiles/month, non-commercial) come from https://carto.com/basemaps/apikey
// and are passed as a `?key=` query parameter.
// ---------------------------------------------------------------------------

// CARTO subdomains for load balancing
const CARTO_SUBDOMAINS = ['a', 'b', 'c', 'd'];
let cartoSubdomainIdx = 0;

function osmTileUrl(z, x, y) {
  return `https://tile.openstreetmap.org/${z}/${x}/${y}.png`;
}

// Read the key lazily rather than capturing it at import time, so a restart
// after `fly secrets set CARTO_API_KEY=...` picks it up and tests can vary it.
function hasCartoKey() {
  return Boolean(process.env.CARTO_API_KEY);
}

function cartoDarkUrl(style, z, x, y) {
  const s = CARTO_SUBDOMAINS[cartoSubdomainIdx++ % CARTO_SUBDOMAINS.length];
  const key = process.env.CARTO_API_KEY;
  const auth = key ? `?key=${encodeURIComponent(key)}` : '';
  return `https://${s}.basemaps.cartocdn.com/${style}/${z}/${x}/${y}.png${auth}`;
}

async function fetchOsmTile(z, x, y) {
  return fetchBuffer(osmTileUrl(z, x, y), OSM_TTL_MS);
}

async function fetchCartoDarkTile(z, x, y) {
  return fetchBuffer(cartoDarkUrl('dark_nolabels', z, x, y), OSM_TTL_MS);
}

async function fetchCartoLabelsTile(z, x, y) {
  return fetchBuffer(cartoDarkUrl('dark_only_labels', z, x, y), OSM_TTL_MS);
}

async function fetchCartoDarkAllTile(z, x, y) {
  return fetchBuffer(cartoDarkUrl('dark_all', z, x, y), OSM_TTL_MS);
}

async function fetchRadarTile(url) {
  return fetchBuffer(url, RADAR_TTL_MS);
}

module.exports = {
  fetchOsmTile,
  fetchCartoDarkTile,
  fetchCartoLabelsTile,
  fetchCartoDarkAllTile,
  fetchRadarTile,
  // Exported for the startup warning in server.js and for unit tests.
  hasCartoKey,
  cartoDarkUrl,
  osmTileUrl,
  redactUrl,
};
