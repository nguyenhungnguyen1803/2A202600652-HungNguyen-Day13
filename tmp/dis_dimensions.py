import sys, dis
sys.path.append('observathon-score.exe_extracted/PYZ.pyz_extracted')
import observathon_score.dimensions as dim

with open('tmp/dimensions_dis.txt', 'w', encoding='utf-8') as f:
    dis.dis(dim, file=f)
print("Disassembled dimensions successfully!")
