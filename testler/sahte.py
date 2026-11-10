"""Testler için sahte komut çalıştırıcı: Docker, PostgreSQL ve openssl'i taklit eder; git ve ssh-keygen gerçektir.

Sahte sunucu durumu:
  konteynerler {ad: durum}, birimler, imajlar {etiket: kimlik},
  veritabanlari {(db_konteyner, db): set(kurulu modüller)}
Davranış bayrakları: guncelleme_hatasi (bir sonraki -u başarısız), saglik_hatasi (sonraki N sağlık denetimi başarısız),
python_var (imajdaki Python paketleri), imaj_moduller (imaj taramasında dönen modüller).
"""
import json
import re
import shlex
from pathlib import Path

from ajan.komut import Komut, KomutHatasi, Sonuc


class SahteKomut(Komut):
    def __init__(self):
        super().__init__()
        self.gercek = Komut()
        self.cagrilar = []
        self.konteynerler = {}
        self.konteyner_env = {}
        self.birimler = set()
        self.imajlar = {"vekosis/test20:20261108-1": "sha256:temel1"}
        self.veritabanlari = {}
        self.guncelleme_hatasi = False
        self.saglik_hatasi = 0
        self.python_var = {"requests"}
        self.imaj_moduller = ["base", "web", "mail", "account", "sale", "stock", "contacts"]
        self.inceleme = {}  # docker inspect <ad> için JSON
        self.istek_satirlari = []  # izleme: docker logs --since çıktısı
        self.ps_adlari = []
        self.guncellenenler = []
        self.notrlestirilen = []
        self.yuklenen_dokumler = []

    # -- yardımcılar
    def gizle(self, *degerler):
        super().gizle(*degerler)
        self.gercek.gizle(*degerler)

    def bul(self, parca):
        return [c for c in self.cagrilar if parca in " ".join(c)]

    def _sonuc(self, kod=0, cikti="", log=None, kontrol=True, args=None, ham=b""):
        if log is not None:
            for satir in cikti.splitlines():
                log(satir)
        sonuc = Sonuc(kod, self.maskele(cikti), ham)
        if kontrol and kod != 0:
            raise KomutHatasi(args or ["?"], sonuc)
        return sonuc

    # -- giriş noktası
    def calistir(self, args, *, girdi=None, girdi_dosya=None, cikti_dosya=None, ortam=None, cwd=None,
                 zaman_asimi=3600, log=None, ikili=False, kontrol=True):
        args = [str(a) for a in args]
        if args[0] in ("git", "ssh-keygen"):
            return self.gercek.calistir(args, girdi=girdi, girdi_dosya=girdi_dosya, cikti_dosya=cikti_dosya,
                                        ortam=ortam, cwd=cwd, zaman_asimi=zaman_asimi, log=log, ikili=ikili,
                                        kontrol=kontrol)
        self.cagrilar.append(args)
        if args[0] == "openssl":
            return self._sonuc(0, "", args=args, ham=b"sahte-imza")
        if args[:2] == ["ip", "-o"]:
            return self._sonuc(0, "\n".join(f"{i}: e{i}    inet {a}/{m} scope global e{i}" for i, (a, m) in
                                            enumerate([("127.0.0.1", 8), ("89.167.114.61", 32), ("172.19.0.1", 16)], 1)),
                               log, kontrol, args)
        if args[0] != "docker":
            return self._sonuc(127, f"bilinmeyen komut {args[0]}", log, kontrol, args)
        if isinstance(girdi, bytes):
            girdi = girdi.decode("utf-8")
        kod, cikti = self._docker(args[1:], girdi, girdi_dosya, cikti_dosya)
        return self._sonuc(kod, cikti, log, kontrol, args)

    # -- docker
    def _docker(self, a, girdi, girdi_dosya, cikti_dosya):  # noqa: C901 - tek yerde okunur taklit
        if a[:2] == ["image", "inspect"]:
            imaj = a[-1]
            return (0, self.imajlar[imaj]) if imaj in self.imajlar else (1, "No such image")
        if a[0] == "inspect" and a[1] == "-f":
            ad = a[-1]
            if "{{.State.Status}}" in a[2]:
                return (0, self.konteynerler[ad]) if ad in self.konteynerler else (1, "No such object")
            if "{{.Name}}" in a[2]:
                return (0, "/" + ad) if ad in self.inceleme or ad in self.konteynerler else (1, "No such object")
            return 0, "172.18.0.5"
        if a[0] == "inspect":
            liste = [self.inceleme[ad] for ad in a[1:] if ad in self.inceleme]
            return (0, json.dumps(liste)) if liste else (1, "No such object")
        if a[0] == "ps":
            if "--filter" in a:
                suzgecler = {a[i + 1].split("=", 1)[1] for i, x in enumerate(a) if x == "--filter"}
                uyan = [ad for ad, i in self.inceleme.items()
                        if suzgecler <= {f"{k}={v}" for k, v in (i["Config"].get("Labels") or {}).items()}]
                return 0, "\n".join(uyan)
            return 0, "\n".join(self.ps_adlari + [k for k in self.konteynerler if k not in self.ps_adlari])
        if a[0] == "stats":
            return 0, "\n".join(f"{ad}|512MiB / 2GiB|1.5%" for ad in a[4:] if self.konteynerler.get(ad) == "running")
        if a[:2] == ["volume", "create"]:
            self.birimler.add(a[-1])
            return 0, a[-1]
        if a[:2] == ["volume", "rm"]:
            self.birimler.discard(a[-1])
            return 0, ""
        if a[:2] == ["rm", "-f"]:
            self.konteynerler.pop(a[-1], None)
            return 0, ""
        if a[0] in ("stop", "start"):
            self.konteynerler[a[-1]] = "exited" if a[0] == "stop" else "running"
            return 0, ""
        if a[0] == "top":
            return (0, "PID COMMAND\n" + "\n".join(f"{i} /usr/bin/python3 /usr/bin/odoo" for i in range(1, 6))
                    + "\n99 sh") if self.konteynerler.get(a[1]) == "running" else (1, "is not running")
        if a[0] == "logs":
            ad = a[-1]
            if ad not in self.konteynerler:
                return 1, "No such container"
            if "--since" in a:  # izleme: son ölçümden beri gelen istek satırları
                return 0, "\n".join(self.istek_satirlari)
            satirlar = [f"2026-11-10T10:{i:02d}:00Z 2026-11-10 10:{i:02d}:00,000 1 INFO {ad} odoo.service.server: "
                        f"istek {i}" for i in range(20)]
            satirlar.append(f"2026-11-10T10:21:00Z 2026-11-10 10:21:00,000 1 WARNING {ad} odoo.addons.base: örnek uyarı")
            return 0, "\n".join(satirlar)
        if a[0] == "build":
            etiket = a[a.index("-t") + 1]
            self.imajlar[etiket] = "sha256:turev-" + etiket
            return 0, "Successfully built"
        if a[0] == "compose":
            return self._compose(a, girdi)
        if a[0] == "exec":
            return self._exec(a, girdi, girdi_dosya, cikti_dosya)
        if a[0] == "run":
            return self._run(a)
        return 0, ""

    def _compose(self, a, girdi):
        dosya = Path(a[a.index("-f") + 1])
        env = dict(s.split("=", 1) for s in Path(a[a.index("--env-file") + 1]).read_text().splitlines() if "=" in s)
        metin = dosya.read_text(encoding="utf-8")
        konteyner = re.search(r"container_name: (\S+)", metin).group(1)
        komut = a[a.index("--env-file") + 2:]
        if komut[0] == "up":
            self.konteynerler[konteyner] = "running"
            self.konteyner_env[konteyner] = env
            return 0, f"Container {konteyner} Started"
        if komut[0] == "stop":
            if konteyner in self.konteynerler:
                self.konteynerler[konteyner] = "exited"
            return 0, ""
        if komut[0] == "down":
            self.konteynerler.pop(konteyner, None)
            return 0, ""
        if komut[0] == "run":
            odoo = komut[komut.index("odoo", 5):]
            db = odoo[odoo.index("-d") + 1]
            anahtar = self._db_anahtari(db)
            if "neutralize" in odoo:
                self.notrlestirilen.append(db)
                return 0, "Neutralization finished"
            if "shell" in odoo:
                return 0, "ORNEK SILINDI: 0\nKISISEL_TAMAM"
            if "-i" in odoo:
                self.veritabanlari[anahtar] = set(odoo[odoo.index("-i") + 1].split(","))
                return 0, "Modules loaded."
            if "-u" in odoo:
                moduller = odoo[odoo.index("-u") + 1].split(",")
                self.guncellenenler.append((db, moduller, env.get("KOD"), env.get("IMAJ")))
                if self.guncelleme_hatasi:
                    self.guncelleme_hatasi = False
                    return 1, "2026-11-10 10:00:00,000 1 ERROR pnl odoo.modules.loading: Failed to load module"
                return 0, f"2026-11-10 10:00:00,000 1 INFO pnl odoo.modules.loading: {len(moduller)} modules updated"
        return 0, ""

    def _db_anahtari(self, db):
        for (konteyner, ad) in self.veritabanlari:
            if ad == db:
                return (konteyner, ad)
        return ("vtest-postgres", db)

    def _exec(self, a, girdi, girdi_dosya, cikti_dosya):
        i = 1
        while a[i].startswith("-"):
            i += 1
        konteyner, program = a[i], a[i + 1:]
        if program[:2] == ["python3", "-c"]:
            if self.saglik_hatasi > 0:
                self.saglik_hatasi -= 1
                return 1, ""
            return (0, "") if self.konteynerler.get(konteyner) == "running" else (1, "not running")
        if program[0] == "pg_dump":
            db = program[-1]
            moduller = sorted(self.veritabanlari.get((konteyner, db), set()))
            Path(cikti_dosya).write_text(json.dumps({"db": db, "moduller": moduller}), encoding="utf-8")
            return 0, ""
        if program[0] == "pg_restore":
            db = program[program.index("-d") + 1]
            dokum = json.loads(Path(girdi_dosya).read_text(encoding="utf-8"))
            self.veritabanlari[(konteyner, db)] = set(dokum["moduller"])
            self.yuklenen_dokumler.append((db, dokum["db"]))
            return 0, ""
        if program[0] == "psql":
            db = program[program.index("-d") + 1]
            return self._sql(konteyner, db, girdi or "")
        return 0, ""

    def _sql(self, konteyner, db, sql):
        anahtar = (konteyner, db)
        if "asistan_sorgusu" in sql:  # asistanın salt okunur sorgusu (--csv)
            return 0, "id,name\n1,Azure\n2,Deco\n"
        if "pg_database_size" in sql:
            return 0, "\n".join(f"{d}|104857600" for k, d in self.veritabanlari if k == konteyner)
        if "FROM pg_database" in sql:
            ad = re.search(r"datname = '([^']+)'", sql).group(1)
            return 0, "1" if (konteyner, ad) in self.veritabanlari else ""
        cikti = []
        for eslesme in re.finditer(r'DROP DATABASE IF EXISTS "([^"]+)"', sql):
            self.veritabanlari.pop((konteyner, eslesme.group(1)), None)
        for eslesme in re.finditer(r'CREATE DATABASE "([^"]+)"[^;]*?(?:TEMPLATE "?([A-Za-z0-9_]+)"?)?;', sql):
            sablon = eslesme.group(2)
            kaynak = self.veritabanlari.get((konteyner, sablon), set()) if sablon and sablon != "template0" else set()
            self.veritabanlari[(konteyner, eslesme.group(1))] = set(kaynak)
        if "FROM pg_stat_activity" in sql:
            return 0, "\n".join(f"{d}|3" for k, d in self.veritabanlari if k == konteyner)
        if "table_name = 'ir_cron'" in sql:
            return 0, "\n".join(["id", "cron_name", "active", "nextcall", "lastcall", "failure_count",
                                 "interval_number", "interval_type", "ir_actions_server_id"])
        if "AS aralik_turu FROM ir_cron c" in sql:  # izleme: zamanlanmış işler listesi
            return 0, json.dumps([
                {"id": 1, "ad": "Posta kuyruğu", "etkin": True, "sonraki": "2026-11-10T18:30:00", "son": "2026-11-10T18:25:00",
                 "hata_sayisi": 0, "aralik": 5, "aralik_turu": "minutes"},
                {"id": 2, "ad": "Kur güncelleme", "etkin": True, "sonraki": "2026-11-11T09:00:00", "son": "2026-11-10T09:00:00",
                 "hata_sayisi": 2, "aralik": 1, "aralik_turu": "days"}])
        if "json_build_object('ad', m.name" in sql:  # modül listesi: kurulu olanlar + imajdaki diğerleri
            kurulu = self.veritabanlari.get(anahtar, set())
            return 0, json.dumps([{"ad": m, "baslik": json.dumps({"en_US": m.title(), "tr_TR": m.title() + " TR"}),
                                   "durum": "installed" if m in kurulu else "uninstalled", "surum": "20.0.1.0.0",
                                   "yazar": "Odoo S.A.", "uygulama": m == "sale", "lisans": "LGPL-3",
                                   "kategori": json.dumps({"en_US": "Sales"})}
                                  for m in sorted(kurulu | set(self.imaj_moduller))])
        if "latest_version" in sql:
            return 0, "\n".join(f"{m}|20.0.1.0.0" for m in sorted(self.veritabanlari.get(anahtar, set())))
        if "WHERE state = 'installed' ORDER BY 1" in sql:
            return 0, "\n".join(sorted(self.veritabanlari.get(anahtar, set())))
        if "count(*) FROM ir_module_module WHERE state = 'installed'" in sql:
            return 0, str(len(self.veritabanlari.get(anahtar, set())))
        if "to upgrade" in sql:
            return 0, ""
        if "pg_get_userbyid" in sql:
            return 0, "0"
        if "database.is_neutralized" in sql:
            cikti += ["notr=True", "cron=0", "posta=0", "entegrator_tablosu=t"]
        if "FROM gib_integrator WHERE active" in sql:
            return 0, "0"
        return 0, "\n".join(cikti)

    def _run(self, a):
        if "--entrypoint" in a and a[a.index("--entrypoint") + 1] == "python3":
            imaj = a[a.index("--entrypoint") + 2]
            betik = a[a.index("-c") + 1]
            if "release.series" in betik:
                return 0, json.dumps({"seri": "20.0", "surum": "20.0", "moduller": self.imaj_moduller,
                                      "yollar": ["/mnt/vekosis-addons"]})
            adlar = a[a.index("-c") + 2:]
            turev = imaj.startswith("pnl/")
            return 0, json.dumps({n: (n in self.python_var) or turev for n in adlar})
        # dosya deposu işlemleri: /cikti bağlaması varsa sahte filestore.tar.gz yaz
        for i, parca in enumerate(a):
            if parca == "-v" and a[i + 1].endswith(":/cikti"):
                Path(a[i + 1].rsplit(":", 1)[0], "filestore.tar.gz").write_bytes(b"sahte")
        return 0, ""


def sahte_http(yanitlar):
    """GitHub API taklidi: yanitlar {(yöntem, yol_parcasi): (durum, json)}; çağrılar listesi döner."""
    cagrilar = []

    def http(yontem, url, basliklar, govde):
        cagrilar.append((yontem, url, json.loads(govde) if govde else None))
        for (y, parca), yanit in yanitlar.items():
            if y == yontem and parca in url:
                return yanit
        return 404, {"message": "Not Found"}

    http.cagrilar = cagrilar
    return http


def komut_metni(args):
    return " ".join(shlex.quote(a) for a in args)
