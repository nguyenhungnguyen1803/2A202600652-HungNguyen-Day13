"""YOUR mitigation + observability layer. The simulator calls mitigate() around the
opaque agent (a REAL LLM) for every request. This is the ONLY place observability can
live -- the agent is silent. Legal moves: retry / cache / route / guardrail / sanitize
/ fallback / session-reset / PROMPT ROUTING, plus your own logging/tracing/metrics.
Illegal: hardcoding answers, importing the agent internals, reading instructor files,
network exfiltration.

  call_next(question, config) -> result   # the only way to reach the black box
  context = {"session_id","turn_index","qid","cache": <shared dict>, "cache_lock": <Lock>}
  result  = {"answer","status","steps","trace","meta":{latency_ms,usage,...}}
"""
from __future__ import annotations
import time
import re
import threading

from telemetry.logger import logger
from telemetry.cost import cost_from_usage
from telemetry.redact import redact, redact_value


def sanitize_question(q: str) -> str:
    """Sanitize and standardize the question for the nano model.
    Extracts structured fields and removes PII and malicious instructions.
    """
    if not isinstance(q, str):
        return q

    q_lower = q.lower()

    # 1. Extract product
    product = None
    for prod in ["iphone", "ipad", "macbook", "airpods", "samsung", "xiaomi"]:
        if prod in q_lower:
            product = prod
            break

    # 2. Extract quantity (default 1)
    qty = 1
    match_qty = re.search(
        r'(\d+)\s*(iphone|ipad|macbook|airpods|samsung|xiaomi|cái|chiếc|sp|sản phẩm|cai|chiec)',
        q_lower
    )
    if match_qty:
        qty = int(match_qty.group(1))
    else:
        # Check any standalone number before the product name
        match_num = re.search(r'\b(\d+)\b', q_lower)
        if match_num:
            qty = int(match_num.group(1))

    # 3. Extract coupon code
    coupon = None
    match_coupon = re.search(r'(?i)(mã|ma|coupon|code|giftcode)\s*([a-z0-9]+)', q)
    if match_coupon:
        coupon = match_coupon.group(2)
        # Avoid matching product name or cities as coupon
        if coupon.lower() in [
            "iphone", "ipad", "macbook", "airpods", "samsung", "xiaomi",
            "giao", "ship", "hải", "hai", "nội", "noi", "hcm", "hồ", "ho", "chí", "chi"
        ]:
            coupon = None

    # 4. Extract destination
    destination = None
    match_dest = re.search(r'(?i)(giao|ship|đến|den|tại|tai)\s+([A-ZÀ-ỹa-z0-9\s]+)', q)
    if match_dest:
        dest_candidate = match_dest.group(2).strip()
        dest_candidate_lower = dest_candidate.lower()
        for city in [
            "hà nội", "ha noi", "hồ chí minh", "ho chi minh", "tphcm", "tp hcm", "hcm",
            "đà nẵng", "da nang", "hải phòng", "hai phong", "đà lạt", "da lat", "nha trang"
        ]:
            if city in dest_candidate_lower:
                destination = city
                break
        if not destination:
            # Fallback: take first 2 words
            words = dest_candidate.split()
            if words:
                destination = " ".join(words[:2])

    # Reconstruct standard structured question
    parts = []
    if product:
        prod_map = {
            "iphone": "iPhone", "ipad": "iPad", "macbook": "MacBook",
            "airpods": "AirPods", "samsung": "Samsung", "xiaomi": "Xiaomi"
        }
        parts.append(f"Sản phẩm: {prod_map[product.lower()]}")
    else:
        parts.append("Sản phẩm: Không có")

    parts.append(f"Số lượng: {qty}")

    if coupon:
        parts.append(f"Mã giảm giá: {coupon.upper()}")
    else:
        parts.append("Mã giảm giá: Không có")

    if destination:
        dest_map = {
            "hà nội": "Hà Nội", "ha noi": "Hà Nội",
            "hồ chí minh": "Hồ Chí Minh", "ho chi minh": "Hồ Chí Minh", "tphcm": "Hồ Chí Minh", "tp hcm": "Hồ Chí Minh", "hcm": "Hồ Chí Minh",
            "đà nẵng": "Đà Nẵng", "da nang": "Đà Nẵng",
            "hải phòng": "Hải Phong", "hai phong": "Hải Phong",
            "đà lạt": "Đà Lạt", "da lat": "Đà Lạt"
        }
        std_dest = dest_map.get(destination.lower(), destination)
        parts.append(f"Nơi nhận: {std_dest}")
    else:
        parts.append("Nơi nhận: Không có")

    # Strip any malicious instructions from the notes/comments
    match_note = re.search(r'(?i)(ghi chú|ghi chu|note|g chú|g chu|gchu)[\s:]*(.*)', q)
    if match_note:
        note_content = match_note.group(2)
        sanitized_note = re.sub(
            r'(?i)(hãy|hay|tính|tinh|giá|gia|lấy|lay|đổi|doi|sửa|sua|cập nhật|cap nhat|set|override|force|change|update|must|price|vnd|đồng|đ)',
            '',
            note_content
        )
        parts.append(f"Ghi chú khách hàng: {sanitized_note.strip()}")

    structured_q = ". ".join(parts) + "."
    return structured_q


def mitigate(call_next, question, config, context):
    t0 = time.time()

    # 1. Sanitize input to mitigate prompt injection and standardize extraction
    sanitized_q = sanitize_question(question)

    # 2. Thread-safe cache check
    cache = context.get("cache")
    cache_lock = context.get("cache_lock")
    qid = context.get("qid", "unknown")

    if cache is not None and cache_lock is not None:
        with cache_lock:
            if sanitized_q in cache:
                cached_res = cache[sanitized_q]
                if logger:
                    logger.log_event("CACHE_HIT", {
                        "qid": qid,
                        "question": question,
                        "cached_answer": cached_res.get("answer"),
                    })
                return cached_res

    # 3. Call the agent with retry on error
    max_retries = 2
    attempt = 0
    res = None
    conf = dict(config)

    while attempt <= max_retries:
        try:
            res = call_next(sanitized_q, conf)
            status = res.get("status", "ok")
            # If the status indicates a loop or error, retry
            if status in ("loop", "max_steps", "wrapper_error") and attempt < max_retries:
                attempt += 1
                time.sleep(0.1 * attempt)
                continue
            break
        except Exception as e:
            if attempt < max_retries:
                attempt += 1
                time.sleep(0.2 * attempt)
                continue
            # If all retries failed, return wrapper_error
            res = {
                "answer": "Xin lỗi, hệ thống đang bận. Vui lòng thử lại sau.",
                "status": "wrapper_error",
                "steps": 0,
                "trace": [],
                "meta": {
                    "latency_ms": int((time.time() - t0) * 1000),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "model": config.get("model", ""),
                    "provider": config.get("provider", ""),
                    "tools_used": []
                }
            }
            break

    # 4. Post-process answer to redact PII (email, phone, CCCD, etc.) just in case
    if res and isinstance(res.get("answer"), str):
        original_answer = res["answer"]
        redacted_answer, num_redactions = redact(original_answer)
        if num_redactions > 0:
            res["answer"] = redacted_answer
            if logger:
                logger.log_event("PII_REDACTED", {
                    "qid": qid,
                    "num_redactions": num_redactions
                })

    # 5. Populate cache thread-safely
    if cache is not None and cache_lock is not None and res and res.get("status") == "ok":
        with cache_lock:
            cache[sanitized_q] = res

    # 6. Observability logging
    wall_ms = int((time.time() - t0) * 1000)
    meta = res.get("meta", {}) if res else {}
    usage = meta.get("usage", {}) if meta else {}

    if logger:
        logger.log_event("AGENT_CALL", {
            "qid": qid,
            "status": res.get("status") if res else "error",
            "reported_latency_ms": meta.get("latency_ms") if meta else 0,
            "wall_ms": wall_ms,
            "tokens": usage,
            "cost_usd": cost_from_usage(meta.get("model", ""), usage) if meta else 0.0,
            "tools_used": meta.get("tools_used", []) if meta else [],
            "steps": res.get("steps") if res else 0,
        })

    return res
