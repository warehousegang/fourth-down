import {test} from 'node:test';
import assert from 'node:assert/strict';
import {dispatch,PLAN,WORKFLOW,CRON} from './dispatch.mjs';
import {readFileSync} from 'node:fs';
const env={ENABLED:'true',GITHUB_TOKEN:'synthetic-secret'};
const kick=Date.parse('2026-10-25T13:30:00Z');
const plan={schema_version:1,season:2026,operations_sha256:'a'.repeat(64),generated_at:'2026-10-25T00:00:00Z',
  games:[{id:'ngs-2026-60272',kickoff:new Date(kick).toISOString(),status:'unknown'}]};
function fixture(hint=plan,runs=[],post=204) {
  const calls=[];
  const fetcher=async(url,options)=>{
    calls.push({url,options});
    if(url===PLAN){assert.equal(options.headers,undefined);return new Response(JSON.stringify(hint));}
    assert.equal(options.headers.Authorization,'Bearer synthetic-secret');
    assert.equal(options.redirect,'manual');
    if(url.endsWith('/dispatches'))return new Response(null,{status:post});
    assert.equal(url,WORKFLOW+'/runs?branch=main&per_page=10');
    return Response.json({workflow_runs:runs});
  };
  return {calls,fetcher};
}
test('review configuration cannot activate a schedule',()=>{
  const config=JSON.parse(readFileSync(new URL('./wrangler.json',import.meta.url)));
  assert.equal(config.vars.ENABLED,'false');assert.deepEqual(config.triggers.crons,[]);
  assert.equal(CRON,'2,17,32,47 * * * *');
});
test('disabled worker makes no request',async()=>{
  assert.deepEqual(await dispatch({},kick,()=>{throw Error('network')}),{outcome:'disabled'});
});
test('fifteen-minute active window and hourly fallback are bounded',async()=>{
  for(const minute of [2,17,32,47]) {
    const f=fixture();const time=Date.parse('2026-10-25T17:00:00Z')+minute*60_000;
    assert.equal((await dispatch(env,time,f.fetcher)).outcome,'dispatched');assert.equal(f.calls.length,3);
    assert.equal(f.calls.at(-1).options.body,JSON.stringify({ref:'main'}));
  }
  for(const minutes of [-28,24*60+2]) {
    const f=fixture();assert.equal((await dispatch(env,kick+minutes*60_000,f.fetcher)).outcome,'outside_game_window');
    assert.equal(f.calls.length,1);
  }
  const f=fixture();assert.equal((await dispatch(env,Date.parse('2026-10-25T10:17:00Z'),f.fetcher)).outcome,'dispatched');
});
test('verified finals, cancellations and postponements end high-frequency dispatch',async()=>{
  for(const status of ['completed','canceled','postponed']) {
    const f=fixture({...plan,games:[{...plan.games[0],status}]});
    assert.equal((await dispatch(env,kick+17*60_000,f.fetcher)).outcome,'outside_game_window');
  }
});
test('busy and duplicate runs suppress POST, prior slot permits one POST',async()=>{
  for(const [status,created_at,outcome] of [
    ['in_progress','2026-10-25T13:02:00Z','skipped_busy'],
    ['completed','2026-10-25T13:32:01Z','skipped_existing'],
    ['completed','2026-10-25T13:17:01Z','dispatched']]) {
    const f=fixture(plan,[{status,created_at}]);
    assert.equal((await dispatch(env,kick+2*60_000,f.fetcher)).outcome,outcome);
    assert.equal(f.calls.filter(c=>c.options.method==='POST').length,outcome==='dispatched'?1:0);
  }
});
test('bad, stale, oversized and unavailable hints retain hourly safety net',async()=>{
  for(const hint of [{}, {...plan,generated_at:'2026-10-01T00:00:00Z'},
    {...plan,games:[...plan.games,...plan.games]}, {...plan,extra:'x'.repeat(65_000)}]) {
    const f=fixture(hint);
    assert.equal((await dispatch(env,kick+2*60_000,f.fetcher)).outcome,'outside_game_window');
    assert.equal((await dispatch(env,kick+47*60_000,f.fetcher)).outcome,'dispatched');
  }
  const f=fixture();
  const unavailable=(url,options)=>url===PLAN?Promise.reject(new Error('offline')):f.fetcher(url,options);
  assert.equal((await dispatch(env,kick+47*60_000,unavailable)).outcome,'dispatched');
});
test('ambiguous POST failure is never retried and does not leak a token',async()=>{
  const f=fixture();let posts=0;
  await assert.rejects(dispatch(env,kick+2*60_000,(url,options)=>{
    if(options.method==='POST'){posts++;throw new Error('synthetic-secret');}
    return f.fetcher(url,options);
  }),{message:'GitHub request failed or timed out; inspect Actions before retrying'});
  assert.equal(posts,1);
});
test('malformed run history and redirect responses cannot dispatch',async()=>{
  for(const body of [{workflow_runs:[{}]},{workflow_runs:null}]) {
    const f=fixture();let posts=0;
    await assert.rejects(dispatch(env,kick+2*60_000,(url,options)=>{
      if(url===PLAN)return f.fetcher(url,options);
      if(options.method==='POST')posts++;
      return Promise.resolve(Response.json(body));
    }),/Invalid GitHub run history/);
    assert.equal(posts,0);
  }
});
