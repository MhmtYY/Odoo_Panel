"""Yedekler: tek dosya (tar) = veritabani.dump (pg_dump -Fc) + filestore.tar.gz + meta.json.

Konum: /opt/odoo-panel/yedekler/<odoo>/<ortam>/<odoo>-<ortam>-<YYYYmmdd-HHMMSS>-<ETIKET>.tar
Her tar'ın yanında aynı adlı .json (liste hızlı okunsun diye meta kopyası) durur.
Bağlanan kurulumların yedeği de burada tutulur; eski test platformunun kendi yedek klasörüne dokunulmaz.
"""
import json
import re
import shutil
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import kayit
from .hata import Hata

ETIKET_DESEN = re.compile(r"^[A-Z][A-Z-]{1,30}$")
# etiket -> en çok kaç yedek tutulur (SILINMEDEN-ONCE hiç silinmez)
SAKLAMA = {"GECE": 7, "DEPLOY-ONCESI": 5, "ELLE": 10, "YENILEME-ONCESI": 3, "GERI-YUKLEME-ONCESI": 3,
           "GERI-ALMA-ONCESI": 3}


class Yedekler:
    def __init__(self, ayar, ortamlar):
        self.ayar = ayar
        self.ortamlar = ortamlar

    def dizin(self, odoo_id, ortam):
        return self.ayar.yedekler / odoo_id / ortam

    def _desen(self, odoo_id, ortam):
        return re.compile(rf"^{re.escape(odoo_id)}-{ortam}-(\d{{8}})-(\d{{6}})-([A-Z-]+)\.tar$")

    def liste(self, odoo_id, ortam):
        dizin = self.dizin(odoo_id, ortam)
        desen = self._desen(odoo_id, ortam)
        liste = []
        if dizin.is_dir():
            for yol in dizin.glob("*.tar"):
                eslesme = desen.match(yol.name)
                if not eslesme:
                    continue
                gun, saat, etiket = eslesme.groups()
                meta = kayit.oku(yol.with_suffix(".json"), {}) or {}
                liste.append({
                    "dosya": yol.name, "etiket": etiket, "boyut": yol.stat().st_size,
                    "tarih": f"{gun[:4]}-{gun[4:6]}-{gun[6:]}T{saat[:2]}:{saat[2:4]}:{saat[4:]}",
                    "commit": meta.get("commit"), "modul_sayisi": meta.get("modul_sayisi"),
                })
        return sorted(liste, key=lambda y: y["tarih"], reverse=True)

    def yol(self, odoo_id, ortam, dosya):
        if not self._desen(odoo_id, ortam).match(dosya or ""):
            raise Hata(400, "Geçersiz yedek adı.")
        yol = self.dizin(odoo_id, ortam) / dosya
        if not yol.is_file():
            raise Hata(404, "Yedek bulunamadı.")
        return yol

    def al(self, o, b, etiket="ELLE"):
        if not ETIKET_DESEN.match(etiket):
            raise Hata(400, "Geçersiz yedek etiketi.")
        dizin = self.dizin(o["odoo"], o["ad"])
        dizin.mkdir(parents=True, exist_ok=True)
        ad = f"{o['odoo']}-{o['ad']}-{datetime.now():%Y%m%d-%H%M%S}-{etiket}.tar"
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        gecici = Path(tempfile.mkdtemp(prefix=".yedek-", dir=self.ayar.gecici))
        try:
            b.yaz(f"Veritabanı yedeği: {o['db_adi']}")
            self.ortamlar.dokum_al(o, b, gecici / "veritabani.dump")
            b.yaz("Dosya deposu yedeği")
            self.ortamlar.filestore_paketle(o, b, gecici)
            sayi = self.ortamlar.psql(o, "SELECT count(*) FROM ir_module_module WHERE state = 'installed';",
                                      kontrol=False)
            meta = {"odoo": o["odoo"], "ortam": o["ad"], "db_adi": o["db_adi"], "commit": o.get("commit"),
                    "imaj": o.get("imaj"), "etiket": etiket, "tarih": kayit.simdi(),
                    "modul_sayisi": int(sayi) if sayi.isdigit() else None}
            (gecici / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            hedef = dizin / ad
            with tarfile.open(dizin / f".{ad}.yaziliyor", "w") as tar:
                for parca in ("veritabani.dump", "filestore.tar.gz", "meta.json"):
                    if (gecici / parca).exists():
                        tar.add(gecici / parca, arcname=parca)
            (dizin / f".{ad}.yaziliyor").replace(hedef)
            hedef.chmod(0o600)
            kayit.yaz(hedef.with_suffix(".json"), meta, gizli=True)
        finally:
            shutil.rmtree(gecici, ignore_errors=True)
        self.temizle(o["odoo"], o["ad"], etiket)
        boyut = hedef.stat().st_size
        b.yaz(f"Yedek: {ad} ({boyut / 1048576:.1f} MB)")
        return {"dosya": ad, "boyut": boyut}

    def temizle(self, odoo_id, ortam, etiket):
        sinir = SAKLAMA.get(etiket)
        if not sinir:
            return
        ayni = [y for y in self.liste(odoo_id, ortam) if y["etiket"] == etiket]
        for eski in ayni[sinir:]:
            yol = self.dizin(odoo_id, ortam) / eski["dosya"]
            yol.unlink(missing_ok=True)
            yol.with_suffix(".json").unlink(missing_ok=True)

    @contextmanager
    def ac(self, yol):
        """Yedeği geçici klasöre açar; (klasör, meta) verir."""
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        gecici = Path(tempfile.mkdtemp(prefix=".ac-", dir=self.ayar.gecici))
        try:
            with tarfile.open(yol) as tar:
                tar.extractall(gecici, filter="data")
            if not (gecici / "veritabani.dump").is_file():
                raise Hata(400, "Yedekte veritabanı yok.")
            meta = kayit.oku(gecici / "meta.json", {}) or {}
            yield gecici, meta
        finally:
            shutil.rmtree(gecici, ignore_errors=True)

    def geri_yukle(self, o, b, yol, guvenlik_yedegi=True):
        """Yedeği ortamın üzerine yükler (yalnız panelin yönettiği ortamlarda)."""
        if o.get("yonetim") != "panel":
            raise Hata(403, "Bağlanan kurulumlara panelden geri yükleme kapalı.")
        with self.ac(yol) as (klasor, meta):
            if guvenlik_yedegi:
                with b.adim("Şimdiki halin yedeği"):
                    self.al(o, b, "GERI-YUKLEME-ONCESI")
            with b.adim("Odoo durduruluyor"):
                self.ortamlar.durdur(o, b)
            with b.adim("Veritabanı yükleniyor"):
                self.ortamlar.db_sil(o, b)
                self.ortamlar.db_olustur(o, b)
                sayi = self.ortamlar.dokum_yukle(o, b, klasor / "veritabani.dump")
                b.yaz(f"{sayi} kurulu modül")
            with b.adim("Dosya deposu yükleniyor"):
                self.ortamlar.filestore_ac(o, b, klasor, meta.get("db_adi") or o["db_adi"])
        return meta
