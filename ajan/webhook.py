"""GitHub webhook'u: imza denetimi ve push olayına göre deploy.

Panel konteyneri /webhook/github isteğini gövdeye ve başlıklara dokunmadan ajana iletir; imzayı ajan denetler
(sır yalnız ajanın klasöründe: /opt/odoo-panel/ayar/webhook_sirri).
Push geldiğinde o depo ve dalı izleyen ortamlar:
  kip webhook -> deploy sıraya girer (aynı ortamda süren deploy varsa bekler; en son commit kazanır)
  kip elle    -> "yayına alınmayı bekliyor" olarak işaretlenir
"""
import json
import re

from . import kayit
from .github import imza_dogru
from .hata import Hata

TESLIM_SAKLA = 500


class Webhook:
    def __init__(self, ayar, odoolar, ortamlar, deploylar):
        self.ayar = ayar
        self.odoolar = odoolar
        self.ortamlar = ortamlar
        self.deploylar = deploylar

    def sir(self):
        yol = self.ayar.ayar_dizin / "webhook_sirri"
        return yol.read_text(encoding="utf-8").strip() if yol.exists() else ""

    def isle(self, govde, basliklar):
        basliklar = {k.lower(): v for k, v in basliklar.items()}
        if not imza_dogru(self.sir(), govde, basliklar.get("x-hub-signature-256", "")):
            raise Hata(401, "Webhook imzası geçersiz.")
        olay = basliklar.get("x-github-event", "")
        teslim = basliklar.get("x-github-delivery", "")
        if teslim and not self._yeni_teslim(teslim):
            return {"durum": "tekrar", "teslim": teslim}
        if olay == "ping":
            return {"durum": "tamam", "olay": "ping"}
        if olay != "push":
            return {"durum": "yok sayildi", "olay": olay}
        try:
            veri = json.loads(govde)
        except ValueError as hata:
            raise Hata(400, "Webhook gövdesi JSON değil.") from hata
        ref = veri.get("ref") or ""
        sonra = veri.get("after") or ""
        if veri.get("deleted") or not ref.startswith("refs/heads/") or not re.match(r"^[0-9a-f]{40}$", sonra) \
                or set(sonra) == {"0"}:
            return {"durum": "yok sayildi", "neden": "dal silindi ya da dal dışı ref"}
        depo_adi = (veri.get("repository") or {}).get("full_name") or ""
        dal = ref[len("refs/heads/"):]
        bas = veri.get("head_commit") or {}
        bilgi = {"baslik": (bas.get("message") or "").splitlines()[0][:200] if bas.get("message") else "",
                 "yazar": ((bas.get("author") or {}).get("name") or (veri.get("pusher") or {}).get("name") or "")[:80]}
        tetiklenen = self.push(depo_adi, dal, sonra, tetik="webhook", kullanici=bilgi["yazar"], bilgi=bilgi)
        return {"durum": "tamam", "depo": depo_adi, "dal": dal, "commit": sonra, "ortamlar": tetiklenen}

    def push(self, depo_adi, dal, sha, tetik="webhook", kullanici=None, bilgi=None):
        """Dala yeni commit geldi: izleyen ortamlar için deploy ya da bekleyen işareti."""
        sonuc = []
        for od, ortam, kip in self.odoolar.depo_izleyenler(depo_adi, dal):
            o = self.ortamlar.oku(od["id"], ortam)
            if not o or o.get("yonetim") != "panel":
                continue
            if o.get("commit") == sha:
                sonuc.append({"odoo": od["id"], "ortam": ortam, "durum": "zaten yayında"})
                continue
            if kip == "webhook":
                is_kaydi = self.deploylar.baslat(od["id"], ortam, commit=sha, tetik=tetik, kullanici=kullanici,
                                                 kuyruk=True)
                sonuc.append({"odoo": od["id"], "ortam": ortam, "durum": "deploy", "is": is_kaydi["id"]})
            else:
                o["bekleyen"] = {"commit": sha, "tarih": kayit.simdi(), **(bilgi or {})}
                self.ortamlar.yaz(o)
                sonuc.append({"odoo": od["id"], "ortam": ortam, "durum": "bekliyor"})
        return sonuc

    def _yeni_teslim(self, teslim):
        yol = self.ayar.onbellek / "webhook_teslim.json"
        liste = kayit.oku(yol, []) or []
        if teslim in liste:
            return False
        liste.append(teslim)
        kayit.yaz(yol, liste[-TESLIM_SAKLA:])
        return True
