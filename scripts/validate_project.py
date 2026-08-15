#!/usr/bin/env python3
import json, pathlib, py_compile, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
errs=[]
for p in ROOT.rglob('*.json'):
    try: json.load(open(p,encoding='utf-8'))
    except Exception as e: errs.append(f'json {p}: {e}')
for p in list((ROOT/'scripts').glob('*.py')) + list((ROOT/'bot').glob('*.py')):
    try: py_compile.compile(str(p),doraise=True)
    except Exception as e: errs.append(f'python {p}: {e}')
r=subprocess.run(['bash','-n',str(ROOT/'docker/start.sh')],capture_output=True,text=True)
if r.returncode: errs.append('bash: '+r.stderr)
# Verify generated workflows have expected core nodes and source mode.
for name in ['GoonMachine_T2I2V_5090_LUSTIFY_SAFE.json','GoonMachine_T2I2V_5090_FALLBACK_SAFE.json','GoonMachine_I2V_5090_SAFE.json','GoonMachine_T2I_5090_LUSTIFY_SAFE.json','GoonMachine_T2I_5090_FALLBACK_SAFE.json']:
    p=ROOT/'workflows'/name; d=json.load(open(p,encoding='utf-8')); ids={n.get('id'):n for n in d['nodes']}
    for nid in (118,68,3031,3103,3106,2899):
        if nid not in ids: errs.append(f'{name}: missing node {nid}')
    if 'SAFE' in name and (ids[68].get('mode')!=4 or ids[3031].get('mode')!=4): errs.append(f'{name}: safe optional nodes not bypassed')
    if name.startswith('GoonMachine_I2V') and ids[3104]['widgets_values'][0]!=0: errs.append(f'{name}: input skip should be zero')

# Telegram API automation requires the workflow->API converter custom node.
nodes=json.load(open(ROOT/'config/nodes.json',encoding='utf-8'))
if not any(n.get('name')=='comfyui-workflow-to-api-converter-endpoint' for n in nodes):
    errs.append('config/nodes.json: workflow-to-api converter is missing')

if errs:
    print('\n'.join(errs),file=sys.stderr); raise SystemExit(2)
print('Project static validation: OK')
