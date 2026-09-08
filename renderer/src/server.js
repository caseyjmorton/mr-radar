const express = require('express');
const { frameHandler, stationsHandler } = require('./handler');
const { hasCartoKey } = require('./tiles');
const { version } = require('../package.json');

const app = express();

app.get('/frame', frameHandler);
app.get('/stations', stationsHandler);
app.get('/health', (_req, res) => res.json({ ok: true, ts: Date.now(), version }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`mr-radar renderer listening on :${PORT}`);
  if (!hasCartoKey()) {
    // Not fatal: unkeyed CARTO tiles still return 200, they just arrive
    // watermarked. Warn loudly because the affected theme is the default, so
    // the symptom (defaced map) is easy to misread as a rendering bug.
    console.warn(
      'WARNING: CARTO_API_KEY is not set. The "vintage" theme — which is the ' +
      'default — will render base map tiles stamped "API KEY REQUIRED". ' +
      'Get a free key at https://carto.com/basemaps/apikey and set ' +
      'CARTO_API_KEY. The "modern" theme uses OpenStreetMap and is unaffected.'
    );
  }
});
