"""
One-time conversion: assets/img/gifs/*.gif -> assets/img/webp/*.webp
(animated WebP is ~35% the size of GIF at comparable quality, and Flet's
Image control renders animated WebP natively). Originals are kept as a
backup — nothing in assets/img/gifs is deleted.

    python tools/gif_to_webp.py
"""
import os
import glob
from PIL import Image, ImageSequence

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE, "assets", "img", "gifs")
OUT_DIR = os.path.join(BASE, "assets", "img", "webp")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(SRC_DIR, "*.gif")))
    total_in = total_out = 0
    for i, f in enumerate(files, 1):
        out = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(f))[0] + ".webp")
        im = Image.open(f)
        frames = [fr.copy() for fr in ImageSequence.Iterator(im)]
        durations = [fr.info.get("duration", 100) for fr in ImageSequence.Iterator(im)]
        frames[0].save(out, format="WEBP", save_all=True, append_images=frames[1:],
                        duration=durations, loop=0, quality=78, method=6)
        total_in += os.path.getsize(f)
        total_out += os.path.getsize(out)
        if i % 100 == 0:
            print(f"{i}/{len(files)}...")
    print(f"Converted {len(files)} gifs.")
    print(f"{total_in/1e6:.1f} MB -> {total_out/1e6:.1f} MB "
          f"({100*total_out/total_in:.1f}%)")


if __name__ == "__main__":
    main()
