"""Ortam provası (Merkezi güncelleme, Aşama 2): bir commit'i ortama uygulamadan önce ortamın verisinin geçici
kopyasında dener.

Adımlar (panelin yönettiği ortamda, ortamın kendi sunucusunda):
  1. depo çekilir, kod commit'e sabit klasöre çıkar (deploy aynı klasörü kullanır), Python katmanı, uyumluluk
  2. veri: ortamın 24 saatten yeni ve aynı commit'teki yedeği; yoksa taze döküm. Geçici veritabanı
     <db>_prova'ya açılır. Dosya deposu kopyalanmaz, HTTP açılmaz, kalıcı konteyner kurulmaz.
  3. nötrleştirme (Odoo neutralize + staging'deki Vekosis eki)
  4. muhasebe değişmezleri "önce" (ajan/degismez.py)
  5. yeni kodla değişen ve kurulu modüller -u (deploy'un güncelleyeceği küme)
  6. teknik denetim (çıkış kodu, ERROR/CRITICAL, bekleyen modül, kurulu sürüm = kod sürümü, çalışan göç betikleri)
  7. muhasebe değişmezleri "sonra" ve karşılaştırma; yayın notundaki beklenen değişiklikler provayı düşürmez
  8. geçici veritabanı ve yapılandırma silinir; kayıtta yalnız sayılar ve geçti/düştü kalır
Aynı sunucuda aynı anda tek prova koşar (iş anahtarı "sunucu/prova").

Kayıtlar: odoolar/<ad>/<ortam>/provalar/<no>.json
Deploy kapısı: Odoo kaydında prova_zorunlu açıksa production deploy'u, aynı commit ve aynı başlangıç sürümü için
48 saat içinde geçmiş bir prova ister (deploy.py). Staging kapıya bağlı değildir (deneme alanı, push'la güncellenir).

Belge çıktısı ve duman senaryoları (ajan/duman.py): nötrleştirmeden sonra eski kodla, güncellemeden sonra yeni kodla
"odoo shell" içinde çalışır; UBL-TR XML'leri (değer özetleri, şema denetimi) ve geri alınan senaryo sonuçları
karşılaştırılır.
"""
import ast
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from . import degismez, duman, kayit, pykatman, uyumluluk
from .deploy import HATA_SATIRI
from .depo import sha_denetle
from .hata import Hata
from .ortam import conf_metni, conf_oku
from .staging import DENETIM_SQL, ek_notr_sql

ANAHTAR = "sunucu/prova"
XSD_DIZINI = Path(__file__).resolve().parent / "veri" / "ubltr_xsd"  # GİB UBL-TR 1.2.1 paketi, xsdrt
BELGE_SINIRI = 10
YEDEK_YASI = timedelta(hours=24)
GECERLILIK = timedelta(hours=48)
GOC_SATIRI = re.compile(r"(?:module ([\w.]+): )?Running migration \[?([^\]\s>]+)>?\]?\s+(\S+)")
# ortam conf'undan provaya taşınmayan ya da üzerine yazılan seçenekler
CONF_EZ = {"workers": "0", "max_cron_threads": "0", "list_db": "False", "data_dir": "/var/lib/odoo",
           "proxy_mode": "False"}
CONF_SIL = {"logfile", "pidfile", "http_port", "gevent_port", "longpolling_port", "db_maxconn", "limit_time_real",
            "limit_time_cpu", "limit_request", "limit_memory_soft", "limit_memory_hard"}


class Provalar:
    def __init__(self, ayar, isler, ortamlar, odoolar, yedekler, deploylar):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.yedekler = yedekler
        self.deploylar = deploylar

    # ------------------------------------------------------------ kayıtlar
    def _dizin(self, odoo_id, ortam):
        return self.ortamlar.dizin(odoo_id, ortam) / "provalar"

    def kayitlar(self, odoo_id, ortam, sinir=30):
        dizin = self._dizin(odoo_id, ortam)
        if not dizin.is_dir():
            return []
        return [kayit.oku(y) for y in sorted(dizin.glob("*.json"), reverse=True)[:sinir]]

    def kayit_oku(self, odoo_id, ortam, no):
        try:
            no = int(no)
        except (TypeError, ValueError) as hata:
            raise Hata(400, "Geçersiz prova numarası.") from hata
        d = kayit.oku(self._dizin(odoo_id, ortam) / f"{no:05d}.json")
        if not d:
            raise Hata(404, "Prova kaydı bulunamadı.")
        return d

    def gecen(self, odoo_id, ortam, sha, taban):
        """sha için, ortam taban commit'teyken geçmiş ve süresi dolmamış son prova (yoksa None)."""
        sinir = (datetime.now() - GECERLILIK).isoformat(timespec="seconds")
        for d in self.kayitlar(odoo_id, ortam, sinir=100):
            if (d.get("commit") == sha and d.get("taban_commit") == taban and d.get("durum") == "gecti"
                    and (d.get("bitis") or "") >= sinir):
                return d
        return None

    def _yeni_kayit(self, o, tetik, kullanici, is_no):
        dizin = self._dizin(o["odoo"], o["ad"])
        dizin.mkdir(parents=True, exist_ok=True)
        no = max((int(p.stem) for p in dizin.glob("*.json") if p.stem.isdigit()), default=0) + 1
        d = {"no": no, "odoo": o["odoo"], "ortam": o["ad"], "tetik": tetik, "kullanici": kullanici, "is": is_no,
             "durum": "calisiyor", "baslangic": kayit.simdi(), "taban_commit": o.get("commit"), "imaj_once": o.get("imaj")}
        self._kaydet(d)
        return d

    def _kaydet(self, d):
        kayit.yaz(self._dizin(d["odoo"], d["ortam"]) / f"{d['no']:05d}.json", d)

    def _bitir(self, d, durum, **ek):
        d.update(ek)
        d["durum"] = durum
        d["bitis"] = kayit.simdi()
        d["sure"] = round((datetime.fromisoformat(d["bitis"]) - datetime.fromisoformat(d["baslangic"])).total_seconds())
        self._kaydet(d)
        return d

    # ------------------------------------------------------------ ayar
    def ayar_yaz(self, odoo_id, govde):
        od = self.odoolar.gerekli(odoo_id)
        od["prova_zorunlu"] = bool((govde or {}).get("zorunlu"))
        self.odoolar.yaz(od)
        return {"prova_zorunlu": od["prova_zorunlu"]}

    # ------------------------------------------------------------ başlatma
    def baslat(self, odoo_id, ortam, *, commit=None, tetik="elle", kullanici=None):
        self.ayar.ortam_denetle(ortam)
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        if o.get("yonetim") != "panel":
            raise Hata(400, "Prova yalnız panelin yönettiği ortamlarda var (bağlanan kurulum önce devralınmalı).")
        self.odoolar.depo_gerekli(od)
        if commit:
            commit = sha_denetle(commit)
        return self.isler.baslat(
            "prova", ANAHTAR,
            lambda b: self._prova(b, odoo_id, ortam, commit=commit, tetik=tetik, kullanici=kullanici),
            odoo=odoo_id, ortam=ortam, agir=True, kullanici=kullanici,
            aciklama=f"Prova {odoo_id}/{ortam}" + (f" {commit[:7]}" if commit else ""))

    # ------------------------------------------------------------ prova
    def _prova(self, b, odoo_id, ortam, *, commit=None, tetik="elle", kullanici=None):
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        depo = self.odoolar.depo_gerekli(od)
        dal = od["depo"]["dallar"].get(ortam)
        if not dal:
            raise Hata(400, f"{ortam} için dal tanımlı değil.")
        d = self._yeni_kayit(o, tetik, kullanici, b.kayit["id"])
        try:
            return self._adimlar(b, o, depo, dal, d, commit)
        except Exception as hata:
            if d.get("durum") == "calisiyor":
                self._bitir(d, "hata", hata=getattr(hata, "mesaj", str(hata))[:2000])
            raise

    def _adimlar(self, b, o, depo, dal, d, commit):
        with b.adim("Depo çekiliyor"):
            bas = depo.getir(dal)
            sha = depo.cozumle(commit) if commit else bas
            bilgi = depo.bilgi(sha)
            d.update(commit=sha, kisa=bilgi["kisa"], baslik=bilgi["baslik"], dal=dal)
            self._kaydet(d)
            b.yaz(f"{bilgi['kisa']} {bilgi['baslik']} (başlangıç: {(o.get('commit') or 'yok')[:7]})")

        kod = self.ortamlar.dizin(o["odoo"], o["ad"]) / "kod" / sha
        with b.adim("Kod hazırlanıyor"):
            if not (kod / ".hazir").exists():
                depo.cikar(sha, kod)
                (kod / ".hazir").write_text(kayit.simdi(), encoding="utf-8")

        with b.adim("Python paketleri"):
            gereksinim = kod / "requirements.txt"
            imaj, paketler = pykatman.imaj_hazirla(self.ortamlar, b, o["imaj_temel"],
                                                   gereksinim.read_text(encoding="utf-8") if gereksinim.exists() else "",
                                                   o["odoo"])
            d.update(imaj=imaj, paketler=paketler)

        with b.adim("Uyumluluk denetimi") as adim:
            kurulu = self.ortamlar.kurulu_moduller(o)
            onceki = o.get("commit")
            degisen = depo.degisen_moduller(onceki, sha) if onceki and depo.commit_var(onceki) else depo.moduller(sha)
            guncellenecek = sorted(degisen & kurulu)
            rapor = self.deploylar.uyumluluk(o, kod, imaj, kurulu, guncellenecek)
            d.update(moduller=guncellenecek, yeni_moduller=sorted(set(rapor["moduller"]) - kurulu),
                     uyumluluk={"engel": len(rapor["engeller"]), "uyari": len(rapor["uyarilar"])})
            if not rapor["gecti"]:
                adim["durum"] = "engel"
                engel = uyumluluk.ozet(rapor)
                b.yaz(f"PROVA DURDU: {engel}")
                self._bitir(d, "durdu", engel=engel, engeller=rapor["engeller"][:20])
                return {"prova": d["no"], "_durum": "hata", "durum": "durdu", "hata": f"Prova durdu: {engel}"}
            b.yaz(f"Güncellenecek: {', '.join(guncellenecek) or 'yok'}")

        if not guncellenecek:
            self._bitir(d, "gecti", **{"not": "Güncellenecek kurulu modül yok; veri provası gerekmedi."})
            return {"prova": d["no"], "durum": "gecti", "moduller": []}

        self.ortamlar.bellek_denetle(self.ayar.ortam_bellek_mb)
        p = self._prova_ortami(o)
        gecici = Path(tempfile.mkdtemp(prefix=".prova-", dir=self._gecici()))
        try:
            self._veri_hazirla(b, o, p, d)
            p["prova_conf"] = str(self._conf_yaz(o, p, gecici))
            with b.adim("Nötrleştiriliyor"):
                d["notr"] = self._notrlestir(b, p, imaj, kod)
            with b.adim("Belge çıktısı ve duman senaryoları (eski kod)"):
                eski_duman = self._duman(b, p, o["imaj"], o["kod"])
            psql = lambda sql: self.ortamlar.psql(p, sql, b=b)  # noqa: E731
            with b.adim("Muhasebe değişmezleri (önce)"):
                once = degismez.olc(psql)
                b.yaz(f"{len(once)} denetim")
            with b.adim(f"Modüller güncelleniyor ({len(guncellenecek)})") as adim:
                teknik = self._guncelle(b, p, imaj, kod, guncellenecek)
                d["teknik"] = teknik
                if teknik["hatalar"]:
                    adim["durum"] = "hata"
            with b.adim("Muhasebe değişmezleri (sonra)"):
                sonra = degismez.olc(psql)
            with b.adim("Belge çıktısı ve duman senaryoları (yeni kod)"):
                yeni_duman = self._duman(b, p, imaj, kod)
            with b.adim("Belge ve duman karşılaştırması") as adim:
                d["belge_duman"] = self._duman_karsilastir(b, eski_duman, yeni_duman, self._yayin_notu(kod))
                if d["belge_duman"]["durum"] == "dustu":
                    adim["durum"] = "hata"
            with b.adim("Karşılaştırma") as adim:
                izinli = degismez.beklenen_farklar(self._yayin_notu(kod))
                sonuc = degismez.karsilastir(once, sonra, izinli)
                d["degismez"] = {**sonuc, "farklar": sonuc["farklar"][:50], "izinli": izinli}
                for fark in sonuc["farklar"][:20]:
                    b.yaz(f"FARK {fark['anahtar']}: {fark['once']} -> {fark['sonra']}")
                if sonuc["izinli_farklar"]:
                    b.yaz(f"Yayın notunda beklenen {len(sonuc['izinli_farklar'])} fark")
                if not sonuc["gecti"]:
                    adim["durum"] = "hata"
        finally:
            with b.adim("Geçici veritabanı siliniyor"):
                try:
                    self.ortamlar.db_sil(p, b)
                except Exception as hata:  # noqa: BLE001 - kayda yazılır, prova sonucu değişmez
                    b.uyari(f"Geçici veritabanı silinemedi ({p['db_adi']}): {getattr(hata, 'mesaj', hata)}")
                shutil.rmtree(gecici, ignore_errors=True)

        nedenler = list(d["teknik"]["hatalar"][:5])
        if not d["degismez"]["gecti"]:
            nedenler.append(f"muhasebe değişmezinde {len(d['degismez']['farklar'])} fark "
                            f"(ilki {d['degismez']['farklar'][0]['anahtar']})")
        nedenler += d["belge_duman"].get("nedenler", [])
        if nedenler:
            self._bitir(d, "dustu", neden=nedenler)
            ek = f" (ve {len(nedenler) - 1} neden daha)" if len(nedenler) > 1 else ""
            return {"prova": d["no"], "_durum": "hata", "durum": "dustu", "neden": nedenler,
                    "hata": f"Prova düştü: {nedenler[0]}{ek}"}
        self._bitir(d, "gecti")
        return {"prova": d["no"], "durum": "gecti", "moduller": guncellenecek,
                "denetim": d["degismez"]["kontrol"]}

    # ------------------------------------------------------------ yardımcılar
    def _gecici(self):
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        return self.ayar.gecici

    def _prova_ortami(self, o):
        p = dict(o)
        p.update(ad=f"{o['ad']}-prova", db_adi=f"{o['db_adi']}_prova")
        return p

    def _veri_hazirla(self, b, o, p, d):
        """Geçici veritabanını ortamın verisiyle doldurur: uygun yedek varsa ondan, yoksa taze dökümden."""
        if self.ortamlar.db_var(p["db_konteyner"], p["db_su"], p["db_adi"]):
            b.yaz(f"Önceki provadan kalan {p['db_adi']} siliniyor")
            self.ortamlar.db_sil(p, b)
        yedek = self._uygun_yedek(o)
        with b.adim("Veri hazırlanıyor"):
            self.ortamlar.db_olustur(p, b)
            if yedek:
                with self.yedekler.ac(self.yedekler.yol(o["odoo"], o["ad"], yedek["dosya"])) as (klasor, _meta):
                    sayi = self.ortamlar.dokum_yukle(p, b, klasor / "veritabani.dump")
                d["veri"] = {"tur": "yedek", "dosya": yedek["dosya"], "tarih": yedek["tarih"]}
            else:
                dokum = self._gecici() / f"prova-{uuid.uuid4().hex}.dump"
                try:
                    self.ortamlar.dokum_al(o, b, dokum)
                    sayi = self.ortamlar.dokum_yukle(p, b, dokum)
                finally:
                    dokum.unlink(missing_ok=True)
                d["veri"] = {"tur": "dokum", "tarih": kayit.simdi()}
            d["veri"]["modul_sayisi"] = sayi
            b.yaz(f"Veri: {d['veri']['tur']} ({sayi} kurulu modül)")
            self._kaydet(d)

    def _uygun_yedek(self, o):
        sinir = (datetime.now() - YEDEK_YASI).isoformat(timespec="seconds")
        for y in self.yedekler.liste(o["odoo"], o["ad"]):
            if y["tarih"] < sinir:
                break
            if y.get("commit") == o.get("commit"):
                return y
        return None

    def _conf_yaz(self, o, p, klasor):
        try:
            secenekler = conf_oku(Path(o["conf"]).read_text(encoding="utf-8"))
        except (OSError, KeyError) as hata:
            raise Hata(500, f"Ortamın odoo.conf dosyası okunamadı: {hata}") from hata
        for anahtar in CONF_SIL:
            secenekler.pop(anahtar, None)
        secenekler.update(CONF_EZ)
        secenekler.update(db_name=p["db_adi"], dbfilter=f"^{p['db_adi']}$")
        self.ortamlar.komut.gizle(*(v for k, v in secenekler.items() if k in ("db_password", "admin_passwd") and v))
        yol = Path(klasor) / "odoo.conf"
        yol.write_text(conf_metni(secenekler), encoding="utf-8")
        yol.chmod(0o644)
        return yol

    def _odoo(self, b, p, imaj, kod, odoo_args, alt_komut=None, log=None, girdi=None):
        """Geçici veritabanında tek seferlik Odoo: verilen imaj ve kod, ayrı yapılandırma, bellekte data_dir."""
        args = ["docker", "run", "--rm"] + (["-i"] if girdi is not None else []) + [
                "--network", self.ayar.ag, "--memory", self.ayar.ortam_bellek_siniri,
                "--cpus", self.ayar.ortam_cpu, "-e", "TZ=Europe/Istanbul", "-e", "PYTHONUTF8=1",
                "--label", "vekosis.panel.prova=1", "--tmpfs", "/var/lib/odoo:rw,mode=1777",
                "-v", f"{p['prova_conf']}:/etc/odoo/odoo.conf:ro", "-v", f"{kod}:/mnt/repo:ro"]
        if p.get("ek_addons") and Path(p["ek_addons"]).is_dir():
            args += ["-v", f"{p['ek_addons']}:/mnt/extra-addons:ro"]
        if XSD_DIZINI.is_dir():
            args += ["-v", f"{XSD_DIZINI}:/mnt/ubltr-xsd:ro"]
        args += [imaj, "odoo"] + ([alt_komut] if alt_komut else []) + ["-c", "/etc/odoo/odoo.conf", "-d", p["db_adi"]]
        kw = {"girdi": girdi} if girdi is not None else {}
        return b.komut(args + list(odoo_args), log=log, kontrol=False, zaman_asimi=3600, **kw)

    def _duman(self, b, p, imaj, kod):
        """Belge çıktısı ve duman senaryoları (ajan/duman.py) verilen kodla; sonuç sözlüğü ya da None."""
        def log(satir):
            if not satir.startswith(duman.IM):  # sonuç satırı (özetler) günlüğe yazılmaz
                b.yaz(satir)

        betik = duman.betik(datetime.now().date(), BELGE_SINIRI, duman.XSD_YOLU if XSD_DIZINI.is_dir() else "")
        sonuc = self._odoo(b, p, imaj, kod, [], alt_komut="shell", log=log, girdi=betik)
        olcum = duman.cozumle(sonuc.cikti)
        if olcum is None:
            b.uyari(f"Belge ve duman ölçümü sonuç vermedi (çıkış kodu {sonuc.kod}).")
        else:
            b.yaz(f"{len(olcum.get('ubl') or {})} belge, {len(olcum.get('duman') or {})} senaryo")
        return olcum

    def _duman_karsilastir(self, b, eski, yeni, notu):
        if eski is None and yeni is None:
            return {"durum": "olculemedi", "nedenler": []}
        if yeni is None:
            return {"durum": "dustu", "nedenler": ["yeni kodla belge ve duman ölçümü çalışmadı (eski kodla çalışıyordu)"]}
        if eski is None:
            b.uyari("Eski kodla belge ve duman ölçülemedi; yalnız yeni kodun sonucu kaydedildi.")
            return {"durum": "olculemedi", "nedenler": [], "notlar": yeni.get("notlar")}
        sonuc = duman.karsilastir(eski, yeni, duman.beklenen_belge(notu), degismez.beklenen_farklar(notu))
        nedenler = []
        belge = sonuc["belge"]
        if belge["beklenmeyen"]:
            ogeler = ", ".join(f"{ad} ({n})" for ad, n in sorted(belge["beklenmeyen"].items())[:8])
            nedenler.append(f"UBL'de yayın notunda bildirilmemiş değişiklik: {ogeler}")
        if belge["hata_farki"]:
            ilk = belge["hata_farki"][0]
            nedenler.append(f"{len(belge['hata_farki'])} belgede üretim sonucu değişti (ilki: {ilk['once']} -> {ilk['sonra']})")
        if belge["gecersiz_yeni"]:
            nedenler.append(f"{len(belge['gecersiz_yeni'])} belge yeni kodla UBL-TR şemasına uymuyor "
                            f"({belge['gecersiz_yeni'][0].get('hata')})")
        if sonuc["duman"]["farklar"]:
            nedenler.append("duman senaryosu farklı: " + ", ".join(f["senaryo"] for f in sonuc["duman"]["farklar"]))
        for satir in nedenler:
            b.yaz(f"FARK {satir}")
        if belge["uretilemeyen"]:
            b.uyari(f"{sum(belge['uretilemeyen'].values())} belge iki kodda da üretilemedi, karşılaştırılamadı: "
                    + "; ".join(belge["uretilemeyen"])[:300])
        b.yaz(f"Belge: {belge['sayi']} ({belge['farkli']} farklı, öğeler {belge['ogeler']}); "
              f"duman: {sonuc['duman']['senaryolar']}")
        return {"durum": "gecti" if sonuc["gecti"] else "dustu", "nedenler": nedenler, "belge": belge,
                "duman": {**sonuc["duman"], "farklar": sonuc["duman"]["farklar"][:10]}, "notlar": sonuc["notlar"]}

    def _notrlestir(self, b, p, imaj, kod):
        sonuc = self._odoo(b, p, imaj, kod, [], alt_komut="neutralize")
        if sonuc.kod != 0:
            raise Hata(500, "Nötrleştirme başarısız (odoo neutralize).")
        self.ortamlar.psql(p, ek_notr_sql(), b=b)
        durum = {}
        for satir in self.ortamlar.psql(p, DENETIM_SQL, b=b).splitlines():
            anahtar, _, deger = satir.partition("=")
            durum[anahtar.strip()] = deger.strip()
        if durum.get("notr") != "True":
            raise Hata(500, "Nötrleştirme doğrulanamadı (database.is_neutralized yok).")
        return {"cron": durum.get("cron"), "posta": durum.get("posta")}

    def _guncelle(self, b, p, imaj, kod, moduller):
        hatalar, goc = [], []

        def log(satir):
            b.yaz(satir)
            if HATA_SATIRI.search(satir) and len(hatalar) < 20:
                hatalar.append(satir.strip()[:400])
            eslesme = GOC_SATIRI.search(satir)
            if eslesme and len(goc) < 50:
                goc.append(" ".join(x for x in (eslesme.group(1), eslesme.group(2), Path(eslesme.group(3)).name) if x))

        sonuc = self._odoo(b, p, imaj, kod, ["-u", ",".join(moduller), "--stop-after-init", "--no-http"], log=log)
        if sonuc.kod != 0 and not hatalar:
            hatalar.append(f"çıkış kodu {sonuc.kod}")
        bekleyen = self.ortamlar.psql(p, "SELECT name || ':' || state FROM ir_module_module "
                                         "WHERE state IN ('to upgrade', 'to install', 'to remove');", kontrol=False)
        if bekleyen.strip():
            hatalar.append(f"bekleyen modül: {bekleyen.strip()[:200]}")
        surumler = self._surum_denetimi(p, kod, moduller)
        hatalar += [f"{m}: kurulu sürüm {k}, kodda {c}" for m, k, c in surumler]
        return {"cikis": sonuc.kod, "hatalar": hatalar, "goc": goc}

    def _surum_denetimi(self, p, kod, moduller):
        """-u'dan sonra kurulu sürüm koddaki sürüme eşit olmalı (eşit değilse modül güncellenmemiştir)."""
        cikti = self.ortamlar.psql(p, "SELECT name || '|' || coalesce(latest_version, '') FROM ir_module_module "
                                      "WHERE state = 'installed';", kontrol=False)
        kurulu = dict(s.split("|", 1) for s in cikti.splitlines() if "|" in s)
        seri = ".".join((kurulu.get("base") or "").split(".")[:2])  # Odoo serisi, örnek 20.0
        uyumsuz = []
        for m in moduller:
            kodda = _manifest_surumu(Path(kod) / m / "__manifest__.py")
            if not kodda or not kurulu.get(m):
                continue
            # Odoo seri ile başlamayan sürümün başına seriyi ekler (odoo.modules.module.adapt_version)
            beklenen = kodda if not seri or kodda.startswith(seri + ".") else f"{seri}.{kodda}"
            if kurulu[m] != beklenen:
                uyumsuz.append((m, kurulu[m], beklenen))
        return uyumsuz

    @staticmethod
    def _yayin_notu(kod):
        yol = Path(kod) / "YAYIN_NOTU.md"
        try:
            return yol.read_text(encoding="utf-8")
        except OSError:
            return ""


def _manifest_surumu(yol):
    try:
        return str(ast.literal_eval(Path(yol).read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError, SyntaxError):
        return ""
