"""İmaj derleme kiti: imajlar/ + Türkçe düzeltme modülleri -> ../dagitim/odoo_imajlar_<sürüm>.tar.gz ve .sha256

    python araclar/imaj_paketle.py

Modüllerin kaynağı D:\\Proje\\Vekosis_ERP\\ERP\\addons20 (Odoo 20 sürümleri). Odoo 19'da yalnız vekosis_web_html_lang
gider; kodu iki sürümde aynıdır, manifest sürümü 19.0'a çevrilir. Enterprise kodu bu pakete girmez
(imajlar/enterprise_al.ps1 ayrı alır).
"""
import hashlib
import io
import re
import tarfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
HEDEF = KOK.parent / "dagitim"
ADDONS20 = Path(r"D:\Proje\Vekosis_ERP\ERP\addons20")
IMAJLAR = KOK / "imajlar"
KIT = ("Dockerfile", "Dockerfile.enterprise", "derle.sh")
MODULLER = {"addons20": ("vekosis_web_html_lang", "vekosis_tr_translations"), "addons19": ("vekosis_web_html_lang",)}
METIN = {".py", ".sh", ".xml", ".js", ".csv", ".po", ".pot", ".scss", ".css", ".md", ".txt", ""}


def veri(yol, klasor):
    icerik = yol.read_bytes()
    if yol.suffix in METIN:
        icerik = icerik.replace(b"\r\n", b"\n")
    if klasor == "addons19" and yol.name == "__manifest__.py":
        metin, sayi = re.subn(r'"version":\s*"20\.0\.', '"version": "19.0.', icerik.decode("utf-8"))
        if sayi != 1:
            raise SystemExit(f"manifest sürümü değiştirilemedi: {yol}")
        icerik = metin.encode("utf-8")
    return icerik


def main():
    girdiler = []
    for ad in KIT:
        girdiler.append((ad, veri(IMAJLAR / ad, ""), 0o755 if ad.endswith(".sh") else 0o644))
    for klasor, moduller in MODULLER.items():
        for modul in moduller:
            for yol in sorted((ADDONS20 / modul).rglob("*")):
                if yol.is_file() and "__pycache__" not in yol.parts and yol.suffix != ".pyc":
                    goreli = yol.relative_to(ADDONS20).as_posix()
                    girdiler.append((f"{klasor}/{goreli}", veri(yol, klasor), 0o644))
    ozet = hashlib.sha256()
    for ad, icerik, _ in girdiler:
        ozet.update(ad.encode() + b"\0" + icerik + b"\0")
    surum = ozet.hexdigest()[:8]
    HEDEF.mkdir(parents=True, exist_ok=True)
    paket = HEDEF / f"odoo_imajlar_{surum}.tar.gz"
    zaman = int(time.time())
    with tarfile.open(paket, "w:gz") as tar:
        for ad, icerik, mod in girdiler:
            bilgi = tarfile.TarInfo(f"imajlar/{ad}")
            bilgi.size, bilgi.mode, bilgi.mtime, bilgi.uname, bilgi.gname = len(icerik), mod, zaman, "root", "root"
            tar.addfile(bilgi, io.BytesIO(icerik))
    sha = hashlib.sha256(paket.read_bytes()).hexdigest()
    (HEDEF / f"{paket.name}.sha256").write_bytes(f"{sha}  {paket.name}\n".encode())
    print(f"sürüm  : {surum}")
    print(f"paket  : {paket} ({paket.stat().st_size / 1024:.0f} KB, {len(girdiler)} dosya)")
    print(f"sha256 : {sha}")


if __name__ == "__main__":
    main()
