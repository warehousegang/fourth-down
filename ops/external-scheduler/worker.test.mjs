import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import worker from './worker.mjs';
import { dispatch, WORKFLOW, CRON } from './dispatch.mjs';

// Deliberately invalid sentinel: never use a real credential in local testing.
const env = { ENABLED: 'true', GITHUB_TOKEN: 'test-only-not-a-credential' };
const time = Date.parse('2026-10-24T23:17:00Z');
const history = runs => Response.json({ workflow_runs: runs });
const done = created_at => ({ status: 'completed', created_at });
function mock(...responses) {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    const response = responses.shift();
    if (response instanceof Error) throw response;
    assert.ok(response, 'Unexpected request');
    return response;
  };
  return { calls, fetcher };
}

test('approved hourly configuration: one cron, no HTTP endpoint, no credential', () => {
  const config = JSON.parse(readFileSync(new URL('./wrangler.json', import.meta.url)));
  assert.deepEqual(config.triggers.crons, [CRON]);
  assert.equal(config.vars.ENABLED, 'true');
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.equal(config.routes, undefined);
  assert.equal(worker.fetch, undefined);
  assert.equal(JSON.stringify(config).includes('GITHUB_TOKEN'), false);
});

test('disabled scheduler never accesses GitHub', async () => {
  const api = mock();
  assert.deepEqual(await dispatch({}, time, api.fetcher), { outcome: 'disabled' });
  assert.equal(api.calls.length, 0);
});

test('missing credential fails before any request', async () => {
  const api = mock();
  await assert.rejects(dispatch({ ENABLED: 'true' }, time, api.fetcher), /Missing GITHUB_TOKEN/);
  assert.equal(api.calls.length, 0);
});

test('fixed endpoint, main branch, minimum API contract and safe transport', async () => {
  const api = mock(history([done('2026-10-24T22:17:00Z')]), Response.json({ workflow_run_id: 123 }));
  assert.deepEqual(await dispatch(env, time, api.fetcher), { outcome: 'dispatched', http_status: 200, run_id: 123 });
  assert.equal(api.calls.length, 2);
  assert.equal(api.calls[0].url, `${WORKFLOW}/runs?branch=main&per_page=10`);
  assert.equal(api.calls[1].url, `${WORKFLOW}/dispatches`);
  assert.equal(api.calls[1].options.method, 'POST');
  assert.deepEqual(JSON.parse(api.calls[1].options.body), { ref: 'main' });
  for (const { url, options } of api.calls) {
    assert.equal(new URL(url).origin, 'https://api.github.com');
    assert.equal(options.redirect, 'manual');
    assert.ok(options.signal instanceof AbortSignal);
    assert.equal(options.headers.Authorization, `Bearer ${env.GITHUB_TOKEN}`);
    assert.equal(options.headers['X-GitHub-Api-Version'], '2026-03-10');
  }
});

test('empty 204 acceptance does not cause another POST', async () => {
  const api = mock(history([]), new Response(null, { status: 204 }));
  assert.equal((await dispatch(env, time, api.fetcher)).outcome, 'dispatched');
  assert.equal(api.calls.length, 2);
});

for (const status of ['in_progress', 'queued', 'waiting', 'pending', 'requested']) {
  test(`does not dispatch while an existing run is ${status}`, async () => {
    const api = mock(history([{ status, created_at: '2026-10-24T22:17:00Z' }]));
    assert.equal((await dispatch(env, time, api.fetcher)).outcome, 'skipped_busy');
    assert.equal(api.calls.length, 1);
  });
}

test('repeated delivery after acceptance skips the existing run', async () => {
  const api = mock(history([]), Response.json({ workflow_run_id: 123 }), history([done('2026-10-24T23:17:01Z')]));
  assert.equal((await dispatch(env, time, api.fetcher)).outcome, 'dispatched');
  assert.equal((await dispatch(env, time, api.fetcher)).outcome, 'skipped_existing');
  assert.equal(api.calls.filter(call => call.options.method === 'POST').length, 1);
});

test('next hour is eligible, even across midnight and the DST fallback', async () => {
  for (const [previous, next] of [
    ['2026-10-24T23:17:01Z', '2026-10-25T00:17:00Z'],
    ['2026-11-01T05:17:01Z', '2026-11-01T06:17:00Z'],
  ]) {
    const api = mock(history([done(previous)]), new Response(null, { status: 204 }));
    assert.equal((await dispatch(env, Date.parse(next), api.fetcher)).outcome, 'dispatched');
  }
});

for (const status of [401, 403, 404, 422, 429, 500, 302]) {
  test(`preflight HTTP ${status} suppresses dispatch without exposing response data`, async () => {
    const api = mock(new Response(env.GITHUB_TOKEN, { status }));
    await assert.rejects(dispatch(env, time, api.fetcher), error => {
      assert.equal(error.message, `GitHub preflight failed (HTTP ${status})`);
      return true;
    });
    assert.equal(api.calls.length, 1);
  });
}

test('malformed run history fails closed', async () => {
  for (const body of [{}, { workflow_runs: [null] }, { workflow_runs: [{ status: 'completed' }] }]) {
    const api = mock(Response.json(body));
    await assert.rejects(dispatch(env, time, api.fetcher), /Invalid GitHub run history/);
    assert.equal(api.calls.length, 1);
  }
});

test('ambiguous POST timeout never retries or echoes the token', async () => {
  const api = mock(history([]), new Error(`network exception with ${env.GITHUB_TOKEN}`));
  await assert.rejects(dispatch(env, time, api.fetcher), error => {
    assert.match(error.message, /timed out/);
    assert.equal(error.message.includes(env.GITHUB_TOKEN), false);
    return true;
  });
  assert.equal(api.calls.length, 2);
});

test('POST error body is never reflected in diagnostics', async () => {
  const api = mock(history([]), new Response(env.GITHUB_TOKEN, { status: 403 }));
  await assert.rejects(dispatch(env, time, api.fetcher), { message: 'GitHub dispatch failed (HTTP 403)' });
  assert.equal(api.calls.length, 2);
});

test('redirected POST fails closed and never follows Location with the credential', async () => {
  const api = mock(history([]), new Response(null, {
    status: 307, headers: { Location: 'https://example.invalid/credential-trap' },
  }));
  await assert.rejects(dispatch(env, time, api.fetcher), { message: 'GitHub dispatch failed (HTTP 307)' });
  assert.equal(api.calls.length, 2);
  assert.ok(api.calls.every(call => call.options.redirect === 'manual'));
});

test('accepted POST with an invalid receipt is not retried', async () => {
  const api = mock(history([]), new Response(env.GITHUB_TOKEN, { status: 200 }));
  assert.deepEqual(await dispatch(env, time, api.fetcher), { outcome: 'dispatched', http_status: 200, run_id: null });
  assert.equal(api.calls.length, 2);
});

test('handler disables platform retries and logs only receipt fields', async () => {
  let noRetry = 0;
  const output = [];
  const originalLog = console.log;
  const originalFetch = globalThis.fetch;
  const api = mock(history([]), Response.json({ workflow_run_id: 123, untrusted: env.GITHUB_TOKEN }));
  console.log = value => output.push(value);
  globalThis.fetch = api.fetcher;
  try {
    await worker.scheduled({ cron: CRON, scheduledTime: time, noRetry: () => noRetry++ }, env);
    assert.equal(noRetry, 1);
    assert.equal(output.length, 1);
    assert.equal(output[0].includes(env.GITHUB_TOKEN), false);
    assert.deepEqual(JSON.parse(output[0]), {
      scheduled_at: '2026-10-24T23:17:00.000Z', outcome: 'dispatched', http_status: 200, run_id: 123,
    });
  } finally {
    console.log = originalLog;
    globalThis.fetch = originalFetch;
  }
});
