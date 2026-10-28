import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

// Optional browser check. Keep browser dependencies outside the managed DSH runtime.
// Set COMPANY_UI_PLAYWRIGHT to an installed playwright/index.mjs and
// COMPANY_UI_SCREENSHOTS to an output directory. No live providers are contacted.
if (!process.env.COMPANY_UI_PLAYWRIGHT) {
  throw new Error('Set COMPANY_UI_PLAYWRIGHT to the absolute path of playwright/index.mjs');
}
const { chromium } = await import(pathToFileURL(process.env.COMPANY_UI_PLAYWRIGHT).href);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const capture = async name => {
    if (process.env.COMPANY_UI_SCREENSHOTS) {
      await page.screenshot({ path: `${process.env.COMPANY_UI_SCREENSHOTS}/${name}.png` });
    }
  };
  await page.route('http://127.0.0.1:3081/**', route => route.fulfill({status:200,contentType:'text/html',body:'<!doctype html><title>Native endpoint stub</title>'}));
  await page.goto(new URL('../../docs/quantum-agent-architecture.zh-CN.html', import.meta.url).href);
  await page.locator('#panel-workspace').waitFor({ state: 'visible' });
  assert.equal(await page.locator('.masthead').isVisible(), false);
  assert.equal(await page.locator('main > .hero').isVisible(), false);
  const homeCopy = await page.locator('#center-content').textContent();
  assert.ok(homeCopy.replace(/\s/g, '').length < 220);
  const columns = await page.locator('.workspace-grid').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').map(parseFloat));
  assert.equal(columns[0],220);
  assert.ok(columns[2] >= 480 && columns[2] <= 720);
  await capture('workspace-1440');

  const dockBefore = await page.locator('.account-dock').boundingBox();
  await page.locator('.resource-tree').evaluate(node => { node.scrollTop = node.scrollHeight; });
  assert.equal((await page.locator('.account-dock').boundingBox()).y, dockBefore.y);
  await page.locator('#account-button').click();
  assert.equal(await page.locator('#account-dialog').evaluate(node => node.open), true);
  await page.locator('[data-auth-mode="register"]').click();
  assert.match(await page.locator('#account-title').textContent(), /注册/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#account-dialog').evaluate(node => node.open), false);

  await page.locator('.workspace-nav [data-file="local-readme"]').click();
  await capture('file-1440');
  const content = await page.locator('#center-content').innerHTML();
  assert.equal(await page.locator('[data-session="coding"]').isDisabled(),true);
  assert.equal(await page.locator('#center-content').innerHTML(), content);
  // Connection management moved to the native DSH Plugins page: the page only
  // carries the jump affordance and a portal status panel.
  await page.locator('[data-view="cloud"]').first().click();
  await page.locator('[data-settings-section="cloud"]').first().click();
  await capture('portal-1440');
  assert.equal(await page.locator('#connection-form').count(), 0);
  await page.locator('#local-tree [data-view="results"]').click();
  await capture('report-1440');

  await page.locator('.workspace-tools a[href="#overview"]').click();
  await page.locator('#panel-overview').waitFor({ state: 'visible' });
  assert.equal(await page.locator('.masthead').isVisible(), true);
  await page.locator('[data-tab="workspace"]').click();
  assert.equal(await page.locator('#editor-tabs [data-view="results"]').getAttribute('aria-current'), 'page');
  const widths = [1440, 1024, 900, 850, 768, 641, 640, 390];
  for (const width of widths) {
    await page.setViewportSize({ width, height: 960 });
    if (width <= 640) await page.locator('button[data-mobile-panel="content"]').click();
    const size = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, height: innerHeight, scrollHeight: document.documentElement.scrollHeight }));
    assert.ok(size.scrollWidth <= width, `horizontal overflow at ${width}`);
    assert.ok(size.scrollHeight <= size.height, `body scroll at ${width}`);
    if (width > 640) {
      for (const panel of ['.workspace-nav', '.workspace-center', '.chat']) assert.equal(await page.locator(panel).isVisible(), true);
    } else {
      assert.equal(await page.locator('.workspace-center').isVisible(), true);
      assert.equal(await page.locator('.chat').isVisible(), false);
      assert.equal(await page.locator('.workspace-nav').isVisible(), false);
      await page.locator('button[data-mobile-panel="resources"]').click();
      assert.equal(await page.locator('.workspace-nav').isVisible(), true);
      await page.locator('button[data-mobile-panel="chat"]').click();
      assert.equal(await page.locator('.chat').isVisible(), true);
      await page.locator('button[data-mobile-panel="resources"]').click();
      assert.equal(await page.locator('.workspace-center').isVisible(), true);
    }
  }
  await page.locator('#editor-tabs [data-view="welcome"]').click();
  await capture('workspace-390');
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'passed', homeCharacters: homeCopy.replace(/\s/g, '').length, widths, screenshots: Boolean(process.env.COMPANY_UI_SCREENSHOTS) }, null, 2));
} finally {
  await browser.close();
}
