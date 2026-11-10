"""Uyumluluk denetimi: kod Odoo'ya gitmeden önce modüllerin bu Odoo'da çalışıp çalışmayacağına bakar.

Denetlenenler (modül başına):
  * sürüm serisi (ör. 19.0.x modül 20.0 Odoo'ya)
  * bağımlılıklar: depoda, imajda ya da ek klasörde var mı; yoksa Enterprise modülü mü
  * Python bağımlılıkları (external_dependencies) imajda var mı
  * Python sözdizimi, manifest'te adı geçen veri dosyalarının varlığı ve XML biçimi

Sorunlu modül kurulu ya da güncellenecekse ENGEL (deploy durur), değilse UYARI.
"""
import ast
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Odoo Enterprise'a özgü sık modüller (Community imajında bulunmazlar)
EE_MODULLER = {
    "web_enterprise", "web_studio", "account_accountant", "accountant", "account_asset", "account_reports",
    "account_loans", "account_budget", "account_consolidation", "account_followup", "documents", "documents_account",
    "sign", "planning", "helpdesk", "industry_fsm", "quality", "quality_control", "quality_mrp", "mrp_workorder",
    "mrp_plm", "mrp_maintenance", "stock_barcode", "approvals", "approvals_purchase", "hr_payroll",
    "hr_payroll_account", "l10n_tr_hr_payroll", "l10n_tr_reports", "sale_subscription", "sale_commission",
    "social", "marketing_automation", "voip", "knowledge", "appointment", "timesheet_grid", "project_forecast",
    "hr_appraisal", "hr_referral", "website_studio", "data_cleaning", "spreadsheet_edition", "planning_field_service",
}
PY_AD = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,80}$")


def manifest_oku(klasor):
    yol = Path(klasor) / "__manifest__.py"
    if not yol.is_file():
        return None
    try:
        veri = ast.literal_eval(yol.read_text(encoding="utf-8"))
    except (ValueError, SyntaxError, UnicodeDecodeError):
        return {"_hatali": True}
    return veri if isinstance(veri, dict) else {"_hatali": True}


def klasor_modulleri(dizin):
    """Klasörün ilk düzeyindeki modüller: {ad: (klasör, manifest)}"""
    dizin = Path(dizin)
    if not dizin.is_dir():
        return {}
    sonuc = {}
    for alt in sorted(dizin.iterdir()):
        if alt.is_dir() and not alt.name.startswith("."):
            manifest = manifest_oku(alt)
            if manifest is not None:
                sonuc[alt.name] = (alt, manifest)
    return sonuc


def python_adlari(moduller):
    adlar = set()
    for _klasor, manifest in moduller.values():
        for ad in ((manifest.get("external_dependencies") or {}).get("python") or []):
            if isinstance(ad, str) and PY_AD.match(ad):
                adlar.add(ad)
    return adlar


def _seri(surum):
    parca = str(surum or "").split(".")
    if len(parca) >= 4:
        return f"{parca[0]}.{parca[1]}"
    return None


def _dosya_sorunlari(klasor, manifest):
    sorunlar = []
    for py in sorted(Path(klasor).rglob("*.py")):
        try:
            compile(py.read_bytes(), str(py), "exec", dont_inherit=True)
        except SyntaxError as hata:
            sorunlar.append(f"Python sözdizimi hatası: {py.relative_to(klasor)} satır {hata.lineno}")
        except (ValueError, UnicodeDecodeError):
            sorunlar.append(f"Okunamayan Python dosyası: {py.relative_to(klasor)}")
        if len(sorunlar) >= 5:
            break
    for anahtar in ("data", "demo"):
        for veri in manifest.get(anahtar) or []:
            if not isinstance(veri, str):
                continue
            yol = Path(klasor) / veri
            if not yol.is_file():
                if anahtar == "data":
                    sorunlar.append(f"Manifest'teki dosya yok: {veri}")
                continue
            if yol.suffix == ".xml":
                try:
                    ET.parse(yol)
                except ET.ParseError as hata:
                    sorunlar.append(f"XML hatası: {veri} ({hata})")
    return sorunlar


def denetle(moduller, *, seri, mevcut, kurulu=(), guncellenecek=(), python_var=None, imaj_moduller=()):
    """moduller: {ad: (klasör, manifest)} denetlenecek modüller.
    mevcut: Odoo'nun bulabileceği diğer modüller (imaj + ek klasör + depodaki diğerleri).
    kurulu: veritabanında kurulu modüller. guncellenecek: bu işte kurulacak ya da güncellenecekler.
    python_var: {python adı: bool} imajda bulunma durumu.
    """
    python_var = python_var or {}
    kullanilan = set(kurulu) | set(guncellenecek)
    tum = set(mevcut) | set(moduller)
    sonuc = {"seri": seri, "moduller": {}, "engeller": [], "uyarilar": []}
    for ad, (klasor, manifest) in sorted(moduller.items()):
        notlar = []
        if manifest.get("_hatali"):
            notlar.append("__manifest__.py okunamadı")
        else:
            modul_seri = _seri(manifest.get("version"))
            if modul_seri and modul_seri != seri:
                notlar.append(f"Sürüm {manifest.get('version')}: {modul_seri} serisi için yazılmış, bu Odoo {seri}")
            for bag in manifest.get("depends") or []:
                if bag not in tum:
                    if bag in EE_MODULLER:
                        notlar.append(f"Enterprise modülüne bağlı: {bag} (bu Odoo'da yok)")
                    else:
                        notlar.append(f"Bağımlılık bulunamadı: {bag}")
            for py in sorted((manifest.get("external_dependencies") or {}).get("python") or []):
                if python_var.get(py) is False:
                    notlar.append(f"Python paketi imajda yok: {py}")
            notlar.extend(_dosya_sorunlari(klasor, manifest))
        kurulamaz = manifest.get("installable", True) is False
        durum = "uygun"
        if notlar:
            durum = "engel" if ad in kullanilan and not kurulamaz else "uyari"
        bilgi = {"surum": manifest.get("version", ""), "ad": manifest.get("name", ad), "durum": durum,
                 "notlar": notlar, "kurulu": ad in kurulu, "kurulamaz": kurulamaz}
        if ad in imaj_moduller:
            bilgi["notlar"] = bilgi["notlar"] + ["İmajda aynı adlı modül var; depodaki kullanılır"]
        sonuc["moduller"][ad] = bilgi
        for not_ in notlar:
            (sonuc["engeller"] if durum == "engel" else sonuc["uyarilar"]).append({"modul": ad, "neden": not_})
    sonuc["gecti"] = not sonuc["engeller"]
    return sonuc


def ozet(rapor, sinir=4):
    """Deploy kaydına yazılacak kısa metin."""
    satirlar = [f"{e['modul']}: {e['neden']}" for e in rapor["engeller"][:sinir]]
    if len(rapor["engeller"]) > sinir:
        satirlar.append(f"... ve {len(rapor['engeller']) - sinir} sorun daha")
    return "; ".join(satirlar)
