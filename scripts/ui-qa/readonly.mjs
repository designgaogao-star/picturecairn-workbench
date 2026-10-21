import assert from 'node:assert/strict';

export const readonlyCalls = [
  ['post', '/api/v1/libraries', { path: 'QA' }],
  ...['scan', 'prewarm', 'build', 'analyze', 'compare', 'audit', 'collect'].map((kind) => [
    'post', '/api/v1/tasks', { kind },
  ]),
  ...['pause', 'resume', 'cancel'].map((action) => [
    'post', '/api/v1/tasks/{task_id}/control', { action },
  ]),
  ['patch', '/api/v1/groups/{group_id}/review', { state: 'kept' }],
  ['put', '/api/v1/groups/{group_id}/position', { image_id: 'qa' }],
  ['post', '/api/v1/operations/delete', { targets: [{ kind: 'image', id: 'qa' }] }],
  ['delete', '/api/v1/tasks/{task_id}', undefined],
];

export async function readonlyApiChecks(server, base) {
  const originalFetch = globalThis.fetch;
  const writes = [];
  globalThis.location = new URL(`${base}?readonly`);
  globalThis.fetch = async (input, options) => {
    if ((options?.method || 'GET') !== 'GET') {
      writes.push(options.method);
      return new Response('{"error":"QA intercepted a write"}', { status: 503 });
    }
    return originalFetch(new URL(input, base), options);
  };
  try {
    const { client, readonly } = await server.ssrLoadModule('/src/api.ts');
    assert.equal(readonly, true);
    await client.request('get', '/api/v1/health');
    const errors = [];
    for (const [method, route, body] of readonlyCalls) {
      try {
        await client.request(method, route, { body, params: { path: { task_id: 'qa', group_id: 'qa' } } });
        errors.push('unexpected success');
      } catch (error) { errors.push(error.message); }
    }
    assert.equal(writes.length, 0, `Readonly writes reached the transport: ${JSON.stringify(writes)}`);
    assert.ok(errors.every((message) => message.includes('只读联调模式')), JSON.stringify(errors));
    console.log(`PASS readonly API boundary: ${readonlyCalls.length} writes blocked, GET succeeds`);
  } finally {
    globalThis.fetch = originalFetch;
    delete globalThis.location;
  }
}

export async function readonlyChecks(page, base, library, output) {
  const writes = [];
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') return route.continue();
    writes.push({ method: request.method(), path: new URL(request.url()).pathname });
    // The baseline must be safe even when the readonly guard is broken.
    await route.fulfill({ status: 503, json: { error: 'QA intercepted a write' } });
  });
  await page.goto(`${base}?readonly`);
  await page.getByRole('button', { name: '添加图库', exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: '选择文件夹…', exact: true }).count(), 0);

  const attempts = await page.evaluate(async (calls) => {
    const { client, readonly } = await import('/src/api.ts');
    if (!readonly) throw new Error('Readonly flag is not enabled in the dev build');
    await client.request('get', '/api/v1/health');
    await new client.constructor('').request('get', '/api/v1/health');
    const results = [];
    for (const [method, route, body] of calls) {
      try {
        await client.request(method, route, {
          body, params: { path: { task_id: 'qa', group_id: 'qa' } },
        });
        results.push('unexpected success');
      } catch (error) { results.push(error.message); }
    }
    return results;
  }, readonlyCalls);
  assert.equal(writes.length, 0, `Readonly writes reached the network: ${JSON.stringify(writes)}`);
  assert.ok(attempts.every((message) => message.includes('只读联调模式')), JSON.stringify(attempts));

  await page.getByPlaceholder('例如 D:\\图片\\收藏').fill(library);
  await page.getByRole('button', { name: '添加图库', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: '只读联调模式' }).waitFor();
  assert.equal(writes.length, 0);
  await page.screenshot({ path: `${output}/readonly-desktop.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: `${output}/readonly-narrow.png` });

  await page.goto(base);
  await page.evaluate(async () => {
    const { client, readonly } = await import('/src/api.ts');
    if (readonly) throw new Error('Readonly flag should be disabled without the query');
    await client.request('post', '/api/v1/tasks', { body: { kind: 'collect' } }).catch(() => {});
  });
  assert.equal(writes.length, 1, 'Normal development requests must reach the transport');
  assert.deepEqual(errors, []);
  console.log(`PASS readonly: ${attempts.length} write calls blocked; browser form, desktop/narrow, ordinary dev mode`);
}
