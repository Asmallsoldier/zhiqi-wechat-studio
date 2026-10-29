"""Refresh license/version inventory from installed Python and npm lock metadata.

Run with backend's development venv after installing requirements. No network.
The output includes dependency metadata, never environment values or paths.
"""
import json
from datetime import date
from pathlib import Path
from importlib.metadata import distribution
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root=Path(__file__).resolve().parents[1]
requirements=[Requirement(line) for line in (root/'backend/requirements.txt').read_text().splitlines() if line and not line.startswith('#')]
queue=[r.name for r in requirements];python={}
while queue:
 name=canonicalize_name(queue.pop())
 if name in python:continue
 dist=distribution(name);meta=dist.metadata
 license=meta.get('License-Expression')
 if not license:
  license='; '.join(c for c in meta.get_all('Classifier',[]) if c.startswith('License ::')) or (meta.get('License','')[:200] or 'See upstream package license')
 python[name]={'name':meta['Name'],'version':dist.version,'license':license}
 for text in dist.requires or []:
  dep=Requirement(text)
  if dep.marker is None or dep.marker.evaluate({'extra':''}):queue.append(dep.name)
lock=json.loads((root/'web/package-lock.json').read_text());web=[]
for path,meta in sorted(lock['packages'].items()):
 if not path:continue
 web.append({'name':path.rsplit('node_modules/',1)[-1],'version':meta.get('version'),'license':meta.get('license','See upstream package license'),'dev':meta.get('dev',False),'optional':meta.get('optional',False)})
(root/'docs/dependencies.json').write_text(json.dumps({'generatedAt':date.today().isoformat(),'python':sorted(python.values(),key=lambda x:x['name'].lower()),'web':web,'note':'Dependency metadata inventory, not a legal rights audit. Full upstream license notices remain with installed packages.'},ensure_ascii=False,indent=2)+'\n')
(root/'backend/requirements.lock').write_text('# Resolved for Python 3.12; refresh with scripts/dependency-inventory.py after dependency review.\n'+'\n'.join(name+'=='+python[name]['version'] for name in sorted(python))+'\n')
print('Dependency metadata and Python lock refreshed')
