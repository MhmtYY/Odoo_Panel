"""Zip ile yüklenen modülün depoya gitmesi.

Depoya bağlı Odoo'da modül sunucuya doğrudan konmaz: zip incelenir, uyumluluğu denetlenir, depoya commit edilir
(dala doğrudan ya da yeni dal + PR). Kod Odoo'ya her zamanki deploy yolundan gelir; depo tek doğru kaynak kalır.

İnceleme: mutlak yol, "..", sembolik bağlantı, boyut ve sıkıştırma oranı sınırı, gizli anahtar taraması.
"""
import ast
import io
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import uyumluluk
from .hata import Hata

SINIR_DOSYA = 5000
SINIR_ACIK = 200 * 1024 * 1024
SINIR_ORAN = 200
ATLANAN_KLASOR = {"__pycache__", "__MACOSX", ".git", ".idea", ".vscode"}
ATLANAN_DOSYA = {".DS_Store", "Thumbs.db"}
ATLANAN_UZANTI = {".pyc", ".pyo"}
MODUL_ADI = re.compile(r"^[a-z0-9_]{2,64}$")
GIZLI_DOSYA = re.compile(r"(^|/)(id_rsa|id_ed25519|id_ecdsa|\.env|.*\.pem|.*\.key|.*\.p12|.*\.pfx)$", re.I)
GIZLI_ICERIK = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"), "özel anahtar"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub jetonu"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"), "GitHub jetonu"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS erişim anahtarı"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "Slack jetonu"),
]
SIFRE_ICERIK = re.compile(r"(?i)\b(password|passwd|sifre|secret|api_key|apikey)\b\s*[:=]\s*['\"][^'\"\s]{6,}['\"]")
METIN_UZANTI = {".py", ".xml", ".csv", ".js", ".json", ".txt", ".conf", ".cfg", ".ini", ".yml", ".yaml", ".po", ".pot",
                ".html", ".scss", ".css", ".md", ".rst", ".sh"}


def _surum(manifest_metni):
    try:
        veri = ast.literal_eval(manifest_metni or "")
    except (ValueError, SyntaxError):
        return None
    return veri.get("version") if isinstance(veri, dict) else None


def _guvenli_ad(ad):
    ad = ad.replace("\\", "/")
    if ad.startswith("/") or re.match(r"^[A-Za-z]:", ad):
        return None
    parcalar = [p for p in ad.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parcalar):
        return None
    return "/".join(parcalar)


def incele(veri, dosya_adi, calisma):
    """Zip'i calisma/ham altına açar, modülleri calisma/moduller altına dizer. Rapor döner."""
    calisma = Path(calisma)
    ham = calisma / "ham"
    ham.mkdir(parents=True)
    rapor = {"moduller": [], "dosya": 0, "boyut": 0, "engeller": [], "uyarilar": []}
    try:
        arsiv = zipfile.ZipFile(io.BytesIO(veri))
    except zipfile.BadZipFile as hata:
        raise Hata(400, "Dosya geçerli bir zip değil.") from hata
    with arsiv:
        for bilgi in arsiv.infolist():
            ad = _guvenli_ad(bilgi.filename)
            if ad is None:
                raise Hata(400, f"Zip'te güvensiz yol var: {bilgi.filename[:120]}")
            if not ad or bilgi.is_dir():
                continue
            if stat.S_ISLNK(bilgi.external_attr >> 16):
                raise Hata(400, f"Zip'te sembolik bağlantı var: {ad[:120]}")
            parcalar = ad.split("/")
            if any(p in ATLANAN_KLASOR for p in parcalar) or parcalar[-1] in ATLANAN_DOSYA \
                    or Path(ad).suffix in ATLANAN_UZANTI:
                continue
            rapor["dosya"] += 1
            rapor["boyut"] += bilgi.file_size
            if rapor["dosya"] > SINIR_DOSYA:
                raise Hata(400, f"Zip'te çok fazla dosya var (en çok {SINIR_DOSYA}).")
            if rapor["boyut"] > SINIR_ACIK:
                raise Hata(400, "Zip açıldığında çok büyük (en çok 200 MB).")
            if bilgi.compress_size and bilgi.file_size / max(bilgi.compress_size, 1) > SINIR_ORAN and bilgi.file_size > 10 ** 6:
                raise Hata(400, f"Şüpheli sıkıştırma oranı: {ad[:120]}")
            hedef = ham / ad
            hedef.parent.mkdir(parents=True, exist_ok=True)
            with arsiv.open(bilgi) as kaynak, open(hedef, "wb") as cikti:
                shutil.copyfileobj(kaynak, cikti, 1024 * 1024)
            if GIZLI_DOSYA.search(ad):
                rapor["engeller"].append({"modul": parcalar[0], "neden": f"Gizli anahtar dosyası: {ad}"})
            elif Path(ad).suffix.lower() in METIN_UZANTI and bilgi.file_size < 2 * 1024 * 1024:
                metin = hedef.read_text(encoding="utf-8", errors="replace")
                for desen, tur in GIZLI_ICERIK:
                    if desen.search(metin):
                        rapor["engeller"].append({"modul": parcalar[0], "neden": f"{ad}: {tur} içeriyor"})
                if SIFRE_ICERIK.search(metin):
                    rapor["uyarilar"].append({"modul": parcalar[0], "neden": f"{ad}: koda yazılmış şifre olabilir"})
    moduller_dizini = calisma / "moduller"
    moduller_dizini.mkdir()
    kok = ham
    if (kok / "__manifest__.py").is_file():
        ad = re.sub(r"[-_ ]v?\d+(\.\d+)+$", "", Path(dosya_adi or "modul").stem.lower())
        ad = re.sub(r"[^a-z0-9_]", "_", ad).strip("_")
        if not MODUL_ADI.match(ad):
            raise Hata(400, "Modül zip'in kökünde; adı zip dosyasının adından çıkarılamadı. Modülü klasörüyle sıkıştırın.")
        shutil.move(str(kok), str(moduller_dizini / ad))
    else:
        adaylar = [p for p in kok.iterdir() if p.is_dir() and (p / "__manifest__.py").is_file()]
        if not adaylar:
            ust = [p for p in kok.iterdir() if p.is_dir()]
            if len(ust) == 1 and not [p for p in kok.iterdir() if p.is_file()]:
                kok = ust[0]
                adaylar = [p for p in kok.iterdir() if p.is_dir() and (p / "__manifest__.py").is_file()]
        if not adaylar:
            raise Hata(400, "Zip'te Odoo modülü bulunamadı (__manifest__.py olan klasör yok).")
        for klasor in adaylar:
            shutil.move(str(klasor), str(moduller_dizini / klasor.name))
    for klasor in sorted(moduller_dizini.iterdir()):
        if not MODUL_ADI.match(klasor.name):
            raise Hata(400, f"Geçersiz modül adı: {klasor.name} (küçük harf, rakam, alt çizgi)")
        if not (klasor / "__init__.py").is_file():
            rapor["engeller"].append({"modul": klasor.name, "neden": "__init__.py yok"})
        rapor["moduller"].append(klasor.name)
    rapor["klasor"] = str(moduller_dizini)
    return rapor


class ZipDepo:
    def __init__(self, ayar, isler, ortamlar, odoolar, deploylar, github, webhook):
        self.ayar = ayar
        self.isler = isler
        self.ortamlar = ortamlar
        self.odoolar = odoolar
        self.deploylar = deploylar
        self.github = github
        self.webhook = webhook

    def yukle(self, odoo_id, ortam, veri, dosya_adi, hedef, mesaj, kullanici=None):
        self.ayar.ortam_denetle(ortam)
        od = self.odoolar.gerekli(odoo_id)
        self.ortamlar.gerekli(odoo_id, ortam)
        depo = self.odoolar.depo_gerekli(od)
        if depo.baglanti != "app":
            raise Hata(400, "Depo deploy key ile bağlı; panel depoya yazamaz. Zip'i depoya göndermek için GitHub App "
                            "bağlantısı gerekir.")
        if hedef not in ("dal", "pr"):
            raise Hata(400, "Hedef dal ya da pr olmalı.")
        dal = od["depo"]["dallar"].get(ortam)
        if not dal:
            raise Hata(400, f"{ortam} için dal tanımlı değil.")
        mesaj = re.sub(r"[\x00-\x08\x0b-\x1f]", "", str(mesaj or "")).strip()[:500]
        return self.isler.baslat(
            "zip", f"{odoo_id}/zip",
            lambda b: self._isle(b, od, ortam, depo, dal, veri, dosya_adi, hedef, mesaj, kullanici),
            odoo=odoo_id, ortam=ortam, kullanici=kullanici, aciklama=f"Zip depoya: {dosya_adi}")

    def _isle(self, b, od, ortam, depo, dal, veri, dosya_adi, hedef, mesaj, kullanici):
        o = self.ortamlar.gerekli(od["id"], ortam)
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        calisma = Path(tempfile.mkdtemp(prefix=".zip-", dir=self.ayar.gecici))
        try:
            with b.adim("Zip inceleniyor"):
                rapor = incele(veri, dosya_adi, calisma)
                moduller = rapor["moduller"]
                b.yaz(f"Modüller: {', '.join(moduller)}; {rapor['dosya']} dosya, {rapor['boyut'] / 1048576:.1f} MB")
                if rapor["engeller"]:
                    raise Hata(400, "Zip depoya gönderilmedi: " + "; ".join(e["neden"] for e in rapor["engeller"][:5]))
            with b.adim("Depo çekiliyor"):
                taban = depo.getir(dal)
            with b.adim("Uyumluluk denetimi"):
                imaj_bilgi = self.ortamlar.imaj_bilgisi(o["imaj"])
                zip_moduller = uyumluluk.klasor_modulleri(rapor["klasor"])
                ek = uyumluluk.klasor_modulleri(o.get("ek_addons") or "")
                kurulu = self.ortamlar.kurulu_moduller(o)
                python_var = self.ortamlar.python_denetle(o["imaj"], uyumluluk.python_adlari(zip_moduller))
                gereksinim = depo.dosya(taban, "requirements.txt") or ""
                for py in [p for p, var in python_var.items() if not var]:
                    if re.search(rf"(?im)^\s*{re.escape(py).replace('_', '[-_]')}\b", gereksinim):
                        python_var[py] = True  # depodaki requirements.txt deploy'da imaja ekler
                u = uyumluluk.denetle(zip_moduller, seri=imaj_bilgi["seri"],
                                      mevcut=set(imaj_bilgi["moduller"]) | set(ek) | depo.moduller(taban),
                                      kurulu=kurulu, guncellenecek=moduller, python_var=python_var,
                                      imaj_moduller=set(imaj_bilgi["moduller"]))
                for uyari in rapor["uyarilar"] + u["uyarilar"]:
                    b.uyari(f"{uyari['modul']}: {uyari['neden']}")
                if not u["gecti"]:
                    raise Hata(400, "Uyumluluk denetimi geçmedi: " + uyumluluk.ozet(u))
                for modul in sorted(set(moduller) & kurulu):
                    eski_surum = _surum(depo.dosya(taban, f"{modul}/__manifest__.py"))
                    if eski_surum and eski_surum == u["moduller"][modul]["surum"]:
                        b.uyari(f"{modul}: sürüm numarası artırılmamış ({eski_surum}); kod yine güncellenir.")
            with b.adim("Commit hazırlanıyor"):
                baslik = mesaj or f"[ADD] {', '.join(moduller)}: zip ile yüklendi"
                govde = f"{baslik}\n\nOdoo Yönetim Paneli'nden zip ile yüklendi ({dosya_adi}); yükleyen: {kullanici or '-'}."
                yeni = depo.commit_olustur(taban, rapor["klasor"], moduller, govde)
                if not yeni:
                    b.yaz("Depodaki modülle aynı; commit gerekmedi.")
                    return {"degisiklik": False, "moduller": moduller}
            if hedef == "dal":
                with b.adim(f"{dal} dalına gönderiliyor"):
                    depo.gonder(yeni, dal, eski=taban)
                    b.yaz(f"Commit {yeni[:7]} -> {dal}")
                tetiklenen = self.webhook.push(depo.ad, dal, yeni, tetik="zip", kullanici=kullanici)
                return {"commit": yeni, "dal": dal, "moduller": moduller, "deploylar": tetiklenen}
            with b.adim("Dal açılıp PR oluşturuluyor"):
                yeni_dal = f"panel/zip-{moduller[0].replace('_', '-')}-{datetime.now():%Y%m%d-%H%M%S}"
                depo.gonder(yeni, yeni_dal)
                pr = self.github.pr_ac(depo.ad, baslik, govde, yeni_dal, dal)
                b.yaz(f"PR #{pr['no']}: {pr['adres']}")
            od = self.odoolar.gerekli(od["id"])
            od.setdefault("zip_pr", []).insert(0, {"no": pr["no"], "adres": pr["adres"], "dal": yeni_dal, "hedef": dal,
                                                   "moduller": moduller, "commit": yeni, "kullanici": kullanici})
            od["zip_pr"] = od["zip_pr"][:20]
            self.odoolar.yaz(od)
            return {"commit": yeni, "pr": pr, "moduller": moduller}
        finally:
            shutil.rmtree(calisma, ignore_errors=True)
