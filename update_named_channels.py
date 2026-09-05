```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAN TV - update_named_channels.py

Amaç:
- categories.json içindeki sabit kanal isimlerini kullanır.
- sources.txt içindeki M3U kaynaklarını indirir.
- Kanal isimlerini categories.json ile eşleştirir.
- Eşleşen yayın URL'sini HTTP olarak kontrol eder.
- Çalışan kaynakları data/kanal_kaynaklari.m3u dosyasına yazar.
- data/kanal_raporu.json oluşturur.

ÖNEMLİ:
- data/kanal_listesi.json KULLANMAZ.
- Kanal listesi doğrudan categories.json dosyasından alınır.
- URL uydurmaz.
- Yalnızca sources.txt içindeki kaynakları kullanır.
"""

import re
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:
    requests = None


# ---------------------------------------------------------
# DOSYALAR
# ---------------------------------------------------------

ROOT = Path(__file__).resolve().parent

CATEGORIES_FILE = ROOT / "categories.json"
SOURCES_FILE = ROOT / "sources.txt"

DATA = ROOT / "data"
OUT_FILE = DATA / "kanal_kaynaklari.m3u"
REPORT_FILE = DATA / "kanal_raporu.json"

TIMEOUT = 12

UA = "Mozilla/5.0 (compatible; CAN-TV-Channel-Matcher/2.0)"


# ---------------------------------------------------------
# NORMALIZE
# ---------------------------------------------------------

def norm(text):
    """
    Kanal isimlerini karşılaştırılabilir hale getirir.

    Örnek:
        TV8       -> TV8
        TV 8      -> TV 8
        TV8.5     -> TV8 5
        BENGÜTÜRK -> BENGUTURK
        HABER TÜRK -> HABER TURK
    """

    s = str(text or "").upper().strip()

    tr_map = str.maketrans({
        "İ": "I",
        "Ş": "S",
        "Ğ": "G",
        "Ü": "U",
        "Ö": "O",
        "Ç": "C",
        "Â": "A",
        "Î": "I",
        "Û": "U",
    })

    s = s.translate(tr_map)

    # Yayın kalitesi ifadelerini kaldır
    s = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264|FULL HD)\b",
        " ",
        s
    )

    # Noktalama işaretlerini boşluk yap
    s = re.sub(r"[^A-Z0-9]+", " ", s)

    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------
# ÖZEL ALIASLAR
# ---------------------------------------------------------

ALIASES = {

    "TV8": {
        "TV8",
        "TV 8",
    },

    "TV8 5": {
        "TV8 5",
        "TV 8 5",
        "TV85",
        "TV 85",
    },

    "HABER TURK": {
        "HABERTURK",
        "HABER TURK",
    },

    "NATIONAL GEOGRAPHIC": {
        "NATIONAL GEOGRAPHIC",
        "NAT GEO",
    },

    "NATIONAL GEOGRAPHIC WILD": {
        "NATIONAL GEOGRAPHIC WILD",
        "NAT GEO WILD",
        "NAT WILD",
        "NATIONAL WILD",
    },

    "DISCOVERY ID": {
        "DISCOVERY ID",
        "ID DISCOVERY",
        "INVESTIGATION DISCOVERY",
    },

    "NR1": {
        "NR1",
        "NR1 TV",
        "NUMBER1",
    },

    "NR1 TURK": {
        "NR1 TURK",
        "NUMBER1 TURK",
    },

    "DREAM TURK": {
        "DREAM TURK",
    },

    "TRT MUZIK": {
        "TRT MUZIK",
    },

    "BENGUTURK": {
        "BENGUTURK",
        "BENGU TURK",
    },

    "BLOOMBERG HT": {
        "BLOOMBERG HT",
        "BLOOMBERGHT",
    },

    "EKOTURK": {
        "EKOTURK",
    },

    "LIFETIME": {
        "LIFETIME",
        "LIFE TIME",
    },

    "KRAL FM": {
        "KRAL FM",
        "KIRAL FM",
    },

    "KRAL POP": {
        "KRAL POP",
        "KIRAL POP",
    },
}


# ---------------------------------------------------------
# KANALLARI categories.json'DAN OKU
# ---------------------------------------------------------

def load_channels():
    """
    categories.json yapısı:

    {
        "Ulusal": [
            "TRT 1",
            "ATV",
            "TV8"
        ],
        "Haber": [
            "TRT HABER"
        ]
    }

    şeklindedir.

    Sonuç:
        [
            ("TRT 1", "Ulusal"),
            ("ATV", "Ulusal"),
            ("TV8", "Ulusal"),
            ("TRT HABER", "Haber")
        ]
    """

    if not CATEGORIES_FILE.exists():
        raise FileNotFoundError(
            f"categories.json bulunamadı: {CATEGORIES_FILE}"
        )

    data = json.loads(
        CATEGORIES_FILE.read_text(
            encoding="utf-8"
        )
    )

    channels = []

    for category, names in data.items():

        if not isinstance(names, list):
            continue

        for name in names:

            if not isinstance(name, str):
                continue

            name = name.strip()

            if not name:
                continue

            channels.append({
                "name": name,
                "category": category
            })

    return channels


# ---------------------------------------------------------
# SOURCE LİSTESİ
# ---------------------------------------------------------

def read_sources():

    if not SOURCES_FILE.exists():
        print("[UYARI] sources.txt bulunamadı.")
        return []

    result = []

    for line in SOURCES_FILE.read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if not (
            line.startswith("http://")
            or line.startswith("https://")
        ):
            continue

        result.append(line)

    return result


# ---------------------------------------------------------
# M3U KAYNAĞI İNDİR
# ---------------------------------------------------------

def fetch(url):

    if requests:

        r = requests.get(
            url,
            timeout=TIMEOUT,
            headers={
                "User-Agent": UA
            }
        )

        r.raise_for_status()

        return r.text

    req = Request(
        url,
        headers={
            "User-Agent": UA
        }
    )

    with urlopen(
        req,
        timeout=TIMEOUT
    ) as r:

        return r.read().decode(
            "utf-8",
            errors="ignore"
        )


# ---------------------------------------------------------
# M3U PARSE
# ---------------------------------------------------------

def parse_m3u(text, source):

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

                if (
                    url
                    and not url.startswith("#")
                    and (
                        url.startswith("http://")
                        or url.startswith("https://")
                    )
                ):

                    # Virgülden sonraki görünen isim
                    if "," in ext:
                        display = ext.split(",", 1)[1].strip()
                    else:
                        display = "KANAL"

                    # tvg-name varsa onu tercih et
                    m = re.search(
                        r'tvg-name\s*=\s*"([^"]+)"',
                        ext,
                        flags=re.IGNORECASE
                    )

                    if m:
                        display = m.group(1).strip()

                    result.append({
                        "name": display,
                        "url": url,
                        "ext": ext,
                        "source": source
                    })

            i = j + 1

        else:
            i += 1

    return result


# ---------------------------------------------------------
# KANAL EŞLEŞTİRME
# ---------------------------------------------------------

def channel_match(target, candidate):

    a = norm(target)
    b = norm(candidate)

    if not a or not b:
        return False

    # Birebir
    if a == b:
        return True

    # Boşluksuz karşılaştırma
    if a.replace(" ", "") == b.replace(" ", ""):
        return True

    # Alias kontrolü
    for canonical, aliases in ALIASES.items():

        canonical_norm = norm(canonical)

        if a == canonical_norm:

            if b == canonical_norm:
                return True

            for alias in aliases:

                if b == norm(alias):
                    return True

        if b == canonical_norm:

            if a == canonical_norm:
                return True

            for alias in aliases:

                if a == norm(alias):
                    return True

    return False


# ---------------------------------------------------------
# YAYIN KONTROL
# ---------------------------------------------------------

def check_stream(url):

    try:

        parsed = urlparse(url)

        if parsed.scheme not in (
            "http",
            "https"
        ):
            return False, "unsupported-scheme"

        if requests:

            r = requests.get(
                url,
                timeout=TIMEOUT,
                headers={
                    "User-Agent": UA
                },
                stream=True,
                allow_redirects=True
            )

            status = r.status_code

            ok = 200 <= status < 400

            r.close()

            return ok, f"http-{status}"

        req = Request(
            url,
            headers={
                "User-Agent": UA
            }
        )

        with urlopen(
            req,
            timeout=TIMEOUT
        ) as r:

            status = getattr(
                r,
                "status",
                200
            )

            return (
                200 <= status < 400,
                f"http-{status}"
            )

    except Exception as e:

        return False, type(e).__name__


# ---------------------------------------------------------
# KALİTE PUANI
# ---------------------------------------------------------

def quality_score(text):

    u = str(text or "").upper()

    if re.search(r"\b4K\b", u):
        return 4

    if "UHD" in u:
        return 4

    if "FHD" in u:
        return 3

    if "FULL HD" in u:
        return 3

    if re.search(r"\bHD\b", u):
        return 2

    if re.search(r"\bSD\b", u):
        return 1

    return 0


# ---------------------------------------------------------
# CANONICAL İSİM
# ---------------------------------------------------------

def canonical_name(name, channels):

    target = norm(name)

    for channel in channels:

        fixed_name = channel["name"]

        if channel_match(
            fixed_name,
            name
        ):
            return fixed_name

    return name


# ---------------------------------------------------------
# ANA PROGRAM
# ---------------------------------------------------------

def main():

    print()
    print("=" * 70)
    print("CAN TV - NAMED CHANNEL UPDATE")
    print("=" * 70)
    print()

    # data klasörünü oluştur
    DATA.mkdir(
        parents=True,
        exist_ok=True
    )

    # -----------------------------------------------------
    # KANALLARI categories.json'DAN OKU
    # -----------------------------------------------------

    try:

        channels = load_channels()

    except Exception as e:

        print(
            f"[HATA] categories.json okunamadı: {e}"
        )

        return 1

    print(
        f"[KANALLAR] {len(channels)} sabit kanal bulundu."
    )

    # -----------------------------------------------------
    # SOURCES
    # -----------------------------------------------------

    sources = read_sources()

    if not sources:

        print(
            "[HATA] sources.txt boş veya bulunamadı."
        )

        return 1

    print(
        f"[SOURCES] {len(sources)} kaynak bulundu."
    )

    print()

    # -----------------------------------------------------
    # KAYNAKLARDAN KANALLARI TOPLA
    # -----------------------------------------------------

    candidates = []

    source_errors = []

    for number, source in enumerate(
        sources,
        start=1
    ):

        try:

            text = fetch(source)

            records = parse_m3u(
                text,
                source
            )

            candidates.extend(records)

            print(
                f"[OK] Kaynak {number}: "
                f"{len(records)} kayıt"
            )

        except Exception as e:

            source_errors.append({
                "source": source,
                "error": str(e)
            })

            print(
                f"[HATA] Kaynak {number}: "
                f"{source}"
            )

            print(
                f"       {e}"
            )

    print()

    print(
        f"[TOPLAM] {len(candidates)} aday kanal bulundu."
    )

    print()

    # -----------------------------------------------------
    # SABİT KANALLARI BUL
    # -----------------------------------------------------

    output = [
        "#EXTM3U"
    ]

    report = {

        "total_channels": len(channels),

        "matched": 0,

        "not_found": 0,

        "source_count": len(sources),

        "candidate_count": len(candidates),

        "source_errors": source_errors,

        "channels": []
    }

    # Aynı kanal için tekrar tekrar aynı URL'yi kontrol
    tested_urls = {}

    # -----------------------------------------------------
    # KANAL KANAL İLERLE
    # -----------------------------------------------------

    for channel in channels:

        name = channel["name"]

        category = channel["category"]

        print(
            f"[ARAMA] {name} "
            f"({category})"
        )

        # -------------------------------------------------
        # ADAYLARI BUL
        # -------------------------------------------------

        matches = []

        for candidate in candidates:

            if channel_match(
                name,
                candidate["name"]
            ):

                matches.append(candidate)

        # -------------------------------------------------
        # KALİTEYE GÖRE SIRALA
        # -------------------------------------------------

        matches.sort(
            key=lambda x: quality_score(
                x["name"]
            ),
            reverse=True
        )

        chosen = None

        attempts = []

        # -------------------------------------------------
        # ÇALIŞAN URL BUL
        # -------------------------------------------------

        for candidate in matches:

            url = candidate["url"]

            if url in tested_urls:

                ok, reason = tested_urls[url]

            else:

                ok, reason = check_stream(
                    url
                )

                tested_urls[url] = (
                    ok,
                    reason
                )

            attempts.append({

                "url": url,

                "source": candidate["source"],

                "ok": ok,

                "reason": reason
            })

            if ok:

                chosen = candidate

                break

        # -------------------------------------------------
        # BULUNDU
        # -------------------------------------------------

        if chosen:

            url = chosen["url"]

            output.append(
                '#EXTINF:-1 '
                f'tvg-name="{name}" '
                f'group-title="{category}",'
                f'{name}'
            )

            output.append(
                url
            )

            report["matched"] += 1

            report["channels"].append({

                "name": name,

                "category": category,

                "status": "working",

                "url": url,

                "source": chosen["source"],

                "attempts": attempts
            })

            print(
                f"[ÇALIŞIYOR] {name}"
            )

            print(
                f"             {url}"
            )

        # -------------------------------------------------
        # BULUNAMADI
        # -------------------------------------------------

        else:

            report["not_found"] += 1

            report["channels"].append({

                "name": name,

                "category": category,

                "status": "not_found",

                "attempts": attempts
            })

            print(
                f"[BULUNAMADI] {name}"
            )

        print()

    # -----------------------------------------------------
    # ÇIKTI
    # -----------------------------------------------------

    OUT_FILE.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8"
    )

    REPORT_FILE.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # -----------------------------------------------------
    # SONUÇ
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("SONUÇ")
    print("=" * 70)

    print(
        f"Toplam kanal       : "
        f"{report['total_channels']}"
    )

    print(
        f"Eşleşen/çalışan    : "
        f"{report['matched']}"
    )

    print(
        f"Bulunamayan        : "
        f"{report['not_found']}"
    )

    print(
        f"Kaynak sayısı      : "
        f"{report['source_count']}"
    )

    print(
        f"Aday kayıt         : "
        f"{report['candidate_count']}"
    )

    print()

    print(
        f"Kaynak dosyası     : "
        f"{SOURCES_FILE}"
    )

    print(
        f"Çıktı              : "
        f"{OUT_FILE}"
    )

    print(
        f"Rapor              : "
        f"{REPORT_FILE}"
    )

    print("=" * 70)

    return 0


# ---------------------------------------------------------
# START
# ---------------------------------------------------------

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
```
