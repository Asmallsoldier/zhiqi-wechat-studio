"""Audit Git-tracked source and export a deterministic public source ZIP.

Not a proof of absence of secrets. Never scans or copies ignored runtime files.
No network, remote push, database access or production configuration reads.
"""
import argparse,hashlib,json,re,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOP={'README.md','LICENSE','NOTICE','AGENTS.md','CONTRIBUTING.md','SECURITY.md','CHANGELOG.md','.gitignore','.env.example','compose.yaml'}
DIRS={'backend','web','docs','scripts','.github'}
PATTERNS=[
 re.compile(r'-----BEGIN '+r'(?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 re.compile(r'\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{25,}\b'),
 re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),
 re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
 re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
 re.compile(r'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'),
]

def files():
 raw=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT)
 return sorted(p for p in raw.decode().split('\0') if p)

def audit(paths):
 problems=[]
 for name in paths:
  path=Path(name);parts=path.parts;file=ROOT/path
  if not parts or (len(parts)==1 and name not in TOP) or (len(parts)>1 and parts[0] not in DIRS):problems.append((name,'outside-public-allowlist'));continue
  if any(p in {'node_modules','.git','runtime','artifacts','data','dist','__pycache__','.venv'} for p in parts) or path.suffix in {'.db','.key','.pem','.log','.zip','.bak'} or (path.name.startswith('.env') and name not in {'.env.example','web/.env.wechat'}):problems.append((name,'runtime-or-private-file'));continue
  if file.is_symlink() or not file.is_file():problems.append((name,'symlink-or-missing'));continue
  content=file.read_bytes()
  if len(content)>3_000_000:problems.append((name,'unexpected-large-file'));continue
  try:value=content.decode('utf8')
  except UnicodeDecodeError:problems.append((name,'binary-not-approved'));continue
  for pattern in PATTERNS:
   if pattern.search(value):problems.append((name,'sensitive-pattern'));break
 for required in ('LICENSE','README.md','.env.example','compose.yaml','SECURITY.md','docs/product.md'):
  if required not in paths:problems.append((required,'required-source-missing'))
 if problems:
  # Never print matched text or secret values.
  for name,reason in problems:print(name+': '+reason)
  raise SystemExit('Public source audit failed')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');parser.add_argument('--output',default='artifacts/wechat-studio-0.3.0-source.zip');args=parser.parse_args()
 paths=files();audit(paths)
 if args.check:print(f'Public source audit passed: {len(paths)} tracked files');return
 output=(ROOT/args.output).resolve()
 if ROOT/'artifacts' not in output.parents:raise SystemExit('Export must stay in artifacts/')
 output.parent.mkdir(exist_ok=True,parents=True)
 manifest={'version':'0.3.0','files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
  for name,content in [(n,(ROOT/n).read_bytes()) for n in paths]+[('SOURCE-MANIFEST.json',json.dumps(manifest,indent=2).encode())]:
   info=zipfile.ZipInfo('wechat-studio/'+name,date_time=(2026,1,1,0,0,0));info.external_attr=0o100644<<16;info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,content)
 digest=hashlib.sha256(output.read_bytes()).hexdigest()
 output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n')
 print('Exported '+str(output.relative_to(ROOT))+f' ({len(paths)} source files)')
if __name__=='__main__':main()
