"""GitHub: App kimliğiyle kısa ömürlü erişim jetonu, REST API çağrıları, webhook imzası.

App bilgisi /opt/odoo-panel/ayar/github_app.json: {"app_id": 123456, "anahtar": "github_app.pem"}
JWT imzası (RS256) sunucudaki openssl ile atılır; standart kitaplıkta RSA yok.
"""
import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from . import kayit
from .hata import Hata

API = "https://api.github.com"


def _b64(veri):
    return base64.urlsafe_b64encode(veri).rstrip(b"=").decode("ascii")


def imza_dogru(sir, govde, imza_basligi):
    """X-Hub-Signature-256 başlığını denetler."""
    if not sir or not imza_basligi or not imza_basligi.startswith("sha256="):
        return False
    beklenen = "sha256=" + hmac.new(sir.encode("utf-8"), govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, imza_basligi)


def urllib_istek(yontem, url, basliklar, govde):
    """Gerçek HTTP isteği; testler bunun yerine sahte işlev verir. (durum, json) döner."""
    istek = urllib.request.Request(url, data=govde, method=yontem, headers=basliklar)
    try:
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            ham = yanit.read()
            return yanit.status, json.loads(ham) if ham else {}
    except urllib.error.HTTPError as hata:
        ham = hata.read()
        try:
            return hata.code, json.loads(ham) if ham else {}
        except ValueError:
            return hata.code, {"message": ham[:300].decode("utf-8", "replace")}
    except (urllib.error.URLError, OSError) as hata:
        raise Hata(502, f"GitHub'a ulaşılamıyor: {hata}") from hata


class GitHub:
    def __init__(self, ayar, komut, http=urllib_istek, saat=time.time):
        self.ayar = ayar
        self.komut = komut
        self.http = http
        self.saat = saat
        self._jetonlar = {}   # kurulum no -> (jeton, bitiş)
        self._kurulumlar = {}  # owner -> kurulum no
        self._kilit = threading.Lock()

    # -- App bilgisi
    def app_bilgisi(self):
        bilgi = kayit.oku(self.ayar.ayar_dizin / "github_app.json")
        if not bilgi or not bilgi.get("app_id") or not bilgi.get("anahtar"):
            return None
        anahtar = self.ayar.ayar_dizin / bilgi["anahtar"]
        if not anahtar.exists():
            return None
        return {"app_id": str(bilgi["app_id"]), "anahtar": anahtar, "ad": bilgi.get("ad", "")}

    def app_var(self):
        return self.app_bilgisi() is not None

    def _jwt(self):
        bilgi = self.app_bilgisi()
        if not bilgi:
            raise Hata(400, "GitHub App bağlantısı kurulmamış.")
        su_an = int(self.saat())
        baslik = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        yuk = _b64(json.dumps({"iat": su_an - 60, "exp": su_an + 540, "iss": bilgi["app_id"]},
                              separators=(",", ":")).encode())
        imzalanacak = f"{baslik}.{yuk}".encode("ascii")
        sonuc = self.komut.calistir(["openssl", "dgst", "-sha256", "-sign", bilgi["anahtar"], "-binary"],
                                    girdi=imzalanacak, ikili=True, zaman_asimi=20)
        return f"{baslik}.{yuk}.{_b64(sonuc.ham)}"

    # -- API
    def istek(self, yontem, yol, govde=None, jeton=None, jwt=False, beklenen=(200, 201, 204)):
        basliklar = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "vekosis-odoo-panel"}
        if jwt:
            basliklar["Authorization"] = f"Bearer {self._jwt()}"
        elif jeton:
            basliklar["Authorization"] = f"token {jeton}"
        veri = None
        if govde is not None:
            veri = json.dumps(govde).encode("utf-8")
            basliklar["Content-Type"] = "application/json"
        durum, yanit = self.http(yontem, API + yol, basliklar, veri)
        if durum not in beklenen:
            mesaj = (yanit or {}).get("message", "") if isinstance(yanit, dict) else ""
            raise Hata(502 if durum >= 500 else 400, f"GitHub {durum}: {mesaj or 'beklenmeyen yanıt'}")
        return yanit

    def jeton(self, depo_adi):
        """Deponun kurulu olduğu App kurulumu için erişim jetonu (önbellekli, bitişten 5 dk önce yenilenir)."""
        sahip = depo_adi.split("/")[0].lower()
        with self._kilit:
            kurulum = self._kurulumlar.get(sahip)
        if kurulum is None:
            yanit = self.istek("GET", f"/repos/{depo_adi}/installation", jwt=True, beklenen=(200,))
            kurulum = yanit["id"]
            with self._kilit:
                self._kurulumlar[sahip] = kurulum
        with self._kilit:
            kayitli = self._jetonlar.get(kurulum)
        if kayitli and kayitli[1] - 300 > self.saat():
            return kayitli[0]
        yanit = self.istek("POST", f"/app/installations/{kurulum}/access_tokens", jwt=True, beklenen=(201,))
        bitis = datetime.strptime(yanit["expires_at"], "%Y-%m-%dT%H:%M:%SZ")
        bitis_sn = (bitis - datetime(1970, 1, 1)).total_seconds()
        with self._kilit:
            self._jetonlar[kurulum] = (yanit["token"], bitis_sn)
        self.komut.gizle(yanit["token"])
        return yanit["token"]

    def pr_ac(self, depo_adi, baslik, aciklama, dal, hedef):
        jeton = self.jeton(depo_adi)
        yanit = self.istek("POST", f"/repos/{depo_adi}/pulls", {"title": baslik, "body": aciklama, "head": dal,
                                                                "base": hedef}, jeton=jeton, beklenen=(201,))
        return {"no": yanit["number"], "adres": yanit["html_url"]}

    def pr_durum(self, depo_adi, no):
        jeton = self.jeton(depo_adi)
        yanit = self.istek("GET", f"/repos/{depo_adi}/pulls/{int(no)}", jeton=jeton, beklenen=(200,))
        return {"no": yanit["number"], "durum": yanit["state"], "birlesti": bool(yanit.get("merged")),
                "adres": yanit["html_url"]}

    def birlestir(self, depo_adi, hedef_dal, kaynak, mesaj):
        """kaynak (dal ya da commit) hedef dala birleştirilir. Zaten içeriyorsa None döner."""
        jeton = self.jeton(depo_adi)
        yanit = self.istek("POST", f"/repos/{depo_adi}/merges",
                           {"base": hedef_dal, "head": kaynak, "commit_message": mesaj}, jeton=jeton,
                           beklenen=(201, 204, 409))
        if isinstance(yanit, dict) and yanit.get("sha"):
            return yanit["sha"]
        if isinstance(yanit, dict) and "conflict" in str(yanit.get("message", "")).lower():
            raise Hata(409, "Birleştirmede çakışma var; GitHub'da elle birleştirin.")
        return None
