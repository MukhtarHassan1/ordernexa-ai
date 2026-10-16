const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app/console/index.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'app/console/app.js'), 'utf8');

test('required blueprint operations screens are present', () => {
  for (const page of [
    'overview','transactions','decisions','approvals','exceptions','recovery',
    'health','governance','askops','readiness','automation','voice','audit'
  ]) assert.match(html, new RegExp(`id="page-${page}"`));
});

test('readiness and model routing are backed by API endpoints', () => {
  assert.match(js, /\/ops\/release-readiness/);
  assert.match(js, /\/ops\/model-routing/);
  assert.match(html, /Implemented, configured and verified are different states/);
});

test('active console uses current OrderNexa product branding only', () => {
  assert.match(html, /OrderNexa AI/);
  assert.match(html, /ATLAS INDUSTRIAL SYSTEMS/);
  assert.doesNotMatch(html, /NECTELIS/i);
  assert.doesNotMatch(html, /ATLAS\s*DEMO/i);
  assert.match(html, /id="last-refresh"/);
});
