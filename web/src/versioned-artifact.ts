import { z } from "zod";

export const timestamp = z.string().datetime({ offset: true });
export const digest = z.string().regex(/^[a-f0-9]{64}$/);
export const finite = z.number().finite();
export const probability = finite.min(0).max(1);
export const count = z.number().int().nonnegative();
export const sourceURL = z.string().url().refine(url => url.startsWith("https://"), "Source must use HTTPS");
export type Versioned<T> = { data: T; file: string; sha256: string };

/** Read a bounded, content-addressed local artifact. A failed check never becomes a partial success. */
export async function loadVersioned<T>(directory: "operations" | "research" | "context", prefix: string, schema: z.ZodType<T>): Promise<Versioned<T>> {
  const base = `${import.meta.env.BASE_URL}data/${directory}/`;
  async function read(file: string, limit: number) {
    const response = await fetch(base + file, { cache: "no-store" });
    if (!response.ok) throw new Error("missing");
    const text = await response.text();
    if (text.length > limit) throw new Error("size");
    return text;
  }
  try {
    const pointer = z.object({ schema_version: z.literal(1), file: z.string(), sha256: digest, generated_at: timestamp }).parse(JSON.parse(await read("latest.json", 2000)));
    if (pointer.file !== `${prefix}-${pointer.sha256}.json`) throw new Error("path");
    const text = await read(pointer.file, 5_000_000);
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    const sha256 = Array.from(new Uint8Array(bytes)).map(x => x.toString(16).padStart(2, "0")).join("");
    if (sha256 !== pointer.sha256) throw new Error("checksum");
    const data = schema.parse(JSON.parse(text));
    if ((data as { generated_at?: string }).generated_at !== pointer.generated_at) throw new Error("metadata");
    return { data, file: pointer.file, sha256 };
  } catch {
    throw new Error(`${directory === "operations" ? "Forecast operations" : directory === "context" ? "Current matchup context" : "Model research"} data is unavailable or failed integrity validation. No unverified results are displayed.`);
  }
}

/** ISO timestamps retain Python microseconds; Date.parse alone loses a strict temporal boundary. */
export function compareTimestamp(a: string, b: string): number {
  const millis = Date.parse(a) - Date.parse(b);
  if (millis) return millis;
  const remainder = (s:string) => Number((s.match(/\.(\d+)(?:Z|[+-]\d{2}:\d{2})$/)?.[1] ?? "").padEnd(9,"0").slice(3,9));
  return remainder(a) - remainder(b);
}
