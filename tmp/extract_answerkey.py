"""
Reconstruct the embedded answer key from _answerkey.pyc
and generate a proper public_questions.json with the correct QID format.
"""
import sys, marshal, json, io, dis, os

# Redirect stdout to utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = r'observathon-score.exe_extracted\PYZ.pyz_extracted\observathon_score\_answerkey.pyc'
with open(base, 'rb') as f:
    f.read(16)
    code = marshal.loads(f.read())

# Execute the module code in a sandbox to get the ANSWER_KEY dict
sandbox = {}
exec(code, sandbox)

# Find the ANSWER_KEY or similar
answer_key = None
for k, v in sandbox.items():
    if isinstance(v, dict) and any(str(kk).startswith('pub-') for kk in v.keys()):
        answer_key = v
        print(f"Found answer key: {k} with {len(v)} entries", file=sys.stderr)
        break

if answer_key is None:
    # Try to find it differently - it might be a function
    for k, v in sandbox.items():
        if callable(v) and k not in ('__builtins__',):
            try:
                result = v()
                if isinstance(result, dict):
                    answer_key = result
                    print(f"Found via function call: {k}", file=sys.stderr)
                    break
            except:
                pass

if answer_key:
    print(json.dumps(answer_key, ensure_ascii=False, indent=2))
else:
    print("No answer key found. Sandbox keys:", list(sandbox.keys()), file=sys.stderr)
    # Print co_consts
    print("co_consts:", code.co_consts, file=sys.stderr)
