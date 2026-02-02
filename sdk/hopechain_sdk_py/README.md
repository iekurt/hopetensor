# hopechain-sdk (Python) v0.1.0

## Install (local)
```bash
pip install -e .
```

## Usage (Gateway)
```python
from hopechain_sdk import HopeChainClient

client = HopeChainClient("https://gateway.example.com/v1", api_key="YOUR_KEY")

req = {
  "client_did": "did:hope:app:magazac-prod",
  "task": {
    "task_type": "chat",
    "model_family": "llm_tr",
    "model_hint": "vicdan-tr-8b",
    "inputs": {"messages": [{"role":"user","content":"Merhaba"}]},
    "constraints": {"max_tokens": 256, "temperature": 0.4, "top_p": 1.0, "latency_sla_ms": 2500, "max_cost_units": 120, "privacy_level": "standard"},
    "required_trace": {"citations": False, "tool_calls": False, "safety_flags": True, "reasoning_summary": True}
  },
  "payment": {"mode":"prepaid","budget_units": 200},
  "idempotency_key": "demo-1"
}

resp = client.create_task(req)
task_id = resp["task_id"]
print(client.get_task(task_id))
```
