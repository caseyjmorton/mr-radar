const sharp = require('sharp');
const { getTileBlock, TILE_SIZE } = require('./tileMath');
const { fetchOsmTile, fetchCartoDarkTile, fetchCartoDarkAllTile, fetchRadarTile } = require('./tiles');
const { getLatestFrame, radarTileUrl } = require('./rainviewer');

const OUTPUT_SIZE = 240;
const DEFAULT_ZOOM = 6;    // ~122 nm radius, matches standard NEXRAD reflectivity range
const MAX_ZOOM = 7;        // RainViewer API hard limit
const MIN_ZOOM = 1;
const DEFAULT_OPACITY = 80;       // percent — radar reflectivity (screen-blended in vintage)
const CANVAS_SIZE = TILE_SIZE * 2; // 512x512 stitched canvas

const frameCache = new Map();
const FRAME_CACHE_TTL_MS = 5 * 60 * 1000;

// Scale the alpha channel of a radar tile by a factor in [0, 1].
async function applyOpacity(buffer, factor) {
  if (factor >= 1) return buffer;
  const { data, info } = await sharp(buffer).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  for (let i = 3; i < data.length; i += 4) {
    data[i] = Math.round(data[i] * factor);
  }
  return sharp(data, { raw: { width: info.width, height: info.height, channels: 4 } }).png().toBuffer();
}

// Build a transparent overlay of just a CARTO tile's bright features (borders,
// labels) using luminance as an alpha mask, so an `over` blend floats them above
// the radar without muting it. dark_all at zoom 6 is dark: bg lum ~6-20, features ~40-68.
async function featureOverlay(buffer) {
  const rgb = sharp(buffer).removeAlpha();
  const [colors, alpha] = await Promise.all([
    rgb.clone().linear(3.5, 30).toBuffer(),                          // hard-brighten dim feature colors
    rgb.clone().grayscale().linear(7, -210).toColourspace('b-w').toBuffer(), // luminance → alpha mask
  ]);
  return sharp(colors).joinChannel(alpha).png().toBuffer();
}

async function renderFrame(lat, lon, fmt, theme = 'vintage', zoom = DEFAULT_ZOOM, opacity = DEFAULT_OPACITY) {
  const frame = await getLatestFrame();

  // Round coords to ~11m precision so nearby devices share cache entries.
  const key = `${lat.toFixed(4)},${lon.toFixed(4)},${fmt},${theme},${zoom},${opacity},${frame.path}`;
  const cached = frameCache.get(key);
  if (cached && Date.now() - cached.time < FRAME_CACHE_TTL_MS) {
    return cached.payload;
  }

  const { tiles, stitchedX, stitchedY } = getTileBlock(lat, lon, zoom);

  const opacityFactor = opacity / 100;
  const isVintage = theme === 'vintage';

  // Fetch all tile layers in parallel; failures return null so we degrade gracefully.
  const [baseBuffers, radarBuffers, overlayBuffers] = await Promise.all([
    Promise.all(tiles.map(t =>
      (isVintage ? fetchCartoDarkTile : fetchOsmTile)(t.z, t.x, t.y).catch(() => null)
    )),
    Promise.all(tiles.map(t =>
      fetchRadarTile(radarTileUrl(frame.host, frame.path, t.z, t.x, t.y)).catch(() => null)
    )),
    // Vintage: dark_all (borders + labels) → masked feature overlay above the radar.
    isVintage
      ? Promise.all(tiles.map(t => fetchCartoDarkAllTile(t.z, t.x, t.y).catch(() => null)))
      : Promise.resolve([null, null, null, null]),
  ]);

  const [dimmedRadarBuffers, featureBuffers] = await Promise.all([
    Promise.all(radarBuffers.map(b => b ? applyOpacity(b, opacityFactor) : null)),
    Promise.all(overlayBuffers.map(b => b ? featureOverlay(b) : null)),
  ]);

  // Composite order: base → radar → map overlay (borders + labels float above radar).
  const inputs = [];
  for (let i = 0; i < 4; i++) {
    const top = Math.floor(i / 2) * TILE_SIZE;
    const left = (i % 2) * TILE_SIZE;
    if (baseBuffers[i])        inputs.push({ input: baseBuffers[i],        top, left });
    // Screen blend keeps radar colors vivid over the dark base instead of darkening them toward it.
    if (dimmedRadarBuffers[i]) inputs.push({ input: dimmedRadarBuffers[i], top, left, blend: isVintage ? 'screen' : 'over' });
    // Masked feature overlay: crisp bright borders + labels over the radar, transparent elsewhere.
    if (featureBuffers[i])     inputs.push({ input: featureBuffers[i],     top, left, blend: 'over' });
  }

  // Canvas fill color: neutral gray for modern, near-black for vintage (matches CARTO dark tiles).
  const canvasBg = theme === 'vintage'
    ? { r: 26, g: 26, b: 26, alpha: 1 }
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
    partial: baseBuffers.some(b => !b) || radarBuffers.some(b => !b) || overlayBuffers.some(b => !b),
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

module.exports = { renderFrame, DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, DEFAULT_OPACITY };
