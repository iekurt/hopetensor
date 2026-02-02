# HOPE Chain Decentralized AI - Tech Spec Artifacts (v0.1.0)

Contents:
- openapi.yaml: Gateway + Node RPC (Worker/Verifier) OpenAPI 3.1 spec
- schemas/: JSON Schema files
- hoped/hoped.py: CLI skeleton (argparse) for worker/verifier/node/bench
- chain/: Solidity event interface stub (optional)

Quick use:
- Validate payloads with schemas (any jsonschema validator)
- Generate clients from openapi.yaml (openapi-generator)
- Extend hoped.py to launch FastAPI/uvicorn servers implementing /v1/health /v1/execute /v1/verify
