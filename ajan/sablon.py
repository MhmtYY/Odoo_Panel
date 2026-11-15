"""Platformdan şablon: her platformun (production ya da staging) anlık kopyası; yeni platform bundan kurulur.

Konum: /opt/odoo-panel/sablonlar/<ad>/
  sablon.json        ad, başlık, tür, kaynak platform, imaj, kurulu modüller
  kod/, ek-addons/   platformun çalışan kodu (depo kodu ve ek modüller)
  veritabani.dump, filestore.tar.gz   yalnız "veri" türünde

İki tür:
  veri      veritabanı ve dosyalarla. Döküm geçici bir veritabanına açılıp temizlenir, şablona temiz hali yazılır:
            Odoo'nun nötrleştirmesi (entegrasyonlar), posta sunucuları, e-Belge ve hesap anahtarları, oturum ve API
            anahtarları silinir; yönetici dışındaki kullanıcılar pasif olur, şifreler silinir.
            Staging'in aksine zamanlanmış işler açık kalır: yeni platform normal çalışacak.
  moduller  yalnız kurulu modül listesi ve kod; yeni platform boş veritabanıyla aynı modülleri kurar.
"""
import re
import shutil
import uuid
from pathlib import Path

from . import kayit
from .hata import Hata
from .ortam import yeni_sifre
from .staging import ek_notr_sql, kimlik_sql

AD_DESEN = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
TURLER = ("veri", "moduller")
KOD_HARIC = shutil.ignore_patterns(".hazir", ".git", "__pycache__")

# Boş bırakılabilen metin sütunlarından adı bunlara uyanlar silinir (kişisel paylaşım bağlantıları access_token kalır)
GIZLI_SUTUN = r"(password|passwd|secret|api_?key|access_key|private_key|refresh_token|_rtoken($|_)|oauth_access_token|bearer|calendar_token)"
GIZLI_PARAMETRE = r"(secret|password|passwd|api_?key|access_key|token|client_id|bearer)"
# Şablona geçmeyen kayıtlar (tablo yoksa ya da başka kayıt bağlıysa atlanır)
SILINECEK_TABLOLAR = ("mail_mail", "res_users_apikeys", "auth_passkey_key", "iap_account", "res_device_log", "bus_bus")
BASE_KULLANICI = "SELECT res_id FROM ir_model_data WHERE model = 'res.users' AND module = 'base'"


def temizlik_sql(aktif_cronlar):
    """Nötrleştirmeden sonra çalışır. aktif_cronlar: nötrleştirmeden önce etkin olan zamanlanmış işler."""
    idler = ",".join(str(int(i)) for i in aktif_cronlar)
    cron = f"UPDATE ir_cron SET active = true WHERE id IN ({idler});" if idler else ""
    silinecek = ",".join(f"('{t}')" for t in SILINECEK_TABLOLAR)
    return f"""DO $$
DECLARE r record;
BEGIN
  UPDATE res_users SET active = false WHERE id NOT IN ({BASE_KULLANICI});
  UPDATE res_users SET password = NULL;
  FOR r IN SELECT c.table_name, c.column_name
             FROM information_schema.columns c
             JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND c.is_nullable = 'YES'
              AND c.data_type IN ('character varying', 'text', 'bytea') AND c.column_name ~* '{GIZLI_SUTUN}' LOOP
    EXECUTE format('UPDATE %I SET %I = NULL WHERE %I IS NOT NULL', r.table_name, r.column_name, r.column_name);
  END LOOP;
  FOR r IN SELECT v.ad FROM (VALUES {silinecek}) AS v(ad)
             JOIN information_schema.tables t ON t.table_schema = 'public' AND t.table_name = v.ad
                                             AND t.table_type = 'BASE TABLE' LOOP
    BEGIN
      EXECUTE format('DELETE FROM %I', r.ad);
    EXCEPTION WHEN foreign_key_violation THEN
      RAISE NOTICE 'silinemedi: %', r.ad;
    END;
  END LOOP;
  BEGIN
    DELETE FROM ir_mail_server;
  EXCEPTION WHEN foreign_key_violation THEN
    UPDATE ir_mail_server SET active = false, smtp_user = NULL, smtp_pass = NULL;
  END;
  DELETE FROM ir_config_parameter
   WHERE key ~* '{GIZLI_PARAMETRE}' AND key !~* '^auth_(password_policy|signup)';
END $$;
{cron}
UPDATE ir_ui_view SET active = false WHERE key = 'web.neutralize_banner';
DELETE FROM ir_config_parameter WHERE key = 'database.is_neutralized';
"""


DENETIM_SQL = f"""
SELECT 'kullanici=' || count(*) FROM res_users WHERE active AND id NOT IN ({BASE_KULLANICI});
SELECT 'sifre=' || count(*) FROM res_users WHERE password IS NOT NULL;
SELECT 'posta=' || count(*) FROM ir_mail_server WHERE active;
"""


class Sablonlar:
    def __init__(self, ayar, isler, ortamlar, odoolar):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar

    def dizin(self, ad):
        return self.ayar.sablonlar / ad

    @staticmethod
    def _ad(ad):
        ad = str(ad or "").strip().lower()
        if not AD_DESEN.match(ad) or "--" in ad:
            raise Hata(400, "Geçersiz şablon adı. Küçük harfle başlar; küçük harf, rakam ve tire; 3-40 karakter.")
        return ad

    def liste(self):
        kok = self.ayar.sablonlar
        sonuc = []
        if kok.is_dir():
            for alt in kok.iterdir():
                bilgi = None if alt.name.startswith(".") else kayit.oku(alt / "sablon.json")
                if bilgi:
                    sonuc.append({**bilgi, "imaj_var": bool(self.ortamlar.imaj_kimligi(bilgi["imaj"]))})
        return sorted(sonuc, key=lambda s: s.get("tarih") or "", reverse=True)

    def gerekli(self, ad):
        bilgi = kayit.oku(self.dizin(self._ad(ad)) / "sablon.json")
        if not bilgi:
            raise Hata(404, f"'{ad}' adlı şablon yok.")
        return bilgi

    def sil(self, ad):
        self.gerekli(ad)
        shutil.rmtree(self.dizin(self._ad(ad)))
        return {"silindi": ad}

    # ------------------------------------------------------------ oluşturma
    def olustur(self, odoo_id, ortam, govde, kullanici=None):
        od = self.odoolar.gerekli(odoo_id)
        o = self.ortamlar.gerekli(odoo_id, ortam)
        ad = self._ad(govde.get("ad"))
        if self.dizin(ad).exists():
            raise Hata(409, f"'{ad}' adlı şablon zaten var.")
        tur = str(govde.get("tur") or "")
        if tur not in TURLER:
            raise Hata(400, "Şablon türü veri ya da moduller olmalı.")
        if tur == "veri":
            if not govde.get("onay"):
                raise Hata(400, "Veriyle şablon için bu platformda gerçek müşteri verisi olmadığını onaylayın.")
            self.ortamlar.bellek_denetle()
        baslik = re.sub(r"[\x00-\x1f]", "", str(govde.get("baslik") or ad)).strip()[:80] or ad
        aciklama = re.sub(r"[\x00-\x09\x0b-\x1f]", "", str(govde.get("aciklama") or "")).strip()[:300]
        return self.isler.baslat(
            "sablon", f"{odoo_id}/{ortam}", lambda b: self._olustur(b, od, o, ad, tur, baslik, aciklama, kullanici),
            odoo=odoo_id, ortam=ortam, agir=True, kullanici=kullanici, aciklama=f"Şablon oluşturuluyor: {ad}")

    def _olustur(self, b, od, o, ad, tur, baslik, aciklama, kullanici):
        hedef = self.dizin(ad)
        gecici = self.ayar.sablonlar / f".{ad}.yapiliyor"
        shutil.rmtree(gecici, ignore_errors=True)
        gecici.mkdir(parents=True)
        try:
            with b.adim("Kod kopyalanıyor"):
                self._kod_al(b, o, gecici)
            moduller = sorted(self.ortamlar.kurulu_moduller(o))
            if not moduller:
                raise Hata(500, "Kurulu modül listesi okunamadı.")
            b.yaz(f"{len(moduller)} kurulu modül")
            if tur == "veri":
                with b.adim("Veritabanı ve dosyalar alınıyor"):
                    self.ortamlar.dokum_al(o, b, gecici / "kaynak.dump")
                    self.ortamlar.filestore_paketle(o, b, gecici)
                with b.adim("Kopya temizleniyor"):
                    self._temizle(b, o, gecici)
            boyut = sum(p.stat().st_size for p in gecici.rglob("*") if p.is_file())
            bilgi = {"ad": ad, "baslik": baslik, "aciklama": aciklama, "tur": tur, "kaynak_odoo": o["odoo"],
                     "kaynak_firma": od.get("firma"), "kaynak_ortam": o["ad"], "seri": od.get("seri"), "imaj": o["imaj"],
                     "db_adi": o["db_adi"] if tur == "veri" else None, "commit": o.get("commit"), "moduller": moduller,
                     "modul_sayisi": len(moduller), "boyut": boyut, "tarih": kayit.simdi(), "olusturan": kullanici}
            kayit.yaz(gecici / "sablon.json", bilgi, gizli=True)
            if hedef.exists():
                raise Hata(409, f"'{ad}' adlı şablon zaten var.")
            gecici.replace(hedef)
        except Exception:
            shutil.rmtree(gecici, ignore_errors=True)
            raise
        b.yaz(f"Şablon hazır: {ad} ({boyut / 1048576:.1f} MB)")
        return {"sablon": ad}

    def _kod_al(self, b, o, gecici):
        if o.get("yonetim") == "panel":
            if o.get("commit") and Path(o["kod"]).is_dir():
                shutil.copytree(o["kod"], gecici / "kod", ignore=KOD_HARIC)
            if Path(o.get("ek_addons") or "").is_dir():
                shutil.copytree(o["ek_addons"], gecici / "ek-addons", ignore=KOD_HARIC)
            return
        for kaynak, nokta in (o.get("kesif") or {}).get("kod_baglamalari", []):
            if nokta == "/mnt/extra-addons" and Path(kaynak).is_dir():
                shutil.copytree(kaynak, gecici / "ek-addons", ignore=KOD_HARIC, dirs_exist_ok=True)
                b.yaz(f"Ek modüller kopyalandı: {kaynak}")
            else:
                b.uyari(f"Kod bağlaması şablona alınmadı: {kaynak} -> {nokta}")

    def _temizle(self, b, o, gecici):
        """Dökümü geçici bir veritabanına açar, temizler ve temiz halini şablona yazar. Geçici her şey silinir."""
        kimlik = f"sbl{uuid.uuid4().hex[:12]}"
        yollar = self.ortamlar.imaj_bilgisi(o["imaj"])["yollar"]
        t = self.ortamlar.yeni_panel_ortami(kimlik, "production", o["imaj"], yollar)
        kaynak = gecici / "kaynak.dump"
        kurulan = []
        try:
            self.ortamlar.dizin(kimlik, "production").mkdir(parents=True)
            kurulan.append("dizin")
            sifre, ana = yeni_sifre(), yeni_sifre(32)
            self.ortamlar.conf_yaz(t, self.ortamlar.temel_conf(t, sifre, ana))
            self.ortamlar.compose_yaz(t)
            self.ortamlar.birim_olustur(t, b)
            kurulan.append("birim")
            self.ortamlar.db_olustur(t, b, sifre)
            kurulan.append("db")
            self.ortamlar.dokum_yukle(t, b, kaynak)
            aktif = [s for s in self.ortamlar.psql(t, "SELECT id FROM ir_cron WHERE active;").split() if s.isdigit()]
            self.ortamlar.odoo_tek(t, b, [], alt_komut="neutralize", zaman_asimi=900)
            self.ortamlar.psql(t, temizlik_sql(aktif), b=b)
            self.ortamlar.psql(t, ek_notr_sql(), b=b)
            self.ortamlar.psql(t, kimlik_sql("https://sablon.invalid"), b=b)
            sonuc = dict(s.split("=", 1) for s in self.ortamlar.psql(t, DENETIM_SQL, b=b).splitlines() if "=" in s)
            b.yaz(f"Temizlik denetimi: {sonuc}")
            for anahtar, ad in (("kullanici", "etkin kullanıcı"), ("sifre", "kullanıcı şifresi"), ("posta", "posta sunucusu")):
                if sonuc.get(anahtar) != "0":
                    raise Hata(500, f"Temizlikten sonra {ad} kaldı: {sonuc.get(anahtar, 'okunamadı')}")
            self.ortamlar.dokum_al(t, b, gecici / "veritabani.dump")
        finally:
            kaynak.unlink(missing_ok=True)
            if "db" in kurulan:
                try:
                    self.ortamlar.db_sil(t, b, rol_da=True)
                except Exception as hata:  # noqa: BLE001 - asıl hatayı gölgelemesin
                    b.yaz(f"Geçici veritabanı silinemedi: {hata}")
            if "birim" in kurulan:
                b.komut(["docker", "volume", "rm", t["birim"]], kontrol=False)
            if "dizin" in kurulan:
                shutil.rmtree(self.ayar.odoolar / kimlik, ignore_errors=True)

    # ------------------------------------------------------------ kullanım
    def kodu_yerlestir(self, sablon, o):
        """Şablonun kodunu yeni ortamın ek modül klasörüne koyar. Depo bağlanırsa /mnt/repo önce geldiği için depo geçerli olur."""
        kaynak = self.dizin(sablon["ad"])
        for alt in ("ek-addons", "kod"):
            if (kaynak / alt).is_dir():
                shutil.copytree(kaynak / alt, o["ek_addons"], dirs_exist_ok=True)
