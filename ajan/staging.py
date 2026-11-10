"""Staging: production'ın (ya da bir yedeğinin) nötrleştirilmiş kopyası.

Staging her zaman panelin yönettiği ortamdır (pnl-<ad>-staging, pnl_<ad>_staging), production bağlanan bir kurulum
olsa bile. Nötrleştirme:
  1. Odoo'nun kendi "odoo neutralize" komutu (posta sunucuları kapanır ve sahte sunucu eklenir, zamanlanmış işler
     durur, webhook'lar kapanır, database.is_neutralized)
  2. Vekosis eki (EK_NOTR): e-Belge entegratörü (Mysoft dahil) test kipine alınır ve kimlik bilgileri silinir,
     e-posta istemcisi hesaplarının şifre ve jetonları silinir
  3. adres, database.uuid ve database.secret staging'e özgü yapılır
Sonra denetlenir: is_neutralized, çalışan zamanlanmış iş, etkin posta sunucusu, etkin entegratör.
"""
import shutil
import uuid
from pathlib import Path

from . import kayit
from .hata import Hata
from .ortam import conf_oku, yeni_sifre

# (tablo, kolon, yeni değer SQL) - tablo/kolon yoksa atlanır
EK_NOTR = [
    ("gib_integrator", "active", "false"),
    ("gib_integrator", "test_mode", "true"),
    ("gib_integrator", "api_key", "NULL"),
    ("gib_integrator", "api_password", "NULL"),
    ("gib_integrator", "mysoft_client_secret", "NULL"),
    ("gib_integrator", "mysoft_access_token", "NULL"),
    ("gib_integrator", "mysoft_token_expiry", "NULL"),
    ("mail_client_account", "password", "NULL"),
    ("mail_client_account", "google_gmail_refresh_token", "NULL"),
    ("mail_client_account", "microsoft_outlook_refresh_token", "NULL"),
    ("mail_client_account", "active", "false"),
]
# production conf'undan staging'e taşınmayan seçenekler (staging kendi değerlerini alır)
CONF_HARIC = {"db_host", "db_port", "db_user", "db_password", "db_name", "dbfilter", "admin_passwd", "addons_path",
              "data_dir", "http_interface", "http_port", "gevent_port", "longpolling_port", "proxy_mode", "list_db",
              "logfile", "pidfile", "workers", "max_cron_threads", "db_maxconn", "smtp_server", "smtp_port",
              "smtp_user", "smtp_password", "smtp_ssl", "email_from", "db_sslmode", "db_template"}


def ek_notr_sql():
    satirlar = ",\n".join(f"    ('{t}', '{k}', '{d}')" for t, k, d in EK_NOTR)
    return f"""DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT * FROM (VALUES
{satirlar}
  ) AS t(tablo, kolon, deger) LOOP
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = r.tablo AND column_name = r.kolon) THEN
      EXECUTE format('UPDATE %I SET %I = %s', r.tablo, r.kolon, r.deger);
      RAISE NOTICE 'notr: %.%', r.tablo, r.kolon;
    END IF;
  END LOOP;
END $$;
"""


def kimlik_sql(adres):
    adres = adres.replace("'", "")
    return f"""
INSERT INTO ir_config_parameter (key, value, create_date, write_date) VALUES ('web.base.url', '{adres}', now(), now())
  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now();
UPDATE ir_config_parameter SET value = gen_random_uuid()::text, write_date = now()
 WHERE key IN ('database.uuid', 'database.secret');
DELETE FROM ir_config_parameter WHERE key IN ('database.enterprise_code', 'database.expiration_date',
  'database.expiration_reason', 'database.already_linked_subscription_url', 'database.already_linked_email',
  'database.already_linked_send_mail_url');
"""


DENETIM_SQL = """
SELECT 'notr=' || coalesce((SELECT value FROM ir_config_parameter WHERE key = 'database.is_neutralized'), '-');
SELECT 'cron=' || count(*) FROM ir_cron c
 WHERE c.active AND c.id NOT IN (SELECT res_id FROM ir_model_data WHERE model = 'ir.cron' AND module = 'base'
                                  AND name = 'autovacuum_job');
SELECT 'posta=' || count(*) FROM ir_mail_server WHERE active AND smtp_host <> 'invalid';
SELECT 'entegrator_tablosu=' || (to_regclass('public.gib_integrator') IS NOT NULL);
"""


class Staging:
    def __init__(self, ayar, isler, ortamlar, odoolar, yedekler, deploylar):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.yedekler = yedekler
        self.deploylar = deploylar

    # ------------------------------------------------------------ istekler
    def olustur(self, odoo_id, kullanici=None):
        self.odoolar.gerekli(odoo_id)
        self.ortamlar.gerekli(odoo_id, "production")
        if self.ortamlar.oku(odoo_id, "staging"):
            raise Hata(409, "Staging zaten var; verisini production'dan yenileyebilirsiniz.")
        self.ortamlar.bellek_denetle()
        return self.isler.baslat("staging-olustur", f"{odoo_id}/staging", lambda b: self._olustur(b, odoo_id),
                                 odoo=odoo_id, ortam="staging", agir=True, kullanici=kullanici,
                                 aciklama="Staging oluşturuluyor")

    def yenile(self, odoo_id, kullanici=None):
        self.ortamlar.gerekli(odoo_id, "staging")
        self.ortamlar.gerekli(odoo_id, "production")
        return self.isler.baslat("staging-yenile", f"{odoo_id}/staging", lambda b: self._yenile(b, odoo_id),
                                 odoo=odoo_id, ortam="staging", agir=True, kullanici=kullanici,
                                 aciklama="Staging verisi production'dan yenileniyor")

    def yedekten_ac(self, odoo_id, dosya, kullanici=None):
        """Production yedeğini staging'de açar (staging yoksa oluşturur)."""
        yol = self.yedekler.yol(odoo_id, "production", dosya)
        self.ortamlar.gerekli(odoo_id, "production")
        if not self.ortamlar.oku(odoo_id, "staging"):
            self.ortamlar.bellek_denetle()
            islev = lambda b: self._olustur(b, odoo_id, yedek=yol)  # noqa: E731
        else:
            islev = lambda b: self._yenile(b, odoo_id, yedek=yol)  # noqa: E731
        return self.isler.baslat("yedek-staging", f"{odoo_id}/staging", islev, odoo=odoo_id, ortam="staging",
                                 agir=True, kullanici=kullanici, aciklama=f"{dosya} staging'de açılıyor")

    def sil(self, odoo_id, kullanici=None):
        self.ortamlar.gerekli(odoo_id, "staging")
        return self.isler.baslat("staging-sil", f"{odoo_id}/staging", lambda b: self._sil(b, odoo_id),
                                 odoo=odoo_id, ortam="staging", kullanici=kullanici, aciklama="Staging siliniyor")

    # ------------------------------------------------------------ işler
    def _olustur(self, b, odoo_id, yedek=None):
        od = self.odoolar.gerekli(odoo_id)
        pr = self.ortamlar.gerekli(odoo_id, "production")
        imaj = pr["imaj"]
        imaj_bilgi = self.ortamlar.imaj_bilgisi(imaj)
        st = self.ortamlar.yeni_panel_ortami(odoo_id, "staging", imaj, imaj_bilgi["yollar"])
        st["imaj_temel"] = pr.get("imaj_temel") or imaj
        dizin = self.ortamlar.dizin(odoo_id, "staging")
        if dizin.exists():
            raise Hata(409, f"Staging klasörü zaten var: {dizin}")
        if self.ortamlar.konteyner_durumu(st) != "yok":
            raise Hata(409, f"{st['konteyner']} adlı konteyner zaten var.")
        if self.ortamlar.db_var(st["db_konteyner"], st["db_su"], st["db_adi"]):
            raise Hata(409, f"{st['db_adi']} veritabanı zaten var.")
        kurulan = []
        try:
            with b.adim("Klasör ve yapılandırma"):
                dizin.mkdir(parents=True)
                kurulan.append("dizin")
                self._kod_kopyala(b, pr, st)
                sifre, ana = yeni_sifre(), yeni_sifre(32)
                self.ortamlar.conf_yaz(st, self.ortamlar.temel_conf(st, sifre, ana, ek=self._conf_eki(pr)))
                self.ortamlar.compose_yaz(st)
                self.ortamlar.birim_olustur(st, b)
                kurulan.append("birim")
                self.ortamlar.db_olustur(st, b, sifre)
                kurulan.append("db")
            self._veri_yukle(b, pr, st, yedek)
            with b.adim("Nötrleştiriliyor"):
                st["notr"] = self._notrlestir(b, st)
            with b.adim("Açılıyor"):
                self.ortamlar.adres_kaydet(self.ayar.adres_adi(odoo_id, "staging"))
                kurulan.append("adres")
                self.ortamlar.baslat(st, b)
                kurulan.append("konteyner")
                if not self.ortamlar.saglik(st, b):
                    raise Hata(500, "Staging açılmadı (giriş sayfası yanıt vermedi).")
        except Exception:
            self._temizle(b, st, kurulan)
            raise
        st["veri_kaynak"] = {"tur": "yedek" if yedek else "production", "dosya": Path(yedek).name if yedek else None,
                             "tarih": kayit.simdi()}
        st["yenileme"] = kayit.simdi()
        self.ortamlar.yaz(st)
        sonuc = {"adres": st["adres"], "notr": st["notr"]}
        dal = ((od.get("depo") or {}).get("dallar") or {}).get("staging")
        if dal:
            is_kaydi = self.deploylar.baslat(odoo_id, "staging", tetik="elle", kuyruk=True)
            sonuc["deploy_isi"] = is_kaydi["id"]
            b.yaz(f"Staging dalı ({dal}) deploy sırasına alındı.")
        return sonuc

    def _yenile(self, b, odoo_id, yedek=None):
        pr = self.ortamlar.gerekli(odoo_id, "production")
        st = self.ortamlar.gerekli(odoo_id, "staging")
        with b.adim("Staging yedeği"):
            self.yedekler.al(st, b, "YENILEME-ONCESI")
        with b.adim("Staging durduruluyor"):
            self.ortamlar.durdur(st, b)
        with b.adim("Eski veri siliniyor"):
            self.ortamlar.db_sil(st, b)
            self.ortamlar.db_olustur(st, b)
        self._veri_yukle(b, pr, st, yedek)
        with b.adim("Nötrleştiriliyor"):
            st["notr"] = self._notrlestir(b, st)
        with b.adim("Açılıyor"):
            self.ortamlar.baslat(st, b)
            if not self.ortamlar.saglik(st, b):
                raise Hata(500, "Staging yenilenen veriyle açılmadı.")
        st["veri_kaynak"] = {"tur": "yedek" if yedek else "production", "dosya": Path(yedek).name if yedek else None,
                             "tarih": kayit.simdi()}
        st["yenileme"] = kayit.simdi()
        self.ortamlar.yaz(st)
        return {"adres": st["adres"], "notr": st["notr"]}

    def _sil(self, b, odoo_id):
        st = self.ortamlar.gerekli(odoo_id, "staging")
        self._temizle(b, st, ["konteyner", "adres", "db", "birim", "dizin"], rol_da=True)
        return {"silindi": True}

    # ------------------------------------------------------------ yardımcılar
    def _kod_kopyala(self, b, pr, st):
        """Production'ın kodunu staging'e kopyalar (staging kendi dalını deploy edene kadar aynı kod)."""
        if pr.get("yonetim") == "panel":
            if pr.get("commit") and Path(pr["kod"]).is_dir():
                hedef = Path(st["kod"]).parent / pr["commit"]
                shutil.copytree(pr["kod"], hedef)
                st.update(kod=str(hedef), commit=pr["commit"], kod_gecmisi=[pr["commit"]])
            if Path(pr.get("ek_addons") or "").is_dir():
                shutil.copytree(pr["ek_addons"], st["ek_addons"], dirs_exist_ok=True)
            return
        for kaynak, hedef in (pr.get("kesif") or {}).get("kod_baglamalari", []):
            if hedef == "/mnt/extra-addons" and Path(kaynak).is_dir():
                shutil.copytree(kaynak, st["ek_addons"], dirs_exist_ok=True)
                b.yaz(f"Ek modüller kopyalandı: {kaynak}")
            else:
                b.uyari(f"Kod bağlaması staging'e alınmadı: {kaynak} -> {hedef}")

    def _conf_eki(self, pr):
        try:
            secenekler = conf_oku(Path(pr["conf"]).read_text(encoding="utf-8"))
        except (OSError, KeyError):
            return {}
        return {k: v for k, v in secenekler.items() if k not in CONF_HARIC}

    def _veri_yukle(self, b, pr, st, yedek):
        if yedek:
            with b.adim("Yedek yükleniyor"):
                with self.yedekler.ac(yedek) as (klasor, meta):
                    sayi = self.ortamlar.dokum_yukle(st, b, klasor / "veritabani.dump")
                    self.ortamlar.filestore_ac(st, b, klasor, meta.get("db_adi") or pr["db_adi"])
            b.yaz(f"{sayi} kurulu modül")
            return
        dokum = self.ayar.gecici / f"{uuid.uuid4().hex}.dump"
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        try:
            with b.adim("Production verisi kopyalanıyor"):
                self.ortamlar.dokum_al(pr, b, dokum)
                sayi = self.ortamlar.dokum_yukle(st, b, dokum)
                b.yaz(f"{sayi} kurulu modül")
            with b.adim("Dosya deposu kopyalanıyor"):
                self.ortamlar.filestore_kopyala(pr, st, b)
        finally:
            dokum.unlink(missing_ok=True)

    def _notrlestir(self, b, st):
        self.ortamlar.odoo_tek(st, b, [], alt_komut="neutralize", zaman_asimi=900)
        self.ortamlar.psql(st, ek_notr_sql(), b=b)
        self.ortamlar.psql(st, kimlik_sql(st["adres"]), b=b)
        cikti = self.ortamlar.psql(st, DENETIM_SQL, b=b)
        sonuc = {}
        for satir in cikti.splitlines():
            anahtar, _, deger = satir.partition("=")
            if anahtar in ("notr", "cron", "posta", "entegrator_tablosu"):
                sonuc[anahtar] = deger.strip()
        if sonuc.pop("entegrator_tablosu", "f") == "t":
            sonuc["entegrator"] = self.ortamlar.psql(st, "SELECT count(*) FROM gib_integrator WHERE active;", b=b)
        b.yaz(f"Nötrleştirme denetimi: {sonuc}")
        if sonuc.get("notr") != "True":
            raise Hata(500, "Nötrleştirme doğrulanamadı (database.is_neutralized yok).")
        for anahtar, ad in (("cron", "zamanlanmış iş"), ("posta", "posta sunucusu"), ("entegrator", "e-Belge entegratörü")):
            if sonuc.get(anahtar, "0") not in ("0", ""):
                raise Hata(500, f"Nötrleştirmeden sonra etkin {ad} kaldı: {sonuc[anahtar]}")
        return {"tarih": kayit.simdi(), **sonuc}

    def _temizle(self, b, st, kurulan, rol_da=True):
        """Yarım kalan staging kurulumunu geri alır (yalnız bu işte oluşturulanlar)."""
        b.yaz("Staging kaldırılıyor: " + ", ".join(kurulan))
        if "konteyner" in kurulan or "dizin" in kurulan:
            if Path(st["compose"]).exists():
                self.ortamlar.compose(st, b, "down", "--timeout", "20", kontrol=False)
            b.komut(["docker", "rm", "-f", st["konteyner"]], kontrol=False)
        if "adres" in kurulan:
            self.ortamlar.adres_kaydet(self.ayar.adres_adi(st["odoo"], "staging"), var=False)
        if "db" in kurulan:
            try:
                self.ortamlar.db_sil(st, b, rol_da=rol_da)
            except Exception as hata:  # noqa: BLE001
                b.yaz(f"Veritabanı silinemedi: {hata}")
        if "birim" in kurulan:
            b.komut(["docker", "volume", "rm", st["birim"]], kontrol=False)
        if "dizin" in kurulan:
            dizin = self.ortamlar.dizin(st["odoo"], "staging")
            arsiv = self.ayar.kok / "silinenler" / f"{st['odoo']}-staging-{kayit.simdi().replace(':', '')}"
            arsiv.parent.mkdir(parents=True, exist_ok=True)
            if dizin.exists():
                shutil.move(str(dizin), str(arsiv))
