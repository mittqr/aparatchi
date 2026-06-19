#!/usr/bin/env python3
"""
Resolve current HLS links from aparatchi channel pages, keep only the live
ones, write an M3U playlist, and push it to a git repo (e.g. GitHub).

Run it from cron or a systemd timer every few hours. The IPTV player on your
TV points at the raw GitHub URL and refreshes on its own schedule.
"""

import re
import sys
import subprocess
import datetime
import urllib.request

# ---- config -----------------------------------------------------------------

# name, channel page url, group, logo url (logo can be left empty)
# scraped from https://www.aparatchi.com/sport-live-tv
CHANNELS = [
    ("Persiana Sports 1",  "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/persiana-sports",        "Sport", ""),
    ("Persiana Sports 2",  "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/persiana-sports2",       "Sport", ""),
    ("Persiana Sports 3",  "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/persiana-sports-3",      "Sport", ""),
    ("Persiana Sports 4",  "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/persiana-sports-4",      "Sport", ""),
    ("Persiana Fight",     "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/persiana-fight",         "Sport", ""),
    ("GEM Sport",          "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/gem-sport-live",        "Sport", ""),
    ("GEM FIT",            "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/gem-fit",                "Sport", ""),
    ("Varzish TV",         "https://www.aparatchi.com/?view=article&id=352:varzish-tv&catid=16",                  "Sport", ""),
    ("Shabake Varzesh",    "https://www.aparatchi.com/iran-live-tv/farsi-irib-tv/irib-varzesh-live-tv",            "Sport", ""),
    ("Shabake Se",         "https://www.aparatchi.com/iran-live-tv/farsi-irib-tv/irib3-live",                      "Sport", ""),
    ("Telewebion Sport 1", "https://www.aparatchi.com/iran-live-tv/farsi-entertainment-tv/telewebion-sport-1",     "Sport", ""),
    # رادیو ورزش (sport radio) left out on purpose, it is audio only, add it back if you want it:
    # ("Radio Varzesh", "https://www.aparatchi.com/iran-live-tv/iranian-radio/radionama-varzesh", "Sport", ""),
]

OUT_FILE  = "/home/adr/Pi/iptv/playlist.m3u"   # path inside your git repo working tree
REPO_DIR  = "/home/adr/Pi/iptv"                # the git repo root
GIT_BRANCH = "main"

REFERER   = "https://www.aparatchi.com/"
UA        = "Mozilla/5.0 (Linux; Android 14; Android TV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

PAGE_TIMEOUT   = 15
STREAM_TIMEOUT = 10
CHECK_LIVENESS = True   # set False to skip the probe and keep every resolved link

# ---- internals --------------------------------------------------------------

M3U8 = re.compile(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*')


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def resolve(page_url):
    try:
        html = fetch(page_url, PAGE_TIMEOUT)
    except Exception as e:
        print(f"[page-fail] {page_url} -> {e}", file=sys.stderr)
        return None
    m = M3U8.search(html)
    if not m:
        print(f"[no-stream] {page_url}", file=sys.stderr)
        return None
    return m.group(0)


def is_alive(stream_url):
    try:
        body = fetch(stream_url, STREAM_TIMEOUT)
    except Exception as e:
        print(f"[dead] {stream_url} -> {e}", file=sys.stderr)
        return False
    return ("#EXTM3U" in body) or ("#EXT-X" in body) or (".ts" in body)


def build_playlist():
    lines = ["#EXTM3U"]
    kept = 0
    for name, page, group, logo in CHANNELS:
        url = resolve(page)
        if not url:
            continue
        if CHECK_LIVENESS and not is_alive(url):
            continue
        lines.append(f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{name}')
        lines.append(f'#EXTVLCOPT:http-referrer={REFERER}')
        lines.append(f'#EXTVLCOPT:http-user-agent={UA}')
        lines.append(url)
        kept += 1
    print(f"[ok] {kept}/{len(CHANNELS)} channels live", file=sys.stderr)
    return "\n".join(lines) + "\n"


def git_push():
    subprocess.run(["git", "-C", REPO_DIR, "add", OUT_FILE], check=True)
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    committed = subprocess.run(
        ["git", "-C", REPO_DIR, "commit", "-m", f"update playlist {stamp}"]
    ).returncode == 0
    if committed:
        subprocess.run(["git", "-C", REPO_DIR, "push", "origin", GIT_BRANCH], check=True)
    else:
        print("[git] nothing changed, skipping push", file=sys.stderr)


def main():
    playlist = build_playlist()
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(playlist)
    git_push()


if __name__ == "__main__":
    main()
