import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const source=readFileSync(new URL('../../apps/company-workspace/layout-model.js',import.meta.url),'utf8');
let model;
vm.runInNewContext(source,{window:{__ModuleLoader__:{load:entry=>{model=entry.factory();}}}});
const plain=value=>JSON.parse(JSON.stringify(value));

test('layout restores only bounded sizes and never hides every panel',()=>{
 const fallback=model.restore(null);assert.equal(fallback.left,260);assert.equal(fallback.chat,580);
 const value=model.restore({left:-100,chat:Infinity,visible:{left:false,center:false,chat:false},focus:'invalid'});
 assert.equal(value.left,190);assert.equal(value.chat,580);assert.equal(value.visible.chat,true);
 let state=model.toggle(model.toggle(model.restore(null),'left'),'center');
 assert.equal(model.toggle(state,'chat'),state);
 assert.equal(model.toggle(state,'invalid'),state);
});

test('visible tracks fit all widths and narrow focus only shows one mounted region',()=>{
 for(const width of [0,390,768,899,900,1024,1440,1920])for(let mask=1;mask<8;mask++){
  const state=model.restore({visible:{left:!!(mask&1),center:!!(mask&2),chat:!!(mask&4)}});
  const layout=model.solve(state,width);
  assert.ok(layout.panels.length>0);
  const total=Object.values(layout.sizes).reduce((a,b)=>a+b,0)+(layout.panels.length-1)*6;
  assert.ok(Math.abs(total-width)<0.01);
  assert.ok(Object.values(layout.sizes).every(n=>Number.isFinite(n)&&n>=0));
  if(width<900)assert.equal(layout.panels.length,1);
 }
});

test('dragging adjusts the requested side and clamps to safe ranges',()=>{
 const state=model.restore(null),initial=model.solve(state,1600);
 const left=model.resize(state,'left',80,1600,initial);assert.equal(left.left,340);assert.equal(left.chat,state.chat);
 const right=model.resize(state,'chat',-90,1600,initial);assert.equal(right.chat,670);
 assert.equal(model.resize(state,'left',-9999,1600,initial).left,190);
 assert.equal(model.resize(state,'chat',9999,1600,initial).chat,320);
 assert.deepEqual(plain(model.resize(state,'chat',-50,390)),plain(state));
});

test('additive client rides native slots and never replaces the conversation shell',()=>{
 const client=readFileSync(new URL('../../apps/company-workspace/client.js',import.meta.url),'utf8');
 const host=readFileSync(new URL('../../apps/company-workspace/host.mjs',import.meta.url),'utf8');
 const css=readFileSync(new URL('../../apps/company-workspace/workspace.css',import.meta.url),'utf8');
 // Additive face: the module declares only shell-owned services; the native
 // conversation plugin is reached through a child scope so rc.3's
 // uiConversation→uiWorkspace ordering cannot couple this upgrade.
 assert.match(client,/inject:\['slots','locale','sidebarRightTabs'\]/);
 assert.match(client,/ctx\.inject\(\['uiConversation'\], scope=>registerReceiptView\(ctx, scope\.get\('uiConversation'\)\)\)/);
 assert.doesNotMatch(client,/inject:\[[^\]]*uiConversation/,'conversation plugin is resolved in a child scope, not a hard dependency');
 // Settings seats (platform section + General row) and the resource tab ride
 // native slots with the pinned identities the seam consumers rely on.
 assert.match(client,/name:'settings.section',id:'platform',order:12/);
 assert.match(client,/name:'settings.general.item',id:'platform-connections',order:25/);
 assert.match(client,/sidebarRightTabs\.register\(/);
 assert.match(client,/name:'sidebar\.right\.pane\.tab'/);
 // The replaced-shell era is gone: no custom root/sidebar frame, no local file
 // tree simulation, and no model/loop-facing client actions anywhere.
 assert.doesNotMatch(client,/name:'root'|name:'sidebar'|renderSlot\(/);
 assert.doesNotMatch(client,/本机文件|quantum-project/);
 assert.doesNotMatch(client,/\.sendMessage\(|\.runCli\(|innerHTML|contentDocument/);
 // The only client-service calls permitted are the read-only connection
 // status poll, the read-only agent-facts projection, the access-plan read
 // and the access-request POST; every other fetch stays forbidden.
 const sidebarFetches = client.match(/fetch\([^;]{0,120}/g) || [];
 assert.ok(sidebarFetches.length >= 1, 'sidebar keeps its status poll');
 const allowedFetches = [
  /\/company-workspace\/\$\{kind\}\/(?:status|overview)/,
  /\/company-workspace\/agent\/state'/,
  /\/company-workspace\/workbench\/tasks'/,
  /\/company-workspace\/access'\)/,
  /\/company-workspace\/access',\{method:'POST'/
 ];
 for (const sidebarFetch of sidebarFetches) {
   assert.ok(allowedFetches.some(allowed => allowed.test(sidebarFetch)), `allowed client-service fetch only: ${sidebarFetch}`);
 }
 assert.doesNotMatch(css,/pI_x6G|hHd-Xa|contenteditable|\.chat-head|\.assistant-message/);
 // Host side: session-gated routes and the boot composition stay read-only
 // additive — native boot entries must never be filtered or replaced here.
 assert.match(host,/authorizeIndex/);assert.match(host,/tapIndex/);
 assert.match(host,/Compose additively on top of the native shell/);
 assert.doesNotMatch(host,/REPLACED|entries\.filter/,'boot composition appends, it never removes native entries');
 assert.doesNotMatch(host,/res\.setHeader\(['"]Access-Control-Allow-Origin|shell:true/);
});
