import type { components } from "./generated";
import { apiRequest } from "./client";

export type Nonconformance = components["schemas"]["NonconformanceResponse"];
export type NonconformanceDisposition = components["schemas"]["NonconformanceDispositionResponse"];
export type NonconformanceCreateRequest = components["schemas"]["NonconformanceCreateRequest"];
export type NonconformanceUpdateRequest = components["schemas"]["NonconformanceUpdateRequest"];
export type NonconformanceApproval = components["schemas"]["NonconformanceApprovalResponse"];

const jsonHeaders = { "Content-Type": "application/json" };

export async function getDispositions(includeInactive = false, sessionHandle?: string) {
  const query = includeInactive ? "?include_inactive=true" : "";
  return (await apiRequest<NonconformanceDisposition[]>(`/api/v1/nonconformance-dispositions${query}`, {}, sessionHandle)).body;
}

export async function getNonconformances(sessionHandle?: string) {
  return (await apiRequest<Nonconformance[]>(`/api/v1/nonconformances`, {}, sessionHandle)).body;
}

export async function getNonconformance(id: string, sessionHandle?: string) {
  return (await apiRequest<Nonconformance>(`/api/v1/nonconformances/${id}`, {}, sessionHandle)).body;
}

export async function createNonconformance(data: NonconformanceCreateRequest, sessionHandle?: string) {
  return (await apiRequest<Nonconformance>(`/api/v1/nonconformances`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function updateNonconformance(
  id: string,
  lockVersion: number,
  data: NonconformanceUpdateRequest,
  sessionHandle?: string,
) {
  return (await apiRequest<Nonconformance>(`/api/v1/nonconformances/${id}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function approveNonconformance(id: string, lockVersion: number, sessionHandle?: string) {
  return (await apiRequest<NonconformanceApproval>(`/api/v1/nonconformances/${id}/approve`, {
    method: "POST",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
  }, sessionHandle)).body;
}

export async function rejectNonconformance(id: string, lockVersion: number, sessionHandle?: string) {
  return (await apiRequest<NonconformanceApproval>(`/api/v1/nonconformances/${id}/reject`, {
    method: "POST",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
  }, sessionHandle)).body;
}
