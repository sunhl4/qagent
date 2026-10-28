import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

// Optional live test: uses the existing authenticated DSH UI, never a second
// model loop. A model request is made ONLY with COMPANY_UI_SEND_MODEL_PROBE=1.
const runtimeLog=process.env.COMPANY_UI_RUNTIME_LOG;
const launch=process.env.COMPANY_UI_URL ?? (runtimeLog
  ? (await readFile(runtimeLog,'utf8')).match(/http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9_-]+/)?.[0]
  : undefined);
if(!launch || !/^http:\/\/127\.0\.0\.1:\d+\/\?token=[A-Za-z0-9_-]+$/.test(launch) || !process.env.COMPANY_UI_PLAYWRIGHT){
  throw new Error('Set COMPANY_UI_URL or COMPANY_UI_RUNTIME_LOG and COMPANY_UI_PLAYWRIGHT');
}
const {chromium}=await import(pathToFileURL(process.env.COMPANY_UI_PLAYWRIGHT).href);
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:1600,height:1000}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const catalogResponse=page.waitForResponse(res=>res.url().endsWith('/api/session/modelCatalog'));
  await page.goto(launch);
  await page.locator('[data-company-shell]').waitFor({timeout:20000});
  const catalog=(await (await catalogResponse).json()).result;
  assert.equal(catalog.ok,true);
  const relay=catalog.value.groups.find(group=>group.id==='company-relay');
  assert.ok(relay?.models.length,'The native picker must advertise company-relay models');
  assert.ok(catalog.value.routableProviders.includes('company-relay'));
  assert.equal(catalog.value.failures.some(f=>f.id==='company-relay'),false);
  let discoveryMatched=false;
  if(process.env.COMPANY_UI_VERIFY_DISCOVERY==='1'){
    // Explicit opt-in endpoint read. Compare live discovery with the picker,
    // rather than hard-coding a model family or silently accepting a subset.
    const discovered=await page.evaluate(async()=>{
      const rpc=async(method,args)=>{
        const response=await fetch('/api/'+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:crypto.randomUUID(),method,payload:{args}})});
        const result=(await response.json()).result;
        if(!result.ok)throw new Error(result.error.code);
        return result.value;
      };
      const settings=await rpc('settings/describe',{});
      const profile=settings.namespaces.find(ns=>ns.ns==='llm-pi-ai').value.providers['company-relay'];
      return rpc('llm/discoverModels',{settingsNs:'llm-pi-ai',request:{provider:'company-relay',baseURL:profile.baseURL,api:profile.api}});
    });
    assert.deepEqual(relay.models.map(row=>row.id).sort(),discovered.map(row=>row.id).sort(),
      'The native relay catalog must include every currently authorized discovered model');
    discoveryMatched=true;
  }
  const notice=page.getByRole('button',{name:/^(Continue|继续)$/});
  if(await notice.isVisible())await notice.click();
  const later=page.getByRole('button',{name:/^(Configure later|稍后配置)$/});
  await later.waitFor({state:'visible',timeout:1500}).catch(()=>{});
  if(await later.isVisible())await later.click();
  await page.getByRole('button',{name:/^(New session|新建会话)$/}).click();
  const trigger=page.getByRole('button',{name:/^Select model|^选择模型/});
  await trigger.waitFor();
  await trigger.click();
  await page.getByRole('menuitem',{name:/^Model|^模型/}).click();
  const menu=page.getByRole('menu',{name:/Model and reasoning effort|模型与推理等级/});
  const group=menu.getByRole('group',{name:relay.name,exact:true});
  for(const model of relay.models){
    const option=group.getByRole('menuitemradio',{name:model.name,exact:true});
    await option.scrollIntoViewIfNeeded();
    assert.equal(await option.isVisible(),true);
  }
  const model=process.env.COMPANY_UI_TEST_MODEL ?? relay.models[0].id;
  const selectedModel=relay.models.find(row=>row.id===model);
  assert.ok(selectedModel,'The test model must come from the live catalog');
  const choice=group.getByRole('menuitemradio',{name:selectedModel.name,exact:true});
  const alreadySelected=await choice.getAttribute('aria-checked')==='true';
  const selectionResponse=alreadySelected ? null : page.waitForResponse(res=>res.url().endsWith('/api/session/selectModel'));
  await choice.click();
  if(selectionResponse){
    const selected=(await (await selectionResponse).json()).result;
    assert.equal(selected.ok,true);
    assert.equal(selected.value.selected.provider,'company-relay');
    assert.equal(selected.value.selected.model,model);
  }
  await page.getByRole('button',{name:new RegExp(`^(Select model|选择模型).*${model.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}`)}).waitFor();
  const replyMarker=process.env.COMPANY_UI_REPLY_MARKER ?? 'RELAY_CONNECTION_OK';
  if(!/^[A-Z][A-Z0-9_]{0,63}$/.test(replyMarker))throw new Error('Use a short uppercase test-reply marker');
  let replyVerified=false;
  if(process.env.COMPANY_UI_SEND_MODEL_PROBE==='1'){
    const editor=page.locator('[contenteditable=true]').first();
    await editor.fill(`This is a connection test. Do not call any tools. Reply with exactly ${replyMarker}.`);
    const admittedResponse=page.waitForResponse(res=>res.url().endsWith('/api/session/prompt'));
    await page.getByRole('button',{name:/^(Send message|发送消息|发送)$/}).click();
    const admitted=(await (await admittedResponse).json()).result;
    assert.equal(admitted.ok,true);
    assert.equal(admitted.value.accepted,true);
    await page.getByText(replyMarker,{exact:true}).waitFor({timeout:90000});
    replyVerified=true;
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',provider:'company-relay',models:relay.models.map(row=>row.id),discoveryMatched,selected:model,replyVerified},null,2));
}finally{
  await browser.close();
}
