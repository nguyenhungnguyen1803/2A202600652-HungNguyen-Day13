import sys, dis
sys.path.append('observathon-score.exe_extracted/PYZ.pyz_extracted')
import observathon_score.engine as eng

with open('tmp/engine_score_run.txt', 'w', encoding='utf-8') as f:
    dis.dis(eng.score_run, file=f)
print("Disassembled score_run successfully!")
