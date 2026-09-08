const { test } = require('node:test');
const assert = require('node:assert/strict');

const { cartoDarkUrl, osmTileUrl, hasCartoKey, redactUrl } = require('../src/tiles');

// The key is read lazily from the environment on every call, so each test can
// set it independently. Restore whatever the runner started with.
const ORIGINAL_KEY = process.env.CARTO_API_KEY;

function withKey(value, fn) {
  if (value === undefined) delete process.env.CARTO_API_KEY;
  else process.env.CARTO_API_KEY = value;
  try {
    return fn();
  } finally {
    if (ORIGINAL_KEY === undefined) delete process.env.CARTO_API_KEY;
    else process.env.CARTO_API_KEY = ORIGINAL_KEY;
  }
}

test('cartoDarkUrl omits the key parameter when CARTO_API_KEY is unset', () => {
  withKey(undefined, () => {
    const url = cartoDarkUrl('dark_nolabels', 7, 34, 48);
    assert.ok(!url.includes('key='), 'no key parameter should be present');
    assert.match(url, /^https:\/\/[a-d]\.basemaps\.cartocdn\.com\/dark_nolabels\/7\/34\/48\.png$/);
  });
});

test('cartoDarkUrl appends the key parameter when CARTO_API_KEY is set', () => {
  withKey('test-key-123', () => {
    const url = cartoDarkUrl('dark_only_labels', 7, 34, 48);
    assert.match(url, /\/dark_only_labels\/7\/34\/48\.png\?key=test-key-123$/);
  });
});

test('cartoDarkUrl percent-encodes keys containing URL-significant characters', () => {
  withKey('a b&c=d', () => {
    const url = cartoDarkUrl('dark_nolabels', 7, 34, 48);
    assert.ok(url.endsWith('?key=a%20b%26c%3Dd'), `unexpected encoding: ${url}`);
  });
});

test('hasCartoKey reflects the environment', () => {
  withKey(undefined, () => assert.equal(hasCartoKey(), false));
  withKey('', () => assert.equal(hasCartoKey(), false));
  withKey('something', () => assert.equal(hasCartoKey(), true));
});

test('osmTileUrl never carries a key, even when one is configured', () => {
  withKey('test-key-123', () => {
    assert.equal(osmTileUrl(7, 34, 48), 'https://tile.openstreetmap.org/7/34/48.png');
  });
});

test('redactUrl hides the key so it cannot leak into logs or errors', () => {
  assert.equal(
    redactUrl('https://a.basemaps.cartocdn.com/dark_nolabels/7/34/48.png?key=secret'),
    'https://a.basemaps.cartocdn.com/dark_nolabels/7/34/48.png?key=REDACTED'
  );
  // Also when the key is not the first parameter.
  assert.equal(
    redactUrl('https://example.com/t.png?a=1&key=secret&b=2'),
    'https://example.com/t.png?a=1&key=REDACTED&b=2'
  );
  // Leaves key-free URLs untouched.
  const plain = 'https://tile.openstreetmap.org/7/34/48.png';
  assert.equal(redactUrl(plain), plain);
});

test('cartoDarkUrl rotates across the load-balancing subdomains', () => {
  withKey(undefined, () => {
    const seen = new Set();
    for (let i = 0; i < 8; i++) {
      seen.add(cartoDarkUrl('dark_nolabels', 7, 34, 48).match(/^https:\/\/([a-d])\./)[1]);
    }
    assert.equal(seen.size, 4, 'should cycle through all four subdomains');
  });
});
