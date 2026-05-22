const sharp = require('sharp');
const { getTileBlock, TILE_SIZE } = require('./tileMath');
const { fetchOsmTile, fetchRadarTile } = require('./tiles');
const { getLatestFrame, radarTileUrl } = require('./rainviewer');

const OUTPUT_SIZE = 240;
const ZOOM = 7;
const CANVAS_SIZE = TILE_SIZE * 2; // 512x512 stitched canvas

const frameCache = new Map();
const FRAME_CACHE_TTL_MS = 5 * 60 * 1000;

// Dark navy base map for vintage theme: grayscale + darken + semi-transparent navy overlay.
async function vintageBaseMap(buf) {
  const dark = await sharp(buf).grayscale().modulate({ brightness: 0.35 }).png().toBuffer();
  const overlay = await sharp({
    create: { width: TILE_SIZE, height: TILE_SIZE, channels: 4, background: { r: 10, g: 20, b: 80, alpha: 0.45 } },
  }).png().toBuffer();
  return sharp(dark).composite([{ input: overlay, blend: 'over' }]).png().toBuffer();
}

async function renderFrame(lat, lon, fmt, theme = 'modern') {
  const frame = await getLatestFrame();

  // Round coords to ~11m precision so nearby devices share cache entries.
  const key = `${lat.toFixed(4)},${lon.toFixed(4)},${fmt},${theme},${frame.path}`;
  const cached = frameCache.get(key);
  if (cached && Date.now() - cached.time < FRAME_CACHE_TTL_MS) {
    return cached.payload;
  }

  const { tiles, stitchedX, stitchedY } = getTileBlock(lat, lon, ZOOM);

  // Fetch all tiles in parallel; failures return null so we degrade gracefully.
  const [osmBuffers, radarBuffers] = await Promise.all([
    Promise.all(tiles.map(t => fetchOsmTile(t.z, t.x, t.y).catch(() => null))),
    Promise.all(
      tiles.map(t =>
        fetchRadarTile(radarTileUrl(frame.host, frame.path, t.z, t.x, t.y)).catch(() => null)
      )
    ),
  ]);

  const baseBuffers = theme === 'vintage'
    ? await Promise.all(osmBuffers.map(b => b ? vintageBaseMap(b) : null))
    : osmBuffers;

  // Build composite inputs for sharp: base map tiles first, radar tiles on top.
  const inputs = [];
  for (let i = 0; i < 4; i++) {
    if (!baseBuffers[i]) continue;
    inputs.push({ input: baseBuffers[i], top: Math.floor(i / 2) * TILE_SIZE, left: (i % 2) * TILE_SIZE });
  }
  for (let i = 0; i < 4; i++) {
    if (!radarBuffers[i]) continue;
    inputs.push({
      input: radarBuffers[i],
      top: Math.floor(i / 2) * TILE_SIZE,
      left: (i % 2) * TILE_SIZE,
      blend: 'over',
    });
  }

  // Canvas fill color: neutral gray for modern, deep navy for vintage (shows at tile edges/gaps).
  const canvasBg = theme === 'vintage'
    ? { r: 5, g: 10, b: 40, alpha: 1 }
    : { r: 180, g: 180, b: 180, alpha: 1 };

  // Stitch into a 512x512 canvas.
  const stitchedPng = await sharp({
    create: { width: CANVAS_SIZE, height: CANVAS_SIZE, channels: 4, background: canvasBg },
  })
    .composite(inputs)
    .png()
    .toBuffer();

  // Crop 240x240 centered on the lat/lon pixel position.
  const cropLeft = Math.max(0, Math.min(stitchedX - OUTPUT_SIZE / 2, CANVAS_SIZE - OUTPUT_SIZE));
  const cropTop  = Math.max(0, Math.min(stitchedY - OUTPUT_SIZE / 2, CANVAS_SIZE - OUTPUT_SIZE));

  let cropper = sharp(stitchedPng).extract({
    left: Math.round(cropLeft),
    top: Math.round(cropTop),
    width: OUTPUT_SIZE,
    height: OUTPUT_SIZE,
  });

  if (theme === 'vintage') {
    cropper = cropper.modulate({ saturation: 2.8, brightness: 1.0 });
  }

  let buffer;
  if (fmt === 'rgb565') {
    const raw = await cropper.removeAlpha().raw().toBuffer();
    buffer = rgb888ToRgb565BE(raw);
  } else {
    buffer = await cropper.jpeg({ quality: 75, mozjpeg: false }).toBuffer();
  }

  const payload = {
    buffer,
    timestamp: frame.timestamp,
    partial: osmBuffers.some(b => !b) || radarBuffers.some(b => !b),
    fmt,
  };

  frameCache.set(key, { payload, time: Date.now() });

  // Clean up stale cache entries on each write.
  const cutoff = Date.now() - FRAME_CACHE_TTL_MS * 2;
  for (const [k, v] of frameCache) {
    if (v.time < cutoff) frameCache.delete(k);
  }

  return payload;
}

// Convert raw RGB888 bytes to big-endian RGB565.
function rgb888ToRgb565BE(buf) {
  const pixels = buf.length / 3;
  const out = Buffer.allocUnsafe(pixels * 2);
  for (let i = 0; i < pixels; i++) {
    const r = buf[i * 3];
    const g = buf[i * 3 + 1];
    const b = buf[i * 3 + 2];
    const v = ((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3);
    out.writeUInt16BE(v, i * 2);
  }
  return out;
}

module.exports = { renderFrame };
