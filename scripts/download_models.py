#!/usr/bin/env python3
import json, os, pathlib, shutil, sys, time
import requests
from huggingface_hub import hf_hub_download

ROOT=pathlib.Path(os.environ.get('MODEL_ROOT','/workspace/models'))
CACHE=pathlib.Path(os.environ.get('HF_HOME','/workspace/.cache/huggingface'))
REPORT=pathlib.Path('/workspace/download-report.json')
MANIFEST=pathlib.Path(os.environ.get('MODEL_MANIFEST','/opt/ltx-suite/config/models.json'))
HF_TOKEN=os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN') or None
CIVITAI_TOKEN=os.environ.get('CIVITAI_TOKEN') or None

report={'started':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'downloads':{},'warnings':[]}

def say(s): print('[models]',s,flush=True)

def ensure_link(src:pathlib.Path, dst:pathlib.Path):
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() or dst.is_symlink():
        try:
            if dst.resolve()==src.resolve(): return
        except Exception: pass
        if dst.is_dir() and not dst.is_symlink(): shutil.rmtree(dst)
        else: dst.unlink()
    try:
        os.symlink(src,dst)
    except OSError:
        try: os.link(src,dst)
        except OSError: shutil.copy2(src,dst)

def hf(item):
    dst=ROOT/item['target']
    if dst.exists() and dst.stat().st_size>1024*1024:
        say(f"skip {item['id']}: {dst}")
        return dst
    say(f"download {item['id']}: {item['repo']} :: {item['file']}")
    src=pathlib.Path(hf_hub_download(repo_id=item['repo'],filename=item['file'],cache_dir=str(CACHE),token=HF_TOKEN))
    ensure_link(src,dst)
    for alias in item.get('aliases',[]): ensure_link(src,ROOT/alias)
    return dst

def civitai_download(url, dst):
    dst=pathlib.Path(dst); dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists() and dst.stat().st_size>1024*1024: return dst
    headers={'User-Agent':'ltx23-goon-vast/1.0'}
    params={}
    if CIVITAI_TOKEN: params['token']=CIVITAI_TOKEN
    with requests.get(url,headers=headers,params=params,stream=True,timeout=(20,120),allow_redirects=True) as r:
        r.raise_for_status()
        tmp=dst.with_suffix(dst.suffix+'.part')
        total=int(r.headers.get('content-length') or 0); got=0; tick=0
        with open(tmp,'wb') as f:
            for chunk in r.iter_content(8*1024*1024):
                if chunk:
                    f.write(chunk); got+=len(chunk)
                    if total and got-tick>256*1024*1024:
                        say(f"  {dst.name}: {got/1024**3:.1f}/{total/1024**3:.1f} GiB")
                        tick=got
        tmp.replace(dst)
    return dst

def get_json(url):
    headers={'User-Agent':'ltx23-goon-vast/1.0'}
    if CIVITAI_TOKEN: headers['Authorization']=f'Bearer {CIVITAI_TOKEN}'
    r=requests.get(url,headers=headers,timeout=30); r.raise_for_status(); return r.json()

def try_lustify():
    if os.environ.get('DOWNLOAD_LUSTIFY_V10','1') in ('0','false','False'): return None
    target=ROOT/'diffusion_models/krea2/lustify-v10-krea-turbo-fp16.safetensors'
    try:
        data=get_json('https://civitai.com/api/v1/models/573152')
        versions=data.get('modelVersions') or []
        def score(v):
            n=(v.get('name') or '').lower(); b=(v.get('baseModel') or '').lower()
            return (10 if 'v10' in n else 0)+(8 if 'krea' in n or 'krea' in b else 0)+(2 if 'turbo' in n else 0)
        for v in sorted(versions,key=score,reverse=True):
            if score(v)<8: continue
            files=[x for x in (v.get('files') or []) if str(x.get('name','')).lower().endswith('.safetensors')]
            if not files: continue
            model_files=[x for x in files if str(x.get('type','')).lower() in ('model','checkpoint')]
            pool=model_files or files
            f=next((x for x in pool if x.get('primary')),pool[0])
            url=f.get('downloadUrl') or f"https://civitai.com/api/download/models/{v.get('id')}"
            say(f"trying Lustify V10/Krea2 from Civitai version {v.get('id')} ({v.get('name')})")
            civitai_download(url,target)
            report['downloads']['lustify_v10']={'status':'ok','source':'civitai','version_id':v.get('id'),'target':str(target)}
            return target
        raise RuntimeError('No Krea2/V10 version returned by Civitai API')
    except Exception as e:
        w=f'Lustify V10 exact checkpoint unavailable: {e}. Public Krea fallback workflow remains available.'
        say('WARNING: '+w); report['warnings'].append(w); report['downloads']['lustify_v10']={'status':'missing','error':str(e)}
        return None

def try_10eros_lora():
    target=ROOT/'loras/LTX/ltx2310eros_v14.safetensors'
    try:
        data=get_json('https://civitai.com/api/v1/model-versions/3109610')
        cand=[]
        for f in data.get('files') or []:
            name=(f.get('name') or '')
            size=float(f.get('sizeKB') or 0)
            if name.lower()=='ltx2310eros_v14.safetensors' and (not size or size < 6_000_000): cand.append((size,f))
        if not cand: raise RuntimeError('LoRA file not found in modelVersion 3109610')
        f=sorted(cand,key=lambda x:x[0] or 10**12)[0][1]
        url=f.get('downloadUrl') or 'https://civitai.com/api/download/models/3109610'
        say('download exact 10Eros LoRA from Civitai')
        civitai_download(url,target)
        report['downloads']['10eros_lora']={'status':'ok','source':'civitai','target':str(target)}
        return target
    except Exception as e:
        w=f'Exact 10Eros LoRA could not be downloaded: {e}. It will be disabled in the generated Goon workflows.'
        say('WARNING: '+w); report['warnings'].append(w); report['downloads']['10eros_lora']={'status':'missing','error':str(e)}
        return None


def try_ultimate_lora():
    """Download the exact optional UltimateDT LoRA only when a direct URL is supplied.

    We intentionally do not substitute similarly named merged checkpoints because the
    supplied workflow loads this asset through a LoRA loader stack.
    """
    target=ROOT/'loras/LTX/ltx23-ultimatedt-NSFW-sulphured_audio_final_k3nk.safetensors'
    if target.exists() and target.stat().st_size>1024*1024:
        report['downloads']['ultimate_dt_lora']={'status':'ok','source':'existing','target':str(target)}
        return target
    url=os.environ.get('ULTIMATE_DT_URL','').strip()
    if not url:
        report['downloads']['ultimate_dt_lora']={'status':'disabled','reason':'ULTIMATE_DT_URL not supplied'}
        return None
    try:
        say('download exact optional UltimateDT LoRA from supplied URL')
        civitai_download(url,target)
        report['downloads']['ultimate_dt_lora']={'status':'ok','source':'custom_url','target':str(target)}
        return target
    except Exception as e:
        w=f'Exact UltimateDT LoRA could not be downloaded: {e}. It will remain disabled in generated Goon workflows.'
        say('WARNING: '+w); report['warnings'].append(w); report['downloads']['ultimate_dt_lora']={'status':'missing','error':str(e)}
        return None

def official_workflow():
    target=pathlib.Path('/workspace/workflows-source/10Eros_10SNodes_I2V_Basic_DMD_V5.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    try:
        src=pathlib.Path(hf_hub_download(repo_id='TenStrip/LTX2.3-10Eros_Workflows',filename='10Eros_10SNodes_I2V_Basic_DMD_V5.json',repo_type='model',cache_dir=str(CACHE),token=HF_TOKEN))
        shutil.copy2(src,target)
        report['downloads']['10eros_workflow']={'status':'ok','target':str(target)}
        return target
    except Exception as e:
        report['downloads']['10eros_workflow']={'status':'missing','error':str(e)}
        raise

def main():
    ROOT.mkdir(parents=True,exist_ok=True); CACHE.mkdir(parents=True,exist_ok=True)
    items=json.load(open(MANIFEST,encoding='utf-8'))
    hard=[]
    for item in items:
        try:
            p=hf(item); report['downloads'][item['id']]={'status':'ok','target':str(p),'provider':'hf'}
        except Exception as e:
            say(f"ERROR {item['id']}: {e}")
            report['downloads'][item['id']]={'status':'error','error':str(e)}
            if item.get('required',True): hard.append(item['id'])
            else: report['warnings'].append(f"Optional model {item['id']} failed: {e}")
    try_lustify(); try_10eros_lora(); try_ultimate_lora()
    try:
        official_workflow()
    except Exception as e:
        hard.append('10eros_workflow'); say(f'ERROR official workflow: {e}')
    report['finished']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    say(f'report: {REPORT}')
    if hard:
        say('Required downloads failed: '+', '.join(hard)); raise SystemExit(2)

if __name__=='__main__': main()
