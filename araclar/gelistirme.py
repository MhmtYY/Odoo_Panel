"""Yerel geliştirme sunucusu: gerçek ajan + gerçek panel, Docker ve PostgreSQL taklit (testler/sahte.py), git gerçek.

    python araclar/gelistirme.py [--port 18080]

Açılışta örnek durum gerçek akışlardan geçirilerek kurulur (kurulum, depo bağlama, deploy, staging, webhook,
bağlama). Durum her açılışta yerel/gelistirme/ altında sıfırdan üretilir; bu klasör depoya girmez.
Giriş bilgileri aşağıdaki GELISTIRME_KULLANICILARI'dadır; yalnız bu yerel sunucu içindir.
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from ajan import sunucu  # noqa: E402
from ajan.ayar import Ayar  # noqa: E402
from ajan.depo import Depo  # noqa: E402
from ajan.servis import Servis  # noqa: E402
from panel import panel as P  # noqa: E402
from testler.sahte import SahteKomut, sahte_http  # noqa: E402
from testler.yardimci import GIT, modul  # noqa: E402

YEREL = KOK / "yerel" / "gelistirme"
AJAN_PORT = 18098
AJAN_ANAHTARI = "gelistirme-ajan-anahtari"
# (kullanıcı, şifre, rol, kapsam) - yalnız yerel geliştirme sunucusu için
GELISTIRME_KULLANICILARI = [
    ("gelistirici", "gelistirme-123", "platform", "*"),
    ("ayse", "gelistirme-123", "yonetici", ["deneme"]),
    ("destek", "gelistirme-123", "kullanici", ["deneme"]),
]


class YavasKomut(SahteKomut):
    """İş pencerelerinde adımlar görünsün diye ağır Docker komutları biraz bekletilir."""

    def calistir(self, args, **kw):
        a = [str(x) for x in args]
        if a[:1] == ["docker"] and any(x in a for x in ("compose", "pg_dump", "pg_restore", "build", "run")):
            time.sleep(0.35)
        return super().calistir(args, **kw)


def git(*args, cwd=None):
    sonuc = subprocess.run(GIT + list(args), cwd=cwd, capture_output=True, text=True)
    if sonuc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {sonuc.stderr}")
    return sonuc.stdout.strip()


class Depo_:
    """Yerel 'uzak' depo ve çalışma kopyası."""

    def __init__(self, kok):
        self.uzak = kok / "uzak.git"
        self.calisma = kok / "calisma"
        git("init", "-q", "--bare", str(self.uzak))
        git("clone", "-q", str(self.uzak), str(self.calisma))

    def commit(self, dosyalar, mesaj, dal="main", taban="main"):
        c = self.calisma
        if git("ls-remote", "--heads", "origin", dal, cwd=c):
            git("fetch", "-q", "origin", dal, cwd=c)
            git("checkout", "-q", "-B", dal, "FETCH_HEAD", cwd=c)
        elif subprocess.run(GIT + ["rev-parse", "--verify", "-q", "HEAD"], cwd=c, capture_output=True).returncode == 0:
            git("fetch", "-q", "origin", taban, cwd=c)
            git("checkout", "-q", "-B", dal, "FETCH_HEAD", cwd=c)
        for yol, metin in dosyalar.items():
            (c / yol).parent.mkdir(parents=True, exist_ok=True)
            (c / yol).write_text(metin, encoding="utf-8")
        git("add", "-A", cwd=c)
        git("-c", "user.name=Ayşe Yılmaz", "-c", "user.email=ayse@example.com", "commit", "-q", "-m", mesaj, cwd=c)
        git("push", "-q", "origin", dal, cwd=c)
        return git("rev-parse", "HEAD", cwd=c)


def birlestiren(http, depo):
    """GitHub'ın merges API'sini yerel depoda gerçekten birleştirerek taklit eder (production'a alma için)."""
    def istek(yontem, url, basliklar, govde):
        if yontem == "POST" and url.endswith("/merges"):
            veri = json.loads(govde)
            c = depo.calisma
            git("fetch", "-q", "origin", veri["base"], cwd=c)
            git("checkout", "-q", "-B", veri["base"], "FETCH_HEAD", cwd=c)
            git("fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*", cwd=c)
            if subprocess.run(GIT + ["merge-base", "--is-ancestor", veri["head"], "HEAD"], cwd=c).returncode == 0:
                return 204, {}
            git("-c", "user.name=Panel", "-c", "user.email=panel@example.com", "merge", "-q", "--no-ff", "-m",
                veri["commit_message"], veri["head"], cwd=c)
            git("push", "-q", "origin", veri["base"], cwd=c)
            return 201, {"sha": git("rev-parse", "HEAD", cwd=c)}
        return http(yontem, url, basliklar, govde)

    istek.cagrilar = http.cagrilar
    return istek


def bekle(s, is_kaydi):
    sonuc = s.isler.oku(is_kaydi["id"])
    if sonuc["durum"] not in ("tamam",):
        print("UYARI:", is_kaydi.get("tur"), sonuc["durum"], sonuc.get("hata"))
    return sonuc


def hazirla():
    if YEREL.exists():
        # git nesne dosyaları Windows'ta salt okunur; önce yazılabilir yapılıp silinir
        shutil.rmtree(YEREL, onexc=lambda islev, yol, _: (os.chmod(yol, stat.S_IWRITE), islev(yol)))
    YEREL.mkdir(parents=True)
    ayar = Ayar(kok=YEREL / "kok", kenar_tenants=YEREL / "edge" / "etc" / "tenants", vtest_kok=YEREL / "vtest",
                saglik_suresi=0, port=AJAN_PORT, kuru=True)
    komut = YavasKomut()
    http = sahte_http({
        ("GET", "/installation"): (200, {"id": 77}),
        ("POST", "/access_tokens"): (201, {"token": "ghs_gelistirmejetonu12345", "expires_at": "2099-01-01T00:00:00Z"}),
        ("POST", "/pulls"): (201, {"number": 12, "html_url": "https://github.com/ornek-yazilim/deneme-addons/pull/12"}),
        ("GET", "/pulls/12"): (200, {"number": 12, "state": "open", "merged": False,
                                     "html_url": "https://github.com/ornek-yazilim/deneme-addons/pull/12"}),
    })
    depo = Depo_(YEREL)
    http = birlestiren(http, depo)
    s = Servis(ayar, komut=komut, http=http, senkron=True)
    (ayar.ayar_dizin / "github_app.json").write_text('{"app_id": 1, "anahtar": "app.pem"}')
    (ayar.ayar_dizin / "app.pem").write_text("gelistirme")
    (ayar.ayar_dizin / "webhook_sirri").write_text("gelistirme-webhook-sirri")
    mock.patch.object(Depo, "_uzak", lambda d, yazma=False: (str(depo.uzak), {})).start()

    # 1. panelin kurduğu Odoo, depoya bağlı, production + staging
    depo.commit({**modul("ornek_stok"), **modul("ornek_satis_raporu"), **modul("ornek_etiket")},
                "[ADD] ornek_stok, ornek_satis_raporu, ornek_etiket")
    depo.commit({"ornek_stok/models/uyari.py": "SINIR = 0\n"}, "[FIX] ornek_stok: negatif miktarda depo uyarısı")
    depo.commit({"ornek_etiket/models/zebra.py": "LOT = True\n"}, "[IMP] ornek_etiket: Zebra şablonuna lot numarası",
                dal="staging")
    bekle(s, s.kurulum.kur({"id": "deneme", "firma": "Deneme Tekstil A.Ş.", "baslangic": "bos",
                            "imaj": "vekosis/test20:20261108-1"}, "gelistirici"))
    komut.veritabanlari[("vtest-postgres", "pnl_deneme")] |= {"ornek_stok", "ornek_satis_raporu", "ornek_etiket"}
    s.odoolar.depo_bagla(s.odoolar.gerekli("deneme"), {
        "ad": "ornek-yazilim/deneme-addons", "baglanti": "app",
        "dallar": {"production": "main", "staging": "staging"}, "kip": {"production": "elle", "staging": "webhook"}})
    bekle(s, s.deploylar.baslat("deneme", "production", kullanici="gelistirici"))
    bekle(s, s.staging.olustur("deneme", "gelistirici"))
    sha = depo.commit({"ornek_satis_raporu/models/ozet.py": "AYLIK = True\n"},
                      "[ADD] ornek_satis_raporu: aylık satış özeti")
    s.webhook.push("ornek-yazilim/deneme-addons", "main", sha, tetik="webhook", kullanici="Ayşe Yılmaz",
                   bilgi={"baslik": "[ADD] ornek_satis_raporu: aylık satış özeti", "yazar": "Ayşe Yılmaz"})

    # 2. depoya bağlı olmayan boş Odoo
    bekle(s, s.kurulum.kur({"id": "tekstil", "firma": "Örnek Mobilya Ltd.", "baslangic": "bos",
                            "imaj": "vekosis/test20:20261108-1"}, "gelistirici"))

    # 3. sunucuda başka yolla kurulmuş Odoo'lar: test platformu ortamı (bağlanır) ve ERP (listede bekler)
    vt = ayar.vtest_kok / "tenants" / "musteri"
    (vt / "addons" / "ozel_rapor").mkdir(parents=True)
    (vt / "addons" / "ozel_rapor" / "__manifest__.py").write_text("{'name': 'Özel Rapor', 'version': '20.0.1.0.2'}")
    (vt / "odoo.conf").write_text("[options]\ndb_host = vtest-postgres\ndb_user = t_musteri\ndb_password = yerel\n"
                                  "db_name = musteri\naddons_path = /mnt/vekosis-addons,/mnt/extra-addons\n")
    erp = YEREL / "erp20"
    erp.mkdir()
    (erp / "odoo.conf").write_text("[options]\ndb_host = db\ndb_user = odoo\ndb_name = vekosis_db\n"
                                   "addons_path = /mnt/vekosis-addons\n")
    ayar.kenar_tenants.mkdir(parents=True, exist_ok=True)
    (ayar.kenar_tenants.parent / "Caddyfile").write_text(
        "erp.vekosis.com {\n    reverse_proxy erp20-odoo:8069 {\n    }\n}\n"
        "*.test.vekosis.com {\n    reverse_proxy odoo-{labels.3}:8069 {\n    }\n}\n")
    komut.konteynerler.update({"odoo-musteri": "running", "erp20-odoo": "running", "erp20-db": "running",
                               "vtest-postgres": "running"})
    komut.veritabanlari[("vtest-postgres", "musteri")] = {"base", "sale", "stock", "ozel_rapor"}
    komut.veritabanlari[("erp20-db", "vekosis_db")] = {"base", "account", "sale"}

    def inceleme(ad, imaj, conf, birim, calisma, etiket_ek=None, baglama=None):
        etiketler = {"com.docker.compose.project": ad, "com.docker.compose.project.working_dir": str(calisma),
                     "com.docker.compose.service": "odoo", **(etiket_ek or {})}
        return {"Name": "/" + ad, "State": {"Status": "running"},
                "Config": {"Image": imaj, "Env": [], "Labels": etiketler},
                "Mounts": [{"Type": "bind", "Source": str(conf), "Destination": "/etc/odoo/odoo.conf"},
                           {"Type": "volume", "Name": birim, "Destination": "/var/lib/odoo"}] + (baglama or []),
                "NetworkSettings": {"Networks": {"vtest": {}}}}

    komut.inceleme = {
        "odoo-musteri": inceleme("odoo-musteri", "vekosis/test20:20261108-1", vt / "odoo.conf", "odoo-musteri-data", vt,
                                 baglama=[{"Type": "bind", "Source": str(vt / "addons"), "Destination": "/mnt/extra-addons"}]),
        "erp20-odoo": inceleme("erp20-odoo", "vekosis/erp20:20261103-1", erp / "odoo.conf", "erp20_odoodata", erp,
                               {"com.docker.compose.project": "erp20"}),
        "vtest-postgres": {"Name": "/vtest-postgres", "Config": {"Image": "postgres:17", "Env": [], "Labels": {}},
                           "Mounts": [], "State": {"Status": "running"}},
        "erp20-db": {"Name": "/erp20-db", "Config": {"Image": "postgres:17", "Env": ["POSTGRES_USER=odoo"], "Labels": {
                         "com.docker.compose.project": "erp20", "com.docker.compose.service": "db"}},
                     "Mounts": [], "State": {"Status": "running"}},
    }
    komut.imajlar["vekosis/erp20:20261103-1"] = "sha256:erp1"
    s.kurulum.bagla({"konteyner": "odoo-musteri", "id": "musteri", "firma": "Müşteri Test Ortamı"}, "gelistirici")
    bekle(s, s.yedek_al("musteri", "production", "gelistirici"))
    ornek_izleme(s)
    s.isler.senkron = False
    return s


class OrnekClaude:
    """Yerel sunucunun asistanı: önce izleme_ozeti aracını çağırır, sonra sonucu kısa bir metinle özetler."""

    def __init__(self):
        from types import SimpleNamespace as N
        self._N = N
        self.beta = N(messages=N(create=self._olustur))

    def _olustur(self, **istek):
        import re as re_
        N = self._N
        son = istek["messages"][-1]
        kullanim = N(input_tokens=1200, output_tokens=180, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        if isinstance(son["content"], str):
            p = re_.search(r"\[Platform: ([a-z0-9-]+), ortam: (\w+)\]", son["content"])
            return N(stop_reason="tool_use", usage=kullanim, content=[
                N(type="text", text="Son 24 saatin ölçümlerine bakıyorum."),
                N(type="tool_use", id=f"ornek{time.time_ns()}", name="izleme_ozeti",
                  input={"platform": p[1], "ortam": p[2], "saat": 24})])
        sonuc = son["content"][0]
        try:
            v = json.loads(sonuc["content"])
            ozet = v.get("olcut_ozeti", {})
            metin = (f"**Yerel örnek yanıt** (gerçek Claude değil).\n\n"
                     f"- Erişilebilirlik (30 gün): %{v.get('erisilebilirlik_30g')}\n"
                     f"- 5xx hata oranı (24 saat): %{v.get('hata_orani_24s')}\n"
                     f"- Yanıt süresi p95 en çok: {ozet.get('p95', {}).get('en_cok')} ms\n"
                     f"- En yavaş uç: `{(v.get('yavas') or [{}])[0].get('uc')}`")
        except (ValueError, TypeError, KeyError):
            metin = f"Araç hata verdi: {sonuc.get('content')}"
        return N(stop_reason="end_turn", usage=kullanim, content=[N(type="text", text=metin)])


def ornek_izleme(s):
    """İzleme ekranı boş görünmesin: son 7 günün 10 dakikalık ÖRNEK ölçümleri (yalnız bu yerel sunucu için)."""
    import random
    from datetime import datetime
    r = random.Random(7)
    simdi = int(time.time())
    uclar = [("account.move.web_read_group", 1400), ("stock.quant.web_search_read", 900),
             ("sale.report.web_read_group", 600), ("res.partner.web_search_read", 180), ("/odoo/action-:id", 120)]
    for odoo_id, ortam, carpan in (("deneme", "production", 1.0), ("deneme", "staging", 0.2),
                                   ("tekstil", "production", 0.3), ("musteri", "production", 0.7)):
        v = 0.5
        for t in range(simdi - 7 * 86400, simdi, 600):
            v = min(0.95, max(0.05, v + (r.random() - 0.5) * 0.25))
            gunduz = 1 if 8 <= datetime.fromtimestamp(t).hour < 19 else 0.3
            istek = round((20 + 80 * v) * gunduz * carpan, 1)
            kesinti = odoo_id == "musteri" and simdi - 3 * 86400 < t < simdi - 3 * 86400 + 1800
            s.izleme._yaz(odoo_id, ortam, {
                "t": t, "durum": "running", "cpu": round((3 + 25 * v) * gunduz * carpan + 1, 1),
                "bellek": round(700 + 300 * v * carpan), "saglik": 0 if kesinti else 1, "saglik_ms": round(15 + 40 * v),
                "istek": istek, "hata5xx": 1 if r.random() < 0.04 else 0, "p95": round(250 + 900 * v * gunduz),
                "ort": round(90 + 200 * v), "surec": 5, "db_baglanti": round(4 + 10 * v * carpan),
                "db_boyut": 1_350_000_000 if odoo_id == "musteri" else 210_000_000,
                "uclar": {u: [n, round(n * ms_ * (0.6 + 0.8 * v)), round(ms_ * 3)]
                          for u, ms_ in uclar for n in [max(1, int(istek * r.random() / 4))]}})


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--port", type=int, default=18080)
    secenek = arg.parse_args()
    print("Örnek durum kuruluyor...", flush=True)
    s = hazirla()
    sunucu.Istek.servis = s
    sunucu.Istek.anahtar = AJAN_ANAHTARI
    sunucu.Istek.rota_listesi = sunucu.rotalar(s)
    ajan_http = ThreadingHTTPServer(("127.0.0.1", AJAN_PORT), sunucu.Istek)
    threading.Thread(target=ajan_http.serve_forever, daemon=True).start()

    P.VERI = YEREL / "panel_veri"
    P.AJAN_URL = f"http://127.0.0.1:{AJAN_PORT}"
    P.AJAN_ANAHTAR = AJAN_ANAHTARI
    P.kullanicilari_yaz({ad: {"sifre": P.sifre_ozeti(sifre), "rol": rol, "kapsam": kapsam, "olusturma": P.simdi()}
                         for ad, sifre, rol, kapsam in GELISTIRME_KULLANICILARI})
    # Panel asistanı: yerelde gerçek Claude yok; araçları gerçekten çağıran, yanıtı hazır metin olan taklit istemci
    P.asistan.sdk_var = lambda: True
    P.asistan.istemci_olustur = lambda anahtar: OrnekClaude()
    P.asistan.ayar_yaz({"anahtar": "sk-ant-yerel-ornek-0000"})
    panel_http = ThreadingHTTPServer(("127.0.0.1", secenek.port), P.Panel)
    print(f"Panel: http://localhost:{secenek.port}  (ajan 127.0.0.1:{AJAN_PORT}, durum {YEREL})", flush=True)
    panel_http.serve_forever()


if __name__ == "__main__":
    main()
