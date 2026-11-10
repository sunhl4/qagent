import { readFileSync } from "node:fs";

const moduleUrl = new URL("../research-layer/packages/domain/src/failure.ts", import.meta.url);
const mod = await import(moduleUrl.href);

const STAGES = new Set([
  "compile",
  "policy",
  "quote",
  "submit",
  "execution",
  "artifacts",
  "decision",
  "unknown_execution",
  "loop",
]);
const CODE = /^[A-Z][A-Z0-9_]{0,39}$/;
const ALLOWED = new Set(["stage", "code", "portErrorCode"]);

function emit(value) {
  process.stdout.write(JSON.stringify(value));
}

let input;
try {
  input = JSON.parse(readFileSync(0, "utf8"));
} catch {
  emit({ ok: false });
  process.exit(0);
}

if (!input || typeof input !== "object" || Array.isArray(input)) {
  emit({ ok: false });
  process.exit(0);
}
if (Object.keys(input).some((key) => !ALLOWED.has(key)) || !STAGES.has(input.stage)) {
  emit({ ok: false });
  process.exit(0);
}

const payload = { stage: input.stage };
for (const key of ["code", "portErrorCode"]) {
  if (input[key] === undefined) continue;
  if (typeof input[key] !== "string" || !CODE.test(input[key])) {
    emit({ ok: false });
    process.exit(0);
  }
  payload[key] = input[key];
}

const record = mod.classifyFailure(payload);
const category = record.category;
emit({
  ok: true,
  category,
  code: record.code,
  stage: record.stage,
  retryable: category === "unknown" ? false : record.retryable === true,
});
