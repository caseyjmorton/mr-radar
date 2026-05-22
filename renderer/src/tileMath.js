const TILE_SIZE = 256;

// Standard Web Mercator slippy-map formulas.
// Returns the global pixel coordinate of a lat/lon at a given zoom level,
// where (0,0) is the top-left of the world tile grid.
function latLonToGlobalPixel(lat, lon, zoom) {
  const n = Math.pow(2, zoom);
  const latRad = (lat * Math.PI) / 180;
  const x = ((lon + 180) / 360) * n * TILE_SIZE;
  const y =
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
    n *
    TILE_SIZE;
  return { x, y };
}

function latLonToTile(lat, lon, zoom) {
  const n = Math.pow(2, zoom);
  const { x: gx, y: gy } = latLonToGlobalPixel(lat, lon, zoom);
  return {
    x: Math.max(0, Math.min(n - 1, Math.floor(gx / TILE_SIZE))),
    y: Math.max(0, Math.min(n - 1, Math.floor(gy / TILE_SIZE))),
    z: zoom,
  };
}

// Returns the 2x2 tile block that best centers the given lat/lon, and the
// pixel position of that lat/lon within the 512x512 stitched image.
// Tile layout in the returned array:  [0][1]
//                                     [2][3]
function getTileBlock(lat, lon, zoom) {
  const n = Math.pow(2, zoom);
  const gp = latLonToGlobalPixel(lat, lon, zoom);
  const tile = latLonToTile(lat, lon, zoom);

  const localX = gp.x - tile.x * TILE_SIZE;
  const localY = gp.y - tile.y * TILE_SIZE;

  // Anchor the 2x2 block so the point lands in the inner half of the stitched image.
  const colStart = localX >= TILE_SIZE / 2 ? tile.x : tile.x - 1;
  const rowStart = localY >= TILE_SIZE / 2 ? tile.y : tile.y - 1;

  const cs = Math.max(0, Math.min(n - 2, colStart));
  const rs = Math.max(0, Math.min(n - 2, rowStart));

  return {
    tiles: [
      { x: cs,     y: rs,     z: zoom },
      { x: cs + 1, y: rs,     z: zoom },
      { x: cs,     y: rs + 1, z: zoom },
      { x: cs + 1, y: rs + 1, z: zoom },
    ],
    stitchedX: Math.round(gp.x - cs * TILE_SIZE),
    stitchedY: Math.round(gp.y - rs * TILE_SIZE),
  };
}

module.exports = { latLonToTile, getTileBlock, TILE_SIZE };
