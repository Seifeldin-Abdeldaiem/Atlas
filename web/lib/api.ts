"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number) {
    super(message);
  }
}

export type Field = { key: string; label: string; use: "analysis" | "context" | "display"; required: boolean };

export type Warning = {
  code: string;
  severity: "warning" | "info";
  title: string;
  detail: string;
  count: number;
  rows: number[];
};

export type ColumnInfo = { name: string; field: string | null; use: string | null; fill_percent: number; sample: string };

export type Kind = "tasks" | "catalogue";

export type Report = {
  kind?: Kind;
  rows_read: number;
  rows_ready: number;
  row_label: "row" | "item";
  blocking: { code: string; message: string }[];
  warnings: Warning[];
  columns: ColumnInfo[];
};

export type Dataset = {
  id: string;
  name: string;
  kind: Kind;
  status: "parsing" | "ready" | "blocked" | "failed" | "analysing" | "analysed";
  error: { code: string; message: string } | null;
  created_at: string;
  file: {
    name: string | null;
    size_bytes: number | null;
    format: "csv" | "xlsx" | "json" | null;
    sheet: string | null;
    sheets: { name: string; approx_rows: number }[];
    raw_file_deleted_at: string | null;
    raw_file_expires_at: string | null;
  };
  columns: string[];
  mapping: Record<string, string | null>;
  report: Report | null;
  analysis: {
    state: "queued" | "running" | "done" | "failed";
    stage?: string;
    progress?: number;
    summary?: AnalysisSummary;
    error?: { code: string; message: string };
  } | null;
  export: ExportState;
  fields: Field[];
};

export type DatasetSummary = {
  id: string;
  name: string;
  kind: Kind;
  status: Dataset["status"];
  created_at: string;
  file_name: string | null;
  rows_read: number | null;
  rows_ready: number | null;
};

export type RowsPage = {
  columns: string[];
  total: number;
  rows: { row_number: number; values: Record<string, string>; malformed: string | null }[];
};

async function parse(res: Response): Promise<unknown> {
  if (res.status === 204) return null;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const error = (body as { error?: { message?: string; code?: string } } | null)?.error;
    throw new ApiError(error?.message ?? "Something went wrong. Try again.", error?.code ?? "unknown", res.status);
  }
  return body;
}

/** Returns a fetch function that sends the Clerk session token. */
export function useApi() {
  const { getToken } = useAuth();
  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
      let res: Response;
      try {
        res = await fetch(`${API_URL}${path}`, { ...init, headers });
      } catch {
        throw new ApiError("We couldn't reach Atlas. Check your connection and try again.", "network", 0);
      }
      return (await parse(res)) as T;
    },
    [getToken],
  );
}

/** Uploads with real progress (fetch can't report upload progress). */
export function uploadFile(token: string | null, file: File, onProgress: (fraction: number) => void): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/v1/datasets`);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new ApiError("We couldn't reach Atlas. Check your connection and try again.", "network", 0));
    xhr.onload = () => {
      let body: { id?: string; error?: { message?: string; code?: string } } | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && body?.id) resolve({ id: body.id });
      else reject(new ApiError(body?.error?.message ?? "The upload didn't go through. Try again.", body?.error?.code ?? "unknown", xhr.status));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const FORMAT_NAMES: Record<string, string> = { csv: "CSV file", xlsx: "Excel workbook", json: "JSON file" };

// ---------------------------------------------------------------- analysis results

export type StockHeadline = {
  has_stock: boolean;
  has_cost: boolean;
  currency: string | null;
  mixed_currencies: string[];
  units_on_duplicates: number | null;
  value_on_duplicates: number | null;
  groups_with_cost_gap: number;
  groups_units_differ: number;
};

export type AnalysisSummary = {
  items: number;
  groups: number;
  duplicate_lines: number;
  lookalikes: number;
  needs_review: number;
  groups_reviewed?: number;
  ai_reviewed: number;
  ai: "on" | "off" | "not_configured" | "tests";
  ai_usage?: { stopped: string | null } | null;
  stock?: StockHeadline;
};

export type ItemView = {
  row_number: number;
  item_code: string | null;
  name: string | null;
  brand: string | null;
  part_number: string | null;
  stock: number | null;
  unit_cost: number | null;
  currency: string | null;
};

export type Member = ItemView & { role: "master" | "duplicate" };

export type DuplicateGroup = {
  id: string;
  confidence: "high" | "medium" | "reviewed";
  reasons: string[];
  name_standard: string | null;
  master_row: number;
  stock_total: number | null;
  stock_on_duplicates: number | null;
  value_on_duplicates: number | null;
  cost_low: number | null;
  cost_high: number | null;
  members: Member[];
};

export type PairView = { a: ItemView; b: ItemView; reason: string; detail: string; similarity: number; source: string };

export type ExportState = {
  state: "building" | "ready" | "failed";
  file?: { name: string; size_bytes: number; format: string; expires_at: string };
  error?: { code: string; message: string };
} | null;

export type WorkspaceSettings = { ai_review: boolean; ai_available: boolean; ai_model: string; currency: string; can_edit: boolean };

/** Downloads a file from the API with the session token and saves it. */
export async function downloadFrom(token: string | null, path: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError("We couldn't reach Atlas. Check your connection and try again.", "network", 0);
  }
  if (!res.ok) await parse(res);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="([^"]+)"/i.exec(disposition)?.[1];
  const name = encoded ? decodeURIComponent(encoded) : plain ?? "atlas-export";
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function formatMoney(value: number | null | undefined, currency: string | null | undefined): string {
  if (value == null) return "";
  if (!currency) return value.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  try {
    return value.toLocaleString("en-GB", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function formatNumber(value: number | null | undefined): string {
  return value == null ? "" : value.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}
