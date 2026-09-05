#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAN TV - Playlist Builder

Özellikler:
- sources.txt içindeki M3U kaynaklarını birleştirir
- Aynı URL'leri temizler
- Aynı kanalın farklı kalite sürümlerinden en kalitelisini seçer
- categories.json içindeki kategori sırasını korur
- categories.json içindeki kanal sırasını korur
- Alias desteği vardır
- group-title ve tvg-name yeniden oluşturulur
- Film tespitini kontrollü yapar
- categories.json'da olmayan kanalları Diğer'e atar
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

UA = "Mozilla/5.0 (CAN-TV-Builder/2.0)"


# ============================================================
# NORMALIZE
# ============================================================

def norm(s):
    """
    Kanal isimlerini karşılaştırılabilir hale getirir.

    Örnek:
        TV 8       -> TV 8
        TV8        -> TV8
        HaberTürk  -> HABERTURK
        TRT MÜZİK  -> TRT MUZIK
    """

    s = (s or "").upper()

    tr = str.maketrans(
        "İŞĞÜÖÇ",
        "ISGUOC"
    )

    s = s.translate(tr)

    # Kalite ifadelerini kaldır
    s = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264|FULL HD)\b",
        " ",
        s
    )

    # Noktalama işaretlerini boşluğa çevir
    s = re.sub(r"[^A-Z0-9]+", " ", s)

    return re.sub(r"\s+", " ", s).strip()


# ============================================================
# SOURCES
# ============================================================

def read_sources():
    if not SOURCES.exists():
        print("[UYARI] sources.txt bulunamadı.")
        return []

    result = []

    for line in SOURCES.read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        result.append(line)

    return result


# ============================================================
# URL'DEN M3U AL
# ============================================================

def fetch(url, timeout):
    req = Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urlopen(req, timeout=timeout) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


# ============================================================
# M3U PARSE
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

            # Boş satırları geç
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):

                url = lines[j].strip()

                # Yeni EXTINF gelmişse URL değildir
                if not url.startswith("#"):

                    if "," in ext:
                        name = ext.split(",", 1)[1].strip()
                    else:
                        name = "KANAL"

                    result.append(
                        (name, ext, url)
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
        "TV8 HD",
        "TV 8 HD"
    ],

    "TV8 5": [
        "TV8.5",
        "TV 8.5",
        "TV8 5",
        "TV 8 5"
    ],

    "HABERTURK": [
        "HABER TURK",
        "HABER TÜRK",
        "HABERTÜRK",
        "HABERTÜRK HD"
    ],

    "NATIONAL GEOGRAPHIC": [
        "NAT GEO",
        "NATIONAL GEOGRAPHIC HD"
    ],

    "NATIONAL GEOGRAPHIC WILD": [
        "NAT GEO WILD",
        "NAT WILD",
        "NATIONAL GEOGRAPHIC WILD HD"
    ],

    "DISCOVERY ID": [
        "ID DISCOVERY",
        "INVESTIGATION DISCOVERY",
        "ID"
    ],

    "TRT MUZIK": [
        "TRT MÜZİK",
        "TRT MUZİK"
    ],

    "DREAM TURK": [
        "DREAM TÜRK"
    ],

    "NR1 TURK": [
        "NR1 TÜRK",
        "NR1 TURK"
    ],

    "BEIN SPORTS HABER": [
        "BEIN HABER",
        "BEIN SPORTS HABER HD"
    ],
}


# ============================================================
# ALIAS INDEX
# ============================================================

def make_alias_index(categories):

    index = {}

    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for name in names:

            key = norm(name)

            if key:
                index[key] = category

    # Alias'ları ekle
    for base, aliases in ALIASES.items():

        base_key = norm(base)

        if base_key in index:

            category = index[base_key]

            for alias in aliases:

                index[norm(alias)] = category

    return index


# ============================================================
# FİLM KONTROLÜ
# ============================================================

def is_film(name, ext):

    name_norm = norm(name)

    ext_upper = (ext or "").upper()

    # Öncelikle film kaynaklarını kontrol et
    film_source_patterns = [
        "IMAGE.TMDB.ORG",
        "IMAGE TMDB ORG",
        "TVG-YEAR",
        "TVG_YEAR",
        "TVG YEAR",
        "FILMDIZI",
        "FILM DIZI"
    ]

    for pattern in film_source_patterns:

        if pattern in ext_upper:
            return True

    # tvg-year XML attribute
    if re.search(
        r'tvg-year\s*=\s*["\']?\d{4}',
        ext,
        re.IGNORECASE
    ):
        return True

    # İsmin sonundaki yıl
    if re.search(
        r"\b(19|20)\d{2}\s*$",
        name_norm
    ):
        return True

    return False


# ============================================================
# KATEGORİ BUL
# ============================================================

def category_for(name, ext, index):

    # Film kontrolü
    if is_film(name, ext):
        return "Film"

    n = norm(name)

    if not n:
        return "Diğer"

    # Tam eşleşme
    if n in index:
        return index[n]

    # Kontrollü çok kelimeli eşleşme
    tokens = set(n.split())

    best_category = None
    best_length = 0

    for key, category in index.items():

        key_tokens = key.split()

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

    u = (name or "").upper()

    # En yüksek
    if "4K" in u or "UHD" in u:
        return 4

    if "FHD" in u or "FULL HD" in u:
        return 3

    if re.search(r"\bHD\b", u):
        return 2

    if re.search(r"\bSD\b", u):
        return 1

    return 0


# ============================================================
# EXTINF YENİDEN OLUŞTUR
# ============================================================

def rewrite_ext(ext, name, group):

    # tvg-name sil
    ext = re.sub(
        r'\s+tvg-name="[^"]*"',
        "",
        ext,
        flags=re.IGNORECASE
    )

    # group-title sil
    ext = re.sub(
        r'\s+group-title="[^"]*"',
        "",
        ext,
        flags=re.IGNORECASE
    )

    # virgülden önceki bölüm
    prefix = ext.split(",", 1)[0]

    return (
        f'{prefix} '
        f'tvg-name="{name}" '
        f'group-title="{group}",'
        f'{name}'
    )


# ============================================================
# KANAL LİSTESİNİ SIRALA
# ============================================================

def sort_by_categories(items, categories, index):

    """
    categories.json sırasını kullanır.

    Önce:
        categories.json kategori sırası

    Sonra:
        kategori içindeki kanal sırası

    En son:
        categories.json'da olmayanlar
    """

    # --------------------------------------------------------
    # Kategori sıralaması
    # --------------------------------------------------------

    category_order = {}

    for category_number, category in enumerate(categories.keys()):
        category_order[category] = category_number

    # Diğer kategori en sona
    if "Diğer" not in category_order:
        category_order["Diğer"] = len(category_order)

    # Film yoksa sona eklenebilir
    if "Film" not in category_order:
        category_order["Film"] = len(category_order)

    # --------------------------------------------------------
    # Kanal sıralaması
    # --------------------------------------------------------

    channel_order = {}

    for category, names in categories.items():

        if not isinstance(names, list):
            continue

        for number, name in enumerate(names):

            key = norm(name)

            if key:
                channel_order[key] = number

    # --------------------------------------------------------
    # Sıralama
    # --------------------------------------------------------

    def sort_key(item):

        name, ext, url = item

        category = category_for(
            name,
            ext,
            index
        )

        cat_number = category_order.get(
            category,
            999999
        )

        name_key = norm(name)

        channel_number = channel_order.get(
            name_key,
            999999
        )

        # categories.json'da olmayanlar kendi arasında
        # alfabetik sıralanır
        fallback_name = name_key

        return (
            cat_number,
            channel_number,
            fallback_name
        )

    return sorted(
        items,
        key=sort_key
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("CAN TV PLAYLIST BUILDER")
    print("=" * 60)

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    if CONFIG.exists():

        try:
            cfg = json.loads(
                CONFIG.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as e:

            print(
                f"[UYARI] config.json okunamadı: {e}"
            )

            cfg = {}

    else:
        cfg = {}

    timeout = int(
        cfg.get(
            "request_timeout",
            15
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
                encoding="utf-8"
            )
        )

    except Exception as e:

        print(
            f"[HATA] categories.json okunamadı: {e}"
        )

        return

    if not isinstance(categories, dict):

        print(
            "[HATA] categories.json bir JSON nesnesi olmalı."
        )

        return

    index = make_alias_index(
        categories
    )

    # --------------------------------------------------------
    # KAYNAKLARI OKU
    # --------------------------------------------------------

    sources = read_sources()

    if not sources:

        print(
            "[HATA] sources.txt boş veya bulunamadı."
        )

        return

    # --------------------------------------------------------
    # TÜM KAYITLAR
    # --------------------------------------------------------

    all_items = []

    ok_sources = 0

    for source in sources:

        try:

            text = fetch(
                source,
                timeout
            )

            items = parse_m3u(
                text
            )

            all_items.extend(
                items
            )

            ok_sources += 1

            print(
                f"[OK] {source} -> "
                f"{len(items)} kayıt"
            )

        except Exception as e:

            print(
                f"[HATA] {source} -> {e}"
            )

    # --------------------------------------------------------
    # URL DUPLICATE TEMİZLE
    # --------------------------------------------------------

    by_url = {}

    for item in all_items:

        name, ext, url = item

        if not url:
            continue

        if (
            url not in by_url
            or quality(name)
            >
            quality(by_url[url][0])
        ):

            by_url[url] = item

    # --------------------------------------------------------
    # AYNI KANAL ADI DUPLICATE
    # --------------------------------------------------------

    best = {}

    for item in by_url.values():

        name, ext, url = item

        key = norm(name)

        if not key:
            continue

        if (
            key not in best
            or quality(name)
            >
            quality(best[key][0])
        ):

            best[key] = item

    # --------------------------------------------------------
    # LİSTE
    # --------------------------------------------------------

    items = list(
        best.values()
    )

    # --------------------------------------------------------
    # CATEGORIES.JSON SIRASINA GÖRE SIRALA
    # --------------------------------------------------------

    items = sort_by_categories(
        items,
        categories,
        index
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
            index
        )

        output.append(
            rewrite_ext(
                ext,
                name,
                group
            )
        )

        output.append(
            url
        )

        counts[group] = (
            counts.get(group, 0) + 1
        )

    # --------------------------------------------------------
    # DOSYAYA YAZ
    # --------------------------------------------------------

    OUTPUT.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # RAPOR
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("SONUÇ")
    print("=" * 60)

    print(
        f"Kaynak sayısı   : {len(sources)}"
    )

    print(
        f"Başarılı kaynak : {ok_sources}"
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
    print("-" * 40)

    # ÖNEMLİ:
    # sorted() KULLANMIYORUZ.
    # categories.json sırasını koruyor.

    printed = set()

    for category in categories.keys():

        if category in counts:

            print(
                f"{category}: "
                f"{counts[category]}"
            )

            printed.add(
                category
            )

    # Film
    if (
        "Film" in counts
        and "Film" not in printed
    ):

        print(
            f"Film: {counts['Film']}"
        )

        printed.add("Film")

    # Diğer
    if (
        "Diğer" in counts
        and "Diğer" not in printed
    ):

        print(
            f"Diğer: {counts['Diğer']}"
        )

    print()
    print(
        f"Çıktı: {OUTPUT}"
    )

    print("=" * 60)


# ============================================================
# ÇALIŞTIR
# ============================================================

if __name__ == "__main__":
    main()
