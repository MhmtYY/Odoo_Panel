"""Sunucu paketi: ajan/, panel/ ve sunucu/ -> ../dagitim/odoo_panel_<sürüm>.tar.gz ve .sha256

    python araclar/paketle.py

Sürüm: son commit'in kısa özeti; çalışma kopyasında commit'lenmemiş değişiklik varsa ardına içerik özeti eklenir
(ör. 9fc7348-d3a1b2). Metin dosyalarının satır sonu LF'ye çevrilir (sunucuda bash ve Python için şart).
Paketlemeden önce arayüz yeniden derlenir.
"""
import hashlib
import io
import subprocess
import sys
import tarfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
HEDEF = KOK.parent / "dagitim"
KLASORLER = ("ajan", "panel", "sunucu")
HARIC = ("panel/arayuz/",)
METIN = {".py", ".sh", ".service", ".timer", ".panel", ".js", ".css", ".html", ".md", ".txt", ""}
CALISTIRILIR = {".sh"}

sys.path.insert(0, str(KOK))
from araclar.arayuz_derle import derle  # noqa: E402


def git(*args):
    return subprocess.run(["git", "-C", str(KOK), *args], capture_output=True, text=True, check=True).stdout


def dosyalar():
    liste = git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    secilen = []
    for ad in sorted(set(liste)):
        if not ad or not ad.startswith(tuple(k + "/" for k in KLASORLER)) or ad.startswith(HARIC):
            continue
        if "__pycache__" in ad or ad.endswith((".pyc", ".gitkeep")):
            continue
        if (KOK / ad).is_file():
            secilen.append(ad)
    return secilen


def icerik(ad):
    veri = (KOK / ad).read_bytes()
    if Path(ad).suffix in METIN or Path(ad).name in ("Dockerfile", "Caddyfile.panel"):
        veri = veri.replace(b"\r\n", b"\n")
    return veri


def main():
    derle()
    adlar = dosyalar()
    commit = git("rev-parse", "--short=7", "HEAD").strip()
    degisik = bool(git("status", "--porcelain", "--", *KLASORLER).strip())
    ozet = hashlib.sha256()
    for ad in adlar:
        ozet.update(ad.encode() + b"\0" + icerik(ad) + b"\0")
    surum = f"{commit}-{ozet.hexdigest()[:6]}" if degisik else commit
    HEDEF.mkdir(parents=True, exist_ok=True)
    paket = HEDEF / f"odoo_panel_{surum}.tar.gz"
    zaman = int(time.time())

    def ekle(tar, ad, veri, mod):
        bilgi = tarfile.TarInfo(f"odoo-panel/{ad}")
        bilgi.size, bilgi.mode, bilgi.mtime, bilgi.uname, bilgi.gname = len(veri), mod, zaman, "root", "root"
        tar.addfile(bilgi, io.BytesIO(veri))

    with tarfile.open(paket, "w:gz") as tar:
        ekle(tar, "SURUM", (surum + "\n").encode(), 0o644)
        for ad in adlar:
            ekle(tar, ad, icerik(ad), 0o755 if Path(ad).suffix in CALISTIRILIR else 0o644)
    sha = hashlib.sha256(paket.read_bytes()).hexdigest()
    (HEDEF / f"{paket.name}.sha256").write_bytes(f"{sha}  {paket.name}\n".encode())
    print(f"sürüm  : {surum}{' (commit edilmemiş değişiklik var)' if degisik else ''}")
    print(f"paket  : {paket} ({paket.stat().st_size / 1024:.0f} KB, {len(adlar)} dosya)")
    print(f"sha256 : {sha}")


if __name__ == "__main__":
    main()
