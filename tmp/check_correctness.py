import json, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load answer key
with open("tmp/answerkey_raw.json", encoding="utf-8-sig") as f:
    key = json.load(f)

# Load our run output
with open("run_output.json", encoding="utf-8") as f:
    run = json.load(f)

results = run.get("results", [])

# Regex to find total VND in our answers
VND_RE = re.compile(r'(?i)tong\s+cong:\s*(\d+)\s*vnd')

mismatches = 0
refusal_errors = 0
calculation_errors = 0
correct = 0

for r in results:
    qid = r["qid"]
    question = r["question"]
    answer = r.get("answer", "")
    
    # Get expected
    expected_spec = key[qid]["spec"]
    
    # Check if we refused
    # Refusal criteria in scorer: contains "wrapper_error" status or does not find a total
    match_vnd = VND_RE.search(answer)
    our_total = int(match_vnd.group(1)) if match_vnd else None
    
    # Let's inspect the tools trace to calculate the expected values
    trace = r.get("trace", [])
    
    # Get tool outputs from trace
    stock_info = None
    discount_pct = 0
    shipping_cost = 0
    shipping_error = False
    
    for step in trace:
        tool = step.get("tool")
        obs = step.get("observation", {})
        if tool == "check_stock":
            stock_info = obs
        elif tool == "get_discount":
            if obs.get("valid"):
                discount_pct = obs.get("percent", 0)
        elif tool == "calc_shipping":
            if obs.get("error"):
                shipping_error = True
            else:
                shipping_cost = obs.get("cost_vnd", 0)
                if shipping_cost is None:
                    shipping_cost = 0

    # Scorer logic for expected refusal
    should_refuse = False
    refusal_reason = ""
    
    if not stock_info or not stock_info.get("found"):
        should_refuse = True
        refusal_reason = "Product not found"
    elif not stock_info.get("in_stock") or stock_info.get("quantity", 0) < expected_spec.get("qty", 1):
        should_refuse = True
        refusal_reason = f"Out of stock (quantity {stock_info.get('quantity', 0)} < {expected_spec.get('qty', 1)})"
    elif expected_spec.get("dest") and (shipping_error or shipping_cost == 0 and expected_spec.get("dest") not in ("ha noi", "tp hcm", "da nang", "hai phong", "can tho", "vung tau", "da lat", "nha trang")):
        # Note: if destination is provided but calc_shipping fails, it should refuse
        should_refuse = True
        refusal_reason = "Shipping not served"

    # Compute expected total
    expected_total = None
    if not should_refuse:
        subtotal = stock_info.get("unit_price_vnd", 0) * expected_spec.get("qty", 1)
        discount = subtotal * discount_pct // 100
        discounted = subtotal - discount
        expected_total = discounted + shipping_cost

    # Compare
    is_correct = False
    if should_refuse:
        if our_total is None:
            is_correct = True
            correct += 1
        else:
            refusal_errors += 1
            mismatches += 1
            print(f"[{qid}] SHOULD REFUSE ({refusal_reason}) but we calculated total {our_total:,} VND.")
            print(f"   Q: {question}")
            print(f"   A: {answer.replace(chr(10), ' | ')[:150]}")
    else:
        if our_total == expected_total:
            is_correct = True
            correct += 1
        else:
            calculation_errors += 1
            mismatches += 1
            print(f"[{qid}] EXPECTED {expected_total:,} VND but we got {our_total} VND.")
            print(f"   Q: {question}")
            print(f"   A: {answer.replace(chr(10), ' | ')[:150]}")
            print(f"   Specs: stock_price={stock_info.get('unit_price_vnd')}, qty={expected_spec.get('qty')}, discount={discount_pct}%, shipping={shipping_cost}")

print(f"\nSummary: Correct={correct}, Mismatches={mismatches} (Refusal Errors={refusal_errors}, Calculation Errors={calculation_errors})")
