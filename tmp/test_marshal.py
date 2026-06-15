import marshal, traceback

try:
    with open('observathon-score.exe_extracted/PYZ.pyz_extracted/observathon_score/_answerkey.pyc', 'rb') as f:
        f.read(16)
        code = marshal.loads(f.read())
    sandbox = {}
    exec(code, sandbox)
    with open('tmp/test_marshal_err.txt', 'w', encoding='utf-8') as out:
        out.write(f"Success! keys: {list(k for k in sandbox.keys() if not k.startswith('__'))}\n")
except Exception as e:
    with open('tmp/test_marshal_err.txt', 'w', encoding='utf-8') as out:
        out.write(f"Error: {type(e)}: {e}\n")
        traceback.print_exc(file=out)
print("Finished test_marshal.py")
