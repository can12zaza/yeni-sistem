#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAN TV - Playlist Builder v4

- categories.json sırasını korur
- Aynı kanalı farklı isimlerle tekrar ettirmez
- Aynı URL'yi tekrar ettirmez
- TV8 / TV 8
- TV8.5 / TV 8.5 / TV8 5
- BENGUTURK / BENGÜTÜRK
  gibi isimleri birleştirir
- En kaliteli kaydı seçer
"""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent

SOURCES = ROOT / "sources.txt"
CATEGORIES = ROOT / "categories.json"
CONFIG = ROOT / "config.json"
OUTPUT = ROOT / "playlist.m3u"

UA = "Mozilla/5.0 (CAN-TV-Builder/4.0)"


# ============================================================
# NORMALIZE
# ============================================================

def norm(value):

    s = str(value or "").upper().strip()

    tr_map = str.maketrans(
        {
            "İ": "I",
            "Ş": "S",
            "Ğ": "G",
            "Ü": "U",
            "Ö": "O",
            "Ç": "C",
            "Â": "A",
            "Î": "I",
            "Û": "U",
        }
    )

    s = s.translate(tr_map)

    # Kalite bilgilerini kaldır
    s = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264|FULL HD)\b",
        " ",
        s,
    )

    # Noktalama
    s = re.sub(
        r"[^A-Z0-9]+",
        " ",
        s,
    )

    return re.sub(
        r"\s+",
        " ",
        s,
    ).strip()


# ============================================================
# CANONICAL CHANNEL KEY
# ============================================================

def channel_key(name):

    n = norm(name)

    # --------------------------------------------------------
    # TV8
    # --------------------------------------------------------

    if n in {
        "TV8",
        "TV 8",
    }:
        return "TV8"

    # --------------------------------------------------------
    # TV8.5
    # --------------------------------------------------------

    if n in {
        "TV 8 5",
        "TV8 5",
        "TV 8 5",
        "TV85",
    }:
        return "TV8.5"

    # --------------------------------------------------------
    # BENGÜTÜRK
    # --------------------------------------------------------

    if n in {
        "BENGUTURK",
        "BENGU TURK",
    }:
        return "BENGUTURK"

    # --------------------------------------------------------
    # HABERTÜRK
    # --------------------------------------------------------

    if n in {
        "HABERTURK",
        "HABER TURK",
    }:
        return "HABERTURK"

    # --------------------------------------------------------
    # TRT MÜZİK
    # --------------------------------------------------------

    if n in {
        "TRT MUZIK",
    }:
        return "TRT MUZIK"

    # --------------------------------------------------------
    # TRT DİYANET
    # --------------------------------------------------------

    if n in {
        "TRT DIYANET",
    }:
        return "TRT DIYANET"

    # --------------------------------------------------------
    # TRT DİYANET ÇOCUK
    # --------------------------------------------------------

    if n in {
        "TRT DIYANET COCUK",
    }:
        return "TRT DIYANET COCUK"

    # --------------------------------------------------------
    # NATIONAL GEOGRAPHIC
    # --------------------------------------------------------

    if n in {
        "NAT GEO",
        "NATIONAL GEOGRAPHIC",
    }:
        return "NATIONAL GEOGRAPHIC"

    # --------------------------------------------------------
    # NATIONAL GEOGRAPHIC WILD
    # --------------------------------------------------------

    if n in {
        "NAT GEO WILD",
        "NAT WILD",
        "NATIONAL GEOGRAPHIC WILD",
    }:
        return "NATIONAL GEOGRAPHIC WILD"

    # --------------------------------------------------------
    # DISCOVERY ID
    # --------------------------------------------------------

    if n in {
        "ID DISCOVERY",
        "DISCOVERY ID",
        "INVESTIGATION DISCOVERY",
    }:
        return "DISCOVERY ID"

    # --------------------------------------------------------
    # BLOOMBERG
    # --------------------------------------------------------

    if n in {
        "BLOOMBERG HT",
        "BLOOMBERGHT",
    }:
        return "BLOOMBERG HT"

    # --------------------------------------------------------
    # EKOTÜRK
    # --------------------------------------------------------

    if n in {
        "EKOTURK",
        "EKOTURK",
    }:
        return "EKOTURK"

    # --------------------------------------------------------
    # LIFETIME
    # --------------------------------------------------------

    if n in {
        "LIFETIME",
        "LIFE TIME",
    }:
        return "LIFETIME"

    # --------------------------------------------------------
    # KRAL FM
    # --------------------------------------------------------

    if n in {
        "KRAL FM",
        "KIRAL FM",
    }:
        return "KRAL FM"

    # --------------------------------------------------------
    # KRAL POP
    # --------------------------------------------------------

    if n in {
        "KRAL POP",
        "KIRAL POP",
    }:
        return "KRAL POP"

    return n


# ============================================================
# SOURCES
# ============================================================

def read_sources():

    if not SOURCES.exists():
        print("[HATA] sources.txt bulunamadı.")
        return []

    result = []

    for line in SOURCES.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        result.append(line)

    return result


# ============================================================
# FETCH
# ============================================================

def fetch(url, timeout):

    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
        },
    )

    with urlopen(
        req,
        timeout=timeout,
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


# ============================================================
# EXTINF NAME
# ============================================================

def extract_name(ext):

    if "," not in ext:
        return "KANAL"

    name = ext.split(
        ",",
        1,
    )[1].strip()

    # Bozuk EXTINF'lerde metadata tekrar edebiliyor.
    # Örneğin:
    #
    # tvg-id="TV 8 tvg-name="5"
    #
    # Burada gerçek isim bazen son tarafta bulunur.

    name = re.sub(
        r'\s+group-title=.*$',
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()

    return name or "KANAL"


# ============================================================
# M3U PARSER
# ============================================================

def parse_m3u(text):

    lines = text.splitlines()

    result = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        if line.startswith("#EXTINF"):

            ext = line

            j = i + 1

            while j < len(lines):

                candidate = lines[j].strip()

                if candidate:
                    break

                j += 1

            if j < len(lines):

                url = lines[j].strip()

                if url and not url.startswith("#"):

                    name = extract_name(ext)

                    result.append(
                        (
                            name,
                            ext,
                            url,
                        )
                    )

                    i = j + 1
                    continue

        i += 1

    return result


# ============================================================
# ALIAS
# ============================================================

ALIASES = {

    "TV8": [
        "TV 8",
    ],

    "TV8.5": [
        "TV 8.5",
        "TV8.5",
        "TV8 5",
        "TV 8 5",
    ],

    "HABERTURK": [
        "HABERTÜRK",
        "HABER TURK",
        "HABER TÜRK",
    ],

    "BENGUTURK": [
        "BENGÜTÜRK",
        "BENGU TURK",
    ],

    "TRT MUZIK": [
        "TRT MÜZİK",
    ],

    "NATIONAL GEOGRAPHIC": [
        "NAT GEO",
    ],

    "NATIONAL GEOGRAPHIC WILD": [
        "NAT GEO WILD",
        "NAT WILD",
    ],

    "DISCOVERY ID": [
        "ID DISCOVERY",
        "INVESTIGATION DISCOVERY",
    ],

    "BLOOMBERG HT": [
        "BLOOMBERGHT",
    ],

    "EKOTURK": [
        "EKOTÜRK",
    ],

    "LIFETIME": [
        "LIFE TIME",
    ],

    "KRAL FM": [
        "KIRAL FM",
    ],

    "KRAL POP": [
        "KIRAL POP",
    ],
}


# ============================================================
# CATEGORY INDEX
# ============================================================

def make_category_index(categories):

    index = {}

    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for name in names:

            key = channel_key(name)

            if key:
                index[key] = category

    return index


# ============================================================
# CATEGORY
# ============================================================

def category_for(name, ext, index):

    key = channel_key(name)

    # Önce tam eşleşme
    if key in index:
        return index[key]

    # --------------------------------------------------------
    # Film kontrolü
    # --------------------------------------------------------

    ext_upper = (ext or "").upper()

    if re.search(
        r'tvg[-_ ]?year\s*=\s*["\']?\d{4}',
        ext_upper,
    ):
        return "Film"

    if "TMDB.ORG" in ext_upper:
        return "Film"

    if "IMAGE.TMDB" in ext_upper:
        return "Film"

    # --------------------------------------------------------
    # Yıl
    # --------------------------------------------------------

    if re.search(
        r"\b(?:19|20)\d{2}\s*$",
        norm(name),
    ):
        return "Film"

    return "Diğer"


# ============================================================
# QUALITY
# ============================================================

def quality(name):

    value = (name or "").upper()

    if re.search(
        r"\b(4K|UHD)\b",
        value,
    ):
        return 4

    if re.search(
        r"\b(FHD|FULL HD)\b",
        value,
    ):
        return 3

    if re.search(
        r"\bHD\b",
        value,
    ):
        return 2

    if re.search(
        r"\bSD\b",
        value,
    ):
        return 1

    return 0


# ============================================================
# EXTINF REWRITE
# ============================================================

def rewrite_ext(ext, name, group):

    # Eski tvg-name
    ext = re.sub(
        r'\s+tvg-name\s*=\s*"[^"]*"',
        "",
        ext,
        flags=re.IGNORECASE,
    )

    # Eski group-title
    ext = re.sub(
        r'\s+group-title\s*=\s*"[^"]*"',
        "",
        ext,
        flags=re.IGNORECASE,
    )

    # Bozuk tvg-id tırnaklarını temizle
    ext = re.sub(
        r'tvg-id="[^"]*',
        lambda m: m.group(0),
        ext,
    )

    prefix = ext.split(
        ",",
        1,
    )[0].strip()

    # Çok uzun/bozuk metadata içindeki
    # tekrar eden tvg-name parçalarını kaldır
    prefix = re.sub(
        r'\s+tvg-name=.*?(?=\s+tvg-logo=|\s+group-title=|$)',
        "",
        prefix,
        flags=re.IGNORECASE,
    )

    prefix = re.sub(
        r'\s+group-title=.*$',
        "",
        prefix,
        flags=re.IGNORECASE,
    )

    return (
        f'{prefix} '
        f'tvg-name="{name}" '
        f'group-title="{group}",'
        f'{name}'
    )


# ============================================================
# CATEGORY ORDER
# ============================================================

def category_order(categories):

    result = {}

    number = 0

    for category in categories.keys():

        result[category] = number

        number += 1

    # Film
    if "Film" not in result:

        result["Film"] = number

        number += 1

    # Diğer en son
    result["Diğer"] = number

    return result


# ============================================================
# CHANNEL ORDER
# ============================================================

def channel_order(categories):

    result = {}

    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for number, name in enumerate(names):

            key = channel_key(name)

            if key:
                result[key] = number

    return result


# ============================================================
# SIRALA
# ============================================================

def sort_items(items, categories, index):

    cat_order = category_order(
        categories
    )

    ch_order = channel_order(
        categories
    )

    def key(item):

        name, ext, url = item

        category = category_for(
            name,
            ext,
            index,
        )

        category_no = cat_order.get(
            category,
            999999,
        )

        channel_no = ch_order.get(
            channel_key(name),
            999999,
        )

        return (
            category_no,
            channel_no,
            channel_key(name),
        )

    return sorted(
        items,
        key=key,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 65)
    print("CAN TV PLAYLIST BUILDER v4")
    print("=" * 65)
    print()

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    if CONFIG.exists():

        try:

            config = json.loads(
                CONFIG.read_text(
                    encoding="utf-8",
                )
            )

        except Exception:

            config = {}

    else:

        config = {}

    timeout = int(
        config.get(
            "request_timeout",
            15,
        )
    )

    # --------------------------------------------------------
    # CATEGORIES
    # --------------------------------------------------------

    if not CATEGORIES.exists():

        print(
            "[HATA] categories.json bulunamadı."
        )

        return

    categories = json.loads(
        CATEGORIES.read_text(
            encoding="utf-8",
        )
    )

    index = make_category_index(
        categories
    )

    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    sources = read_sources()

    if not sources:

        print(
            "[HATA] sources.txt boş."
        )

        return

    # --------------------------------------------------------
    # TOPLA
    # --------------------------------------------------------

    all_items = []

    successful = 0

    for source in sources:

        try:

            text = fetch(
                source,
                timeout,
            )

            records = parse_m3u(
                text
            )

            all_items.extend(
                records
            )

            successful += 1

            print(
                f"[OK] {len(records):>6} kayıt | {source}"
            )

        except Exception as e:

            print(
                f"[HATA] {source}"
            )

            print(
                f"       {e}"
            )

    print()

    # ========================================================
    # 1. URL DUPLICATE
    # ========================================================

    by_url = {}

    for item in all_items:

        name, ext, url = item

        if not url:
            continue

        old = by_url.get(url)

        if old is None:

            by_url[url] = item

        else:

            if quality(name) > quality(old[0]):

                by_url[url] = item

    # ========================================================
    # 2. CHANNEL DUPLICATE
    # ========================================================

    by_channel = {}

    duplicate_count = 0

    for item in by_url.values():

        name, ext, url = item

        key = channel_key(name)

        if not key:
            continue

        old = by_channel.get(key)

        if old is None:

            by_channel[key] = item

        else:

            duplicate_count += 1

            # Önce kalite
            new_quality = quality(name)
            old_quality = quality(old[0])

            if new_quality > old_quality:

                by_channel[key] = item

            # Kaliteler aynıysa ilk geleni koru
            # Böylece sources.txt sırası bozulmaz.

    # ========================================================
    # 3. LİSTE
    # ========================================================

    items = list(
        by_channel.values()
    )

    # ========================================================
    # 4. CATEGORIES SIRASI
    # ========================================================

    items = sort_items(
        items,
        categories,
        index,
    )

    # ========================================================
    # OUTPUT
    # ========================================================

    output = [
        "#EXTM3U"
    ]

    counts = {}

    for name, ext, url in items:

        group = category_for(
            name,
            ext,
            index,
        )

        output.append(
            rewrite_ext(
                ext,
                name,
                group,
            )
        )

        output.append(
            url
        )

        counts[group] = (
            counts.get(group, 0) + 1
        )

    OUTPUT.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8",
    )

    # ========================================================
    # RAPOR
    # ========================================================

    print("=" * 65)
    print("SONUÇ")
    print("=" * 65)

    print(
        f"Kaynak             : {len(sources)}"
    )

    print(
        f"Başarılı kaynak    : {successful}"
    )

    print(
        f"Toplam kayıt       : {len(all_items)}"
    )

    print(
        f"Tekil URL          : {len(by_url)}"
    )

    print(
        f"Tekil kanal        : {len(by_channel)}"
    )

    print(
        f"Silinen duplicate  : {duplicate_count}"
    )

    print()

    print("KATEGORİLER")
    print("-" * 65)

    # categories.json sırasını koru
    for category in categories.keys():

        print(
            f"{category}: "
            f"{counts.get(category, 0)}"
        )

    if "Film" in counts:

        print(
            f"Film: {counts['Film']}"
        )

    if "Diğer" in counts:

        print(
            f"Diğer: {counts['Diğer']}"
        )

    print()

    print(
        f"Çıktı: {OUTPUT}"
    )

    print("=" * 65)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
