"""
Generate one static PNG thumbnail per exercise from frame 0 of its animated
WebP, for the exercise list (list rows render this instead of decoding a full
animation per row; the animation still plays in the exercise detail view).

Input : assets/img/gifs_webp/<id>.webp
Output: assets/img/thumbs/<id>.png (200x200, contain-fit onto transparent bg)

    pip install pillow
    python tools/gen_thumbnails.py
"""
import os
from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(BASE, "assets", "img", "gifs_webp")
OUT_DIR = os.path.join(BASE, "assets", "img", "thumbs")
SIZE = 200


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    made = skipped = failed = 0
    for fn in sorted(os.listdir(SRC_DIR)):
        if not fn.lower().endswith(".webp"):
            continue
        xid = os.path.splitext(fn)[0]
        dst = os.path.join(OUT_DIR, f"{xid}.png")
        existing = next((os.path.join(OUT_DIR, f"{xid}.{ext}") for ext in ("webp", "png")
                         if os.path.exists(os.path.join(OUT_DIR, f"{xid}.{ext}"))), None)
        if existing and os.path.getsize(existing) > 0:
            skipped += 1
            continue
        try:
            im = Image.open(os.path.join(SRC_DIR, fn))
            im.seek(0)
            frame = im.convert("RGBA")
            frame.thumbnail((SIZE, SIZE), Image.LANCZOS)
            canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
            canvas.paste(frame, ((SIZE - frame.width) // 2, (SIZE - frame.height) // 2), frame)
            canvas.save(dst, "PNG", optimize=True)
            made += 1
        except Exception as ex:
            failed += 1
            print("FAIL", fn, ex)
    print(f"thumbnails: made {made}, skipped {skipped}, failed {failed} -> {OUT_DIR}")


if __name__ == "__main__":
    main()
