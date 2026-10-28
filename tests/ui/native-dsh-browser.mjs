import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';

// Real native UI checks. No messages are sent and no science tools are invoked.
const launch=process.env.COMPANY_UI_DEMO_URL;
if(!launch||!/^http:\/\/127\.0\.0\.1:\d+\/start\/[A-Za-z0-9_-]+$/.test(launch)||!process.env.COMPANY_UI_PLAYWRIGHT)throw new Error('Set the local demo launch URL and Playwright module path');
const {chromium}=await import(pathToFileURL(process.env.COMPANY_UI_PLAYWRIGHT).href);
const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const dismiss=async()=>{
  const notice=page.getByRole('button',{name:'Continue',exact:true});
  if(await notice.isVisible()){await notice.click();await notice.waitFor({state:'hidden'});}
  const later=page.getByRole('button',{name:'Configure later',exact:true});
  await later.waitFor({state:'visible',timeout:5000}).catch(()=>{});
  if(await later.isVisible()){await later.click();await later.waitFor({state:'hidden'});}
 };
 await page.goto(launch);await page.locator('[data-company-shell]').waitFor();await dismiss();
 assert.equal(page.url(),'http://127.0.0.1:3081/');
 assert.equal(await page.locator('[data-panel=chat] iframe').count(),0);
 assert.equal(await page.locator('[data-native-workspaces]').count(),1);
 const session=page.locator('[data-native-workspaces]').getByText('New Session',{exact:true});
 await session.waitFor();await session.click();
 const editor=page.locator('[contenteditable=true]').first();await editor.waitFor();
 await editor.fill('布局检查草稿，不发送。');
 const element=await editor.elementHandle();
 for(const panel of ['left','center','chat']){
  await page.locator(`[data-panel-toggle=${panel}]`).click();
  assert.equal(await page.locator(`[data-panel=${panel}]`).isVisible(),false);
  await page.locator(`[data-panel-toggle=${panel}]`).click();
  assert.equal(await page.locator(`[data-panel=${panel}]`).isVisible(),true);
  assert.equal(await editor.innerText(),'布局检查草稿，不发送。');
 }
 assert.equal(await element.evaluate(node=>node.isConnected),true);
 const before=await page.locator('[data-panel=left]').boundingBox();
 const handle=await page.getByRole('separator',{name:'调整左栏宽度'}).boundingBox();
 await page.mouse.move(handle.x+3,handle.y+80);await page.mouse.down();await page.mouse.move(handle.x+80,handle.y+80,{steps:8});await page.mouse.up();
 assert.ok((await page.locator('[data-panel=left]').boundingBox()).width>before.width+50);
 const chatWidth=(await page.locator('[data-panel=chat]').boundingBox()).width;
 await page.getByRole('separator',{name:'调整对话宽度'}).focus();await page.keyboard.press('ArrowLeft');
 assert.ok((await page.locator('[data-panel=chat]').boundingBox()).width>chatWidth);
 assert.equal(await page.locator('[data-panel=chat] [aria-label=Settings]').count(),0);
 await page.locator('.cw-native-settings [aria-label=Settings]').click();
 await page.getByRole('button',{name:'Models',exact:true}).click();
 await page.getByText('Enter your API keys to use models from the following providers.',{exact:true}).waitFor();
 assert.equal(await page.locator('input[type=password]').first().inputValue(),'');
 await page.getByRole('button',{name:'Close',exact:true}).click();
 await page.locator('.cw-tree-item').filter({hasText:'analysis.html'}).click();
 await page.frameLocator('[data-company-content]').locator('svg.chart').waitFor();
 assert.equal(await editor.innerText(),'布局检查草稿，不发送。');
 await editor.fill('');
 const state=await page.evaluate(()=>JSON.parse(localStorage.getItem('unitqc.workspace.layout.v1')));
 await page.reload();await page.locator('[data-company-shell]').waitFor();await dismiss();
 assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('unitqc.workspace.layout.v1')).left),state.left);
 for(const width of [1440,1024,900,768,390]){
  await page.setViewportSize({width,height:960});
  if(width<900)for(const panel of ['left','center','chat']){await page.locator(`[data-panel-focus=${panel}]`).click();assert.equal(await page.locator(`[data-panel=${panel}]`).isVisible(),true);}
  const size=await page.evaluate(()=>({w:innerWidth,sw:document.documentElement.scrollWidth,h:innerHeight,sh:document.documentElement.scrollHeight}));
  assert.ok(size.sw<=size.w);assert.ok(size.sh<=size.h);
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({status:'passed',checks:['single native workspace sidebar','native conversation without nested sidebar','panel hide/restore without losing draft','pointer and keyboard resize','persistent widths','native model settings','content navigation','narrow panels'],modelMessageSent:false},null,2));
}finally{await browser.close();}
