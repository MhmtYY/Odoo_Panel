"""Platformun kendi alan adı: panelin kurduğu platformun production ortamı, panel adresi (<ad>.<alan>) yerine
başka bir adla açılır (ör. decros.test.vekosis.com ya da erp.ornekfirma.com.tr).

Uygulanınca:
  - alan adı production konteynerine gider; sertifika isteğe bağlı alınır (izin dosyası: kenar_tenants/<alan>);
  - panel adresi alan adına yönlenir (302); staging panel adresinde kalır;
  - Odoo'nun web.base.url'si (ve adresi panel adresi olan web sitesi) https://<alan> olur, Odoo yeniden başlar;
  - ortamın "adres"i https://<alan> olur: arayüzdeki bağlantı, silme ve geri yükleme onayı bu adı ister.

Caddy kuralı <caddy_alanlar>/<ad>.caddy dosyasıdır; panel.caddy bu klasörü içe aktarır (sunucu/kur.sh). Tam ad
Caddy'de joker kuralın (*.test.vekosis.com, *.panel.vekosis.com) önüne geçer. Kural değişince Caddy önce doğrular,
sonra yeniden yükler; geçmezse eski kural geri konur. Uygulama yarıda kalırsa yapılanlar geri alınır.

Kayıt (production ortam.json): "alan_adi": {"alan", "durum": "bekliyor" | "etkin", "kayit", "uygulama", "kullanici"}
"""
import ipaddress
import re
import socket
import threading
import time
from pathlib import Path

from . import kayit
from .hata import Hata

ALAN_DESEN = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])$")
# Kural dosyaları aynı Caddy'yi paylaşır: aynı anda tek değişiklik (doğrula + yükle)
CADDY_KILIDI = threading.Lock()
DENEME = 18  # sertifika için en çok 18 deneme (bekleme 5 sn: 90 sn)


def alan_normallestir(deger):
    """Kullanıcının yazdığı adı Caddy'ye ve SQL'e girebilecek biçime getirir (küçük harf, IDNA)."""
    alan = str(deger or "").strip().lower()
    alan = re.sub(r"^[a-z][a-z0-9+.-]*://", "", alan).split("/", 1)[0].rstrip(".")
    if ":" in alan or "@" in alan:
        raise Hata(400, "Alan adına port ya da kullanıcı yazılmaz; yalnız ad: decros.test.vekosis.com")
    try:
        alan = alan.encode("idna").decode("ascii") if alan else ""
    except UnicodeError as hata:
        raise Hata(400, "Alan adı geçersiz.") from hata
    if not ALAN_DESEN.fullmatch(alan):
        raise Hata(400, "Alan adı geçersiz. Örnek: decros.test.vekosis.com ya da erp.ornekfirma.com.tr")
    return alan


def adres_sql(yeni_alan, eski_alanlar):
    """web.base.url = https://<yeni_alan>; adresi eski adlardan biri olan web sitesinin adresi de değişir.
    Adlar alan_normallestir'den ya da ayarlardan gelir; yine de yalnız ad karakterleri kabul edilir."""
    for ad in [yeni_alan, *eski_alanlar]:
        if not re.fullmatch(r"[a-z0-9.-]+", ad or ""):
            raise Hata(500, f"Geçersiz adres: {ad}")
    yeni = f"https://{yeni_alan}"
    eskiler = sorted({f"{on}{ad}" for ad in eski_alanlar for on in ("", "http://", "https://")} - {yeni})
    liste = ", ".join(f"'{d}'" for d in eskiler)
    kosul = (f"UPDATE website SET domain = '{yeni}', write_date = now() at time zone 'utc' WHERE domain IN ({liste});"
             if eskiler else "NULL;")
    return f"""BEGIN;
INSERT INTO ir_config_parameter (key, value, create_date, write_date)
  VALUES ('web.base.url', '{yeni}', now() at time zone 'utc', now() at time zone 'utc')
  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = EXCLUDED.write_date;
DO $$ BEGIN
  IF to_regclass('public.website') IS NOT NULL THEN
    {kosul}
  END IF;
END $$;
COMMIT;
"""


def caddy_siteleri(metin):
    """Caddyfile'ın üst düzey site blokları: [{"adresler": [ad, ...], "hedef": "konteyner:port" | None}].
    Hedef, bloğun 8069'a giden reverse_proxy'si (yoksa ilk reverse_proxy). Genel ayar bloğu, parçacıklar ("(ad)")
    ve yalnız port (":5555") atlanır. Yer tutucular ({labels.3}, {uri}) satır içinde kapandığı için süslü parantez
    sayımı bozulmaz."""
    siteler, site, derinlik = [], None, 0
    for ham in metin.splitlines():
        satir = ham.split("#", 1)[0].strip()
        if not satir:
            continue
        if derinlik == 0:
            site = None
            if satir.endswith("{"):
                adresler = []
                for parca in satir[:-1].replace(",", " ").split():
                    ad = re.sub(r"^https?://", "", parca).split("/", 1)[0]
                    ad = re.sub(r":\d+$", "", ad).lower()
                    if ad and not ad.startswith(("(", ":")):
                        adresler.append(ad)
                if adresler:
                    site = {"adresler": adresler, "hedef": None}
                    siteler.append(site)
        elif site is not None:
            parcalar = satir.split()
            if parcalar[0] == "reverse_proxy":
                parcalar = parcalar[1:]
                if parcalar and parcalar[0].startswith(("/", "@", "*")):  # eşleyici: /websocket*, @ad
                    parcalar = parcalar[1:]
                hedef = parcalar[0] if parcalar and parcalar[0] != "{" else None
                if hedef and (site["hedef"] is None or hedef.endswith(":8069")):
                    site["hedef"] = hedef
        derinlik = max(0, derinlik + satir.count("{") - satir.count("}"))
    return siteler


def joker_eslesir(desen, alan):
    """*.test.vekosis.com, decros.test.vekosis.com'u kapsar (tek etiket); test.vekosis.com'u ve a.b.test... kapsamaz."""
    if not desen.startswith("*."):
        return False
    son = desen[1:]
    return alan.endswith(son) and len(alan) > len(son) and "." not in alan[: -len(son)]


def joker_hedef(hedef, alan):
    """odoo-{labels.3}:8069 + decros.test.vekosis.com -> odoo-decros. Başka yer tutucu kalırsa None."""
    if not hedef:
        return None
    etiketler = alan.split(".")

    def yerine(eslesme):
        sira = int(eslesme.group(1))
        return etiketler[-(sira + 1)] if sira < len(etiketler) else eslesme.group(0)

    ad = re.sub(r"\{labels\.(\d+)\}", yerine, re.sub(r":\d+$", "", hedef))
    return ad if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", ad) else None


def _cozumle(ad, surum):
    """Sunucunun çözümleyicisiyle A (4) ya da AAAA (6) kayıtları."""
    aile = socket.AF_INET if surum == 4 else socket.AF_INET6
    try:
        return {b[4][0] for b in socket.getaddrinfo(ad, None, aile, socket.SOCK_STREAM)}
    except (OSError, UnicodeError):
        return set()


class AlanAdlari:
    def __init__(self, ayar, komut, isler, ortamlar, odoolar, cozumle=None):
        self.ayar = ayar
        self.komut = komut
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.cozumle = cozumle or _cozumle
        self.bekleme = 5  # sertifika ve son denetim denemeleri arasında (saniye); testlerde 0

    # ------------------------------------------------------------ temel
    def acik(self):
        """Kural klasörü tanımlı değilse (eski kur.sh, Verisfa sunucusu) özellik kapalıdır."""
        return self.ayar.caddy_alanlar is not None

    def kural_yolu(self, odoo_id):
        return Path(self.ayar.caddy_alanlar) / f"{odoo_id}.caddy"

    def panel_adresi(self, odoo_id):
        return self.ayar.adres_adi(odoo_id, "production")

    def _platform(self, odoo_id):
        od = self.odoolar.gerekli(odoo_id)
        if od.get("tur") != "panel":
            raise Hata(400, "Alan adı yalnız panelin kurduğu platformlara verilir; bağlanan kurulumun adresi kendi "
                            "Caddy kuralındadır.")
        return od, self.ortamlar.gerekli(odoo_id, "production")

    def _acik_denetle(self):
        if not self.acik():
            raise Hata(409, "Bu sunucuda alan adı kuralları kurulu değil. Panelin kur.sh betiği bu sürümle yeniden "
                            "çalıştırılmalı.")

    # ------------------------------------------------------------ durum, kayıt
    def durum(self, odoo_id):
        _od, pr = self._platform(odoo_id)
        k = pr.get("alan_adi")
        v4, _v6 = self._sunucu_ipleri(odoo_id)
        sonuc = {"acik": self.acik(), "panel_adresi": self.panel_adresi(odoo_id), "ip": ", ".join(sorted(v4)),
                 "kayit": k, "rapor": None}
        if k and k.get("durum") != "etkin":
            sonuc["rapor"] = self.rapor(odoo_id, k["alan"])
        return sonuc

    def kaydet(self, odoo_id, govde, kullanici=None):
        """Adı denetleyip kaydeder; DNS hazır olmasa da kaydedilir (rapor döner), uygulama ayrı istenir."""
        self._acik_denetle()
        alan = alan_normallestir(govde.get("alan"))
        _od, pr = self._platform(odoo_id)
        if self.isler.mesgul(f"{odoo_id}/production"):
            raise Hata(409, "Bu ortamda süren bir iş var. Bitince tekrar deneyin.")
        eski = pr.get("alan_adi") or {}
        if eski.get("durum") == "etkin" and eski.get("alan") != alan:
            raise Hata(409, f"{eski['alan']} uygulanmış durumda. Başka bir ad için önce onu kaldırın.")
        engeller, _uyarilar = self._cakismalar(odoo_id, alan)
        if engeller:
            raise Hata(409, engeller[0])
        if eski.get("alan") != alan:
            pr["alan_adi"] = {"alan": alan, "durum": "bekliyor", "kayit": kayit.simdi(), "kullanici": kullanici}
            self.ortamlar.yaz(pr)
        return self.durum(odoo_id)

    # ------------------------------------------------------------ denetimler
    def _sunucu_ipleri(self, odoo_id):
        """Bu sunucunun genel adresleri: panel adresinin çözüldüğü adresler + makinedeki genel adresler."""
        panel = self.panel_adresi(odoo_id)
        v4, v6 = set(self.cozumle(panel, 4)), set(self.cozumle(panel, 6))
        sonuc = self.komut.calistir(["ip", "-o", "addr", "show"], kontrol=False, zaman_asimi=15)
        for metin in re.findall(r"\binet6? ([0-9a-fA-F.:]+)/", sonuc.cikti if sonuc.tamam else ""):
            try:
                ip = ipaddress.ip_address(metin)
            except ValueError:
                continue
            if ip.is_global:
                (v4 if ip.version == 4 else v6).add(str(ip))
        return v4, v6

    def rapor(self, odoo_id, alan):
        """DNS ve çakışma raporu. "hazir" yalnız engel yoksa doğrudur; uyarılar engellemez."""
        engeller, uyarilar = self._cakismalar(odoo_id, alan)
        v4, v6 = self._sunucu_ipleri(odoo_id)
        ip_metni = ", ".join(sorted(v4)) or "bu sunucunun adresi"
        ipler, ipv6 = set(self.cozumle(alan, 4)), set(self.cozumle(alan, 6))
        if not ipler:
            engeller.append(f"{alan} DNS'te görünmüyor. A kaydı {ip_metni} olmalı; yeni eklendiyse yayılması beklenir.")
        elif ipler - v4:
            engeller.append(f"{alan} şu anda {', '.join(sorted(ipler))} adresine çözülüyor; {ip_metni} olmalı. "
                            "DNS sağlayıcısında vekil (proxy) açıksa kapatılmalı.")
        if ipv6 - v6:
            engeller.append(f"{alan} için IPv6 (AAAA) kaydı var: {', '.join(sorted(ipv6 - v6))}. Bu adres bu sunucunun "
                            "değil; ziyaretçiler ve sertifika doğrulaması oraya gidebilir. Kayıt silinmeli.")
        return {"alan": alan, "ip": ip_metni, "gorunen": sorted(ipler), "engeller": engeller, "uyarilar": uyarilar,
                "hazir": not engeller, "zaman": kayit.simdi()}

    def _caddy_siteleri(self):
        """Kenar Caddy'nin klasöründeki Caddyfile ve *.caddy dosyaları (alan adı kuralları alt klasörde, dahil değil)."""
        kok = self.ayar.kenar_tenants.parent
        siteler = []
        for yol in [kok / "Caddyfile", *sorted(kok.glob("*.caddy"))]:
            try:
                siteler += caddy_siteleri(yol.read_text(encoding="utf-8"))
            except OSError:
                continue
        return siteler

    def _konteyner_var(self, ad):
        return self.komut.calistir(["docker", "inspect", "-f", "{{.Name}}", ad], kontrol=False, zaman_asimi=20).tamam

    def _joker_sahibi(self, alan):
        """Adı joker kuralla alan ve şu anda var olan konteyner (ör. test platformundaki odoo-musteri) ya da None."""
        for site in self._caddy_siteleri():
            for desen in site["adresler"]:
                if joker_eslesir(desen, alan):
                    konteyner = joker_hedef(site["hedef"], alan)
                    if konteyner and self._konteyner_var(konteyner):
                        return konteyner
        return None

    def _cakismalar(self, odoo_id, alan):
        """(engeller, uyarılar): panelin kendi ad alanı, başka platform, Caddy'de tam ad ya da dolu joker ad."""
        engeller, uyarilar = [], []
        panel = self.panel_adresi(odoo_id)
        if alan == self.ayar.alan or alan.endswith("." + self.ayar.alan):
            engeller.append(f"{self.ayar.alan} altındaki adlar panelin kendi adresleri; bu platformun adresi zaten "
                            f"{panel}.")
        elif getattr(self.ayar, "panel_adres", "") and alan == self.ayar.panel_adres:
            engeller.append(f"{alan} panelin kendi adresi.")
        for od in self.odoolar.liste():
            if od["id"] == odoo_id:
                continue
            o = self.ortamlar.oku(od["id"], "production") or {}
            if (o.get("alan_adi") or {}).get("alan") == alan:
                engeller.append(f"{alan} başka bir platformda kayıtlı: {od['id']}.")
        for site in self._caddy_siteleri():
            for desen in site["adresler"]:
                if desen == alan:
                    engeller.append(f"{alan} sunucuda zaten başka bir yere gidiyor (Caddy kuralı: "
                                    f"{site['hedef'] or 'yönlendirme ya da sabit yanıt'}).")
                elif joker_eslesir(desen, alan):
                    konteyner = joker_hedef(site["hedef"], alan)
                    if konteyner and self._konteyner_var(konteyner):
                        engeller.append(f"{alan} şu anda {konteyner} konteynerinin adresi ({desen} kuralı). "
                                        "O kurulumun adresi bu platforma verilemez.")
                    else:
                        uyarilar.append(f"{alan}, Caddy'deki {desen} joker kuralının altında"
                                        + (f" (o kural {konteyner} konteynerine gider; şu anda yok)" if konteyner else "")
                                        + ". Uygulanınca bu ad yalnız bu platforma gider; o tarafta aynı adla kurulum "
                                          "açılmamalı.")
        return engeller, uyarilar

    def _ice_aktariliyor(self):
        """Kenar Caddy'nin bir dosyası kural klasörünü içe aktarıyor mu (panel.caddy: import .../<klasör>/*.caddy)."""
        kok = self.ayar.kenar_tenants.parent
        klasor = re.escape(Path(self.ayar.caddy_alanlar).name)
        for yol in [kok / "Caddyfile", *kok.glob("*.caddy")]:
            try:
                metin = yol.read_text(encoding="utf-8")
            except OSError:
                continue
            if re.search(rf"^\s*import\s+\S*/{klasor}/\*\.caddy\s*$", metin, re.M):
                return True
        return False

    # ------------------------------------------------------------ Caddy
    def kural_metni(self, odoo_id, alan, konteyner, yonlendir):
        panel = self.panel_adresi(odoo_id)
        metin = f"""# Odoo Yönetim Paneli üretti, elle değiştirmeyin (platform: {odoo_id}).
# {alan} -> {konteyner}{f"; panel adresi {panel} bu ada yönlenir" if yonlendir else ""}.
{alan} {{
    tls {{
        on_demand
    }}
    @dbyonetici path /web/database /web/database/*
    respond @dbyonetici "Erisim yok" 403
    request_body {{
        max_size 256MB
    }}
    encode zstd gzip
    header Strict-Transport-Security "max-age=31536000"
    reverse_proxy /websocket* {konteyner}:8072
    reverse_proxy {konteyner}:8069 {{
        request_buffers 16MB
    }}
}}
"""
        if yonlendir:
            metin += f"""
# Panel adresi: joker kuralın (*.{self.ayar.alan}) önüne geçer; sertifika izni kurulumda açıldı.
{panel} {{
    tls {{
        on_demand
    }}
    redir https://{alan}{{uri}} temporary
}}
"""
        return metin

    def kural_oku(self, odoo_id):
        yol = self.kural_yolu(odoo_id)
        return yol.read_text(encoding="utf-8") if yol.exists() else None

    def _dosya_yaz(self, yol, metin):
        if metin is None:
            yol.unlink(missing_ok=True)
            return
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_name(yol.name + ".yeni")
        gecici.write_text(metin, encoding="utf-8")
        gecici.chmod(0o644)
        gecici.replace(yol)

    def _caddy(self, b, islem):
        """caddy validate | reload; başarılıysa None, değilse çıktının son satırları."""
        sonuc = b.komut(["docker", "exec", self.ayar.caddy_konteyner, "caddy", islem, "--config",
                         self.ayar.caddy_config, "--adapter", "caddyfile"], kontrol=False, zaman_asimi=120)
        if sonuc.tamam:
            return None
        return "\n".join(sonuc.cikti.splitlines()[-15:]) or f"caddy {islem} başarısız"

    def kural_gecir(self, b, odoo_id, metin):
        """Kuralı yazar (metin None ise siler), Caddy doğrular ve yeniden yükler; geçmezse eskisi geri konur."""
        yol = self.kural_yolu(odoo_id)
        with CADDY_KILIDI:
            eski = self.kural_oku(odoo_id)
            if metin == eski:
                b.yaz("Caddy kuralı zaten bu halde.")
                return
            self._dosya_yaz(yol, metin)
            hata = self._caddy(b, "validate") or self._caddy(b, "reload")
            if hata:
                self._dosya_yaz(yol, eski)
                self._caddy(b, "reload")
                raise Hata(500, "Caddy yeni kuralı kabul etmedi; eski kural geri kondu.", ayrinti=hata)
            b.yaz(f"Caddy yeniden yüklendi ({yol.name} {'silindi' if metin is None else 'yazıldı'}).")

    # ------------------------------------------------------------ HTTPS denetimi
    def _curl(self, ad, yol="/", bicim="%{http_code}"):
        """Sunucunun kendisinden, kenar Caddy üzerinden HTTPS isteği; bağlantı ya da sertifika yoksa 000."""
        sonuc = self.komut.calistir(["curl", "-s", "-o", "/dev/null", "-w", bicim, "--max-time", "30",
                                     "--resolve", f"{ad}:443:127.0.0.1", f"https://{ad}{yol}"],
                                    kontrol=False, zaman_asimi=60)
        return sonuc.cikti.strip() or "000"

    def _sertifika_bekle(self, b, alan):
        for deneme in range(DENEME):
            kod = self._curl(alan, "/web/login")
            if not kod.startswith("000"):
                b.yaz(f"{alan}: sertifika tamam, HTTPS yanıtı {kod}.")
                return
            if deneme < DENEME - 1:
                time.sleep(self.bekleme)
        kayitlar = self.komut.calistir(["docker", "logs", "--since", "10m", self.ayar.caddy_konteyner],
                                       kontrol=False, zaman_asimi=30)
        for satir in [s for s in kayitlar.cikti.splitlines() if alan in s][-3:]:
            b.yaz(satir[:400])
        raise Hata(500, f"{alan} için sertifika alınamadı. DNS kaydının bu sunucuyu gösterdiğini ve 80/443 "
                        "portlarının açık olduğunu denetleyin.")

    def _son_denetim(self, b, alan, panel):
        kod = yon = "000"
        for deneme in range(6):
            kod = self._curl(alan, "/web/login")
            yon = self._curl(panel, "/", "%{http_code} %{redirect_url}")
            if kod == "200" and yon == f"302 https://{alan}/":
                b.yaz(f"https://{alan}/web/login 200; {panel} -> https://{alan}/ (302)")
                return
            if deneme < 5:
                time.sleep(self.bekleme)
        raise Hata(500, f"Son denetim geçmedi: https://{alan}/web/login {kod} döndü (200 bekleniyordu); {panel} "
                        f"yanıtı '{yon}' (302 https://{alan}/ bekleniyordu).")

    # ------------------------------------------------------------ Odoo
    def _yeniden_baslat(self, b, o):
        if self.ortamlar.konteyner_durumu(o) != "running":
            b.yaz("Odoo çalışmıyor; başlatılınca yeni adresi okur.")
            return
        # SQL ile yazılan parametre çalışan işçilerin önbelleğine ulaşmaz
        self.ortamlar.docker(b, "restart", "--time", "30", o["konteyner"], zaman_asimi=180)
        if not self.ortamlar.saglik(o, b):
            kayitlar = self.komut.calistir(["docker", "logs", "--tail", "40", o["konteyner"]], kontrol=False,
                                           zaman_asimi=30)
            for satir in kayitlar.cikti.splitlines()[-40:]:
                b.yaz(satir[:400])
            raise Hata(500, "Odoo yeniden başladıktan sonra açılmadı.")

    def _odoo_adresi(self, b, o, yeni_alan, eski_alanlar):
        """web.base.url'yi (ve web sitesi adresini) yazar, Odoo'yu yeniden başlatır; eski web.base.url'yi döner."""
        eski = self.ortamlar.psql(o, "SELECT value FROM ir_config_parameter WHERE key = 'web.base.url';", b=b)
        self.ortamlar.psql(o, adres_sql(yeni_alan, eski_alanlar), b=b)
        b.yaz(f"web.base.url: {eski or '(boş)'} -> https://{yeni_alan}")
        self._yeniden_baslat(b, o)
        return eski

    def _odoo_adresi_geri(self, b, o, eski_deger, alan, panel):
        deger = str(eski_deger or "").replace("'", "''")
        taban = (f"UPDATE ir_config_parameter SET value = '{deger}', write_date = now() at time zone 'utc' "
                 f"WHERE key = 'web.base.url';" if deger else "DELETE FROM ir_config_parameter WHERE key = 'web.base.url';")
        self.ortamlar.psql(o, f"""BEGIN;
{taban}
DO $$ BEGIN
  IF to_regclass('public.website') IS NOT NULL THEN
    UPDATE website SET domain = 'https://{panel}' WHERE domain = 'https://{alan}';
  END IF;
END $$;
COMMIT;
""", b=b)
        self._yeniden_baslat(b, o)

    # ------------------------------------------------------------ sertifika izni
    def _izin_ekle(self, alan):
        """İzin dosyasını açar; önceden yoksa True (geri almada silinir)."""
        if (self.ayar.kenar_tenants / alan).exists():
            return False
        self.ortamlar.adres_kaydet(alan)
        return True

    def _izin_sil(self, alan):
        """İzin dosyasını siler; ad joker kuralla başka bir kuruluma da gidiyorsa (sonradan açılmışsa) bırakır."""
        sahip = self._joker_sahibi(alan)
        if sahip:
            return sahip
        self.ortamlar.adres_kaydet(alan, var=False)
        return None

    # ------------------------------------------------------------ işler
    def uygula(self, odoo_id, kullanici=None):
        self._acik_denetle()
        _od, pr = self._platform(odoo_id)
        k = pr.get("alan_adi")
        if not k:
            raise Hata(404, "Kayıtlı alan adı yok.")
        alan, panel = k["alan"], self.panel_adresi(odoo_id)
        if not self._ice_aktariliyor():
            raise Hata(409, "Kenar Caddy alan adı kurallarını okumuyor (panel.caddy'de import satırı yok). Panelin "
                            "kur.sh betiği bu sürümle yeniden çalıştırılmalı.")
        if self.ortamlar.konteyner_durumu(pr) != "running":
            raise Hata(409, "Production çalışmıyor. Önce başlatın, sonra uygulayın.")
        rapor = self.rapor(odoo_id, alan)  # kurala ve sertifikaya DNS ve çakışma denetimi geçmeden girilmez
        if not rapor["hazir"]:
            raise Hata(409, f"Uygulanamaz: {rapor['engeller'][0]}")

        def isle(b):
            yapilan = {"kural": self.kural_oku(odoo_id), "izin": False, "taban": None}
            try:
                with b.adim(f"Sertifika izni ve Caddy kuralı: {alan}"):
                    yapilan["izin"] = self._izin_ekle(alan)
                    self.kural_gecir(b, odoo_id, self.kural_metni(odoo_id, alan, pr["konteyner"], yonlendir=False))
                with b.adim("Sertifika alınıyor"):
                    self._sertifika_bekle(b, alan)
                with b.adim(f"Odoo adresi https://{alan} oluyor (Odoo yeniden başlar)"):
                    o = self.ortamlar.gerekli(odoo_id, "production")
                    yapilan["taban"] = self._odoo_adresi(b, o, alan, [panel])
                with b.adim(f"{panel} adresi {alan} adına yönlendiriliyor"):
                    self.kural_gecir(b, odoo_id, self.kural_metni(odoo_id, alan, pr["konteyner"], yonlendir=True))
                with b.adim("Son denetim"):
                    self._son_denetim(b, alan, panel)
            except BaseException:
                self._geri_al(b, odoo_id, alan, panel, yapilan)
                raise
            o = self.ortamlar.gerekli(odoo_id, "production")
            o["alan_adi"] = {**(o.get("alan_adi") or k), "alan": alan, "durum": "etkin", "uygulama": kayit.simdi(),
                             "kullanici": kullanici}
            o["adres"] = f"https://{alan}"
            self.ortamlar.yaz(o)
            return {"alan": alan, "adres": o["adres"]}

        return self.isler.baslat("alan-adi", f"{odoo_id}/production", isle, odoo=odoo_id, ortam="production",
                                 kullanici=kullanici, aciklama=f"{alan} uygulanıyor")

    def _geri_al(self, b, odoo_id, alan, panel, yapilan):
        b.yaz("Alan adı uygulanamadı, yapılanlar geri alınıyor.")
        if yapilan["taban"] is not None:
            try:
                self._odoo_adresi_geri(b, self.ortamlar.gerekli(odoo_id, "production"), yapilan["taban"], alan, panel)
                b.yaz("Odoo adresi eski haline döndü.")
            except Exception as hata:  # noqa: BLE001 - geri almanın kalanı sürer
                b.uyari(f"Odoo adresi geri alınamadı ({hata}); web.base.url elle denetlenmeli.")
        if self.kural_oku(odoo_id) != yapilan["kural"]:
            try:
                self.kural_gecir(b, odoo_id, yapilan["kural"])
            except Exception as hata:  # noqa: BLE001
                b.uyari(f"Caddy kuralı geri alınamadı ({hata}); {self.kural_yolu(odoo_id)} elle denetlenmeli.")
        if yapilan["izin"]:
            self.ortamlar.adres_kaydet(alan, var=False)
        b.yaz(f"Geri alındı; platform {panel} adresinde açılır.")

    def kaldir(self, odoo_id, kullanici=None):
        """Uygulanmamış kaydı hemen siler; uygulanmışsa kural, Odoo adresi ve izin geri alınır (tekrar çalıştırılabilir)."""
        _od, pr = self._platform(odoo_id)
        k = pr.get("alan_adi")
        if not k:
            raise Hata(404, "Kayıtlı alan adı yok.")
        if k.get("durum") != "etkin":
            if self.isler.mesgul(f"{odoo_id}/production"):
                raise Hata(409, "Bu ortamda süren bir iş var. Bitince tekrar deneyin.")
            pr.pop("alan_adi", None)
            self.ortamlar.yaz(pr)
            return {"silindi": True}
        self._acik_denetle()
        alan, panel = k["alan"], self.panel_adresi(odoo_id)

        def isle(b):
            with b.adim("Caddy kuralı kaldırılıyor"):
                self.kural_gecir(b, odoo_id, None)
            with b.adim(f"Odoo adresi https://{panel} oluyor (Odoo yeniden başlar)"):
                self._odoo_adresi(b, self.ortamlar.gerekli(odoo_id, "production"), panel, [alan])
            with b.adim("Sertifika izni ve kayıt siliniyor"):
                sahip = self._izin_sil(alan)
                if sahip:
                    b.yaz(f"{alan} izni bırakıldı: ad joker kuralla {sahip} konteynerine de gidiyor.")
                o = self.ortamlar.gerekli(odoo_id, "production")
                o.pop("alan_adi", None)
                o["adres"] = f"https://{panel}"
                self.ortamlar.yaz(o)
            with b.adim("Son denetim"):
                kod = "000"
                for deneme in range(6):
                    kod = self._curl(panel, "/web/login")
                    if kod == "200":
                        break
                    if deneme < 5:
                        time.sleep(self.bekleme)
                if kod == "200":
                    b.yaz(f"https://{panel}/web/login 200")
                else:
                    b.uyari(f"https://{panel}/web/login {kod} döndü; Odoo açılıyorsa birkaç dakika sonra yeniden bakın.")
            return {"adres": f"https://{panel}"}

        return self.isler.baslat("alan-adi", f"{odoo_id}/production", isle, odoo=odoo_id, ortam="production",
                                 kullanici=kullanici, aciklama=f"{alan} kaldırılıyor")

    def temizle(self, b, pr):
        """Platform silinirken: kural ve sertifika izni kalkar. Hata silmeyi durdurmaz, uyarı olarak yazılır."""
        k = pr.get("alan_adi") or {}
        if self.acik() and self.kural_yolu(pr["odoo"]).exists():
            try:
                self.kural_gecir(b, pr["odoo"], None)
            except Exception as hata:  # noqa: BLE001
                b.uyari(f"Alan adı kuralı kaldırılamadı ({hata}); {self.kural_yolu(pr['odoo'])} elle silinmeli.")
        if k.get("durum") == "etkin":
            self._izin_sil(k["alan"])
