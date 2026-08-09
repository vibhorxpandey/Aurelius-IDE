export type ActivityKind = "connect" | "structural" | "verified" | "gate" | "search" | "error";

export interface ActivityEvent {
  id: number;
  time: number;
  kind: ActivityKind;
  title: string;
  details: string[];
}

let counter = 0;

export function makeEvent(kind: ActivityKind, title: string, details: string[] = []): ActivityEvent {
  return { id: ++counter, time: Date.now(), kind, title, details };
}
