"""Odoo kayıtları: /opt/odoo-panel/odoolar/<ad>/odoo.json

{
  "id": "deneme", "firma": "...", "tur": "panel" | "bagli", "kaynak": "panel" | "vtest" | "erp" | "diger",
  "seri": "20.0", "olusturma": "...",
  "depo": {"ad": "sahip/depo", "baglanti": "app" | "anahtar" | "acik",
           "dallar": {"production": "main", "staging": "staging"},
           "kip": {"production": "elle" | "webhook", "staging": "webhook" | "elle"}} | null,
  "islemler_acik": false   # bağlanan kurulumda durdur/başlat izni
}
"""
from . import kayit
from .depo import Depo, dal_denetle, depo_denetle
from .hata import Hata

KIPLER = ("elle", "webhook")


class Odoolar:
    def __init__(self, ayar, komut, github):
        self.ayar = ayar
        self.komut = komut
        self.github = github

    def yol(self, odoo_id):
        return self.ayar.odoolar / odoo_id / "odoo.json"

    def oku(self, odoo_id):
        return kayit.oku(self.yol(odoo_id))

    def gerekli(self, odoo_id):
        od = self.oku(odoo_id) if odoo_id and "/" not in odoo_id and ".." not in odoo_id else None
        if not od:
            raise Hata(404, f"'{odoo_id}' adlı Odoo yok.")
        return od

    def yaz(self, od):
        return kayit.yaz(self.yol(od["id"]), od)

    def liste(self):
        if not self.ayar.odoolar.is_dir():
            return []
        sonuc = []
        for alt in sorted(self.ayar.odoolar.iterdir()):
            od = kayit.oku(alt / "odoo.json")
            if od:
                sonuc.append(od)
        return sonuc

    def depo(self, od):
        bilgi = od.get("depo")
        if not bilgi:
            return None
        return Depo(self.ayar, self.komut, bilgi["ad"], bilgi.get("baglanti", "app"), self.github)

    def depo_gerekli(self, od):
        depo = self.depo(od)
        if depo is None:
            raise Hata(400, "Bu Odoo'ya depo bağlı değil.")
        return depo

    def depo_bagla(self, od, govde):
        """Depo bilgisini doğrulayıp kaydeder (kod çekmez; ilk deploy ayrı istenir)."""
        if od.get("tur") != "panel":
            raise Hata(400, "Depo yalnız panelin kurduğu Odoo'lara bağlanır.")
        ad = depo_denetle(govde.get("ad"))
        baglanti = str(govde.get("baglanti") or "app")
        dallar = govde.get("dallar") or {}
        kip = govde.get("kip") or {}
        bilgi = {
            "ad": ad, "baglanti": baglanti,
            "dallar": {"production": dal_denetle(dallar.get("production") or "main")},
            "kip": {"production": kip.get("production") or "elle"},
        }
        if dallar.get("staging"):
            bilgi["dallar"]["staging"] = dal_denetle(dallar["staging"])
            bilgi["kip"]["staging"] = kip.get("staging") or "webhook"
        if any(k not in KIPLER for k in bilgi["kip"].values()):
            raise Hata(400, "Deploy kipi elle ya da webhook olmalı.")
        if bilgi["dallar"].get("staging") == bilgi["dallar"]["production"]:
            raise Hata(400, "Staging dalı production dalından farklı olmalı.")
        Depo(self.ayar, self.komut, ad, baglanti, self.github)  # bağlantı türünü denetler
        od["depo"] = bilgi
        return self.yaz(od)

    def depo_kaldir(self, od):
        """Depo bağlantısını kaldırır; yayındaki kod ve deploy geçmişi kalır, yeni push gelmez."""
        if not od.get("depo"):
            raise Hata(400, "Bu Odoo'ya depo bağlı değil.")
        od["depo"] = None
        return self.yaz(od)

    def depo_izleyenler(self, depo_adi, dal):
        """Bu depo ve dalı izleyen (odoo, ortam, kip) listesi."""
        sonuc = []
        for od in self.liste():
            bilgi = od.get("depo")
            if not bilgi or bilgi["ad"].lower() != depo_adi.lower():
                continue
            for ortam, izlenen in bilgi.get("dallar", {}).items():
                if izlenen == dal:
                    sonuc.append((od, ortam, bilgi.get("kip", {}).get(ortam, "elle")))
        return sonuc
