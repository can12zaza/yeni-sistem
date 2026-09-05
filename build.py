#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAN TV - Playlist Builder
v3

Özellikler:
- sources.txt kaynaklarını birleştirir
- Aynı URL'leri temizler
- Aynı kanalın en kaliteli sürümünü seçer
- categories.json kategori sırasını korur
- categories.json kanal sırasını korur
- Alias desteği
- Kontrollü film tespiti
- group-title / tvg-name düzenleme
- Bilinmeyen kanalları Diğer'e atma
"""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


# ============================================================
# DOSYALAR
# ============================================================

ROOT = Path(__file__).resolve().parent

SOURCES = ROOT / "sources.txt"
CATEGORIES = ROOT / "categories.json"
CONFIG = ROOT / "config.json"
OUTPUT = ROOT / "playlist.m3u"

UA = "Mozilla/5.0 (CAN-TV-Builder/3.0)"


# ============================================================
# NORMALIZE
# ============================================================

def norm(value):
    """
    Kanal isimlerini karşılaştırmak için normalize eder.

    Örnek:

    TRT MÜZİK -> TRT MUZIK
    HABERTÜRK -> HABERTURK
    TV8       -> TV8
    TV 8      -> TV 8
    """

    s = str(value or "").upper().strip()

    # Türkçe karakterler
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

    # Kalite ifadelerini kaldır
    s = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264|FULL HD)\b",
        " ",
        s,
        flags=re.IGNORECASE,
    )

    # Noktalama işaretleri
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
# SOURCES.TXT
# ============================================================

def read_sources():

    if not SOURCES.exists():
        print("[HATA] sources.txt bulunamadı.")
        return []

    sources = []

    for line in SOURCES.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        sources.append(line)

    return sources


# ============================================================
# M3U İNDİR
# ============================================================

def fetch(url, timeout):

    request = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


# ============================================================
# M3U PARSER
# ============================================================

def parse_m3u(text):

    lines = text.splitlines()

    records = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        if line.startswith("#EXTINF"):

            ext = line

            j = i + 1

            # Boş satırları geç
            while j < len(lines):

                next_line = lines[j].strip()

                if next_line:
                    break

                j += 1

            if j < len(lines):

                url = lines[j].strip()

                # URL satırı # ile başlamamalı
                if url and not url.startswith("#"):

                    if "," in ext:
                        name = ext.split(
                            ",",
                            1,
                        )[1].strip()
                    else:
                        name = "KANAL"

                    records.append(
                        (
                            name,
                            ext,
                            url,
                        )
                    )

                    i = j + 1
                    continue

        i += 1

    return records


# ============================================================
# ALIAS
# ============================================================

ALIASES = {

    "TV8": [
        "TV 8",
        "TV8 HD",
        "TV 8 HD",
    ],

    "TV 8.5": [
        "TV8.5",
        "TV 8 5",
        "TV8 5",
    ],

    "HABERTÜRK": [
        "HABERTURK",
        "HABER TURK",
        "HABER TÜRK",
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

    "TRT MÜZİK": [
        "TRT MUZIK",
    ],

    "DREAM TÜRK": [
        "DREAM TURK",
    ],

    "NR1 TÜRK": [
        "NR1 TURK",
    ],

    "BEIN SPORTS HABER": [
        "BEIN HABER",
    ],

    "BLOOMBERG HT": [
        "BLOOMBERGHT",
    ],

    "EKOTÜRK": [
        "EKOTURK",
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
# ALIAS INDEX
# ============================================================

def make_alias_index(categories):

    index = {}

    # Önce categories.json
    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for name in names:

            key = norm(name)

            if key:
                index[key] = category

    # Sonra aliaslar
    for canonical, aliases in ALIASES.items():

        canonical_key = norm(canonical)

        if canonical_key not in index:
            continue

        category = index[canonical_key]

        for alias in aliases:

            alias_key = norm(alias)

            if alias_key:
                index[alias_key] = category

    return index


# ============================================================
# FİLM TESPİTİ
# ============================================================

def is_film(name, ext):

    """
    SADECE gerçek film kayıtlarını yakalamaya çalışır.

    ÖNEMLİ:
    'FILM', 'MOVIE', 'MOVIES' kelimesine tek başına
    bakılmaz.

    Böylece:

    BEIN MOVIES PREMIERE
    BEIN MOVIES ACTION
    FILMSCREEN
    SİNEMA TV

    yanlışlıkla Film kategorisine gitmez.
    """

    ext_upper = (ext or "").upper()

    name_upper = (name or "").upper()

    # --------------------------------------------------------
    # 1. tvg-year
    # --------------------------------------------------------

    if re.search(
        r'tvg[-_ ]?year\s*=\s*["\']?\d{4}',
        ext_upper,
        re.IGNORECASE,
    ):
        return True

    # --------------------------------------------------------
    # 2. TMDB
    # --------------------------------------------------------

    tmdb_patterns = [
        "IMAGE.TMDB.ORG",
        "IMAGE TMDB ORG",
        "TMDB.ORG",
        "IMAGE.TMDB",
    ]

    for pattern in tmdb_patterns:

        if pattern in ext_upper:
            return True

    # --------------------------------------------------------
    # 3. Film/Dizi arşivi kaynak işaretleri
    # --------------------------------------------------------

    archive_patterns = [
        "FILMDIZI",
        "FILM DIZI",
        "FILM-DIZI",
        "MOVIE-DATABASE",
        "MOVIEDB",
    ]

    for pattern in archive_patterns:

        if pattern in ext_upper:
            return True

    # --------------------------------------------------------
    # 4. Kanal isminin sonunda yıl
    # --------------------------------------------------------

    if re.search(
        r"\b(?:19|20)\d{2}\s*$",
        norm(name),
    ):
        return True

    # --------------------------------------------------------
    # 5. Açık film kaynağı bilgisi
    # --------------------------------------------------------

    source_patterns = [
        "TURKCE DUBLAJ",
        "TURKCE ALTYAZI",
        "IMDB",
    ]

    # Sadece EXTINF metadata içinde kontrol et
    for pattern in source_patterns:

        if pattern in ext_upper:
            return True

    return False


# ============================================================
# KATEGORİ BELİRLE
# ============================================================

def category_for(name, ext, index):

    # Önce gerçek film
    if is_film(name, ext):
        return "Film"

    n = norm(name)

    if not n:
        return "Diğer"

    # --------------------------------------------------------
    # Tam eşleşme
    # --------------------------------------------------------

    if n in index:
        return index[n]

    # --------------------------------------------------------
    # Çok kelimeli kontrollü eşleşme
    # --------------------------------------------------------

    tokens = set(n.split())

    best_category = None
    best_length = 0

    for key, category in index.items():

        key_tokens = key.split()

        # Tek kelimeli substring kullanma
        if len(key_tokens) < 2:
            continue

        if set(key_tokens).issubset(tokens):

            if len(key_tokens) > best_length:

                best_category = category
                best_length = len(key_tokens)

    if best_category:
        return best_category

    return "Diğer"


# ============================================================
# KALİTE
# ============================================================

def quality(name):

    value = (name or "").upper()

    # 4K / UHD
    if re.search(
        r"\b(4K|UHD)\b",
        value,
    ):
        return 4

    # FHD
    if re.search(
        r"\b(FHD|FULL HD)\b",
        value,
    ):
        return 3

    # HD
    if re.search(
        r"\bHD\b",
        value,
    ):
        return 2

    # SD
    if re.search(
        r"\bSD\b",
        value,
    ):
        return 1

    return 0


# ============================================================
# EXTINF DÜZENLE
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

    # Virgülden önceki bölüm
    prefix = ext.split(
        ",",
        1,
    )[0].strip()

    return (
        f'{prefix} '
        f'tvg-name="{name}" '
        f'group-title="{group}",'
        f'{name}'
    )


# ============================================================
# KATEGORİ SIRASI
# ============================================================

def build_category_order(categories):

    order = {}

    number = 0

    for category in categories.keys():

        order[category] = number

        number += 1

    # Film en sona yakın
    if "Film" not in order:

        order["Film"] = number
        number += 1

    # Diğer kesinlikle son
    order["Diğer"] = number

    return order


# ============================================================
# KANAL SIRASI
# ============================================================

def build_channel_order(categories):

    order = {}

    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for number, name in enumerate(names):

            key = norm(name)

            if key:
                order[key] = number

    return order


# ============================================================
# PLAYLIST SIRALA
# ============================================================

def sort_items(items, categories, index):

    category_order = build_category_order(
        categories
    )

    channel_order = build_channel_order(
        categories
    )

    def sort_key(item):

        name, ext, url = item

        category = category_for(
            name,
            ext,
            index,
        )

        category_number = category_order.get(
            category,
            999999,
        )

        name_key = norm(name)

        channel_number = channel_order.get(
            name_key,
            999999,
        )

        # categories.json'da bulunanlar
        if channel_number != 999999:

            return (
                category_number,
                0,
                channel_number,
            )

        # categories.json'da bulunmayanlar
        return (
            category_number,
            1,
            name_key,
        )

    return sorted(
        items,
        key=sort_key,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 65)
    print("CAN TV - PLAYLIST BUILDER v3")
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

        except Exception as e:

            print(
                f"[UYARI] config.json okunamadı: {e}"
            )

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
            "[HATA] categories.json bulunamadı!"
        )

        return

    try:

        categories = json.loads(
            CATEGORIES.read_text(
                encoding="utf-8",
            )
        )

    except Exception as e:

        print(
            f"[HATA] categories.json okunamadı: {e}"
        )

        return

    if not isinstance(categories, dict):

        print(
            "[HATA] categories.json JSON nesnesi olmalı."
        )

        return

    index = make_alias_index(
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
    # TÜM KAYITLAR
    # --------------------------------------------------------

    all_items = []

    successful_sources = 0

    for source in sources:

        try:

            text = fetch(
                source,
                timeout,
            )

            items = parse_m3u(
                text
            )

            all_items.extend(
                items
            )

            successful_sources += 1

            print(
                f"[OK] {source}"
            )

            print(
                f"     {len(items)} kayıt"
            )

        except Exception as e:

            print(
                f"[HATA] {source}"
            )

            print(
                f"       {e}"
            )

    print()

    # --------------------------------------------------------
    # URL DUPLICATE
    # --------------------------------------------------------

    by_url = {}

    for item in all_items:

        name, ext, url = item

        if not url:
            continue

        if url not in by_url:

            by_url[url] = item

        else:

            old = by_url[url]

            if quality(name) > quality(old[0]):

                by_url[url] = item

    # --------------------------------------------------------
    # AYNI KANAL ADI
    # --------------------------------------------------------

    best = {}

    for item in by_url.values():

        name, ext, url = item

        key = norm(name)

        if not key:
            continue

        if key not in best:

            best[key] = item

        else:

            old = best[key]

            if quality(name) > quality(old[0]):

                best[key] = item

    # --------------------------------------------------------
    # SIRALA
    # --------------------------------------------------------

    items = list(
        best.values()
    )

    items = sort_items(
        items,
        categories,
        index,
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # DOSYAYI YAZ
    # --------------------------------------------------------

    OUTPUT.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # RAPOR
    # --------------------------------------------------------

    print("=" * 65)
    print("SONUÇ")
    print("=" * 65)

    print(
        f"Kaynak sayısı   : {len(sources)}"
    )

    print(
        f"Başarılı kaynak : {successful_sources}"
    )

    print(
        f"Toplam kayıt    : {len(all_items)}"
    )

    print(
        f"Tekil URL       : {len(by_url)}"
    )

    print(
        f"Tekil kanal     : {len(best)}"
    )

    print()

    print("KATEGORİLER")
    print("-" * 65)

    # categories.json sırası
    for category in categories.keys():

        print(
            f"{category}: "
            f"{counts.get(category, 0)}"
        )

    # Film
    if "Film" in counts:

        print(
            f"Film: {counts['Film']}"
        )

    # Diğer
    if "Diğer" in counts:

        print(
            f"Diğer: {counts['Diğer']}"
        )

    print()

    print(
        f"Çıktı: {OUTPUT}"
    )

    print("=" * 65)
    print()


# ============================================================
# ÇALIŞTIR
# ============================================================

if __name__ == "__main__":
    main()
