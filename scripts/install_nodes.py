#!/usr/bin/env python3
import argparse, json, os, pathlib, re, subprocess, sys, traceback


def run(cmd, cwd=None, check=True):
    print('+', ' '.join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check)


def patch_ltxvideo_kornia(repo: pathlib.Path):
    """Patch ComfyUI-LTXVideo for Kornia versions where pyramid.pad was removed."""
    target = repo / 'pyramid_blending.py'
    if not target.exists():
        return
    text = target.read_text(encoding='utf-8')
    original = text
    text = text.replace('    pad,\n', '')
    text = re.sub(r'(?<![\w.])pad\(', 'F.pad(', text)
    if text != original:
        target.write_text(text, encoding='utf-8')
        print('[patch] ComfyUI-LTXVideo: replaced deprecated kornia pyramid.pad with torch.nn.functional.pad', flush=True)
    elif 'from kornia.geometry.transform.pyramid' in text and 'pad,' not in text:
        print('[patch] ComfyUI-LTXVideo: Kornia compatibility already OK', flush=True)


def install_requirements(repo: pathlib.Path, py: str):
    req = repo / 'requirements.txt'
    if req.exists() and req.stat().st_size:
        run([py, '-m', 'pip', 'install', '--no-cache-dir', '-r', str(req)])
    if repo.name == 'ComfyUI-LTXVideo':
        patch_ltxvideo_kornia(repo)
    # Impact Pack has an installer for additional pieces.
    if repo.name == 'ComfyUI-Impact-Pack' and (repo / 'install.py').exists():
        run([py, 'install.py'], cwd=repo, check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default='/opt/ltx-suite/config/nodes.json')
    ap.add_argument('--custom-nodes', default='/opt/workspace-internal/ComfyUI/custom_nodes')
    ap.add_argument('--python', default=sys.executable)
    args = ap.parse_args()
    manifest = json.load(open(args.manifest, encoding='utf-8'))
    root = pathlib.Path(args.custom_nodes)
    root.mkdir(parents=True, exist_ok=True)
    failed = []
    for item in manifest:
        name, repo, required = item['name'], item['repo'], bool(item.get('required', True))
        dest = root / name
        try:
            if not dest.exists():
                run(['git', 'clone', '--depth', '1', '--recursive', repo, str(dest)])
            else:
                print(f'[skip] {name}: already present')
            install_requirements(dest, args.python)
        except Exception as e:
            print(f'[ERROR] custom node {name}: {e}', file=sys.stderr)
            traceback.print_exc()
            failed.append((name, required, str(e)))
    hard = [x for x in failed if x[1]]
    if failed:
        print('\nNode installation failures:')
        for name, required, err in failed:
            print(f' - {name}: {"REQUIRED" if required else "optional"}: {err}')
    if hard:
        raise SystemExit(2)

if __name__ == '__main__':
    main()
