const express = require('express');
const { frameHandler, stationsHandler } = require('./handler');

const app = express();

app.get('/frame', frameHandler);
app.get('/stations', stationsHandler);
app.get('/health', (_req, res) => res.json({ ok: true, ts: Date.now() }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`mr-radar renderer listening on :${PORT}`);
});
