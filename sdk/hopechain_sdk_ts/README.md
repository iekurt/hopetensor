# hopechain-sdk (TypeScript) v0.1.0

## Install (local)
```bash
npm i
npm run build
```

## Usage (Gateway)
```ts
import { HopeChainClient } from "./dist/index.js";

const client = new HopeChainClient({
  baseUrl: "https://gateway.example.com/v1",
  apiKey: "YOUR_KEY"
});

const resp = await client.createTask({
  client_did: "did:hope:app:magazac-prod",
  task: {
    task_type: "chat",
    model_family: "llm_tr",
    model_hint: "vicdan-tr-8b",
    inputs: { messages: [{ role: "user", content: "Merhaba" }] },
    constraints: { max_tokens: 256, temperature: 0.4, top_p: 1.0, latency_sla_ms: 2500, max_cost_units: 120, privacy_level: "standard" },
    required_trace: { citations: false, tool_calls: false, safety_flags: true, reasoning_summary: true }
  },
  payment: { mode: "prepaid", budget_units: 200 },
  idempotency_key: "demo-1"
});

console.log(await client.getTask(resp.task_id));
```
