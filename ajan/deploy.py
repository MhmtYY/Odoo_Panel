"""Deploy, geri alma ve production'a alma.

Deploy adımları (panelin yönettiği ortamda):
  1. depo çekilir, istenen commit belirlenir
  2. kod commit'e sabit klasöre çıkarılır (odoolar/<ad>/<ortam>/kod/<commit>)
  3. requirements.txt varsa Python paket katmanı (türetilmiş imaj)
  4. uyumluluk denetimi; engel varsa deploy DURUR, hiçbir şeye dokunulmaz
  5. production'da yedek (DEPLOY-ONCESI)
  6. Odoo durur, değişen ve kurulu modüller yeni kodla güncellenir (-u)
  7. konteyner yeni imaj ve kodla açılır, sağlık denetimi
  Güncelleme ya da sağlık denetimi başarısızsa: production'da veri yedekten geri yüklenir, eski kod ve imajla açılır.

Deploy kayıtları: odoolar/<ad>/<ortam>/deploylar/<no>.json
"""
import re
from datetime import datetime
from pathlib import Path

from . import kayit, pykatman, uyumluluk
from .depo import sha_denetle
from .hata import Hata

HATA_SATIRI = re.compile(r"\s(ERROR|CRITICAL)\s")


class Deploylar:
    def __init__(self, ayar, isler, ortamlar, odoolar, yedekler):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.yedekler = yedekler

    # ------------------------------------------------------------ kayıtlar
    def _dizin(self, odoo_id, ortam):
        return self.ortamlar.dizin(odoo_id, ortam) / "deploylar"

    def kayitlar(self, odoo_id, ortam, sinir=30):
        dizin = self._dizin(odoo_id, ortam)
        if not dizin.is_dir():
            return []
        yollar = sorted(dizin.glob("*.json"), reverse=True)[:sinir]
        return [kayit.oku(y) for y in yollar]

    def kayit_oku(self, odoo_id, ortam, no):
        try:
            no = int(no)
        except (TypeError, ValueError) as hata:
            raise Hata(400, "Geçersiz deploy numarası.") from hata
        d = kayit.oku(self._dizin(odoo_id, ortam) / f"{no:05d}.json")
        if not d:
            raise Hata(404, "Deploy kaydı bulunamadı.")
        return d

    def _yeni_kayit(self, o, tetik, kullanici, is_no):
        dizin = self._dizin(o["odoo"], o["ad"])
        dizin.mkdir(parents=True, exist_ok=True)
        mevcut = [int(p.stem) for p in dizin.glob("*.json") if p.stem.isdigit()]
        no = max(mevcut, default=0) + 1
        d = {"no": no, "odoo": o["odoo"], "ortam": o["ad"], "tetik": tetik, "kullanici": kullanici, "is": is_no,
             "durum": "calisiyor", "baslangic": kayit.simdi(), "onceki": {"commit": o.get("commit"),
                                                                           "imaj": o.get("imaj"), "kod": o.get("kod")}}
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

    # ------------------------------------------------------------ başlatma
    def baslat(self, odoo_id, ortam, *, commit=None, tetik="elle", kullanici=None, kuyruk=False):
        self.ayar.ortam_denetle(ortam)
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        if o.get("yonetim") != "panel":
            raise Hata(400, "Bağlanan kurulumlarda deploy yok.")
        self.odoolar.depo_gerekli(od)
        if commit:
            commit = sha_denetle(commit)
        return self.isler.baslat(
            "deploy", f"{odoo_id}/{ortam}",
            lambda b: self._deploy(b, odoo_id, ortam, commit=commit, tetik=tetik, kullanici=kullanici),
            odoo=odoo_id, ortam=ortam, kuyruk=kuyruk, agir=True, kullanici=kullanici,
            aciklama=f"Deploy {ortam}" + (f" {commit[:7]}" if commit else ""))

    # ------------------------------------------------------------ deploy
    def _deploy(self, b, odoo_id, ortam, *, commit=None, tetik="elle", kullanici=None, geri_alinan=None):
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        depo = self.odoolar.depo_gerekli(od)
        dal = od["depo"]["dallar"].get(ortam)
        if not dal:
            raise Hata(400, f"{ortam} için dal tanımlı değil.")
        d = self._yeni_kayit(o, tetik, kullanici, b.kayit["id"])
        if geri_alinan:
            d["geri_alinan"] = geri_alinan
        try:
            return self._deploy_adimlari(b, od, o, depo, dal, d, commit, tetik)
        except Exception as hata:
            if d.get("durum") == "calisiyor":
                self._bitir(d, "hata", hata=getattr(hata, "mesaj", str(hata))[:2000])
            raise

    def _deploy_adimlari(self, b, od, o, depo, dal, d, commit, tetik):
        ortam = o["ad"]
        with b.adim("Depo çekiliyor"):
            bas = depo.getir(dal)
            sha = depo.cozumle(commit) if commit else bas
            bilgi = depo.bilgi(sha)
            d.update(commit=sha, kisa=bilgi["kisa"], baslik=bilgi["baslik"], yazar=bilgi["yazar"], dal=dal,
                     dal_disi=bool(commit) and not depo.ata(sha, bas))
            self._kaydet(d)
            b.yaz(f"{bilgi['kisa']} {bilgi['baslik']} ({bilgi['yazar']})")
        if tetik == "webhook" and sha == o.get("commit"):
            self._bitir(d, "atlandi", **{"not": "Bu commit zaten yayında."})
            return {"deploy": d["no"], "_durum": "tamam", "atlandi": True}

        kod = self.ortamlar.dizin(o["odoo"], ortam) / "kod" / sha
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
            if not paketler:
                b.yaz("requirements.txt yok ya da boş; temel imaj kullanılır.")

        with b.adim("Uyumluluk denetimi") as adim:
            kurulu = self.ortamlar.kurulu_moduller(o)
            onceki = o.get("commit")
            if onceki and depo.commit_var(onceki):
                degisen = depo.degisen_moduller(onceki, sha)
            else:
                degisen = depo.moduller(sha)
            guncellenecek = sorted(degisen & kurulu)
            rapor = self.uyumluluk(o, kod, imaj, kurulu, guncellenecek)
            depodaki = set(rapor["moduller"])
            d.update(moduller=guncellenecek, yeni_moduller=sorted(depodaki - kurulu),
                     uyumluluk={"engel": len(rapor["engeller"]), "uyari": len(rapor["uyarilar"])})
            if rapor["uyarilar"]:
                d["uyarilar"] = [f"{u['modul']}: {u['neden']}" for u in rapor["uyarilar"][:10]]
            if not rapor["gecti"]:
                adim["durum"] = "engel"
                engel = uyumluluk.ozet(rapor)
                b.yaz(f"DEPLOY DURDU: {engel}")
                self._bitir(d, "durdu", engel=engel, engeller=rapor["engeller"][:20])
                return {"deploy": d["no"], "_durum": "hata", "engel": engel}
            b.yaz(f"Güncellenecek: {', '.join(guncellenecek) or 'yok'}; yeni (kurulmayacak): "
                  f"{', '.join(d['yeni_moduller']) or 'yok'}")

        yedek = None
        if ortam == "production":
            with b.adim("Yedek alınıyor"):
                yedek = self.yedekler.al(o, b, "DEPLOY-ONCESI")["dosya"]
                d["yedek"] = yedek
                self._kaydet(d)

        return self._uygula(b, o, d, imaj, kod, sha, guncellenecek, yedek)

    def _uygula(self, b, o, d, imaj, kod, sha, guncellenecek, yedek):
        """Durdur -> güncelle -> yeni kodla aç -> sağlık. Hata olursa eski hale döner."""
        eski = {"imaj": o["imaj"], "kod": o["kod"], "commit": o.get("commit")}
        veri_degisti = False
        try:
            with b.adim("Odoo durduruluyor"):
                self.ortamlar.durdur(o, b)
            if guncellenecek:
                with b.adim(f"Modüller güncelleniyor ({len(guncellenecek)})"):
                    veri_degisti = True
                    self._guncelle(b, o, guncellenecek, imaj, kod)
            with b.adim("Yeni sürüm açılıyor"):
                o.update(imaj=imaj, kod=str(kod))
                self.ortamlar.env_yaz(o, o["env"], imaj, str(kod))
                self.ortamlar.baslat(o, b)
            with b.adim("Sağlık denetimi"):
                if not self.ortamlar.saglik(o, b):
                    raise Hata(500, "Odoo yeni sürümle açılmadı (giriş sayfası yanıt vermedi).")
        except Exception as hata:
            mesaj = getattr(hata, "mesaj", str(hata))
            b.yaz(f"HATA: {mesaj}")
            notu = self._geri_don(b, o, eski, yedek if veri_degisti else None)
            self._bitir(d, "hata", hata=mesaj[:2000], **{"not": notu})
            return {"deploy": d["no"], "_durum": "hata", "hata": mesaj, "not": notu}

        gecmis = [sha] + [c for c in o.get("kod_gecmisi", []) if c != sha]
        o.update(commit=sha, kod_gecmisi=gecmis[:10], son_deploy=d["no"], son_deploy_tarih=kayit.simdi())
        o.pop("bekleyen", None)
        self.ortamlar.yaz(o)
        self.ortamlar.kod_temizle(o)
        durum = "uyari" if d.get("uyarilar") else "tamam"
        self._bitir(d, durum)
        return {"deploy": d["no"], "commit": sha, "moduller": guncellenecek}

    def _guncelle(self, b, o, moduller, imaj, kod):
        hatalar = []

        def log(satir):
            b.yaz(satir)
            if HATA_SATIRI.search(satir) and len(hatalar) < 20:
                hatalar.append(satir.strip()[:400])

        sonuc = self.ortamlar.odoo_tek(o, b, ["-u", ",".join(moduller), "--stop-after-init", "--no-http"],
                                       imaj=imaj, kod=str(kod), log=log, kontrol=False)
        bekleyen = self.ortamlar.psql(o, "SELECT name || ':' || state FROM ir_module_module "
                                         "WHERE state IN ('to upgrade', 'to install', 'to remove');", kontrol=False)
        if sonuc.kod != 0 or hatalar or bekleyen.strip():
            neden = (hatalar[0] if hatalar else (f"bekleyen modül: {bekleyen.strip()[:200]}" if bekleyen.strip()
                                                  else f"çıkış kodu {sonuc.kod}"))
            raise Hata(500, f"Modül güncellemesi başarısız: {neden}")

    def _geri_don(self, b, o, eski, yedek):
        """Hata sonrası: veri değiştiyse yedekten geri yükler, eski kod ve imajla açar."""
        notlar = []
        try:
            with b.adim("Önceki sürüme dönülüyor"):
                o.update(imaj=eski["imaj"], kod=eski["kod"])
                self.ortamlar.env_yaz(o, o["env"], eski["imaj"], eski["kod"])
                if yedek:
                    self.yedekler.geri_yukle(o, b, self.yedekler.yol(o["odoo"], o["ad"], yedek), guvenlik_yedegi=False)
                    notlar.append("Veritabanı deploy öncesi yedekten geri yüklendi.")
                elif o["ad"] == "staging":
                    notlar.append("Staging verisi yarım güncellenmiş olabilir; gerekirse production'dan yenileyin.")
                self.ortamlar.baslat(o, b)
                if self.ortamlar.saglik(o, b):
                    notlar.insert(0, "Önceki sürüme dönüldü.")
                else:
                    notlar.insert(0, "DİKKAT: önceki sürüm de açılmadı, elle bakılmalı.")
        except Exception as hata:  # noqa: BLE001 - not olarak kaydedilir
            notlar.insert(0, f"DİKKAT: önceki sürüme dönülemedi: {getattr(hata, 'mesaj', hata)}")
        self.ortamlar.yaz(o)
        return " ".join(notlar)

    # ------------------------------------------------------------ uyumluluk
    def uyumluluk(self, o, kod, imaj, kurulu=None, guncellenecek=()):
        imaj_bilgi = self.ortamlar.imaj_bilgisi(imaj)
        depo_moduller = uyumluluk.klasor_modulleri(kod)
        ek_moduller = uyumluluk.klasor_modulleri(o.get("ek_addons") or "")
        kurulu = self.ortamlar.kurulu_moduller(o) if kurulu is None else kurulu
        python_var = self.ortamlar.python_denetle(imaj, uyumluluk.python_adlari(depo_moduller))
        return uyumluluk.denetle(depo_moduller, seri=imaj_bilgi["seri"],
                                 mevcut=set(imaj_bilgi["moduller"]) | set(ek_moduller), kurulu=kurulu,
                                 guncellenecek=guncellenecek, python_var=python_var,
                                 imaj_moduller=set(imaj_bilgi["moduller"]))

    def uyumluluk_isi(self, odoo_id, ortam, kullanici=None):
        """Dalın son commit'ini deploy etmeden denetler."""
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        depo = self.odoolar.depo_gerekli(od)

        def isle(b):
            with b.adim("Depo çekiliyor"):
                sha = depo.getir(od["depo"]["dallar"][ortam])
            kod = self.ortamlar.dizin(odoo_id, ortam) / "kod" / sha
            with b.adim("Kod hazırlanıyor"):
                if not (kod / ".hazir").exists():
                    depo.cikar(sha, kod)
                    (kod / ".hazir").write_text(kayit.simdi(), encoding="utf-8")
            with b.adim("Denetim"):
                gereksinim = kod / "requirements.txt"
                paketler = pykatman.gereksinimleri_temizle(
                    gereksinim.read_text(encoding="utf-8") if gereksinim.exists() else "")
                imaj = o["imaj_temel"]
                rapor = self.uyumluluk(o, kod, imaj)
                if paketler:
                    # paket katmanı derlenince gelecek paketler imajda yok sayılmaz
                    # paket adı çoğu zaman içe aktarma adıyla aynıdır (değilse uyarı kalır, deploy'da kesinleşir)
                    adlar = {re.split(r"[\[<>=!~;\s]", p, maxsplit=1)[0].lower().replace("-", "_") for p in paketler}
                    for liste in (rapor["engeller"], rapor["uyarilar"]):
                        liste[:] = [e for e in liste if not (e["neden"].startswith("Python paketi imajda yok:")
                                                             and e["neden"].split(":")[1].strip().lower() in adlar)]
                    rapor["gecti"] = not rapor["engeller"]
                    rapor["paketler"] = paketler
            rapor.update(commit=sha, _durum="tamam")
            return rapor

        return self.isler.baslat("uyumluluk", f"{odoo_id}/{ortam}", isle, odoo=odoo_id, ortam=ortam,
                                 kullanici=kullanici, aciklama="Uyumluluk denetimi")

    # ------------------------------------------------------------ geri alma
    def geri_al(self, odoo_id, ortam, no, kip, kullanici=None):
        """no numaralı deploy'u geri alır.
        kip "kod"      : deploy'dan önceki commit yeniden deploy edilir (değişen modüller eski kodla güncellenir)
        kip "kod-veri" : deploy öncesi yedek geri yüklenir ve önceki kodla açılır (sonradan girilen veri gider)
        """
        self.ayar.ortam_denetle(ortam)
        d = self.kayit_oku(odoo_id, ortam, no)
        onceki = d.get("onceki") or {}
        if d.get("durum") not in ("tamam", "uyari"):
            raise Hata(400, "Yalnız başarılı deploy geri alınır.")
        if not onceki.get("commit"):
            raise Hata(400, "Bu deploy'dan önce yayında commit yok; geri alınacak sürüm yok.")
        if kip == "kod":
            od = self.odoolar.gerekli(odoo_id)
            self.odoolar.depo_gerekli(od)
            return self.isler.baslat(
                "geri-al", f"{odoo_id}/{ortam}",
                lambda b: self._deploy(b, odoo_id, ortam, commit=onceki["commit"], tetik="geri", kullanici=kullanici,
                                       geri_alinan=d["no"]),
                odoo=odoo_id, ortam=ortam, agir=True, kullanici=kullanici, aciklama=f"Deploy #{d['no']} geri (kod)")
        if kip == "kod-veri":
            if not d.get("yedek"):
                raise Hata(400, "Bu deploy'un öncesinde yedek yok (staging'de deploy öncesi yedek alınmaz).")
            yol = self.yedekler.yol(odoo_id, ortam, d["yedek"])
            return self.isler.baslat(
                "geri-al", f"{odoo_id}/{ortam}", lambda b: self._kod_veri_geri(b, odoo_id, ortam, d, yol, kullanici),
                odoo=odoo_id, ortam=ortam, agir=True, kullanici=kullanici,
                aciklama=f"Deploy #{d['no']} geri (kod + veri)")
        raise Hata(400, "Geri alma kipi kod ya da kod-veri olmalı.")

    def _kod_veri_geri(self, b, odoo_id, ortam, d, yol, kullanici):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        onceki = d["onceki"]
        yeni = self._yeni_kayit(o, "geri", kullanici, b.kayit["id"])
        yeni.update(commit=onceki["commit"], kisa=onceki["commit"][:7], geri_alinan=d["no"], imaj=onceki["imaj"],
                    baslik=f"Deploy #{d['no']} geri alındı (kod + veri)")
        kod = Path(onceki["kod"])
        if not (kod / ".hazir").exists():
            depo = self.odoolar.depo_gerekli(self.odoolar.gerekli(odoo_id))
            with b.adim("Önceki kod hazırlanıyor"):
                depo.getir(d.get("dal") or "main")
                depo.cikar(onceki["commit"], kod)
                (kod / ".hazir").write_text(kayit.simdi(), encoding="utf-8")
        try:
            with b.adim("Şimdiki halin yedeği"):
                yeni["yedek"] = self.yedekler.al(o, b, "GERI-ALMA-ONCESI")["dosya"]
            self.yedekler.geri_yukle(o, b, yol, guvenlik_yedegi=False)
            with b.adim("Önceki sürüm açılıyor"):
                o.update(imaj=onceki["imaj"], kod=str(kod))
                self.ortamlar.env_yaz(o, o["env"], onceki["imaj"], str(kod))
                self.ortamlar.baslat(o, b)
            with b.adim("Sağlık denetimi"):
                if not self.ortamlar.saglik(o, b):
                    raise Hata(500, "Odoo geri alınan sürümle açılmadı.")
        except Exception as hata:
            self._bitir(yeni, "hata", hata=getattr(hata, "mesaj", str(hata))[:2000],
                        **{"not": f"Geri alma öncesi yedek: {yeni.get('yedek') or 'alınamadı'}"})
            raise
        gecmis = [onceki["commit"]] + [c for c in o.get("kod_gecmisi", []) if c != onceki["commit"]]
        o.update(commit=onceki["commit"], kod_gecmisi=gecmis[:10], son_deploy=yeni["no"])
        self.ortamlar.yaz(o)
        self._bitir(yeni, "tamam")
        return {"deploy": yeni["no"], "commit": onceki["commit"]}

    # ------------------------------------------------------------ production'a al
    def production_al(self, odoo_id, github, kullanici=None):
        """Staging'de yayındaki commit production'a geçer.
        GitHub App varsa staging commit'i production dalına birleştirilir (dal gerçeği korunur), sonra dalın son hali
        deploy edilir. App yoksa commit sabitlenerek deploy edilir (dal ile yayın farklı kalır, kayda yazılır).
        """
        od = self.odoolar.gerekli(odoo_id)
        st = self.ortamlar.gerekli(odoo_id, "staging")
        if not st.get("commit"):
            raise Hata(400, "Staging'de henüz deploy edilmiş commit yok.")
        bilgi = od.get("depo") or {}
        sha = st["commit"]

        def isle(b):
            commit = None
            if bilgi.get("baglanti") == "app" and github.app_var():
                with b.adim("Staging commit'i production dalına birleştiriliyor"):
                    birlesik = github.birlestir(bilgi["ad"], bilgi["dallar"]["production"], sha,
                                                f"Production'a alındı: staging {sha[:7]} (Odoo Yönetim Paneli)")
                    b.yaz(f"Birleştirme commit'i: {birlesik[:7]}" if birlesik else "Production dalı zaten içeriyor.")
            else:
                commit = sha
                b.uyari("Depo App ile bağlı değil; commit production dalına birleştirilmeden yayına alındı.")
            return self._deploy(b, odoo_id, "production", commit=commit, tetik="elle", kullanici=kullanici)

        return self.isler.baslat("production-al", f"{odoo_id}/production", isle, odoo=odoo_id, ortam="production",
                                 agir=True, kullanici=kullanici, aciklama=f"Staging {sha[:7]} production'a")

    def onde(self, odoo_id):
        """Staging'de olup production'da olmayan commit'ler."""
        od = self.odoolar.gerekli(odoo_id)
        depo = self.odoolar.depo(od)
        st = self.ortamlar.oku(odoo_id, "staging")
        pr = self.ortamlar.oku(odoo_id, "production")
        if not depo or not st or not st.get("commit"):
            return []
        if not pr or not pr.get("commit"):
            return depo.aradaki(None, st["commit"], 30)
        if not depo.commit_var(pr["commit"]) or not depo.commit_var(st["commit"]):
            return []
        return depo.aradaki(pr["commit"], st["commit"], 30)
