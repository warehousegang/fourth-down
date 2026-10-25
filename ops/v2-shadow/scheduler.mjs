// Inactive preparation. Separate Worker; public V1 scheduler stays untouched.
const URL='https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nfl_ngs_schedules/ngs_schedule_2026.csv';
export function csv(text) {
  const rows=[];let row=[],field='',quoted=false;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"') {if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}
    else if(c===','&&!quoted){row.push(field);field='';}
    else if(c==='\n'&&!quoted){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}
    else field+=c;
  }
  if(quoted)throw new Error('Unclosed calendar field');
  if(field||row.length){row.push(field.replace(/\r$/,''));rows.push(row);}
  const headers=rows.shift();
  if(!['season','season_type','game_time','phase'].every(k=>headers.includes(k))) throw new Error('Missing calendar columns');
  return rows.filter(r=>r.some(Boolean)).map(r=>{
    if(r.length!==headers.length)throw new Error('Malformed calendar row');
    return Object.fromEntries(headers.map((k,i)=>[k,r[i]]));
  });
}
export function due(rows, now, activation) {
  if(rows.some(r=>r.season!=='2026'))throw new Error('Wrong calendar season');
  if(!Number.isFinite(activation))throw new Error('Missing activation boundary');
  if(now<activation)return false;
  // Daily coverage/recovery sweep also records misses and source outages.
  const utc=new Date(now);if(utc.getUTCHours()===11&&utc.getUTCMinutes()<5)return true;
  return rows.some(r=>{
    const kickoff=Date.parse(r.game_time), cutoff=kickoff-3600000;
    return r.season_type==='REG'&&['','SCHEDULED','PREGAME','PRE_GAME'].includes(r.phase.toUpperCase())&&
      Number.isFinite(kickoff)&&cutoff>activation&&now>=cutoff-1800000&&now<=cutoff+900000;
  });
}
export default {
  async scheduled(event, env) {
    if(env.ENABLED!=='true'){console.log('v2-shadow-disabled');return;}
    const calendar=await fetch(URL,{headers:{'User-Agent':'FourthDown-V2-calendar','Cache-Control':'no-cache'}});
    if(!calendar.ok)throw new Error(`Calendar unavailable (${calendar.status}); no false capture`);
    const text=await calendar.text();if(text.length>2000000)throw new Error('Calendar size limit');
    if(!due(csv(text),event.scheduledTime,Date.parse(env.ACTIVATION_AT)))return;
    const response=await fetch('https://api.github.com/repos/warehousegang/fourth-down/actions/workflows/v2-shadow.yml/dispatches',{
      method:'POST',headers:{Authorization:`Bearer ${env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json',
        'User-Agent':'FourthDown-V2-Shadow','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
      body:JSON.stringify({ref:'main'})
    });
    console.log(JSON.stringify({scheduled_at:event.scheduledTime,status:response.status,accepted:response.status===204}));
    if(response.status!==204)throw new Error(`V2 dispatch rejected (${response.status})`);
  },
  async fetch(){return new Response('V2 shadow scheduler has no public dispatch endpoint',{status:404});}
};
