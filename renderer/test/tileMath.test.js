const { test } = require('node:test');
const assert = require('node:assert/strict');

const { latLonToTile, getTileBlock, TILE_SIZE } = require('../src/tileMath');

test('TILE_SIZE is the standard slippy-map tile dimension', () => {
  assert.equal(TILE_SIZE, 256);
});

test('latLonToTile places (0,0) at the grid center for zoom 7', () => {
  // At zoom 7 the world is 128x128 tiles; (lat 0, lon 0) is the exact center,
  // which falls on the tile (64, 64).
  assert.deepEqual(latLonToTile(0, 0, 7), { x: 64, y: 64, z: 7 });
});

test('latLonToTile clamps to valid tile indices at the extremes', () => {
  const n = Math.pow(2, 7);
  const tile = latLonToTile(85, 179.9, 7);
  assert.ok(tile.x >= 0 && tile.x <= n - 1, 'x within grid');
  assert.ok(tile.y >= 0 && tile.y <= n - 1, 'y within grid');
});

test('getTileBlock returns a 2x2 block centered on the point', () => {
  const block = getTileBlock(0, 0, 7);
  assert.equal(block.tiles.length, 4, 'four tiles');
  for (const t of block.tiles) {
    assert.equal(t.z, 7);
  }
  // The 2x2 block forms a contiguous square.
  const [tl, tr, bl, br] = block.tiles;
  assert.equal(tr.x, tl.x + 1);
  assert.equal(bl.y, tl.y + 1);
  assert.equal(br.x, tl.x + 1);
  assert.equal(br.y, tl.y + 1);
  // For the exact center point the station sits at the middle of the 512px stitch.
  assert.equal(block.stitchedX, 256);
  assert.equal(block.stitchedY, 256);
});

test('getTileBlock keeps the station within the 512px stitched window', () => {
  // KILN (Wilmington, OH) — a real station from the database.
  const block = getTileBlock(39.4208, -83.8217, 7);
  assert.equal(block.tiles.length, 4);
  assert.ok(block.stitchedX >= 0 && block.stitchedX <= 2 * TILE_SIZE);
  assert.ok(block.stitchedY >= 0 && block.stitchedY <= 2 * TILE_SIZE);
  // A 240px crop centered on the station must stay on the stitched image.
  assert.ok(block.stitchedX - 120 >= 0 && block.stitchedX + 120 <= 2 * TILE_SIZE);
  assert.ok(block.stitchedY - 120 >= 0 && block.stitchedY + 120 <= 2 * TILE_SIZE);
});
