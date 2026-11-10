import assert from 'node:assert/strict';
import test from 'node:test';
import {spawnSync} from 'node:child_process';
import {Readable} from 'node:stream';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import http from 'node:http';
import {Writable} from 'node:stream';
import {apply, projectAutomation, projectHpcFiles, projectSacctLine, projectSqueueLine, projectWorkbenchTasks, restoreWorkbenchTasks, resolveTrustedSubject, scopedFactKey, workbenchEventRank, workbenchTaskFromEvent} from '../../apps/company-workspace/host.mjs';

async function host(port, options = {}){
 // Explicit per-test port: ambient COMPANY_AGENT_DSH_PORT from developer
 // shells must never decide the trusted origin under test.
 if(port !== undefined) process.env.COMPANY_AGENT_DSH_PORT = port;
 const routes=new Map();let tap;
 const authorizeIndex = options.open
  ? () => true
  : (req, res) => {if(String(req.headers.cookie||'').split(';').some(part=>part.trim()==='fixture'))return true;res.writeHead(401);res.end();return false;};
 const ctx={effect:fn=>fn(),workspaceRegistry:{list:()=>[]},connection:{authorizeIndex},webServer:{register:route=>{routes.set(route.path,route.handler);return()=>routes.delete(route.path);},tapIndex:fn=>{tap=fn;return()=>{};}}};
 await apply(ctx);return{routes,tap};
}
function response(){return{status:0,headers:{},body:'',writeHead(status,headers={}){this.status=status;this.headers=headers;},end(body=''){this.body=body;}};}
function streamingResponse(){
 const chunks=[];let status=0,headers={};
 const result=new Writable({write(chunk,_encoding,callback){chunks.push(Buffer.from(chunk));callback();}});
 result.writeHead=(nextStatus,nextHeaders={})=>{status=nextStatus;headers=nextHeaders;};
 const end=result.end.bind(result);result.end=body=>{if(body!==undefined)chunks.push(Buffer.from(body));end();};
 result.result=()=>({status,headers,body:Buffer.concat(chunks).toString()});
 return result;
}

test('account route returns only the desktop display name',async()=>{
 const previous=process.env.COMPANY_AGENT_ACCOUNT_NAME;
 process.env.COMPANY_AGENT_ACCOUNT_NAME='alice';
 try{
  const {routes}=await host('3081');
  const res=response();
  await routes.get('/company-workspace/account')({method:'GET',headers:{host:'127.0.0.1:3081',cookie:'fixture'}},res);
  assert.equal(res.status,200);
  assert.deepEqual(JSON.parse(res.body),{username:'alice'});
 }finally{
  if(previous===undefined)delete process.env.COMPANY_AGENT_ACCOUNT_NAME;
  else process.env.COMPANY_AGENT_ACCOUNT_NAME=previous;
 }
});

test('automation route fails closed without the company python', async () => {
 const previous = process.env.COMPANY_AGENT_PYTHON;
 delete process.env.COMPANY_AGENT_PYTHON;
 try {
  const {routes} = await host('3081');
  const res = response();
  await routes.get('/company-workspace/automation')({method:'GET', headers:{host:'127.0.0.1:3081', cookie:'fixture'}}, res);
  assert.equal(res.status, 200);
  assert.deepEqual(JSON.parse(res.body), {available:false, items:[], observed:0, reason:'unconfigured'});
 } finally {
  if (previous === undefined) delete process.env.COMPANY_AGENT_PYTHON;
  else process.env.COMPANY_AGENT_PYTHON = previous;
 }
});

test('automation projection keeps short ticket fields', () => {
 const ticket = 'tic_' + 'ab'.repeat(16);
 const projected = projectAutomation({
  available: true,
  observed: 2,
  truncated: false,
  items: [{
   ticket_id: ticket,
   title: 'Visible',
   state: 'open',
   mandate: 'lab',
   execution_state: 'running',
   session_ref: 'dsh:session-1',
   created_at: '2026-11-09T12:00:00Z',
   text: 'secret trigger body',
  }, {ticket_id: 'tic_short', title: 'Hidden', state: 'open', mandate: 'lab'}],
 });
 assert.equal(projected.available, true);
 assert.equal(projected.observed, 2);
 assert.deepEqual(projected.items, [{
  ticket_id: ticket,
  title: 'Visible',
  state: 'open',
  mandate: 'lab',
  execution_state: 'running',
  session_ref: 'dsh:session-1',
  created_at: '2026-11-09T12:00:00Z',
 }]);
 assert.equal(JSON.stringify(projected).includes('secret'), false);
 assert.equal(projectAutomation(null).reason, 'unavailable');
});

test('access seam keeps its documented client-facing envelope',async()=>{
 const {routes}=await host('3081');
 const res=response();await routes.get('/company-workspace/access')({method:'GET',headers:{host:'127.0.0.1:3081',cookie:'fixture'}},res);
 assert.equal(res.status,200);
 const body=JSON.parse(res.body);
 assert.deepEqual(Object.keys(body).sort(),['cloud','hpc','requests']);
 for(const kind of ['cloud','hpc']){
  assert.deepEqual(Object.keys(body[kind]),['open']);
  assert.equal(typeof body[kind].open,'boolean');
 }
 assert.ok(Array.isArray(body.requests));
 // Envelope is the documented access-seam contract (docs/company-workspace-access-seam.zh-CN.md):
 // changing it is a contract-level change and must update the seam doc, the Plugins
 // settings page consumer, and this pin together.
 assert.match(res.headers['content-type'],/application\/json/);
});

test('UI assets require native auth and exact trusted origin',async()=>{
 const {routes}=await host('3081');
 for(const handler of routes.values()){
  for(const headers of [{host:'evil.example',cookie:'fixture'},{host:'127.0.0.1:3081',origin:'https://evil.example',cookie:'fixture'},{host:'127.0.0.1:3081','sec-fetch-site':'cross-site',cookie:'fixture'}]){
   const res=response();handler({method:'GET',headers},res);assert.equal(res.status,403);
  }
  const res=response();handler({method:'GET',headers:{host:'127.0.0.1:3081'}},res);assert.equal(res.status,401);
 }
 const res=response();routes.get('/company-workspace/content')({method:'GET',headers:{host:'127.0.0.1:3081',cookie:'fixture'}},res);
 assert.equal(res.status,200);assert.doesNotMatch(res.body,/<iframe id="dsh-native-frame"/);assert.match(res.body,/content-embed/);
 assert.doesNotMatch(res.body,/220\.178\.61\.185/);assert.doesNotMatch(res.body,/192\.168\.110\.37/);assert.doesNotMatch(res.body,/connectionUrls/);
 assert.match(res.body,/\/company-workspace\/workbench\/tasks/);
 assert.match(res.body,/空列表不当成没有任务/);
 assert.match(res.body,/not_projected/);
 assert.match(res.body,/event.origin!==location.origin/);assert.match(res.body,/event.source!==parent/);
});

test('custom loopback port keeps exact Host and Origin checks',async()=>{
 const previous=process.env.COMPANY_AGENT_DSH_PORT;
 let routes;
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3084';
  ({routes}=await host('3084'));
 }finally{
  if(previous===undefined)delete process.env.COMPANY_AGENT_DSH_PORT;
  else process.env.COMPANY_AGENT_DSH_PORT=previous;
 }
 const handler=routes.get('/company-workspace/workspace.css');
 const allowed=response();
 handler({method:'GET',headers:{host:'127.0.0.1:3084',origin:'http://127.0.0.1:3084',cookie:'fixture'}},allowed);
 assert.equal(allowed.status,200);
 for(const headers of [
  {host:'127.0.0.1:3081',cookie:'fixture'},
  {host:'127.0.0.1:3084',origin:'http://127.0.0.1:3081',cookie:'fixture'},
  {host:'127.0.0.1:3084',origin:'https://evil.example',cookie:'fixture'},
  {host:'127.0.0.1:3084','sec-fetch-site':'cross-site',cookie:'fixture'},
 ]){
  const res=response();handler({method:'GET',headers},res);assert.equal(res.status,403);
 }
 const unauthenticated=response();
 handler({method:'GET',headers:{host:'127.0.0.1:3084'}},unauthenticated);
 assert.equal(unauthenticated.status,401);
});

test('invalid configured loopback ports fail before mounting routes',async()=>{
 const previous=process.env.COMPANY_AGENT_DSH_PORT;
 try{
  for(const port of ['', '0', '65536', '3084/path', 'evil.example']){
   process.env.COMPANY_AGENT_DSH_PORT=port;
   await assert.rejects(host(),/COMPANY_AGENT_DSH_PORT/);
  }
 }finally{
  if(previous===undefined)delete process.env.COMPANY_AGENT_DSH_PORT;
  else process.env.COMPANY_AGENT_DSH_PORT=previous;
 }
});

test('host serves data routes and does not append a second client',async()=>{
 const {tap,routes}=await host('3081');
 assert.equal(tap, undefined);
 assert.equal(routes.has('/company-workspace/client.js'), false);
 assert.equal(typeof routes.get('/company-workspace/account'), 'function');
});

test('workbench task projection is auth-gated and reads one reconciled server fact source',async()=>{
 const previous={python:process.env.COMPANY_AGENT_PYTHON,port:process.env.COMPANY_AGENT_DSH_PORT};
 const dir=await mkdtemp(join(tmpdir(),'unitqc-workbench-'));
 const fakePython=join(dir,'fake-python.mjs');
 await writeFile(fakePython,``, 'utf8');
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3097';
  process.env.COMPANY_AGENT_PYTHON=process.execPath;
  const {routes}=await host('3097');
  const handler=routes.get('/company-workspace/workbench/tasks');
  assert.ok(handler);
  const unauth=response();await handler({method:'GET',headers:{host:'127.0.0.1:3097'}},unauth);assert.equal(unauth.status,401);
  // The real CLI is intentionally unavailable in this fixture; the endpoint must
  // report unavailable rather than manufacture an empty successful task list.
  const unavailable=response();await handler({method:'GET',headers:{host:'127.0.0.1:3097',cookie:'fixture'}},unavailable);
  assert.equal(unavailable.status,200);
  assert.deepEqual(JSON.parse(unavailable.body),{available:false,tasks:[],reason:'receipt_unavailable'});
 }finally{
  await rm(dir,{recursive:true,force:true});
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
 }
});

test('workbench projection keeps unknown outcomes and only completes with a platform reference',()=>{
 const request='req_'+'a'.repeat(32);
 const rows=projectWorkbenchTasks([
  {record:'outcome',request_id:request,operation:'hpc.submit',status:'ok',execution_state:'completed',business_ref:'',timestamp:30},
  {record:'dispatch',request_id:request,operation:'hpc.submit',status:'dispatched',execution_state:'dispatched',business_ref:'',timestamp:20},
  {record:'outcome',request_id:request,operation:'hpc.submit',status:'error',execution_state:'unknown',business_ref:'',timestamp:40},
  {record:'outcome',request_id:'req_'+'b'.repeat(32),operation:'cloud.submit',status:'ok',execution_state:'completed',business_ref:'cloud-task-7',timestamp:10},
  {record:'outcome',request_id:'req_'+'c'.repeat(32),operation:'device.run',status:'ok',execution_state:'completed',business_ref:'twin_9',timestamp:9},
  {record:'outcome',request_id:'req_'+'d'.repeat(32),operation:'knowledge.search',status:'ok',execution_state:'completed',business_ref:'ignored',timestamp:99},
 ]);
 assert.deepEqual(rows.map(row=>row.request_id),['req_'+'a'.repeat(32),'req_'+'b'.repeat(32),'req_'+'c'.repeat(32)]);
 assert.equal(rows[0].status,'unknown');assert.equal(rows[0].result_state,'unknown');assert.equal(rows[0].business_ref,'');
 assert.equal(rows[1].status,'completed');assert.equal(rows[1].business_ref,'cloud-task-7');
 assert.equal(rows[2].status,'completed');assert.equal(rows[2].business_ref,'twin_9');
 assert.ok(rows.every(row=>row.billing_state==='not_projected'));
});


test('invalid workbench event states fail closed',()=>{
 assert.equal(workbenchEventRank({record:'outcome',status:'ok',execution_state:'unknown'}),-1);
 assert.equal(workbenchEventRank({record:'dispatch',status:'ok',execution_state:'completed'}),-1);
 assert.equal(workbenchTaskFromEvent({record:'outcome',request_id:'req_'+'a'.repeat(32),operation:'hpc.submit',status:'refused',execution_state:'dispatched',timestamp:1}).status,'refused');
});

test('workbench projection rejects stale, malformed and duplicate events, and restores disconnected facts',()=>{
 const request='req_'+'e'.repeat(32);
 const completed={record:'outcome',request_id:request,operation:'cloud.submit',status:'ok',execution_state:'completed',business_ref:'cloud-task-1',timestamp:50};
 const rows=projectWorkbenchTasks([
  completed,
  {...completed,timestamp:50},
  {record:'outcome',request_id:request,operation:'cloud.submit',status:'error',execution_state:'unknown',business_ref:'',timestamp:49},
  {record:'dispatch',request_id:request,operation:'cloud.submit',status:'dispatched',execution_state:'dispatched',business_ref:'',timestamp:20},
  {record:'outcome',request_id:request,operation:'cloud.submit',status:'ok',execution_state:'completed',business_ref:'bad ref!',timestamp:60},
  {record:'outcome',request_id:'req_'+'f'.repeat(32),operation:'cloud.submit',status:'ok',execution_state:'completed',business_ref:'cloud-task-2',timestamp:61},
  {record:'outcome',request_id:'forged',operation:'cloud.submit',status:'ok',execution_state:'completed',business_ref:'cloud-task-3',timestamp:99},
 ]);
 assert.deepEqual(rows.map(row=>row.request_id),['req_'+'f'.repeat(32),request]);
 assert.equal(rows[1].status,'unknown');
 assert.equal(rows[0].connection_state,'server_facts');
 const restored=restoreWorkbenchTasks({tasks:[{...rows[0],connection_state:'server_facts'}],active:true},[],{});
 assert.equal(restored[0].connection_state,'reconnecting');
 assert.equal(restored[0].source,'server-facts-reconnect');
});

test('trusted subject and cache keys are server-derived and tenant-scoped',()=>{
 const connection={subjectForRequest:req=>req.headers.subject};
 const req={headers:{subject:'operator@corp.example.com'}};
 assert.equal(resolveTrustedSubject(connection,req),'operator@corp.example.com');
 assert.equal(resolveTrustedSubject(connection,{headers:{subject:'../../guest'}}),'unknown@unknown');
 assert.equal(scopedFactKey('agent-state','operator@corp.example.com'),'agent-state:operator@corp.example.com');
 assert.notEqual(scopedFactKey('agent-state','operator@corp.example.com'),scopedFactKey('agent-state','guest@corp.example.com'));
});


test('portal proxy embeds configured pages and isolates portal cookies from Agent auth',async()=>{
 const previous={port:process.env.COMPANY_AGENT_DSH_PORT,config:process.env.UQC_WORKSPACE_CONFIG,hpc:process.env.HPC_PORTAL};
 const upstream=http.createServer((req,res)=>{
  if(req.url==='/'){
   res.setHeader('content-type','text/html');res.setHeader('set-cookie','SESSIONID=portal-secret; Path=/; HttpOnly');
   res.end('<meta charset="utf-8"/><script src="/app.js"></script><form action="/login" method="post"></form><a href="/next">next</a>');return;
  }
  if(req.url==='/app.js'){
   if(req.headers.cookie!=='SESSIONID=portal-secret'){res.statusCode=404;res.end('missing cookie');return;}
   res.setHeader('content-type','text/javascript');res.end('window.portalReady=true');return;
  }
  if(req.url==='/flags.js'){
   res.setHeader('content-type','text/javascript');res.end('s.replace(/"/g,"&quot;");var root="/"+file;var logo="/logo.png";');return;
  }
  if(req.url==='/login'&&req.method==='POST'){
   let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{res.setHeader('content-type','text/plain');res.end(JSON.stringify({body,cookie:req.headers.cookie||''}));});return;
  }
  res.statusCode=404;res.end('missing');
 });
 await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3099';process.env.UQC_WORKSPACE_CONFIG='/tmp/unitqc-proxy-test-missing.json';process.env.HPC_PORTAL=`http://127.0.0.1:${upstream.address().port}`;
  const {routes}=await host('3099');const handler=routes.get('/company-workspace/portal/hpc');assert.ok(handler);
  const page=streamingResponse();await handler({method:'GET',url:'/company-workspace/portal/hpc/',headers:{host:'127.0.0.1:3099',cookie:'fixture'}},page);await new Promise(resolve=>setTimeout(resolve,30));
  const pageResult=page.result();assert.equal(pageResult.status,200);assert.match(pageResult.body,/\/company-workspace\/portal\/hpc\/app\.js/);assert.match(pageResult.body,/\/company-workspace\/portal\/hpc\/login/);assert.match(pageResult.body,/<meta charset="utf-8"\/>/);assert.doesNotMatch(pageResult.body,/utf-8"\/company-workspace/);assert.match(pageResult.headers['set-cookie'][0],/^UQC_PORTAL_HPC_SESSIONID=/);
  const script=streamingResponse();await handler({method:'GET',url:'/company-workspace/portal/hpc/app.js',headers:{host:'127.0.0.1:3099',cookie:'fixture'}},script);await new Promise(resolve=>setTimeout(resolve,30));
  const scriptResult=script.result();assert.equal(scriptResult.status,200);assert.equal(scriptResult.body,'window.portalReady=true');
  const flags=streamingResponse();await handler({method:'GET',url:'/company-workspace/portal/hpc/flags.js',headers:{host:'127.0.0.1:3099',cookie:'fixture'}},flags);await new Promise(resolve=>setTimeout(resolve,30));
  const flagsResult=flags.result();assert.equal(flagsResult.status,200);assert.match(flagsResult.body,/\/"\/g/);assert.match(flagsResult.body,/\/company-workspace\/portal\/hpc\/"\+file/);assert.match(flagsResult.body,/\/company-workspace\/portal\/hpc\/logo\.png/);
  const post=streamingResponse();const {Readable}=await import('node:stream');const request=Readable.from([Buffer.from('username=a')]);request.method='POST';request.url='/company-workspace/portal/hpc/login';request.headers={host:'127.0.0.1:3099',cookie:'fixture; dsh-auth=agent-secret; UQC_PORTAL_HPC_SESSIONID=portal-secret','content-type':'application/x-www-form-urlencoded','content-length':'10'};await handler(request,post);await new Promise(resolve=>setTimeout(resolve,30));
  const postResult=post.result();assert.equal(postResult.status,200);const seen=JSON.parse(postResult.body);assert.equal(seen.body,'username=a');assert.equal(seen.cookie,'SESSIONID=portal-secret');
 }finally{
  await new Promise(resolve=>upstream.close(resolve));
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
 }
});
test('portal proxy remembers a session when the desktop cannot store cookies',async()=>{
 const previous=process.env.HPC_PORTAL;
 const upstream=http.createServer((req,res)=>{
  if(req.url==='/'){
   res.setHeader('content-type','text/html');res.setHeader('set-cookie','SESSIONID=portal-secret; Path=/; HttpOnly');
   res.end('<script src="/app.js"></script>');return;
  }
  if(req.url==='/app.js'){
   if(req.headers.cookie!=='SESSIONID=portal-secret'){res.statusCode=404;res.end('missing cookie');return;}
   res.setHeader('content-type','text/javascript');res.end('window.portalReady=true');return;
  }
  res.statusCode=404;res.end('missing');
 });
 await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3102';process.env.HPC_PORTAL=`http://127.0.0.1:${upstream.address().port}`;
  const {routes}=await host('3102',{open:true});const handler=routes.get('/company-workspace/portal/hpc');
  const page=streamingResponse();await handler({method:'GET',url:'/company-workspace/portal/hpc/',headers:{host:'127.0.0.1:3102'}},page);await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(page.result().status,200);
  const script=streamingResponse();await handler({method:'GET',url:'/company-workspace/portal/hpc/app.js',headers:{host:'127.0.0.1:3102'}},script);await new Promise(resolve=>setTimeout(resolve,30));
  assert.equal(script.result().status,200);assert.equal(script.result().body,'window.portalReady=true');
 }finally{
  await new Promise(resolve=>upstream.close(resolve));
  if(previous===undefined)delete process.env.HPC_PORTAL;else process.env.HPC_PORTAL=previous;
 }
});
test('grant is token-only and settings never accept credentials',async()=>{
 const envKeys=['UQC_WORKSPACE_CONFIG','COMPANY_AGENT_DSH_PORT','HPC_PORTAL','HPC_GATEWAY','HPC_JOBS_URL','HPC_TOKEN','HPC_USER','HPC_HOST','UQC_CLOUD_API_KEY','UQC_CLOUD_API_BASE_URL','UQC_CLOUD_PORTAL'];
 const previous=Object.fromEntries(envKeys.map(key=>[key,process.env[key]]));
 for(const key of envKeys)delete process.env[key];
 const dir=await mkdtemp(join(tmpdir(),'unitqc-seam-grant-'));
 // Pre-seed the admin secret so the token used below is deterministic.
 await writeFile(join(dir,'admin-token'),'grant-test-token-42\n',{mode:0o600});
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3098';
  process.env.UQC_WORKSPACE_CONFIG=join(dir,'workspace.json');
  const {routes}=await host('3098');
  const unset=response();
  await routes.get('/company-workspace/settings')({method:'GET',headers:{host:'127.0.0.1:3098',cookie:'fixture'}},unset);
  assert.equal(JSON.parse(unset.body).cloudApi,'');
  const post=(path,payload,headers={})=>{
   const request=Readable.from([Buffer.from(JSON.stringify(payload))]);
   request.method='POST';request.url=path;request.headers={host:'127.0.0.1:3098',cookie:'fixture','content-type':'application/json',...headers};
   const result=streamingResponse();
   return routes.get(path)(request,result).then(()=>new Promise(resolve=>setTimeout(()=>resolve(result.result()),20)));
  };
  // §2: grant sits outside the browser-session seat — a valid session cookie
  // and no/incorrect admin token must be refused, so signed-in users cannot
  // self-grant or inject credentials.
  const noToken=await post('/company-workspace/access/grant',{kind:'cloud'});
  assert.equal(noToken.status,401);assert.equal(noToken.body,'{"error":"unauthorized"}');
  const wrongToken=await post('/company-workspace/access/grant',{kind:'cloud'},{'x-admin-token':'forged'});
  assert.equal(wrongToken.status,401);
  const granted=await post('/company-workspace/access/grant',{kind:'cloud',cloudKey:'sk-grant-test'},{'x-admin-token':'grant-test-token-42'});
  assert.equal(granted.status,200);
  const grantBody=JSON.parse(granted.body);
  assert.deepEqual(Object.keys(grantBody).sort(),['granted','ok']);
  assert.deepEqual(Object.keys(grantBody.granted).sort(),['kind','open','requestsUpdated']);
  // Credentials cannot enter through the ordinary settings POST (§2:
  // non-sensitive fields only); the grant path is the sole credential write-in.
  const cred=await post('/company-workspace/settings',{cloudKey:'sk-should-fail'});
  assert.equal(cred.status,400);assert.match(cred.body,/凭据由服务端统一注入/);
  const plain=await post('/company-workspace/settings',{cloudApi:'http://127.0.0.1:8003'});
  assert.equal(plain.status,200);
  const plainBody=JSON.parse(plain.body);
  // §2非敏感视图: booleans/addresses only — the credential itself and its env
  // origin must never appear, under any ambient configuration.
  assert.equal(plainBody.cloudKeySet,true);
  assert.equal(plainBody.cloudApi,'http://127.0.0.1:8003');
  assert.equal(plainBody.cloudPortal,'');
  assert.equal(plainBody.hpcPortal,'');
  const missing=streamingResponse();
  await routes.get('/company-workspace/portal/cloud')({method:'GET',url:'/company-workspace/portal/cloud/',headers:{host:'127.0.0.1:3098',cookie:'fixture'}},missing);
  assert.equal(missing.result().status,404);
  assert.equal(missing.result().body,'portal not configured');
  assert.deepEqual(Object.keys(plainBody).sort(),['cloudApi','cloudKeySet','cloudPortal','hpcHost','hpcPortal','hpcUser','note'].sort());
  // The granted credential itself must never be echoed back in any field.
  assert.ok(!JSON.stringify(plainBody).includes('sk-grant-test'));
 }finally{
  // Async server writes (config/access ledgers) may still be settling; give
  // them a beat, then remove the workspace dir with retries.
  await new Promise(resolve=>setTimeout(resolve,150));
  for(let attempt=0;attempt<5;attempt+=1){
   try{await rm(dir,{recursive:true,force:true});break;}
   catch(error){if(attempt===4)throw error;await new Promise(resolve=>setTimeout(resolve,120));}
  }
  for(const [key,value] of Object.entries(previous)){if(value===undefined)delete process.env[key];else process.env[key]=value;}
 }
});
test('presentation overlay cannot activate in production or device profile',()=>{
 const gate = /Workspace demo UI requires development with company-agent-minimal \(boot\|algo\) or company-agent \(lab\|sign\)/;
 const dshCli=new URL('../../scripts/dsh-cli.mjs',import.meta.url);
 const dshCliPath=process.platform==='win32'&&dshCli.pathname.startsWith('/')?decodeURIComponent(dshCli.pathname.slice(1)):decodeURIComponent(dshCli.pathname);
 const result=spawnSync(process.execPath,[dshCliPath],{env:{PATH:process.env.PATH,COMPANY_AGENT_DEPLOYMENT_MODE:'production',COMPANY_AGENT_PROFILE:'company-agent-minimal',COMPANY_AGENT_PRESET:'boot',COMPANY_AGENT_DEMO_UI:'1'},encoding:'utf8'});
 assert.notEqual(result.status,0);assert.match(result.stderr,gate);
 // The composed company-agent profile keeps the presentation shell in
 // development under its approval presets (lab/sign); the gate lets it through
 // to the next boot check instead.
 const allowed=spawnSync(process.execPath,[dshCliPath],{env:{PATH:process.env.PATH,COMPANY_AGENT_DEPLOYMENT_MODE:'development',COMPANY_AGENT_PROFILE:'company-agent',COMPANY_AGENT_PRESET:'lab',COMPANY_AGENT_DEMO_UI:'1'},encoding:'utf8'});
 assert.notEqual(allowed.status,0);assert.doesNotMatch(allowed.stderr,gate);assert.match(allowed.stderr,/COMPANY_AGENT_DSH_ENTRY/);
});
test('cloud probe does not bake a developer machine path', async () => {
 const {readFile} = await import('node:fs/promises');
 const text = await readFile(new URL('../../apps/company-workspace/host.mjs', import.meta.url), 'utf8');
 assert.equal(text.includes('/home/sunhl/'), false);
 assert.match(text, /UQC_CLOUD_PROBE_PYTHON/);
 assert.match(text, /python3/);
});
test('hpc projection keeps the job id and splits files on real lines',()=>{
 const row=projectSqueueLine('5010|train job|cpu|RUNNING|1:02|2026-11-09|2');
 assert.equal(row.job,'5010');
 assert.equal(row.name,'train job');
 assert.equal(row.nodes,'2');
 assert.equal(projectSacctLine('5010.batch|train|cpu|COMPLETED|1:00|t0|t1'),null);
 assert.deepEqual(projectHpcFiles('notes.txt\tf\nruns\td\n'),[{name:'notes.txt',kind:'file'},{name:'runs',kind:'directory'}]);
});
test('workspace route lists the registered directory and does not invent an empty root',async()=>{
 const previous=process.env.COMPANY_AGENT_DSH_PORT;
 const dir=await mkdtemp(join(tmpdir(),'unitqc-workspace-'));
 await writeFile(join(dir,'notes.txt'),'ok','utf8');
 try{
  process.env.COMPANY_AGENT_DSH_PORT='3098';
  const routes=new Map();
  const ctx={effect:fn=>fn(),workspaceRegistry:{list:()=>[{id:'ws-1',title:'项目',path:dir,sessionIds:['s1'],updatedAt:'2026-11-09'}]},connection:{authorizeIndex:(req,res)=>{if(String(req.headers.cookie||'').split(';').some(part=>part.trim()==='fixture'))return true;res.writeHead(401);res.end();return false;}},webServer:{register:route=>{routes.set(route.path,route.handler);return()=>routes.delete(route.path);},tapIndex:()=>{}}};
  await apply(ctx);
  const handler=routes.get('/company-workspace/workspace');
  assert.ok(handler);
  const unauth=response();
  await handler({method:'GET',headers:{host:'127.0.0.1:3098'}},unauth);
  assert.equal(unauth.status,401);
  const ok=response();
  await handler({method:'GET',url:'/company-workspace/workspace?path=..',headers:{host:'127.0.0.1:3098',cookie:'fixture'}},ok);
  assert.equal(ok.status,200);
  const body=JSON.parse(ok.body);
  assert.equal(body.ready,true);
  assert.equal(body.workspaces[0].path,dir);
  assert.ok(body.entries.some(entry=>entry.name==='notes.txt'&&entry.kind==='file'));
  assert.equal(body.entries.some(entry=>String(entry.name).includes('..')),false);
 }finally{
  await rm(dir,{recursive:true,force:true});
  if(previous===undefined)delete process.env.COMPANY_AGENT_DSH_PORT;
  else process.env.COMPANY_AGENT_DSH_PORT=previous;
 }
});
