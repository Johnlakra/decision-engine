export type SourceHealth = "ok" | "failing" | "paused";

export function sourceHealth(source: { readonly enabled: boolean; readonly error_count: number }): SourceHealth {
  if (!source.enabled) {
    return "paused";
  }
  return source.error_count > 0 ? "failing" : "ok";
}
