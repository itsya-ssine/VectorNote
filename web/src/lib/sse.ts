/** Minimal Server-Sent Events parsing, for the `/ask/stream` endpoint. */

export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Split a text buffer into complete events and the unfinished remainder.
 *
 * Network chunks can end anywhere, so the caller appends each decoded chunk to the previous
 * remainder and parses again. An event is complete once a blank line follows it.
 */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue; // comment or keep-alive
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      let value = colon === -1 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length > 0) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}
