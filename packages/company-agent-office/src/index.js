import { registerCapabilityTools } from "@unitqc/company-agent-core/runtime";

export const name = "company-agent-office";
export const inject = ["tools"];

export function apply(ctx) {
  // company.office is the WPS-suite porting slice over the mounted workspace:
  // P1 bounded extraction (docx/xlsx/pptx/pdf/text), P2 bounded single-file
  // artifact creation, P3 surgical w:ins/w:del edits + line diff + declarative
  // charts, P4.5 matter artifacts (timeline/chronology/mindmap), the L4
  // companion read-only format audit (baseline GB/T 9704 draft vs imported
  // describe), the §4.5 pptx slice (structured-layout render + in-place
  // shape text rewrite with a read-back B5 gate), and the L6/L7 exit:
  // local soffice conversion, open-in-WPS, pptx preview, review tables,
  // reversible file moves, format fix and the revision surface.
  // The preset catalog filter decides visibility (boot/lab/algo see it, sign does not).
  // Every call resolves the bounded workspace the core runtime forwards and fails closed outside it.
  // standard-library work over the mounted workspace, so no ask gate applies
  // (writes carry their audit line).
  registerCapabilityTools(ctx, ["company.office"]);
}
