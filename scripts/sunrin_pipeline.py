#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, json, os, subprocess, sys, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BG = "#F5EBD7"
INK = "#303030"
ACCENT = "#8C1D18"

def project_dir(job): return ROOT / "projects" / job

def load(job):
    p = project_dir(job) / "project.json"
    return json.loads(p.read_text(encoding="utf-8"))

def save_status(job, **data):
    p = project_dir(job) / "status.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    old.update(data)
    p.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")

def size_for(aspect):
    return {"16:9": (1536,1024), "9:16": (1024,1536), "1:1": (1024,1024)}.get(aspect,(1536,1024))

def openai_image(prompt, out, size):
    key = os.getenv("OPENAI_API_KEY")
    if not key: return False
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    body = json.dumps({"model": os.getenv("OPENAI_IMAGE_MODEL","gpt-image-2"), "prompt": prompt, "size": f"{size[0]}x{size[1]}", "quality":"medium"}).encode()
    try:
        with urllib.request.urlopen(req, body, timeout=180) as r: data=json.load(r)
        item=data["data"][0]
        if item.get("b64_json"):
            out.write_bytes(base64.b64decode(item["b64_json"])); return True
        if item.get("url"):
            with urllib.request.urlopen(item["url"],timeout=180) as r: out.write_bytes(r.read()); return True
    except Exception as e:
        print(f"[warn] OpenAI image generation failed: {e}")
    return False

def fallback_image(scene, out, size):
    w,h=size; im=Image.new("RGB",size,BG); d=ImageDraw.Draw(im)
    # clean drawable fallback: person + phone + chart + alert/lock, arranged to fit any scam scenario
    lw=max(4,w//250)
    cx,cy=w//2,h//2
    d.ellipse((w*.10,h*.28,w*.25,h*.48),outline=INK,width=lw)
    d.line((w*.175,h*.48,w*.175,h*.78),fill=INK,width=lw)
    d.line((w*.175,h*.56,w*.08,h*.68),fill=INK,width=lw); d.line((w*.175,h*.56,w*.30,h*.65),fill=INK,width=lw)
    d.rounded_rectangle((w*.34,h*.24,w*.61,h*.72),radius=20,outline=INK,width=lw)
    d.line((w*.39,h*.58,w*.46,h*.48,w*.52,h*.53,w*.58,h*.38),fill=ACCENT,width=lw)
    d.polygon([(w*.58,h*.38),(w*.55,h*.40),(w*.58,h*.43)],fill=ACCENT)
    d.rounded_rectangle((w*.68,h*.36,w*.88,h*.60),radius=25,outline=INK,width=lw)
    d.arc((w*.72,h*.28,w*.84,h*.44),180,360,fill=INK,width=lw)
    d.ellipse((w*.765,h*.46,w*.79,h*.50),fill=ACCENT)
    out.parent.mkdir(parents=True,exist_ok=True); im.save(out)

def annotations(job, project):
    folder=project_dir(job)/"scenes"
    for i,s in enumerate(project["scenes"],1):
        img=Image.open(folder/f"scene-{i:02d}.png"); w,h=img.size; dur=int(s.get("durationMs") or 4000)
        parts=[]
        for j in range(3):
            x=int(w*j/3); x2=int(w*(j+1)/3); start=int(200+j*(dur-400)/3); d=max(500,int((dur-500)/3))
            parts.append({"id":f"part-{j+1}","label":f"part-{j+1}","sequence":j+1,"narrativeRole":s.get("role","scene"),"subtitle":s.get("narration",""),"type":"structure","region":{"x":x,"y":0,"width":x2-x,"height":h},"reveal":{"direction":"top_to_bottom","startMs":start,"durationMs":d,"maskPaddingPx":18,"protectedRegions":[]},"handPath":{"start":[(x+x2)//2,20],"end":[(x+x2)//2,h-20],"easing":"easeInOut"}})
        ann={"sceneId":f"scene-{i:02d}","canvas":{"width":w,"height":h},"storyBasis":s.get("visual",""),"sceneDurationMs":dur,"elements":parts}
        (folder/f"scene-{i:02d}.annotation.json").write_text(json.dumps(ann,ensure_ascii=False,indent=2),encoding="utf-8")

def generate_images(job):
    p=load(job); folder=project_dir(job)/"scenes"; folder.mkdir(parents=True,exist_ok=True); size=size_for(p.get("aspect"))
    for i,s in enumerate(p["scenes"],1):
        out=folder/f"scene-{i:02d}.png"
        prompt=(f"Premium hand-drawn whiteboard illustration on warm cream paper {BG}. {s.get('visual','')}. "
                "Dark gray pen outlines, sparse muted navy and burgundy accents, no readable text, no logo, no photo realism, no 3D, generous negative space, clear separated objects, clean contours suitable for progressive pen drawing.")
        if not openai_image(prompt,out,size): fallback_image(s,out,size)
    annotations(job,p); save_status(job,stage="images-ready",imagesReady=True)

def render_scene(job,index,total_ms=None):
    folder=project_dir(job)/"scenes"; renders=project_dir(job)/"renders"; renders.mkdir(parents=True,exist_ok=True)
    img=folder/f"scene-{index:02d}.png"; ann=folder/f"scene-{index:02d}.annotation.json"; out=renders/f"scene-{index:02d}.mp4"
    cmd=[sys.executable,str(ROOT/"scripts/render_stream_whiteboard.py"),str(img),str(ann),str(out),str(ROOT/"assets/drawing-hand.png"),"--ink-path","grid","--color-fill","contour-wipe"]
    if total_ms: cmd += ["--total-ms",str(total_ms)]
    subprocess.run(cmd,check=True)
    return out

def preview(job):
    p=load(job); annotations(job,p); out=render_scene(job,1,min(7000,int(p["scenes"][0].get("durationMs") or 5000)))
    target=project_dir(job)/"preview.mp4"; target.write_bytes(out.read_bytes()); save_status(job,stage="preview-ready",previewReady=True)

def final(job):
    p=load(job); annotations(job,p); outs=[]
    for i,s in enumerate(p["scenes"],1): outs.append(render_scene(job,i,int(s.get("durationMs") or 4000)))
    target=project_dir(job)/"final.mp4"
    subprocess.run([sys.executable,str(ROOT/"scripts/merge_scenes.py"),"--inputs",*[str(x) for x in outs],"--output",str(target)],check=True)
    save_status(job,stage="final-ready",finalReady=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("mode",choices=["images","preview","final"]); ap.add_argument("job")
    a=ap.parse_args(); save_status(a.job,stage=f"{a.mode}-running",error=None)
    try:
        {"images":generate_images,"preview":preview,"final":final}[a.mode](a.job)
    except Exception as e:
        save_status(a.job,stage="error",error=str(e)); raise
if __name__=="__main__": main()
