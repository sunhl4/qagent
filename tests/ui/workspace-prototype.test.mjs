import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { JSDOM, VirtualConsole } from 'jsdom';

// Design-only checks: no live runtime, user identity, provider, network or device.
const source = readFileSync(new URL('../../docs/quantum-agent-architecture.zh-CN.html', import.meta.url), 'utf8');
function page(hash = '#workspace') {
  const errors = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error));
  const dom = new JSDOM(source, {
    url: 'https://design.invalid/architecture' + hash,
    runScripts: 'dangerously',
    virtualConsole: console,
    beforeParse(window) {
      window.CSS = { escape: value => String(value).replace(/[^a-zA-Z0-9_-]/g, character => `\\${character}`) };
      window.HTMLElement.prototype.scrollIntoView = function () {};
      // jsdom has no native modal implementation. Browser verification is separate.
      window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
      window.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
      window.fetch = () => { throw new Error('Network is forbidden in a design prototype'); };
      window.XMLHttpRequest = class { constructor() { throw new Error('Network is forbidden'); } };
    }
  });
  const { document } = dom.window;
  const click = selector => {
    const target = document.querySelector(selector);
    assert.ok(target, `Missing target ${selector}`);
    target.click();
    assert.deepEqual(errors, []);
  };
  assert.deepEqual(errors, []);
  return { dom, document, click, errors };
}

test('remote trees start collapsed and the bottom dock defers settings to native DSH', () => {
  const { dom, document } = page();
  assert.equal(document.querySelector('#panel-workspace').hidden, false);
  assert.deepEqual(Array.from(document.querySelectorAll('.resource-tree > details'), item => item.id), ['cloud-tree', 'hpc-tree', 'local-tree', 'workspaces-tree']);
  assert.equal(document.querySelector('#cloud-tree').open, false);
  assert.equal(document.querySelector('#hpc-tree').open, false);
  assert.equal(document.querySelector('#local-tree').open, true);
  assert.equal(document.querySelector('#workspaces-tree').open, true);
  assert.ok(document.querySelector('.account-dock #account-button'));
  // Settings entry is de-duplicated: the page own gear link is gone, the dock
  // only points at the single native DSH settings dialog.
  assert.equal(document.querySelector('.account-dock .gear-button'), null);
  assert.match(document.querySelector('.account-dock .gear-note').textContent, /设置入口唯一：原生 DSH「设置」/);
  assert.match(document.querySelector('#account-button').textContent, /未登录/);
  const ids = Array.from(document.querySelectorAll('[id]'), node => node.id);
  assert.equal(new Set(ids).size, ids.length, 'All DOM IDs must be unique');
  dom.window.close();
});

test('account dialog switches registration/login without accepting credentials or claiming success', () => {
  const { dom, document, click } = page();
  click('#account-button');
  assert.equal(document.querySelector('#account-dialog').open, true);
  click('[data-auth-mode="register"]');
  assert.match(document.querySelector('#account-title').textContent, /注册/);
  assert.equal(document.querySelector('#register-name').hidden, false);
  assert.ok(Array.from(document.querySelectorAll('#account-dialog input')).every(input => input.disabled));
  assert.equal(document.querySelector('#auth-submit').disabled, true);
  click('[data-auth-mode="login"]');
  assert.equal(document.querySelector('#register-name').hidden, true);
  click('#close-account');
  assert.equal(document.querySelector('#account-dialog').open, false);
  assert.match(document.querySelector('#account-button').textContent, /未登录/);
  dom.window.close();
});

test('middle tabs preserve file origin, deduplicate and remain independent from conversation selection', () => {
  const { dom, document, click } = page();
  const session = document.querySelector('[data-session][aria-current="true"]').dataset.session;
  click('[data-file="cloud-input"]');
  click('[data-file="local-input"]');
  click('[data-file="cloud-input"]');
  assert.equal(document.querySelectorAll('#editor-tabs [data-view="file-cloud-input"]').length, 1);
  assert.equal(document.querySelectorAll('#editor-tabs [data-view="file-local-input"]').length, 1);
  assert.match(document.querySelector('#editor-label').textContent, /^云平台/);
  assert.equal(document.querySelector('[data-session][aria-current="true"]').dataset.session, session);
  const content = document.querySelector('#center-content').innerHTML;
  click('[data-session="analysis"]');
  assert.equal(document.querySelector('[data-session][aria-current="true"]').dataset.session, session);
  assert.equal(document.querySelector('[data-session="analysis"]').disabled, true);
  assert.equal(document.querySelector('#center-content').innerHTML, content);
  click('[data-close-view="file-cloud-input"]');
  assert.match(document.querySelector('#editor-label').textContent, /^本机/);
  click('[data-close-view="file-local-input"]');
  click('[data-close-view="welcome"]');
  assert.match(document.querySelector('#editor-label').textContent, /工作区/);
  assert.equal(document.querySelectorAll('#editor-tabs [data-view]').length, 1);
  dom.window.close();
});

test('platform connection management lives in native DSH Settings; the page only points at it', async () => {
  const { dom, document, click } = page();
  const center = document.querySelector('#center-content');
  // The in-page settings view is retired; connection management happens in
  // DSH's native Settings dialog ("Platform Connections" section page, with a
  // General-section discoverability row). The document carries no settings
  // tabs, no access panels, no jump affordances and collects nothing.
  assert.equal(document.querySelectorAll('.settings-tabs, .settings-content').length, 0);
  assert.equal(document.querySelectorAll('#center-content input, #center-content select, #center-content textarea, #center-content form').length, 0);
  assert.equal(document.querySelectorAll('[data-settings-section]').length, 0);
  const seen = [];
  dom.window.addEventListener('message', event => seen.push(event.data));
  click('[data-view="cloud"]');
  assert.match(center.textContent, /「设置」→「平台连接」/);
  click('[data-view="hpc"]');
  assert.match(center.textContent, /「设置」→「平台连接」/);
  click('[data-view="knowledge"]');
  assert.match(center.textContent, /「设置」→「平台连接」/);
  assert.deepEqual(seen, [], 'no cross-frame settings jump messages are sent');
  assert.equal(dom.window.localStorage.length, 0);
  assert.equal(dom.window.sessionStorage.length, 0);
  assert.equal(document.cookie, '');
  dom.window.close();
});

test('right column loads the unmodified native DSH origin without recreated controls', () => {
  const { dom, document, click } = page();
  const slot = document.querySelector('.chat');
  const frame = document.querySelector('#dsh-native-frame');
  assert.equal(frame.tagName, 'IFRAME');
  assert.equal(frame.src, 'http://127.0.0.1:3081/');
  assert.equal(frame.getAttribute('referrerpolicy'), 'no-referrer');
  assert.equal(frame.hasAttribute('srcdoc'), false);
  assert.equal(slot.querySelectorAll('button, input, textarea, select, [contenteditable]').length, 0);
  assert.equal(slot.querySelectorAll('.chat-head, .chat-session, .dsh-status, #dsh-session-label').length, 0);
  assert.doesNotMatch(slot.textContent, /待接入/);
  assert.doesNotMatch(source, /\.chat-head|\.chat-session|\.dsh-status|\.chat-compose|\.user-message|\.assistant-message/);
  const original = slot.innerHTML;
  click('[data-session="coding"]');
  assert.equal(slot.innerHTML, original);
  assert.equal(document.querySelector('[data-session="coding"]').disabled, true);
  click('#native-expand');
  assert.equal(document.body.classList.contains('native-expanded'), true);
  click('#native-expand');
  assert.equal(document.body.classList.contains('native-expanded'), false);
  assert.equal(slot.innerHTML, original);
  dom.window.close();
});

test('company work scenarios change design content without changing identity, connection or conversation', () => {
  const { dom, document, click } = page();
  const identity = document.querySelector('#workspace-account').textContent;
  const audience = document.body.dataset.audience;
  const session = document.querySelector('[data-session][aria-current="true"]').dataset.session;
  click('[data-tab="enterprise"]');
  for (const scenario of ['research', 'customer', 'daily']) {
    click(`[data-scenario="${scenario}"]`);
    assert.equal(document.querySelectorAll('[data-scenario][aria-pressed="true"]').length, 1);
    assert.equal(document.querySelectorAll('#enterprise-scenario ol li').length, 4);
    assert.match(document.querySelector('#enterprise-scenario').textContent, /非权限切换/);
    assert.equal(document.body.dataset.audience, audience);
    assert.equal(document.querySelector('#workspace-account').textContent, identity);
    assert.equal(document.querySelector('[data-session][aria-current="true"]').dataset.session, session);
  }
  assert.match(document.querySelector('#enterprise-scenario').textContent, /无需先创建量子任务/);
  for (const node of ['productivity','development','enterpriseKnowledge']) {
    click(`[data-node="${node}"]`);
    assert.ok(document.querySelector('#node-detail h3').textContent);
  }
  assert.equal(dom.window.localStorage.length, 0);
  dom.window.close();
});

test('general Agent capabilities are core design requirements, without changing the product workspace', () => {
  const { dom, document, click } = page();
  const content = document.querySelector('#center-content').innerHTML;
  const chat = document.querySelector('.chat').innerHTML;
  const identity = document.querySelector('#workspace-account').textContent;
  click('[data-tab="enterprise"]');
  const baseline = document.querySelector('#general-capability-baseline');
  assert.ok(baseline);
  assert.equal(baseline.closest('.panel').id, 'panel-enterprise');
  assert.equal(baseline.querySelectorAll('li').length, 6);
  for (const expected of [/文件与办公/, /代码与命令/, /数据与调研/, /连续执行/, /副作用单独确认/, /真实完成标准/]) {
    assert.match(baseline.textContent, expected);
  }
  assert.match(document.querySelector('#general-agent-roadmap').textContent, /首期：通用 Agent 内部可用版/);
  assert.ok(document.querySelector('#panel-enterprise a[href="super-dsh-product-plan.zh-CN.md"]'));
  click('[data-scenario="daily"]');
  assert.match(document.querySelector('#enterprise-scenario').textContent, /实际读写文件/);
  assert.match(document.querySelector('#enterprise-scenario').textContent, /当前合同尚未实现/);
  assert.equal(document.querySelector('#center-content').innerHTML, content);
  assert.equal(document.querySelector('.chat').innerHTML, chat);
  assert.equal(document.querySelector('#workspace-account').textContent, identity);
  click('[data-tab="workspace"]');
  assert.equal(document.querySelector('#panel-workspace #general-capability-baseline'), null);
  assert.equal(dom.window.localStorage.length, 0);
  assert.equal(dom.window.sessionStorage.length, 0);
  dom.window.close();
});

test('DSH integration design prioritizes reuse, scoped tools and interface robustness without runtime effects', () => {
  const { dom, document, click } = page();
  const content = document.querySelector('#center-content').innerHTML;
  const chat = document.querySelector('.chat').innerHTML;
  const session = document.querySelector('[data-session][aria-current="true"]').dataset.session;
  const identity = document.querySelector('#workspace-account').textContent;
  click('[data-tab="enterprise"]');
  const baseline = document.querySelector('#dsh-integration-baseline');
  assert.ok(baseline);
  assert.equal(baseline.closest('.panel').id, 'panel-enterprise');
  assert.equal(baseline.querySelectorAll('li').length, 6);
  for (const expected of [/MCP/, /Skills/, /合同/, /超时/, /幂等/, /设备自动重试为零/, /隔离/]) {
    assert.match(baseline.textContent, expected);
  }
  assert.match(document.querySelector('.enterprise-summary').textContent, /并列接入/);
  assert.match(document.querySelector('#general-agent-roadmap').textContent, /优先复用已有 API/);
  assert.ok(document.querySelector('#panel-enterprise a[href="super-dsh-handbook-2026-11-06.zh-CN.md"]'));
  assert.ok(document.querySelector('#panel-enterprise a[href="company-agent-harness-framework-v0.8.zh-CN.md"]'));
  assert.equal(baseline.querySelectorAll('button, input, textarea, select, iframe').length, 0);
  assert.equal(document.querySelector('#center-content').innerHTML, content);
  assert.equal(document.querySelector('.chat').innerHTML, chat);
  assert.equal(document.querySelector('[data-session][aria-current="true"]').dataset.session, session);
  assert.equal(document.querySelector('#workspace-account').textContent, identity);
  click('[data-tab="workspace"]');
  assert.equal(document.querySelector('#panel-workspace #dsh-integration-baseline'), null);
  assert.equal(dom.window.localStorage.length, 0);
  assert.equal(dom.window.sessionStorage.length, 0);
  dom.window.close();
});

test('knowledge guidance is in documentation, while workspace drafts remain unavailable', () => {
  const { dom, document, click } = page();
  click('[data-session="coding"]');
  const session = document.querySelector('[data-session][aria-current="true"]').dataset.session;
  click('[data-view="knowledge"]');
  const center = document.querySelector('#center-content');
  assert.match(center.textContent, /未连接/);
  click('#center-content [data-view="capture"]');
  assert.match(center.textContent, /暂无草稿/);
  assert.equal(center.querySelector('button').disabled, true);
  assert.equal(center.querySelectorAll('[data-knowledge-stage]').length, 0);
  const content = center.innerHTML;
  click('[data-tab="enterprise"]');
  for (const stage of ['select','draft','check','review','publish','maintain']) {
    click(`[data-knowledge-stage="${stage}"]`);
    assert.equal(document.querySelectorAll('[data-knowledge-stage][aria-pressed="true"]').length, 1);
    assert.equal(center.innerHTML, content);
    assert.equal(document.querySelector('[data-session][aria-current="true"]').dataset.session, session);
  }
  click('[data-knowledge-stage="publish"]');
  const explanation = document.querySelector('#knowledge-design-detail').textContent;
  assert.match(explanation, /已保存待索引/);
  assert.match(explanation, /索引失败只恢复同步/);
  click('[data-tab="workspace"]');
  assert.equal(center.innerHTML, content);
  assert.equal(dom.window.localStorage.length, 0);
  assert.equal(dom.window.sessionStorage.length, 0);
  assert.equal(document.cookie, '');
  dom.window.close();
});

test('development and daily views show concise empty states without granting permissions', () => {
  const { dom, document, click } = page();
  const chat = document.querySelector('.chat').innerHTML;
  click('[data-view="development"]');
  const center = document.querySelector('#center-content');
  assert.match(center.textContent, /未连接仓库/);
  assert.equal(center.querySelectorAll('input, select, textarea, form').length, 0);
  assert.equal(document.querySelector('.chat').innerHTML, chat);
  click('[data-view="daily"]');
  assert.match(center.textContent, /暂无文档/);
  assert.equal(center.querySelector('button').disabled, true);
  dom.window.close();
});

test('workspace is the default product view and documentation can be visited without losing tabs', () => {
  const { dom, document, click } = page('');
  assert.equal(document.body.classList.contains('workspace-mode'), true);
  assert.equal(document.querySelector('#panel-workspace').hidden, false);
  assert.match(document.querySelector('#workspace-account').textContent, /左侧为示例 · 右侧原生 DSH/);
  click('[data-file="local-readme"]');
  const content = document.querySelector('#center-content').innerHTML;
  click('[data-tab="overview"]');
  assert.equal(document.body.classList.contains('workspace-mode'), false);
  click('[data-tab="workspace"]');
  assert.equal(document.body.classList.contains('workspace-mode'), true);
  assert.equal(document.querySelector('#center-content').innerHTML, content);
  assert.match(document.querySelector('#editor-label').textContent, /本机/);
  assert.equal(document.querySelector('#editor-tabs [data-view="file-local-readme"]').textContent, 'README.md');
  dom.window.close();
});

test('product copy stays short and does not contain architecture explanations', () => {
  const { dom, document, click } = page();
  const center = document.querySelector('#center-content');
  assert.ok(center.textContent.replace(/\s/g,'').length < 220, 'Home has no product essay');
  assert.equal(document.querySelectorAll('#panel-workspace .boundary-row, #panel-workspace .notice').length, 0);
  for (const view of ['knowledge','capture','development','daily','canvas','cloud','hpc']) {
    click(`[data-view="${view}"]`);
    assert.ok(center.textContent.replace(/\s/g,'').length < 170, `Concise ${view} empty state`);
    assert.doesNotMatch(center.textContent, /失败闭合|唯一 Agent Runtime|正式产品|本原型|权限边界|建设顺序|设计示例/);
  }
  dom.window.close();
});

test('narrow-screen navigation selects content or chat without mutating either', () => {
  const { dom, document, click } = page();
  const grid = document.querySelector('.workspace-grid');
  click('button[data-mobile-panel="resources"]');
  assert.equal(grid.dataset.mobilePanel, 'resources');
  click('[data-file="local-readme"]');
  assert.equal(grid.dataset.mobilePanel, 'content');
  const content = document.querySelector('#center-content').innerHTML;
  click('button[data-mobile-panel="resources"]');
  click('button[data-mobile-panel="chat"]');
  assert.equal(grid.dataset.mobilePanel, 'chat');
  assert.equal(document.querySelector('#center-content').innerHTML, content);
  click('button[data-mobile-panel="content"]');
  assert.equal(grid.dataset.mobilePanel, 'content');
  assert.equal(document.querySelectorAll('button[data-mobile-panel][aria-pressed="true"]').length, 1);
  dom.window.close();
});

test('existing architecture navigation, review filters, scenarios and keyboard navigation still work', () => {
  const { dom, document, click, errors } = page();
  for (const tab of document.querySelectorAll('[data-tab]')) {
    click(`[data-tab="${tab.dataset.tab}"]`);
    assert.equal(document.querySelectorAll('.panel:not([hidden])').length, 1);
    assert.equal(document.getElementById(tab.getAttribute('aria-controls')).hidden, false);
  }
  click('[data-tab="overview"]');
  for (const node of document.querySelectorAll('[data-node]')) {
    click(`[data-node="${node.dataset.node}"]`);
    assert.ok(document.querySelector('#node-detail h3').textContent);
  }
  click('[data-tab="workflow"]');
  for (const stage of document.querySelectorAll('[data-stage]')) click(`[data-stage="${stage.dataset.stage}"]`);
  click('[data-tab="review"]');
  click('[data-review-filter="P0"]');
  for (const finding of document.querySelectorAll('[data-priority]')) assert.equal(finding.hidden, finding.dataset.priority !== 'P0');
  const select = document.querySelector('#state-scenario');
  for (const option of select.options) {
    select.value = option.value;
    select.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    assert.equal(document.querySelectorAll('.state-column').length, 4);
  }
  document.querySelector('[data-tab="overview"]').focus();
  document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(document.activeElement.dataset.tab, 'workspace');
  assert.equal(document.querySelector('#panel-workspace').hidden, false);
  assert.deepEqual(errors, []);
  dom.window.close();
});
