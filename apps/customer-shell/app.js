const FIELDS = [
  "llm_base_url",
  "llm_model",
  "llm_pool",
  "hpc_host",
  "hpc_user",
  "quantum_host",
  "quantum_user",
  "knowledge_path",
  "cloud_url",
  "qdata_home",
  "qchem_home",
  "ionstack_home",
];

const state = { busy: false, ready: false, inboxKey: "", receiptKey: "", elnKey: "", currentCircuitId: "", currentCircuitScore: 0, govLamps: {}, hasAsk: false, inspector: "task" };

const $ = (id) => document.getElementById(id);

function token() {
  const params = new URLSearchParams(location.search);
  const fromQuery = params.get("token");
  const fromRole = (params.get("role") || "").trim();
  const fromTenant = (params.get("tenant") || "").trim();
  try {
    if (fromQuery) {
      localStorage.setItem("QAGENT_SHELL_TOKEN", fromQuery);
    }
    if (params.has("role")) {
      if (fromRole && fromRole !== "staff") {
        localStorage.setItem("QAGENT_SHELL_ROLE", fromRole);
      } else {
        localStorage.removeItem("QAGENT_SHELL_ROLE");
      }
    }
    // ?tenant= persists like ?token= / ?role=customer
    // empty ?tenant= clears so staff see all again
    if (params.has("tenant")) {
      if (fromTenant) {
        localStorage.setItem("QAGENT_SHELL_TENANT", fromTenant);
      } else {
        localStorage.removeItem("QAGENT_SHELL_TENANT");
      }
    }
    if (fromQuery || params.has("role") || params.has("tenant")) {
      history.replaceState({}, "", location.pathname);
    }
    return localStorage.getItem("QAGENT_SHELL_TOKEN") || "";
  } catch (_err) {
    return fromQuery || "";
  }
}

function role() {
  try {
    return localStorage.getItem("QAGENT_SHELL_ROLE") || "";
  } catch (_err) {
    return "";
  }
}

function tenant() {
  try {
    return (localStorage.getItem("QAGENT_SHELL_TENANT") || "").trim();
  } catch (_err) {
    return "";
  }
}

function applyCustomerRole() {
  // ?role=customer persists like ?token=
  const customer = role() === "customer";
  document.querySelectorAll(".secret-fieldset").forEach((box) => {
    box.hidden = customer;
    box.setAttribute("aria-hidden", customer ? "true" : "false");
  });
  document.querySelectorAll("details.staff-pack").forEach((box) => {
    box.hidden = customer;
  });
  document.querySelectorAll(".settings-reserved").forEach((box) => {
    box.hidden = customer;
  });
  const eln = $("eln-face");
  if (eln) {
    eln.hidden = customer;
    eln.setAttribute("aria-hidden", customer ? "true" : "false");
  }
  document.querySelectorAll(".welcome .packs").forEach((list) => {
    list.hidden = customer;
  });
}

function showInspector(tab) {
  const name = String(tab || "task");
  state.inspector = name;
  document.querySelectorAll("[data-pane]").forEach((pane) => {
    pane.hidden = pane.getAttribute("data-pane") !== name;
  });
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    const on = btn.getAttribute("data-tab") === name;
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    const nav = btn.getAttribute("data-nav");
    btn.classList.toggle("on", nav === name);
  });
}

function showSettingsPage(page) {
  const name = String(page || "workspace");
  document.querySelectorAll("[data-settings-page]").forEach((pane) => {
    pane.hidden = pane.getAttribute("data-settings-page") !== name;
  });
  document.querySelectorAll("[data-settings-tab]").forEach((btn) => {
    const on = btn.getAttribute("data-settings-tab") === name;
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function headers() {
  const out = { "Content-Type": "application/json" };
  const value = token();
  if (value) {
    out["X-QAGENT-DEBUG-TOKEN"] = value;
    out["X-QAGENT-APPROVE-TOKEN"] = value;
  }
  const tenantId = tenant();
  if (tenantId) {
    out["X-QAGENT-TENANT"] = tenantId;
  }
  return out;
}

function publicModelName(status) {
  const row = (status && status.workplace) || {};
  return String((status && status.next_model) || row.llm_model || (status && status.llm_model) || "").trim();
}

function paintHealth(status) {
  const ready = Boolean(status && status.ready);
  state.ready = ready;
  const line = $("health-line");
  if (!line) return;
  line.dataset.ready = ready ? "true" : "false";
  const model = publicModelName(status);
  line.title = model;
  if (!ready) {
    line.textContent = "本机还没接模型";
    return;
  }
  line.textContent = "控制台已就绪";
}

function revealStaffPackIfNeeded() {
  const pack = document.querySelector("details.staff-pack");
  if (pack && !state.ready && role() !== "customer") {
    pack.open = true;
    showSettingsPage("workspace");
  }
}

function openSettingsDialog() {
  applyCustomerRole();
  revealStaffPackIfNeeded();
  const dialog = $("settings");
  if (dialog && !dialog.open) dialog.showModal();
}

function shortAssignmentId(id) {
  const text = String(id || "");
  if (text.length <= 10) return text || "—";
  return text.slice(-8);
}

function askTool(row) {
  if (!row) return "未点名工具";
  if (row.ask && row.ask.tool) return String(row.ask.tool);
  if (row.ask_tool) return String(row.ask_tool);
  return "未点名工具";
}

function humanToolLabel(name) {
  const raw = String(name || "");
  if (!raw || raw === "未点名工具") return "待确认的上机";
  if (raw.indexOf("list_engines") >= 0) return "已接软件";
  if (raw.indexOf("qchem") >= 0) return "化学计算";
  if (raw.indexOf("qdata") >= 0 && raw.indexOf("dequant") >= 0) return "优势对照";
  if (raw.indexOf("qdata") >= 0) return "数据资产";
  if (raw.indexOf("pin") >= 0) return "钉住线路";
  if (raw.indexOf("estimate") >= 0) return "时间估计";
  if (raw.indexOf("aer") >= 0) return "对照模拟";
  if (raw.indexOf("docs") >= 0) return "查阅手册";
  if (raw.indexOf("transpile") >= 0 || raw.indexOf("qiskit") >= 0) return "线路处理";
  if (raw.indexOf("twin") >= 0) return "上机";
  return "待确认的上机";
}

function faceKind(status) {
  const value = String(status || "needs_ask");
  if (value === "signed") return "signed";
  if (value === "failed" || value === "rejected") return "stopped";
  return "waiting";
}

function faceClass(status) {
  const kind = faceKind(status);
  if (kind === "signed") return "face-signed";
  if (kind === "stopped") return "face-stopped";
  return "face-waiting";
}

function faceLabel(status, reason) {
  const value = String(status || "needs_ask");
  const why = String(reason || "");
  if (value === "signed") return "已签收";
  if (why === "cancelled") return "已取消";
  if (why === "rejected" || value === "rejected") return "已拒绝";
  if (why === "failed" || value === "failed") return "失败";
  if (value === "needs_ask") return "待批准";
  if (value === "running") return "还在跑";
  return "未签收";
}

function signedTwinId(row) {
  if (!row || String(row.status || "") !== "signed") return "";
  const handles = row.handles || {};
  return handles.twin_id ? String(handles.twin_id) : "";
}

function faceMakespan(row) {
  const n = Number(row && row.makespan_ns);
  if (!Number.isFinite(n) || n < 0) return "";
  return String(Math.round(n));
}

function faceB3Verdict(row) {
  const raw = row && row.b3_verdict;
  if (raw === "quantum_wins") return "量子赢";
  if (raw === "classical_wins") return "经典赢";
  if (raw === "inconclusive") return "尚无定论";
  return "";
}

function faceAerProvenance(row) {
  const raw = row && row.aer_provenance;
  if (raw === "aer") return "Aer · 不是孪生签收";
  if (raw === "ibm") return "IBM · 不是孪生签收";
  if (raw === "cirq") return "Cirq · 不是孪生签收";
  if (raw === "qccd-twin") return "我们的机器";
  return "";
}

function faceShots(row) {
  const n = Number(row && row.shots_actual);
  if (!Number.isFinite(n) || n <= 0) return "";
  return String(Math.round(n));
}

function faceCircuitId(row) {
  const handles = (row && row.handles) || {};
  return handles.circuit_id ? String(handles.circuit_id) : "";
}

function faceAssetId(row) {
  const handles = (row && row.handles) || {};
  return handles.asset_id ? String(handles.asset_id) : "";
}

function inboxKey(rows) {
  return (rows || [])
    .map((row) => [row.assignment_id || "", row.status || "", askTool(row), faceMakespan(row), faceCircuitId(row), faceAssetId(row)].join(":"))
    .join("|");
}

function paintPreflight(assignmentId, checks) {
  const row = $("inbox-list").querySelector(`[data-asg="${assignmentId}"]`);
  const line = row && row.querySelector(".inbox-preflight");
  if (!line || !checks) return;
  const bits = [
    checks.twin_live ? "Twin 已接通" : "Twin 未接通",
    checks.has_circuit ? "有线路" : "还没有线路",
    checks.has_asset ? "有资产" : "还没有资产",
  ];
  if (checks.estimate_ok === true) bits.push("预估可用");
  if (checks.estimate_ok === false) bits.push("预估未就绪");
  const estimateNs = Number(checks.estimate_ns);
  if (Number.isFinite(estimateNs) && estimateNs > 0) bits.push(`估计 ${Math.round(estimateNs)} ns`);
  line.textContent = `预检 · ${bits.join(" · ")}`;
  const yes = row.querySelector("button.act");
  if (yes) yes.classList.toggle("soft", checks.estimate_ok === false);
}

function loadPreflight(assignmentId) {
  if (!assignmentId) return;
  fetch(`/api/assignments/${encodeURIComponent(assignmentId)}/preflight`, { headers: headers() })
    .then((res) => res.json())
    .then((data) => paintPreflight(assignmentId, data.checks || {}))
    .catch(() => {});
}

function assignmentAction(assignmentId, action) {
  const id = String(assignmentId || "").trim();
  const verb = String(action || "").trim();
  if (!id || !verb || state.busy) return;
  setBusy(true);
  fetch(`/api/assignments/${encodeURIComponent(id)}/${verb}`, {
    method: "POST",
    headers: headers(),
    body: "{}",
  })
    .then((res) => res.json().then((data) => ({ status: res.status, data })))
    .then(({ status, data }) => {
      if (status === 403) {
        addMessage("assistant", "批准要带工作台令牌。不会伪造上机句柄。");
        return;
      }
      if (data && data.status === "signed") {
        addMessage("assistant", "已签收。右侧可下载短回执。");
        return;
      }
      if (data && data.status === "failed") {
        addMessage("assistant", "上机没签下。不会伪造 twin_id。");
        return;
      }
      if (verb === "fork" && data && data.assignment_id) {
        addMessage("assistant", "已分出未签收交办。不会带走 twin_id。");
        return;
      }
      if (data && (data.status === "rejected" || data.reason === "cancelled")) {
        addMessage("assistant", "先不上机。");
      }
    })
    .catch(() => {
      addMessage("assistant", "这次没连上。不会伪造上机句柄。");
    })
    .finally(() => {
      setBusy(false);
      refreshInbox();
    });
}

function newestAssignment(rows) {
  let best = null;
  (rows || []).forEach((row) => {
    if (!row) return;
    if (!best) {
      best = row;
      return;
    }
    const next = String(row.updated_at || row.created_at || "");
    const prev = String(best.updated_at || best.created_at || "");
    if (next >= prev) best = row;
  });
  return best;
}

function paintInbox(rows) {
  const asks = (rows || []).filter((row) => row && row.status === "needs_ask");
  state.hasAsk = asks.length > 0;
  const recent = asks.slice(-8);
  const current = newestAssignment(asks) || newestAssignment(recent);
  const painted = current ? [current] : [];
  const empty = $("inbox-empty");
  const list = $("inbox-list");
  const key = inboxKey(painted);
  if (key === state.inboxKey && list.childElementCount === painted.length) return;
  state.inboxKey = key;
  list.textContent = "";
  if (!painted.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  painted.forEach((row) => {
    const item = document.createElement("li");
    const kind = faceKind(row.status || "needs_ask");
    item.className = `inbox-row ${faceClass(row.status || "needs_ask")}`;
    item.dataset.asg = row.assignment_id || "";
    item.dataset.face = kind;
    const meta = document.createElement("p");
    meta.className = "inbox-meta";
    const toolEl = document.createElement("span");
    toolEl.className = "inbox-tool";
    toolEl.textContent = humanToolLabel(askTool(row));
    const statusEl = document.createElement("span");
    statusEl.className = "inbox-status face-label";
    statusEl.textContent = faceLabel(row.status || "needs_ask", row.reason);
    meta.append(toolEl, statusEl);
    const estimate = faceMakespan(row);
    if (estimate) {
      const estEl = document.createElement("span");
      estEl.className = "inbox-estimate";
      estEl.textContent = `估计 · ${estimate} ns`;
      meta.appendChild(estEl);
    }
    const circuit = faceCircuitId(row);
    if (circuit) {
      const circEl = document.createElement("span");
      circEl.className = "inbox-circuit";
      circEl.textContent = "这份线路";
      meta.appendChild(circEl);
    }
    const asset = faceAssetId(row);
    if (asset) {
      const assetEl = document.createElement("span");
      assetEl.className = "inbox-asset";
      assetEl.textContent = "已备好的数据";
      meta.appendChild(assetEl);
    }
    const pre = document.createElement("p");
    pre.className = "inbox-preflight";
    pre.textContent = "预检 · 还在看";
    const actions = document.createElement("div");
    actions.className = "msg-actions";
    const yes = document.createElement("button");
    yes.className = "act";
    yes.type = "button";
    yes.textContent = "批准上机";
    yes.disabled = state.busy;
    yes.addEventListener("click", () => assignmentAction(row.assignment_id, "approve"));
    const no = document.createElement("button");
    no.className = "ghost";
    no.type = "button";
    no.textContent = "先不上机";
    no.disabled = state.busy;
    no.addEventListener("click", () => assignmentAction(row.assignment_id, "cancel"));
    actions.append(yes, no);
    item.append(meta, pre, actions);
    list.appendChild(item);
    loadPreflight(row.assignment_id);
  });
}

function receiptKey(rows) {
  return (rows || [])
    .map((row) => [row.assignment_id || "", row.status || "", signedTwinId(row), faceB3Verdict(row), faceAerProvenance(row), faceCircuitId(row), faceAssetId(row), faceShots(row)].join(":"))
    .join("|");
}

function loadReceiptRaw(assignmentId) {
  return fetch(`/api/assignments/${encodeURIComponent(assignmentId)}/receipt`, { headers: headers() })
    .then((res) => res.text());
}

function loadReceipt(assignmentId) {
  return loadReceiptRaw(assignmentId).then((raw) => JSON.parse(raw));
}

function saveReceiptJson(assignmentId, raw) {
  const text = typeof raw === "string" ? raw : JSON.stringify(raw, null, 2);
  const blob = new Blob([text], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "签收回执.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

function downloadSignedReceipt(assignmentId) {
  loadReceiptRaw(assignmentId)
    .then((raw) => saveReceiptJson(assignmentId, raw))
    .catch(() => {});
}

function verifySignedReceipt(assignmentId, line) {
  loadReceiptRaw(assignmentId)
    .then((raw) =>
      fetch("/api/receipts/verify", {
        method: "POST",
        headers: headers(),
        body: raw,
      }).then((res) => res.json())
    )
    .then((data) => {
      if (!line) return;
      line.hidden = false;
      line.textContent = data && data.ok ? "ok" : "fail";
      line.dataset.ok = data && data.ok ? "true" : "false";
    })
    .catch(() => {
      if (!line) return;
      line.hidden = false;
      line.textContent = "fail";
      line.dataset.ok = "false";
    });
}

function paintFaceRow(row) {
  const status = row.status || "needs_ask";
  const kind = faceKind(status);
  const item = document.createElement("li");
  item.className = `receipt-row ${faceClass(status)}`;
  item.dataset.asg = row.assignment_id || "";
  item.dataset.face = kind;
  if (kind === "signed") {
    const seal = document.createElement("span");
    seal.className = "face-seal";
    seal.setAttribute("aria-hidden", "true");
    item.appendChild(seal);
  }
  const label = document.createElement("span");
  label.className = "face-label";
  label.textContent = faceLabel(status, row.reason);
  item.append(label);
  const circuit = faceCircuitId(row);
  if (circuit) {
    const circEl = document.createElement("span");
    circEl.className = "receipt-circuit";
    circEl.textContent = "这份线路";
    item.appendChild(circEl);
  }
  const asset = faceAssetId(row);
  if (asset) {
    const assetEl = document.createElement("span");
    assetEl.className = "receipt-asset";
    assetEl.textContent = "已备好的数据";
    item.appendChild(assetEl);
  }
  const twin = signedTwinId(row);
  if (twin) {
    const twinEl = document.createElement("span");
    twinEl.className = "receipt-twin";
    twinEl.textContent = "已在我们的机器上签收";
    item.appendChild(twinEl);
  }
  const verdict = faceB3Verdict(row);
  if (verdict) {
    const b3El = document.createElement("span");
    b3El.className = "receipt-b3";
    b3El.textContent = `B3 · ${verdict}`;
    item.appendChild(b3El);
  }
  const foreign = faceAerProvenance(row);
  if (foreign) {
    const aerEl = document.createElement("span");
    aerEl.className = "receipt-aer";
    aerEl.textContent = foreign;
    item.appendChild(aerEl);
  }
  const shots = faceShots(row);
  if (shots) {
    const shotEl = document.createElement("span");
    shotEl.className = "receipt-shots";
    shotEl.textContent = `实打 · ${shots} 发`;
    item.appendChild(shotEl);
  }
  if (kind === "signed") {
    const actions = document.createElement("div");
    actions.className = "receipt-actions";
    const downloadBtn = document.createElement("button");
    downloadBtn.className = "ghost";
    downloadBtn.type = "button";
    downloadBtn.textContent = "下载回执";
    downloadBtn.addEventListener("click", () => downloadSignedReceipt(row.assignment_id));
    const verifyBtn = document.createElement("button");
    verifyBtn.className = "ghost";
    verifyBtn.type = "button";
    verifyBtn.textContent = "核验";
    const verifyLine = document.createElement("span");
    verifyLine.className = "receipt-verify";
    verifyLine.hidden = true;
    verifyBtn.addEventListener("click", () => verifySignedReceipt(row.assignment_id, verifyLine));
    const forkBtn = document.createElement("button");
    forkBtn.className = "ghost";
    forkBtn.type = "button";
    forkBtn.textContent = "再走一遍";
    forkBtn.addEventListener("click", () => assignmentAction(row.assignment_id, "fork"));
    actions.append(downloadBtn, verifyBtn, forkBtn);
    item.append(actions, verifyLine);
  }
  return item;
}

function paintReceipts(rows) {
  const shown = (rows || []).filter((row) => row && row.status && row.status !== "needs_ask");
  const empty = $("receipt-empty");
  const list = $("receipt-list");
  if (!empty || !list) return;
  const signed = shown.filter((row) => row.status === "signed");
  const other = shown.filter((row) => row.status !== "signed");
  const recent = signed.concat(other).slice(0, 8);
  const current = newestAssignment(shown) || newestAssignment(recent);
  const painted = current ? [current] : [];
  const key = receiptKey(painted);
  if (key === state.receiptKey && list.childElementCount === painted.length) return;
  state.receiptKey = key;
  list.textContent = "";
  if (!painted.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  painted.forEach((row) => {
    list.appendChild(paintFaceRow(row));
  });
}

const ELN_KIND_MAP = {
  "qagent/recipe_pin": "recipe_pin",
  "qagent/estimate": "estimate",
  "qagent/twin_signoff": "twin_signoff",
  "qagent/b3": "b3",
  "qagent/assignment": "assignment",
  "qagent/claim_blocked": "claim_blocked",
  recipe_pin: "recipe_pin",
  estimate: "estimate",
  twin_signoff: "twin_signoff",
  b3: "b3",
  assignment: "assignment",
  claim_blocked: "claim_blocked",
};

function elnType(row) {
  const raw = String((row && row.type) || "");
  if (ELN_KIND_MAP[raw]) return ELN_KIND_MAP[raw];
  if (raw.indexOf("/") >= 0) return raw.split("/").pop();
  return raw;
}

function elnKindLabel(kind) {
  if (kind === "recipe_pin") return "配方钉住";
  if (kind === "estimate") return "估计";
  if (kind === "twin_signoff") return "签收";
  if (kind === "b3") return "B3";
  if (kind === "assignment") return "交办";
  if (kind === "claim_blocked") return "未认领";
  return kind;
}

function elnAssignmentId(row) {
  if (!row) return "";
  if (row.assignment_id) return String(row.assignment_id);
  if (row.payload && row.payload.assignment_id) return String(row.payload.assignment_id);
  return "";
}

function elnReason(row) {
  if (!row) return "";
  if (row.reason) return String(row.reason);
  if (row.payload && row.payload.reason) return String(row.payload.reason);
  return "";
}

function elnMakespan(row) {
  const raw = row && (row.makespan_ns != null ? row.makespan_ns : row.payload && row.payload.makespan_ns);
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) return "";
  return String(Math.round(n));
}

function elnB3Verdict(row) {
  const raw = row && (row.verdict || (row.payload && row.payload.verdict) || "");
  return faceB3Verdict({ b3_verdict: raw });
}

function elnShots(row) {
  const raw = row && (row.shots_actual != null ? row.shots_actual : row.payload && row.payload.shots_actual);
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return "";
  return String(Math.round(n));
}

function elnCircuitId(row) {
  if (!row) return "";
  if (row.circuit_id) return String(row.circuit_id);
  if (row.payload && row.payload.circuit_id) return String(row.payload.circuit_id);
  return "";
}

function elnAssetId(row) {
  if (!row) return "";
  if (row.asset_id) return String(row.asset_id);
  if (row.payload && row.payload.asset_id) return String(row.payload.asset_id);
  return "";
}

function elnKey(rows) {
  return (rows || [])
    .map((row) => [elnType(row), elnAssignmentId(row), elnReason(row), elnMakespan(row), elnB3Verdict(row), elnShots(row), elnCircuitId(row), elnAssetId(row)].join(":"))
    .join("|");
}

function paintEln(rows) {
  const empty = $("eln-empty");
  const list = $("eln-list");
  if (!empty || !list) return;
  const shown = rows || [];
  const recent = shown.slice(-8);
  const painted = recent.slice(-1);
  const key = elnKey(painted);
  if (key === state.elnKey && list.childElementCount === painted.length) return;
  state.elnKey = key;
  list.textContent = "";
  if (!painted.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  painted.forEach((row) => {
    const kind = elnType(row);
    if (!kind) return;
    const item = document.createElement("li");
    item.className = "eln-row";
    const typeEl = document.createElement("span");
    typeEl.className = "eln-type";
    typeEl.textContent = elnKindLabel(kind);
    item.appendChild(typeEl);
    const aid = elnAssignmentId(row);
    if (aid) {
      item.dataset.asg = aid;
      item.dataset.asgShort = shortAssignmentId(aid);
    }
    const reason = elnReason(row);
    if (reason) {
      const reasonEl = document.createElement("span");
      reasonEl.className = "eln-reason";
      reasonEl.textContent = reason.slice(0, 40);
      item.appendChild(reasonEl);
    }
    const estimate = elnMakespan(row);
    if (estimate) {
      const estEl = document.createElement("span");
      estEl.className = "eln-estimate";
      estEl.textContent = `估计 · ${estimate} ns`;
      item.appendChild(estEl);
    }
    const verdict = elnB3Verdict(row);
    if (verdict) {
      const b3El = document.createElement("span");
      b3El.className = "eln-b3";
      b3El.textContent = `B3 · ${verdict}`;
      item.appendChild(b3El);
    }
    const shots = elnShots(row);
    if (shots) {
      const shotEl = document.createElement("span");
      shotEl.className = "eln-shots";
      shotEl.textContent = `实打 · ${shots} 发`;
      item.appendChild(shotEl);
    }
    const circuit = elnCircuitId(row);
    if (circuit) {
      const circEl = document.createElement("span");
      circEl.className = "eln-circuit";
      circEl.textContent = "这份线路";
      item.appendChild(circEl);
    }
    const asset = elnAssetId(row);
    if (asset) {
      const assetEl = document.createElement("span");
      assetEl.className = "eln-asset";
      assetEl.textContent = "已备好的数据";
      item.appendChild(assetEl);
    }
    list.appendChild(item);
  });
}

async function refreshInbox() {
  try {
    const data = await (await fetch("/api/assignments?status=needs_ask", { headers: headers() })).json();
    paintInbox(data.assignments || []);
  } catch (_err) {
    if (!$("inbox-list").childElementCount) {
      $("inbox-empty").hidden = false;
    }
  }
  try {
    const data = await (await fetch("/api/assignments", { headers: headers() })).json();
    paintReceipts(data.assignments || []);
  } catch (_err) {
    if ($("receipt-list") && !$("receipt-list").childElementCount) {
      $("receipt-empty").hidden = false;
    }
  }
  try {
    const data = await (await fetch("/api/eln", { method: "GET", headers: headers() })).json();
    paintEln(data.events || []);
  } catch (_err) {
    if ($("eln-list") && !$("eln-list").childElementCount) {
      $("eln-empty").hidden = false;
    }
  }
  try {
    const data = await (await fetch("/api/gov/face", { headers: headers() })).json();
    paintGov(data);
  } catch (_err) {
    if ($("gov-empty")) $("gov-empty").hidden = false;
  }
  try {
    const data = await (await fetch("/api/chat/sessions", { headers: headers() })).json();
    paintSessions(data.sessions || []);
  } catch (_err) {
    if ($("session-list") && !$("session-list").childElementCount) {
      $("session-empty").hidden = false;
    }
  }
}

function faceGovLamps(face) {
  const box = $("gov-lamps");
  state.govLamps = (face && face.lamps) || {};
  if (!box) return;
  box.textContent = "";
  const lamps = state.govLamps;
  [
    ["孪生", lamps.twin],
    ["预估", lamps.estimate],
    ["数据", lamps.qdata],
    ["待批", state.hasAsk],
  ].forEach(([label, value]) => {
    const li = document.createElement("li");
    const lit = typeof value === "number" ? value > 0 : Boolean(value);
    li.className = lit ? "lamp on" : "lamp";
    li.textContent = label;
    box.appendChild(li);
  });
}

function faceGovLife(face) {
  const box = $("gov-life");
  if (!box) return;
  box.textContent = "";
  const steps = face && Array.isArray(face.life) ? face.life : [];
  box.hidden = !steps.length;
  steps.forEach((label) => {
    const li = document.createElement("li");
    li.textContent = String(label);
    box.appendChild(li);
  });
}

function paintGov(face) {
  faceGovLamps(face);
  faceGovLife(face);
  const empty = $("gov-empty");
  const list = $("gov-list");
  if (!empty || !list) return;
  list.textContent = "";
  const rows = [];
  if (face && face.has_circuit) rows.push(["线路", "这份线路"]);
  if (face && face.has_asset) rows.push(["数据", "已备好的数据"]);
  if (face && face.has_twin) rows.push(["签收", "已在我们的机器上签收"]);
  if (face && face.b3_verdict) rows.push(["B3", String(face.b3_verdict)]);
  if (face && face.provenance) {
    rows.push(["出处", faceAerProvenance({ aer_provenance: face.provenance }) || String(face.provenance)]);
  }
  if (face && face.safe_mode) rows.push(["安全模式", "开"]);
  if (!rows.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  rows.forEach((pair) => {
    const dt = document.createElement("dt");
    dt.textContent = pair[0];
    const dd = document.createElement("dd");
    dd.textContent = pair[1];
    list.append(dt, dd);
  });
}

function paintSessions(rows) {
  const empty = $("session-empty");
  const list = $("session-list");
  if (!empty || !list) return;
  list.textContent = "";
  const items = Array.isArray(rows) ? rows : [];
  if (!items.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  items.slice(0, 8).forEach((row) => {
    const li = document.createElement("li");
    li.className = "session-row" + (row && row.current ? " current" : "");
    const name = document.createElement("span");
    name.className = "session-name";
    name.textContent = String((row && row.title) || "还没留话的对话");
    const meta = document.createElement("span");
    meta.className = "session-meta";
    const when = String((row && row.updated_at) || "").replace("T", " ").slice(5, 16);
    meta.textContent = `${row && row.current ? "当前" : "已清"}${when ? ` · ${when}` : ""}`;
    li.append(name, meta);
    list.appendChild(li);
  });
}

function circuitMount(meta) {
  rememberCircuit(meta);
  const box = document.createElement("div");
  box.className = "circuit-face";
  box.dataset.circuitId = String((meta && meta.circuit_id) || "");
  const cap = document.createElement("p");
  cap.className = "circuit-cap";
  cap.textContent = circuitTitle(meta);
  const scroll = document.createElement("div");
  scroll.className = "circuit-scroll";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "电路图");
  scroll.appendChild(svg);
  const actions = document.createElement("div");
  actions.className = "circuit-actions";
  const download = document.createElement("button");
  download.className = "ghost";
  download.type = "button";
  download.textContent = "下载这份线路";
  download.addEventListener("click", () => downloadCircuitProgram(meta.circuit_id));
  actions.appendChild(download);
  box.append(cap, scroll, actions);
  loadCircuitFace(meta.circuit_id, svg, cap);
  return box;
}

async function loadCircuitFace(circuitId, svg, cap) {
  try {
    const res = await fetch(`/api/circuits/${encodeURIComponent(circuitId)}`, { headers: headers() });
    const data = await res.json();
    if (!res.ok || !data.gates) {
      cap.textContent = "电路还没钉住，画不出图。";
      return;
    }
    cap.textContent = circuitTitle(data);
    rememberCircuit(data);
    drawCircuitSvg(svg, data);
  } catch (_err) {
    cap.textContent = "电路图这次没画上。";
  }
}

function drawCircuitSvg(svg, data) {
  const n = Number(data.n_qubits) || 0;
  const gates = data.gates || [];
  const colW = 22;
  const rowH = 26;
  const left = 28;
  const top = 14;
  const width = left + Math.max(gates.length, 1) * colW + 12;
  const height = top + Math.max(n, 1) * rowH + 8;
  const ns = "http://www.w3.org/2000/svg";
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  const el = (name, attrs) => {
    const node = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  for (let q = 0; q < n; q += 1) {
    const y = top + q * rowH;
    const label = el("text", { x: 4, y: y + 4, fill: "#8ea0b0", "font-size": "10" });
    label.textContent = `q${q}`;
    svg.appendChild(label);
    svg.appendChild(el("line", {
      x1: left,
      y1: y,
      x2: width - 8,
      y2: y,
      stroke: "#2a3846",
      "stroke-width": "1",
    }));
  }
  gates.forEach((gate, i) => {
    const x = left + i * colW + colW / 2;
    const name = String(gate.name || "").toUpperCase();
    const qs = (gate.qubits || []).map(Number);
    if ((name === "CX" || name === "CNOT" || name === "CZ") && qs.length >= 2) {
      const c = top + qs[0] * rowH;
      const t = top + qs[1] * rowH;
      svg.appendChild(el("line", {
        x1: x, y1: c, x2: x, y2: t, stroke: "#6ba3c7", "stroke-width": "1.4",
      }));
      svg.appendChild(el("circle", { cx: x, cy: c, r: 3.2, fill: "#6ba3c7" }));
      if (name === "CZ") {
        svg.appendChild(el("circle", { cx: x, cy: t, r: 3.2, fill: "#6ba3c7" }));
      } else {
        svg.appendChild(el("circle", {
          cx: x, cy: t, r: 6, fill: "none", stroke: "#6ba3c7", "stroke-width": "1.4",
        }));
        svg.appendChild(el("line", {
          x1: x - 4, y1: t, x2: x + 4, y2: t, stroke: "#6ba3c7", "stroke-width": "1.4",
        }));
        svg.appendChild(el("line", {
          x1: x, y1: t - 4, x2: x, y2: t + 4, stroke: "#6ba3c7", "stroke-width": "1.4",
        }));
      }
      return;
    }
    qs.forEach((q) => {
      const y = top + q * rowH;
      const w = 18;
      const h = 16;
      svg.appendChild(el("rect", {
        x: x - w / 2,
        y: y - h / 2,
        width: w,
        height: h,
        rx: 2,
        fill: "#16202b",
        stroke: name === "X" ? "#c9a227" : "#6ba3c7",
      }));
      const text = el("text", {
        x,
        y: y + 3.5,
        fill: "#e8eef4",
        "font-size": name.length > 3 ? "7" : "9",
        "text-anchor": "middle",
      });
      text.textContent = name.length > 4 ? name.slice(0, 4) : name;
      svg.appendChild(text);
    });
  });
}

function circuitScore(meta) {
  const nq = Number(meta && meta.n_qubits) || 0;
  const gates = Number((meta && meta.n_instructions) || (meta && meta.gates && meta.gates.length) || 0);
  return nq * 1000 + gates;
}

function rememberCircuit(meta, force) {
  const id = meta && meta.circuit_id ? String(meta.circuit_id) : "";
  if (!id) return false;
  const score = circuitScore(meta);
  if (force || !state.currentCircuitId || id === state.currentCircuitId) {
    state.currentCircuitId = id;
    if (score > (state.currentCircuitScore || 0)) state.currentCircuitScore = score;
    return true;
  }
  if (score && score >= state.currentCircuitScore) {
    state.currentCircuitId = id;
    state.currentCircuitScore = score;
    return true;
  }
  return false;
}

function circuitTitle(meta) {
  const nq = meta && meta.n_qubits ? `${meta.n_qubits} 比特` : "";
  const count = meta && (meta.n_instructions || (meta.gates && meta.gates.length));
  const gates = count ? `${count} 门` : "";
  const ansatz = String((meta && meta.ansatz) || "").toLowerCase();
  const mol = String((meta && meta.molecule) || "").toLowerCase();
  let kind = "";
  if (ansatz === "uccsd" && (mol === "h2" || mol === "hydrogen")) kind = "氢分子 UCCSD";
  else if (ansatz === "uccsd") kind = "UCCSD";
  else if (ansatz) kind = ansatz.toUpperCase();
  return [kind || "这份线路", nq, gates].filter(Boolean).join(" · ");
}

function redactHandles(text) {
  return String(text || "")
    .replace(/\bcirc_[0-9a-f]{8,}\b/gi, "这份线路")
    .replace(/\basset_[0-9a-z]{6,}\b/gi, "这份数据")
    .replace(/\btwin_[0-9a-f]{8,}\b/gi, "签收回执")
    .replace(/\bsession-[0-9a-f-]{8,}\b/gi, "这次会话")
    .replace(/\basg_[0-9a-z_]{4,}\b/gi, "这份交办")
    .replace(/\b(?:a2_chem\w*|a2_spin\w*|a1_closed\w*|qem_[a-z0-9_]{4,})\b/g, "这份计算")
    .replace(/\bqiskit_export_circuit\b/g, "线路")
    .replace(/\bqiskit_transpile\b/g, "线路处理")
    .replace(/\bqiskit_aer_run\b/g, "对照模拟")
    .replace(/\bqchem_run\b/g, "化学计算")
    .replace(/\bqdata_run_recipe\b/g, "数据计算")
    .replace(/\bqdata_list_assets\b/g, "数据目录")
    .replace(/\bqagent_pin_circuit\b/g, "钉住线路")
    .replace(/\bqagent_list_engines\b/g, "已接软件")
    .replace(/\bionstack_compile_estimate\b/g, "时间估计")
    .replace(/\buccsd_pauli\b/g, "UCCSD")
    .replace(/\bminimal_vqe\b/g, "VQE")
    .replace(/\b\w*twin\w*run\b/gi, "上机");
}

function renderMath(tex, displayMode) {
  const el = document.createElement(displayMode ? "div" : "span");
  el.className = displayMode ? "math-block" : "math-inline";
  const engine = window.katex;
  if (!engine || typeof engine.render !== "function") {
    el.textContent = displayMode ? `$$${tex}$$` : `\\(${tex}\\)`;
    return el;
  }
  try {
    engine.render(String(tex || ""), el, {
      throwOnError: false,
      displayMode: Boolean(displayMode),
      maxSize: 20,
      maxExpand: 1000,
      trust: false,
      strict: "ignore",
    });
  } catch (_err) {
    el.textContent = String(tex || "");
  }
  return el;
}

function splitMath(text) {
  const src = String(text || "");
  const parts = [];
  let i = 0;
  while (i < src.length) {
    if (src.startsWith("$$", i)) {
      const end = src.indexOf("$$", i + 2);
      if (end >= 0) {
        parts.push({ kind: "math", display: true, tex: src.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (src.startsWith("\\[", i)) {
      const end = src.indexOf("\\]", i + 2);
      if (end >= 0) {
        parts.push({ kind: "math", display: true, tex: src.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (src.startsWith("\\(", i)) {
      const end = src.indexOf("\\)", i + 2);
      if (end >= 0) {
        parts.push({ kind: "math", display: false, tex: src.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (src[i] === "`") {
      const end = src.indexOf("`", i + 1);
      if (end > i) {
        parts.push({ kind: "code", text: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    if (src.startsWith("**", i)) {
      const end = src.indexOf("**", i + 2);
      if (end > i + 2) {
        parts.push({ kind: "strong", text: src.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (src[i] === "$" && src[i + 1] !== "$") {
      const end = src.indexOf("$", i + 1);
      if (end > i + 1 && src[i + 1] !== " " && src[end - 1] !== " ") {
        parts.push({ kind: "math", display: false, tex: src.slice(i + 1, end) });
        i = end + 1;
        continue;
      }
    }
    let j = i + 1;
    while (j < src.length) {
      if (src.startsWith("$$", j) || src.startsWith("\\[", j) || src.startsWith("\\(", j)) break;
      if (src[j] === "`" || src.startsWith("**", j)) break;
      if (src[j] === "$" && src[j + 1] !== "$") break;
      j += 1;
    }
    parts.push({ kind: "text", text: src.slice(i, j) });
    i = j;
  }
  return parts;
}

function appendInline(parent, text) {
  splitMath(text).forEach((part) => {
    if (part.kind === "math") {
      parent.appendChild(renderMath(part.tex, part.display));
      return;
    }
    if (part.kind === "code") {
      const code = document.createElement("code");
      code.textContent = part.text;
      parent.appendChild(code);
      return;
    }
    if (part.kind === "strong") {
      const strong = document.createElement("strong");
      strong.textContent = part.text;
      parent.appendChild(strong);
      return;
    }
    parent.appendChild(document.createTextNode(part.text || ""));
  });
}

function takeDisplayMath(lines, i) {
  const start = String(lines[i] || "").trimStart();
  let closer = "";
  let skip = 0;
  if (start.startsWith("$$")) {
    closer = "$$";
    skip = 2;
  } else if (start.startsWith("\\[")) {
    closer = "\\]";
    skip = 2;
  } else {
    return null;
  }
  const rest = start.slice(skip);
  const same = rest.indexOf(closer);
  if (same >= 0) {
    return { tex: rest.slice(0, same).trim(), next: i + 1 };
  }
  const parts = [rest];
  let j = i + 1;
  while (j < lines.length) {
    const line = String(lines[j] || "");
    const at = line.indexOf(closer);
    if (at >= 0) {
      parts.push(line.slice(0, at));
      return { tex: parts.join("\n").trim(), next: j + 1 };
    }
    parts.push(line);
    j += 1;
  }
  return null;
}

function renderTable(rows) {
  const table = document.createElement("table");
  const body = document.createElement("tbody");
  rows.forEach((row, index) => {
    if (index === 1 && /^\|\s*[-:| ]+\|/.test(row)) return;
    const tr = document.createElement("tr");
    row.replace(/^\|/, "").replace(/\|$/, "").split("|").forEach((cell) => {
      const el = document.createElement(index === 0 ? "th" : "td");
      appendInline(el, cell.trim());
      tr.appendChild(el);
    });
    if (index === 0) {
      const head = document.createElement("thead");
      head.appendChild(tr);
      table.appendChild(head);
    } else {
      body.appendChild(tr);
    }
  });
  if (body.childElementCount) table.appendChild(body);
  return table;
}

function fillRichText(root, text) {
  root.textContent = "";
  const src = redactHandles(text).replace(/\r\n/g, "\n").trim();
  if (!src) return;
  const lines = src.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const display = takeDisplayMath(lines, i);
    if (display) {
      root.appendChild(renderMath(display.tex, true));
      i = display.next;
      continue;
    }
    if (/^\|/.test(line) && i + 1 < lines.length && /^\|\s*[-:| ]+\|/.test(lines[i + 1] || "")) {
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        rows.push(lines[i]);
        i += 1;
      }
      root.appendChild(renderTable(rows));
      continue;
    }
    if (/^#{1,3}\s+/.test(line)) {
      const marks = line.replace(/^(#{1,3}).*/, "$1").length;
      const heading = document.createElement(marks === 1 ? "h3" : marks === 2 ? "h4" : "h5");
      appendInline(heading, line.replace(/^#{1,3}\s+/, ""));
      root.appendChild(heading);
      i += 1;
      continue;
    }
    const listed = /^\s*[-*]\s+/.test(line);
    const numbered = /^\s*\d+\.\s+/.test(line);
    if (listed || numbered) {
      const list = document.createElement(numbered ? "ol" : "ul");
      while (i < lines.length && (numbered ? /^\s*\d+\.\s+/.test(lines[i]) : /^\s*[-*]\s+/.test(lines[i]))) {
        const item = document.createElement("li");
        appendInline(item, lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, ""));
        list.appendChild(item);
        i += 1;
      }
      root.appendChild(list);
      continue;
    }
    const para = document.createElement("p");
    const chunk = [line];
    i += 1;
    while (
      i < lines.length
      && lines[i].trim()
      && !/^#{1,3}\s+/.test(lines[i])
      && !/^\s*[-*]\s+/.test(lines[i])
      && !/^\s*\d+\.\s+/.test(lines[i])
      && !/^\|/.test(lines[i])
      && !/^\s*\$\$/.test(lines[i])
      && !/^\s*\\\[/.test(lines[i])
    ) {
      chunk.push(lines[i]);
      i += 1;
    }
    appendInline(para, chunk.join(" "));
    root.appendChild(para);
  }
}

function downloadCircuitProgram(circuitId) {
  const id = String(circuitId || state.currentCircuitId || "").trim();
  if (!id) return;
  fetch(`/api/circuits/${encodeURIComponent(id)}/program`, { headers: headers() })
    .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || !data || !data.qasm3) return;
      const blob = new Blob([data.qasm3], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = String(data.filename || "线路.qasm");
      link.click();
      URL.revokeObjectURL(link.href);
    })
    .catch(() => {});
}

function addMessage(role, text, extras) {
  const article = document.createElement("article");
  article.className = `msg ${role}`;
  const body = document.createElement("div");
  body.className = "msg-body";
  if (String(role || "").indexOf("user") >= 0 || String(role || "").indexOf("busy") >= 0) {
    body.textContent = redactHandles(text);
  } else {
    fillRichText(body, text);
  }
  article.appendChild(body);
  if (extras && extras.cards && extras.cards.length) {
    const list = document.createElement("ul");
    list.className = "tool-cards";
    extras.cards.forEach((card) => {
      const item = document.createElement("li");
      item.textContent = humanToolLabel(card.name || card.kind || "");
      list.appendChild(item);
    });
    article.appendChild(list);
  }
  if (extras && extras.circuit && extras.circuit.circuit_id && rememberCircuit(extras.circuit)) {
    article.appendChild(circuitMount(extras.circuit));
  }
  if (extras && extras.awaiting === "approve") {
    const permit = document.createElement("section");
    permit.className = "permit";
    const title = document.createElement("p");
    title.className = "permit-title";
    title.textContent = "许可单";
    const note = document.createElement("p");
    note.className = "permit-note";
    note.textContent = "上我们的机器前要你拍板。估计写在右侧在办；不批不会上机。";
    permit.append(title, note);
    const estimateNs = Number(extras.pending && extras.pending.makespan_ns);
    if (Number.isFinite(estimateNs) && estimateNs > 0) {
      const est = document.createElement("p");
      est.className = "permit-estimate";
      est.textContent = `估计 · ${Math.round(estimateNs)} ns`;
      permit.appendChild(est);
    }
    if (state.govLamps.estimate === false) {
      const hint = document.createElement("p");
      hint.className = "permit-hint";
      hint.textContent = "预估未就绪。仍可拍板，先看右侧四灯。";
      permit.appendChild(hint);
    }
    const row = document.createElement("div");
    row.className = "msg-actions";
    const yes = document.createElement("button");
    yes.className = state.govLamps.estimate === false ? "act soft" : "act";
    yes.type = "button";
    yes.textContent = "批准上机";
    yes.addEventListener("click", () => send("批准"));
    const no = document.createElement("button");
    no.className = "ghost";
    no.type = "button";
    no.textContent = "先不上机";
    no.addEventListener("click", () => send("先不批"));
    row.append(yes, no);
    permit.appendChild(row);
    article.appendChild(permit);
    showInspector("task");
  }
  $("thread").appendChild(article);
  article.scrollIntoView({ block: "end" });
  return article;
}

function attachCircuitFile(file) {
  if (!file || state.busy) return;
  const reader = new FileReader();
  reader.onload = () => {
    setBusy(true);
    fetch("/api/circuits", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ qasm3: String(reader.result || "") }),
    })
      .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
      .then(({ ok, data }) => {
        if (!ok || !data || !data.circuit_id) {
          addMessage("assistant", (data && data.error) || "这份线路没收下。请用 OpenQASM。");
          return;
        }
        rememberCircuit(data, true);
        addMessage("assistant", "已收下你的线路。可以下载核对，或接着让我估计、上机。", { circuit: data });
      })
      .catch(() => {
        addMessage("assistant", "这份线路这次没附上。");
      })
      .finally(() => setBusy(false));
  };
  reader.readAsText(file);
}

function paintWelcome(status) {
  const root = document.createElement("section");
  root.className = "welcome";
  const ready = Boolean(status && status.ready);
  const title = "你想做什么？";
  const body = ready
    ? "用平常话交办就行。模型会自己选公司工具，没有写死的配方。上机前会问你。"
    : "用平常话写下要算什么。本机还没接模型时，我不会假装已经在算。";
  root.innerHTML = `<h2>${title}</h2><p>${body}</p><ul class="starters"></ul><ul class="packs"></ul>`;
  const starters = root.querySelector(".starters");
  [
    { label: "先看看接了哪些软件", text: "我们接了哪些软件？先别上机。" },
    { label: "先估计，先不上机", text: "先做时间估计，先不上机。" },
  ].forEach((row) => {
    const item = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ghost";
    btn.textContent = row.label;
    btn.addEventListener("click", () => send(row.text));
    item.appendChild(btn);
    starters.appendChild(item);
  });
  (status.engines || []).forEach((pack) => {
    const item = document.createElement("li");
    item.textContent = `${pack.label} · ${pack.kind} · ${pack.status}`;
    root.querySelector(".packs").appendChild(item);
  });
  $("thread").appendChild(root);
}

function fillSettings(status) {
  const row = (status && status.workplace) || {};
  FIELDS.forEach((key) => {
    if ($(key)) $(key).value = row[key] || "";
  });
  ["llm_api_key", "hpc_secret", "quantum_secret"].forEach((key) => {
    const el = $(key);
    if (!el) return;
    el.value = "";
    el.placeholder = "已保存";
  });
  const list = $("engine-list");
  list.innerHTML = "";
  (status.engines || []).forEach((pack) => {
    const item = document.createElement("li");
    item.textContent = `${pack.label} · ${pack.kind} · ${pack.status}`;
    list.appendChild(item);
  });
  const reserved = $("reserved-list");
  reserved.innerHTML = "";
  (status.reserved_engines || []).forEach((pack) => {
    const item = document.createElement("li");
    item.textContent = `${pack.label} · ${pack.kind} · ${pack.status}`;
    reserved.appendChild(item);
  });
}

function typingInField(el) {
  if (!el || el === document.body) return false;
  const tag = String(el.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || Boolean(el.isContentEditable);
}

function setBusy(busy) {
  state.busy = busy;
  $("send").disabled = busy;
  $("prompt").disabled = busy;
  $("stage").setAttribute("aria-busy", busy ? "true" : "false");
  $("composer").setAttribute("aria-busy", busy ? "true" : "false");
  $("send").setAttribute("aria-busy", busy ? "true" : "false");
  $("inbox-list").querySelectorAll("button").forEach((btn) => {
    btn.disabled = busy;
  });
}

function humanChatFault(status, data) {
  const err = String((data && data.error) || "").trim();
  if (err) return err;
  if (Number(status) === 403) return "这一步要组内令牌。";
  return "这次没连上。再发一句即可。";
}

async function readJson(res) {
  const raw = await res.text();
  if (!String(raw || "").trim()) return {};
  try {
    return JSON.parse(raw);
  } catch (_err) {
    return { error: "这次回了非 JSON。再发一句即可。" };
  }
}

async function send(text) {
  const message = (text || $("prompt").value || "").trim();
  if (!message || state.busy) return;
  if (!text) $("prompt").value = "";
  addMessage("user", message);
  const pending = addMessage("assistant busy", "在办…");
  setBusy(true);
  try {
    const payload = { message };
    if (state.currentCircuitId) payload.circuit_id = state.currentCircuitId;
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(payload),
    });
    const data = await readJson(res);
    pending.remove();
    if (!res.ok || data.error) {
      addMessage("assistant fault", humanChatFault(res.status, data));
      return;
    }
    if (data.circuit) rememberCircuit(data.circuit);
    const waiting = Boolean(data.running);
    const reply = String(data.reply || "").trim() || (waiting ? "还在办。结果出来后会出现在这边。" : "没有回复。");
    const shown = addMessage(waiting ? "assistant busy" : "assistant", reply, {
      awaiting: data.awaiting,
      cards: data.cards,
      circuit: data.circuit,
      pending: data.pending_approval,
    });
    if (typeof data.ready === "boolean") {
      state.ready = data.ready;
    }
    if (data.open_settings === true && !state.ready) {
      openSettingsDialog();
    }
    if (waiting) {
      await pollStatus(shown);
    }
  } catch (_err) {
    pending.remove();
    const shown = addMessage("assistant busy", "连线晃了一下。我继续看这一轮。");
    try {
      await pollStatus(shown);
    } catch (_poll) {
      addMessage("assistant fault", "这次没连上。再发一句即可。");
    }
  } finally {
    setBusy(false);
    refreshInbox();
    const active = document.activeElement;
    if (!active || active === document.body || active === $("send") || active === $("prompt")) {
      $("prompt").focus();
    }
  }
}

async function pollStatus(article) {
  refreshInbox();
  let misses = 0;
  for (let i = 0; i < 180; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const data = await readJson(await fetch("/api/chat/status", { headers: headers() }));
      if (data.error || typeof data.ready !== "boolean") {
        misses += 1;
        if (misses >= 8) break;
        continue;
      }
      misses = 0;
      const body = article.querySelector(".msg-body");
      if (body && data.reply) fillRichText(body, data.reply);
      if (i % 3 === 0) refreshInbox();
      if (data.open_settings === true && !state.ready) {
        openSettingsDialog();
      }
      if (data.circuit && data.circuit.circuit_id && rememberCircuit(data.circuit)) {
        const face = article.querySelector(".circuit-face");
        const id = String(data.circuit.circuit_id);
        if (!face) {
          article.appendChild(circuitMount(data.circuit));
        } else if (face.dataset.circuitId !== id) {
          face.replaceWith(circuitMount(data.circuit));
        }
      }
      if (!data.running) {
        if (article) article.classList.remove("busy");
        if (data.awaiting === "approve" && !article.querySelector(".msg-actions")) {
          addMessage("assistant", data.reply || "需要批准。", {
            awaiting: "approve",
            cards: data.cards,
            circuit: data.circuit,
            pending: data.pending_approval,
          });
        }
        refreshInbox();
        return;
      }
    } catch (_err) {
      misses += 1;
      if (misses >= 8) break;
    }
  }
  if (article && article.querySelector(".msg-body")) {
    const body = article.querySelector(".msg-body");
    const text = String(body.textContent || "").trim();
    if (!text || text.indexOf("连线晃了一下") >= 0 || text === "在办…" || text.indexOf("还在办") === 0) {
      fillRichText(body, "这次没连上。再发一句即可。");
      article.classList.add("fault");
    }
    article.classList.remove("busy");
  }
}

async function saveSettings() {
  const body = {};
  FIELDS.forEach((key) => {
    body[key] = $(key).value.trim();
  });
  ["llm_api_key", "hpc_secret", "quantum_secret"].forEach((key) => {
    if ($(key).value) body[key] = $(key).value;
  });
  const res = await fetch("/api/workplace", {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const why = Number(res.status) === 403
      ? "保存要组内 token。请用带 ?token= 的组内地址打开再保存。"
      : String((data && data.error) || "设置没存上。");
    addMessage("assistant", why);
    return;
  }
  const workplace = data.workplace || {};
  paintHealth({ ready: Boolean(data.ready), workplace });
  ["llm_api_key", "hpc_secret", "quantum_secret"].forEach((key) => {
    $(key).value = "";
  });
  let note = "设置已保存。还缺模型地址或模型名。";
  if (state.ready) {
    note = "设置已保存。现在可以直接说话。";
  } else if (!(workplace.llm_base_url || "").trim()) {
    note = "设置已保存。还要填接口地址，例如 https://api.deepseek.com/v1。";
  } else if (!(workplace.llm_model || "").trim()) {
    note = "设置已保存。还要填模型名，例如 deepseek-chat。";
  }
  addMessage("assistant", note);
  $("settings").close();
}

function newChat() {
  if (state.busy) return;
  setBusy(true);
  const reset = token()
    ? fetch("/api/agent/reset", { method: "POST", headers: headers() })
        .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
    : Promise.resolve({ ok: false, data: {} });
  reset
    .then(({ ok }) => {
      state.currentCircuitId = "";
      state.currentCircuitScore = 0;
      $("thread").textContent = "";
      return fetch("/api/workplace", { headers: headers() })
        .then((res) => res.json())
        .catch(() => ({ ready: state.ready, engines: [] }))
        .then((status) => ({ ok, status }));
    })
    .then(({ ok, status }) => {
      paintHealth(status);
      paintWelcome(status);
      applyCustomerRole();
      refreshInbox();
      if (!ok) {
        addMessage("assistant", "这一页已清空。要断开运行时会话，请用组内地址打开。");
      }
      $("prompt").focus();
    })
    .catch(() => {
      addMessage("assistant", "新对话这次没开成。");
    })
    .finally(() => setBusy(false));
}

async function boot() {
  token();
  try {
    const company = await (await fetch("/api/company")).json();
    if (company.company && company.company.legal_name) {
      $("legal").textContent = company.company.legal_name;
    }
  } catch (_err) {
    /* keep footer */
  }
  let status = { ready: false, engines: [], workplace: {} };
  try {
    status = await (await fetch("/api/workplace")).json();
  } catch (_err) {
    /* first visit */
  }
  state.ready = Boolean(status.ready);
  paintHealth(status);
  paintWelcome(status);
  fillSettings(status);
  applyCustomerRole();
  if ($("btn-new")) {
    $("btn-new").addEventListener("click", () => newChat());
  }
  $("btn-settings").addEventListener("click", () => {
    applyCustomerRole();
    revealStaffPackIfNeeded();
    $("settings").showModal();
  });
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.getAttribute("data-nav");
      if (name === "settings") {
        openSettingsDialog();
        return;
      }
      showInspector(name);
    });
  });
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => showInspector(btn.getAttribute("data-tab")));
  });
  document.querySelectorAll("[data-settings-tab]").forEach((btn) => {
    btn.addEventListener("click", () => showSettingsPage(btn.getAttribute("data-settings-tab")));
  });
  $("btn-save").addEventListener("click", () => saveSettings().catch(() => {
    addMessage("assistant", "设置没存上。");
  }));
  $("composer").addEventListener("submit", (ev) => {
    ev.preventDefault();
    send();
  });
  if ($("btn-attach") && $("circuit-file")) {
    $("btn-attach").addEventListener("click", () => $("circuit-file").click());
    $("circuit-file").addEventListener("change", (ev) => {
      const file = ev.target.files && ev.target.files[0];
      ev.target.value = "";
      attachCircuitFile(file);
    });
  }
  $("settings-form").addEventListener("submit", (ev) => {
    ev.stopPropagation();
  });
  $("prompt").addEventListener("keydown", (ev) => {
    if (ev.isComposing) return;
    if ($("settings").open) return;
    if (typingInField(ev.target) && ev.target !== $("prompt")) return;
    if (ev.key === "Enter" && !ev.shiftKey && ev.target === $("prompt")) {
      ev.preventDefault();
      send();
    }
  });
  if (!state.ready) {
    applyCustomerRole();
    revealStaffPackIfNeeded();
    $("settings").showModal();
  }
  refreshInbox();
  window.setInterval(() => {
    if (document.hidden) return;
    refreshInbox();
  }, 6000);
  $("prompt").focus();
}

boot();
