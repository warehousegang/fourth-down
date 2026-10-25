// Scheduling only. GitHub owns forecasting, history, locking, tests and publication.
export const WORKFLOW = 'https://api.github.com/repos/warehousegang/thomashowarddev/actions/workflows/fourth-down-refresh.yml';
export const CRON = '17 * * * *';
const HOUR = 60 * 60 * 1000;

async function request(fetcher, url, token, method = 'GET', body) {
  try {
    return await fetcher(url, {
      method,
      redirect: 'manual', // Workers supports manual; callers reject every 3xx status.
      signal: AbortSignal.timeout(10_000),
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'User-Agent': 'fourth-down-scheduler',
        'X-GitHub-Api-Version': '2026-03-10',
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    // A network error can contain request details. Do not log the original error.
    throw new Error('GitHub request failed or timed out; inspect Actions before retrying');
  }
}

export async function dispatch(env, scheduledTime, fetcher = fetch) {
  if (env.ENABLED !== 'true') return { outcome: 'disabled' };
  if (!env.GITHUB_TOKEN) throw new Error('Missing GITHUB_TOKEN secret');
  if (!Number.isFinite(scheduledTime)) throw new Error('Invalid scheduled time');

  const response = await request(fetcher, `${WORKFLOW}/runs?branch=main&per_page=10`, env.GITHUB_TOKEN);
  if (response.status !== 200) throw new Error(`GitHub preflight failed (HTTP ${response.status})`);
  let runs;
  try {
    runs = (await response.json()).workflow_runs;
    if (!Array.isArray(runs) || runs.some(run => !run || typeof run.status !== 'string' ||
        !Number.isFinite(Date.parse(run.created_at)))) throw new Error();
  } catch {
    throw new Error('Invalid GitHub run history; dispatch suppressed');
  }
  // One clock replaces the native cron. History also suppresses repeated deliveries
  // and a manual invocation already covering this :17-to-:17 interval.
  const slotStart = Math.floor((scheduledTime - 17 * 60_000) / HOUR) * HOUR + 17 * 60_000;
  if (runs.some(run => run.status !== 'completed')) return { outcome: 'skipped_busy' };
  if (runs.some(run => Date.parse(run.created_at) >= slotStart)) return { outcome: 'skipped_existing' };

  // Exactly one POST attempt per invocation; an ambiguous timeout is never retried.
  const dispatched = await request(fetcher, `${WORKFLOW}/dispatches`, env.GITHUB_TOKEN, 'POST', { ref: 'main' });
  if (![200, 204].includes(dispatched.status)) throw new Error(`GitHub dispatch failed (HTTP ${dispatched.status})`);
  let runId = null;
  if (dispatched.status === 200) {
    try {
      const body = await dispatched.json();
      if (Number.isSafeInteger(body.workflow_run_id)) runId = body.workflow_run_id;
    } catch { /* Accepted POST: never resend because a receipt could not be parsed. */ }
  }
  return { outcome: 'dispatched', http_status: dispatched.status, run_id: runId };
}

