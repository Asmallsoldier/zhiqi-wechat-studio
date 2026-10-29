"""Run inside the API container: python /tmp/backup.py /data/studio.db /data/backups/name.db"""
import os,sqlite3,sys
from pathlib import Path
source,target=sys.argv[1:]
p=Path(target)
if p.exists():raise SystemExit('Refusing to overwrite an existing backup')
p.parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:
    src.backup(dst)
    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Integrity check failed')
os.chmod(target,0o600)
print('Backup completed and integrity checked.')
