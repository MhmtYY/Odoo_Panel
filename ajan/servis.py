"""Parçaları birbirine bağlar; HTTP sunucusu ve testler bu nesneyi kullanır."""
import json

from . import kayit, uyumluluk
from .asistan import Asistan
from .deploy import Deploylar
from .github import GitHub, urllib_istek
from .hata import Hata
from .isler import Isler
from .izleme import Izleme
from .komut import Komut
from .kurulum import Kurulum
from .odoolar import Odoolar
from .ortam import Ortamlar
from .staging import Staging
from .webhook import Webhook
from .yedek import Yedekler
from .zipdepo import ZipDepo


def _ceviri(deger):
    """Odoo 16+ çevrilebilir alanı jsonb ({"en_US": ..., "tr_TR": ...}); eski sürümlerde düz metin."""
    if not deger:
        return ""
    if isinstance(deger, str) and deger.startswith("{"):
        try:
            sozluk = json.loads(deger)
        except ValueError:
            return deger
        if isinstance(sozluk, dict):
            return sozluk.get("tr_TR") or sozluk.get("en_US") or next(iter(sozluk.values()), "")
    return str(deger)


class Servis:
    def __init__(self, ayar, komut=None, http=urllib_istek, senkron=False):
        self.ayar = ayar
        ayar.klasorleri_kur()
        self.komut = komut or Komut()
        self.isler = Isler(ayar, self.komut, senkron=senkron)
        self.github = GitHub(ayar, self.komut, http=http)
        self.ortamlar = Ortamlar(ayar, self.komut)
        self.odoolar = Odoolar(ayar, self.komut, self.github)
        self.yedekler = Yedekler(ayar, self.ortamlar)
        self.deploylar = Deploylar(ayar, self.isler, self.ortamlar, self.odoolar, self.yedekler)
        self.staging = Staging(ayar, self.isler, self.ortamlar, self.odoolar, self.yedekler, self.deploylar)
        self.kurulum = Kurulum(ayar, self.komut, self.isler, self.ortamlar, self.odoolar)
        self.webhook = Webhook(ayar, self.odoolar, self.ortamlar, self.deploylar)
        self.zipdepo = ZipDepo(ayar, self.isler, self.ortamlar, self.odoolar, self.deploylar, self.github, self.webhook)
        self.izleme = Izleme(ayar, self.komut, self.ortamlar, self.odoolar, self.deploylar)
        self.asistan = Asistan(ayar, self.komut, self.ortamlar, self.odoolar, self.webhook)

    # ------------------------------------------------------------ özetler
    def odoo_ozeti(self, od, durum=False):
        ozet = dict(od)
        ozet["ortamlar"] = {}
        for ortam in ("production", "staging"):
            o = self.ortamlar.oku(od["id"], ortam)
            if not o:
                ozet["ortamlar"][ortam] = None
                continue
            ozet["ortamlar"][ortam] = self.ortam_ozeti(o, durum=durum)
        return ozet

    def ortam_ozeti(self, o, durum=False):
        alanlar = ("ad", "yonetim", "konteyner", "adres", "imaj", "imaj_temel", "commit", "son_deploy",
                   "son_deploy_tarih", "bekleyen", "veri_kaynak", "yenileme", "notr", "db_adi", "olusturma")
        ozet = {k: o.get(k) for k in alanlar}
        ozet["mesgul"] = self.isler.mesgul(f"{o['odoo']}/{o['ad']}")
        if durum:
            ozet["durum"] = self.ortamlar.konteyner_durumu(o)
        return ozet

    def odoo_listesi(self):
        liste = [self.odoo_ozeti(od) for od in self.odoolar.liste()]
        konteynerler = [o["konteyner"] for od in liste for o in od["ortamlar"].values() if o]
        istatistik = self.ortamlar.istatistik(konteynerler)
        for od in liste:
            for o in od["ortamlar"].values():
                if o:
                    o["kaynak"] = istatistik.get(o["konteyner"])
                    o["durum"] = "running" if o["kaynak"] else None
        return {"odoolar": liste, "bos_bellek_mb": self.ortamlar.bos_bellek_mb()}

    def giris_bilgisi(self, odoo_id):
        self.odoolar.gerekli(odoo_id)
        bilgi = kayit.oku(self.ayar.odoolar / odoo_id / "giris.json")
        if not bilgi:
            raise Hata(404, "Bu Odoo için saklanan giriş bilgisi yok (bağlanan kurulum ya da eski kayıt).")
        return bilgi

    # ------------------------------------------------------------ durdur / başlat
    def durdur_baslat(self, odoo_id, ortam, islem, kullanici=None):
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        if o.get("yonetim") != "panel" and not od.get("islemler_acik"):
            raise Hata(403, "Bu bağlanan kurulumda durdurma ve başlatma kapalı (Ayarlar'dan açılır).")

        def isle(b):
            with b.adim("Durduruluyor" if islem == "durdur" else "Başlatılıyor"):
                if islem == "durdur":
                    self.ortamlar.durdur(o, b)
                else:
                    self.ortamlar.baslat(o, b)
            if islem == "baslat":
                with b.adim("Sağlık denetimi"):
                    if not self.ortamlar.saglik(o, b):
                        raise Hata(500, "Odoo açılmadı.")
            return {"durum": self.ortamlar.konteyner_durumu(o)}

        return self.isler.baslat(islem, f"{odoo_id}/{ortam}", isle, odoo=odoo_id, ortam=ortam, kullanici=kullanici,
                                 aciklama=f"{ortam} {'durduruluyor' if islem == 'durdur' else 'başlatılıyor'}")

    def yedek_al(self, odoo_id, ortam, kullanici=None, etiket="ELLE"):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        return self.isler.baslat("yedek", f"{odoo_id}/{ortam}",
                                 lambda b: self.yedekler.al(o, b, etiket), odoo=odoo_id, ortam=ortam, agir=True,
                                 kullanici=kullanici, aciklama=f"{ortam} yedeği")

    def geri_yukle(self, odoo_id, ortam, dosya, onay, kullanici=None):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        if o.get("yonetim") != "panel":
            raise Hata(403, "Bağlanan kurulumlara panelden geri yükleme kapalı.")
        beklenen = o["adres"].replace("https://", "")
        if str(onay or "").strip().lower() != beklenen:
            raise Hata(400, f"Onay için tam adres yazılmalı: {beklenen}")
        yol = self.yedekler.yol(odoo_id, ortam, dosya)

        def isle(b):
            meta = self.yedekler.geri_yukle(o, b, yol)
            with b.adim("Odoo başlatılıyor"):
                self.ortamlar.baslat(o, b)
                if not self.ortamlar.saglik(o, b):
                    raise Hata(500, "Odoo geri yüklemeden sonra açılmadı.")
            if meta.get("commit") and meta.get("commit") != o.get("commit"):
                b.uyari(f"Yedek {str(meta['commit'])[:7]} commit'iyle alınmıştı; yayındaki kod "
                        f"{str(o.get('commit') or '-')[:7]}. Gerekirse o commit'i deploy edin.")
            return {"dosya": dosya}

        return self.isler.baslat("geri-yukle", f"{odoo_id}/{ortam}", isle, odoo=odoo_id, ortam=ortam, agir=True,
                                 kullanici=kullanici, aciklama=f"{dosya} geri yükleniyor")

    def gece_yedegi(self):
        """Bütün ortamların GECE yedeği (systemd zamanlayıcısı çağırır); sırayla, senkron."""
        sonuc = []
        for od in self.odoolar.liste():
            for ortam in ("production", "staging"):
                o = self.ortamlar.oku(od["id"], ortam)
                if not o or self.ortamlar.konteyner_durumu(o) == "yok":
                    continue
                anahtar = f"{od['id']}/{ortam}"
                try:
                    is_kaydi = self.isler.baslat("yedek", anahtar, lambda b, o=o: self.yedekler.al(o, b, "GECE"),
                                                 odoo=od["id"], ortam=ortam, kuyruk=True, aciklama="Gece yedeği")
                    sonuc.append({"odoo": od["id"], "ortam": ortam, "is": is_kaydi["id"]})
                except Hata as hata:
                    sonuc.append({"odoo": od["id"], "ortam": ortam, "hata": hata.mesaj})
        return sonuc

    # ------------------------------------------------------------ modüller ve loglar
    def moduller(self, odoo_id, ortam):
        """Veritabanındaki bütün modüller. Bu ortama özel olanlar (depo, ek klasör) kaynağıyla işaretlenir;
        klasörde olup veritabanının listesinde henüz olmayanlar da eklenir."""
        o = self.ortamlar.gerekli(odoo_id, ortam)
        sql = ("SELECT coalesce(json_agg(json_build_object('ad', m.name, 'baslik', m.shortdesc::text, 'durum', m.state, "
               "'surum', m.latest_version, 'yazar', m.author, 'uygulama', m.application, 'lisans', m.license, "
               "'kategori', c.name::text) ORDER BY m.name), '[]') FROM ir_module_module m "
               "LEFT JOIN ir_module_category c ON c.id = m.category_id;")
        cikti = self.ortamlar.psql(o, sql, kontrol=False)
        try:
            db_moduller = json.loads(cikti.splitlines()[-1]) if cikti.strip() else []
        except ValueError:
            db_moduller = []
        satirlar = {}
        for m in db_moduller:
            satirlar[m["ad"]] = {"ad": m["ad"], "baslik": _ceviri(m.get("baslik")) or m["ad"], "durum": m.get("durum"),
                                 "kurulu": m.get("durum") == "installed", "kurulu_surum": m.get("surum"),
                                 "yazar": m.get("yazar") or "", "uygulama": bool(m.get("uygulama")),
                                 "lisans": m.get("lisans") or "", "kategori": _ceviri(m.get("kategori")) or "",
                                 "kaynak": None}
        for tur, klasor in self._ozel_klasorler(o):
            for ad, (_yol, manifest) in uyumluluk.klasor_modulleri(klasor).items():
                satir = satirlar.setdefault(ad, {"ad": ad, "baslik": manifest.get("name", ad), "durum": "listede-yok",
                                                 "kurulu": False, "kurulu_surum": None, "yazar": manifest.get("author", ""),
                                                 "uygulama": bool(manifest.get("application")),
                                                 "lisans": manifest.get("license", ""), "kategori": manifest.get("category", "")})
                satir.update(kaynak=tur, surum=manifest.get("version", ""),
                             kurulamaz=manifest.get("installable", True) is False)
        liste = sorted(satirlar.values(), key=lambda m: m["ad"])
        return {"moduller": liste, "kurulu_sayisi": sum(1 for m in liste if m["kurulu"]),
                "ozel_sayisi": sum(1 for m in liste if m.get("kaynak")), "commit": o.get("commit")}

    def _ozel_klasorler(self, o):
        klasorler = []
        if o.get("yonetim") == "panel":
            if o.get("commit") and o.get("kod"):
                klasorler.append(("depo", o["kod"]))
            if o.get("ek_addons"):
                klasorler.append(("ek", o["ek_addons"]))
        else:
            klasorler += [("ek", kaynak) for kaynak, _ in (o.get("kesif") or {}).get("kod_baglamalari", [])]
        return klasorler

    def loglar(self, odoo_id, ortam, satir=300):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        satir = max(50, min(int(satir or 300), 3000))
        sonuc = self.komut.calistir(["docker", "logs", "--tail", str(satir), "--timestamps", o["konteyner"]],
                                    kontrol=False, zaman_asimi=30)
        if not sonuc.tamam:
            raise Hata(404, "Konteyner bulunamadı ya da log okunamadı.")
        return {"satirlar": sonuc.cikti.splitlines()[-satir:], "konteyner": o["konteyner"]}
