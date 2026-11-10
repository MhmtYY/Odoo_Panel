"""Ortam (production / staging): durum dosyası, compose ve odoo.conf üretimi, Docker ve PostgreSQL işlemleri.

İki yönetim türü:
  panel  compose dosyası panelin; imaj ve kod .env'den gelir (deploy .env'i değiştirip konteyneri yeniden oluşturur)
  bagli  panelin kurmadığı konteyner (ERP, test platformu ortamı). Compose'a dokunulmaz; yalnız izleme, yedek,
         izin verildiyse docker stop/start.
"""
import configparser
import json
import re
import secrets
import shutil
import time
from pathlib import Path

from . import kayit
from .hata import Hata

PY_SINAMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,80}$")

IMAJ_TARAMA = r"""
import json, os, sys
import odoo.addons  # Odoo 19+: odoo ve odoo.addons ad alanı paketi; "import odoo" addons'u yüklemez
from odoo import release
yollar = [p for p in odoo.addons.__path__]
ek = [p for p in ("/mnt/vekosis-addons", "/mnt/enterprise-addons", "/mnt/extra-addons", "/mnt/addons")
      if os.path.isdir(p)]
moduller = set()
dolu = []
for yol in yollar + ek:
    try:
        adlar = os.listdir(yol)
    except OSError:
        continue
    bulunan = [a for a in adlar if os.path.isfile(os.path.join(yol, a, "__manifest__.py"))]
    moduller.update(bulunan)
    if yol in ek and bulunan:
        dolu.append(yol)
print(json.dumps({"seri": release.series, "surum": release.version, "moduller": sorted(moduller), "yollar": dolu}))
"""

PY_SORGU = ("import importlib.util, json, sys\n"
            "s = {}\n"
            "for n in sys.argv[1:]:\n"
            "    try:\n"
            "        s[n] = importlib.util.find_spec(n) is not None\n"
            "    except Exception:\n"
            "        s[n] = False\n"
            "print(json.dumps(s))\n")

SAGLIK = ("import sys, urllib.request\n"
          "try:\n"
          "    r = urllib.request.urlopen('http://localhost:8069/web/login', timeout=10)\n"
          "    sys.exit(0 if r.status == 200 else 1)\n"
          "except Exception:\n"
          "    sys.exit(1)\n")


def conf_oku(metin):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(metin)
    return dict(parser["options"]) if parser.has_section("options") else {}


def conf_metni(secenekler):
    satirlar = ["[options]"]
    for anahtar, deger in secenekler.items():
        satirlar.append(f"{anahtar} = {deger}")
    return "\n".join(satirlar) + "\n"


class Ortamlar:
    def __init__(self, ayar, komut):
        self.ayar = ayar
        self.komut = komut

    # ------------------------------------------------------------ durum dosyaları
    def dizin(self, odoo_id, ortam):
        return self.ayar.odoolar / odoo_id / ortam

    def oku(self, odoo_id, ortam):
        return kayit.oku(self.dizin(odoo_id, ortam) / "ortam.json")

    def gerekli(self, odoo_id, ortam):
        o = self.oku(odoo_id, ortam)
        if not o:
            raise Hata(404, f"{odoo_id} için {ortam} ortamı yok.")
        return o

    def yaz(self, o):
        return kayit.yaz(self.dizin(o["odoo"], o["ad"]) / "ortam.json", o)

    def yeni_panel_ortami(self, odoo_id, ortam, imaj, addons_yollari):
        """Panelin yöneteceği yeni ortamın kaydı (henüz hiçbir şey kurulmaz)."""
        dizin = self.dizin(odoo_id, ortam)
        return {
            "odoo": odoo_id, "ad": ortam, "yonetim": "panel",
            "konteyner": self.ayar.konteyner_adi(odoo_id, ortam),
            "compose": str(dizin / "compose.yml"), "env": str(dizin / ".env"),
            "db_konteyner": self.ayar.pg_konteyner, "db_su": self.ayar.pg_su,
            "db_adi": self.ayar.db_adi(odoo_id, ortam), "db_rol": self.ayar.rol_adi(odoo_id, ortam),
            "birim": self.ayar.birim_adi(odoo_id, ortam), "imaj": imaj, "imaj_temel": imaj,
            "adres": f"https://{self.ayar.adres_adi(odoo_id, ortam)}", "conf": str(dizin / "odoo.conf"),
            "kod": str(dizin / "kod" / "bos"), "commit": None, "ek_addons": str(dizin / "ek-addons"),
            "addons_yollari": addons_yollari, "olusturma": kayit.simdi(),
        }

    # ------------------------------------------------------------ dosyalar
    def compose_yaz(self, o):
        dizin = self.dizin(o["odoo"], o["ad"])
        dizin.mkdir(parents=True, exist_ok=True)
        for klasor in (o["ek_addons"], o["kod"]):
            Path(klasor).mkdir(parents=True, exist_ok=True)
            Path(klasor).chmod(0o755)
        metin = f"""# Odoo Yönetim Paneli tarafından üretildi; elle değiştirmeyin (deploy yeniden yazar).
name: {o['konteyner']}
services:
  odoo:
    image: ${{IMAJ}}
    container_name: {o['konteyner']}
    restart: unless-stopped
    command: odoo -c /etc/odoo/odoo.conf
    environment:
      TZ: Europe/Istanbul
      PYTHONUTF8: "1"
    volumes:
      - {o['conf']}:/etc/odoo/odoo.conf:ro
      - ${{KOD}}:/mnt/repo:ro
      - {o['ek_addons']}:/mnt/extra-addons:ro
      - odoo-data:/var/lib/odoo
    mem_limit: {self.ayar.ortam_bellek_siniri}
    cpus: {self.ayar.ortam_cpu}
    labels:
      vekosis.panel.odoo: "{o['odoo']}"
      vekosis.panel.ortam: "{o['ad']}"
    networks: [{self.ayar.ag}]
networks:
  {self.ayar.ag}:
    external: true
volumes:
  odoo-data:
    name: {o['birim']}
    external: true
"""
        Path(o["compose"]).write_text(metin, encoding="utf-8")
        self.env_yaz(o, Path(o["env"]), o["imaj"], o["kod"])

    @staticmethod
    def env_yaz(o, yol, imaj, kod):
        Path(yol).write_text(f"IMAJ={imaj}\nKOD={kod}\n", encoding="utf-8")

    def conf_yaz(self, o, secenekler):
        yol = Path(o["conf"])
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(conf_metni(secenekler), encoding="utf-8")
        try:
            yol.chmod(0o644)  # konteynerdeki odoo kullanıcısı okuyabilmeli; klasör root'a kapalı
        except OSError:
            pass

    def temel_conf(self, o, sifre, ana_sifre, ek=None):
        yollar = ["/mnt/repo"] + [y for y in o.get("addons_yollari", []) if y not in ("/mnt/repo", "/mnt/extra-addons")]
        yollar.append("/mnt/extra-addons")
        secenekler = {
            "db_host": self.ayar.pg_konteyner, "db_port": "5432", "db_user": o["db_rol"], "db_password": sifre,
            "db_name": o["db_adi"], "dbfilter": f"^{o['db_adi']}$", "list_db": "False", "admin_passwd": ana_sifre,
            "proxy_mode": "True", "http_interface": "0.0.0.0", "addons_path": ",".join(yollar),
            "data_dir": "/var/lib/odoo", "workers": "2", "max_cron_threads": "1", "gevent_port": "8072",
            "db_maxconn": "16", "limit_memory_soft": "1073741824", "limit_memory_hard": "1610612736",
            "limit_time_cpu": "600", "limit_time_real": "1200", "limit_request": "8192",
        }
        if ek:
            secenekler.update(ek)
        self.komut.gizle(sifre, ana_sifre)
        return secenekler

    # ------------------------------------------------------------ Docker
    def docker(self, b, *args, **kw):
        calistir = b.komut if b is not None else self.komut.calistir
        return calistir(["docker", *args], **kw)

    def compose(self, o, b, *args, env=None, **kw):
        if o.get("yonetim") != "panel":
            raise Hata(400, "Bu ortamın compose dosyası panelin değil.")
        return self.docker(b, "compose", "-f", o["compose"], "--env-file", env or o["env"], *args, **kw)

    def konteyner_durumu(self, o):
        sonuc = self.komut.calistir(["docker", "inspect", "-f", "{{.State.Status}}", o["konteyner"]], kontrol=False,
                                    zaman_asimi=20)
        return sonuc.cikti.strip() if sonuc.tamam else "yok"

    def istatistik(self, konteynerler):
        """{konteyner: {"bellek_mb", "cpu"}} - çalışmayanlar listede olmaz."""
        if not konteynerler:
            return {}
        sonuc = self.komut.calistir(["docker", "stats", "--no-stream", "--format",
                                     "{{.Name}}|{{.MemUsage}}|{{.CPUPerc}}", *konteynerler], kontrol=False,
                                    zaman_asimi=40)
        cikti = {}
        for satir in sonuc.cikti.splitlines():
            parca = satir.split("|")
            if len(parca) != 3:
                continue
            cikti[parca[0]] = {"bellek_mb": _mb(parca[1].split("/")[0]), "cpu": _yuzde(parca[2])}
        return cikti

    def durdur(self, o, b=None):
        if o.get("yonetim") == "panel":
            self.compose(o, b, "stop", "--timeout", "30")
        else:
            self.docker(b, "stop", "--time", "30", o["konteyner"])

    def baslat(self, o, b=None):
        if o.get("yonetim") == "panel":
            self.compose(o, b, "up", "-d", "--quiet-pull")
        else:
            self.docker(b, "start", o["konteyner"])

    def odoo_tek(self, o, b, odoo_args, imaj=None, kod=None, zaman_asimi=3600, alt_komut=None, **kw):
        """Ortamın yapılandırmasıyla tek seferlik Odoo komutu (sunucu konteyneri durdurulmuş olmalı).
        alt_komut: "shell", "neutralize" gibi; verilmezse sunucu komutu (-u, -i ... --stop-after-init)."""
        env = o["env"]
        if imaj or kod:
            env = str(Path(o["env"]).with_name(".env.tek"))
            self.env_yaz(o, env, imaj or o["imaj"], kod or o["kod"])
        args = ["odoo"] + ([alt_komut] if alt_komut else []) + ["-c", "/etc/odoo/odoo.conf", "-d", o["db_adi"]]
        return self.compose(o, b, "run", "--rm", "-T", "--no-deps", "odoo", *args, *odoo_args, env=env,
                            zaman_asimi=zaman_asimi, **kw)

    def saglik(self, o, b=None, sure=None):
        """Konteynerin içinden /web/login 200 dönene kadar bekler."""
        sure = sure or self.ayar.saglik_suresi
        bitis = time.time() + sure
        while True:
            sonuc = self.komut.calistir(["docker", "exec", o["konteyner"], "python3", "-c", SAGLIK], kontrol=False,
                                        zaman_asimi=30)
            if sonuc.tamam:
                return True
            if time.time() >= bitis:
                return False
            time.sleep(3)

    # ------------------------------------------------------------ PostgreSQL
    def psql(self, o, sql, db=None, b=None, kontrol=True):
        args = ["docker", "exec", "-i", o["db_konteyner"], "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                "-U", o["db_su"], "-d", db or o["db_adi"], "-At"]
        calistir = b.komut if b is not None else self.komut.calistir
        kw = {"log": None} if b is not None else {}
        sonuc = calistir(args, girdi=sql, kontrol=kontrol, zaman_asimi=600, **kw)
        return sonuc.cikti.strip()

    def kurulu_moduller(self, o):
        cikti = self.psql(o, "SELECT name FROM ir_module_module WHERE state = 'installed' ORDER BY 1;", kontrol=False)
        return {s.strip() for s in cikti.splitlines() if re.match(r"^[a-z0-9_]+$", s.strip())}

    def db_var(self, db_konteyner, db_su, db_adi):
        sonuc = self.komut.calistir(["docker", "exec", "-i", db_konteyner, "psql", "-X", "-At", "-U", db_su, "-d",
                                     "postgres"], girdi=f"SELECT 1 FROM pg_database WHERE datname = '{_sql_ad(db_adi)}';",
                                    kontrol=False, zaman_asimi=30)
        return sonuc.cikti.strip() == "1"

    def db_olustur(self, o, b, sifre=None):
        """Ortamın rolünü (yoksa) ve boş veritabanını oluşturur. sifre verilirse rolün şifresi de yazılır."""
        rol, db = _sql_ad(o["db_rol"]), _sql_ad(o["db_adi"])
        if sifre is not None and not re.match(r"^[A-Za-z0-9]{12,64}$", sifre):
            raise Hata(400, "Geçersiz veritabanı şifresi.")
        sifre_sql = f"ALTER ROLE \"{rol}\" PASSWORD '{sifre}';" if sifre else ""
        sql = f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{rol}') THEN
    CREATE ROLE "{rol}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT 40;
  END IF;
END $$;
{sifre_sql}
CREATE DATABASE "{db}" OWNER "{rol}" ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C.UTF-8';
REVOKE CONNECT ON DATABASE "{db}" FROM PUBLIC;
"""
        self.psql(o, sql, db="postgres", b=b)

    def db_sil(self, o, b, rol_da=False):
        sql = f'DROP DATABASE IF EXISTS "{_sql_ad(o["db_adi"])}" WITH (FORCE);\n'
        if rol_da:
            sql += f'DROP ROLE IF EXISTS "{_sql_ad(o["db_rol"])}";\n'
        self.psql(o, sql, db="postgres", b=b)

    def dokum_al(self, o, b, hedef):
        """Ortamın veritabanını pg_dump -Fc ile hedef dosyaya alır."""
        self.docker(b, "exec", o["db_konteyner"], "pg_dump", "-U", o["db_su"], "-Fc", o["db_adi"], cikti_dosya=hedef,
                    zaman_asimi=3600)
        if not Path(hedef).exists() or Path(hedef).stat().st_size == 0:
            raise Hata(500, "Veritabanı dökümü boş çıktı.")

    def dokum_yukle(self, o, b, dosya):
        """Dökümü ortamın (boş) veritabanına yükler; nesneler ortamın rolüne geçer."""
        sonuc = self.docker(b, "exec", "-i", o["db_konteyner"], "pg_restore", "-U", o["db_su"], "-d", o["db_adi"],
                            "--no-owner", f"--role={o['db_rol']}", "--no-privileges", girdi_dosya=dosya,
                            kontrol=False, log=None, zaman_asimi=3600)
        satirlar = [s for s in sonuc.cikti.splitlines()
                    if s.strip() and "must be owner of extension" not in s and not s.startswith(
                        ("pg_restore: warning", "pg_restore: while PROCESSING", "pg_restore: from TOC entry",
                         "pg_restore: error: could not execute query: ERROR:  must be owner"))]
        if b is not None and satirlar:
            for satir in satirlar[-8:]:
                b.yaz(satir)
        sayi = self.psql(o, "SELECT count(*) FROM ir_module_module WHERE state = 'installed';", kontrol=False)
        if not sayi.isdigit() or int(sayi) == 0:
            raise Hata(500, "Veritabanı yüklenemedi (kurulu modül bulunamadı).")
        return int(sayi)

    # ------------------------------------------------------------ dosya deposu
    def birim_olustur(self, o, b):
        self.docker(b, "volume", "create", "--label", f"vekosis.panel.odoo={o['odoo']}", o["birim"])

    def filestore_kopyala(self, kaynak, hedef, b):
        """kaynak ortamın dosya deposunu hedef ortamın birimine kopyalar (hedefteki eskisi silinir)."""
        _sql_ad(kaynak["db_adi"]), _sql_ad(hedef["db_adi"])
        betik = (f"rm -rf /hedef/filestore/{hedef['db_adi']} && mkdir -p /hedef/filestore && "
                 f"if [ -d /kaynak/filestore/{kaynak['db_adi']} ]; then "
                 f"cp -a /kaynak/filestore/{kaynak['db_adi']} /hedef/filestore/{hedef['db_adi']}; "
                 f"else mkdir -p /hedef/filestore/{hedef['db_adi']}; fi && chown -R odoo:odoo /hedef/filestore")
        self.docker(b, "run", "--rm", "--user", "0", "--network", "none", "--entrypoint", "sh",
                    "-v", f"{kaynak['birim']}:/kaynak:ro", "-v", f"{hedef['birim']}:/hedef", hedef["imaj"], "-c", betik,
                    zaman_asimi=3600)

    def filestore_paketle(self, o, b, cikti_dizini):
        _sql_ad(o["db_adi"])
        betik = (f"if [ -d /veri/filestore/{o['db_adi']} ]; then "
                 f"tar -czf /cikti/filestore.tar.gz -C /veri/filestore {o['db_adi']}; fi")
        self.docker(b, "run", "--rm", "--user", "0", "--network", "none", "--entrypoint", "sh",
                    "-v", f"{o['birim']}:/veri:ro", "-v", f"{cikti_dizini}:/cikti", o["imaj"], "-c", betik,
                    zaman_asimi=3600)

    def filestore_ac(self, o, b, girdi_dizini, kaynak_db):
        """Yedekteki filestore.tar.gz'yi ortamın birimine açar (klasör adı ortamın veritabanına çevrilir)."""
        _sql_ad(o["db_adi"]), _sql_ad(kaynak_db)
        betik = (f"rm -rf /veri/filestore/{o['db_adi']} /veri/filestore/.geri && mkdir -p /veri/filestore/.geri && "
                 f"if [ -f /girdi/filestore.tar.gz ]; then tar -xzf /girdi/filestore.tar.gz -C /veri/filestore/.geri; fi && "
                 f"if [ -d /veri/filestore/.geri/{kaynak_db} ]; then "
                 f"mv /veri/filestore/.geri/{kaynak_db} /veri/filestore/{o['db_adi']}; "
                 f"else mkdir -p /veri/filestore/{o['db_adi']}; fi && rm -rf /veri/filestore/.geri && "
                 f"chown -R odoo:odoo /veri/filestore")
        self.docker(b, "run", "--rm", "--user", "0", "--network", "none", "--entrypoint", "sh",
                    "-v", f"{o['birim']}:/veri", "-v", f"{girdi_dizini}:/girdi:ro", o["imaj"], "-c", betik,
                    zaman_asimi=3600)

    # ------------------------------------------------------------ imaj
    def imaj_kimligi(self, imaj):
        sonuc = self.komut.calistir(["docker", "image", "inspect", "-f", "{{.Id}}", imaj], kontrol=False, zaman_asimi=30)
        return sonuc.cikti.strip() if sonuc.tamam else None

    def imaj_bilgisi(self, imaj):
        """İmajdaki Odoo serisi ve modül listesi (imaj kimliğine göre önbellekte)."""
        kimlik = self.imaj_kimligi(imaj)
        if not kimlik:
            raise Hata(400, f"İmaj sunucuda yok: {imaj}")
        onbellek = self.ayar.onbellek / f"imaj-{kimlik.replace(':', '_')[:80]}.json"
        bilgi = kayit.oku(onbellek)
        if bilgi:
            return bilgi
        sonuc = self.komut.calistir(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python3", imaj,
                                     "-c", IMAJ_TARAMA], zaman_asimi=180)
        satir = [s for s in sonuc.cikti.strip().splitlines() if s.startswith("{")]
        if not satir:
            raise Hata(500, "İmaj taranamadı.")
        bilgi = json.loads(satir[-1])
        kayit.yaz(onbellek, bilgi)
        return bilgi

    def python_denetle(self, imaj, adlar):
        adlar = sorted(a for a in set(adlar) if PY_SINAMA.match(a))
        if not adlar:
            return {}
        sonuc = self.komut.calistir(["docker", "run", "--rm", "--network", "none", "--entrypoint", "python3", imaj,
                                     "-c", PY_SORGU, *adlar], zaman_asimi=120)
        satir = [s for s in sonuc.cikti.strip().splitlines() if s.startswith("{")]
        return json.loads(satir[-1]) if satir else {a: False for a in adlar}

    # ------------------------------------------------------------ sunucu
    def bos_bellek_mb(self):
        try:
            for satir in Path("/proc/meminfo").read_text().splitlines():
                if satir.startswith("MemAvailable:"):
                    return int(satir.split()[1]) // 1024
        except OSError:
            pass
        return None

    def bellek_denetle(self, gereken_mb=None):
        bos = self.bos_bellek_mb()
        gereken = (gereken_mb or self.ayar.ortam_bellek_mb) + self.ayar.bellek_payi_mb
        if bos is not None and bos < gereken:
            raise Hata(409, f"Sunucuda yeterli bellek yok: boş {bos} MB, gereken {gereken} MB "
                            f"(ortam {gereken - self.ayar.bellek_payi_mb} + pay {self.ayar.bellek_payi_mb}). "
                            "Önce kullanılmayan bir ortamı durdurun.")
        return bos

    def adres_kaydet(self, adres_adi, var=True):
        """Caddy'nin isteğe bağlı SSL listesine adı ekler/çıkarır."""
        yol = self.ayar.kenar_tenants / adres_adi
        if var:
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.touch()
        else:
            yol.unlink(missing_ok=True)

    def kod_temizle(self, o, sakla=None):
        """Eski kod klasörlerini siler; şimdiki ve son 'sakla' kadar commit kalır."""
        sakla = sakla or self.ayar.kod_sakla
        kok = self.dizin(o["odoo"], o["ad"]) / "kod"
        if not kok.is_dir():
            return []
        tut = {Path(o["kod"]).name, "bos"} | set(o.get("kod_gecmisi", [])[:sakla])
        silinen = []
        for alt in kok.iterdir():
            if alt.is_dir() and alt.name not in tut and not alt.name.startswith("."):
                shutil.rmtree(alt, ignore_errors=True)
                silinen.append(alt.name)
        return silinen


def yeni_sifre(uzunluk=24):
    return secrets.token_hex(uzunluk // 2)


def _sql_ad(ad):
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,62}$", ad or ""):
        raise Hata(400, f"Geçersiz veritabanı adı: {ad}")
    return ad


def _mb(metin):
    eslesme = re.match(r"\s*([\d.]+)\s*([KMG]i?B|B)", metin or "")
    if not eslesme:
        return None
    sayi, birim = float(eslesme.group(1)), eslesme.group(2)
    carpan = {"B": 1 / 1048576, "KiB": 1 / 1024, "KB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}
    return round(sayi * carpan.get(birim, 1))


def _yuzde(metin):
    try:
        return float((metin or "").strip().rstrip("%"))
    except ValueError:
        return None
