#!/usr/bin/env python3
"""Odoo Yönetim Paneli web sunucusu (panel.vekosis.com).

Arayüzü sunar, kullanıcı girişini ve yetkiyi denetler, izin verilen istekleri ajana iletir. Ajanın anahtarını
yalnız bu süreç bilir; tarayıcı ajana doğrudan ulaşamaz. Root yetkisi yoktur, Docker'a erişemez.
GitHub webhook'u (/webhook/github) gövdesine dokunulmadan ajana iletilir; imzayı ajan denetler.

Ortam değişkenleri:
  AJAN_URL      ajanın adresi (ör. http://172.18.0.1:8098)
  AJAN_ANAHTAR  ajanın gizli anahtarı
  PANEL_VERI    kullanıcı ve işlem kaydı klasörü (/veri)
  PANEL_PORT    8080

Komut satırı (ilk kurulum ve acil durum):
  python -m panel kullanici-ekle <ad> [şifre]   platform yöneticisi ekler; şifre verilmezse üretilir
  python -m panel sifre-degistir <ad> [şifre]
  python -m panel kullanicilar
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from .yetki import ROLLER, YETKILER, istek_bul, kapsam_tum, kapsamda, yetkili

AJAN_URL = os.environ.get("AJAN_URL", "http://172.18.0.1:8098").rstrip("/")
AJAN_ANAHTAR = os.environ.get("AJAN_ANAHTAR", "")
VERI = Path(os.environ.get("PANEL_VERI", "/veri"))
PORT = int(os.environ.get("PANEL_PORT", "8080"))
STATIK = Path(__file__).resolve().parent / "static"

OTURUM_SURESI = 12 * 3600
DENEME_SINIRI = 5
KILIT_SURESI = 15 * 60
PBKDF2_TUR = 600_000
EN_AZ_SIFRE = 10
KULLANICI_ADI = r"[a-z0-9._-]{3,30}"
SINIR_JSON = 64 * 1024
SINIR_ZIP = 60 * 1024 * 1024
SINIR_WEBHOOK = 10 * 1024 * 1024
TURLER = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
          ".woff2": "font/woff2"}
GUVENLIK_BASLIKLARI = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}

OTURUMLAR = {}
DENEMELER = {}
KILIT = threading.Lock()


def simdi():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- kullanıcılar

def kullanici_dosyasi():
    return VERI / "kullanicilar.json"


def kullanicilari_oku():
    yol = kullanici_dosyasi()
    return json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}


def kullanicilari_yaz(kullanicilar):
    VERI.mkdir(parents=True, exist_ok=True)
    gecici = kullanici_dosyasi().with_suffix(".tmp")
    gecici.write_text(json.dumps(kullanicilar, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(gecici, 0o600)
    gecici.replace(kullanici_dosyasi())


def sifre_ozeti(sifre, tuz=None):
    tuz = tuz or secrets.token_hex(16)
    ozet = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), PBKDF2_TUR).hex()
    return f"pbkdf2_sha256${PBKDF2_TUR}${tuz}${ozet}"


def sifre_dogru(sifre, kayitli):
    try:
        _yontem, tur, tuz, ozet = kayitli.split("$")
        yeni = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), int(tur)).hex()
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(yeni, ozet)


def kullanici_gorunumu(ad, kayit):
    return {"ad": ad, "rol": kayit.get("rol"), "kapsam": "*" if kapsam_tum(kayit) else kayit.get("kapsam", []),
            "olusturma": kayit.get("olusturma"), "son_giris": kayit.get("son_giris")}


def islem_kaydet(kullanici, ip, olay, odoo=None, kod=None):
    VERI.mkdir(parents=True, exist_ok=True)
    satir = {"zaman": simdi(), "ip": ip, "kullanici": kullanici or "-", "olay": olay}
    if odoo:
        satir["odoo"] = odoo
    if kod is not None:
        satir["kod"] = kod
    with open(VERI / "islem.jsonl", "a", encoding="utf-8") as kayit:
        kayit.write(json.dumps(satir, ensure_ascii=False) + "\n")


def oturumlari_kapat(ad):
    with KILIT:
        for anahtar in [a for a, o in OTURUMLAR.items() if o["kullanici"] == ad]:
            OTURUMLAR.pop(anahtar, None)


# ---------------------------------------------------------------- ajan

def ajana_ilet(yontem, yol, govde=None, kullanici=None, akis=False, basliklar=None, zaman_asimi=60):
    """İsteği ajana iletir; akis=True ise (durum, yanıt nesnesi) döner."""
    ek = {"X-Ajan-Anahtar": AJAN_ANAHTAR, "X-Panel-Kullanici": kullanici or ""}
    if isinstance(govde, (dict, list)):
        govde = json.dumps(govde).encode("utf-8")
        ek["Content-Type"] = "application/json"
    ek.update(basliklar or {})
    istek = urllib.request.Request(f"{AJAN_URL}/{yol}", data=govde, method=yontem, headers=ek)
    try:
        yanit = urllib.request.urlopen(istek, timeout=600 if akis else zaman_asimi)
        if akis:
            return yanit.status, yanit
        with yanit:
            return yanit.status, json.loads(yanit.read() or b"{}")
    except urllib.error.HTTPError as hata:
        try:
            return hata.code, json.loads(hata.read() or b"{}")
        except ValueError:
            return hata.code, {"hata": f"Ajan hatası ({hata.code})."}
    except (urllib.error.URLError, OSError) as hata:
        return 502, {"hata": f"Ajana ulaşılamıyor: {hata}"}


# ---------------------------------------------------------------- HTTP

class Panel(BaseHTTPRequestHandler):
    server_version = "OdooYonetimPaneli/0.1"
    sys_version = ""

    # -- yardımcılar
    def _ip(self):
        ileri = self.headers.get("X-Forwarded-For", "")
        return ileri.split(",")[0].strip() or self.client_address[0]

    def _basliklar(self):
        for ad, deger in GUVENLIK_BASLIKLARI.items():
            self.send_header(ad, deger)

    def _json(self, kod, veri, cerez=None):
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        if cerez is not None:
            self.send_header("Set-Cookie", cerez)
        self._basliklar()
        self.end_headers()
        self.wfile.write(govde)

    def _ham_govde(self, sinir):
        uzunluk = int(self.headers.get("Content-Length") or 0)
        if uzunluk > sinir:
            raise ValueError("istek çok büyük")
        return self.rfile.read(uzunluk) if uzunluk else b""

    def _govde(self):
        ham = self._ham_govde(SINIR_JSON)
        govde = json.loads(ham) if ham else {}
        if not isinstance(govde, dict):
            raise ValueError("geçersiz gövde")
        return govde

    def _oturum(self):
        cerezler = dict(p.strip().split("=", 1) for p in self.headers.get("Cookie", "").split(";") if "=" in p)
        anahtar = cerezler.get("panel_oturum", "")
        with KILIT:
            oturum = OTURUMLAR.get(anahtar)
            if oturum and oturum["bitis"] > time.time():
                return anahtar, oturum
            OTURUMLAR.pop(anahtar, None)
        return None, None

    def _yetki(self, post=False, yetki=None):
        """Oturum, POST'ta CSRF ve istenirse yetki denetimi. Sorun varsa yanıtı yazar, None döner.
        Dönen kayıt kullanıcının GÜNCEL bilgisidir (rolü ya da kapsamı değiştiyse hemen geçerli)."""
        _anahtar, oturum = self._oturum()
        if not oturum:
            self._json(401, {"hata": "Oturum süresi doldu, tekrar giriş yapın."})
            return None
        if post and not hmac.compare_digest(self.headers.get("X-CSRF", ""), oturum["csrf"]):
            self._json(403, {"hata": "Güvenlik denetimi başarısız, sayfayı yenileyin."})
            return None
        kayit = kullanicilari_oku().get(oturum["kullanici"])
        if not kayit:
            self._json(401, {"hata": "Kullanıcı artık yok."})
            return None
        kullanici = {"ad": oturum["kullanici"], **kayit}
        if yetki and not yetkili(kullanici.get("rol"), yetki):
            self._json(403, {"hata": "Bu işlem için yetkiniz yok."})
            return None
        return kullanici

    # -- yönlendirme
    def do_GET(self):  # noqa: N802
        yol = urlsplit(self.path).path
        if yol == "/api/ben":
            return self._ben()
        if yol == "/api/kullanicilar":
            return self._kullanici_listesi()
        if yol == "/api/denetim":
            return self._denetim()
        if yol.startswith("/api/ajan/"):
            return self._ajan("GET", yol[len("/api/ajan/"):])
        return self._statik(yol)

    def do_HEAD(self):  # noqa: N802
        self.send_response(200 if urlsplit(self.path).path in ("/", "/index.html") else 404)
        self._basliklar()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        yol = urlsplit(self.path).path
        if yol == "/webhook/github":
            return self._webhook()
        if yol == "/api/giris":
            return self._giris()
        if yol == "/api/cikis":
            return self._cikis()
        if yol == "/api/sifrem":
            return self._sifrem()
        if yol == "/api/kullanicilar" or yol.startswith("/api/kullanicilar/"):
            return self._kullanici_islem(yol[len("/api/kullanicilar"):].strip("/"))
        if yol.startswith("/api/ajan/"):
            return self._ajan("POST", yol[len("/api/ajan/"):])
        self._json(404, {"hata": "Bulunamadı."})

    # -- statik
    def _statik(self, yol):
        ad = "index.html" if yol in ("/", "") else yol.lstrip("/")
        if ad.startswith("static/"):
            ad = ad[len("static/"):]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?", ad) or ".." in ad:
            return self._json(404, {"hata": "Bulunamadı."})
        dosya = STATIK / ad
        if not dosya.is_file() or dosya.suffix not in TURLER:
            return self._json(404, {"hata": "Bulunamadı."})
        govde = dosya.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TURLER[dosya.suffix])
        self.send_header("Content-Length", str(len(govde)))
        self._basliklar()
        self.end_headers()
        self.wfile.write(govde)

    # -- oturum
    def _ben(self):
        kullanici = self._yetki()
        if not kullanici:
            return
        _anahtar, oturum = self._oturum()
        rol = kullanici.get("rol")
        self._json(200, {"kullanici": kullanici["ad"], "rol": rol, "rol_adi": ROLLER.get(rol, rol),
                         "kapsam": "*" if kapsam_tum(kullanici) else kullanici.get("kapsam", []),
                         "yetkiler": sorted(y for y in YETKILER if yetkili(rol, y)), "csrf": oturum["csrf"]})

    def _giris(self):
        ip = self._ip()
        su_an = time.time()
        with KILIT:
            denemeler = [z for z in DENEMELER.get(ip, []) if su_an - z < KILIT_SURESI]
            DENEMELER[ip] = denemeler
        if len(denemeler) >= DENEME_SINIRI:
            return self._json(429, {"hata": "Çok fazla hatalı deneme. 15 dakika sonra tekrar deneyin."})
        try:
            govde = self._govde()
        except ValueError:
            return self._json(400, {"hata": "Geçersiz istek."})
        ad = str(govde.get("kullanici") or "").strip().lower()
        kayit = kullanicilari_oku().get(ad)
        if not kayit or not sifre_dogru(str(govde.get("sifre") or ""), kayit.get("sifre", "")):
            with KILIT:
                DENEMELER.setdefault(ip, []).append(su_an)
            islem_kaydet(ad, ip, "HATALI GIRIS")
            time.sleep(1)
            return self._json(401, {"hata": "Kullanıcı adı ya da şifre yanlış."})
        anahtar, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with KILIT:
            OTURUMLAR[anahtar] = {"kullanici": ad, "bitis": su_an + OTURUM_SURESI, "csrf": csrf}
            DENEMELER.pop(ip, None)
            kullanicilar = kullanicilari_oku()
            if ad in kullanicilar:
                kullanicilar[ad]["son_giris"] = simdi()
                kullanicilari_yaz(kullanicilar)
        islem_kaydet(ad, ip, "GIRIS")
        cerez = f"panel_oturum={anahtar}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={OTURUM_SURESI}"
        self._json(200, {"kullanici": ad, "rol": kayit.get("rol"), "csrf": csrf}, cerez=cerez)

    def _cikis(self):
        anahtar, oturum = self._oturum()
        if oturum:
            with KILIT:
                OTURUMLAR.pop(anahtar, None)
            islem_kaydet(oturum["kullanici"], self._ip(), "CIKIS")
        self._json(200, {"tamam": True}, cerez="panel_oturum=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0")

    def _sifrem(self):
        kullanici = self._yetki(post=True)
        if not kullanici:
            return
        try:
            govde = self._govde()
        except ValueError:
            return self._json(400, {"hata": "Geçersiz istek."})
        yeni = str(govde.get("yeni") or "")
        with KILIT:
            kullanicilar = kullanicilari_oku()
            kayit = kullanicilar.get(kullanici["ad"])
            if not kayit or not sifre_dogru(str(govde.get("eski") or ""), kayit.get("sifre", "")):
                return self._json(400, {"hata": "Şimdiki şifre yanlış."})
            if len(yeni) < EN_AZ_SIFRE:
                return self._json(400, {"hata": f"Yeni şifre en az {EN_AZ_SIFRE} karakter olmalı."})
            kayit["sifre"] = sifre_ozeti(yeni)
            kullanicilari_yaz(kullanicilar)
        islem_kaydet(kullanici["ad"], self._ip(), "KENDI SIFRESINI DEGISTIRDI")
        self._json(200, {"tamam": True})

    # -- kullanıcı yönetimi
    def _kullanici_listesi(self):
        kullanici = self._yetki(yetki="kullanicilar")
        if not kullanici:
            return
        liste = []
        for ad, kayit in sorted(kullanicilari_oku().items()):
            if kapsam_tum(kullanici) or (not kapsam_tum(kayit) and set(kayit.get("kapsam", [])) <= set(kullanici.get("kapsam", []))):
                liste.append(kullanici_gorunumu(ad, kayit))
        self._json(200, {"kullanicilar": liste, "roller": ROLLER})

    def _kapsam_dogrula(self, yapan, kapsam):
        if kapsam == "*":
            if not kapsam_tum(yapan):
                raise ValueError("Bütün Odoo'ları kapsayan kullanıcıyı yalnız bütün kapsamlı kullanıcı açar.")
            return "*"
        if not isinstance(kapsam, list) or not all(isinstance(k, str) and re.fullmatch(r"[a-z][a-z0-9-]{1,20}[a-z0-9]", k)
                                                   for k in kapsam):
            raise ValueError("Kapsam Odoo adlarının listesi ya da * olmalı.")
        if not kapsam_tum(yapan) and not set(kapsam) <= set(yapan.get("kapsam", [])):
            raise ValueError("Kendi kapsamınızda olmayan Odoo'yu veremezsiniz.")
        return sorted(set(kapsam))

    def _kullanici_islem(self, alt_yol):
        yapan = self._yetki(post=True, yetki="kullanicilar")
        if not yapan:
            return
        try:
            govde = self._govde()
        except ValueError:
            return self._json(400, {"hata": "Geçersiz istek."})
        parca = alt_yol.split("/") if alt_yol else []
        try:
            with KILIT:
                kullanicilar = kullanicilari_oku()
                platform_sayisi = sum(1 for k in kullanicilar.values() if k.get("rol") == "platform")
                if not parca:
                    ad = str(govde.get("ad") or "").strip().lower()
                    rol = str(govde.get("rol") or "kullanici")
                    if not re.fullmatch(KULLANICI_ADI, ad):
                        raise ValueError("Kullanıcı adı 3-30 karakter: küçük harf, rakam, nokta, tire, alt çizgi.")
                    if ad in kullanicilar:
                        raise ValueError(f"'{ad}' adlı kullanıcı zaten var.")
                    if rol not in ROLLER or (rol == "platform" and yapan.get("rol") != "platform"):
                        raise ValueError("Bu rolü veremezsiniz.")
                    kapsam = "*" if rol == "platform" else self._kapsam_dogrula(yapan, govde.get("kapsam", []))
                    sifre = str(govde.get("sifre") or "") or secrets.token_urlsafe(12)
                    if len(sifre) < EN_AZ_SIFRE:
                        raise ValueError(f"Şifre en az {EN_AZ_SIFRE} karakter olmalı.")
                    kullanicilar[ad] = {"sifre": sifre_ozeti(sifre), "rol": rol, "kapsam": kapsam, "olusturma": simdi()}
                    olay, yanit = f"KULLANICI EKLEDI {ad} ({rol})", {**kullanici_gorunumu(ad, kullanicilar[ad]),
                                                                      "sifre": sifre}
                elif len(parca) == 2 and parca[1] in ("rol", "kapsam", "sifre", "sil"):
                    ad, islem = parca
                    hedef = kullanicilar.get(ad)
                    if not hedef:
                        return self._json(404, {"hata": "Böyle bir kullanıcı yok."})
                    if ad == yapan["ad"] and islem != "sifre":
                        raise ValueError("Kendi rolünüzü ya da kapsamınızı değiştiremez, kendinizi silemezsiniz.")
                    if hedef.get("rol") == "platform" and yapan.get("rol") != "platform":
                        raise ValueError("Platform yöneticisini yalnız platform yöneticisi değiştirir.")
                    if not kapsam_tum(yapan) and (kapsam_tum(hedef) or
                                                  not set(hedef.get("kapsam", [])) <= set(yapan.get("kapsam", []))):
                        raise ValueError("Bu kullanıcı kapsamınızın dışında.")
                    if islem == "rol":
                        rol = str(govde.get("rol") or "")
                        if rol not in ROLLER or (rol == "platform" and yapan.get("rol") != "platform"):
                            raise ValueError("Bu rolü veremezsiniz.")
                        if hedef.get("rol") == "platform" and rol != "platform" and platform_sayisi <= 1:
                            raise ValueError("En az bir platform yöneticisi kalmalı.")
                        hedef["rol"] = rol
                        if rol == "platform":
                            hedef["kapsam"] = "*"
                        olay, yanit = f"ROL DEGISTIRDI {ad} -> {rol}", kullanici_gorunumu(ad, hedef)
                    elif islem == "kapsam":
                        if hedef.get("rol") == "platform":
                            raise ValueError("Platform yöneticisinin kapsamı her zaman bütün Odoo'lardır.")
                        hedef["kapsam"] = self._kapsam_dogrula(yapan, govde.get("kapsam"))
                        olay, yanit = f"KAPSAM DEGISTIRDI {ad}", kullanici_gorunumu(ad, hedef)
                    elif islem == "sifre":
                        sifre = secrets.token_urlsafe(12)
                        hedef["sifre"] = sifre_ozeti(sifre)
                        olay, yanit = f"SIFRE SIFIRLADI {ad}", {"ad": ad, "sifre": sifre}
                    else:
                        if hedef.get("rol") == "platform" and platform_sayisi <= 1:
                            raise ValueError("En az bir platform yöneticisi kalmalı.")
                        kullanicilar.pop(ad)
                        olay, yanit = f"KULLANICI SILDI {ad}", {"ad": ad, "silindi": True}
                else:
                    return self._json(404, {"hata": "Bilinmeyen istek."})
                kullanicilari_yaz(kullanicilar)
        except ValueError as hata:
            return self._json(400, {"hata": str(hata)})
        if parca:
            oturumlari_kapat(parca[0])
        islem_kaydet(yapan["ad"], self._ip(), olay)
        self._json(200, yanit)

    def _denetim(self):
        kullanici = self._yetki(yetki="izle")
        if not kullanici:
            return
        yol = VERI / "islem.jsonl"
        satirlar = yol.read_text(encoding="utf-8").splitlines()[-2000:] if yol.exists() else []
        sonuc = []
        for satir in reversed(satirlar):
            try:
                kayit = json.loads(satir)
            except ValueError:
                continue
            if kapsam_tum(kullanici) or kayit.get("kullanici") == kullanici["ad"] or \
                    (kayit.get("odoo") and kapsamda(kullanici, kayit["odoo"])):
                sonuc.append(kayit)
            if len(sonuc) >= 300:
                break
        self._json(200, {"kayitlar": sonuc})

    # -- ajan
    def _ajan(self, yontem, yol):
        yol = yol.strip("/")
        bulunan = istek_bul(yontem, yol)
        if not bulunan:
            return self._json(404, {"hata": "Bilinmeyen istek."})
        eslesme, yetki, kapsam = bulunan
        kullanici = self._yetki(post=yontem == "POST", yetki=yetki)
        if not kullanici:
            return
        odoo = eslesme.group(1) if kapsam == "odoo" else None
        if kapsam == "odoo" and not kapsamda(kullanici, odoo):
            return self._json(404, {"hata": "Bu Odoo bulunamadı."})
        if kapsam == "tum" and not kapsam_tum(kullanici):
            return self._json(403, {"hata": "Bu işlem bütün sunucuyu ilgilendirir; yalnız bütün kapsamlı kullanıcılar."})
        sorgu = parse_qs(urlsplit(self.path).query)
        ajan_yolu = yol
        if yol == "isler":
            istenen = (sorgu.get("odoo") or [""])[0]
            if not kapsam_tum(kullanici) and not (istenen and kapsamda(kullanici, istenen)):
                return self._json(400, {"hata": "İş listesi için Odoo seçin."})
            if istenen:
                ajan_yolu = f"isler?odoo={quote(istenen)}"
        satir = (sorgu.get("satir") or [""])[0]
        if yol.endswith("/loglar") and satir.isdigit():
            ajan_yolu = f"{yol}?satir={satir}"
        try:
            if yol.endswith("/zip") and yontem == "POST":
                govde = self._ham_govde(SINIR_ZIP)
                parametre = {k: (sorgu.get(k) or [""])[0][:500] for k in ("dosya", "hedef", "mesaj")}
                ajan_yolu = f"{yol}?" + "&".join(f"{k}={quote(v)}" for k, v in parametre.items())
                kod, sonuc = ajana_ilet("POST", ajan_yolu, govde, kullanici["ad"],
                                        basliklar={"Content-Type": "application/zip"}, zaman_asimi=120)
            else:
                govde = self._govde() if yontem == "POST" else None
                indirme = yontem == "GET" and "/yedekler/" in yol
                kod, sonuc = ajana_ilet(yontem, ajan_yolu, govde, kullanici["ad"], akis=indirme)
                if indirme and kod == 200:
                    islem_kaydet(kullanici["ad"], self._ip(), f"INDIRDI {yol}", odoo, kod)
                    return self._indir(sonuc)
        except ValueError:
            return self._json(400, {"hata": "Geçersiz istek."})
        if yontem == "POST":
            islem_kaydet(kullanici["ad"], self._ip(), f"POST {yol}", odoo or (govde or {}).get("id")
                         if isinstance(govde, dict) else odoo, kod)
        sonuc = self._suz(kullanici, yontem, yol, kod, sonuc, govde)
        if sonuc is None:
            return self._json(404, {"hata": "Bulunamadı."})
        self._json(kod, sonuc)

    def _suz(self, kullanici, yontem, yol, kod, sonuc, govde):
        """Yanıtı kullanıcının kapsamına göre süzer; görmemesi gereken tek kayıt için None."""
        if kapsam_tum(kullanici) or kod >= 400:
            return sonuc
        if yol == "odoolar" and yontem == "GET":
            sonuc["odoolar"] = [o for o in sonuc.get("odoolar", []) if kapsamda(kullanici, o.get("id"))]
            sonuc.pop("bos_bellek_mb", None)
        elif yol == "odoolar" and yontem == "POST" and kod == 202:
            # kapsamı sınırlı kullanıcının kurduğu Odoo kendi kapsamına eklenir
            with KILIT:
                kullanicilar = kullanicilari_oku()
                kayit = kullanicilar.get(kullanici["ad"])
                if kayit and kayit.get("kapsam") != "*":
                    kayit["kapsam"] = sorted(set(kayit.get("kapsam", [])) | {str((govde or {}).get("id"))})
                    kullanicilari_yaz(kullanicilar)
        elif yol.startswith("isler/") and not kapsamda(kullanici, sonuc.get("odoo") or ""):
            return None
        return sonuc

    def _indir(self, yanit):
        with yanit:
            self.send_response(200)
            for baslik in ("Content-Type", "Content-Length", "Content-Disposition"):
                if yanit.headers.get(baslik):
                    self.send_header(baslik, yanit.headers[baslik])
            self._basliklar()
            self.end_headers()
            while parca := yanit.read(1024 * 1024):
                self.wfile.write(parca)

    def _webhook(self):
        """GitHub -> ajan. Oturum gerekmez; imzayı ajan denetler."""
        try:
            govde = self._ham_govde(SINIR_WEBHOOK)
        except ValueError:
            return self._json(413, {"hata": "İstek çok büyük."})
        basliklar = {ad: self.headers[ad] for ad in ("X-Hub-Signature-256", "X-GitHub-Event", "X-GitHub-Delivery",
                                                      "Content-Type") if self.headers.get(ad)}
        kod, sonuc = ajana_ilet("POST", "webhook/github", govde, "github", basliklar=basliklar)
        islem_kaydet("github", self._ip(), f"WEBHOOK {basliklar.get('X-GitHub-Event', '-')}", None, kod)
        self._json(kod, sonuc)

    def log_message(self, bicim, *args):
        print(f"{simdi()} {self._ip()} {bicim % args}", flush=True)


# ---------------------------------------------------------------- komut satırı

def _komut(arguman):
    kullanicilar = kullanicilari_oku()
    islem = arguman[0] if arguman else ""
    if islem == "kullanicilar":
        for ad in sorted(kullanicilar):
            print(ad, kullanicilar[ad].get("rol"), kullanicilar[ad].get("olusturma", ""))
        return 0
    if islem in ("kullanici-ekle", "sifre-degistir") and len(arguman) >= 2:
        ad = arguman[1].strip().lower()
        if not re.fullmatch(KULLANICI_ADI, ad):
            print("HATA: kullanıcı adı 3-30 karakter: küçük harf, rakam, nokta, tire, alt çizgi")
            return 1
        if (islem == "kullanici-ekle") == (ad in kullanicilar):
            print(f"HATA: {ad} {'zaten var' if ad in kullanicilar else 'yok'}")
            return 1
        sifre = arguman[2] if len(arguman) >= 3 else secrets.token_urlsafe(12)
        if len(sifre) < EN_AZ_SIFRE:
            print(f"HATA: şifre en az {EN_AZ_SIFRE} karakter olmalı")
            return 1
        kayit = kullanicilar.get(ad, {"olusturma": simdi(), "rol": "platform", "kapsam": "*"})
        kayit["sifre"] = sifre_ozeti(sifre)
        kullanicilar[ad] = kayit
        kullanicilari_yaz(kullanicilar)
        print(f"KULLANICI {ad}  SIFRE {sifre}")
        return 0
    print(__doc__)
    return 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        return _komut(argv)
    if not AJAN_ANAHTAR:
        sys.exit("AJAN_ANAHTAR tanımlı değil")
    VERI.mkdir(parents=True, exist_ok=True)
    sunucu = ThreadingHTTPServer(("0.0.0.0", PORT), Panel)
    print(f"{simdi()} Odoo Yönetim Paneli dinliyor: :{PORT} -> ajan {AJAN_URL}", flush=True)
    sunucu.serve_forever()
    return 0
