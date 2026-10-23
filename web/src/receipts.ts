import type { CommandReceipt } from "./types";

// A delayed poll must not turn an already applied command back into pending.
export function mergeReceipts(current: CommandReceipt[], incoming: CommandReceipt[]) {
  const rows = new Map(current.map(row => [row.id, row]));
  for (const row of incoming) {
    const previous = rows.get(row.id);
    if (!previous || previous.status === "pending") rows.set(row.id, row);
  }
  const order = [...new Set([...incoming, ...current].map(row => row.id))];
  return order.slice(0, 100).map(id => rows.get(id)!);
}
