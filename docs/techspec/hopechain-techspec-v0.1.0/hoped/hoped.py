#!/usr/bin/env python3
"""hoped - HOPE Chain node daemon CLI (v0.1.0)

Subcommands:
  worker run
  verifier run
  node register
  node attest
  bench run
  bench sign

This is a skeleton you can wire into FastAPI/uvicorn or any HTTP server.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

VERSION = "0.1.0"

def eprint(*args):
    print(*args, file=sys.stderr)

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def cmd_worker_run(args: argparse.Namespace) -> int:
    # Placeholder: start your worker HTTP server here
    eprint("[hoped] worker run")
    eprint(" node_did:", args.node_did)
    eprint(" listen  :", args.listen)
    eprint(" models  :", args.models)
    eprint(" pricing :", args.pricing)
    eprint(" stake   :", args.stake)
    eprint(" chain   :", args.chain_rpc)
    eprint("NOTE: wire this into your server (FastAPI/uvicorn) and implement /v1/execute, /v1/health")
    return 0

def cmd_verifier_run(args: argparse.Namespace) -> int:
    eprint("[hoped] verifier run")
    eprint(" node_did  :", args.node_did)
    eprint(" listen    :", args.listen)
    eprint(" profile   :", args.profile)
    eprint(" threshold :", args.threshold)
    eprint(" chain     :", args.chain_rpc)
    eprint("NOTE: implement /v1/verify, /v1/health")
    return 0

def cmd_node_register(args: argparse.Namespace) -> int:
    caps = load_json(args.capabilities)
    out = {
        "node_did": args.node_did,
        "role": args.role,
        "capabilities": caps,
        "ts": int(time.time()),
        "version": VERSION,
    }
    save_json(args.out, out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

def cmd_node_attest(args: argparse.Namespace) -> int:
    out = {
        "node_did": args.node_did,
        "attestation": args.attestation,
        "proof_path": args.proof,
        "ts": int(time.time()),
        "version": VERSION,
    }
    save_json(args.out, out)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

def cmd_bench_run(args: argparse.Namespace) -> int:
    # Minimal placeholder benchmark report
    report = {
        "suite": args.suite,
        "node_did": args.node_did,
        "metrics": {
            "throughput_tps": 0,
            "p95_latency_ms": 0,
            "gpu": args.gpu or "unknown"
        },
        "ts": int(time.time()),
        "version": VERSION
    }
    save_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

def cmd_bench_sign(args: argparse.Namespace) -> int:
    # Placeholder: sign bench report with Ed25519 (implement with pynacl/cryptography)
    report = load_json(args.infile)
    signed = {
        "report": report,
        "signature": "TODO_BASE64_ED25519_SIGNATURE",
        "signer_did": args.node_did,
        "ts": int(time.time()),
        "version": VERSION
    }
    save_json(args.out, signed)
    print(json.dumps(signed, ensure_ascii=False, indent=2))
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hoped", description="HOPE Chain node daemon CLI")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    sub = p.add_subparsers(dest="cmd", required=True)

    # worker run
    worker = sub.add_parser("worker", help="Worker node commands")
    worker_sub = worker.add_subparsers(dest="subcmd", required=True)
    worker_run = worker_sub.add_parser("run", help="Run worker server")
    worker_run.add_argument("--node-did", required=True)
    worker_run.add_argument("--listen", default="0.0.0.0:8080")
    worker_run.add_argument("--models", required=True, help="comma-separated model ids")
    worker_run.add_argument("--pricing", default="per1k=12")
    worker_run.add_argument("--stake", type=int, default=0)
    worker_run.add_argument("--chain-rpc", default="")
    worker_run.set_defaults(func=cmd_worker_run)

    # verifier run
    verifier = sub.add_parser("verifier", help="Verifier node commands")
    verifier_sub = verifier.add_subparsers(dest="subcmd", required=True)
    verifier_run = verifier_sub.add_parser("run", help="Run verifier server")
    verifier_run.add_argument("--node-did", required=True)
    verifier_run.add_argument("--listen", default="0.0.0.0:8081")
    verifier_run.add_argument("--profile", default="standard", choices=["standard","high_trust_required","confidential"])
    verifier_run.add_argument("--threshold", type=float, default=0.90)
    verifier_run.add_argument("--chain-rpc", default="")
    verifier_run.set_defaults(func=cmd_verifier_run)

    # node register/attest
    node = sub.add_parser("node", help="Node identity commands")
    node_sub = node.add_subparsers(dest="subcmd", required=True)

    node_reg = node_sub.add_parser("register", help="Create a node registration payload")
    node_reg.add_argument("--node-did", required=True)
    node_reg.add_argument("--role", required=True, choices=["worker","verifier"])
    node_reg.add_argument("--capabilities", required=True, help="caps json file")
    node_reg.add_argument("--out", default="node_registration.json")
    node_reg.set_defaults(func=cmd_node_register)

    node_att = node_sub.add_parser("attest", help="Create an attestation payload")
    node_att.add_argument("--node-did", required=True)
    node_att.add_argument("--attestation", required=True)
    node_att.add_argument("--proof", required=True)
    node_att.add_argument("--out", default="node_attestation.json")
    node_att.set_defaults(func=cmd_node_attest)

    # bench
    bench = sub.add_parser("bench", help="Benchmark commands")
    bench_sub = bench.add_subparsers(dest="subcmd", required=True)

    bench_run = bench_sub.add_parser("run", help="Run a benchmark suite (placeholder)")
    bench_run.add_argument("--suite", default="llm_small")
    bench_run.add_argument("--node-did", default="did:hope:node:unknown")
    bench_run.add_argument("--gpu", default="")
    bench_run.add_argument("--out", default="bench_report.json")
    bench_run.set_defaults(func=cmd_bench_run)

    bench_sign = bench_sub.add_parser("sign", help="Sign a benchmark report (placeholder)")
    bench_sign.add_argument("--node-did", required=True)
    bench_sign.add_argument("--in", dest="infile", required=True)
    bench_sign.add_argument("--out", default="bench_report.signed.json")
    bench_sign.set_defaults(func=cmd_bench_sign)

    return p

def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
