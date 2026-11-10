"""Roller, yetkiler ve ajana iletilebilecek istekler.

Roller (önizlemedeki tabloyla aynı):
  platform  kurulumu işleten ekip: her şey, bütün Odoo'lar
  yonetici  paneli kullanan firmanın yöneticisi: terminal dışında her şey, yalnız kapsamındaki Odoo'lar
  kullanici günlük işler: kurma, durdurma/başlatma, yedek, izleme
Kapsam: kullanıcının görebildiği Odoo listesi ya da "*" (hepsi). platform her zaman "*".
"""
import re

ROLLER = {"platform": "Platform yöneticisi", "yonetici": "Yönetici", "kullanici": "Kullanıcı"}

# yetki -> (platform, yonetici, kullanici)
YETKILER = {
    "kur": (1, 1, 1), "durdur": (1, 1, 1), "yedekAl": (1, 1, 1), "izle": (1, 1, 1),
    "geriYukle": (1, 1, 0), "yedekYukle": (1, 1, 0), "sil": (1, 1, 0), "alanAdi": (1, 1, 0), "modul": (1, 1, 0),
    "deploy": (1, 1, 0), "stagingYenile": (1, 1, 0), "github": (1, 1, 0), "asistan": (1, 1, 0), "eposta": (1, 1, 0),
    "kullanicilar": (1, 1, 0), "sablon": (1, 1, 0), "bagla": (1, 1, 0), "yukseltme": (1, 1, 0), "isler": (1, 1, 0),
    "destek": (1, 1, 0), "terminal": (1, 0, 0),
}
SUTUN = {"platform": 0, "yonetici": 1, "kullanici": 2}

AD = r"[a-z][a-z0-9-]{1,20}[a-z0-9]"
ORT = r"production|staging"
YEDEK = r"[A-Za-z0-9._-]+\.tar"

# (yöntem, yol deseni, yetki, kapsam): kapsam "odoo" = yoldaki ilk grup Odoo kimliği; "tum" = yalnız "*" kapsamlılar;
# "yok" = kapsamdan bağımsız (yanıt gerekirse süzülür)
ISTEKLER = [
    ("GET", r"saglik", "izle", "yok"),
    ("GET", r"odoolar", "izle", "yok"),
    ("POST", r"odoolar", "kur", "yok"),
    ("GET", r"sablon", "kur", "yok"),
    ("GET", r"bulunanlar", "bagla", "tum"),
    ("POST", r"bagla", "bagla", "tum"),
    ("GET", rf"odoolar/({AD})", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/giris", "kur", "odoo"),
    ("POST", rf"odoolar/({AD})/baglantiyi-kaldir", "bagla", "tum"),
    ("POST", rf"odoolar/({AD})/islemler", "bagla", "tum"),
    ("POST", rf"odoolar/({AD})/depo", "github", "odoo"),
    ("POST", rf"odoolar/({AD})/depo/anahtar", "github", "odoo"),
    ("POST", rf"odoolar/({AD})/depo/kaldir", "github", "odoo"),
    ("POST", rf"odoolar/({AD})/sil", "sil", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/moduller", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/loglar", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/onde", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/zip-pr", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/durum", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/izleme", "izle", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/(durdur|baslat)", "durdur", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/deploylar", "izle", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/deploylar/(\d+)", "izle", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/deploy", "deploy", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/geri-al", "deploy", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/uyumluluk", "deploy", "odoo"),
    ("POST", rf"odoolar/({AD})/production/production-al", "deploy", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/yedekler", "yedekAl", "odoo"),
    ("GET", rf"odoolar/({AD})/({ORT})/yedekler/({YEDEK})", "yedekAl", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/yedek", "yedekAl", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/geri-yukle", "geriYukle", "odoo"),
    ("POST", rf"odoolar/({AD})/staging/(olustur|yenile|sil)", "stagingYenile", "odoo"),
    ("POST", rf"odoolar/({AD})/yedek-staging", "stagingYenile", "odoo"),
    ("POST", rf"odoolar/({AD})/({ORT})/zip", "modul", "odoo"),
    ("GET", r"isler", "izle", "yok"),
    ("GET", r"isler/([0-9a-f]{12})", "izle", "yok"),
]


def yetkili(rol, yetki):
    satir = YETKILER.get(yetki)
    return bool(satir and rol in SUTUN and satir[SUTUN[rol]])


def kapsam_tum(kullanici):
    return kullanici.get("rol") == "platform" or kullanici.get("kapsam") == "*"


def kapsamda(kullanici, odoo_id):
    if kapsam_tum(kullanici):
        return True
    return odoo_id in (kullanici.get("kapsam") or [])


def istek_bul(yontem, yol):
    """(desen eşleşmesi, yetki, kapsam türü) ya da None."""
    for r_yontem, desen, yetki, kapsam in ISTEKLER:
        if r_yontem == yontem:
            eslesme = re.fullmatch(desen, yol)
            if eslesme:
                return eslesme, yetki, kapsam
    return None
