"""Ajanın ayarları: yollar, adlar, sınırlar.

Sunucuda varsayılanlar kullanılır; değerler /opt/odoo-panel/ayar/ajan.env ile ya da ortam değişkenleriyle değişir.
Testler geçici bir kök klasörle kendi Ayar nesnesini kurar.
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .hata import Hata

# Odoo kimliği: adresin ilk etiketi olur (<ad>.panel.vekosis.com). Tire ile başlamaz/bitmez, "-staging" ile bitmez.
AD_DESEN = re.compile(r"^[a-z][a-z0-9-]{1,20}[a-z0-9]$")
AYRILMIS = {"www", "mail", "panel", "admin", "api", "ftp", "smtp", "imap", "pop", "ns1", "ns2", "webmail",
            "cpanel", "autodiscover", "autoconfig", "erp", "test", "sablon", "staging", "webhook", "static"}
ORTAMLAR = ("production", "staging")


@dataclass
class Ayar:
    kok: Path = Path("/opt/odoo-panel")
    alan: str = "panel.vekosis.com"
    ag: str = "vtest"
    pg_konteyner: str = "vtest-postgres"
    pg_su: str = "postgres"
    kenar_tenants: Path = Path("/opt/edge/etc/tenants")
    vtest_kok: Path = Path("/opt/vekosis-test")
    adres: str = "127.0.0.1"
    port: int = 8098
    izinli_konteyner: str = "pnl-panel"
    kuru: bool = False
    # yeni ortam açmadan önce sunucuda bu kadar bellek boş kalmalı (deploy güncellemesi + PostgreSQL payı)
    bellek_payi_mb: int = 3072
    ortam_bellek_mb: int = 1200
    ortam_bellek_siniri: str = "2g"
    ortam_cpu: str = "2"
    # aynı anda en çok bu kadar ağır iş (güncelleme, veri kopyası, imaj derleme)
    agir_is_siniri: int = 2
    kod_sakla: int = 4
    saglik_suresi: int = 240

    # -- klasörler
    @property
    def ayar_dizin(self):
        return self.kok / "ayar"

    @property
    def odoolar(self):
        return self.kok / "odoolar"

    @property
    def depolar(self):
        return self.kok / "depolar"

    @property
    def yedekler(self):
        return self.kok / "yedekler"

    @property
    def isler(self):
        return self.kok / "isler"

    @property
    def gecici(self):
        return self.kok / "gecici"

    @property
    def onbellek(self):
        return self.kok / "onbellek"

    def klasorleri_kur(self):
        for yol in (self.ayar_dizin, self.odoolar, self.depolar, self.yedekler, self.isler, self.gecici,
                    self.onbellek, self.ayar_dizin / "anahtarlar"):
            yol.mkdir(parents=True, exist_ok=True)
        for yol in (self.ayar_dizin, self.yedekler, self.gecici):
            try:
                os.chmod(yol, 0o700)
            except OSError:
                pass

    # -- adlar
    def ad_denetle(self, ad):
        ad = str(ad or "").strip().lower()
        if not AD_DESEN.match(ad) or ad.endswith("-staging") or "--" in ad:
            raise Hata(400, "Geçersiz ad. Küçük harfle başlar; küçük harf, rakam ve tire; 3-22 karakter; "
                            "'-staging' ile bitemez.")
        if ad in AYRILMIS:
            raise Hata(400, f"'{ad}' ayrılmış bir ad, kullanılamaz.")
        return ad

    @staticmethod
    def ortam_denetle(ortam):
        if ortam not in ORTAMLAR:
            raise Hata(400, "Ortam production ya da staging olmalı.")
        return ortam

    @staticmethod
    def ek(ortam):
        return "" if ortam == "production" else "-staging"

    def konteyner_adi(self, ad, ortam):
        return f"pnl-{ad}{self.ek(ortam)}"

    def birim_adi(self, ad, ortam):
        return f"pnl-{ad}{self.ek(ortam)}-data"

    @staticmethod
    def db_adi(ad, ortam):
        return f"pnl_{ad.replace('-', '_')}" + ("" if ortam == "production" else "_staging")

    @staticmethod
    def rol_adi(ad, ortam):
        return f"pnl_{ad.replace('-', '_')}" + ("" if ortam == "production" else "_st")

    def adres_adi(self, ad, ortam):
        return f"{ad}{self.ek(ortam)}.{self.alan}"


def ortamdan(env=None):
    """Ayarları ortam değişkenlerinden okur (systemd EnvironmentFile)."""
    env = os.environ if env is None else env
    ayar = Ayar()
    eslem = {
        "PANEL_KOK": ("kok", Path), "PANEL_ALAN": ("alan", str), "PANEL_AG": ("ag", str),
        "PANEL_PG": ("pg_konteyner", str), "PANEL_KENAR_TENANTS": ("kenar_tenants", Path),
        "PANEL_VTEST_KOK": ("vtest_kok", Path), "AJAN_ADRES": ("adres", str), "AJAN_PORT": ("port", int),
        "AJAN_IZINLI": ("izinli_konteyner", str), "PANEL_BELLEK_PAYI_MB": ("bellek_payi_mb", int),
        "PANEL_AGIR_IS": ("agir_is_siniri", int),
    }
    for anahtar, (alan, tur) in eslem.items():
        if env.get(anahtar):
            setattr(ayar, alan, tur(env[anahtar]))
    ayar.kuru = env.get("AJAN_KURU") == "1"
    return ayar
