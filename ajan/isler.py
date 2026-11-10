"""Uzun süren işler: arka planda çalışır, adımları ve günlüğü dosyaya yazılır.

Her iş bir anahtar taşır (ör. "deneme/production"). Aynı anahtarda aynı anda tek iş çalışır.
kuyruk=True verilen işler (webhook deploy'u) anahtar meşgulse bekler. Bekleyen tek iş tutulur;
yenisi gelirse eskisinin yerini alır (en son commit kazanır).
"""
import json
import threading
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime

from . import kayit
from .hata import Hata, Mesgul
from .komut import KomutHatasi


class IsBaglami:
    def __init__(self, yonetici, is_kaydi):
        self.yonetici = yonetici
        self.kayit = is_kaydi
        self.log_yolu = yonetici.dizin / f"{is_kaydi['id']}.log"
        self._kilit = threading.Lock()

    def yaz(self, satir):
        satir = self.yonetici.komut.maskele(str(satir))
        with self._kilit, open(self.log_yolu, "a", encoding="utf-8") as log:
            log.write(satir + "\n")

    def uyari(self, metin):
        self.kayit.setdefault("uyarilar", []).append(metin)
        self.yaz(f"UYARI: {metin}")
        self.yonetici.kaydet(self.kayit)

    @contextmanager
    def adim(self, ad):
        adimlar = self.kayit.setdefault("adimlar", [])
        adim = {"ad": ad, "durum": "calisiyor", "baslangic": kayit.simdi()}
        adimlar.append(adim)
        self.yaz(f"== ADIM {len(adimlar)}: {ad}")
        self.yonetici.kaydet(self.kayit)
        baslangic = datetime.now()
        try:
            yield adim
        except BaseException:
            adim["durum"] = "hata"
            raise
        else:
            if adim["durum"] == "calisiyor":
                adim["durum"] = "tamam"
        finally:
            adim["sure"] = round((datetime.now() - baslangic).total_seconds(), 1)
            self.yonetici.kaydet(self.kayit)

    def komut(self, args, **kw):
        kw.setdefault("log", None if "cikti_dosya" in kw else self.yaz)
        self.yaz("$ " + " ".join(str(a) for a in args[:12]) + (" ..." if len(args) > 12 else ""))
        return self.yonetici.komut.calistir(args, **kw)


class Isler:
    def __init__(self, ayar, komut, senkron=False):
        self.ayar = ayar
        self.komut = komut
        self.senkron = senkron
        self.dizin = ayar.isler
        self.dizin.mkdir(parents=True, exist_ok=True)
        self._kilit = threading.Lock()
        self._aktif = {}      # anahtar -> iş no
        self._bekleyen = {}   # anahtar -> (kayıt, işlev)
        self._agir = threading.BoundedSemaphore(max(1, ayar.agir_is_siniri))

    # -- kayıt
    def kaydet(self, is_kaydi):
        kayit.yaz(self.dizin / f"{is_kaydi['id']}.json", is_kaydi)

    def oku(self, is_no, satir=60):
        if not is_no or len(is_no) != 12 or any(c not in "0123456789abcdef" for c in is_no):
            raise Hata(400, "Geçersiz iş numarası.")
        is_kaydi = kayit.oku(self.dizin / f"{is_no}.json")
        if is_kaydi is None:
            raise Hata(404, "İş bulunamadı.")
        log = self.dizin / f"{is_no}.log"
        satirlar = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
        is_kaydi["cikti"] = "\n".join(satirlar[-satir:])
        return is_kaydi

    def liste(self, odoo=None, sinir=50, idler=None):
        kayitlar = []
        if idler:  # denetim kaydındaki işlerin sonucu
            for is_no in idler[:300]:
                if len(is_no) == 12 and all(c in "0123456789abcdef" for c in is_no):
                    is_kaydi = kayit.oku(self.dizin / f"{is_no}.json")
                    if is_kaydi:
                        kayitlar.append(is_kaydi)
            return kayitlar
        for yol in sorted(self.dizin.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                is_kaydi = json.loads(yol.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if odoo and is_kaydi.get("odoo") != odoo:
                continue
            kayitlar.append(is_kaydi)
            if len(kayitlar) >= sinir:
                break
        return kayitlar

    def _mesgul_metni(self, is_no):
        k = kayit.oku(self.dizin / f"{is_no}.json") or {}
        ne = k.get("aciklama") or k.get("tur") or "bir iş"
        kim = f", {k['kullanici']}" if k.get("kullanici") else ""
        zaman = str(k.get("baslangic") or k.get("olusturma") or "")
        ne_zaman = f", {zaman[11:16]} başladı" if len(zaman) >= 16 else ""
        return f"Bu ortamda süren bir iş var ({ne}{kim}{ne_zaman}). Bitince tekrar deneyin."

    def mesgul(self, anahtar):
        with self._kilit:
            return anahtar in self._aktif

    def aktif(self):
        with self._kilit:
            return dict(self._aktif)

    # -- başlatma
    def baslat(self, tur, anahtar, islev, *, odoo=None, ortam=None, kuyruk=False, agir=False, aciklama="",
               kullanici=None, ek=None):
        is_kaydi = {
            "id": uuid.uuid4().hex[:12], "tur": tur, "anahtar": anahtar, "odoo": odoo, "ortam": ortam,
            "aciklama": aciklama, "kullanici": kullanici, "durum": "bekliyor", "olusturma": kayit.simdi(),
        }
        if ek:
            is_kaydi.update(ek)
        with self._kilit:
            if anahtar in self._aktif:
                if not kuyruk:
                    raise Mesgul(self._mesgul_metni(self._aktif[anahtar]))
                eski = self._bekleyen.get(anahtar)
                if eski:
                    eski[0].update({"durum": "atlandi", "bitis": kayit.simdi(),
                                    "not": "Yerine daha yeni bir istek geldi."})
                    self.kaydet(eski[0])
                self._bekleyen[anahtar] = (is_kaydi, islev, agir)
                self.kaydet(is_kaydi)
                return is_kaydi
            self._aktif[anahtar] = is_kaydi["id"]
        self.kaydet(is_kaydi)
        self._calistir(is_kaydi, islev, agir)
        return is_kaydi

    def _calistir(self, is_kaydi, islev, agir):
        if self.senkron:
            self._yurut(is_kaydi, islev, agir)
        else:
            threading.Thread(target=self._yurut, args=(is_kaydi, islev, agir), daemon=True).start()

    def _yurut(self, is_kaydi, islev, agir):
        baglam = IsBaglami(self, is_kaydi)
        try:
            if agir:
                if not self._agir.acquire(blocking=False):
                    baglam.yaz("Başka ağır işlerin bitmesi bekleniyor...")
                    self._agir.acquire()
            try:
                is_kaydi.update(durum="calisiyor", baslangic=kayit.simdi())
                self.kaydet(is_kaydi)
                sonuc = islev(baglam)
                is_kaydi.update(durum=(sonuc or {}).pop("_durum", "tamam") if isinstance(sonuc, dict) else "tamam",
                                sonuc=sonuc or {})
            finally:
                if agir:
                    self._agir.release()
        except (Hata, KomutHatasi) as hata:
            is_kaydi.update(durum="hata", hata=hata.mesaj)
            if getattr(hata, "ayrinti", None):
                is_kaydi["ayrinti"] = hata.ayrinti
            baglam.yaz(f"HATA: {hata.mesaj}")
            if getattr(hata, "ayrinti", None):
                baglam.yaz(hata.ayrinti)
        except Exception as hata:  # noqa: BLE001 - iş kaydına yazılır
            is_kaydi.update(durum="hata", hata=f"Beklenmeyen hata: {type(hata).__name__}: {hata}",
                            ayrinti=traceback.format_exc()[-4000:])
            baglam.yaz(traceback.format_exc())
        finally:
            is_kaydi["bitis"] = kayit.simdi()
            self.kaydet(is_kaydi)
            self._sonraki(is_kaydi["anahtar"])

    def _sonraki(self, anahtar):
        with self._kilit:
            bekleyen = self._bekleyen.pop(anahtar, None)
            if bekleyen is None:
                self._aktif.pop(anahtar, None)
                return
            self._aktif[anahtar] = bekleyen[0]["id"]
        self._calistir(*bekleyen)
