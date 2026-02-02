import type { TaskCreateRequest, TaskCreateResponse, TaskGetResponse } from "./types";

export class HopeChainError extends Error {
  status?: number;
  payload?: any;
  constructor(message: string, status?: number, payload?: any) {
    super(message);
    this.name = "HopeChainError";
    this.status = status;
    this.payload = payload;
  }
}

export interface HopeChainClientOptions {
  baseUrl: string;    // e.g. https://gateway.example.com/v1
  apiKey?: string;    // Bearer token
  timeoutMs?: number; // default 30000
}

export class HopeChainClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeoutMs: number;

  constructor(opts: HopeChainClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, "");
    this.apiKey = opts.apiKey;
    this.timeoutMs = opts.timeoutMs ?? 30000;
  }

  private headers(extra?: Record<string,string>): HeadersInit {
    const h: Record<string,string> = { "Content-Type": "application/json" };
    if (this.apiKey) h["Authorization"] = `Bearer ${this.apiKey}`;
    return { ...h, ...(extra ?? {}) };
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, { ...init, signal: ctrl.signal });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      const payload = ct.includes("application/json") ? await res.json() : await res.text();

      if (!res.ok) throw new HopeChainError(`HTTP ${res.status}`, res.status, payload);
      if (payload && typeof payload === "object" && (payload as any).ok === false) {
        throw new HopeChainError(`API error`, res.status, payload);
      }
      return payload as T;
    } finally {
      clearTimeout(t);
    }
  }

  // Gateway
  createTask(req: TaskCreateRequest): Promise<TaskCreateResponse> {
    return this.request<TaskCreateResponse>("/tasks", {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(req),
    });
  }

  getTask(taskId: string): Promise<TaskGetResponse> {
    return this.request<TaskGetResponse>(`/tasks/${encodeURIComponent(taskId)}`, {
      method: "GET",
      headers: this.headers(),
    });
  }

  // Node RPC helpers (use node baseUrl)
  nodeHealth(): Promise<any> {
    return this.request<any>("/health", { method: "GET", headers: this.headers() });
  }

  workerExecute(payload: any): Promise<any> {
    return this.request<any>("/execute", { method: "POST", headers: this.headers(), body: JSON.stringify(payload) });
  }

  verifierVerify(payload: any): Promise<any> {
    return this.request<any>("/verify", { method: "POST", headers: this.headers(), body: JSON.stringify(payload) });
  }
}
