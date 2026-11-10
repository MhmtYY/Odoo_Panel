"""Asistan ve bağlı ajanlar (MCP) için ajan tarafı: kod okuma, salt okunur SQL, staging dalına commit.

Bu uçlar tarayıcıdan çağrılmaz; panel yalnız kendi araç katmanından (yetki ve kapsam denetiminden sonra) çağırır.

Sınırlar:
  - Kod: ortamda ÇALIŞAN kod (panelin kurduğu Odoo'da deploy edilmiş commit ve ek klasör; bağlanan kurulumda
    konteynere bağlanan eklenti klasörleri). Lisanslı (enterprise) klasörler, odoo.conf, anahtar ve .env dosyaları
    okunmaz.
  - SQL: tek SELECT / WITH / EXPLAIN cümlesi; süper kullanıcı OLMAYAN "pnl_okuyucu" rolüyle, salt okunur işlemde,
    15 sn sınırla. Rolün yetkisi sütun düzeyinde verilir; adı şifre, anahtar, jeton ve benzeri olan sütunlar ve
    ir_config_parameter tablosu okunamaz.
  - Commit: yalnız staging dalına, GitHub App bağlantısıyla; .github/ ve .git/ altına yazılmaz.
"""
import csv
import io
import re
import time
from pathlib import Path

from .hata import Hata

OKUYUCU = "pnl_okuyucu"
GIZLI_SUTUN = r"(pass|secret|token|sifre|parola|credential|private|totp|(^|_)key($|_)|apikey|api_key|refresh|salt)"
GIZLI_DOSYA = re.compile(r"(^|/)(odoo\.conf|\.env[^/]*|[^/]*\.(pem|key|p12|pfx|crt)|id_(rsa|ed25519)[^/]*|\.git)(/|$)", re.I)
METIN_UZANTI = {".py", ".xml", ".js", ".csv", ".po", ".pot", ".scss", ".css", ".txt", ".md", ".rst", ".json", ".yml",
                ".yaml", ".html", ".sql", ".cfg", ".toml", ".ini", ".sh", ".xsl", ".xslt"}
SINIR_OKU = 2 * 1024 * 1024
SINIR_SATIR = 800
SINIR_ARA = 200
SINIR_SQL_SATIR = 200


def _yol_denetle(yol):
    yol = str(yol or "").replace("\\", "/").strip("/")
    if any(p in ("..", "") for p in yol.split("/")) and yol:
        raise Hata(400, "Geçersiz yol.")
    if GIZLI_DOSYA.search(yol):
        raise Hata(403, "Bu dosya asistana kapalı (yapılandırma, anahtar ya da gizli dosya).")
    return yol


class Asistan:
    def __init__(self, ayar, komut, ortamlar, odoolar, webhook):
        self.ayar = ayar
        self.komut = komut
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.webhook = webhook
        self._okuyucu_hazir = {}  # (db_konteyner, db) -> zaman

    # ------------------------------------------------------------ kod
    def kaynaklar(self, odoo_id, ortam):
        """{etiket: klasör}: ortamda çalışan, asistanın okuyabileceği kod klasörleri."""
        o = self.ortamlar.gerekli(odoo_id, ortam)
        kaynak = {}
        if o.get("yonetim") == "panel":
            if o.get("kod") and Path(o["kod"]).is_dir():
                kaynak["depo"] = Path(o["kod"])
            if o.get("ek_addons") and Path(o["ek_addons"]).is_dir():
                kaynak["ek"] = Path(o["ek_addons"])
        else:
            for i, (kaynak_yol, hedef) in enumerate((o.get("kesif") or {}).get("kod_baglamalari", [])):
                if re.search(r"enterprise", f"{kaynak_yol} {hedef}", re.I) or not Path(kaynak_yol).is_dir():
                    continue
                kaynak[Path(hedef).name or f"ek{i}"] = Path(kaynak_yol)
        return kaynak

    def _coz(self, odoo_id, ortam, yol):
        yol = _yol_denetle(yol)
        kaynak = self.kaynaklar(odoo_id, ortam)
        if not yol:
            return kaynak, None, None
        etiket, _, ic = yol.partition("/")
        if etiket not in kaynak:
            raise Hata(404, f"Kaynak bulunamadı: {etiket}. Kökler: {', '.join(kaynak) or 'yok'}.")
        kok = kaynak[etiket].resolve()
        hedef = (kok / ic).resolve() if ic else kok
        if hedef != kok and kok not in hedef.parents:
            raise Hata(400, "Geçersiz yol.")
        return kaynak, kok, hedef

    def kod_listele(self, odoo_id, ortam, yol=""):
        kaynak, kok, hedef = self._coz(odoo_id, ortam, yol)
        if hedef is None:
            return {"yol": "", "ogeler": [{"ad": k, "tur": "klasor"} for k in sorted(kaynak)]}
        if not hedef.is_dir():
            raise Hata(400, "Bu bir klasör değil; içeriği için kod_oku kullanın.")
        ogeler = []
        for p in sorted(hedef.iterdir(), key=lambda x: (not x.is_dir(), x.name))[:500]:
            goreli = f"{yol.strip('/')}/{p.name}"
            if p.name.startswith(".git") or GIZLI_DOSYA.search(goreli) or p.is_symlink():
                continue
            ogeler.append({"ad": p.name, "tur": "klasor" if p.is_dir() else "dosya",
                           **({} if p.is_dir() else {"boyut": p.stat().st_size})})
        return {"yol": yol.strip("/"), "ogeler": ogeler}

    def kod_oku(self, odoo_id, ortam, yol, bas=1, son=None):
        _, kok, hedef = self._coz(odoo_id, ortam, yol)
        if hedef is None or not hedef.is_file() or hedef.is_symlink():
            raise Hata(404, "Dosya bulunamadı.")
        if hedef.stat().st_size > SINIR_OKU:
            raise Hata(413, "Dosya 2 MB'tan büyük; kod_ara ile parça arayın.")
        satirlar = hedef.read_bytes().decode("utf-8", "replace").splitlines()
        bas = max(1, int(bas or 1))
        son = min(len(satirlar), int(son) if son else bas + SINIR_SATIR - 1, bas + SINIR_SATIR - 1)
        return {"yol": yol.strip("/"), "toplam_satir": len(satirlar), "bas": bas, "son": son,
                "icerik": "\n".join(f"{i}\t{s}" for i, s in enumerate(satirlar[bas - 1:son], bas))}

    def kod_ara(self, odoo_id, ortam, desen, yol=""):
        if not desen or len(desen) > 200:
            raise Hata(400, "Arama deseni 1-200 karakter olmalı.")
        try:
            duzenli = re.compile(desen)
        except re.error as hata:
            raise Hata(400, f"Geçersiz düzenli ifade: {hata}") from None
        kaynak, kok, hedef = self._coz(odoo_id, ortam, yol)
        kokler = [(k, v.resolve()) for k, v in kaynak.items()] if hedef is None else [(yol.strip("/"), hedef)]
        bulunan, taranan, bitis = [], 0, time.monotonic() + 20
        for etiket, klasor in kokler:
            dosyalar = [klasor] if klasor.is_file() else klasor.rglob("*")
            for p in dosyalar:
                if time.monotonic() > bitis or len(bulunan) >= SINIR_ARA:
                    break
                if not p.is_file() or p.is_symlink() or p.suffix.lower() not in METIN_UZANTI or "/.git" in p.as_posix():
                    continue
                goreli = f"{etiket}/{p.relative_to(klasor).as_posix()}" if p != klasor else etiket
                if GIZLI_DOSYA.search(goreli) or p.stat().st_size > 1024 * 1024:
                    continue
                taranan += 1
                for no, satir in enumerate(p.read_bytes().decode("utf-8", "replace").splitlines(), 1):
                    if duzenli.search(satir):
                        bulunan.append({"yol": goreli, "satir": no, "metin": satir.strip()[:300]})
                        if len(bulunan) >= SINIR_ARA:
                            break
        return {"desen": desen, "taranan_dosya": taranan, "sonuc": bulunan, "kesik": len(bulunan) >= SINIR_ARA}

    # ------------------------------------------------------------ SQL
    def _okuyucu_hazirla(self, o):
        anahtar = (o["db_konteyner"], o["db_adi"])
        if time.time() - self._okuyucu_hazir.get(anahtar, 0) < 600:
            return
        db = o["db_adi"].replace('"', "")
        sql = f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{OKUYUCU}') THEN
    CREATE ROLE {OKUYUCU} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
  END IF;
END $$;
GRANT CONNECT ON DATABASE "{db}" TO {OKUYUCU};
GRANT USAGE ON SCHEMA public TO {OKUYUCU};
REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {OKUYUCU};
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT c.table_name, string_agg(quote_ident(c.column_name), ', ') AS sutunlar
           FROM information_schema.columns c JOIN information_schema.tables t
             ON t.table_schema = c.table_schema AND t.table_name = c.table_name
           WHERE c.table_schema = 'public' AND t.table_type IN ('BASE TABLE', 'VIEW')
             AND c.column_name !~* '{GIZLI_SUTUN}' AND c.table_name <> 'ir_config_parameter'
           GROUP BY c.table_name LOOP
    EXECUTE format('GRANT SELECT (%s) ON public.%I TO {OKUYUCU}', r.sutunlar, r.table_name);
  END LOOP;
END $$;
"""
        self.ortamlar.psql(o, sql)
        self._okuyucu_hazir[anahtar] = time.time()

    def sql_oku(self, odoo_id, ortam, sorgu):
        o = self.ortamlar.gerekli(odoo_id, ortam)
        sorgu = str(sorgu or "").strip().rstrip(";").strip()
        if not sorgu or len(sorgu) > 20000:
            raise Hata(400, "Sorgu boş ya da çok uzun.")
        if ";" in re.sub(r"'(?:[^']|'')*'", "''", sorgu):
            raise Hata(400, "Yalnız tek bir sorgu çalıştırılabilir.")
        if not re.match(r"(?is)^\s*(select|with|explain)\b", sorgu):
            raise Hata(400, "Yalnız SELECT, WITH ya da EXPLAIN sorgusu çalıştırılabilir.")
        self._okuyucu_hazirla(o)
        govde = sorgu if re.match(r"(?is)^\s*explain\b", sorgu) else \
            f"SELECT * FROM (\n{sorgu}\n) AS asistan_sorgusu LIMIT {SINIR_SQL_SATIR + 1}"
        girdi = ("SET statement_timeout = '15s';\nSET lock_timeout = '2s';\nBEGIN TRANSACTION READ ONLY;\n"
                 f"{govde};\nROLLBACK;\n")
        sonuc = self.komut.calistir(["docker", "exec", "-i", o["db_konteyner"], "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                                     "-U", OKUYUCU, "-d", o["db_adi"], "--csv"], girdi=girdi, kontrol=False, zaman_asimi=40)
        cikti = sonuc.cikti
        if not sonuc.tamam:
            hata = next((s for s in cikti.splitlines() if "ERROR" in s or "FATAL" in s), cikti.strip()[-500:])
            ipucu = " Gizli sütunlar (şifre, anahtar, jeton) okunamaz; sütunları tek tek yazın." \
                if "permission denied" in cikti else ""
            raise Hata(400, f"Sorgu çalışmadı: {hata.strip()[:500]}{ipucu}")
        satirlar = list(csv.reader(io.StringIO(cikti)))
        if not satirlar:
            return {"sutunlar": [], "satirlar": [], "kesik": False}
        sutunlar, veri = satirlar[0], satirlar[1:]
        kesik = len(veri) > SINIR_SQL_SATIR
        return {"sutunlar": sutunlar, "satirlar": [[h[:500] for h in s] for s in veri[:SINIR_SQL_SATIR]], "kesik": kesik}

    # ------------------------------------------------------------ staging commit
    def staging_commit(self, odoo_id, dosyalar, mesaj, kullanici=None, isler=None):
        od = self.odoolar.gerekli(odoo_id)
        depo = self.odoolar.depo_gerekli(od)
        if depo.baglanti != "app":
            raise Hata(400, "Depo GitHub App ile bağlı değil; panel depoya yazamaz.")
        dal = (od["depo"].get("dallar") or {}).get("staging")
        if not dal:
            raise Hata(400, "Bu platformda staging dalı tanımlı değil (Ayarlar > Kod deposu).")
        if not isinstance(dosyalar, list) or not 1 <= len(dosyalar) <= 30:
            raise Hata(400, "1-30 dosya verilmeli: [{yol, icerik}] (silmek için icerik: null).")
        degisiklik = {}
        for d in dosyalar:
            yol = _yol_denetle((d or {}).get("yol"))
            if not yol or yol.startswith(".github/") or "/" not in yol and not yol.endswith((".txt", ".md")):
                raise Hata(400, f"Bu yola yazılamaz: {yol or '(boş)'}. Değişiklik modül klasörlerinin içinde olmalı.")
            icerik = d.get("icerik")
            if icerik is not None and (not isinstance(icerik, str) or len(icerik.encode("utf-8")) > 512 * 1024):
                raise Hata(400, f"{yol}: içerik metin olmalı ve 512 KB'ı geçmemeli.")
            degisiklik[yol] = icerik
        mesaj = re.sub(r"[\x00-\x08\x0b-\x1f]", "", str(mesaj or "")).strip()[:500] or "[IMP] asistan değişikliği"

        def isle(b):
            with b.adim("Depo çekiliyor"):
                taban = depo.getir(dal)
            with b.adim("Commit hazırlanıyor"):
                govde = f"{mesaj}\n\nOdoo Yönetim Paneli asistanı; onaylayan: {kullanici or '-'}."
                yeni = depo.dosyalari_degistir(taban, degisiklik, govde)
                if not yeni:
                    b.yaz("Dosyalar depodakiyle aynı; commit gerekmedi.")
                    return {"degisiklik": False}
                b.yaz("Değişen dosyalar: " + ", ".join(degisiklik))
            with b.adim(f"{dal} dalına gönderiliyor"):
                depo.gonder(yeni, dal, eski=taban)
                b.yaz(f"Commit {yeni[:7]} -> {dal}")
            tetiklenen = self.webhook.push(depo.ad, dal, yeni, tetik="asistan", kullanici=kullanici)
            return {"commit": yeni, "dal": dal, "dosyalar": list(degisiklik), "deploylar": tetiklenen}

        return isler.baslat("asistan-commit", f"{odoo_id}/asistan", isle, odoo=odoo_id, ortam="staging",
                            kullanici=kullanici, aciklama=f"Asistan değişikliği: {mesaj[:80]}")
