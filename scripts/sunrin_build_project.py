#!/usr/bin/env python3
"""Create a reusable Sunrin whiteboard-video project from a scenario template.

This generator does not replace the upstream renderer. It prepares the SRT,
scene manifest, image-generation prompts and project folders that feed the
existing render_stream_whiteboard.py pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUNRIN = ROOT / "sunrin"
TEMPLATES = SUNRIN / "templates"
PROJECTS = ROOT / "projects"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^0-9a-zA-Z가-힣]+", "-", value)
    return value.strip("-") or "whiteboard-video"


def srt_time(ms: int) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def allocate(scenes: list[dict], total_ms: int) -> list[tuple[int, int]]:
    weights = [float(x.get("weight", 1)) for x in scenes]
    unit = total_ms / sum(weights)
    spans, cursor = [], 0
    for i, weight in enumerate(weights):
        end = total_ms if i == len(weights) - 1 else round(cursor + unit * weight)
        spans.append((cursor, end))
        cursor = end
    return spans


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="stock-reading-room")
    ap.add_argument("--title", default="주식리딩방 사기")
    ap.add_argument("--duration", type=float, default=30)
    ap.add_argument("--aspect", choices=["16:9", "9:16", "1:1"], default="16:9")
    ap.add_argument("--project", default=None)
    args = ap.parse_args()

    brand = json.loads((SUNRIN / "brand.json").read_text(encoding="utf-8"))
    template_path = TEMPLATES / f"{args.template}.json"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    scenes = template["scenes"]
    total_ms = round(args.duration * 1000)
    spans = allocate(scenes, total_ms)

    project_id = args.project or slugify(args.title)
    out = PROJECTS / project_id
    (out / "scenes").mkdir(parents=True, exist_ok=True)
    (out / "renders").mkdir(parents=True, exist_ok=True)

    srt = []
    manifest_scenes = []
    rules = ", ".join(brand["visualRules"])
    for idx, (scene, span) in enumerate(zip(scenes, spans), 1):
        start, end = span
        srt.extend([str(idx), f"{srt_time(start)} --> {srt_time(end)}", scene["narration"], ""])
        image_name = f"scene-{idx:02d}.png"
        annotation_name = f"scene-{idx:02d}.annotation.json"
        prompt = (
            f"Whiteboard hand-drawn illustration for scene {idx}. {scene['visual']} "
            f"Brand style: {rules}. Canvas background {brand['canvasColor']}. "
            "Single coherent scene, clear drawable contours, separated semantic objects, "
            "large clean shapes suitable for progressive pen-stroke reveal."
        )
        manifest_scenes.append({
            "index": idx,
            "role": scene["role"],
            "startMs": start,
            "endMs": end,
            "durationMs": end - start,
            "narration": scene["narration"],
            "image": f"scenes/{image_name}",
            "annotation": f"scenes/{annotation_name}",
            "imagePrompt": prompt,
            "status": "needs-image-and-annotation"
        })

    (out / "script.srt").write_text("\n".join(srt), encoding="utf-8")
    manifest = {
        "project": project_id,
        "title": args.title,
        "template": args.template,
        "durationMs": total_ms,
        "aspect": args.aspect,
        "brand": brand,
        "renderer": "scripts/render_stream_whiteboard.py",
        "handAsset": brand["drawingHandPath"],
        "scenes": manifest_scenes
    }
    (out / "project.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    prompts = "\n\n".join(f"SCENE {s['index']:02d}\n{s['imagePrompt']}" for s in manifest_scenes)
    (out / "image-prompts.txt").write_text(prompts, encoding="utf-8")
    print(f"PROJECT={out}")
    print(f"SRT={out / 'script.srt'}")
    print(f"MANIFEST={out / 'project.json'}")


if __name__ == "__main__":
    main()
