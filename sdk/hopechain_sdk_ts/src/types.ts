export type PrivacyLevel = "public" | "standard" | "restricted" | "confidential";
export type TaskType = "chat" | "embed" | "classify" | "summarize" | "vision" | "agent";
export type ModelFamily = "llm_tr" | "llm_en" | "multimodal" | "small_fast";
export type VerificationProfile = "standard" | "high_trust_required" | "confidential";
export type Verdict = "accepted" | "rejected" | "retry";

export interface RequiredTrace {
  citations: boolean;
  tool_calls: boolean;
  safety_flags: boolean;
  reasoning_summary: boolean;
}

export interface Constraints {
  max_tokens: number;
  temperature: number;
  top_p: number;
  latency_sla_ms: number;
  max_cost_units: number;
  privacy_level: PrivacyLevel;
}

export interface Task {
  task_type: TaskType;
  model_family: ModelFamily;
  model_hint: string;
  inputs: Record<string, any>;
  constraints: Constraints;
  required_trace: RequiredTrace;
}

export interface Payment {
  mode: "prepaid" | "postpaid";
  budget_units: number;
}

export interface TaskCreateRequest {
  client_did: string;
  task: Task;
  payment: Payment;
  idempotency_key: string;
}

export interface TaskCreateResponse {
  ok: boolean;
  task_id: string;
  status: "queued";
  estimated_start_ms?: number;
  trace_id?: string;
}

export interface TaskGetResponse {
  ok: boolean;
  task_id: string;
  status: "queued" | "running" | "done" | "failed";
  assigned?: any;
  result?: any;
  error?: any;
}
