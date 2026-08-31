import type { Context } from "../../../seams/dsh.d.ts";

export const name = "qagent-eln";
export const inject = ["tools"];

export function apply(_ctx: Context) {
  // Event writes go through Python invoke() → services.eln.
  // dsh session JSON is not the science source of truth.
}
