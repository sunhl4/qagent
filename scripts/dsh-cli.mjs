import { fileURLToPath, pathToFileURL } from "node:url";

// Only the isolated, device-free local demo may add the presentation shell.
// minimal supports boot and algo presets; the demo UI stays presentation-only in
// both, while device execution remains gated by the kernel policy (deny in algo).
// The full company-agent profile may keep the same presentation shell: the patch
// only adds slot composition and never mounts agent tools; lab/sign approval
// still happens in the kernel, so presentation stays policy-neutral.
if (process.env.COMPANY_AGENT_DEMO_UI === "1") {
  const profile = process.env.COMPANY_AGENT_PROFILE;
  const preset = process.env.COMPANY_AGENT_PRESET || "";
  const compatible = profile === "company-agent-minimal"
    ? ["boot", "algo"].includes(preset)
    : profile === "company-agent"
      ? ["lab", "sign"].includes(preset)
      : false;
  if (process.env.COMPANY_AGENT_DEPLOYMENT_MODE !== "development" || !compatible) {
    throw new Error("Workspace demo UI requires development with company-agent-minimal (boot|algo) or company-agent (lab|sign)");
  }
  process.argv.splice(2, 0, "--patch", fileURLToPath(new URL("../apps/company-workspace/cordis.patch.yml", import.meta.url)));
}

const entry = process.env.COMPANY_AGENT_DSH_ENTRY;
if (!entry) throw new Error("COMPANY_AGENT_DSH_ENTRY is required");
const module = await import(pathToFileURL(entry).href);
if (typeof module.runCli !== "function") throw new Error("installed DSH does not export runCli");
await module.runCli();
