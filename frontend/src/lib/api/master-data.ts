import type { components } from "./generated";
import { apiRequest } from "./client";

export type Supplier = components["schemas"]["SupplierResponse"];
export type SupplierCreateRequest = components["schemas"]["SupplierCreateRequest"];
export type SupplierUpdateRequest = components["schemas"]["SupplierUpdateRequest"];

export type Material = components["schemas"]["MaterialResponse"];
export type MaterialCreateRequest = components["schemas"]["MaterialCreateRequest"];
export type MaterialUpdateRequest = components["schemas"]["MaterialUpdateRequest"];

export type MaterialModel = components["schemas"]["MaterialModelResponse"];
export type MaterialModelCreateRequest = components["schemas"]["MaterialModelCreateRequest"];
export type MaterialModelUpdateRequest = components["schemas"]["MaterialModelUpdateRequest"];

const jsonHeaders = { "Content-Type": "application/json" };

export async function getSuppliers(sessionHandle?: string) {
  return (await apiRequest<Supplier[]>("/api/v1/suppliers", {}, sessionHandle)).body;
}

export async function getSupplier(supplierId: string, sessionHandle?: string) {
  return (await apiRequest<Supplier>(`/api/v1/suppliers/${supplierId}`, {}, sessionHandle)).body;
}

export async function createSupplier(data: SupplierCreateRequest, sessionHandle?: string) {
  return (await apiRequest<Supplier>("/api/v1/suppliers", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function updateSupplier(
  supplierId: string,
  lockVersion: number,
  data: SupplierUpdateRequest,
  sessionHandle?: string,
) {
  return (await apiRequest<Supplier>(`/api/v1/suppliers/${supplierId}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function getMaterials(sessionHandle?: string) {
  return (await apiRequest<Material[]>("/api/v1/materials", {}, sessionHandle)).body;
}

export async function getMaterial(materialId: string, sessionHandle?: string) {
  return (await apiRequest<Material>(`/api/v1/materials/${materialId}`, {}, sessionHandle)).body;
}

export async function createMaterial(data: MaterialCreateRequest, sessionHandle?: string) {
  return (await apiRequest<Material>("/api/v1/materials", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function updateMaterial(
  materialId: string,
  lockVersion: number,
  data: MaterialUpdateRequest,
  sessionHandle?: string,
) {
  return (await apiRequest<Material>(`/api/v1/materials/${materialId}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function getMaterialModels(sessionHandle?: string) {
  return (await apiRequest<MaterialModel[]>("/api/v1/material-models", {}, sessionHandle)).body;
}

export async function getMaterialModel(modelId: string, sessionHandle?: string) {
  return (await apiRequest<MaterialModel>(`/api/v1/material-models/${modelId}`, {}, sessionHandle)).body;
}

export async function createMaterialModel(data: MaterialModelCreateRequest, sessionHandle?: string) {
  return (await apiRequest<MaterialModel>("/api/v1/material-models", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}

export async function updateMaterialModel(
  modelId: string,
  lockVersion: number,
  data: MaterialModelUpdateRequest,
  sessionHandle?: string,
) {
  return (await apiRequest<MaterialModel>(`/api/v1/material-models/${modelId}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(lockVersion) },
    body: JSON.stringify(data),
  }, sessionHandle)).body;
}
