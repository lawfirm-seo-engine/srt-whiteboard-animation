#!/usr/bin/env python3
from __future__ import annotations
import base64, io, urllib.request
from PIL import Image
import sunrin_pipeline as sp

BG = sp.BG


def _fit_to_canvas(raw: bytes, out, size):
    src = Image.open(io.BytesIO(raw)).convert('RGB')
    w, h = size
    scale = min(w / src.width, h / src.height)
    nw, nh = max(1, round(src.width * scale)), max(1, round(src.height * scale))
    src = src.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, BG)
    canvas.paste(src, ((w - nw) // 2, (h - nh) // 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, 'PNG')


def _load_scene_image(scene):
    data = scene.get('imageData') or ''
    if data.startswith('data:image/') and ',' in data:
        return base64.b64decode(data.split(',', 1)[1])
    url = (scene.get('imageUrl') or '').strip()
    if url:
        req = urllib.request.Request(url, headers={'User-Agent': 'sunrin-whiteboard/1.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    return None


def generate_images(job):
    p = sp.load(job)
    folder = sp.project_dir(job) / 'scenes'
    folder.mkdir(parents=True, exist_ok=True)
    size = sp.size_for(p.get('aspect'))
    sp.save_status(job, stage='images-running', imagesReady=False)
    for i, scene in enumerate(p['scenes'], 1):
        out = folder / f'scene-{i:02d}.png'
        raw = None
        try:
            raw = _load_scene_image(scene)
        except Exception as e:
            print(f'[warn] preset image load failed for scene {i}: {e}')
        if raw:
            _fit_to_canvas(raw, out, size)
        else:
            sp.fallback_image(scene, out, size)
        sp.save_status(job, currentScene=i, totalScenes=len(p['scenes']))
    sp.annotations(job, p)
    sp.save_status(job, stage='images-ready', imagesReady=True, currentScene=None, totalScenes=len(p['scenes']))


sp.generate_images = generate_images

if __name__ == '__main__':
    sp.main()
