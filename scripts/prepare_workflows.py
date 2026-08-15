#!/usr/bin/env python3
import argparse, copy, json, os, pathlib, re, shutil

PROJECT=pathlib.Path(os.environ.get('PROJECT_DIR','/opt/ltx-suite'))
ORIGINAL=PROJECT/'workflows/GoonMachine_original_v08.json'
OUT=pathlib.Path(os.environ.get('WORKFLOW_OUT','/workspace/user/default/workflows'))
REPORT=pathlib.Path('/workspace/download-report.json')
MODELS=pathlib.Path('/workspace/models')

MODEL_EXT=('.safetensors','.pth','.pt','.pkl','.gguf','.cube')

def norm_value(x):
    if isinstance(x,str):
        if x.startswith('C:\\ComfyUI\\output'):
            return x.replace('C:\\ComfyUI\\output','/workspace/output').replace('\\','/')
        if '\\' in x and any(e in x.lower() for e in MODEL_EXT): return x.replace('\\','/')
        return x
    if isinstance(x,list): return [norm_value(v) for v in x]
    if isinstance(x,dict): return {k:norm_value(v) for k,v in x.items()}
    return x

def node_by_id(d,nid):
    for n in d.get('nodes',[]):
        if n.get('id')==nid:return n
    raise KeyError(nid)

def disable_lora_by_name(d, needle):
    needle=needle.lower()
    for n in d.get('nodes',[]):
        vals=n.get('widgets_values')
        if not isinstance(vals,list):
            continue
        if n.get('type')=='Power Lora Loader (rgthree)':
            for v in vals:
                if isinstance(v,dict) and needle in str(v.get('lora','')).lower():
                    v['on']=False
        elif n.get('type')=='Lora Loader Stack (rgthree)':
            # Deprecated rgthree stack serializes lora_name,strength pairs. rgthree's
            # implementation skips a LoRA when its strength is exactly 0.
            for i,v in enumerate(vals[:-1]):
                if isinstance(v,str) and needle in v.lower() and isinstance(vals[i+1],(int,float)):
                    vals[i+1]=0

def patch_goon(base, source='t2i', krea='lustify', safe=True, ten_lora=True, ultimate_lora=False):
    d=copy.deepcopy(base)
    d=norm_value(d)
    # Vast/Linux paths.
    n=node_by_id(d,3103)
    if isinstance(n.get('widgets_values'),dict):
        n['widgets_values']['directory']='/workspace/input'
        vp=n['widgets_values'].get('videopreview')
        if isinstance(vp,dict) and isinstance(vp.get('params'),dict):
            vp['params']['filename']='/workspace/input'
    # Generate first image or use an image dropped into ComfyUI input folder.
    combo=node_by_id(d,3106)
    if source=='t2i': combo['widgets_values'][0]='Generate with Krea2'; combo['widgets_values'][1]=0
    else:
        combo['widgets_values'][0]='Use input folder'; combo['widgets_values'][1]=1
        node_by_id(d,3104)['widgets_values'][0]=0
    unet=node_by_id(d,118)
    unet['widgets_values'][0]=('krea2/lustify-v10-krea-turbo-fp16.safetensors' if krea=='lustify' else 'krea2/krea2TurboUncensored_v1.safetensors')
    # The exact UltimateDT LoRA from the source workflow is not mirrored reliably.
    # Do not substitute a similarly named merged checkpoint as a LoRA: disable it unless
    # the exact file has been provided/downloaded. The remaining LTX LoRAs stay active.
    if not ultimate_lora:
        disable_lora_by_name(d,'ltx23-ultimatedt-NSFW-sulphured_audio_final_k3nk.safetensors')
    if not ten_lora:
        disable_lora_by_name(d,'ltx2310eros_v14.safetensors')
    if safe:
        # Blackwell-safe defaults: let native attention run and bypass optional RTX VSR.
        node_by_id(d,68)['mode']=4
        node_by_id(d,3031)['mode']=4
    return d


def patch_image_only(d):
    # Keep the Krea image generation/output branch but disable the LTX/video output branches.
    # ComfyUI executes dependencies of enabled output nodes, so muting video outputs prevents
    # a text-only Telegram request from wasting time rendering a video.
    for nid in (2922, 2923, 3018, 3007, 3042):
        try:
            node_by_id(d,nid)['mode']=4
        except KeyError:
            pass
    return d

def patch_10eros(obj):
    def rec(x):
        if isinstance(x,str):
            s=x.replace('\\','/') if any(e in x.lower() for e in MODEL_EXT) else x
            low=s.lower()
            if low.endswith('.safetensors') and '10eros' in low and 'lora' not in low:
                return '10Eros_v1.4_fp8mixed_learned.safetensors'
            if low.endswith('.safetensors') and 'dmd' in low:
                return 'LTX2.3_DMD_reshaped_r256.safetensors'
            return s
        if isinstance(x,list): return [rec(v) for v in x]
        if isinstance(x,dict): return {k:rec(v) for k,v in x.items()}
        return x
    return rec(obj)

def write(p,d): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')

def static_build(project):
    original=json.load(open(project/'workflows/GoonMachine_original_v08.json',encoding='utf-8'))
    out=project/'workflows'
    write(out/'GoonMachine_T2I2V_5090_LUSTIFY_SAFE.json',patch_goon(original,'t2i','lustify',True,True,False))
    write(out/'GoonMachine_T2I2V_5090_FALLBACK_SAFE.json',patch_goon(original,'t2i','fallback',True,False,False))
    write(out/'GoonMachine_I2V_5090_SAFE.json',patch_goon(original,'i2v','fallback',True,False,False))
    write(out/'GoonMachine_T2I2V_5090_LUSTIFY_FULL.json',patch_goon(original,'t2i','lustify',False,True,False))
    write(out/'GoonMachine_T2I_5090_LUSTIFY_SAFE.json',patch_image_only(patch_goon(original,'t2i','lustify',True,True,False)))
    write(out/'GoonMachine_T2I_5090_FALLBACK_SAFE.json',patch_image_only(patch_goon(original,'t2i','fallback',True,False,False)))

def runtime():
    OUT.mkdir(parents=True,exist_ok=True)
    base=json.load(open(ORIGINAL,encoding='utf-8'))
    have_lustify=(MODELS/'diffusion_models/krea2/lustify-v10-krea-turbo-fp16.safetensors').exists()
    have_10lora=(MODELS/'loras/LTX/ltx2310eros_v14.safetensors').exists()
    have_ultimate=(MODELS/'loras/LTX/ltx23-ultimatedt-NSFW-sulphured_audio_final_k3nk.safetensors').exists()
    krea='lustify' if have_lustify else 'fallback'
    write(OUT/'GoonMachine_T2I2V_5090_AUTO_SAFE.json',patch_goon(base,'t2i',krea,True,have_10lora,have_ultimate))
    write(OUT/'GoonMachine_T2I2V_5090_AUTO_FULL.json',patch_goon(base,'t2i',krea,False,have_10lora,have_ultimate))
    write(OUT/'GoonMachine_T2I_5090_AUTO_SAFE.json',patch_image_only(patch_goon(base,'t2i',krea,True,have_10lora,have_ultimate)))
    write(OUT/'GoonMachine_I2V_5090_SAFE.json',patch_goon(base,'i2v',krea,True,have_10lora,have_ultimate))
    # Keep the exact source workflow accessible for comparison.
    shutil.copy2(ORIGINAL,OUT/'GoonMachine_original_v08.json')
    source=pathlib.Path('/workspace/workflows-source/10Eros_10SNodes_I2V_Basic_DMD_V5.json')
    if source.exists():
        d=json.load(open(source,encoding='utf-8')); write(OUT/'10Eros_I2V_DMD_V5_5090.json',patch_10eros(d))
    print(f'[workflows] installed in {OUT}; krea={krea}; 10eros_lora={have_10lora}; ultimate_lora={have_ultimate}')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--static-project'); a=ap.parse_args()
    if a.static_project: static_build(pathlib.Path(a.static_project))
    else: runtime()
