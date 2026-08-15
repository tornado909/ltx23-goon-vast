#!/usr/bin/env python3
import os, pathlib, shutil

COMFY = pathlib.Path(os.environ.get('COMFYUI_DIR', '/opt/workspace-internal/ComfyUI'))
WORK = pathlib.Path(os.environ.get('WORKSPACE_DIR', '/workspace'))


def merge_and_link(name: str):
    dst = WORK / name
    src = COMFY / name
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if src.resolve() == dst.resolve():
            return
        src.unlink()
    elif src.exists():
        # Preserve anything shipped by ComfyUI/image before replacing with a workspace symlink.
        if src.is_dir():
            for p in src.iterdir():
                target = dst / p.name
                if not target.exists():
                    shutil.move(str(p), str(target))
            try: src.rmdir()
            except OSError: pass
        else:
            src.unlink()
    src.symlink_to(dst, target_is_directory=True)


def main():
    for n in ('models','input','output','user'):
        merge_and_link(n)
    for p in [WORK/'.cache/huggingface', WORK/'.cache/ollama', WORK/'user/default/workflows', WORK/'models/loras/LTX', WORK/'models/loras/krea2', WORK/'models/diffusion_models/ltx', WORK/'models/diffusion_models/krea2']:
        p.mkdir(parents=True, exist_ok=True)
    print('[runtime] workspace ready:', WORK)

if __name__ == '__main__': main()
