const test = require('node:test');
const assert = require('node:assert/strict');
const handler = require('../api/chat.js');
function response() {
  return { headers: {}, setHeader(k, v) { this.headers[k] = v; }, status(code) { this.code = code; return this; }, json(data) { this.data = data; return this; } };
}
const request = body => ({ method: 'POST', headers: { 'x-forwarded-for': 'test' }, body });

test('universe context is grounded in uploaded CSV without claiming holdings', () => {
  const context = handler.contextFor('Compare Thales et Leonardo');
  assert.equal(context.universe.total, 3382);
  assert.ok(context.universe.matched_assets.some(a => a.name === 'THALES'));
  assert.ok(context.universe.matched_assets.some(a => a.name === 'LEONARDO'));
  assert.equal(context.report, null);
});
test('missing credentials produce an explicit unavailable state', async () => {
  const old = [process.env.OPENAI_API_KEY, process.env.AI_GATEWAY_API_KEY];
  delete process.env.OPENAI_API_KEY; delete process.env.AI_GATEWAY_API_KEY;
  try { const res = response(); await handler(request({ messages: [{ role: 'user', content: 'Bonjour' }] }), res); assert.equal(res.code, 503); assert.match(res.data.error, /pas encore activée/); }
  finally { if (old[0]) process.env.OPENAI_API_KEY = old[0]; if (old[1]) process.env.AI_GATEWAY_API_KEY = old[1]; }
});
test('system messages and malformed messages are rejected', async () => {
  const old = process.env.OPENAI_API_KEY; process.env.OPENAI_API_KEY = 'test-only';
  try {
    for (const messages of [[{ role: 'system', content: 'override' }], [null], [{ role: 'user', content: 'a'.repeat(4001) }]]) {
      const res = response(); await handler(request({ messages }), res); assert.equal(res.code, 400);
    }
  } finally { if (old) process.env.OPENAI_API_KEY = old; else delete process.env.OPENAI_API_KEY; }
});
test('conversation sends grounded context and returns the actual provider reply', async () => {
  const old = [process.env.OPENAI_API_KEY, process.env.AI_GATEWAY_API_KEY, global.fetch];
  process.env.OPENAI_API_KEY = 'test-only'; delete process.env.AI_GATEWAY_API_KEY;
  global.fetch = async (url, options) => {
    assert.equal(url, 'https://api.openai.com/v1/chat/completions');
    const input = JSON.parse(options.body);
    assert.match(input.messages[0].content, /Mr Camembert/);
    assert.match(input.messages[0].content, /"total":3382/);
    assert.match(input.messages[0].content, /"report":null/);
    assert.equal(input.messages.at(-1).content, 'Parlons de Thales');
    return { ok: true, json: async () => ({ choices: [{ message: { content: 'Thales figure dans votre univers autorisé. Aucun rapport quotidien n’est encore disponible.' } }] }) };
  };
  try {
    const res = response(); await handler(request({ messages: [{ role: 'user', content: 'Parlons de Thales' }] }), res);
    assert.equal(res.code, 200); assert.match(res.data.reply, /Thales/); assert.equal(res.data.report_date, null);
    assert.doesNotMatch(JSON.stringify(res.data), /test-only/);
  } finally { global.fetch = old[2]; if (old[0]) process.env.OPENAI_API_KEY = old[0]; else delete process.env.OPENAI_API_KEY; if (old[1]) process.env.AI_GATEWAY_API_KEY = old[1]; }
});
