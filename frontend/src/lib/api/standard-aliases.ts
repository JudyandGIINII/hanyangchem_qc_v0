import type { components } from "./generated";
import { apiRequest } from "./client";

export type StandardTestItemAlias = components["schemas"]["StandardTestItemAliasResponse"];
export type StandardTestItemAliasCreateRequest = components["schemas"]["StandardTestItemAliasCreateRequest"];
export type StandardTestItemAliasUpdateRequest = components["schemas"]["StandardTestItemAliasUpdateRequest"];

const jsonHeaders = { "Content-Type": "application/json" };

export async function getAliases(sessionHandle?: string) {
  return (await apiRequest<StandardTestItemAlias[]>("/api/v1/standard-test-item-aliases", {}, sessionHandle)).body;
}

export async function lookupAlias(aliasText: string, sessionHandle?: string) {
  const query = `?alias_text=${encodeURIComponent(aliasText)}`;
  return (await apiRequest<StandardTestItemAlias | null>(`/api/v1/standard-test-item-aliases/lookup${query}`, {}, sessionHandle)).body;
}

export async function getAlias(aliasId: string, sessionHandle?: string) {
  return (await apiRequest<StandardTestItemAlias>(`/api/v1/standard-test-item-aliases/${aliasId}`, {}, sessionHandle)).body;
}

export async function createAlias(data: StandardTestItemAliasCreateRequest, sessionHandle?: string) {
  return (await apiRequest<StandardTestItemAlias>("/api/v1/standard-test-item-aliases", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function updateAlias(
  aliasId: string,
  lockVersion: number,
  data: StandardTestItemAliasUpdateRequest,
  sessionHandle?: string,
) {
  return (await apiRequest<StandardTestItemAlias>(`/api/v1/standard-test-item-aliases/${aliasId}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function deleteAlias(aliasId: string, lockVersion: number, sessionHandle?: string) {
  return (await apiRequest<{ message: string }>(`/api/v1/standard-test-item-aliases/${aliasId}`, {
    method: "DELETE",
    headers: { "If-Match": String(lockVersion) },
  }, sessionHandle)).body;
}
