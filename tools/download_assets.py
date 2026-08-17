"""
Download exercise frame images into assets/img/ so the app works OFFLINE.

Reads data/exercises.json; for each exercise, downloads every URL in
`frames_remote` to the matching local path in `frames` (img/<id>/<n>.jpg).
Skips files already present. Re-run after tools/build_library.py.

    python tools/download_assets.py

(Runs on your machine with normal internet — no API key needed.)
"""
import json
import os
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "exercises.json")
ASSETS = os.path.join(BASE, "assets")


def main():
    lib = json.load(open(DATA))
    got = skipped = failed = 0
    for e in lib:
        for local, url in zip(e.get("frames", []), e.get("frames_remote", [])):
            dst = os.path.join(ASSETS, local)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                skipped += 1
                continue
            try:
                urllib.request.urlretrieve(url, dst)
                got += 1
            except Exception as ex:
                failed += 1
                print("FAIL", url, ex)
    print(f"downloaded {got}, skipped {skipped}, failed {failed}")
    print("App is now offline-ready." if failed == 0 else "Some downloads failed — re-run.")


if __name__ == "__main__":
    main()
