"""İzleme: dakikada bir ölçüm ve geçmişin özeti.

Her ortam için dakikada bir:
  - konteyner: durum, işlemci, bellek (docker stats)
  - sağlık: /web/health yanıtı ve süresi (sunucudan konteynerin IP'sine)
  - istekler: son ölçümden beri konteyner çıktısındaki istek satırları (sayı, 5xx, yanıt süresi, en yoğun uçlar)
  - veritabanı: bağlantı sayısı; 10 dakikada bir boyut. Odoo süreç sayısı 5 dakikada bir.

Ölçümler <kök>/izleme/<odoo>/<ortam>/<YYYY-AA-GG>.jsonl dosyalarına yazılır, 8 günden eskisi silinir.
Günlük erişilebilirlik özeti (gunluk.json) 35 gün tutulur.
"""
import json
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta

from . import kayit

SAKLAMA_GUN = 8
GUNLUK_GUN = 35
ARALIKLAR = (1, 24, 168)

# Odoo 16-18 (werkzeug) ve 19+ (kendi sunucusu) istek satırı: "YÖNTEM yol HTTP/x" durum boyut [sorgu_sayısı sorgu_sn kalan_sn]
ISTEK_SATIRI = re.compile(r'"(?P<yontem>[A-Z]+) (?P<yol>\S+) HTTP/[^"]*" (?P<durum>\d{3}) \S+'
                          r'(?: (?P<qn>\d+) (?P<qt>[\d.]+) (?P<rt>[\d.]+))?')
# Yanıt süresine katılmayan uçlar: statik dosyalar, uzun bekleyen bağlantılar, kendi sağlık denetimimiz
ATLANAN = re.compile(r"^/(web/(static|assets|image|content|binary|health|webclient/(load_menus|translations|locale))"
                     r"|[a-z0-9_]+/static/|websocket|longpolling|bus/|favicon)")


def uc_adi(yol):
    """İstek yolunu gruplanabilir uca çevirir: model.metot ya da kayıt numarası atılmış yol."""
    yol, _, rpc = yol.partition("#")
    yol = yol.split("?", 1)[0]
    if rpc:
        return rpc[:80]
    eslesme = re.match(r"^/(?:web/dataset/call_kw|json/2)/([\w.]+)/(\w+)", yol)
    if eslesme:
        return f"{eslesme[1]}.{eslesme[2]}"
    return re.sub(r"/\d+(?=/|$)", "/:id", yol)[:80]


def istekleri_ozetle(satirlar):
    """Konteyner çıktısındaki istek satırlarından (sayı, 5xx, süreler ms, uçlar {uc: [sayı, toplam_ms, en_uzun_ms]})."""
    sayi = hata = 0
    sureler = []
    uclar = {}
    for satir in satirlar:
        eslesme = ISTEK_SATIRI.search(satir)
        if not eslesme:
            continue
        yol = eslesme["yol"]
        if ATLANAN.match(yol.split("#", 1)[0]):
            continue
        sayi += 1
        if eslesme["durum"].startswith("5"):
            hata += 1
        if eslesme["qt"] is not None:
            ms = round((float(eslesme["qt"]) + float(eslesme["rt"])) * 1000)
            sureler.append(ms)
            uc = uclar.setdefault(uc_adi(yol), [0, 0, 0])
            uc[0] += 1
            uc[1] += ms
            uc[2] = max(uc[2], ms)
    return sayi, hata, sureler, uclar


def yuzdelik(degerler, oran):
    if not degerler:
        return None
    sirali = sorted(degerler)
    return sirali[min(len(sirali) - 1, int(round(oran * (len(sirali) - 1))))]


def _http_saglik(adres, zaman_asimi=5):
    """(tamam, süre ms)."""
    bas = time.monotonic()
    try:
        with urllib.request.urlopen(adres, timeout=zaman_asimi) as yanit:
            tamam = yanit.status == 200
    except Exception:  # noqa: BLE001 - ulaşılamayan ortam "kapalı" sayılır
        tamam = False
    return tamam, round((time.monotonic() - bas) * 1000)


class Izleme:
    def __init__(self, ayar, komut, ortamlar, odoolar, deploylar=None, saglik_denetle=_http_saglik):
        self.ayar = ayar
        self.komut = komut
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.deploylar = deploylar
        self.saglik_denetle = saglik_denetle
        self.kok = ayar.kok / "izleme"
        self._son = {}       # (odoo, ortam) -> son ölçüm zamanı (istek satırları bu andan sonrası okunur)
        self._ip = {}        # konteyner -> (ip, zaman)
        self._db_boyut = {}  # (db_konteyner, db) -> bayt
        self._surec = {}     # konteyner -> süreç sayısı
        self._sayac = 0
        self._kilit = threading.Lock()

    # ------------------------------------------------------------ toplama
    def baslat(self):
        threading.Thread(target=self._dongu, daemon=True, name="izleme").start()

    def _dongu(self):
        time.sleep(5)
        while True:
            bas = time.time()
            try:
                self.ornekle()
            except Exception as hata:  # noqa: BLE001 - izleme ajanı durdurmamalı
                print(f"{kayit.simdi()} izleme hatası: {type(hata).__name__}: {hata}", flush=True)
            time.sleep(max(5.0, 60 - (time.time() - bas)))

    def _ortamlar(self):
        sonuc = []
        for od in self.odoolar.liste():
            for ad in ("production", "staging"):
                o = self.ortamlar.oku(od["id"], ad)
                if o and o.get("konteyner"):
                    sonuc.append((od["id"], ad, o))
        return sonuc

    def ornekle(self, simdi=None):
        """Bütün ortamların bir ölçümü; yazılan kayıtları döner."""
        with self._kilit:
            simdi = int(simdi or time.time())
            ortamlar = self._ortamlar()
            if not ortamlar:
                return []
            self._sayac += 1
            istatistik = self.ortamlar.istatistik([o["konteyner"] for _, _, o in ortamlar])
            baglantilar = self._db_olcumleri(ortamlar)
            yazilan = []
            for odoo_id, ad, o in ortamlar:
                k = istatistik.get(o["konteyner"])
                ornek = {"t": simdi, "durum": "running" if k else self.ortamlar.konteyner_durumu(o)}
                if k:
                    ornek.update(cpu=k.get("cpu"), bellek=k.get("bellek_mb"))
                if ornek["durum"] == "running":
                    tamam, ms = self._saglik(o)
                    ornek.update(saglik=1 if tamam else 0, saglik_ms=ms)
                    ornek.update(self._istekler(odoo_id, ad, o, simdi))
                    if self._sayac % 5 == 1:
                        self._surec[o["konteyner"]] = self._surec_sayisi(o)
                    ornek["surec"] = self._surec.get(o["konteyner"])
                else:
                    ornek["saglik"] = 0
                anahtar = (o.get("db_konteyner"), o.get("db_adi"))
                ornek["db_baglanti"] = baglantilar.get(anahtar)
                ornek["db_boyut"] = self._db_boyut.get(anahtar)
                self._yaz(odoo_id, ad, ornek)
                yazilan.append((odoo_id, ad, ornek))
            if self._sayac % 60 == 1:
                self._temizle()
            return yazilan

    def _saglik(self, o):
        ip, zaman = self._ip.get(o["konteyner"], (None, 0))
        if not ip or time.time() - zaman > 600:
            sonuc = self.komut.calistir(["docker", "inspect", "-f",
                                         "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", o["konteyner"]],
                                        kontrol=False, zaman_asimi=15)
            ip = (sonuc.cikti.split() or [None])[0] if sonuc.tamam else None
            self._ip[o["konteyner"]] = (ip, time.time())
        if not ip:
            return False, None
        return self.saglik_denetle(f"http://{ip}:{o.get('http_port') or 8069}/web/health")

    def _istekler(self, odoo_id, ad, o, simdi):
        son = self._son.get((odoo_id, ad)) or simdi - 60
        self._son[(odoo_id, ad)] = simdi
        sonuc = self.komut.calistir(["docker", "logs", "--since", str(son), "--until", str(simdi), o["konteyner"]],
                                    kontrol=False, zaman_asimi=30)
        if not sonuc.tamam:
            return {}
        sayi, hata, sureler, uclar = istekleri_ozetle(sonuc.cikti.splitlines())
        dakika = max(1.0, (simdi - son) / 60)
        veri = {"istek": round(sayi / dakika, 1), "hata5xx": hata}
        if sureler:
            veri.update(p95=yuzdelik(sureler, 0.95), ort=round(sum(sureler) / len(sureler)))
        if uclar:
            # dosya büyümesin: toplam süresi en yüksek 15 uç
            veri["uclar"] = dict(sorted(uclar.items(), key=lambda x: -x[1][1])[:15])
        return veri

    def _surec_sayisi(self, o):
        sonuc = self.komut.calistir(["docker", "top", o["konteyner"], "-eo", "pid,args"], kontrol=False, zaman_asimi=15)
        if not sonuc.tamam:
            return None
        return sum(1 for s in sonuc.cikti.splitlines()[1:] if "odoo" in s)

    def _db_olcumleri(self, ortamlar):
        """{(db_konteyner, db): bağlantı sayısı}; 10 dakikada bir boyutları da günceller."""
        sunucular = {}
        for _, _, o in ortamlar:
            if o.get("db_konteyner"):
                sunucular.setdefault((o["db_konteyner"], o.get("db_su") or "postgres"), o)
        baglanti = {}
        for (db_konteyner, _), o in sunucular.items():
            cikti = self.ortamlar.psql(o, "SELECT datname || '|' || count(*) FROM pg_stat_activity "
                                          "WHERE datname IS NOT NULL GROUP BY datname;", db="postgres", kontrol=False)
            for satir in cikti.splitlines():
                db, _, n = satir.partition("|")
                if n.isdigit():
                    baglanti[(db_konteyner, db)] = int(n)
            if self._sayac % 10 == 1:
                cikti = self.ortamlar.psql(o, "SELECT datname || '|' || pg_database_size(datname) FROM pg_database "
                                              "WHERE NOT datistemplate;", db="postgres", kontrol=False)
                for satir in cikti.splitlines():
                    db, _, n = satir.partition("|")
                    if n.isdigit():
                        self._db_boyut[(db_konteyner, db)] = int(n)
        return baglanti

    # ------------------------------------------------------------ dosyalar
    def _dizin(self, odoo_id, ortam):
        return self.kok / odoo_id / ortam

    def _yaz(self, odoo_id, ortam, ornek):
        dizin = self._dizin(odoo_id, ortam)
        dizin.mkdir(parents=True, exist_ok=True)
        gun = datetime.fromtimestamp(ornek["t"]).strftime("%Y-%m-%d")
        with open(dizin / f"{gun}.jsonl", "a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(ornek, separators=(",", ":")) + "\n")
        gunluk = kayit.oku(dizin / "gunluk.json", {})
        toplam, ayakta = gunluk.get(gun, [0, 0])
        gunluk[gun] = [toplam + 1, ayakta + (1 if ornek.get("saglik") else 0)]
        sinir = (datetime.fromtimestamp(ornek["t"]) - timedelta(days=GUNLUK_GUN)).strftime("%Y-%m-%d")
        kayit.yaz(dizin / "gunluk.json", {g: v for g, v in gunluk.items() if g >= sinir})

    def _temizle(self):
        sinir = (datetime.now() - timedelta(days=SAKLAMA_GUN)).strftime("%Y-%m-%d")
        for dosya in self.kok.glob("*/*/*.jsonl"):
            if dosya.stem < sinir:
                dosya.unlink(missing_ok=True)

    def _oku(self, odoo_id, ortam, bas):
        dizin = self._dizin(odoo_id, ortam)
        if not dizin.is_dir():
            return []
        ilk_gun = datetime.fromtimestamp(bas).strftime("%Y-%m-%d")
        ornekler = []
        for dosya in sorted(dizin.glob("*.jsonl")):
            if dosya.stem < ilk_gun:
                continue
            for satir in dosya.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    ornek = json.loads(satir)
                except ValueError:
                    continue
                if ornek.get("t", 0) >= bas:
                    ornekler.append(ornek)
        return ornekler

    # ------------------------------------------------------------ özet
    def ozet(self, odoo_id, ortam, saat=24):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        saat = int(saat) if str(saat).isdigit() and int(saat) in ARALIKLAR else 24
        simdi = int(time.time())
        bas = simdi - saat * 3600
        ornekler = self._oku(odoo_id, ortam, min(bas, simdi - 24 * 3600))
        aralik = [x for x in ornekler if x["t"] >= bas]
        son24 = [x for x in ornekler if x["t"] >= simdi - 24 * 3600]
        kova = max(60, saat * 3600 // 120)
        seriler = {ad: [] for ad in ("cpu", "bellek", "istek", "p95", "db_baglanti")}
        gruplar = {}
        for x in aralik:
            gruplar.setdefault(x["t"] - x["t"] % kova, []).append(x)
        for t in sorted(gruplar):
            grup = gruplar[t]
            for ad in seriler:
                degerler = [x[ad] for x in grup if x.get(ad) is not None]
                if degerler:
                    deger = max(degerler) if ad == "p95" else sum(degerler) / len(degerler)
                    seriler[ad].append([t, round(deger, 1)])
        istek_24 = sum((x.get("istek") or 0) for x in son24)
        hata_24 = sum((x.get("hata5xx") or 0) for x in son24)
        uclar = {}
        for x in aralik:
            for uc, (n, toplam, en) in (x.get("uclar") or {}).items():
                a = uclar.setdefault(uc, [0, 0, 0])
                a[0] += n
                a[1] += toplam
                a[2] = max(a[2], en)
        yavas = [{"uc": uc, "sayi": n, "ort_ms": round(toplam / n) if n else 0, "en_uzun_ms": en}
                 for uc, (n, toplam, en) in sorted(uclar.items(), key=lambda x: -(x[1][1] / max(1, x[1][0])))[:10]]
        gunluk = kayit.oku(self._dizin(odoo_id, ortam) / "gunluk.json", {})
        gunler = []
        for i in range(29, -1, -1):
            gun = (datetime.fromtimestamp(simdi) - timedelta(days=i)).strftime("%Y-%m-%d")
            toplam, ayakta = gunluk.get(gun, [0, 0])
            gunler.append({"gun": gun, "oran": round(100 * ayakta / toplam, 2) if toplam else None, "olcum": toplam})
        olculen = [g for g in gunler if g["olcum"]]
        erisilebilirlik = (round(100 * sum(gunluk.get(g["gun"], [0, 0])[1] for g in olculen)
                                 / sum(g["olcum"] for g in olculen), 2) if olculen else None)
        son = ornekler[-1] if ornekler else None
        return {
            "aralik_saat": saat, "kova_sn": kova, "olcum_sayisi": len(aralik), "son": son,
            "seriler": seriler,
            "istek_kaydi": any(x.get("istek") for x in ornekler),
            "hata_orani_24s": round(100 * hata_24 / istek_24, 2) if istek_24 else None,
            "hata_24s": hata_24,
            "erisilebilirlik_30g": erisilebilirlik, "gunler": gunler,
            "yavas": yavas,
            "db_boyut": next((x["db_boyut"] for x in reversed(ornekler) if x.get("db_boyut")), None),
            "deploylar": self._deploy_anlari(odoo_id, ortam, bas),
            "cronlar": self.cronlar(o) if (son or {}).get("durum") == "running" or not son else [],
        }

    def _deploy_anlari(self, odoo_id, ortam, bas):
        if not self.deploylar:
            return []
        anlar = []
        for d in self.deploylar.kayitlar(odoo_id, ortam):
            try:
                t = int(datetime.fromisoformat(d.get("bitis") or d.get("baslangic")).timestamp())
            except (TypeError, ValueError):
                continue
            if t >= bas:
                anlar.append({"t": t, "commit": d.get("commit"), "durum": d.get("durum")})
        return anlar

    def cronlar(self, o):
        """Zamanlanmış işler (ir_cron): sürüme göre var olan sütunlarla."""
        sutunlar = set(self.ortamlar.psql(o, "SELECT column_name FROM information_schema.columns "
                                             "WHERE table_name = 'ir_cron';", kontrol=False).split())
        if not sutunlar:
            return []
        ad = "c.cron_name" if "cron_name" in sutunlar else "a.name::text"
        son = "c.lastcall" if "lastcall" in sutunlar else "NULL"
        hata = "c.failure_count" if "failure_count" in sutunlar else "0"
        sql = (f"SELECT coalesce(json_agg(t), '[]') FROM (SELECT c.id, {ad} AS ad, c.active AS etkin, "
               f"c.nextcall AS sonraki, {son} AS son, {hata} AS hata_sayisi, c.interval_number AS aralik, "
               f"c.interval_type AS aralik_turu FROM ir_cron c LEFT JOIN ir_act_server a "
               f"ON a.id = c.ir_actions_server_id ORDER BY c.active DESC, c.nextcall LIMIT 300) t;")
        cikti = self.ortamlar.psql(o, sql, kontrol=False)
        try:
            liste = json.loads(cikti.splitlines()[-1]) if cikti.strip() else []
        except ValueError:
            return []
        for c in liste:
            deger = c.get("ad") or ""
            if isinstance(deger, str) and deger.startswith("{"):
                try:
                    sozluk = json.loads(deger)
                    deger = sozluk.get("tr_TR") or sozluk.get("en_US") or deger
                except ValueError:
                    pass
            c["ad"] = deger
        return liste
