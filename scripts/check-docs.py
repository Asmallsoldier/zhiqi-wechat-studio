from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
missing=[]
for doc in [root/'README.md',*sorted((root/'docs').glob('*.md'))]:
 for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)',doc.read_text()):
  if '://' not in target and not (doc.parent/target).exists():missing.append((str(doc.relative_to(root)),target))
if missing:raise SystemExit(str(missing))
print('All local documentation links resolve.')
