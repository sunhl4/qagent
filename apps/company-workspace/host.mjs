import {readFile, writeFile, mkdir, chmod, readdir, lstat} from 'node:fs/promises';
import {createHash, randomBytes, timingSafeEqual} from 'node:crypto';
import {execFile} from 'node:child_process';
import {request as httpRequest} from 'node:http';
import {request as httpsRequest, Agent as HttpsAgent} from 'node:https';
import {promisify} from 'node:util';
import {homedir} from 'node:os';
import {dirname, join, relative, resolve, sep} from 'node:path';
const run = promisify(execFile);

// Presentation and content extension over the native DSH shell. No tools,
// model calls, or runtime loops: everything mounts through native slots.
// The running boot graph and native Slot/seat contracts are integration
// boundaries; this plugin only appends entries and never replaces native ones.
export const name = 'company-workspace-shell';
export const inject = ['webServer', 'connection', 'clientModules', 'workspaceRegistry'];
const ID = '@unitqc/company-workspace-ui';
const ROOT = new URL('../../', import.meta.url);
const WORKBENCH_OPERATIONS = new Set(['cloud.submit', 'hpc.submit', 'device.run']);
const REQUEST_ID = /^req_[0-9a-f]{32}$/;
const BUSINESS_REF = /^[A-Za-z0-9_.:-]{1,256}$/;
const SUBJECT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,62}@[A-Za-z0-9][A-Za-z0-9.-]{0,52}$/;
const WORKBENCH_RECORDS = new Set(['dispatch', 'outcome']);
const WORKBENCH_CONNECTION_STATES = new Set(['server_facts', 'reconnecting', 'unavailable']);

function trusted(req, authority) {
  const host = req.headers.host;
  if (host !== authority || req.headers['sec-fetch-site'] === 'cross-site') return false;
  return !req.headers.origin || req.headers.origin === `http://${authority}`;
}

export function workbenchEventRank(row) {
  if (!row || typeof row !== 'object' || !WORKBENCH_RECORDS.has(row.record)) return -1;
  const status = String(row.status || '');
  const execution = String(row.execution_state || '');
  if (row.record === 'outcome' && status === 'ok' && execution === 'completed') return 5;
  if (row.record === 'outcome' && status === 'refused' && execution === 'dispatched') return 4;
  if (row.record === 'outcome' && status === 'error' && execution === 'unknown') return 3;
  if (row.record === 'dispatch' && status === 'dispatched' && execution === 'dispatched') return 2;
  return -1;
}

export function workbenchTaskFromEvent(row, connectionState = 'server_facts') {
  const rank = workbenchEventRank(row);
  if (rank < 0) return null;
  const requestId = String(row.request_id || '');
  const operation = String(row.operation || '');
  const timestamp = Number(row.timestamp);
  const updatedAt = Number.isSafeInteger(timestamp) && timestamp >= 0 ? timestamp : 0;
  const successful = rank === 5;
  const reference = successful && BUSINESS_REF.test(String(row.business_ref || '')) ? String(row.business_ref) : '';
  const completed = successful && Boolean(reference);
  return {
    request_id: requestId,
    operation,
    status: completed ? 'completed' : rank === 4 ? 'refused' : 'unknown',
    execution_state: completed ? 'completed' : row.execution_state === 'dispatched' ? 'dispatched' : 'unknown',
    approval_state: 'not_projected',
    connection_state: connectionState,
    business_ref: reference,
    result_state: completed ? 'available' : 'unknown',
    billing_state: 'not_projected',
    updated_at: updatedAt,
    source: 'company-agent-receipts',
    _rank: rank,
  };
}

export function resolveTrustedSubject(connection, req) {
  const resolver = connection && typeof connection.subjectForRequest === 'function'
    ? connection.subjectForRequest
    : connection && typeof connection.subject === 'function' ? connection.subject : null;
  const candidate = resolver ? resolver(req) : '';
  return typeof candidate === 'string' && SUBJECT_PATTERN.test(candidate.trim())
    ? candidate.trim() : 'unknown@unknown';
}

export function scopedFactKey(key, subjectValue) {
  const subject = typeof subjectValue === 'string' && SUBJECT_PATTERN.test(subjectValue.trim())
    ? subjectValue.trim() : 'unknown@unknown';
  return `${key}:${subject}`;
}

export function projectWorkbenchTasks(records, options = {}) {
  if (!Array.isArray(records)) return [];
  const connectionState = WORKBENCH_CONNECTION_STATES.has(options.connectionState)
    ? options.connectionState : 'server_facts';
  const grouped = new Map();
  const targetSubject = typeof options.subject === 'string' && SUBJECT_PATTERN.test(options.subject.trim())
    ? options.subject.trim() : '';
  for (const row of records) {
    if (!row || typeof row !== 'object' || !REQUEST_ID.test(String(row.request_id || ''))) continue;
    if (targetSubject && String(row.subject || '') !== targetSubject) continue;
    const operation = String(row.operation || '');
    if (!WORKBENCH_OPERATIONS.has(operation)) continue;
    const event = workbenchTaskFromEvent(row, connectionState);
    if (!event) continue;
    const requestId = event.request_id;
    const previous = grouped.get(requestId);
    if (previous && (
      event.updated_at < previous.updated_at
      || (event.updated_at === previous.updated_at && event._rank <= previous._rank)
    )) continue;
    grouped.set(requestId, event);
  }
  return [...grouped.values()]
    .sort((a,b)=>b.updated_at-a.updated_at || b._rank-a._rank || a.request_id.localeCompare(b.request_id))
    .slice(0,24)
    .map(({_rank,_record,...task})=>task);
}

export function restoreWorkbenchTasks(snapshot, records, options = {}) {
  const next = projectWorkbenchTasks(records, options);
  if (!snapshot || typeof snapshot !== 'object' || !Array.isArray(snapshot.tasks)) return next;
  const byRequest = new Map(next.map(task => [task.request_id, task]));
  for (const cached of snapshot.tasks) {
    if (!cached || typeof cached !== 'object' || !REQUEST_ID.test(String(cached.request_id || ''))) continue;
    if (options.subject && cached.subject && cached.subject !== options.subject) continue;
    if (!byRequest.has(cached.request_id)) {
      byRequest.set(cached.request_id, {
        ...cached,
        connection_state: 'reconnecting',
        source: 'server-facts-reconnect',
      });
    }
  }
  return [...byRequest.values()].slice(0,24);
}

export async function apply(ctx) {
  const port = process.env.COMPANY_AGENT_DSH_PORT ?? '3081';
  if (!/^[0-9]+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
    throw new Error('COMPANY_AGENT_DSH_PORT must be an integer from 1 to 65535');
  }
  const authority = `127.0.0.1:${Number(port)}`;
  const trustedRequest = req => trusted(req, authority);
  const trustedSubject = req => resolveTrustedSubject(ctx.connection, req);
  const subprocessEnvFor = req => ({...process.env, COMPANY_AGENT_SUBJECT: trustedSubject(req)});
  const [client, css, layoutModel, page] = await Promise.all([
    readFile(new URL('client.js', import.meta.url), 'utf8'),
    readFile(new URL('workspace.css', import.meta.url), 'utf8'),
    readFile(new URL('layout-model.js', import.meta.url), 'utf8'),
    readFile(new URL('docs/quantum-agent-architecture.zh-CN.html', ROOT), 'utf8'),
  ]);
  const bundle = layoutModel + '\n' + client;
  const rev = createHash('sha256').update(bundle).update(css).digest('hex').slice(0,12);
  const content = page.replace(/<iframe id="dsh-native-frame"[\s\S]*?<\/iframe>/, '')
    .replace("frame-src http://127.0.0.1:3081", "frame-src 'self'")
    .replace('</head>', `<style>
      body.content-embed{overflow:hidden}body.content-embed>.masthead,body.content-embed main>.hero,body.content-embed main>.tabs,body.content-embed main>.footer{display:none!important}
      body.content-embed .workspace-bar,body.content-embed .mobile-panels,body.content-embed .workspace-nav,body.content-embed .chat{display:none!important}
      body.content-embed .workspace-grid{display:block!important;flex:1;min-height:0}
      body.content-embed .workspace-center{display:flex!important;height:100%;max-height:none}
      body.content-embed main.shell{max-width:none;padding:0}body.content-embed .workspace{height:100vh;height:100dvh;border:0;border-radius:0}
      body.content-embed #panel-workspace{padding:0}
    </style></head>`)
    .replace('<body data-audience="external">', '<body data-audience="external" class="content-embed">')
    .replace('</body>', `<script>
      selectTab('workspace',false,false);
      const allowedViews=new Set(['welcome','cloud','hpc','knowledge','capture','development','daily','canvas','results','file-local-readme','file-local-input']);
      addEventListener('message',event=>{
        if(event.origin!==location.origin||event.source!==parent||!event.data||event.data.type!=='company-content-open')return;
        if(allowedViews.has(event.data.view))renderView(event.data.view);
      });
      parent.postMessage({type:'company-content-ready'},location.origin);
    <\/script></body>`);

  // Server-side proxy for cloud/HPC connection data. Tokens never enter model or front-end storage.
  // Precedence per field: config file (saved from the workspace settings page) > process env > default.
  const configPath = process.env.UQC_WORKSPACE_CONFIG || join(homedir(), '.config', 'unitqc', 'workspace.json');
  let savedConfig = {};
  try {
    const parsed = JSON.parse(await readFile(configPath, 'utf8'));
    if (parsed && typeof parsed === 'object') savedConfig = parsed;
  } catch {}
  const cleanValue = value => typeof value === 'string' ? value.trim().replace(/\/+$/, '') : '';
  const CONFIG = {
    cloudApi: cleanValue(savedConfig.cloudApi || process.env.UQC_CLOUD_API_BASE_URL) || 'http://cloud.unitaryqubit.com:8003',
    cloudKey: cleanValue(savedConfig.cloudKey || process.env.UQC_CLOUD_API_KEY),
    cloudPortal: cleanValue(savedConfig.cloudPortal || process.env.UQC_CLOUD_PORTAL) || 'https://220.178.61.185:8443',
    hpcPortal: cleanValue(savedConfig.hpcPortal || process.env.HPC_PORTAL) || 'http://192.168.110.37',
    hpcGateway: cleanValue(savedConfig.hpcGateway || process.env.HPC_GATEWAY),
    hpcJobs: cleanValue(savedConfig.hpcJobsUrl || process.env.HPC_JOBS_URL),
    hpcToken: cleanValue(savedConfig.hpcToken || process.env.HPC_TOKEN),
    hpcUser: cleanValue(savedConfig.hpcUser || process.env.HPC_USER),
    hpcHost: cleanValue(savedConfig.hpcHost || process.env.HPC_HOST)
  };
  const saveConfigUpdates = async updates => {
    const next = {...savedConfig, ...updates};
    savedConfig = next;
    await mkdir(dirname(configPath), {recursive:true}).catch(() => {});
    await writeFile(configPath, JSON.stringify(next, null, 2) + '\n', {mode:0o600});
    await chmod(configPath, 0o600).catch(() => {});
  };
  // Unified account management: users apply for platform access from the settings
  // page; an authorized administrator grants it server-side. Users never touch
  // credentials — the agent account is managed centrally and credentials are
  // injected into the server-side config on grant.
  const accessPath = join(dirname(configPath), 'workspace-access.json');
  const adminTokenPath = join(dirname(configPath), 'admin-token');
  const accessRead = async () => {
    try {
      const parsed = JSON.parse(await readFile(accessPath, 'utf8'));
      return parsed && Array.isArray(parsed.requests) ? parsed : {requests:[]};
    } catch {return {requests:[]};}
  };
  const accessWrite = async state => {
    await mkdir(dirname(accessPath), {recursive:true}).catch(() => {});
    await writeFile(accessPath, JSON.stringify(state, null, 2) + '\n', {mode:0o600});
    await chmod(accessPath, 0o600).catch(() => {});
  };
  const adminToken = async () => {
    try {const token = (await readFile(adminTokenPath, 'utf8')).trim(); if (token) return token;} catch {}
    const token = randomBytes(24).toString('hex');
    await mkdir(dirname(adminTokenPath), {recursive:true}).catch(() => {});
    await writeFile(adminTokenPath, token + '\n', {mode:0o600});
    await chmod(adminTokenPath, 0o600).catch(() => {});
    return token;
  };
  // Constant-time comparison over fixed-length SHA-256 digests: the presented
  // grant token never opens a timing/length oracle on the stored secret.
  const adminTokenMatches = async candidate => {
    if (!candidate) return false;
    const secret = await adminToken();
    return timingSafeEqual(
      createHash('sha256').update(candidate).digest(),
      createHash('sha256').update(secret).digest()
    );
  };
  const planOpen = kind => kind === 'cloud' ? Boolean(CONFIG.cloudKey) : Boolean(CONFIG.hpcUser && CONFIG.hpcHost);
  // Accepts field names exactly as sent from the workspace settings page. Field names are fixed
  // here, not taken from arbitrary strings; every value is length/range limited before use.
  // Credentials are NOT accepted here (access-seam doc §2: settings POST is
  // non-sensitive fields only) — the credential write-in is solely the grant
  // endpoint's job, keeping "user pastes a key" from reappearing as a path.
  const saveSettings = async payload => {
    const updates = {};
    for (const field of ['cloudApi','cloudPortal','hpcPortal','hpcGateway','hpcUser','hpcHost']) {
      const raw = payload[field];
      if (typeof raw !== 'string' || !raw.trim()) continue;
      const value = raw.trim().replace(/\/+$/, '');
      if (value.length > 512) return {error:`${field} 超过长度上限`};
      if (field !== 'hpcUser' && field !== 'hpcHost' && !/^https?:\/\//i.test(value)) return {error:`${field} 必须是 http/https 地址`};
      updates[field] = value;
      CONFIG[field] = value;
    }
    if (typeof payload.hpcUser === 'string' && payload.hpcUser.trim() && !/^[A-Za-z0-9._-]{1,64}$/.test(payload.hpcUser.trim())) return {error:'hpcUser 含非法字符'};
    if (typeof payload.hpcHost === 'string' && payload.hpcHost.trim() && !/^[A-Za-z0-9.:_-]{1,253}$/.test(payload.hpcHost.trim())) return {error:'hpcHost 含非法字符'};
    if (payload.cloudKey !== undefined || payload.cloudKeyClear !== undefined || payload.hpcToken !== undefined) {
      return {error:'凭据由服务端统一注入：请在「平台连接」页申请开通，不走本端点'};
    }
    if (!Object.keys(updates).length) return {error:'没有可保存的字段'};
    try {
      await saveConfigUpdates(updates);
    } catch (exc) {
      return {error:'写入服务端配置失败：' + String(exc && exc.message || exc).slice(0, 80)};
    }
    invalidateServiceCache();
    return {
      cloudKeySet: Boolean(CONFIG.cloudKey),
      cloudApi: CONFIG.cloudApi,
      cloudPortal: CONFIG.cloudPortal,
      hpcUser: CONFIG.hpcUser,
      hpcHost: CONFIG.hpcHost,
      hpcPortal: CONFIG.hpcPortal,
      note:'密钥不回显；状态接口有最多 20 秒缓存，稍后刷新即生效。'
    };
  };
  const cache = new Map();
  const cacheKeyFor = (key, req) => scopedFactKey(key, trustedSubject(req));
  const invalidateCache = key => {
    for (const cachedKey of cache.keys()) if (cachedKey === key || cachedKey.startsWith(`${key}:`)) cache.delete(cachedKey);
  };
  const cached = (key, ttlSeconds, fn, req) => {
    const scopedKey = cacheKeyFor(key, req);
    const hit = cache.get(scopedKey);
    if (hit && Date.now() - hit.at < ttlSeconds * 1000) return Promise.resolve(hit.data);
    return fn().then(data => {cache.set(scopedKey, {at:Date.now(), data});return data;},
                    error => {const data = {error:String(error && error.message || error).slice(0,160)};cache.set(scopedKey,{at:Date.now(),data});return data;});
  };
  const invalidateServiceCache = () => {
    for (const key of ['cloud-status','cloud-overview','hpc-status','hpc-overview','cloud-probe','hpc-portal-probe','agent-state']) invalidateCache(key);
  };
  const probePortal = async url => {
    try {
      const target = new URL(url);
      const request = target.protocol === 'https:' ? httpsRequest : httpRequest;
      return await new Promise(resolveProbe => {
        const req = request(target, {method:'HEAD',timeout:7000,agent:target.protocol === 'https:' ? new HttpsAgent({rejectUnauthorized:false}) : undefined}, res => {
          res.resume();
          resolveProbe({status:res.statusCode || 0,headers:Object.fromEntries(Object.entries(res.headers).map(([key,value])=>[key,String(Array.isArray(value)?value[0]||'':value||'')]))});
        });
        req.once('timeout',()=>req.destroy(new Error('timeout')));
        req.once('error',error=>resolveProbe({status:0,error:String(error && error.message || error).slice(0,120)}));
        req.end();
      });
    } catch (error) {
      return {status:0,error:String(error && error.message || error).slice(0,120)};
    }
  };
  const flat = body => {
    const root = body && typeof body === 'object' ? ('data' in body ? body.data : body) : null;
    if (Array.isArray(root)) return root;
    if (root && typeof root === 'object') for (const key of ['list','items','tasks','records','rows','devices']) if (Array.isArray(root[key])) return root[key];
    return null;
  };
  const scalar = v => (v === null || v === undefined || typeof v === 'object') ? '' : String(v).slice(0,80);
  const pick = (m, ...names) => {for (const name of names) if (m[name]) return m[name];return '';};
  const rows = (body, limit, keys) => {
    const list = flat(body);
    if (!list) return null;
    return list.slice(0, limit).map(item => {
      if (!item || typeof item !== 'object') return {raw:scalar(item)};
      const m = {};let count = 0;
      for (const [k, v] of Object.entries(item)) {if (count >= 40) break;if (typeof v !== 'object') {m[k.toLowerCase()] = scalar(v);count++;}}
      return Object.fromEntries(keys.map(([field, ...names]) => [field, pick(m, ...names)]));
    });
  };
  // Cloud status is verified over the official Socket.IO SDK (uqc_client). The
  // sk- prefixed API key authenticates at the Socket.IO layer; the REST gateway
  // (/api/v1/*) is a separate auth layer and would reject it with a false
  // INVALID_API_KEY. The probe script receives the key via env (never argv) and
  // prints exactly one JSON line; the key never leaves this process.
  const cloudProbeCandidates = () => {
    const list = [];
    // Interpreter choice is env-driven for deployment; the two trailing
    // entries are fallback conveniences: a known on-host venv that ships
    // uqc_client, then the system python3. Candidates whose interpreter or
    // module is missing simply fail through to the next entry, so foreign
    // hosts degrade to python3 without configuration.
    if (process.env.UQC_CLOUD_PROBE_PYTHON) list.push(process.env.UQC_CLOUD_PROBE_PYTHON);
    list.push('/home/sunhl/projects/qchem_qml_md/.venv/bin/python', 'python3');
    return list.filter((value, index) => list.indexOf(value) === index);
  };
  const cloudProbe = (req) => cached('cloud-probe', 15, async () => {
    let lastError = '';
    for (const python of cloudProbeCandidates()) {
      try {
        const uqcEnv = {...process.env,
        UQC_CLOUD_API_KEY: CONFIG.cloudKey,
        UQC_CLOUD_HOST: (() => {try {return new URL(CONFIG.cloudApi).hostname;} catch {return '';}})(),
        UQC_CLOUD_PORT: (() => {try {return String(new URL(CONFIG.cloudApi).port || '8003');} catch {return '';}})()
      };
      for (const key of Object.keys(uqcEnv)) if (uqcEnv[key] === undefined) delete uqcEnv[key];
      const {stdout} = await run(python,
        [new URL('uqc-cloud-probe.py', import.meta.url).pathname],
        {timeout:50000, maxBuffer:256 * 1024, windowsHide:true, env:{...uqcEnv, COMPANY_AGENT_SUBJECT:trustedSubject(req)}});
      const line = String(stdout).trim().split('\n').filter(Boolean).pop() || '';
        return JSON.parse(line);
      } catch (exc) {
        lastError = String(exc && (exc.message || exc)).slice(0,120);
        // Missing interpreter/module: try next candidate; a parse/probe failure
        // with a finished JSON payload is handled above.
      }
    }
    return {connected:false, reason:'probe_error', detail:lastError};
  });
  const cloudStatus = (req) => cached('cloud-status', 20, async () => {
    if (!CONFIG.cloudKey) return {connected:false, reason:'missing_api_key', apiBase:CONFIG.cloudApi, portal:CONFIG.cloudPortal};
    const probe = await cloudProbe(req);
    const base = {apiBase:CONFIG.cloudApi, portal:CONFIG.cloudPortal};
    if (probe.connected) return {connected:true, ...base};
    return {connected:false, reason:probe.reason || 'unreachable', detail:String(probe.detail || '').slice(0,160), ...base};
  });
  const cloudOverview = (req) => cached('cloud-overview', 15, async () => {
    if (!CONFIG.cloudKey) return {reason:'missing_api_key', devices:null, jobs:[]};
    const probe = await cloudProbe(req);
    if (!probe.connected) return {reason:probe.reason || 'unreachable', devices:null, jobs:[], detail:String(probe.detail || '').slice(0,160)};
  return {
    reason:'ok',
    devices: Array.isArray(probe.chips) ? probe.chips : null,
    jobs: [],
    files: [],
    filesNote: '云平台 SDK 当前没有远端文件夹浏览接口；云端文件通过提交工具上传、结果工具回收。'
  };
  });
  const sshTarget = () => /^[A-Za-z0-9._-]+@[A-Za-z0-9.:_-]+$/.test(`${CONFIG.hpcUser}@${CONFIG.hpcHost}`)
    ? `${CONFIG.hpcUser}@${CONFIG.hpcHost}` : '';
  const sshRun = async command => run('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=accept-new', sshTarget(), command],
    {timeout:20000, maxBuffer:256 * 1024, windowsHide:true});
  const hpcStatus = (req) => cached('hpc-status', 20, async () => {
    if (!CONFIG.hpcPortal) return {connected:false, reason:'unconfigured', gateway:CONFIG.hpcGateway};
    const probe = await cached('hpc-portal-probe', 30, () => probePortal(CONFIG.hpcPortal), req);
    if (probe.error || !probe.status) return {connected:false, reason:'unreachable', detail:probe.error, portal:CONFIG.hpcPortal};
    const headers = probe.headers || {};
    const policy = /sameorigin/i.test(headers['x-frame-options'] || '') ? 'self' :
      /deny/i.test(headers['x-frame-options'] || '') ? 'deny' :
      /frame-ancestors/i.test(headers['content-security-policy'] || '') && !/\(https?:/.test(headers['content-security-policy'] || '') ? 'csp' : 'allowed';
    if (!sshTarget()) return {connected:false, sshOk:false, reason:'unconfigured', gateway:CONFIG.hpcGateway,
      portal:CONFIG.hpcPortal, embeddable:true, framePolicy:'proxied'};
    let sshOk = false, sshDetail = '';
    try {await sshRun('true');sshOk = true;} catch (exc) {sshDetail = String(exc && exc.message || exc).slice(0,120);}
    return {connected:sshOk, sshOk, sshDetail, reason:sshOk ? 'ok' : 'portal_ok_without_ssh',
      portal:CONFIG.hpcPortal, host:CONFIG.hpcHost, user:CONFIG.hpcUser, embeddable:true, framePolicy:'proxied'};
  });
  const hpcOverview = (req) => cached('hpc-overview', 15, async () => {
    if (!sshTarget()) return {reason:'unconfigured', running:null, history:null};
    try {
      const {stdout} = await sshRun(`squeue -u $USER -h -o '%.18i %.30j %.9P %.12T %.10M %.12S' ; echo '##' ; sacct -u $USER -S $(date -d '-7 days' +%Y-%m-%d) --noheader -P -o 'JobID,JobName%30,Partition,State,Elapsed,Start,End' | grep -v '\\.batch\\|\\.extern\\|\\.0' | tail -25`);
      const [live, hist] = stdout.split('##');
      const liveRows = live.trim().split('\n').filter(Boolean).map(line => {
        const [id, job, part, state, elapsed, start] = line.trim().split(/\s+/).map(c => c.trim().slice(0,60));
        return {id, job, part, state, elapsed, start};
      });
      const histRows = hist.trim().split('\n').filter(Boolean).map(line => {
        const [id, job, part, state, elapsed, start, end] = line.trim().split('|').map(c => c.trim().slice(0,60));
        return {id, job, part, state, elapsed, start, end};
      }).filter(j => j.id && j.state);
      let files = [];
      try {
        const fileResult = await sshRun("find \"$HOME\" -maxdepth 1 -mindepth 1 -printf '%f\\t%y\\n' | head -64");
        if (fileResult.stdout) files = fileResult.stdout.split('\\n').filter(Boolean).slice(0,64).map(line => {
          const [name, kind] = line.split('\\t');
          return {name: String(name || '').slice(0,160), kind: kind === 'd' ? 'directory' : 'file'};
        });
      } catch {}
      return {reason:'ok', running:liveRows.slice(0, 15), history:histRows.slice(-15).reverse(),
        files, filesNote: 'HPC 远端目录通过 SSH 读取；文件上传、下载、创建和删除仍由对话工具执行并逐次审批。'};
    } catch (exc) {
      return {reason:'unreachable', detail:String(exc && exc.message || exc).slice(0,140), running:null, history:null};
    }
  });
  const subjectHeader = (req, subjectValue) => {
    if (req && req.headers) req.headers['x-company-agent-subject'] = subjectValue;
  };
  const jsonRoute = (path, handler, tag) => ctx.effect(() => ctx.webServer.register({kind:'exact', path, handler:async (req, res) => {
    if (!trustedRequest(req)) {res.writeHead(403);res.end();return;}
    if (ctx.connection.requestRejection) {
      const reject = ctx.connection.requestRejection(req);
      if (reject) {res.writeHead(reject, {'content-type':'application/json'});res.end('{"error":"unauthorized"}');return;}
    } else if (ctx.connection.authorizeIndex && !ctx.connection.authorizeIndex(req, res)) return;
    if (req.method!=='GET') {res.writeHead(405);res.end();return;}
    const subjectValue = trustedSubject(req);
    subjectHeader(req, subjectValue);
    res.writeHead(200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
    res.end(JSON.stringify(await handler(req)));
  }}), tag);
  const portalRoute = (kind) => ctx.effect(() => ctx.webServer.register({kind:'prefix', path:`/company-workspace/portal/${kind}`, handler:async (req, res) => {
    if (!sessionGate(req, res)) return;
    if (!['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'].includes(req.method)) {res.writeHead(405);res.end();return;}
    const base = kind === 'cloud' ? CONFIG.cloudPortal : CONFIG.hpcPortal;
    const prefix = `/company-workspace/portal/${kind}`;
    if (!base) {res.writeHead(404);res.end('portal not configured');return;}
    const requestPath = new URL(req.url || '/', 'http://workspace.local').pathname;
    const suffix = requestPath.startsWith(prefix) ? requestPath.slice(prefix.length) || '/' : '/';
    let target;
    try {target = new URL(base + suffix + (new URL(req.url || '/', 'http://workspace.local').search));}
    catch {res.writeHead(502);res.end();return;}
    const request = target.protocol === 'https:' ? httpsRequest : httpRequest;
    const portalCookiePrefix = `UQC_PORTAL_${kind.toUpperCase()}_`;
    const portalCookieHeader = String(req.headers.cookie || '').split(';').map(part => part.trim()).filter(part => part.startsWith(portalCookiePrefix)).map(part => part.slice(portalCookiePrefix.length)).join('; ');
    const headers = {accept:req.headers.accept || '*/*', 'user-agent':'UNITQC Agent workspace portal'};
    if (portalCookieHeader) headers.cookie = portalCookieHeader;
    for (const key of ['content-type','content-length','x-requested-with','accept-language']) if (req.headers[key]) headers[key] = req.headers[key];
    const options = {method:req.method,headers,agent:target.protocol === 'https:' ? new HttpsAgent({rejectUnauthorized:false}) : undefined};
    const rewriteLocation = value => {
      if (!value) return value;
      try {
        const parsed = new URL(value, target);
        if (parsed.origin !== target.origin) return value;
        return prefix + parsed.pathname + parsed.search + parsed.hash;
      } catch {return value;}
    };
    const escapedPrefix = prefix.slice(1).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const rewriteText = text => text
      .replace(new RegExp(`(['"])\\/(?![\\/]|${escapedPrefix}\\/)`, 'g'), `$1${prefix}/`)
      .replace(new RegExp(`(url\\(\\s*)\\/(?!\\/|${escapedPrefix}\\/)`, 'gi'), `$1${prefix}/`);
    const forwardBody = ['GET','HEAD','OPTIONS'].includes(req.method) ? Promise.resolve(null) : new Promise(resolveBody => {
      const chunks = [];
      let bytes = 0;
      req.on('data', chunk => {bytes += chunk.length;if (bytes <= 2 * 1024 * 1024) chunks.push(Buffer.from(chunk));});
      req.on('end', () => resolveBody(bytes <= 2 * 1024 * 1024 ? Buffer.concat(chunks) : null));
      req.on('error', () => resolveBody(null));
    });
    const upstream = request(target, options, remote => {
      const headers = {};
      for (const [key,value] of Object.entries(remote.headers)) {
        if (['content-security-policy','x-frame-options','content-length','content-encoding','transfer-encoding','location','set-cookie'].includes(key)) continue;
        if (value !== undefined) headers[key] = value;
      }
      if (remote.headers['set-cookie']) {
        const cookies = Array.isArray(remote.headers['set-cookie']) ? remote.headers['set-cookie'] : [remote.headers['set-cookie']];
        headers['set-cookie'] = cookies.map(cookie => `${portalCookiePrefix}${String(cookie).replace(/;\s*(?:domain|path|secure|httponly|samesite)[^;]*/ig, '').replace(/=.*/, match => match)}; Path=/`);
      }
      if (remote.headers.location) headers.location = rewriteLocation(String(remote.headers.location));
      headers['cache-control'] = 'no-store';
      const contentType = String(remote.headers['content-type'] || '').toLowerCase();
      const rewritable = /^(?:text\/(?:html|css)|(?:application|text)\/javascript)/.test(contentType);
      if (req.method === 'HEAD' || !rewritable) {
        res.writeHead(remote.statusCode || 502, headers);
        if (req.method === 'HEAD') {remote.resume();res.end();} else remote.pipe(res);
        return;
      }
      const chunks = [];
      let bytes = 0;
      remote.on('data', chunk => {bytes += chunk.length;if (bytes <= 8 * 1024 * 1024) chunks.push(chunk);});
      remote.on('end', () => {
        if (bytes > 8 * 1024 * 1024) {res.writeHead(502, {'content-type':'text/plain; charset=utf-8'});res.end('portal response too large');return;}
        const body = rewriteText(Buffer.concat(chunks).toString('utf8'));
        res.writeHead(remote.statusCode || 502, headers);
        res.end(body);
      });
      remote.on('error', error => {if (!res.headersSent) {res.writeHead(502, {'content-type':'text/plain; charset=utf-8'});res.end('portal unavailable');} else res.destroy(error);});
    });
    upstream.once('timeout',()=>upstream.destroy(new Error('timeout')));
    upstream.once('error',error=>{if (!res.headersSent) {res.writeHead(502, {'content-type':'text/plain; charset=utf-8'});res.end('portal unavailable');} else res.destroy(error);});
    forwardBody.then(body => {if (body === null && !['GET','HEAD','OPTIONS'].includes(req.method)) {upstream.destroy();return;}if (body) upstream.write(body);upstream.end();});
  }}), `company-workspace: ${kind} portal proxy`);
  portalRoute('cloud');
  portalRoute('hpc');
  const workspaceRegistry = ctx.workspaceRegistry;
  if (!workspaceRegistry || typeof workspaceRegistry.list !== 'function') {
    throw new Error('company workspace shell requires the DSH Workspace registry');
  }
  const workspaceState = () => {
    const rows = workspaceRegistry?.list?.() || [];
    return {
      ready: rows.length > 0,
      workspaces: rows.slice(0, 32).map(row => ({
        workspaceId: String(row.id || ''),
        title: String(row.title || row.path || '').slice(0, 160),
        path: String(row.path || '').slice(0, 2048),
        sessionCount: Array.isArray(row.sessionIds) ? row.sessionIds.length : 0,
        updatedAt: String(row.updatedAt || ''),
      })),
      note: rows.length > 0
        ? '本机文件根目录来自 DSH 当前 Workspace。'
        : '请先用 DSH 原生工作区选择器选择真实本机目录，再创建会话。',
    };
  };
  const localFiles = async (workspaceId, relativePath = '') => {
    const row = (workspaceRegistry?.list?.() || []).find(item => String(item.id) === workspaceId);
    if (!row || typeof row.path !== 'string') return {error:'workspace unavailable'};
    const root = resolve(row.path);
    const clean = String(relativePath || '').replace(/\\\\/g, '/');
    if (clean.split('/').some(part => !part || part === '.' || part === '..')) return {error:'invalid path'};
    const target = resolve(root, clean || '.');
    if (target !== root && !target.startsWith(root + sep)) return {error:'path outside workspace'};
    let info;
    try { info = await lstat(target); } catch { return {error:'path unavailable'}; }
    if (!info.isDirectory() || info.isSymbolicLink()) return {error:'directory unavailable'};
    const entries = [];
    try {
      for (const entry of await readdir(target, {withFileTypes:true})) {
        if (entries.length >= 64) break;
        let size = 0;
        try { if (entry.isFile()) size = (await lstat(resolve(target, entry.name))).size; } catch {}
        entries.push({name:entry.name.slice(0,256), kind:entry.isDirectory()?'directory':entry.isFile()?'file':'other', bytes:size});
      }
    } catch { return {error:'directory unreadable'}; }
    return {workspaceId, path:clean, entries};
  };
  const agentState = (req) => cached('agent-state', 10, async () => {
    const python = process.env.COMPANY_AGENT_PYTHON;
    if (!python || !python.trim()) return {available:false, reason:'unconfigured'};
    const call = args => run(python, ['-P','-m','company_agent.cli', ...args],
      {timeout:12000, maxBuffer:256 * 1024, windowsHide:true, env:subprocessEnvFor(req)}).then(
      r => {const body=JSON.parse(String(r.stdout||'{}')||'{}');return body;}, () => null);
    const [doctor, reconcile] = await Promise.all([
      call(['doctor']),
      call(['reconcile','--limit','24']).catch(() => null)
    ]);
    const healthy = doctor && typeof doctor === 'object' && !doctor.error;
    return {
      available: Boolean(healthy),
      knowledge_governance: healthy ? (doctor.knowledge_governance || null) : null,
      skills_governance: healthy ? (doctor.skills_governance || null) : null,
      tenants_governance: healthy ? (doctor.tenants_governance || null) : null,
      receipts: healthy ? {
        unknown_outcomes: Math.max(0, Math.min(Number(((doctor.receipts||{}).unknown_outcomes ?? 0)) || 0, 200))
      } : null,
      workspace: workspaceState(),
      unknown: Array.isArray(reconcile && reconcile.unknown) ? reconcile.unknown.slice(0, 6) : [],
      note: reconcile && typeof reconcile.note === 'string' ? reconcile.note.slice(0, 180) : ''
    };
  });
  const workbenchTasks = async (req) => {
    const python = process.env.COMPANY_AGENT_PYTHON;
    if (!python || !python.trim()) return {available:false, tasks:[], reason:'unconfigured'};
    const result = await run(python, ['-P','-m','company_agent.cli', 'reconcile', '--limit', '24'],
      {timeout:12000, maxBuffer:256 * 1024, windowsHide:true, env:subprocessEnvFor(req)}).then(
      value => {try{return JSON.parse(String(value.stdout || '{}'));}catch{return null;}},
      () => null);
    if (!result || result.available !== true) return {available:false, tasks:[], reason:'receipt_unavailable'};
    const records = Array.isArray(result.recent) ? result.recent : [];
    return {available:true, tasks:projectWorkbenchTasks(records, {subject:trustedSubject(req)})};
  };
  jsonRoute('/company-workspace/workbench/tasks', workbenchTasks, 'company-workspace: workbench tasks');
  jsonRoute('/company-workspace/agent/state', agentState, 'company-workspace: agent state');
  jsonRoute('/company-workspace/cloud/status', cloudStatus, 'company-workspace: cloud status');
  jsonRoute('/company-workspace/cloud/overview', cloudOverview, 'company-workspace: cloud overview');
  jsonRoute('/company-workspace/hpc/status', hpcStatus, 'company-workspace: hpc status');
  jsonRoute('/company-workspace/hpc/overview', hpcOverview, 'company-workspace: hpc overview');
  ctx.effect(() => ctx.webServer.register({kind:'exact', path:'/company-workspace/settings', handler:async (req, res) => {
    if (!trustedRequest(req)) {res.writeHead(403);res.end();return;}
    if (ctx.connection.requestRejection) {
      const reject = ctx.connection.requestRejection(req);
      if (reject) {res.writeHead(reject, {'content-type':'application/json'});res.end('{"error":"unauthorized"}');return;}
    } else if (ctx.connection.authorizeIndex && !ctx.connection.authorizeIndex(req, res)) return;
    if (req.method === 'GET') {
      // Non-secret view of the current connection config. Sites bake these values
      // server-side; the page only asks the user for account + credential.
      res.writeHead(200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
      res.end(JSON.stringify({
        cloudApi:CONFIG.cloudApi, cloudPortal:CONFIG.cloudPortal, cloudKeySet:Boolean(CONFIG.cloudKey),
        hpcUser:CONFIG.hpcUser, hpcHost:CONFIG.hpcHost, hpcPortal:CONFIG.hpcPortal
      }));
      return;
    }
    if (req.method !== 'POST') {res.writeHead(405, {'content-type':'application/json'});res.end('{"error":"method"}');return;}
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 8192) {req.destroy();return;}
    });
    req.on('end', async () => {
      let payload = null;
      try {payload = JSON.parse(body || 'null');} catch {}
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        res.writeHead(400, {'content-type':'application/json; charset=utf-8'});
        res.end('{"error":"invalid_payload"}');
        return;
      }
      const result = await saveSettings(payload);
      res.writeHead(result.error ? 400 : 200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
      res.end(JSON.stringify(result));
    });
  }}), 'company-workspace: settings save');
  // Unified access management: status/query & apply are gated by the browser session;
  // the grant endpoint authenticates the administrator with a shared admin token
  // stored server-side (0600), never handed to the model or front-end.
  const sessionGate = (req, res) => {
    if (!trustedRequest(req)) {res.writeHead(403);res.end();return false;}
    if (ctx.connection.requestRejection) {
      const reject = ctx.connection.requestRejection(req);
      if (reject) {res.writeHead(reject, {'content-type':'application/json'});res.end('{"error":"unauthorized"}');return false;}
    } else if (ctx.connection.authorizeIndex && !ctx.connection.authorizeIndex(req, res)) return false;
    return true;
  };
  const settingsGate = async (req, res) => {
    if (!trustedRequest(req)) {res.writeHead(403);res.end();return false;}
    // Grant is the one endpoint outside the browser-session seat: only the
    // x-admin-token matching the service-side 0600 secret may call it — no
    // session fallback, or any signed-in user could self-grant and inject
    // credentials (access-seam doc §2, change requires contract-level review).
    const token = (req.headers['x-admin-token'] || '').toString();
    if (token.trim() && await adminTokenMatches(token.trim())) return true;
    res.writeHead(401, {'content-type':'application/json'});
    res.end('{"error":"unauthorized"}');
    return false;
  };
  const readJson = (req, res, handle) => {
    let body = '';
    req.on('data', chunk => {body += chunk; if (body.length > 8192) {req.destroy();return;}});
    req.on('end', async () => {
      let payload = null;
      try {payload = JSON.parse(body || 'null');} catch {}
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        res.writeHead(400, {'content-type':'application/json; charset=utf-8'});
        res.end('{"error":"invalid_payload"}');
        return;
      }
      const result = await handle(payload);
      res.writeHead(result.error ? 400 : 200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
      res.end(JSON.stringify(result));
    });
  };
  ctx.effect(() => ctx.webServer.register({kind:'exact', path:'/company-workspace/access', handler:async (req, res) => {
    if (!sessionGate(req, res)) return;
    if (req.method === 'GET') {
      const state = await accessRead();
      res.writeHead(200, {'content-type':'application/json; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
      res.end(JSON.stringify({cloud:{open:planOpen('cloud')}, hpc:{open:planOpen('hpc')}, requests:state.requests.slice(-20).reverse()}));
      return;
    }
    if (req.method !== 'POST') {res.writeHead(405, {'content-type':'application/json'});res.end('{"error":"method"}');return;}
    readJson(req, res, async payload => {
      const kind = payload.kind;
      if (kind !== 'cloud' && kind !== 'hpc') return {error:'kind 必须是 cloud 或 hpc'};
      const account = payload.account ? String(payload.account).trim().slice(0, 80) : '';
      const state = await accessRead();
      state.requests.push({id:String(Date.now()), kind, account, requestedAt:new Date().toISOString(), status:'pending'});
      await accessWrite(state);
      return {ok:true, pending:true};
    });
  }}), 'company-workspace: access request');
  ctx.effect(() => ctx.webServer.register({kind:'exact', path:'/company-workspace/access/grant', handler:async (req, res) => {
    if (!await settingsGate(req, res)) return;
    if (req.method !== 'POST') {res.writeHead(405, {'content-type':'application/json'});res.end('{"error":"method"}');return;}
    readJson(req, res, async payload => {
      const kind = payload.kind;
      if (kind !== 'cloud' && kind !== 'hpc') return {error:'kind 必须是 cloud 或 hpc'};
      if (kind === 'hpc') {
        const account = String(payload.account || '').trim().slice(0, 80);
        if (account) {const result = await saveSettings({hpcUser:account}); if (result.error) return result;}
      }
      if (payload.cloudKey) {
        const key = String(payload.cloudKey).trim();
        if (key.length > 512) return {error:'cloudKey 超过长度上限'};
        // Credentials enter the config only through this grant path (0600),
        // never through the ordinary settings endpoint.
        const result = await saveConfigUpdates({cloudKey:key}).then(
          () => {CONFIG.cloudKey = key;return {};},
          exc => {return {error:'写入服务端配置失败：' + String(exc && exc.message || exc).slice(0, 80)};}
        );
        if (result.error) return result;
      }
      const state = await accessRead();
      let updated = 0;
      state.requests.forEach(request => {
        if (request.kind === kind && request.status === 'pending') {request.status = 'granted';request.grantedAt = new Date().toISOString();updated++;}
      });
      await accessWrite(state);
      invalidateServiceCache();
      return {ok:true, granted:{kind, open:planOpen(kind), requestsUpdated:updated}};
    });
  }}), 'company-workspace: access grant');

  const files = new Map([
    ['/company-workspace/client.js', [bundle, 'text/javascript; charset=utf-8']],
    ['/company-workspace/workspace.css', [css, 'text/css; charset=utf-8']],
    ['/company-workspace/content', [content, 'text/html; charset=utf-8']],
  ]);
  for (const [path,[body,type]] of files) ctx.effect(() => ctx.webServer.register({kind:'exact',path,handler:(req,res) => {
    if (!trustedRequest(req)) {res.writeHead(403);res.end();return;}
    if (!ctx.connection.authorizeIndex(req,res)) return;
    if (!['GET','HEAD'].includes(req.method)) {res.writeHead(405);res.end();return;}
    res.writeHead(200, {'content-type':type,'cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'});
    res.end(req.method === 'HEAD' ? undefined : body);
  }}), 'company-workspace: UI resource');

  // Compose additively on top of the native shell: the native layout,
  // conversation, workspace, settings and renderer factories stay fully
  // active, and this plugin only appends its own entry (resource tab,
  // receipt view and settings pages ride native slots).
  const assemble = `(()=>{
    if(new URL(location.href).searchParams.get('native')==='1')return;
    const graph=globalThis.__DSH_BOOT__;
    if(!graph||graph.entries.some(e=>e.id===${JSON.stringify(ID)}))return;
    graph.entries.push({id:${JSON.stringify(ID)},url:'/company-workspace/client.js',rev:${JSON.stringify(rev)},inject:['@deepseek-ai/dsh-client-ui-renderer','@deepseek-ai/dsh-client-ui-session','@deepseek-ai/dsh-client-ui-theme','@deepseek-ai/dsh-client-locale'],immediately:true});
    graph.batches.push({phase:'application',url:'/company-workspace/client.js',rev:${JSON.stringify(rev)},entries:[${JSON.stringify(ID)}]});
    graph.rev+='-company-${rev}';
    const link=document.createElement('link');link.rel='stylesheet';link.href='/company-workspace/workspace.css';document.head.append(link);
  })()`;
  ctx.effect(() => ctx.webServer.tapIndex(html => html.replace('</head>', `<script>${assemble}<\/script></head>`)), 'company-workspace: boot composition');
}
