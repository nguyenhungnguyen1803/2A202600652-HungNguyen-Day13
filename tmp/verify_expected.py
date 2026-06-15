import json, unicodedata, sys
sys.path.append('observathon-score.exe_extracted/PYZ.pyz_extracted')
import observathon_score.oracle as oracle

_CATALOG = {
    'iphone': {'in_stock': True, 'quantity': 12, 'unit_price_vnd': 22000000, 'weight_kg': 0.5},
    'macbook': {'in_stock': True, 'quantity': 4, 'unit_price_vnd': 35000000, 'weight_kg': 1.6},
    'airpods': {'in_stock': False, 'quantity': 0, 'unit_price_vnd': 4500000, 'weight_kg': 0.1},
    'ipad': {'in_stock': True, 'quantity': 7, 'unit_price_vnd': 18000000, 'weight_kg': 0.45}
}

_COUPONS = {'WINNER': 10, 'VIP20': 20, 'SALE15': 15, 'EXPIRED': 0}

_SHIP = {'ha noi': 30000, 'tp hcm': 25000, 'da nang': 35000, 'hai phong': 28000}

def _ascii(s):
    if not s:
        return ''
    s = s.strip().lower().replace('đ', 'd')
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def compute_expected(spec):
    item = spec.get('item')
    qty = spec.get('qty', 1)
    coupon = spec.get('coupon')
    dest = spec.get('dest')

    # check stock
    item_norm = _ascii(item)
    rec = _CATALOG.get(item_norm)
    if not rec:
        return {
            'status': 'item_not_found',
            'total_vnd': None,
            'answer_kind': 'refusal',
            'tools': ['check_stock']
        }
    
    if not rec['in_stock']:
        return {
            'status': 'out_of_stock',
            'total_vnd': None,
            'answer_kind': 'refusal',
            'tools': ['check_stock'],
            'unit_price_vnd': rec['unit_price_vnd']
        }
    
    # stock only check (no dest and no coupon)
    if not dest and not coupon:
        return {
            'status': 'ok',
            'total_vnd': None,
            'answer_kind': 'stock_only',
            'tools': ['check_stock'],
            'unit_price_vnd': rec['unit_price_vnd']
        }
        
    # discount
    pct = 0
    if coupon:
        pct = _COUPONS.get(coupon.upper(), 0)
    
    # shipping
    ship = 0
    tools = ['check_stock']
    if coupon:
        tools.append('get_discount')
        
    if dest:
        tools.append('calc_shipping')
        dest_norm = _ascii(dest)
        base = _SHIP.get(dest_norm)
        if base is None:
            return {
                'status': 'dest_not_served',
                'total_vnd': None,
                'answer_kind': 'refusal',
                'tools': tools
            }
        weight = rec['weight_kg']
        ship = int(base + max(0.0, weight * qty - 1.0) * 5000)
    
    subtotal = rec['unit_price_vnd'] * qty
    discounted = subtotal * (100 - pct) // 100
    total = discounted + ship
    
    return {
        'status': 'ok',
        'total_vnd': total,
        'answer_kind': 'purchase_total',
        'tools': tools,
        'discount_pct': pct,
        'ship_vnd': ship if dest else None,
        'unit_price_vnd': rec['unit_price_vnd']
    }

key = json.load(open('tmp/answerkey_raw.json', encoding='utf-8-sig'))

mismatches = 0
for qid, val in key.items():
    exp = compute_expected(val['spec'])
    ref = oracle.compute_expected(val['spec'])
    for k in ['status', 'total_vnd', 'answer_kind', 'tools', 'discount_pct', 'ship_vnd', 'unit_price_vnd']:
        if exp.get(k) != ref.get(k):
            print(f"Mismatch {qid} {k}: {exp.get(k)} != {ref.get(k)}")
            mismatches += 1

print(f"Verification finished. Total mismatches: {mismatches}")
