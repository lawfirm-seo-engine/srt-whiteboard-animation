#!/usr/bin/env python3
from __future__ import annotations
import base64, io, subprocess, sys, urllib.request
from PIL import Image
import sunrin_pipeline as sp

BG = sp.BG
HAND_MODE = 'hand'
PLAIN_MODES = {'slide','zoom','parallax','cinematic','callout','card-stack','news','glitch','plain'}


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
    p = sp.load(job); folder = sp.project_dir(job) / 'scenes'; folder.mkdir(parents=True, exist_ok=True)
    size = sp.size_for(p.get('aspect')); sp.save_status(job, stage='images-running', imagesReady=False)
    for i, scene in enumerate(p['scenes'], 1):
        out = folder / f'scene-{i:02d}.png'; raw = None
        try: raw = _load_scene_image(scene)
        except Exception as e: print(f'[warn] preset image load failed for scene {i}: {e}')
        _fit_to_canvas(raw, out, size) if raw else sp.fallback_image(scene, out, size)
        sp.save_status(job, currentScene=i, totalScenes=len(p['scenes']))
    sp.annotations(job, p); sp.save_status(job, stage='images-ready', imagesReady=True, currentScene=None, totalScenes=len(p['scenes']))


def _mode(project):
    mode = str(project.get('renderMode') or '').strip()
    if mode in PLAIN_MODES or mode == HAND_MODE: return mode
    return HAND_MODE if project.get('useHandDrawing', True) else 'slide'


def _canvas(aspect):
    return {'9:16':(1080,1920),'1:1':(1080,1080)}.get(aspect,(1920,1080))


def _vf(mode, sec, w, h, index):
    base=f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xF5EBD7"
    fo=max(0.0,sec-.28)
    fade=f"fade=t=in:st=0:d=.20,fade=t=out:st={fo:.3f}:d=.28"
    if mode in ('slide','plain'):
        return f"{base},{fade},format=yuv420p"
    if mode=='zoom':
        return f"{base},zoompan=z='min(zoom+0.00055,1.055)':d=1:s={w}x{h}:fps=30,{fade},format=yuv420p"
    if mode=='parallax':
        x="iw/2-(iw/zoom/2)+sin(on/18)*10"; y="ih/2-(ih/zoom/2)+cos(on/23)*7"
        return f"{base},zoompan=z='1.025':x='{x}':y='{y}':d=1:s={w}x{h}:fps=30,{fade},format=yuv420p"
    if mode=='cinematic':
        direction=1 if index%2 else -1
        x=f"iw/2-(iw/zoom/2)+{direction}*(on/30)*2"
        return f"{base},zoompan=z='min(zoom+0.00028,1.04)':x='{x}':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30,{fade},format=yuv420p"
    if mode=='callout':
        return f"{base},zoompan=z='if(lt(on,35),1,if(lt(on,75),1.07,1.025))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30,drawbox=x=w*.08:y=h*.08:w=w*.84:h=h*.84:color=0x8C1D18@0.38:t=3:enable='between(t,.7,1.7)',{fade},format=yuv420p"
    if mode=='card-stack':
        return f"{base},scale='if(lt(t,.28),iw*(.90+t*.35),iw)':'if(lt(t,.28),ih*(.90+t*.35),ih)':eval=frame,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xF5EBD7,{fade},format=yuv420p"
    if mode=='news':
        return f"{base},drawbox=x=0:y=h*.84:w=w:h=h*.16:color=0x172033@0.82:t=fill,drawbox=x=0:y=h*.84:w=w*.025:h=h*.16:color=0x8C1D18@1:t=fill,{fade},format=yuv420p"
    if mode=='glitch':
        return f"{base},noise=alls=7:allf=t:enable='between(t,.10,.20)+between(t,1.0,1.10)',eq=contrast=1.08:saturation=.92,{fade},format=yuv420p"
    return f"{base},{fade},format=yuv420p"


def _render_styled_scene(job,index,total_ms,mode,aspect):
    folder=sp.project_dir(job)/'scenes'; renders=sp.project_dir(job)/'renders'; renders.mkdir(parents=True,exist_ok=True)
    img=folder/f'scene-{index:02d}.png'; out=renders/f'scene-{index:02d}.mp4'; sec=max(.6,int(total_ms or 4000)/1000.0); w,h=_canvas(aspect)
    subprocess.run(['ffmpeg','-y','-loop','1','-i',str(img),'-t',f'{sec:.3f}','-vf',_vf(mode,sec,w,h,index),'-an','-c:v','libx264','-preset','medium','-crf','20','-movflags','+faststart',str(out)],check=True)
    return out


def _styled_final(job,p,mode):
    p=sp.ensure_images(job); sp.save_status(job,stage=f'{mode}-final-running',finalReady=False,renderMode=mode,useHandDrawing=False); outs=[]
    for i,s in enumerate(p['scenes'],1):
        sp.save_status(job,currentScene=i,totalScenes=len(p['scenes']))
        outs.append(_render_styled_scene(job,i,int(s.get('durationMs') or 4000),mode,p.get('aspect','16:9')))
    target=sp.project_dir(job)/'final.mp4'
    subprocess.run([sys.executable,str(sp.ROOT/'scripts/merge_scenes.py'),'--inputs',*[str(x) for x in outs],'--output',str(target)],check=True)
    sp.save_status(job,stage='final-ready',finalReady=True,imagesReady=True,currentScene=None,totalScenes=len(p['scenes']),renderMode=mode,useHandDrawing=False)


def final(job):
    p=sp.load(job); mode=_mode(p)
    # 핵심 수정: 손 렌더러는 renderMode가 정확히 hand일 때만 실행한다.
    if mode == HAND_MODE and p.get('useHandDrawing', True) is not False:
        sp.save_status(job,renderMode='hand',useHandDrawing=True)
        return ORIGINAL_FINAL(job)
    return _styled_final(job,p,'slide' if mode=='plain' else mode)


def direct(job):
    p=sp.load(job); mode=_mode(p); hand=(mode==HAND_MODE and p.get('useHandDrawing',True) is not False)
    if not hand and mode==HAND_MODE: mode='slide'
    sp.save_status(job,stage='direct-running',imagesReady=False,previewReady=False,finalReady=False,renderMode=mode,useHandDrawing=hand)
    generate_images(job); final(job)


ORIGINAL_FINAL=sp.final
sp.generate_images=generate_images
sp.final=final
sp.direct=direct

if __name__=='__main__': sp.main()
