#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAN TV - tek dosyalı playlist oluşturucu."""

import json, re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources.txt"
CATEGORIES = ROOT / "categories.json"
CONFIG = ROOT / "config.json"
OUTPUT = ROOT / "playlist.m3u"

UA = "Mozilla/5.0 (CAN-TV-Builder/1.0)"

def norm(s):
    s = (s or "").upper()
    tr = str.maketrans("İŞĞÜÖÇ", "ISGUOC")
    s = s.translate(tr)
    s = re.sub(r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264)\b", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def read_sources():
    if not SOURCES.exists():
        return []
    return [x.strip() for x in SOURCES.read_text(encoding="utf-8", errors="ignore").splitlines()
            if x.strip() and not x.lstrip().startswith("#")]

def fetch(url, timeout):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

def parse_m3u(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("#EXTINF"):
            ext = lines[i].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].startswith("#"):
                url = lines[j].strip()
                name = ext.split(",", 1)[1].strip() if "," in ext else "KANAL"
                out.append((name, ext, url))
                i = j + 1
                continue
        i += 1
    return out

ALIASES = {
    "TV8": ["TV 8"],
    "TV8 5": ["TV8.5", "TV 8.5", "TV8 5"],
    "HABERTURK": ["HABER TURK", "HABER TÜRK"],
    "NATIONAL GEOGRAPHIC": ["NAT GEO"],
    "NATIONAL GEOGRAPHIC WILD": ["NAT GEO WILD", "NAT WILD"],
    "DISCOVERY ID": ["ID DISCOVERY", "INVESTIGATION DISCOVERY"],
    "TRT MUZIK": ["TRT MÜZİK"],
    "DREAM TURK": ["DREAM TÜRK"],
    "NR1 TURK": ["NR1 TÜRK", "NR1 TURK"],
    "BEIN SPORTS HABER": ["BEIN HABER", "BEIN SPORTS HABER"],
}

def make_alias_index(categories):
    idx = {}
    for cat, names in categories.items():
        for name in names:
            idx[norm(name)] = cat
    for base, aliases in ALIASES.items():
        if base in idx:
            for a in aliases:
                idx[norm(a)] = idx[base]
    return idx

def is_film(name, ext):
    u = norm(name + " " + ext)
    # Film kaynaklarında sık görülen açık işaretler.
    if any(x in u for x in ["IMAGE TMDB ORG", "TVG YEAR", "FILMDIZI", "MOVIE", "FILM"]):
        return True
    return bool(re.search(r"\b(19|20)\d{2}\b$", u))

def category_for(name, ext, index):
    if is_film(name, ext):
        return "Film"
    n = norm(name)
    if n in index:
        return index[n]
    # Kontrollü substring eşleşmesi: kısa isimlerde yanlış eşleşmeyi önler.
    tokens = set(n.split())
    best = None
    best_len = 0
    for key, cat in index.items():
        kt = key.split()
        if len(kt) >= 2 and set(kt).issubset(tokens) and len(kt) > best_len:
            best, best_len = cat, len(kt)
    return best or "Diğer"

def quality(name):
    u = (name or "").upper()
    if "4K" in u or "UHD" in u: return 4
    if "FHD" in u or "FULL HD" in u: return 3
    if re.search(r"\bHD\b", u): return 2
    if re.search(r"\bSD\b", u): return 1
    return 0

def rewrite_ext(ext, name, group):
    # Eski group-title ve tvg-name değerlerini kontrollü şekilde değiştir.
    ext = re.sub(r'\s+tvg-name="[^"]*"', "", ext, flags=re.I)
    ext = re.sub(r'\s+group-title="[^"]*"', "", ext, flags=re.I)
    prefix = ext.split(",", 1)[0]
    return f'{prefix} tvg-name="{name}" group-title="{group}",{name}'

def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    categories = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    index = make_alias_index(categories)
    timeout = int(cfg.get("request_timeout", 15))

    all_items = []
    ok_sources = 0
    for src in read_sources():
        try:
            text = fetch(src, timeout)
            items = parse_m3u(text)
            all_items.extend(items)
            ok_sources += 1
            print(f"[OK] {src} -> {len(items)} kayıt")
        except Exception as e:
            print(f"[HATA] {src} -> {e}")

    # Aynı URL'yi tek kez tut.
    by_url = {}
    for name, ext, url in all_items:
        if url not in by_url or quality(name) > quality(by_url[url][0]):
            by_url[url] = (name, ext, url)

    # Aynı normalize kanal adında en kaliteli kaydı seç.
    best = {}
    for item in by_url.values():
        key = norm(item[0])
        if not key:
            continue
        if key not in best or quality(item[0]) > quality(best[key][0]):
            best[key] = item

    output = ["#EXTM3U"]
    counts = {}
    for name, ext, url in best.values():
        group = category_for(name, ext, index)
        # Film alt türleri için basit ve güvenli ayırım.
        if group == "Film":
            group = "Film"
        output.append(rewrite_ext(ext, name, group))
        output.append(url)
        counts[group] = counts.get(group, 0) + 1

    OUTPUT.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"\nKaynak: {ok_sources}")
    print(f"Tekil kayıt: {len(best)}")
    print("Kategoriler:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print(f"Çıktı: {OUTPUT}")

if __name__ == "__main__":
    main()
