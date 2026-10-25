// Small public scheduling hint; never forecast or evaluation evidence.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const data=fileURLToPath(new URL('../public/data/',import.meta.url));
const pointer=JSON.parse(readFileSync(data+'operations/latest.json','utf8'));
if(!/^operations-[a-f0-9]{64}\.json$/.test(pointer.file))throw new Error('Invalid operations pointer');
const raw=readFileSync(data+'operations/'+pointer.file);
if(createHash('sha256').update(raw).digest('hex')!==pointer.sha256)throw new Error('Operations checksum mismatch');
const ops=JSON.parse(raw);
if(ops.season<2026||ops.schedule.length>300||ops.schedule.some(g=>g.season!==ops.season))throw new Error('Invalid schedule season');
const hint={schema_version:1,season:ops.season,generated_at:ops.generated_at,operations_sha256:pointer.sha256,
  games:ops.schedule.map(({id,kickoff,status})=>({id,kickoff,status}))};
writeFileSync(data+'game-day.json',JSON.stringify(hint)+'\n');
