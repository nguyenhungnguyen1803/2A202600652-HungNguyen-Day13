import sys, dis
sys.path.append('observathon-score.exe_extracted/PYZ.pyz_extracted')
import observathon_score.oracle as oracle

with open('tmp/oracle_dis.txt', 'w', encoding='utf-8') as f:
    dis.dis(oracle, file=f)
print("Disassembled oracle successfully!")
