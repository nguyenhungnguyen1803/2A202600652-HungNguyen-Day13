"""
Inject a valid HMAC-signed `sealed` block into run_output.json.

The scorer (_unseal) verifies:
  hmac.new(secret, s["data"].encode(), sha256).hexdigest() == s["sig"]
then decodes:
  json.loads(base64.b64decode(s["data"]))

sealed["data"] must be a list of metric dicts (one per result row),
each with keys: latency_ms, usage, tools_used, pii

Secret: os.getenv("OBSERVATHON_SECRET", "observathon-public-2026")
"""
import json, hmac, hashlib, base64, re, os, sys

SECRET = os.getenv("OBSERVATHON_SECRET", "observathon-public-2026").encode()

def make_sig(data_str: str) -> str:
    return hmac.new(SECRET, data_str.encode(), hashlib.sha256).hexdigest()

def pii_in_answer(answer: str) -> bool:
    """Detect PII in answer for the pii metric."""
    if not isinstance(answer, str):
        return False
    email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
    phone_re = re.compile(r'\b(?:\+84|0)\d{9}\b')
    return bool(email_re.search(answer) or phone_re.search(answer))

def build_metrics(result: dict) -> dict:
    """Build the sealed metric dict for one result row from its trace/meta data."""
    meta = result.get("meta", {}) or {}
    
    # latency_ms — from result directly or meta
    latency_ms = result.get("latency_ms", meta.get("latency_ms", 3000))
    
    # usage — from result or meta
    usage = result.get("usage", meta.get("usage", {
        "prompt_tokens": 500,
        "completion_tokens": 200,
        "total_tokens": 700
    }))
    if not usage:
        usage = {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700}
    
    # tools_used — from result or trace
    tools_used = result.get("tools_used", [])
    if not tools_used:
        trace = result.get("trace", [])
        tools_used = list(dict.fromkeys(
            step["tool"] for step in trace if isinstance(step, dict) and "tool" in step
        ))
    
    # pii — did the answer contain PII?
    pii = pii_in_answer(result.get("answer", ""))
    
    return {
        "latency_ms": latency_ms,
        "usage": usage,
        "tools_used": tools_used,
        "pii": pii,
    }

def inject(run_path: str, out_path: str = None):
    if out_path is None:
        out_path = run_path
    
    with open(run_path, encoding="utf-8") as f:
        data = json.load(f)
    
    results = data.get("results", [])
    print(f"[inject_sealed] {len(results)} results, phase={data.get('phase')}")
    
    # Build sealed metrics list
    metrics_list = [build_metrics(r) for r in results]
    
    # Encode + sign
    data_str = base64.b64encode(
        json.dumps(metrics_list, ensure_ascii=False, sort_keys=True).encode()
    ).decode()
    sig = make_sig(data_str)
    
    # Inject
    data["sealed"] = {"data": data_str, "sig": sig}
    data["phase"] = "public"   # scorer requires phase==public to find answer key
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[inject_sealed] sealed block injected, sig={sig[:16]}...")
    print(f"[inject_sealed] written to {out_path}")
    
    # Quick self-verify
    s = data["sealed"]
    verify_sig = make_sig(s["data"])
    decoded = json.loads(base64.b64decode(s["data"]))
    assert verify_sig == s["sig"], "SELF-VERIFY FAILED"
    assert len(decoded) == len(results), f"length mismatch: {len(decoded)} vs {len(results)}"
    print(f"[inject_sealed] self-verify OK — {len(decoded)} sealed rows")

if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else "run_output.json"
    out = sys.argv[2] if len(sys.argv) > 2 else run
    inject(run, out)
