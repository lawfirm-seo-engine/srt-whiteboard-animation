#!/usr/bin/env python3
from __future__ import annotations
import base64, io, subprocess, sys, urllib.request
from pathlib import Path
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


def _hand_enabled(project):
    if 'useHandDrawing' in project:
        return bool(project.get('useHandDrawing'))
    return project.get('renderMode', 'hand') != 'plain'


def _render_plain_scene(job, index, total_ms):
    folder = sp.project_dir(job) / 'scenes'
    renders = sp.project_dir(job) / 'renders'
    renders.mkdir(parents=True, exist_ok=True)
    img = folder / f'scene-{index:02d}.png'
    out = renders / f'scene-{index:02d}.mp4'
    sec = max(0.6, int(total_ms or 4000) / 1000.0)
    # 손이 없는 일반 영상: 원본 이미지 유지 + 아주 약한 줌 + 페이드 인/아웃
    fade_out = max(0.0, sec - 0.35)
    vf = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xF5EBD7,"
        "zoompan=z='min(zoom+0.00045,1.035)':d=1:s=1920x1080:fps=30,"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.35,format=yuv420p"
    )
    cmd = [
        'ffmpeg', '-y', '-loop', '1', '-i', str(img), '-t', f'{sec:.3f}',
        '-vf', vf, '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
        '-movflags', '+faststart', str(out)
    ]
    subprocess.run(cmd, check=True)
    return out


def _plain_final(job):
    p = sp.ensure_images(job)
    sp.save_status(job, stage='plain-final-running', finalReady=False, renderMode='plain')
    outs = []
    for i, scene in enumerate(p['scenes'], 1):
        sp.save_status(job, currentScene=i, totalScenes=len(p['scenes']))
        outs.append(_render_plain_scene(job, i, int(scene.get('durationMs') or 4000)))
    target = sp.project_dir(job) / 'final.mp4'
    subprocess.run([
        sys.executable, str(sp.ROOT / 'scripts/merge_scenes.py'), '--inputs',
        *[str(x) for x in outs], '--output', str(target)
    ], check=True)
    sp.save_status(job, stage='final-ready', finalReady=True, imagesReady=True,
                   currentScene=None, totalScenes=len(p['scenes']), renderMode='plain')


def final(job):
    p = sp.load(job)
    if _hand_enabled(p):
        return ORIGINAL_FINAL(job)
    return _plain_final(job)


def direct(job):
    p = sp.load(job)
    mode = 'hand' if _hand_enabled(p) else 'plain'
    sp.save_status(job, stage='direct-running', imagesReady=False, previewReady=False,
                   finalReady=False, renderMode=mode)
    generate_images(job)
    final(job)


ORIGINAL_FINAL = sp.final
sp.generate_images = generate_images
sp.final = final
sp.direct = direct

if __name__ == '__main__':
    sp.main()
