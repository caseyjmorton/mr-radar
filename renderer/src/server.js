const express = require('express');
const { frameHandler, stationsHandler } = require('./handler');
const { version } = require('../package.json');

const app = express();

app.get('/frame', frameHandler);
app.get('/stations', stationsHandler);
app.get('/health', (_req, res) => res.json({ ok: true, ts: Date.now(), version }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`mr-radar renderer listening on :${PORT}`);
});
