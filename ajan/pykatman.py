"""Python paket katmanı: depodaki requirements.txt için temel imajdan türetilmiş imaj.

İmaj adı pnl/<odoo>:<özet>; özet = temel imaj kimliği + temizlenmiş gereksinim satırları. Aynı içerik ikinci kez
derlenmez. Güvenlik için yalnız "paket[ekler] karşılaştırma sürüm" biçimindeki satırlar kabul edilir:
URL, git+, -e, --index-url gibi seçenekler reddedilir.
"""
import hashlib
import re
import shutil
import tempfile
from pathlib import Path

from .hata import Hata

SATIR = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}(\[[A-Za-z0-9_,.-]+\])?"
    r"(\s*(==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!-]{1,40}(\s*,\s*(==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!-]{1,40})*)?"
    r"(\s*;\s*[A-Za-z0-9_ .'\"<>=!]{1,120})?$")


def gereksinimleri_temizle(metin):
    satirlar = []
    for no, ham in enumerate((metin or "").splitlines(), 1):
        satir = ham.split(" #", 1)[0].strip()
        if not satir or satir.startswith("#"):
            continue
        if not SATIR.match(satir):
            raise Hata(400, f"requirements.txt satır {no} kabul edilmiyor: {satir[:80]} "
                            "(yalnız paket adı ve sürüm koşulu; URL, git+ ve seçenekler yok)")
        satirlar.append(satir)
    return satirlar


def imaj_hazirla(ortamlar, b, temel_imaj, gereksinim_metni, odoo_id):
    """Gereksinim yoksa temel imajı, varsa türetilmiş imajı döner (gerekirse derler)."""
    satirlar = gereksinimleri_temizle(gereksinim_metni)
    if not satirlar:
        return temel_imaj, []
    kimlik = ortamlar.imaj_kimligi(temel_imaj)
    if not kimlik:
        raise Hata(400, f"Temel imaj sunucuda yok: {temel_imaj}")
    ozet = hashlib.sha256((kimlik + "\n" + "\n".join(satirlar)).encode("utf-8")).hexdigest()[:12]
    imaj = f"pnl/{odoo_id}:{ozet}"
    if ortamlar.imaj_kimligi(imaj):
        b.yaz(f"Paket katmanı hazır: {imaj}")
        return imaj, satirlar
    ortamlar.ayar.gecici.mkdir(parents=True, exist_ok=True)
    klasor = Path(tempfile.mkdtemp(prefix=".imaj-", dir=ortamlar.ayar.gecici))
    try:
        (klasor / "requirements.txt").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        (klasor / "Dockerfile").write_text(
            f"FROM {temel_imaj}\n"
            "USER root\n"
            "COPY requirements.txt /tmp/panel-requirements.txt\n"
            "RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/panel-requirements.txt \\\n"
            "    && rm -f /tmp/panel-requirements.txt\n"
            "USER odoo\n"
            f'LABEL vekosis.panel.odoo="{odoo_id}" vekosis.panel.temel="{temel_imaj}"\n', encoding="utf-8")
        b.yaz(f"Paket katmanı derleniyor: {', '.join(satirlar)}")
        b.komut(["docker", "build", "--pull=false", "-t", imaj, str(klasor)], zaman_asimi=1800)
    finally:
        shutil.rmtree(klasor, ignore_errors=True)
    return imaj, satirlar
