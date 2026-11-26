#!/usr/bin/env python3
"""Find the newest llama.cpp release that ships the requested binary asset.

The pinned "latest" GitHub release of llama.cpp is a pointer release with
no binaries; the real builds live in per-commit releases (b12776, ...).
This walks releases newest-first and prints "<tag> <download_url>" for the
first asset matching the given name pattern.

Usage: python3 fetch_llama.py '<asset-name-regex>'
"""
import json
import re
import sys
import urllib.request


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fetch_llama.py '<asset-name-regex>'", file=sys.stderr)
        return 2
    pat = re.compile(sys.argv[1])

    req = urllib.request.Request(
        "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=25",
        headers={"User-Agent": "pms-docker-build"},
    )
    rels = json.load(urllib.request.urlopen(req))

    best = None
    for rel in rels:
        for asset in rel.get("assets", []):
            if not pat.match(asset["name"]):
                continue
            # prefer the highest CUDA/ROCm toolchain version when several match
            ver = re.findall(r"-(?:cuda|rocm)-([0-9.]+)-", asset["name"])
            key = tuple(int(x) for x in ver[0].split(".")) if ver else (0,)
            cand = (rel["tag_name"], asset["browser_download_url"])
            if best is None or key > best[0]:
                best = (key, cand)

    if best is None:
        print("no llama.cpp release found with matching assets", file=sys.stderr)
        return 1
    print(f"{best[1][0]} {best[1][1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
