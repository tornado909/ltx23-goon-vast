#!/usr/bin/env python3
import os, shutil, subprocess, sys
import psutil

def gpu():
    try:
        out=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader,nounits'], text=True).strip().splitlines()[0]
        name, mem, drv=[x.strip() for x in out.split(',',2)]
        return name, int(float(mem)), drv
    except Exception as e:
        print('[preflight] nvidia-smi failed:',e)
        return None,0,None

def main():
    name,vram,drv=gpu()
    ram=psutil.virtual_memory().total/1024**3
    disk=shutil.disk_usage('/workspace').free/1024**3
    print(f'[preflight] GPU={name} VRAM={vram/1024:.1f} GiB driver={drv}')
    print(f'[preflight] RAM={ram:.1f} GiB free_disk={disk:.1f} GiB')
    if not name:
        raise SystemExit('No NVIDIA GPU detected')
    if vram < 30000:
        raise SystemExit('This build expects about 32 GB VRAM or more. Pick an RTX 5090/32GB or larger host.')
    if '5090' not in name:
        print('[preflight] WARNING: target is RTX 5090; continuing because VRAM is sufficient.')
    if ram < 55:
        raise SystemExit('At least ~64 GB system RAM is recommended; detected too little RAM.')
    if disk < 150:
        raise SystemExit('Not enough free disk. Allocate at least 200 GB to the Vast instance/template.')
    try:
        import torch
        print(f'[preflight] torch={torch.__version__} cuda={torch.version.cuda} available={torch.cuda.is_available()}')
        if not torch.cuda.is_available(): raise RuntimeError('torch CUDA unavailable')
        x=torch.ones((64,64), device='cuda', dtype=torch.float16); y=x@x; del x,y
        torch.cuda.synchronize()
        print('[preflight] CUDA smoke test OK')
    except Exception as e:
        raise SystemExit(f'PyTorch/CUDA smoke test failed: {e}')

if __name__=='__main__': main()
