#!/usr/bin/env python3
"""Merge multiple whiteboard MP4 scenes into one final MP4."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


def _ffmpeg_concat_copy(inputs: list[Path], output: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in inputs:
            f.write(f"file '{p.resolve().as_posix()}'\n")
        list_path = Path(f.name)
    try:
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c", "copy", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"ffmpeg concat-copy completed: {output}")
            return True

        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
             "-vf", "scale='trunc(iw/2)*2':'trunc(ih/2)*2'", "-movflags", "+faststart", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"ffmpeg re-encode concat completed: {output}")
            return True
        print(f"[warn] ffmpeg concat failed: {res.stderr.strip()[:500]}", file=sys.stderr)
        return False
    finally:
        list_path.unlink(missing_ok=True)


def _pyav_concat(inputs: list[Path], output: Path) -> bool:
    try:
        import av
    except ImportError:
        return False

    first = av.open(str(inputs[0]))
    vs = first.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    rate = vs.average_rate or 60
    first.close()

    rate_fraction = Fraction(rate)
    time_base = Fraction(rate_fraction.denominator, rate_fraction.numerator)

    out = av.open(str(output), mode="w")
    ostream = out.add_stream("h264", rate=rate_fraction)
    ostream.width, ostream.height = w, h
    ostream.pix_fmt = "yuv420p"
    ostream.time_base = time_base
    ostream.options = {"crf": "22", "preset": "medium", "movflags": "+faststart"}

    frame_index = 0
    try:
        for p in inputs:
            cont = av.open(str(p))
            try:
                for src in cont.decode(video=0):
                    # Rebuild each frame so source PTS/time_base cannot reset at scene boundaries.
                    arr = src.to_ndarray(format="bgr24")
                    frame = av.VideoFrame.from_ndarray(arr, format="bgr24")
                    if frame.width != w or frame.height != h:
                        frame = frame.reformat(width=w, height=h, format="yuv420p")
                    else:
                        frame = frame.reformat(format="yuv420p")
                    frame.pts = frame_index
                    frame.time_base = time_base
                    frame_index += 1
                    for pkt in ostream.encode(frame):
                        out.mux(pkt)
            finally:
                cont.close()

        for pkt in ostream.encode(None):
            out.mux(pkt)
    finally:
        out.close()

    print(f"PyAV concat completed: {output} ({frame_index} frames)")
    return output.exists() and output.stat().st_size > 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Merge whiteboard MP4 scenes in playback order")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    inputs = [Path(x) for x in args.inputs]
    missing = [str(x) for x in inputs if not x.exists()]
    if missing:
        print(f"[err] Missing inputs: {', '.join(missing)}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    if _ffmpeg_concat_copy(inputs, output) or _pyav_concat(inputs, output):
        print(f"OUTPUT={output.resolve()}")
        return 0

    print("[err] Scene merge failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
