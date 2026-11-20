const { test } = require('node:test');
const assert = require('node:assert/strict');
const { defaults, buildRequest, requestHash, parseHash, pageRequest } = require('../frontend/site/js/test-console.js');

test('lookup preserves input and only builds the selected API request', () => {
  const request = buildRequest('lookup', ' Huízen & huis ', defaults('lookup'));
  assert.equal(request.method, 'GET');
  assert.equal(request.path, '/lookup');
  assert.equal(new URLSearchParams(request.search).get('q'), ' Huízen & huis ');
  assert.equal(new URLSearchParams(request.search).get('limit'), '5');
  assert.equal(request.body, undefined);
});

test('semantic body preserves language, negation, quotes and false include_related', () => {
  const query = 'a noun for a vehicle with 2 wheels, not a motorbike: "fiets"';
  const request = buildRequest('semantic', query, { limit: 3, include_related: false });
  assert.equal(request.path, '/semantic-search');
  assert.equal(request.method, 'POST');
  assert.deepEqual(request.body, { query, limit: 3, include_related: false });
  assert.equal(request.search, undefined);
});

test('entry pagination changes one group and preserves every other page', () => {
  const request = buildRequest('entry', '1', { ...defaults('entry'), form_offset: 50, example_limit: 10 });
  const next = pageRequest(request, ['senses'], 20, 20);
  const params = new URLSearchParams(next.search);
  assert.equal(next.path, '/entries/1');
  assert.equal(params.get('sense_offset'), '20');
  assert.equal(params.get('form_offset'), '50');
  assert.equal(params.get('example_limit'), '10');
  assert.equal(pageRequest(request, ['senses', 'items', '0', 'examples'], 3, 3), null);
});

test('sense examples use their own pagination endpoint', () => {
  const request = buildRequest('examples', '12960', defaults('examples'));
  const next = pageRequest(request, ['examples'], 10, 10);
  assert.equal(next.path, '/senses/12960/examples');
  assert.equal(new URLSearchParams(next.search).get('offset'), '10');
});

test('existing deep links fill the appropriate API form without needing a request', () => {
  assert.equal(parseHash('#/betekenis').endpoint, 'semantic');
  assert.deepEqual(parseHash('#/woord/19?q=er&form=er&mt=form_exact'), { endpoint: 'entry', query: '19', params: defaults('entry') });
  assert.equal(parseHash('#/zoeken?q=huizen').query, 'huizen');
  const request = buildRequest('semantic', '可以借书的地方', { limit: 5, include_related: false });
  const parsed = parseHash(requestHash(request));
  assert.equal(parsed.query, request.query);
  assert.equal(parsed.params.include_related, false);
  assert.equal(parsed.params.limit, '5');
});
