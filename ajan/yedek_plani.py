"""Otomatik yedek planı: genel varsayılan + platform başına değiştirme.

Genel plan /opt/odoo-panel/ayar/yedek_plani.json dosyasında, platformun planı odoo.json'da "yedek_plani" alanında
durur (yoksa genel plan geçerlidir). Plan:
  periyot_saat  0 (kapalı), 6, 12, 24, 48 ya da 168 (haftalık)
  saat          yedeklerin saati (0-23); 6 ve 12 saatlikte gün bu saatten başlayarak bölünür
  saklama_gun   otomatik yedeklerin kaç gün tutulacağı (1-365)
Zamanlayıcı saatte bir (xx:20) turu çalıştırır. Her ortam (production ve varsa staging) için zamanı geldiyse
OTOMATIK yedeği alınır; saklama süresini aşan otomatik yedekler silinir, en yenisi her zaman kalır.
Eski GECE etiketli yedekler de otomatik sayılır.
"""
from datetime import datetime, timedelta

from . import kayit
from .hata import Hata

PERIYOTLAR = (0, 6, 12, 24, 48, 168)
VARSAYILAN = {"periyot_saat": 24, "saat": 4, "saklama_gun": 7}
OTOMATIK = ("OTOMATIK", "GECE")
DAKIKA = 20  # zamanlayıcının dakikası (odoo-panel-gece-yedek.timer)


def plan_denetle(govde):
    govde = govde if isinstance(govde, dict) else {}
    try:
        plan = {k: int(govde.get(k, VARSAYILAN[k])) for k in VARSAYILAN}
    except (TypeError, ValueError):
        raise Hata(400, "Yedek planındaki değerler sayı olmalı.") from None
    if plan["periyot_saat"] not in PERIYOTLAR:
        raise Hata(400, "Yedek sıklığı kapalı, 6, 12, 24, 48 ya da 168 saat olmalı.")
    if not 0 <= plan["saat"] <= 23:
        raise Hata(400, "Yedek saati 0 ile 23 arasında olmalı.")
    if not 1 <= plan["saklama_gun"] <= 365:
        raise Hata(400, "Saklama süresi 1 ile 365 gün arasında olmalı.")
    return plan


def yuvada(plan, an):
    """Bu saat, planın yedek saatlerinden biri mi?"""
    adim = min(plan["periyot_saat"], 24)
    return (an.hour - plan["saat"]) % adim == 0


def zamani_geldi(plan, son, an):
    """Saatlik turda bu ortamın otomatik yedeği alınmalı mı? son: en yeni otomatik yedeğin zamanı ya da None."""
    periyot = plan["periyot_saat"]
    if not periyot:
        return False
    if son is None:
        return yuvada(plan, an)
    gecen = (an - son).total_seconds() / 3600
    if gecen >= periyot + 2:  # sunucu kapalıyken kaçırılan yedek
        return True
    return gecen >= periyot - 0.5 and yuvada(plan, an)


def sonraki(plan, son, an):
    """Sonraki otomatik yedeğin yaklaşık zamanı (saat başı + DAKIKA) ya da None."""
    if not plan["periyot_saat"]:
        return None
    aday = an.replace(minute=DAKIKA, second=0, microsecond=0)
    if aday < an:
        aday += timedelta(hours=1)
    for _ in range(24 * 9):
        if zamani_geldi(plan, son, aday):
            return aday
        aday += timedelta(hours=1)
    return None


class YedekPlani:
    def __init__(self, ayar, isler, ortamlar, odoolar, yedekler):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.yedekler = yedekler

    @property
    def yol(self):
        return self.ayar.ayar_dizin / "yedek_plani.json"

    # ------------------------------------------------------------ ayarlar
    def genel(self):
        return {**VARSAYILAN, **(kayit.oku(self.yol) or {})}

    def genel_yaz(self, govde):
        plan = plan_denetle(govde)
        kayit.yaz(self.yol, plan)
        return plan

    def gecerli(self, od):
        return od.get("yedek_plani") or self.genel()

    def platform(self, odoo_id, an=None):
        od = self.odoolar.gerekli(odoo_id)
        an = an or datetime.now()
        gecerli = self.gecerli(od)
        ortamlar = {}
        for ortam in ("production", "staging"):
            if self.ortamlar.oku(odoo_id, ortam):
                son = self._son(odoo_id, ortam)
                ortamlar[ortam] = {"son": son.isoformat(timespec="seconds") if son else None,
                                   "sonraki": _iso(sonraki(gecerli, son, an))}
        return {"genel": self.genel(), "ozel": od.get("yedek_plani"), "gecerli": gecerli, "ortamlar": ortamlar}

    def platform_yaz(self, odoo_id, govde):
        od = self.odoolar.gerekli(odoo_id)
        ozel = (govde or {}).get("ozel")
        if ozel:
            od["yedek_plani"] = plan_denetle(ozel)
        else:
            od.pop("yedek_plani", None)
        self.odoolar.yaz(od)
        return self.platform(odoo_id)

    def ozet(self, an=None):
        an = an or datetime.now()
        platformlar = []
        for od in self.odoolar.liste():
            bilgi = self.platform(od["id"], an)
            platformlar.append({"id": od["id"], "firma": od.get("firma"), "ozel": bool(bilgi["ozel"]),
                                "gecerli": bilgi["gecerli"], "ortamlar": bilgi["ortamlar"]})
        return {"genel": self.genel(), "periyotlar": list(PERIYOTLAR), "dakika": DAKIKA, "platformlar": platformlar}

    # ------------------------------------------------------------ saatlik tur
    def _son(self, odoo_id, ortam):
        for yedek in self.yedekler.liste(odoo_id, ortam):  # en yeni önce
            if yedek["etiket"] in OTOMATIK:
                return datetime.fromisoformat(yedek["tarih"])
        return None

    def tur(self, an=None):
        """Zamanlayıcı saatte bir çağırır: zamanı gelen ortamların yedeği sıraya girer, eski otomatik yedekler silinir."""
        an = an or datetime.now()
        sonuc = []
        for od in self.odoolar.liste():
            plan = self.gecerli(od)
            for ortam in ("production", "staging"):
                o = self.ortamlar.oku(od["id"], ortam)
                if not o:
                    continue
                satir = {"odoo": od["id"], "ortam": ortam}
                silinen = self.yedekler.otomatik_temizle(od["id"], ortam, plan["saklama_gun"], an, OTOMATIK)
                if silinen:
                    satir["silinen"] = silinen
                if not zamani_geldi(plan, self._son(od["id"], ortam), an):
                    satir["durum"] = "kapali" if not plan["periyot_saat"] else "bekliyor"
                elif self.ortamlar.konteyner_durumu(o) == "yok":
                    satir["durum"] = "konteyner-yok"
                else:
                    try:
                        is_kaydi = self.isler.baslat(
                            "yedek", f"{od['id']}/{ortam}", lambda b, o=o: self.yedekler.al(o, b, "OTOMATIK"),
                            odoo=od["id"], ortam=ortam, kuyruk=True, aciklama="Otomatik yedek")
                        satir.update(durum="alindi", **{"is": is_kaydi["id"]})
                    except Hata as hata:
                        satir.update(durum="hata", hata=hata.mesaj)
                sonuc.append(satir)
        return sonuc


def _iso(an):
    return an.isoformat(timespec="minutes") if an else None
