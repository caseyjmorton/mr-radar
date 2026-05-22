const { renderFrame } = require('./composite');
const { resolveStation, listStations } = require('./stations');

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
      return res.status(400).json({ error: 'Provide station=KILN or valid lat/lon coordinates' });
    }
  }

  const fmt = q.fmt || 'jpeg';
  if (fmt !== 'rgb565' && fmt !== 'jpeg') {
    return res.status(400).json({ error: 'fmt must be rgb565 or jpeg' });
  }

  const theme = q.theme || 'modern';
  if (theme !== 'modern' && theme !== 'vintage') {
    return res.status(400).json({ error: 'theme must be modern or vintage' });
  }

  try {
    const result = await renderFrame(lat, lon, fmt, theme);
    res
      .status(200)
      .set({
        'Content-Type': fmt === 'rgb565' ? 'application/octet-stream' : 'image/jpeg',
        'Content-Length': result.buffer.length,
        'X-Radar-Timestamp': String(result.timestamp),
        'X-Partial-Data': result.partial ? '1' : '0',
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
