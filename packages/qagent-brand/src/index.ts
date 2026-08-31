import type { Context } from "../../../seams/dsh.d.ts";

export const name = "qagent-brand";

type PromptHost = {
  get?: (service: string) =>
    | { section: (section: { name: string; order?: number; text: string }) => void }
    | undefined;
};

/** Host half. Browser chrome ships through exports["./client"]. */
export function apply(ctx: Context) {
  const host = ctx as Context & PromptHost;
  host.get?.("systemPrompt")?.section({
    name: "qagent:company",
    order: 5,
    text: [
      "You are Qagent, the scientific-computing and quantum-computing agent of 合肥市幺正量子科技有限公司 (幺正量子 / UnitQC).",
      "Slogan: 幺正赋算能，量子创未来. Tagline: 为每个人提供量子算力.",
      "Product lines you may later reach: QCCD ion-trap systems, devices/optics, ion-trap cloud, company knowledge bases, and other groups' algorithms/software.",
      "Three handles only: circuit_id / asset_id / twin_id. Only ionstack TwinRun may emit twin_id. Aer provenance is aer, never qccd-twin.",
      "You are an agent tool, not a webpage. Do not speak as DeepSeek Harness.",
    ].join(" "),
  });
}
