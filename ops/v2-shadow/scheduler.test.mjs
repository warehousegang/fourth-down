import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{csv,due} from './scheduler.mjs';
const activation='2026-10-29T00:00:00Z';
const calendar='season,season_type,game_time,phase,venue\n2026,REG,2026-11-01T18:00:00Z,,"Quoted, Stadium"\n';
const event={scheduledTime:Date.parse('2026-11-01T16:35:00Z')};
test('disabled scheduler cannot dispatch',async()=>{
 const original=globalThis.fetch;globalThis.fetch=()=>assert.fail('Disabled Worker made a request');
 try{await worker.scheduled(event,{ENABLED:'false'});}finally{globalThis.fetch=original;}
});
test('dispatch only V2 in active window, HTTP 204 is acceptance only',async()=>{
 const original=globalThis.fetch;let requests=0;
 globalThis.fetch=async(url,options)=>{
  requests++;if(requests===1)return{ok:true,text:async()=>calendar};
  assert.equal(url,'https://api.github.com/repos/warehousegang/fourth-down/actions/workflows/v2-shadow.yml/dispatches');
  assert.deepEqual(JSON.parse(options.body),{ref:'main'});return{status:204};
 };
 try{await worker.scheduled(event,{ENABLED:'true',ACTIVATION_AT:activation,GITHUB_TOKEN:'synthetic-test-only'});assert.equal(requests,2);}
 finally{globalThis.fetch=original;}
});
test('calendar quoted fields, day-independent boundaries, DST and odd minutes',()=>{
 const rows=csv(calendar);assert.equal(rows[0].venue,'Quoted, Stadium');
 for(const kickoff of ['2026-10-30T00:15:00Z','2026-11-01T14:30:00Z','2026-11-01T18:00:00Z','2026-11-03T01:15:00Z','2026-11-04T22:37:00Z']){
   rows[0].game_time=kickoff;const t=Date.parse(kickoff)-3600000;
   assert.equal(due(rows,t-1800000,Date.parse(activation)),true);
   assert.equal(due(rows,t+900000,Date.parse(activation)),true);
   assert.equal(due(rows,t+900001,Date.parse(activation)),false);
 }
 rows[0].game_time='';assert.equal(due(rows,event.scheduledTime,Date.parse(activation)),false);
 assert.throws(()=>due([{...rows[0],season:'2025'}],event.scheduledTime,Date.parse(activation)),/season/);
 assert.throws(()=>csv('season,season_type,game_time,phase\n2026,REG,"broken'),/Unclosed/);
});
test('daily recovery sweep, no requests to dispatch outside game windows',async()=>{
 assert.equal(due([],Date.parse('2026-11-03T11:00:00Z'),Date.parse(activation)),true);
 const original=globalThis.fetch;let calls=0;globalThis.fetch=async()=>{calls++;return{ok:true,text:async()=>calendar};};
 try{await worker.scheduled({scheduledTime:Date.parse('2026-11-03T12:00:00Z')},{ENABLED:'true',ACTIVATION_AT:activation});assert.equal(calls,1);}
 finally{globalThis.fetch=original;}
});
test('upstream and dispatch failures remain errors',async()=>{
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async()=>({ok:false,status:503});await assert.rejects(()=>worker.scheduled(event,{ENABLED:'true'}),/503/);
  let calls=0;globalThis.fetch=async()=>++calls===1?{ok:true,text:async()=>calendar}:{status:403};
  await assert.rejects(()=>worker.scheduled(event,{ENABLED:'true',ACTIVATION_AT:activation,GITHUB_TOKEN:'synthetic-test-only'}),/403/);
 }finally{globalThis.fetch=original;}
});
