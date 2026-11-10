"""Yeni Odoo kurma ve mevcut kurulumu panele bağlama.

Yeni Odoo (panelin yönettiği production ortamı):
  bos     boş veritabanı: base + Türkçe
  sablon  test platformunun geçerli tam şablonu kopyalanır (eski platformun yeni-musteri.sh'iyle aynı yöntem);
          örnek veri isteğe bağlı yenilenir ya da silinir
Bağlama: konteyner incelenir (imaj, odoo.conf, veritabanı, dosya deposu birimi, adres). Hiçbir şey yeniden
başlatılmaz, compose dosyasına dokunulmaz.
"""
import json
import re
import shutil
from pathlib import Path

from . import kayit
from .hata import Hata
from .ortam import conf_oku, yeni_sifre

KISISEL = r"""
import json, uuid
from odoo import fields
A = json.loads(%(ayar)r)
P = env['ir.config_parameter'].sudo()
P.set_str('database.uuid', str(uuid.uuid1()))
P.set_str('database.secret', str(uuid.uuid4()))
P.set_str('database.create_date', fields.Datetime.to_string(fields.Datetime.now()))
P.set_str('web.base.url', A['adres'])
env.ref('base.main_company').write({'name': A['firma']})
try:
    env['res.lang']._activate_lang('tr_TR')
except Exception as hata:
    print('DIL UYARISI:', hata)
env.ref('base.user_admin').write({'password': A['sifre'], 'lang': 'tr_TR', 'tz': 'Europe/Istanbul'})
if A['sablon'] and 'vekosis.sample.data' in env:
    Ornek = env['vekosis.sample.data']
    print('ORNEK SILINDI:', Ornek._vsd_remove())
    if A['ornek']:
        sonuc = Ornek._vsd_load()
        print('ORNEK YUKLENDI: %%s kayit, hata: %%s' %% (sonuc['count'], len(sonuc['errors'])))
env.cr.execute('DELETE FROM mail_mail')
env.cr.commit()
print('KISISEL_TAMAM')
"""


class Kurulum:
    def __init__(self, ayar, komut, isler, ortamlar, odoolar):
        self.ayar = ayar
        self.komut = komut
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar

    # ------------------------------------------------------------ test platformu şablonu
    def sablon(self):
        """Eski test platformunun geçerli şablonu: {"ad", "imaj", "filestore"} ya da None."""
        guncel = self.ayar.vtest_kok / "sablon" / "GUNCEL"
        if not guncel.is_file():
            return None
        ad = guncel.read_text(encoding="utf-8").strip()
        bilgi = self.ayar.vtest_kok / "sablon" / ad / "BILGI"
        if not re.match(r"^sablon_\d{12}$", ad) or not bilgi.is_file():
            return None
        imaj = None
        for satir in bilgi.read_text(encoding="utf-8").splitlines():
            if satir.startswith("IMG="):
                imaj = satir.split("=", 1)[1].strip()
        filestore = self.ayar.vtest_kok / "sablon" / ad / "filestore.tar.gz"
        if not imaj:
            return None
        return {"ad": ad, "imaj": imaj, "filestore": str(filestore) if filestore.is_file() else None}

    # ------------------------------------------------------------ yeni Odoo
    def kur(self, govde, kullanici=None):
        odoo_id = self.ayar.ad_denetle(govde.get("id"))
        firma = re.sub(r"[\x00-\x1f]", "", str(govde.get("firma") or odoo_id)).strip()[:120] or odoo_id
        baslangic = str(govde.get("baslangic") or "bos")
        if baslangic not in ("bos", "sablon"):
            raise Hata(400, "Başlangıç bos ya da sablon olmalı.")
        sablon = self.sablon() if baslangic == "sablon" else None
        if baslangic == "sablon" and not sablon:
            raise Hata(400, "Test platformunda geçerli şablon yok.")
        imaj = str(govde.get("imaj") or (sablon or self.sablon() or {}).get("imaj") or "")
        if not re.match(r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+$", imaj):
            raise Hata(400, "İmaj belirtilmeli (ör. vekosis/test20:20261108-1).")
        if sablon and imaj != sablon["imaj"]:
            raise Hata(400, f"Şablondan kurulumda imaj şablonunki olmalı: {sablon['imaj']}")
        if self.odoolar.oku(odoo_id) or self.ortamlar.dizin(odoo_id, "production").exists():
            raise Hata(409, f"'{odoo_id}' zaten var.")
        self.ortamlar.bellek_denetle()
        ornek = bool(govde.get("ornek", True))
        deneme_gun = govde.get("deneme_gun")
        return self.isler.baslat(
            "kur", f"{odoo_id}/production",
            lambda b: self._kur(b, odoo_id, firma, imaj, sablon, ornek, deneme_gun, kullanici),
            odoo=odoo_id, ortam="production", agir=True, kullanici=kullanici, aciklama=f"{odoo_id} kuruluyor")

    def _kur(self, b, odoo_id, firma, imaj, sablon, ornek, deneme_gun, kullanici):
        imaj_bilgi = self.ortamlar.imaj_bilgisi(imaj)
        o = self.ortamlar.yeni_panel_ortami(odoo_id, "production", imaj, imaj_bilgi["yollar"])
        if self.ortamlar.konteyner_durumu(o) != "yok":
            raise Hata(409, f"{o['konteyner']} adlı konteyner zaten var.")
        if self.ortamlar.db_var(o["db_konteyner"], o["db_su"], o["db_adi"]):
            raise Hata(409, f"{o['db_adi']} veritabanı zaten var.")
        od = {"id": odoo_id, "firma": firma, "tur": "panel", "kaynak": "panel", "seri": imaj_bilgi["seri"],
              "olusturma": kayit.simdi(), "olusturan": kullanici, "depo": None,
              "baslangic": "sablon" if sablon else "bos", "sablon": (sablon or {}).get("ad")}
        if deneme_gun:
            od["deneme_gun"] = int(deneme_gun)
        dizin = self.ortamlar.dizin(odoo_id, "production")
        kurulan = []
        admin_sifre = yeni_sifre(16)
        self.komut.gizle(admin_sifre)
        try:
            with b.adim("Klasör ve yapılandırma"):
                dizin.mkdir(parents=True)
                kurulan.append("dizin")
                sifre, ana = yeni_sifre(), yeni_sifre(32)
                self.ortamlar.conf_yaz(o, self.ortamlar.temel_conf(o, sifre, ana))
                self.ortamlar.compose_yaz(o)
                self.ortamlar.birim_olustur(o, b)
                kurulan.append("birim")
            if sablon:
                with b.adim("Veritabanı şablondan kopyalanıyor"):
                    self._sablondan(b, o, sablon, sifre)
                    kurulan.append("db")
            else:
                with b.adim("Boş veritabanı oluşturuluyor"):
                    self.ortamlar.db_olustur(o, b, sifre)
                    kurulan.append("db")
                    self.ortamlar.odoo_tek(o, b, ["-i", "base", "--load-language", "tr_TR", "--stop-after-init",
                                                  "--no-http"], zaman_asimi=1800)
            with b.adim("Firma ve yönetici ayarlanıyor"):
                ayar = json.dumps({"adres": o["adres"], "firma": firma, "sifre": admin_sifre,
                                   "sablon": bool(sablon), "ornek": ornek}, ensure_ascii=False)
                sonuc = self.ortamlar.odoo_tek(o, b, ["--no-http"], alt_komut="shell", girdi=KISISEL % {"ayar": ayar},
                                               zaman_asimi=1800, log=None)
                if "KISISEL_TAMAM" not in sonuc.cikti:
                    raise Hata(500, "Firma ve yönetici ayarlanamadı.")
                for satir in sonuc.cikti.splitlines():
                    if satir.startswith("ORNEK"):
                        b.yaz(satir)
            with b.adim("Açılıyor"):
                self.ortamlar.adres_kaydet(self.ayar.adres_adi(odoo_id, "production"))
                kurulan.append("adres")
                self.ortamlar.baslat(o, b)
                kurulan.append("konteyner")
                if not self.ortamlar.saglik(o, b):
                    raise Hata(500, "Odoo açılmadı (giriş sayfası yanıt vermedi).")
        except Exception:
            self._geri_al(b, o, kurulan)
            raise
        kayit.yaz(self.ayar.odoolar / odoo_id / "giris.json",
                  {"adres": o["adres"], "kullanici": "admin", "sifre": admin_sifre, "tarih": kayit.simdi()}, gizli=True)
        self.ortamlar.yaz(o)
        self.odoolar.yaz(od)
        return {"adres": o["adres"], "odoo": odoo_id}

    def _sablondan(self, b, o, sablon, sifre):
        rol, db, kaynak = o["db_rol"], o["db_adi"], sablon["ad"]
        self.ortamlar.psql(o, f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{rol}') THEN
    CREATE ROLE "{rol}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 40;
  END IF;
END $$;
ALTER ROLE "{rol}" PASSWORD '{sifre}';
CREATE DATABASE "{db}" OWNER "{rol}" TEMPLATE "{kaynak}";
REVOKE CONNECT ON DATABASE "{db}" FROM PUBLIC;
\\c "{db}"
REASSIGN OWNED BY "t_sablon" TO "{rol}";
REVOKE ALL ON SCHEMA public FROM "t_sablon";
""", db="postgres", b=b)
        kalan = self.ortamlar.psql(o, f"SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                                      f"WHERE n.nspname = 'public' AND pg_get_userbyid(c.relowner) <> '{rol}';")
        if kalan.strip() != "0":
            raise Hata(500, f"{kalan} tablo yeni role devredilemedi.")
        if sablon.get("filestore"):
            girdi = str(Path(sablon["filestore"]).parent)
            self.ortamlar.docker(
                b, "run", "--rm", "--user", "0", "--network", "none", "--entrypoint", "sh",
                "-v", f"{o['birim']}:/var/lib/odoo", "-v", f"{girdi}:/girdi:ro", o["imaj"], "-c",
                f"mkdir -p /var/lib/odoo/filestore && tar -xzf /girdi/filestore.tar.gz -C /var/lib/odoo/filestore && "
                f"mv /var/lib/odoo/filestore/{kaynak} /var/lib/odoo/filestore/{db} && chown -R odoo:odoo /var/lib/odoo")

    def _geri_al(self, b, o, kurulan):
        b.yaz("Kurulum yarıda kaldı, yapılanlar geri alınıyor: " + ", ".join(kurulan))
        if "konteyner" in kurulan or "dizin" in kurulan:
            if Path(o["compose"]).exists():
                self.ortamlar.compose(o, b, "down", "--timeout", "20", kontrol=False)
            b.komut(["docker", "rm", "-f", o["konteyner"]], kontrol=False)
        if "adres" in kurulan:
            self.ortamlar.adres_kaydet(self.ayar.adres_adi(o["odoo"], "production"), var=False)
        if "db" in kurulan:
            try:
                self.ortamlar.db_sil(o, b, rol_da=True)
            except Exception as hata:  # noqa: BLE001
                b.yaz(f"Veritabanı silinemedi: {hata}")
        if "birim" in kurulan:
            b.komut(["docker", "volume", "rm", o["birim"]], kontrol=False)
        if "dizin" in kurulan:
            shutil.rmtree(self.ortamlar.dizin(o["odoo"], "production").parent, ignore_errors=True)

    # ------------------------------------------------------------ silme
    def sil(self, odoo_id, onay, staging, yedekler, kullanici=None):
        """Panelin kurduğu Odoo'yu staging'iyle birlikte siler. Önce SILINMEDEN-ONCE yedeği alınır ve saklanır."""
        od = self.odoolar.gerekli(odoo_id)
        if od.get("tur") != "panel":
            raise Hata(400, "Bağlanan kurulum silinmez; yalnız bağlantısı kaldırılır.")
        pr = self.ortamlar.gerekli(odoo_id, "production")
        beklenen = pr["adres"].replace("https://", "")
        if str(onay or "").strip().lower() != beklenen:
            raise Hata(400, f"Onay için tam adres yazılmalı: {beklenen}")

        def isle(b):
            st = self.ortamlar.oku(odoo_id, "staging")
            if st:
                with b.adim("Staging siliniyor"):
                    staging._temizle(b, st, ["konteyner", "adres", "db", "birim", "dizin"], rol_da=True)
            with b.adim("Son yedek alınıyor (silinmez)"):
                yedek = yedekler.al(pr, b, "SILINMEDEN-ONCE")["dosya"]
            with b.adim("Production siliniyor"):
                self._geri_al(b, pr, ["konteyner", "adres", "db", "birim"])
                arsiv = self.ayar.kok / "silinenler" / f"{odoo_id}-{kayit.simdi().replace(':', '')}"
                arsiv.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(self.ayar.odoolar / odoo_id), str(arsiv))
            return {"silindi": odoo_id, "yedek": yedek}

        return self.isler.baslat("sil", f"{odoo_id}/production", isle, odoo=odoo_id, ortam="production", agir=True,
                                 kullanici=kullanici, aciklama=f"{odoo_id} siliniyor")

    # ------------------------------------------------------------ bağlama
    def bulunanlar(self):
        """Sunucudaki, panelin yönetmediği Odoo konteynerleri."""
        sonuc = self.komut.calistir(["docker", "ps", "-a", "--format", "{{.Names}}"], zaman_asimi=30)
        adlar = [a.strip() for a in sonuc.cikti.splitlines() if a.strip() and not a.startswith("pnl-")]
        if not adlar:
            return []
        incelemeler = json.loads(self.komut.calistir(["docker", "inspect", *adlar], zaman_asimi=60).cikti)
        bagli = {}
        for od in self.odoolar.liste():
            pr = self.ortamlar.oku(od["id"], "production")
            if pr and od.get("tur") == "bagli":
                bagli[pr["konteyner"]] = od["id"]
        liste = []
        for inceleme in incelemeler:
            ad = inceleme["Name"].lstrip("/")
            if not _conf_baglamasi(inceleme):
                continue
            kaynak = self._kaynak(inceleme)
            liste.append({"konteyner": ad, "imaj": inceleme["Config"]["Image"],
                          "durum": inceleme["State"]["Status"], "kaynak": kaynak,
                          "onerilen_ad": self._onerilen_ad(ad, kaynak), "bagli_odoo": bagli.get(ad),
                          "adres": self._adres(ad)})
        return liste

    def kesfet(self, konteyner):
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$", konteyner or ""):
            raise Hata(400, "Geçersiz konteyner adı.")
        if konteyner.startswith("pnl-"):
            raise Hata(400, "Bu konteyner zaten panelin.")
        sonuc = self.komut.calistir(["docker", "inspect", konteyner], kontrol=False, zaman_asimi=30)
        if not sonuc.tamam:
            raise Hata(404, f"Konteyner bulunamadı: {konteyner}")
        inceleme = json.loads(sonuc.cikti)[0]
        conf_yolu = _conf_baglamasi(inceleme)
        if not conf_yolu:
            raise Hata(400, "Konteynerde /etc/odoo/odoo.conf bağlaması yok; Odoo konteyneri değil gibi.")
        conf = conf_oku(Path(conf_yolu).read_text(encoding="utf-8"))
        db_adi = conf.get("db_name") or ""
        if not db_adi:
            eslesme = re.match(r"^\^([A-Za-z0-9_-]+)\$$", conf.get("dbfilter", ""))
            db_adi = eslesme.group(1) if eslesme else ""
        if not db_adi:
            raise Hata(400, "odoo.conf'ta tek veritabanı (db_name) yok; çok veritabanlı kurulum bağlanmaz.")
        if not re.match(r"^[a-z0-9][a-z0-9_-]{0,62}$", db_adi):
            raise Hata(400, f"Veritabanı adı panelin kabul ettiği biçimde değil: {db_adi[:80]}")
        etiketler = inceleme["Config"].get("Labels") or {}
        db_konteyner = self._db_konteyneri(conf.get("db_host", ""), etiketler)
        db_inceleme = json.loads(self.komut.calistir(["docker", "inspect", db_konteyner], zaman_asimi=30).cikti)[0]
        db_env = dict(e.split("=", 1) for e in db_inceleme["Config"].get("Env") or [] if "=" in e)
        birim = next((m.get("Name") for m in inceleme.get("Mounts", [])
                      if m.get("Destination") == "/var/lib/odoo" and m.get("Type") == "volume"), None)
        if not birim:
            raise Hata(400, "Dosya deposu birimi (/var/lib/odoo) bulunamadı.")
        yollar = [y.strip() for y in conf.get("addons_path", "").split(",") if y.strip()]
        kod_baglamalari = [(m["Source"], m["Destination"]) for m in inceleme.get("Mounts", [])
                           if m.get("Type") == "bind" and m.get("Destination") in yollar]
        kaynak = self._kaynak(inceleme)
        return {
            "yonetim": "bagli", "konteyner": konteyner, "compose": None, "env": None,
            "db_konteyner": db_konteyner, "db_su": db_env.get("POSTGRES_USER") or "postgres", "db_adi": db_adi,
            "db_rol": conf.get("db_user"), "birim": birim, "imaj": inceleme["Config"]["Image"],
            "imaj_temel": inceleme["Config"]["Image"], "adres": self._adres(konteyner), "conf": conf_yolu,
            "kod": None, "commit": None, "ek_addons": None,
            "addons_yollari": [y for y in yollar if y not in [h for _, h in kod_baglamalari]],
            "kesif": {"kaynak": kaynak, "compose_proje": etiketler.get("com.docker.compose.project"),
                      "compose_dosyalar": etiketler.get("com.docker.compose.project.config_files"),
                      "servis": etiketler.get("com.docker.compose.service"), "kod_baglamalari": kod_baglamalari,
                      "aglar": sorted((inceleme.get("NetworkSettings") or {}).get("Networks", {}).keys())},
        }

    def bagla(self, govde, kullanici=None):
        konteyner = str(govde.get("konteyner") or "")
        o = self.kesfet(konteyner)
        odoo_id = self.ayar.ad_denetle(govde.get("id") or self._onerilen_ad(konteyner, o["kesif"]["kaynak"]))
        if self.odoolar.oku(odoo_id):
            raise Hata(409, f"'{odoo_id}' adı panelde kullanılıyor.")
        for od in self.odoolar.liste():
            pr = self.ortamlar.oku(od["id"], "production")
            if pr and pr.get("konteyner") == konteyner:
                raise Hata(409, f"Bu konteyner zaten '{od['id']}' adıyla bağlı.")
        imaj_bilgi = self.ortamlar.imaj_bilgisi(o["imaj"])
        firma = re.sub(r"[\x00-\x1f]", "", str(govde.get("firma") or odoo_id)).strip()[:120]
        o.update(odoo=odoo_id, ad="production", olusturma=kayit.simdi())
        od = {"id": odoo_id, "firma": firma, "tur": "bagli", "kaynak": o["kesif"]["kaynak"], "seri": imaj_bilgi["seri"],
              "olusturma": kayit.simdi(), "olusturan": kullanici, "depo": None, "islemler_acik": False}
        self.ortamlar.yaz(o)
        self.odoolar.yaz(od)
        return {"odoo": od, "production": o}

    def baglantiyi_kaldir(self, odoo_id):
        od = self.odoolar.gerekli(odoo_id)
        if od.get("tur") != "bagli":
            raise Hata(400, "Yalnız bağlanan kurulumun bağlantısı kaldırılır.")
        if self.ortamlar.oku(odoo_id, "staging"):
            raise Hata(409, "Önce staging'i silin.")
        arsiv = self.ayar.kok / "silinenler" / f"{odoo_id}-baglanti-{kayit.simdi().replace(':', '')}"
        arsiv.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.ayar.odoolar / odoo_id), str(arsiv))
        return {"kaldirildi": odoo_id}

    # ------------------------------------------------------------ yardımcılar
    def _kaynak(self, inceleme):
        etiketler = inceleme["Config"].get("Labels") or {}
        calisma = etiketler.get("com.docker.compose.project.working_dir", "")
        if calisma and Path(calisma).parent == self.ayar.vtest_kok / "tenants":
            return "vtest"
        if calisma.rstrip("/") == "/opt/erp20" or inceleme["Name"].lstrip("/") == "erp20-odoo":
            return "erp"
        return "diger"

    @staticmethod
    def _onerilen_ad(konteyner, kaynak):
        if kaynak == "erp":
            return "erp-vekosis"
        ad = konteyner[5:] if konteyner.startswith("odoo-") else konteyner
        ad = re.sub(r"[^a-z0-9-]", "-", ad.lower()).strip("-")[:22]
        return ad if len(ad) >= 3 else f"odoo-{ad}"

    def _db_konteyneri(self, db_host, etiketler):
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$", db_host or ""):
            raise Hata(400, "odoo.conf'ta db_host yok.")
        if self.komut.calistir(["docker", "inspect", "-f", "{{.Name}}", db_host], kontrol=False, zaman_asimi=20).tamam:
            return db_host
        proje = etiketler.get("com.docker.compose.project")
        if proje:
            sonuc = self.komut.calistir(["docker", "ps", "--format", "{{.Names}}", "--filter",
                                         f"label=com.docker.compose.project={proje}", "--filter",
                                         f"label=com.docker.compose.service={db_host}"], zaman_asimi=20)
            adlar = sonuc.cikti.split()
            if len(adlar) == 1:
                return adlar[0]
        raise Hata(400, f"Veritabanı konteyneri bulunamadı ({db_host}).")

    def _adres(self, konteyner):
        caddyfile = self.ayar.kenar_tenants.parent / "Caddyfile"
        try:
            metin = caddyfile.read_text(encoding="utf-8")
        except OSError:
            return None
        site = None
        for ham in metin.splitlines():
            satir = ham.split("#", 1)[0].rstrip()
            if satir and not ham.startswith((" ", "\t")) and satir.endswith("{"):
                site = satir[:-1].strip()
                continue
            eslesme = re.search(r"reverse_proxy\s+(?:/\S+\s+)?([A-Za-z0-9_.{}-]+):8069", satir)
            if not eslesme or not site:
                continue
            hedef = eslesme.group(1)
            if hedef == konteyner and not site.startswith("*"):
                return f"https://{site}"
            if "{labels.3}" in hedef and site.startswith("*."):
                desen = "^" + re.escape(hedef).replace(re.escape("{labels.3}"), "([a-z0-9-]+)") + "$"
                eslesme = re.match(desen, konteyner)
                if eslesme:
                    return f"https://{eslesme.group(1)}{site[1:]}"
        return None


def _conf_baglamasi(inceleme):
    for baglama in inceleme.get("Mounts", []):
        if baglama.get("Destination") == "/etc/odoo/odoo.conf" and baglama.get("Type") == "bind":
            return baglama.get("Source")
    return None
