const { renderFrame, DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, DEFAULT_OPACITY } = require('./composite');
const { resolveStation, listStations } = require('./stations');
const { version } = require('../package.json');

async function frameHandler(req, res) {
  const q = req.query;

  let lat, lon;

  if (q.station) {
    const station = resolveStation(q.station);
    if (!station) {
      return res.status(404).json({ error: `Unknown station: ${q.station}` });
    }
    ({ lat, lon } = station);
  } else {
    lat = parseFloat(q.lat);
    lon = parseFloat(q.lon);
    if (!isFinite(lat) || !isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return res.status(400).json({ error: 'Provide station=<nexrad-station-id> or valid lat/lon coordinates' });
    }
  }

  const fmt = q.fmt || 'jpeg';
  if (fmt !== 'rgb565' && fmt !== 'jpeg') {
    return res.status(400).json({ error: 'fmt must be rgb565 or jpeg' });
  }

  const theme = q.theme || 'vintage';
  if (theme !== 'modern' && theme !== 'vintage') {
    return res.status(400).json({ error: 'theme must be modern or vintage' });
  }

  const zoom = q.zoom !== undefined ? parseInt(q.zoom, 10) : DEFAULT_ZOOM;
  if (!Number.isInteger(zoom) || zoom < MIN_ZOOM || zoom > MAX_ZOOM) {
    return res.status(400).json({ error: `zoom must be an integer between ${MIN_ZOOM} and ${MAX_ZOOM}` });
  }

  const opacity = q.opacity !== undefined ? parseInt(q.opacity, 10) : DEFAULT_OPACITY;
  if (!Number.isInteger(opacity) || opacity < 0 || opacity > 100) {
    return res.status(400).json({ error: 'opacity must be an integer between 0 and 100' });
  }

  try {
    const result = await renderFrame(lat, lon, fmt, theme, zoom, opacity);
    res
      .status(200)
      .set({
        'Content-Type': fmt === 'rgb565' ? 'application/octet-stream' : 'image/jpeg',
        'Content-Length': result.buffer.length,
        'X-Radar-Timestamp': String(result.timestamp),
        'X-Partial-Data': result.partial ? '1' : '0',
        'X-Renderer-Version': version,
        'Cache-Control': 'no-store',
      })
      .end(result.buffer);
  } catch (err) {
    console.error('[frameHandler] renderFrame failed:', err.message);
    res.status(502).json({ error: 'render failed', detail: err.message });
  }
}

function stationsHandler(req, res) {
  res.json(listStations());
}

module.exports = { frameHandler, stationsHandler };
