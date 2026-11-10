"""Ajanın HTTP arayüzü. Yalnız panel konteynerinin IP'sinden ve gizli anahtarla gelen istekler kabul edilir.

İstekte X-Ajan-Anahtar başlığı ve panelin işlemi yapan kullanıcısı (X-Panel-Kullanici, kayıt için) gelir.
Yetki ve kapsam denetimini panel yapar; ajan yalnız adları ve değerleri doğrular.
"""
import hmac
import json
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import SURUM, kayit
from .depo import Depo
from .hata import Hata
from .komut import KomutHatasi

AD = r"[a-z][a-z0-9-]{1,20}[a-z0-9]"
ORT = r"production|staging"
SINIR_JSON = 64 * 1024
SINIR_ZIP = 60 * 1024 * 1024
SINIR_WEBHOOK = 10 * 1024 * 1024


class Dosya:
    def __init__(self, yol, tur="application/x-tar"):
        self.yol = Path(yol)
        self.tur = tur


def rotalar(s):
    """(yöntem, desen, işlev(eşleşme, gövde, istek)) listesi."""
    k = lambda istek: istek.kullanici  # noqa: E731

    def is_(kayit_):
        return 202, kayit_

    return [
        ("GET", r"saglik", lambda m, g, i: (200, {"durum": "ok", "surum": SURUM, "alan": s.ayar.alan,
                                                  "kuru": s.ayar.kuru, "app": s.github.app_var()})),
        ("GET", r"odoolar", lambda m, g, i: (200, s.odoo_listesi())),
        ("POST", r"odoolar", lambda m, g, i: is_(s.kurulum.kur(g, k(i)))),
        ("GET", r"sablon", lambda m, g, i: (200, {"sablon": s.kurulum.sablon()})),
        ("GET", r"bulunanlar", lambda m, g, i: (200, {"bulunanlar": s.kurulum.bulunanlar()})),
        ("POST", r"bagla", lambda m, g, i: (200, s.kurulum.bagla(g, k(i)))),
        ("GET", rf"odoolar/({AD})", lambda m, g, i: (200, s.odoo_ozeti(s.odoolar.gerekli(m[1]), durum=True))),
        ("GET", rf"odoolar/({AD})/giris", lambda m, g, i: (200, s.giris_bilgisi(m[1]))),
        ("POST", rf"odoolar/({AD})/baglantiyi-kaldir", lambda m, g, i: (200, s.kurulum.baglantiyi_kaldir(m[1]))),
        ("POST", rf"odoolar/({AD})/islemler", lambda m, g, i: (200, _islemler(s, m[1], g))),
        # depo
        ("POST", rf"odoolar/({AD})/depo", lambda m, g, i: (200, s.odoolar.depo_bagla(s.odoolar.gerekli(m[1]), g))),
        ("POST", rf"odoolar/({AD})/depo/anahtar", lambda m, g, i: (200, {"acik_anahtar": _anahtar(s, g)})),
        ("POST", rf"odoolar/({AD})/depo/kaldir", lambda m, g, i: (200, s.odoolar.depo_kaldir(s.odoolar.gerekli(m[1])))),
        ("POST", rf"odoolar/({AD})/sil",
         lambda m, g, i: is_(s.kurulum.sil(m[1], g.get("onay"), s.staging, s.yedekler, k(i)))),
        ("GET", rf"odoolar/({AD})/({ORT})/moduller", lambda m, g, i: (200, s.moduller(m[1], m[2]))),
        ("GET", rf"odoolar/({AD})/({ORT})/loglar", lambda m, g, i: (200, s.loglar(m[1], m[2], _satir(i)))),
        ("GET", rf"odoolar/({AD})/onde", lambda m, g, i: (200, {"commitler": s.deploylar.onde(m[1])})),
        ("GET", rf"odoolar/({AD})/zip-pr", lambda m, g, i: (200, {"pr": _zip_pr(s, m[1])})),
        # ortam
        ("GET", rf"odoolar/({AD})/({ORT})/durum", lambda m, g, i: (200, _durum(s, m[1], m[2]))),
        ("GET", rf"odoolar/({AD})/({ORT})/izleme", lambda m, g, i: (200, s.izleme.ozet(m[1], m[2], i.sorgu.get("saat", 24)))),
        ("POST", rf"odoolar/({AD})/({ORT})/(durdur|baslat)",
         lambda m, g, i: is_(s.durdur_baslat(m[1], m[2], m[3], k(i)))),
        ("GET", rf"odoolar/({AD})/({ORT})/deploylar", lambda m, g, i: (200, {"deploylar": s.deploylar.kayitlar(m[1], m[2])})),
        ("GET", rf"odoolar/({AD})/({ORT})/deploylar/(\d+)", lambda m, g, i: (200, _deploy(s, m[1], m[2], m[3]))),
        ("POST", rf"odoolar/({AD})/({ORT})/deploy",
         lambda m, g, i: is_(s.deploylar.baslat(m[1], m[2], commit=g.get("commit"), kullanici=k(i)))),
        ("POST", rf"odoolar/({AD})/({ORT})/geri-al",
         lambda m, g, i: is_(s.deploylar.geri_al(m[1], m[2], g.get("no"), str(g.get("kip") or ""), k(i)))),
        ("POST", rf"odoolar/({AD})/({ORT})/uyumluluk", lambda m, g, i: is_(s.deploylar.uyumluluk_isi(m[1], m[2], k(i)))),
        ("POST", rf"odoolar/({AD})/production/production-al",
         lambda m, g, i: is_(s.deploylar.production_al(m[1], s.github, k(i)))),
        ("GET", rf"odoolar/({AD})/({ORT})/yedekler", lambda m, g, i: (200, {"yedekler": s.yedekler.liste(m[1], m[2])})),
        ("GET", rf"odoolar/({AD})/({ORT})/yedekler/([A-Za-z0-9._-]+\.tar)",
         lambda m, g, i: (200, Dosya(s.yedekler.yol(m[1], m[2], m[3])))),
        ("POST", rf"odoolar/({AD})/({ORT})/yedek", lambda m, g, i: is_(s.yedek_al(m[1], m[2], k(i)))),
        ("POST", rf"odoolar/({AD})/({ORT})/geri-yukle",
         lambda m, g, i: is_(s.geri_yukle(m[1], m[2], g.get("dosya"), g.get("onay"), k(i)))),
        # staging
        ("POST", rf"odoolar/({AD})/staging/olustur", lambda m, g, i: is_(s.staging.olustur(m[1], k(i)))),
        ("POST", rf"odoolar/({AD})/staging/yenile", lambda m, g, i: is_(s.staging.yenile(m[1], k(i)))),
        ("POST", rf"odoolar/({AD})/staging/sil", lambda m, g, i: is_(_staging_sil(s, m[1], g, k(i)))),
        ("POST", rf"odoolar/({AD})/yedek-staging",
         lambda m, g, i: is_(s.staging.yedekten_ac(m[1], str(g.get("dosya") or ""), k(i)))),
        # asistan ve bağlı ajanlar (yalnız panelin araç katmanı çağırır)
        ("GET", rf"odoolar/({AD})/({ORT})/kod", lambda m, g, i: (200, s.asistan.kod_listele(m[1], m[2], i.sorgu.get("yol", "")))),
        ("GET", rf"odoolar/({AD})/({ORT})/kod/oku", lambda m, g, i: (200, s.asistan.kod_oku(
            m[1], m[2], i.sorgu.get("yol", ""), _sayi(i.sorgu.get("bas")), _sayi(i.sorgu.get("son"))))),
        ("GET", rf"odoolar/({AD})/({ORT})/kod/ara", lambda m, g, i: (200, s.asistan.kod_ara(
            m[1], m[2], i.sorgu.get("desen", ""), i.sorgu.get("yol", "")))),
        ("POST", rf"odoolar/({AD})/({ORT})/sql", lambda m, g, i: (200, s.asistan.sql_oku(m[1], m[2], g.get("sorgu")))),
        ("POST", rf"odoolar/({AD})/staging/asistan-commit", lambda m, g, i: is_(s.asistan.staging_commit(
            m[1], g.get("dosyalar"), g.get("mesaj"), k(i), s.isler))),
        # işler
        ("GET", r"isler", lambda m, g, i: (200, {"isler": s.isler.liste(
            odoo=i.sorgu.get("odoo"), idler=[x for x in i.sorgu.get("idler", "").split(",") if x] or None)})),
        ("GET", r"isler/([0-9a-f]{12})", lambda m, g, i: (200, s.isler.oku(m[1]))),
        ("POST", r"gece-yedegi", lambda m, g, i: (202, {"isler": s.gece_yedegi()})),
    ]


def _sayi(deger):
    deger = str(deger or "")
    return int(deger) if deger.isdigit() else None


def _satir(istek):
    deger = str(istek.sorgu.get("satir", ""))
    return int(deger) if deger.isdigit() else 300


def _islemler(s, odoo_id, govde):
    od = s.odoolar.gerekli(odoo_id)
    if od.get("tur") != "bagli":
        raise Hata(400, "Bu ayar yalnız bağlanan kurulumlarda.")
    od["islemler_acik"] = bool(govde.get("acik"))
    return s.odoolar.yaz(od)


def _anahtar(s, govde):
    depo = Depo(s.ayar, s.komut, govde.get("ad"), "anahtar", s.github)
    return depo.anahtar_uret()


def _zip_pr(s, odoo_id):
    od = s.odoolar.gerekli(odoo_id)
    liste = []
    for pr in od.get("zip_pr", [])[:5]:
        try:
            pr = {**pr, **s.github.pr_durum(od["depo"]["ad"], pr["no"])}
        except Hata as hata:
            pr = {**pr, "hata": hata.mesaj}
        liste.append(pr)
    return liste


def _durum(s, odoo_id, ortam):
    o = s.ortamlar.gerekli(odoo_id, ortam)
    ozet = s.ortam_ozeti(o, durum=True)
    ozet["kaynak"] = s.ortamlar.istatistik([o["konteyner"]]).get(o["konteyner"])
    return ozet


def _deploy(s, odoo_id, ortam, no):
    d = s.deploylar.kayit_oku(odoo_id, ortam, no)
    if d.get("is"):
        try:
            d["cikti"] = s.isler.oku(d["is"], satir=400).get("cikti", "")
        except Hata:
            d["cikti"] = ""
    return d


def _staging_sil(s, odoo_id, govde, kullanici):
    st = s.ortamlar.gerekli(odoo_id, "staging")
    beklenen = st["adres"].replace("https://", "")
    if str(govde.get("onay") or "").strip().lower() != beklenen:
        raise Hata(400, f"Onay için tam adres yazılmalı: {beklenen}")
    return s.staging.sil(odoo_id, kullanici)


class Istek(BaseHTTPRequestHandler):
    servis = None
    anahtar = ""
    rota_listesi = []
    _ip = {"zaman": 0.0, "ipler": set()}
    _yerel = {"zaman": 0.0, "ipler": set()}
    _ip_kilit = threading.Lock()
    server_version = f"OdooPanelAjan/{SURUM}"
    sys_version = ""

    # -- erişim
    def _panel_ipleri(self, yenile=False):
        with self._ip_kilit:
            if yenile or time.time() - self._ip["zaman"] > 30:
                sonuc = self.servis.komut.calistir(
                    ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
                     self.servis.ayar.izinli_konteyner], kontrol=False, zaman_asimi=15)
                self._ip["ipler"] = set(sonuc.cikti.split()) if sonuc.tamam else set()
                self._ip["zaman"] = time.time()
            return self._ip["ipler"]

    def _sunucu_ipleri(self):
        """Sunucunun kendi IPv4 adresleri.

        Sunucudan ajana giden istek (gece yedeği zamanlayıcısı, "python3 -m ajan saglik") Docker'ın NAT kuralından
        geçer (POSTROUTING -s <ağ> ! -o <köprü> MASQUERADE) ve ajana sunucunun genel adresiyle gelir. Dışarıdan
        bu adreslerle gelen paketi çekirdek zaten atar (martian source); anahtar denetimi ayrıca yapılır."""
        with self._ip_kilit:
            if time.time() - self._yerel["zaman"] > 30:
                sonuc = self.servis.komut.calistir(["ip", "-o", "-4", "addr", "show"], kontrol=False, zaman_asimi=15)
                self._yerel["ipler"] = (set(re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)/", sonuc.cikti))
                                        if sonuc.tamam else set())
                self._yerel["zaman"] = time.time()
            return self._yerel["ipler"]

    def _izinli(self):
        if self.servis.ayar.kuru:
            return True
        ip = self.client_address[0]
        # sunucunun kendisi; konteynerler kendi IP'leriyle gelir, yalnız panel konteyneri kabul edilir
        if ip in ("127.0.0.1", self.servis.ayar.adres) or ip in self._sunucu_ipleri():
            return True
        return ip in self._panel_ipleri() or ip in self._panel_ipleri(yenile=True)

    # -- yanıt
    def _yanit(self, kod, veri):
        govde = json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def _dosya(self, dosya):
        self.send_response(200)
        self.send_header("Content-Type", dosya.tur)
        self.send_header("Content-Length", str(dosya.yol.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{dosya.yol.name}"')
        self.end_headers()
        with open(dosya.yol, "rb") as kaynak:
            while parca := kaynak.read(1024 * 1024):
                self.wfile.write(parca)

    def _govde(self, sinir):
        uzunluk = int(self.headers.get("Content-Length") or 0)
        if uzunluk > sinir:
            raise Hata(413, "İstek çok büyük.")
        return self.rfile.read(uzunluk) if uzunluk else b""

    # -- işleme
    def _isle(self, yontem):
        if not self._izinli():
            return self._yanit(403, {"hata": "Bu adresten istek kabul edilmiyor."})
        gelen = self.headers.get("X-Ajan-Anahtar", "")
        if not self.anahtar or not hmac.compare_digest(gelen.encode("utf-8"), self.anahtar.encode("utf-8")):
            return self._yanit(403, {"hata": "Ajan anahtarı yanlış."})
        parca = urlsplit(self.path)
        yol = unquote(parca.path).strip("/")
        self.sorgu = {k: v[0] for k, v in parse_qs(parca.query).items()}
        self.kullanici = re.sub(r"[^a-z0-9._-]", "", (self.headers.get("X-Panel-Kullanici") or "").lower())[:30] or None
        try:
            if yontem == "POST" and yol == "webhook/github":
                veri = self.servis.webhook.isle(self._govde(SINIR_WEBHOOK), dict(self.headers.items()))
                return self._yanit(200, veri)
            eslesme = re.fullmatch(rf"odoolar/({AD})/({ORT})/zip", yol)
            if yontem == "POST" and eslesme:
                veri = self._govde(SINIR_ZIP)
                is_kaydi = self.servis.zipdepo.yukle(eslesme[1], eslesme[2], veri, self.sorgu.get("dosya", "modul.zip"),
                                                     self.sorgu.get("hedef", "dal"), self.sorgu.get("mesaj", ""),
                                                     self.kullanici)
                return self._yanit(202, is_kaydi)
            govde = {}
            if yontem == "POST":
                ham = self._govde(SINIR_JSON)
                govde = json.loads(ham) if ham else {}
                if not isinstance(govde, dict):
                    raise Hata(400, "Geçersiz istek gövdesi.")
            for r_yontem, desen, islev in self.rota_listesi:
                if r_yontem != yontem:
                    continue
                eslesme = re.fullmatch(desen, yol)
                if eslesme:
                    kod, veri = islev(eslesme, govde, self)
                    if isinstance(veri, Dosya):
                        return self._dosya(veri)
                    return self._yanit(kod, veri)
            raise Hata(404, "Bilinmeyen istek.")
        except (Hata, KomutHatasi) as hata:
            veri = {"hata": hata.mesaj}
            if getattr(hata, "ayrinti", None):
                veri["ayrinti"] = hata.ayrinti
            self._yanit(hata.kod, veri)
        except (ValueError, json.JSONDecodeError):
            self._yanit(400, {"hata": "Geçersiz istek."})
        except Exception as hata:  # noqa: BLE001 - panele hata olarak döner
            self.log_message("BEKLENMEYEN HATA %s", hata)
            self._yanit(500, {"hata": f"Ajanda beklenmeyen bir hata oluştu: {type(hata).__name__}: {hata}",
                              "ayrinti": traceback.format_exc()[-4000:]})

    def do_GET(self):  # noqa: N802
        self._isle("GET")

    def do_POST(self):  # noqa: N802
        self._isle("POST")

    def log_message(self, bicim, *args):
        print(f"{kayit.simdi()} {self.client_address[0]} {bicim % args}", flush=True)


def calistir(servis, anahtar):
    Istek.servis = servis
    Istek.anahtar = anahtar
    Istek.rota_listesi = rotalar(servis)
    sunucu = ThreadingHTTPServer((servis.ayar.adres, servis.ayar.port), Istek)
    if not servis.ayar.kuru:
        servis.izleme.baslat()  # dakikada bir ölçüm (izleme.py)
    print(f"{kayit.simdi()} Odoo Yönetim Paneli ajanı {SURUM} dinliyor: {servis.ayar.adres}:{servis.ayar.port} "
          f"(kuru={servis.ayar.kuru})", flush=True)
    sunucu.serve_forever()
