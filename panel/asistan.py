"""Panel içi asistan: her platform ortamı için sohbet; Claude API (resmî anthropic SDK) ve arac.py araçları.

Ayar (yalnız platform yöneticisi): VERI/asistan.json -> API anahtarı, model, effort. Anahtar tarayıcıya hiç gitmez.
Sohbetler bellekte tutulur (panel yeniden başlarsa sıfırlanır). Staging'e kod değişikliği panelde ONAY bekler:
model değişikliği önerir, kullanıcı "Commit at" derse panel gönderir.
"""
import importlib.util
import json
import os
import threading
import time

from . import arac

MODELLER = {"claude-opus-5-5": "Claude Opus 5.5", "claude-sonnet-5-5": "Claude Sonnet 5.5",
            "claude-haiku-5-5": "Claude Haiku 5.5"}
EFFORTLAR = ("low", "medium", "high", "xhigh", "max")
VARSAYILAN = {"model": "claude-opus-5-5", "effort": "high"}
EN_COK_ADIM = 25
KILIT = threading.Lock()
SOHBETLER = {}  # (kullanıcı, platform, ortam) -> sohbet

SISTEM = """Sen Odoo Yönetim Paneli'nin asistanısın. Kullanıcı bir Odoo platformunun tek bir ortamı (production ya da \
staging) üzerinde çalışıyor; platform ve ortam her mesajın başında belirtilir.

Araçlarla ortamın durumunu, loglarını, izleme ölçümlerini, modüllerini, deploy geçmişini, çalışan kodunu okuyabilir ve \
salt okunur veritabanı sorgusu çalıştırabilirsin. Kurallar:
- Önce veriye bak, sonra yanıtla. Tahmin ettiğin şeyi tahmin olarak söyle.
- Production'a yazan araç yoktur. Kod değişikliği yalnız staging_degisikligi_gonder ile önerilir; panel bunu kullanıcıya \
onaylatır, onaylanınca staging dalına commit atılır ve staging deploy'u başlar.
- Değişiklik önermeden önce ilgili dosyayı kod_oku ile oku; dosyanın TAM yeni içeriğini ver ve Odoo modül sürümünü \
(__manifest__.py version) artırmayı unutma.
- Veritabanında yalnız gereken sütunları seç; şifre, anahtar ve jeton sütunları zaten okunamaz.
- Yanıtı Türkçe, kısa ve somut yaz; dosya yollarını ve satır numaralarını ver."""


def _p():
    from . import panel
    return panel


# ---------------------------------------------------------------- ayar

def _ayar_dosyasi():
    return _p().VERI / "asistan.json"


def ayar_oku():
    yol = _ayar_dosyasi()
    veri = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    return {**VARSAYILAN, **veri}


def sdk_var():
    """Panel imajında resmî Claude SDK'sı var mı (yerel geliştirme sunucusu taklitle değiştirir)."""
    return importlib.util.find_spec("anthropic") is not None


def ayar_gorunumu():
    a = ayar_oku()
    anahtar = a.get("anahtar") or ""
    sdk = sdk_var()
    return {"anahtar_var": bool(anahtar), "anahtar_son": anahtar[-4:] if anahtar else "", "model": a["model"],
            "effort": a["effort"], "modeller": MODELLER, "effortlar": list(EFFORTLAR), "sdk": sdk}


def ayar_yaz(govde):
    a = ayar_oku()
    if "anahtar" in govde:
        anahtar = str(govde.get("anahtar") or "").strip()
        if anahtar and (not anahtar.startswith("sk-ant-") or len(anahtar) > 300):
            raise ValueError("Anthropic API anahtarı sk-ant- ile başlar.")
        a["anahtar"] = anahtar
    if govde.get("model"):
        if govde["model"] not in MODELLER:
            raise ValueError("Bilinmeyen model.")
        a["model"] = govde["model"]
    if govde.get("effort"):
        if govde["effort"] not in EFFORTLAR:
            raise ValueError("Geçersiz effort.")
        a["effort"] = govde["effort"]
    P = _p()
    P.VERI.mkdir(parents=True, exist_ok=True)
    gecici = _ayar_dosyasi().with_suffix(".tmp")
    gecici.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(gecici, 0o600)
    except OSError:
        pass
    gecici.replace(_ayar_dosyasi())
    return ayar_gorunumu()


# ---------------------------------------------------------------- sohbet

def _sohbet(kullanici_adi, platform, ortam):
    with KILIT:
        return SOHBETLER.setdefault((kullanici_adi, platform, ortam), {
            "mesajlar": [], "akis": [], "mesgul": False, "oneri": None, "not": None, "kullanim": {"girdi": 0, "cikti": 0}})


def gorunum(kullanici_adi, platform, ortam):
    s = _sohbet(kullanici_adi, platform, ortam)
    return {"akis": s["akis"], "mesgul": s["mesgul"], "oneri": s["oneri"], "kullanim": s["kullanim"],
            "ayar": {k: v for k, v in ayar_gorunumu().items() if k in ("anahtar_var", "model", "effort", "sdk")}}


def sifirla(kullanici_adi, platform, ortam):
    with KILIT:
        s = SOHBETLER.get((kullanici_adi, platform, ortam))
        if s and s["mesgul"]:
            raise ValueError("Asistan çalışırken yeni oturum açılamaz.")
        SOHBETLER.pop((kullanici_adi, platform, ortam), None)
    return gorunum(kullanici_adi, platform, ortam)


def istemci_olustur(anahtar):
    """anthropic istemcisi (testlerde sahtesiyle değiştirilir)."""
    import anthropic
    return anthropic.Anthropic(api_key=anahtar, max_retries=2, timeout=600)


def gonder(kullanici, platform, ortam, metin, ip="-"):
    ayar = ayar_oku()
    if not ayar.get("anahtar"):
        raise ValueError("Asistan için API anahtarı girilmemiş (Ajan bağlantıları > Panel asistanı, platform yöneticisi).")
    metin = str(metin or "").strip()
    if not metin or len(metin) > 8000:
        raise ValueError("Mesaj boş ya da çok uzun (en çok 8000 karakter).")
    s = _sohbet(kullanici["ad"], platform, ortam)
    with KILIT:
        if s["mesgul"]:
            raise ValueError("Asistan önceki mesajı yanıtlıyor; bitmesini bekleyin.")
        s["mesgul"] = True
    s["akis"].append({"tur": "ben", "metin": metin, "zaman": time.time()})
    on = f"[Platform: {platform}, ortam: {ortam}]"
    if s["not"]:
        on += f"\n[Panel notu: {s['not']}]"
        s["not"] = None
    s["mesajlar"].append({"role": "user", "content": f"{on}\n\n{metin}"})
    _p().islem_kaydet(kullanici["ad"], ip, "ASISTAN MESAJ", platform)
    threading.Thread(target=_dongu, args=(kullanici, platform, ortam, s, ayar, ip), daemon=True).start()
    return gorunum(kullanici["ad"], platform, ortam)


def _adim_metni(ad, girdi):
    ozet = {k: v for k, v in girdi.items() if k not in ("platform", "ortam", "dosyalar")}
    if ad == "staging_degisikligi_gonder":
        ozet = {"dosyalar": [d.get("yol") for d in girdi.get("dosyalar") or [] if isinstance(d, dict)]}
    baslik = arac.ARACLAR.get(ad, (ad,))[0]
    return f"{baslik}" + (f": {json.dumps(ozet, ensure_ascii=False)[:200]}" if ozet else "")


def _dongu(kullanici, platform, ortam, s, ayar, ip):  # noqa: C901 - tek yerde okunan araç döngüsü
    try:
        istemci = istemci_olustur(ayar["anahtar"])
        araclar = arac.anthropic_tanimlari(kullanici)
        for _ in range(EN_COK_ADIM):
            yanit = istemci.beta.messages.create(
                model=ayar["model"], max_tokens=16000, system=SISTEM, tools=araclar, messages=s["mesajlar"],
                thinking={"type": "adaptive"}, output_config={"effort": ayar["effort"]},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            kullanim = getattr(yanit, "usage", None)
            if kullanim:
                s["kullanim"]["girdi"] += (getattr(kullanim, "input_tokens", 0) or 0) + \
                    (getattr(kullanim, "cache_read_input_tokens", 0) or 0) + (getattr(kullanim, "cache_creation_input_tokens", 0) or 0)
                s["kullanim"]["cikti"] += getattr(kullanim, "output_tokens", 0) or 0
            s["mesajlar"].append({"role": "assistant", "content": yanit.content})
            for blok in yanit.content:
                if getattr(blok, "type", "") == "text" and blok.text.strip():
                    s["akis"].append({"tur": "cevap", "metin": blok.text, "zaman": time.time()})
            if yanit.stop_reason == "refusal":
                s["akis"].append({"tur": "hata", "metin": "Asistan bu isteği güvenlik nedeniyle yanıtlamadı. "
                                  "İsteği farklı ve daha somut yazmayı deneyin.", "zaman": time.time()})
                return
            if yanit.stop_reason == "pause_turn":
                continue
            if yanit.stop_reason == "max_tokens":
                s["akis"].append({"tur": "hata", "metin": "Yanıt uzunluk sınırına takıldı; soruyu daraltın.",
                                  "zaman": time.time()})
                return
            if yanit.stop_reason != "tool_use":
                return
            sonuclar = []
            for blok in [b for b in yanit.content if getattr(b, "type", "") == "tool_use"]:
                girdi = blok.input if isinstance(blok.input, dict) else {}
                s["akis"].append({"tur": "adim", "metin": _adim_metni(blok.name, girdi), "zaman": time.time()})
                if blok.name == "staging_degisikligi_gonder":
                    s["oneri"] = {"platform": girdi.get("platform") or platform, "mesaj": str(girdi.get("mesaj") or "")[:500],
                                  "dosyalar": [{"yol": str(d.get("yol")), "icerik": d.get("icerik")}
                                               for d in (girdi.get("dosyalar") or [])[:30] if isinstance(d, dict)]}
                    sonuclar.append({"type": "tool_result", "tool_use_id": blok.id,
                                     "content": "Değişiklik kullanıcının onayına sunuldu. Onaylanırsa panel staging dalına "
                                                "commit atar ve staging deploy'u başlar. Kullanıcıya neyi değiştirdiğini "
                                                "kısaca anlat."})
                    continue
                try:
                    sonuc = arac.calistir(kullanici, blok.name, girdi, kaynak="ASISTAN", ip=ip)
                    sonuclar.append({"type": "tool_result", "tool_use_id": blok.id, "content": arac.metne(sonuc)})
                except arac.AracHatasi as hata:
                    sonuclar.append({"type": "tool_result", "tool_use_id": blok.id, "content": str(hata), "is_error": True})
            s["mesajlar"].append({"role": "user", "content": sonuclar})
        s["akis"].append({"tur": "hata", "metin": f"Asistan {EN_COK_ADIM} adımda bitiremedi; soruyu daraltıp tekrar deneyin.",
                          "zaman": time.time()})
    except Exception as hata:  # noqa: BLE001 - kullanıcıya açık hata olarak gösterilir
        s["akis"].append({"tur": "hata", "metin": _api_hatasi(hata), "zaman": time.time()})
        # yarım kalan tur geçmişi bozmasın: son kullanıcı mesajına kadar geri al
        while s["mesajlar"] and not (s["mesajlar"][-1]["role"] == "user" and isinstance(s["mesajlar"][-1]["content"], str)):
            s["mesajlar"].pop()
        if s["mesajlar"]:
            s["mesajlar"].pop()
    finally:
        s["mesgul"] = False


def _api_hatasi(hata):
    try:
        import anthropic
    except ImportError:
        return "Sunucuda anthropic paketi yok; panel imajı yeniden oluşturulmalı."
    if isinstance(hata, anthropic.AuthenticationError):
        return "API anahtarı geçersiz. Platform yöneticisi Ajan bağlantıları ekranından yeni anahtar girmeli."
    if isinstance(hata, anthropic.PermissionDeniedError):
        return "API anahtarının bu modele yetkisi yok."
    if isinstance(hata, anthropic.NotFoundError):
        return "Model bulunamadı; Ajan bağlantıları ekranında başka bir model seçin."
    if isinstance(hata, anthropic.RateLimitError):
        return "Claude API kullanım sınırına takıldı; biraz sonra tekrar deneyin."
    if isinstance(hata, anthropic.BadRequestError):
        return f"Claude API isteği reddetti: {getattr(hata, 'message', hata)}"
    if isinstance(hata, anthropic.APIStatusError):
        return f"Claude API hata verdi ({hata.status_code}); biraz sonra tekrar deneyin."
    if isinstance(hata, anthropic.APIConnectionError):
        return "Claude API'ye ulaşılamadı (sunucunun dış bağlantısı)."
    return f"Asistan hatası: {type(hata).__name__}: {hata}"


def oneri_karar(kullanici, platform, ortam, evet, ip="-"):
    """Önerilen staging değişikliği: evet -> commit (iş kaydı döner), hayır -> atılır."""
    s = _sohbet(kullanici["ad"], platform, ortam)
    oneri = s["oneri"]
    if not oneri:
        raise ValueError("Bekleyen değişiklik yok.")
    s["oneri"] = None
    if not evet:
        s["not"] = "Kullanıcı önerilen staging değişikliğini reddetti."
        s["akis"].append({"tur": "adim", "metin": "Değişiklik reddedildi.", "zaman": time.time()})
        return {"durum": "reddedildi"}
    try:
        sonuc = arac.calistir(kullanici, "staging_degisikligi_gonder",
                              {"platform": oneri["platform"], "dosyalar": oneri["dosyalar"], "mesaj": oneri["mesaj"]},
                              kaynak="ASISTAN", ip=ip)
    except arac.AracHatasi as hata:
        s["oneri"] = oneri
        raise ValueError(str(hata)) from None
    s["not"] = f"Kullanıcı değişikliği onayladı; staging'e commit işi başladı (iş {sonuc.get('id')})."
    s["akis"].append({"tur": "adim", "metin": f"Onaylandı: staging dalına commit işi başladı ({sonuc.get('id')}).",
                      "zaman": time.time()})
    return sonuc
