"""Asistan ve bağlı ajanların (MCP) araçları.

Panel içi sohbet ve MCP aynı araçları kullanır. Her çağrıda:
  - kullanıcının ROLÜ aracın yetkisini taşımalı (yetki.py),
  - platform kullanıcının KAPSAMINDA olmalı,
  - production'a yazan araç yoktur; kod değişikliği yalnız staging dalına gider.
Araçlar ajana panelin kendi anahtarıyla gider; tarayıcıdan bu uçlara doğrudan erişim yoktur.
"""
import json
import re
from urllib.parse import quote

from .yetki import kapsam_tum, kapsamda, yetkili

ORTAMLAR = ("production", "staging")
SINIR_METIN = 60000  # bir aracın modele dönen en uzun çıktısı (karakter)


class AracHatasi(Exception):
    pass


def _p():
    from . import panel  # döngüsel içe aktarmayı önlemek için geç yükleme
    return panel


def _ozellik(tur, aciklama, **ek):
    return {"type": tur, "description": aciklama, **ek}


PLATFORM = _ozellik("string", "Platform kimliği (platformlari_listele çıktısındaki id).")
ORTAM = _ozellik("string", "Ortam: production ya da staging.", enum=list(ORTAMLAR))


def _sema(ozellikler, gerekli):
    return {"type": "object", "properties": ozellikler, "required": gerekli, "additionalProperties": False}


# ad -> (başlık, açıklama, şema, yetki, yazar mı)
ARACLAR = {
    "platformlari_listele": (
        "Platformları listele",
        "Erişebildiğin platformları (Odoo kurulumlarını) ortamlarıyla, durumlarıyla ve adresleriyle listeler. "
        "Diğer araçlara verilecek platform kimliği buradan alınır.",
        _sema({}, []), "izle", False),
    "ortam_durumu": (
        "Ortam durumu",
        "Bir ortamın konteyner durumu, imajı, çalışan commit'i, bellek ve işlemci kullanımı.",
        _sema({"platform": PLATFORM, "ortam": ORTAM}, ["platform", "ortam"]), "izle", False),
    "izleme_ozeti": (
        "İzleme özeti",
        "Dakikalık ölçümlerin özeti: işlemci, bellek, istek/dakika, yanıt süresi (p95), 5xx hata oranı, erişilebilirlik, "
        "en yavaş uçlar ve zamanlanmış işlerin (ir_cron) durumu.",
        _sema({"platform": PLATFORM, "ortam": ORTAM,
               "saat": _ozellik("integer", "Geriye dönük süre (saat): 1, 24 ya da 168.", enum=[1, 24, 168])},
              ["platform", "ortam"]), "izle", False),
    "loglar": (
        "Loglar",
        "Odoo konteynerinin son log satırları. seviye ile yalnız uyarı/hata, ara ile metin süzülebilir.",
        _sema({"platform": PLATFORM, "ortam": ORTAM,
               "satir": _ozellik("integer", "Okunacak son satır sayısı (50-3000, varsayılan 300)."),
               "seviye": _ozellik("string", "hepsi, uyari (uyarı ve hata) ya da hata.", enum=["hepsi", "uyari", "hata"]),
               "ara": _ozellik("string", "Yalnız bu metni içeren satırlar (büyük/küçük harf duyarsız).")},
              ["platform", "ortam"]), "izle", False),
    "moduller": (
        "Modüller",
        "Veritabanındaki modüller: durum, sürüm, kaynak (depo / ek klasör / standart).",
        _sema({"platform": PLATFORM, "ortam": ORTAM,
               "suzgec": _ozellik("string", "kurulu, ozel (bu platforma özel), kurulu_degil ya da hepsi.",
                                  enum=["kurulu", "ozel", "kurulu_degil", "hepsi"]),
               "ara": _ozellik("string", "Teknik ad ya da başlıkta aranacak metin.")},
              ["platform", "ortam"]), "izle", False),
    "deploy_gecmisi": (
        "Deploy geçmişi",
        "Ortamın son deploy kayıtları: commit, sonuç, süre, güncellenen modüller.",
        _sema({"platform": PLATFORM, "ortam": ORTAM}, ["platform", "ortam"]), "izle", False),
    "deploy_ayrintisi": (
        "Deploy ayrıntısı",
        "Bir deploy kaydının adımları, uyarıları ve log çıktısı.",
        _sema({"platform": PLATFORM, "ortam": ORTAM, "no": _ozellik("integer", "Deploy numarası.")},
              ["platform", "ortam", "no"]), "izle", False),
    "yedekler": (
        "Yedekler",
        "Ortamın yedek listesi: tarih, tür, boyut, commit.",
        _sema({"platform": PLATFORM, "ortam": ORTAM}, ["platform", "ortam"]), "yedekAl", False),
    "is_durumu": (
        "İş durumu",
        "Arka planda süren bir işin (deploy, yedek, commit) durumu ve son log satırları.",
        _sema({"is_no": _ozellik("string", "12 karakterlik iş numarası.")}, ["is_no"]), "izle", False),
    "kod_listele": (
        "Kod klasörü",
        "Ortamda çalışan kodun klasör içeriği. yol boşsa kök klasörler (depo, ek ...) listelenir. "
        "Lisanslı modüller, odoo.conf ve anahtar dosyaları görünmez.",
        _sema({"platform": PLATFORM, "ortam": ORTAM,
               "yol": _ozellik("string", "Kökten göreli yol, ör. depo/ornek_stok/models.")},
              ["platform", "ortam"]), "asistan", False),
    "kod_oku": (
        "Kod dosyası oku",
        "Ortamda çalışan bir kaynak dosyayı satır numaralarıyla okur (bir seferde en çok 800 satır).",
        _sema({"platform": PLATFORM, "ortam": ORTAM, "yol": _ozellik("string", "Dosya yolu, ör. depo/ornek_stok/models/stok.py."),
               "bas": _ozellik("integer", "İlk satır (1'den başlar)."), "son": _ozellik("integer", "Son satır.")},
              ["platform", "ortam", "yol"]), "asistan", False),
    "kod_ara": (
        "Kodda ara",
        "Ortamda çalışan kodda düzenli ifadeyle arar (.py, .xml, .js, .csv, .po ...); en çok 200 sonuç.",
        _sema({"platform": PLATFORM, "ortam": ORTAM, "desen": _ozellik("string", "Python düzenli ifadesi."),
               "yol": _ozellik("string", "Aramayı bu klasör ya da dosyayla sınırla.")},
              ["platform", "ortam", "desen"]), "asistan", False),
    "sql_sorgu": (
        "Veritabanı sorgusu (salt okunur)",
        "Ortamın veritabanında tek bir SELECT/WITH/EXPLAIN sorgusu çalıştırır: salt okunur işlem, 15 sn sınırı, "
        "en çok 200 satır. Şifre, anahtar ve jeton sütunları ile ir_config_parameter okunamaz; SELECT * yerine "
        "sütun adlarını yazın.",
        _sema({"platform": PLATFORM, "ortam": ORTAM, "sorgu": _ozellik("string", "PostgreSQL sorgusu.")},
              ["platform", "ortam", "sorgu"]), "asistan", False),
    "yedek_al": (
        "Yedek al",
        "Ortamın veritabanı ve dosya deposunun yedeğini başlatır (iş numarası döner).",
        _sema({"platform": PLATFORM, "ortam": ORTAM}, ["platform", "ortam"]), "yedekAl", True),
    "staging_degisikligi_gonder": (
        "Staging'e kod değişikliği gönder",
        "Kod değişikliğini platformun STAGING dalına commit eder; staging deploy'u kendiliğinden başlar. Production'a "
        "dokunmaz. Dosyaların TAM yeni içeriği verilir (silmek için icerik null). Önce kod_oku ile güncel içeriği okuyun.",
        _sema({"platform": PLATFORM,
               "dosyalar": {"type": "array", "minItems": 1, "maxItems": 30, "description": "Değişen dosyalar.",
                            "items": _sema({"yol": _ozellik("string", "Depo kökünden göreli yol, ör. ornek_stok/models/stok.py."),
                                            "icerik": {"type": ["string", "null"], "description": "Dosyanın tam yeni içeriği; null silinir."}},
                                           ["yol", "icerik"])},
               "mesaj": _ozellik("string", "Commit mesajı, ör. [FIX] ornek_stok: negatif miktar uyarısı.")},
              ["platform", "dosyalar", "mesaj"]), "asistan", True),
}
# bu araçlar ek yetki de ister
EK_YETKI = {"staging_degisikligi_gonder": "deploy"}


def kullanilabilir(kullanici):
    """Kullanıcının rolüyle çağırabileceği araç adları."""
    rol = kullanici.get("rol")
    return [ad for ad, (_, _, _, yetki, _) in ARACLAR.items()
            if yetkili(rol, yetki) and (ad not in EK_YETKI or yetkili(rol, EK_YETKI[ad]))]


def anthropic_tanimlari(kullanici):
    return [{"name": ad, "description": ARACLAR[ad][1], "input_schema": ARACLAR[ad][2]} for ad in kullanilabilir(kullanici)]


def mcp_tanimlari(kullanici):
    sonuc = []
    for ad in kullanilabilir(kullanici):
        baslik, aciklama, sema, _, yazar = ARACLAR[ad]
        sonuc.append({"name": ad, "title": baslik, "description": aciklama, "inputSchema": sema,
                      "annotations": {"title": baslik, "readOnlyHint": not yazar, "destructiveHint": False,
                                      "openWorldHint": False}})
    return sonuc


# ---------------------------------------------------------------- çalıştırma

def _ajan(kullanici, yontem, yol, govde=None):
    kod, veri = _p().ajana_ilet(yontem, yol, govde, kullanici["ad"])
    if kod >= 400:
        raise AracHatasi(veri.get("hata") if isinstance(veri, dict) else f"Ajan hatası ({kod}).")
    return veri


def _platform(kullanici, girdi):
    platform = str(girdi.get("platform") or "")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,20}[a-z0-9]", platform) or not kapsamda(kullanici, platform):
        raise AracHatasi(f"Platform bulunamadı ya da erişiminiz yok: {platform or '(boş)'}. platformlari_listele ile bakın.")
    return platform


def _ortam(girdi):
    ortam = str(girdi.get("ortam") or "")
    if ortam not in ORTAMLAR:
        raise AracHatasi("ortam production ya da staging olmalı.")
    return ortam


def _q(deger):
    return quote(str(deger), safe="")


def calistir(kullanici, ad, girdi, kaynak="MCP", ip="-"):
    """Aracı çalıştırır; JSON'a çevrilebilir sonuç döner ya da AracHatasi yükseltir. Her çağrı denetim kaydına yazılır."""
    if ad not in ARACLAR:
        raise AracHatasi(f"Bilinmeyen araç: {ad}")
    if ad not in kullanilabilir(kullanici):
        raise AracHatasi("Rolünüz bu aracı kullanamaz.")
    girdi = girdi if isinstance(girdi, dict) else {}
    platform = None
    try:
        sonuc = _calistir(kullanici, ad, girdi)
        platform = girdi.get("platform")
        _p().islem_kaydet(kullanici["ad"], ip, f"{kaynak} {ad}", platform if isinstance(platform, str) else None, 200)
        return sonuc
    except AracHatasi as hata:
        _p().islem_kaydet(kullanici["ad"], ip, f"{kaynak} {ad}", girdi.get("platform") if isinstance(girdi.get("platform"), str)
                          else None, 400, hata=str(hata))
        raise


def _calistir(k, ad, g):  # noqa: C901 - araç başına kısa dallar
    if ad == "platformlari_listele":
        veri = _ajan(k, "GET", "odoolar")
        liste = []
        for o in veri.get("odoolar", []):
            if not kapsamda(k, o.get("id")):
                continue
            ortamlar = {}
            for ortam, b in (o.get("ortamlar") or {}).items():
                if b:
                    ortamlar[ortam] = {"durum": b.get("durum"), "adres": b.get("adres"), "commit": (b.get("commit") or "")[:12],
                                       "imaj": b.get("imaj"), "yonetim": b.get("yonetim")}
            liste.append({"id": o.get("id"), "firma": o.get("firma"), "tur": o.get("tur"), "seri": o.get("seri"),
                          "depo": (o.get("depo") or {}).get("ad"), "dallar": (o.get("depo") or {}).get("dallar"),
                          "ortamlar": ortamlar})
        return {"platformlar": liste, "tum_kapsam": kapsam_tum(k)}
    if ad == "is_durumu":
        is_no = str(g.get("is_no") or "")
        if not re.fullmatch(r"[0-9a-f]{12}", is_no):
            raise AracHatasi("Geçersiz iş numarası.")
        veri = _ajan(k, "GET", f"isler/{is_no}")
        if not kapsamda(k, veri.get("odoo") or ""):
            raise AracHatasi("İş bulunamadı.")
        return {a: veri.get(a) for a in ("id", "tur", "odoo", "ortam", "durum", "aciklama", "hata", "sonuc", "cikti",
                                          "baslangic", "bitis")}
    platform = _platform(k, g)
    if ad == "staging_degisikligi_gonder":
        return _ajan(k, "POST", f"odoolar/{platform}/staging/asistan-commit",
                     {"dosyalar": g.get("dosyalar"), "mesaj": g.get("mesaj")})
    ortam = _ortam(g)
    taban = f"odoolar/{platform}/{ortam}"
    if ad == "ortam_durumu":
        return _ajan(k, "GET", f"{taban}/durum")
    if ad == "izleme_ozeti":
        saat = g.get("saat") if g.get("saat") in (1, 24, 168) else 24
        veri = _ajan(k, "GET", f"{taban}/izleme?saat={saat}")
        ozet = {}
        for olcut, seri in (veri.pop("seriler", None) or {}).items():
            degerler = [n[1] for n in seri]
            if degerler:
                ozet[olcut] = {"en_az": min(degerler), "ortalama": round(sum(degerler) / len(degerler), 1),
                               "en_cok": max(degerler), "son": degerler[-1]}
        veri["olcut_ozeti"] = ozet
        veri.pop("gunler", None)
        return veri
    if ad == "loglar":
        satir = g.get("satir") if isinstance(g.get("satir"), int) else 300
        veri = _ajan(k, "GET", f"{taban}/loglar?satir={max(50, min(3000, satir))}")
        satirlar = veri.get("satirlar", [])
        if g.get("seviye") == "hata":
            satirlar = [s for s in satirlar if re.search(r" (ERROR|CRITICAL) ", s)]
        elif g.get("seviye") == "uyari":
            satirlar = [s for s in satirlar if re.search(r" (WARNING|ERROR|CRITICAL) ", s)]
        if g.get("ara"):
            ara = str(g["ara"]).lower()
            satirlar = [s for s in satirlar if ara in s.lower()]
        return {"konteyner": veri.get("konteyner"), "satir_sayisi": len(satirlar), "satirlar": satirlar}
    if ad == "moduller":
        veri = _ajan(k, "GET", f"{taban}/moduller")
        suzgec = g.get("suzgec") or "kurulu"
        secim = {"kurulu": lambda m: m.get("kurulu"), "ozel": lambda m: m.get("kaynak"),
                 "kurulu_degil": lambda m: not m.get("kurulu")}.get(suzgec, lambda m: True)
        ara = str(g.get("ara") or "").lower()
        liste = [{a: m.get(a) for a in ("ad", "baslik", "durum", "kurulu_surum", "surum", "kaynak", "yazar")}
                 for m in veri.get("moduller", []) if secim(m)
                 and (not ara or ara in (m.get("ad") or "").lower() or ara in (m.get("baslik") or "").lower())]
        return {"kurulu_sayisi": veri.get("kurulu_sayisi"), "gosterilen": len(liste[:400]), "kesik": len(liste) > 400,
                "moduller": liste[:400]}
    if ad == "deploy_gecmisi":
        veri = _ajan(k, "GET", f"{taban}/deploylar")
        return {"deploylar": [{a: d.get(a) for a in ("no", "commit", "baslik", "durum", "tetik", "kullanici", "baslangic",
                                                      "sure", "moduller", "hata")} for d in veri.get("deploylar", [])[:20]]}
    if ad == "deploy_ayrintisi":
        no = g.get("no")
        if not isinstance(no, int) or no < 1:
            raise AracHatasi("Geçersiz deploy numarası.")
        return _ajan(k, "GET", f"{taban}/deploylar/{no}")
    if ad == "yedekler":
        return _ajan(k, "GET", f"{taban}/yedekler")
    if ad == "kod_listele":
        return _ajan(k, "GET", f"{taban}/kod?yol={_q(g.get('yol') or '')}")
    if ad == "kod_oku":
        ek = "".join(f"&{a}={int(g[a])}" for a in ("bas", "son") if isinstance(g.get(a), int))
        return _ajan(k, "GET", f"{taban}/kod/oku?yol={_q(g.get('yol') or '')}{ek}")
    if ad == "kod_ara":
        return _ajan(k, "GET", f"{taban}/kod/ara?desen={_q(g.get('desen') or '')}&yol={_q(g.get('yol') or '')}")
    if ad == "sql_sorgu":
        return _ajan(k, "POST", f"{taban}/sql", {"sorgu": g.get("sorgu")})
    if ad == "yedek_al":
        return _ajan(k, "POST", f"{taban}/yedek")
    raise AracHatasi(f"Bilinmeyen araç: {ad}")


def metne(sonuc):
    """Araç sonucunu modele gidecek metne çevirir (çok uzunsa kısaltır)."""
    metin = json.dumps(sonuc, ensure_ascii=False, default=str)
    if len(metin) > SINIR_METIN:
        metin = metin[:SINIR_METIN] + f'... [çıktı {len(metin)} karakter, ilk {SINIR_METIN} karakter gösterildi; süzgeç kullanın]'
    return metin
