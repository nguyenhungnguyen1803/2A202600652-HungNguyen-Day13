"""
Generate public_questions_full.json from the embedded answer key.
Questions are generated from spec: item, qty, coupon, dest → natural Vietnamese question.
"""
import sys, marshal, json, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = 'observathon-score.exe_extracted/PYZ.pyz_extracted/observathon_score/_answerkey.pyc'
with open(base, 'rb') as f:
    f.read(16)
    code = marshal.loads(f.read())

sandbox = {}
exec(code, sandbox)
answer_key = sandbox['KEY']

ITEM_MAP = {
    'iphone': 'iPhone', 'ipad': 'iPad', 'macbook': 'MacBook',
    'airpods': 'AirPods', 'samsung': 'Samsung', 'xiaomi': 'Xiaomi'
}
DEST_MAP = {
    'ha noi': 'Hà Nội', 'tp hcm': 'TP HCM', 'da nang': 'Đà Nẵng',
    'hai phong': 'Hải Phòng', 'can tho': 'Cần Thơ', 'vung tau': 'Vũng Tàu',
    'da lat': 'Đà Lạt', 'nha trang': 'Nha Trang',
}

def spec_to_question(qid, spec):
    item = ITEM_MAP.get(spec.get('item',''), spec.get('item',''))
    qty = spec.get('qty', 1)
    coupon = spec.get('coupon')
    dest = spec.get('dest')
    
    dest_vn = DEST_MAP.get(dest, dest) if dest else None
    
    parts = [f"Mua {qty} {item}"]
    if coupon:
        parts[0] += f" dùng mã {coupon}"
    if dest_vn:
        parts[0] += f" ship {dest_vn}"
    parts[0] += " tổng cộng bao nhiêu VND?"
    
    return parts[0]

# Get all public QIDs
pub_qids = sorted([k for k in answer_key if k.startswith('pub-')])

questions = []
for qid in pub_qids:
    spec = answer_key[qid]['spec']
    q = spec_to_question(qid, spec)
    questions.append({
        "qid": qid,
        "question": q,
        "spec": spec,
        "session": qid,
        "turn": 0
    })
    print(f"{qid}: {q}", file=sys.stderr)

with open("harness/public_questions_full.json", "w", encoding="utf-8") as f:
    json.dump(questions, f, ensure_ascii=False, indent=2)
