// Scheduling only. GitHub owns forecasting, history, locking, tests and publication.
export const WORKFLOW = 'https://api.github.com/repos/warehousegang/thomashowarddev/actions/workflows/fourth-down-refresh.yml';
export const CRON = '2,17,32,47 * * * *';
export const PLAN = 'https://thomashoward.dev/fourth-down/data/game-day.json';
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

  let active=false;
  try {
    const planResponse=await fetcher(PLAN,{redirect:'manual',signal:AbortSignal.timeout(10_000)});
    if(planResponse.status===200){
      const body=await planResponse.text();
      if(body.length>64_000)throw new Error('Oversized plan');
      const plan=JSON.parse(body),generated=Date.parse(plan.generated_at);
      if(plan.schema_version!==1||!Number.isInteger(plan.season)||plan.season<2026||
         !/^[a-f0-9]{64}$/.test(plan.operations_sha256)||!Number.isFinite(generated)||
         generated>scheduledTime||scheduledTime-generated>7*24*HOUR||!Array.isArray(plan.games)||plan.games.length>300||
         new Set(plan.games.map(g=>g.id)).size!==plan.games.length||
         plan.games.some(g=>!new RegExp(`^ngs-${plan.season}-[0-9]+$`).test(g.id)||
           !['scheduled','in_progress','completed','postponed','canceled','unknown'].includes(g.status)||
           (g.kickoff!==null&&!Number.isFinite(Date.parse(g.kickoff)))))throw new Error('Invalid plan');
      active=plan.games.some(g=>g.kickoff&& !['completed','canceled','postponed'].includes(g.status)&&
        scheduledTime>=Date.parse(g.kickoff)-15*60_000&&scheduledTime<=Date.parse(g.kickoff)+24*HOUR);
    }
  }catch { /* An unavailable/invalid hint falls back to the original hourly check. */ }
  const minute=new Date(scheduledTime).getUTCMinutes();
  if(!active&&minute!==17)return {outcome:'outside_game_window'};
  const interval=active?15*60_000:HOUR, offset=(active?2:17)*60_000;
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
  // Run history suppresses duplicates in the current 15-minute or hourly slot.
  const slotStart = Math.floor((scheduledTime-offset)/interval)*interval+offset;
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
