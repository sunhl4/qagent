/** Skeleton execute. Replace fill() with a real call. */
export class FillSlotError extends Error {
  constructor(public slotId: string, public where: string) {
    super(`empty slot ${slotId}: fill ${where}`);
    this.name = "FillSlotError";
  }
}

export function fill(slotId: string, where: string): never {
  throw new FillSlotError(slotId, where);
}
