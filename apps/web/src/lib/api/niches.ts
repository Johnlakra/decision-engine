import type { components } from "@decision-engine/client";
import { requestJson } from "@/lib/api/request";
import type { NicheConfig } from "@/lib/niches/yaml";

export { ApiError } from "@/lib/api/request";

export type NicheRow = components["schemas"]["NicheRow"];
export type NicheList = components["schemas"]["NicheList"];
export type NicheDetail = components["schemas"]["NicheDetail"];

export function fetchNiches(): Promise<NicheList> {
  return requestJson<NicheList>("GET", "/niches");
}

export function fetchNiche(name: string): Promise<NicheDetail> {
  return requestJson<NicheDetail>("GET", `/niches/${encodeURIComponent(name)}`);
}

/** Saves the whole config. All-or-nothing on the server: a 422 writes nothing. */
export function saveNiche(name: string, config: NicheConfig): Promise<NicheDetail> {
  return requestJson<NicheDetail>("PUT", `/niches/${encodeURIComponent(name)}`, config);
}
