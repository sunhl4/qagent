// LIVE boot probe: loads the REAL served DSH web page (real runtime server on
// 127.0.0.1:<port>) inside jsdom, lets the real client bundle mount, and fails
// with the first captured console error when the company three-column shell
// (left sidebar folders 云平台/超算) does not appear.
// Usage: COMPANY_AGENT_LIVE_PORTAL_URL=http://127.0.0.1:PORT/?token=... node live-boot.test.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {CookieJar} from 'jsdom';
import {JSDOM, VirtualConsole, ResourceLoader} from 'jsdom';
import test from 'node:test';

const server = process.env.COMPANY_AGENT_LIVE_SERVER;
if (!server) {
  test('live boot probe', {skip: 'set COMPANY_AGENT_LIVE_SERVER to run the live boot probe'});
  process.exit(0);
}

// First call establishes the session cookie from the ?token= login redirect.
const bootstrap = await fetch(server, {redirect: 'manual'});
assert.ok([200, 303].includes(bootstrap.status), `login returned ${bootstrap.status}`);
const cookies = bootstrap.headers.getSetCookie?.() ?? [];
const jar = new CookieJar();
for (const cookie of cookies) jar.setCookieSync(cookie, server);
let cookieHeader = jar.getCookieStringSync(server);
if (cookies.length && !cookieHeader) {
  // jsdom cookie jar may reject SameSite edges; fall back to a manual jar pass.
  cookieHeader = cookies.map(cookie => cookie.split(';')[0]).join('; ');
}
const page = await fetch(server, {headers: {cookie: cookieHeader}});
assert.equal(page.status, 200, `index returned ${page.status}`);
const html = await page.text();
assert.match(html, /__DSH_BOOT__/);

const resources = {fetched: [], failed: []};
class AuthedLoader extends ResourceLoader {
  fetch(url, options) {
    // Keep every subresource same-origin-authenticated regardless of jsdom's
    // private cookie policy derivations.
    resources.fetched.push(String(url));
    const promise = super.fetch(url, {...options, headers: {...options.headers, cookie: cookieHeader}});
    promise.catch(error => resources.failed.push([String(url), String(error)]));
    // jsdom never runs type="module" scripts, so the app entry (a single-file
    // Vite module with no static imports; only lazily loaded language packs
    // remain dynamic) is rewritten to a classic script here. fetch() resolves
    // to the raw text buffer; the only change is import.meta.url -> the
    // bundle's own absolute URL string.
    if (String(url).includes('/assets/') && String(url).endsWith('.js')) {
      const transformed = promise.then(data => {
        const text = Buffer.isBuffer(data) ? data.toString('utf8') : String(data);
        return text.split('import.meta.url').join(JSON.stringify(url));
      });
      transformed.abort = promise.abort.bind(promise);
      if (promise.getHeader) transformed.getHeader = promise.getHeader.bind(promise);
      return transformed;
    }
    return promise;
  }
}

const diagnostics = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', error => diagnostics.push(['page', String(error?.message || error), String(error?.stack || '').slice(0, 900)]));
for (const level of ['error', 'warn']) {
  virtualConsole.on(level, (...args) => diagnostics.push([level, args.map(arg =>
    arg instanceof Error ? `${arg.name}: ${arg.message}` : typeof arg === 'string' ? arg : JSON.stringify(arg).slice(0, 400)).join(' ').slice(0, 900)]));
}

// jsdom never executes type="module" scripts. The app entry is a single-file
// Vite module (no static imports; only lazily loaded language packs stay
// dynamic), so the probe rewrites it to a classic script and adapts
// import.meta.url inside the resource loader. No shell logic is changed.
const bootHtml = html.replace('<script type="module" crossorigin src=', '<script crossorigin defer src=');
const dom = new JSDOM(bootHtml, {
  url: server,
  resources: new AuthedLoader(),
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  cookieJar: jar,
  virtualConsole,
  beforeParse(window) {
    // Page-environment gaps only; no shell behavior is shimmed.
    if (typeof window.Promise.withResolvers !== 'function') {
      window.Promise.withResolvers = function () {
        let resolve;
        let reject;
        const promise = new this((res, rej) => {resolve = res;reject = rej;});
        return {promise, resolve, reject};
      };
    }
    window.fetch = ((input, init = {}) => globalThis.fetch(String(input), {
      ...init,
      headers: {...(init.headers ?? {}), cookie: cookieHeader},
    }));
    if (!window.ResizeObserver) {
      window.ResizeObserver = class {
        constructor(callback) { this.callback = callback; }
        observe(target) { queueMicrotask(() => this.callback?.([{target}], this)); }
        unobserve() {} disconnect() {}
      };
    }
    if (!window.IntersectionObserver) {
      window.IntersectionObserver = class {
        observe() {} unobserve() {} disconnect() {} takeRecords() { return []; }
      };
    }
    if (!window.matchMedia) {
      window.matchMedia = query => ({matches: false, media: query, onchange: null,
        addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false});
    }
    window.scrollTo = () => {};
    window.HTMLElement.prototype.scrollIntoView = function () {};
  },
});

const {window} = dom;
await new Promise(resolve => {
  let remaining = 45;
  const tick = setInterval(() => {
    remaining -= 1;
    const frame = window.document.querySelector('[data-company-shell]');
    if (frame || diagnostics.some(([level, text]) => level === 'page') || remaining === 0) {
      clearInterval(tick);
      resolve();
    }
  }, 500);
});

const frame = window.document.querySelector('[data-company-shell]');
const folders = [...window.document.querySelectorAll('.cw-folder')];
const sidebarText = window.document.querySelector('.cw-resources')?.textContent || '';
const reportLocal = {
  frame: Boolean(frame),
  folderCount: folders.length,
  folderTitles: [...folders].map(node => node.querySelector('.cw-folder-title')?.textContent || '').slice(0, 8),
  cloudVisible: /云平台/.test(sidebarText) || folders.some(node => /云平台/.test(node.textContent || '')),
  hpcVisible: /超算/.test(sidebarText) || folders.some(node => /超算/.test(node.textContent || '')),
  nativeWorkspaces: Boolean(window.document.querySelector('[data-native-workspaces]')),
  bodyChildren: window.document.body.children.length,
  bodyTags: [...window.document.body.children].map(node => `${node.tagName}${node.id ? '#' + node.id : ''}${typeof node.className === 'string' ? '.' + node.className : ''}`),
  hasBoot: typeof window.__DSH_BOOT__ === 'object',
  moduleLoaderKeys: window.__ModuleLoader__ ? Object.keys(window.__ModuleLoader__) : null,
  resources: {count: resources.fetched.length, urls: resources.fetched.slice(0, 12), failed: resources.failed.slice(0, 6)},
  diagnostics: diagnostics.slice(0, 12),
};
console.log(JSON.stringify(reportLocal, null, 1));
dom.window.close();
if (!frame) throw new Error(`company shell never mounted; first page error: ${JSON.stringify(diagnostics.find(([level]) => level === 'page') || reportLocal)}`);
assert.ok(reportLocal.cloudVisible && reportLocal.hpcVisible, `sidebar missing 云平台/超算 folders: ${JSON.stringify(reportLocal)}`);
