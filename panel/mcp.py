"""Bağlı ajanlar: MCP sunucusu (/mcp), OAuth 2.1 girişi ve kişisel erişim jetonları.

  - Claude Desktop / claude.ai: "özel bağlayıcı" olarak https://panel.vekosis.com/mcp eklenir; giriş panelin kendi
    onay ekranından yapılır (OAuth 2.1, PKCE S256, dinamik istemci kaydı).
  - Codex (ve jeton kabul eden diğer istemciler): Platform > Ajan bağlantıları ekranında üretilen kişisel jetonla
    (Authorization: Bearer ...).
Ajan, jetonun sahibi kullanıcının GÜNCEL rolü ve kapsamıyla çalışır (arac.py). Jetonlar diskte yalnız SHA-256 özeti
olarak tutulur; kullanıcı silinirse ya da jeton kaldırılırsa erişim hemen biter.
"""
import base64
import hashlib
import json
import re
import secrets
import threading
import time
from html import escape
from urllib.parse import parse_qs, urlencode, urlsplit

from . import arac

MCP_SURUMLERI = ("2025-11-25", "2025-06-18", "2025-03-26")
ERISIM_SURESI = 3600
YENILEME_SURESI = 30 * 86400
KOD_SURESI = 600
# OAuth yönlendirme adresleri: claude.ai / claude.com bağlayıcıları ve yerel istemciler (Claude Code, Codex)
IZINLI_YONLENDIRME = re.compile(r"^(https://(claude\.ai|claude\.com)/api/mcp/auth_callback|"
                                r"http://(localhost|127\.0\.0\.1)(:\d{1,5})?/[A-Za-z0-9/_.-]*)$")
FORM_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self' https://claude.ai https://claude.com http://localhost:* http://127.0.0.1:*")
KILIT = threading.Lock()
KODLAR = {}  # yetkilendirme kodu -> bilgi (bellekte, 10 dakika)


def _p():
    from . import panel
    return panel


def _ozet(jeton):
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- kayıt dosyası

def _dosya():
    return _p().VERI / "ajan_baglantilari.json"


def _oku():
    yol = _dosya()
    veri = json.loads(yol.read_text(encoding="utf-8")) if yol.exists() else {}
    veri.setdefault("istemciler", {})
    veri.setdefault("jetonlar", {})
    return veri


def _yaz(veri):
    P = _p()
    P.VERI.mkdir(parents=True, exist_ok=True)
    gecici = _dosya().with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        import os
        os.chmod(gecici, 0o600)
    except OSError:
        pass
    gecici.replace(_dosya())


def _temizle(veri):
    simdi = time.time()
    veri["jetonlar"] = {o: j for o, j in veri["jetonlar"].items() if not j.get("bitis") or j["bitis"] > simdi}
    return veri


def jeton_uret(kullanici, tur, ad="", istemci=None, sure=None, aile=None):
    """Yeni jeton üretir, özetini kaydeder; jetonun kendisini döner (bir kez görünür)."""
    onek = {"kisisel": "pnl_pat_", "erisim": "pnl_oat_", "yenileme": "pnl_ort_"}[tur]
    jeton = onek + secrets.token_urlsafe(32)
    with KILIT:
        veri = _temizle(_oku())
        veri["jetonlar"][_ozet(jeton)] = {
            "tur": tur, "kullanici": kullanici, "ad": ad[:60], "istemci": istemci, "aile": aile or secrets.token_hex(8),
            "olusturma": time.time(), "bitis": time.time() + sure if sure else None, "son_kullanim": None}
        _yaz(veri)
    return jeton


def jeton_dogrula(jeton, tur=("kisisel", "erisim")):
    """Geçerli jetonun kaydı (kullanıcı bilgisiyle) ya da None."""
    if not jeton or not jeton.startswith("pnl_"):
        return None
    ozet = _ozet(jeton)
    with KILIT:
        veri = _oku()
        j = veri["jetonlar"].get(ozet)
        if not j or j["tur"] not in tur or (j.get("bitis") and j["bitis"] < time.time()):
            return None
        if not j.get("son_kullanim") or time.time() - j["son_kullanim"] > 60:
            j["son_kullanim"] = time.time()
            _yaz(veri)
    kayit = _p().kullanicilari_oku().get(j["kullanici"])
    if not kayit:
        return None
    return {"ozet": ozet, "jeton": j, "kullanici": {"ad": j["kullanici"], **kayit}}


def baglantilar(kullanici_adi):
    """Kullanıcının kişisel jetonları ve OAuth ile bağlanan istemcileri (arayüz için; jetonun kendisi yok)."""
    with KILIT:
        veri = _temizle(_oku())
    sonuc = []
    aileler = {}
    for ozet, j in veri["jetonlar"].items():
        if j["kullanici"] != kullanici_adi:
            continue
        if j["tur"] == "kisisel":
            sonuc.append({"id": ozet[:12], "tur": "kisisel", "ad": j["ad"], "olusturma": j["olusturma"],
                          "bitis": j.get("bitis"), "son_kullanim": j.get("son_kullanim")})
        else:
            a = aileler.setdefault(j["aile"], {"id": "a" + j["aile"][:11], "tur": "oauth", "ad": "", "olusturma": j["olusturma"],
                                               "bitis": None, "son_kullanim": None})
            istemci = veri["istemciler"].get(j.get("istemci") or "", {})
            a["ad"] = istemci.get("ad") or "OAuth istemcisi"
            a["olusturma"] = min(a["olusturma"], j["olusturma"])
            a["son_kullanim"] = max(filter(None, [a["son_kullanim"], j.get("son_kullanim")]), default=None)
    return sorted(sonuc + list(aileler.values()), key=lambda x: -x["olusturma"])


def baglanti_kaldir(kullanici_adi, kimlik):
    with KILIT:
        veri = _oku()
        silinecek = [o for o, j in veri["jetonlar"].items() if j["kullanici"] == kullanici_adi and
                     (o[:12] == kimlik or ("a" + j.get("aile", "")[:11]) == kimlik)]
        for o in silinecek:
            veri["jetonlar"].pop(o)
        _yaz(veri)
    return len(silinecek)


def kullanici_jetonlarini_sil(kullanici_adi):
    with KILIT:
        veri = _oku()
        veri["jetonlar"] = {o: j for o, j in veri["jetonlar"].items() if j["kullanici"] != kullanici_adi}
        _yaz(veri)


# ---------------------------------------------------------------- HTTP yardımcıları

def taban_adres(istek):
    host = istek.headers.get("X-Forwarded-Host") or istek.headers.get("Host") or "panel.vekosis.com"
    sema = istek.headers.get("X-Forwarded-Proto") or ("http" if re.match(r"^(localhost|127\.0\.0\.1)(:\d+)?$", host) else "https")
    return f"{sema}://{host}"


def _json(istek, kod, veri, basliklar=None):
    govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
    istek.send_response(kod)
    istek.send_header("Content-Type", "application/json; charset=utf-8")
    istek.send_header("Content-Length", str(len(govde)))
    istek.send_header("Cache-Control", "no-store")
    istek.send_header("X-Content-Type-Options", "nosniff")
    for ad, deger in (basliklar or {}).items():
        istek.send_header(ad, deger)
    istek.end_headers()
    istek.wfile.write(govde)


def _bos(istek, kod, basliklar=None):
    istek.send_response(kod)
    istek.send_header("Content-Length", "0")
    for ad, deger in (basliklar or {}).items():
        istek.send_header(ad, deger)
    istek.end_headers()


# ---------------------------------------------------------------- keşif belgeleri

def korunan_kaynak(istek):
    taban = taban_adres(istek)
    _json(istek, 200, {"resource": f"{taban}/mcp", "authorization_servers": [taban], "scopes_supported": ["mcp"],
                       "bearer_methods_supported": ["header"], "resource_name": "Odoo Yönetim Paneli"})


def yetki_sunucusu(istek):
    taban = taban_adres(istek)
    _json(istek, 200, {
        "issuer": taban, "authorization_endpoint": f"{taban}/oauth/authorize", "token_endpoint": f"{taban}/oauth/token",
        "registration_endpoint": f"{taban}/oauth/register", "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": ["mcp"]})


# ---------------------------------------------------------------- OAuth

def kayit_ol(istek):
    """Dinamik istemci kaydı (RFC 7591). Yalnız bilinen yönlendirme adreslerine izin verilir."""
    try:
        govde = json.loads(istek.rfile.read(min(int(istek.headers.get("Content-Length") or 0), 16384)) or b"{}")
    except ValueError:
        return _json(istek, 400, {"error": "invalid_client_metadata", "error_description": "Geçersiz JSON."})
    adresler = govde.get("redirect_uris") if isinstance(govde, dict) else None
    if not isinstance(adresler, list) or not adresler or len(adresler) > 5 or \
            not all(isinstance(a, str) and IZINLI_YONLENDIRME.match(a) for a in adresler):
        return _json(istek, 400, {"error": "invalid_redirect_uri",
                                  "error_description": "Yalnız claude.ai / claude.com bağlayıcıları ve yerel istemciler kaydolabilir."})
    istemci_id = "pnl_c_" + secrets.token_urlsafe(16)
    ad = re.sub(r"[\x00-\x1f<>]", "", str(govde.get("client_name") or "Ajan"))[:60]
    with KILIT:
        veri = _oku()
        if len(veri["istemciler"]) >= 300:  # en eskiler silinir
            for eski in sorted(veri["istemciler"], key=lambda x: veri["istemciler"][x]["olusturma"])[:50]:
                veri["istemciler"].pop(eski)
        veri["istemciler"][istemci_id] = {"ad": ad, "adresler": adresler, "olusturma": time.time()}
        _yaz(veri)
    _json(istek, 201, {"client_id": istemci_id, "client_id_issued_at": int(time.time()), "client_name": ad,
                       "redirect_uris": adresler, "grant_types": ["authorization_code", "refresh_token"],
                       "response_types": ["code"], "token_endpoint_auth_method": "none"})


def _istemci(istemci_id):
    with KILIT:
        return _oku()["istemciler"].get(istemci_id or "")


def _form_sayfasi(istek, baslik, govde, kod=200):
    sayfa = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(baslik)} · Odoo Yönetim Paneli</title><style>
body{{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f3f5f7;color:#1f2933;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px}}
.kart{{background:#fff;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.08);padding:28px;max-width:440px;width:100%}}
h1{{font-size:1.25rem;margin:0 0 .4rem}}p{{color:#52606d;line-height:1.5}}ul{{color:#52606d;padding-left:1.1rem;line-height:1.6}}
label{{display:block;font-size:.88rem;margin:.8rem 0 .3rem}}input{{width:100%;box-sizing:border-box;padding:.6rem .7rem;border:1px solid #cbd2d9;border-radius:8px;font:inherit}}
.dugmeler{{display:flex;gap:.5rem;margin-top:1.2rem}}button{{flex:1;padding:.65rem;border-radius:8px;border:1px solid #cbd2d9;background:#fff;font:inherit;cursor:pointer}}
button.birincil{{background:#017e84;border-color:#017e84;color:#fff;font-weight:600}}.hata{{background:#fde8e6;color:#b42318;padding:.6rem .8rem;border-radius:8px}}
code{{background:#eef2f5;padding:.1rem .3rem;border-radius:4px}}</style></head><body><div class="kart">{govde}</div></body></html>"""
    veri = sayfa.encode("utf-8")
    istek.send_response(kod)
    istek.send_header("Content-Type", "text/html; charset=utf-8")
    istek.send_header("Content-Length", str(len(veri)))
    istek.send_header("Content-Security-Policy", FORM_CSP)
    istek.send_header("X-Frame-Options", "DENY")
    istek.send_header("Cache-Control", "no-store")
    istek.send_header("Referrer-Policy", "no-referrer")
    istek.end_headers()
    istek.wfile.write(veri)


def _yetki_parametreleri(sorgu):
    p = {k: (v[0] if v else "") for k, v in sorgu.items()}
    istemci = _istemci(p.get("client_id"))
    if not istemci:
        return None, "Bilinmeyen istemci. Bağlantıyı istemciden yeniden başlatın."
    if p.get("redirect_uri") not in istemci["adresler"]:
        return None, "Yönlendirme adresi bu istemcinin kaydıyla eşleşmiyor."
    if p.get("response_type") != "code" or p.get("code_challenge_method") != "S256" or \
            not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", p.get("code_challenge") or ""):
        return None, "Geçersiz yetkilendirme isteği (PKCE S256 gerekli)."
    return {**p, "istemci_adi": istemci["ad"]}, None


def yetkilendir_goster(istek):
    p, hata = _yetki_parametreleri(parse_qs(urlsplit(istek.path).query))
    if hata:
        return _form_sayfasi(istek, "Bağlantı kurulamadı", f'<h1>Bağlantı kurulamadı</h1><p class="hata">{escape(hata)}</p>', 400)
    _anahtar, oturum = istek._oturum()
    gizli = "".join(f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">' for k, v in p.items()
                    if k in ("client_id", "redirect_uri", "code_challenge", "code_challenge_method", "state", "scope",
                             "resource", "response_type"))
    giris = "" if oturum else """<label for="k">Kullanıcı adı</label><input id="k" name="kullanici" autocomplete="username" required>
        <label for="s">Şifre</label><input id="s" name="sifre" type="password" autocomplete="current-password" required>"""
    kim = f"<p>Oturum: <strong>{escape(oturum['kullanici'])}</strong></p>" if oturum else ""
    govde = f"""<h1>Ajan bağlantısı</h1>
    <p><strong>{escape(p['istemci_adi'])}</strong> Odoo Yönetim Paneli'ne sizin adınıza bağlanmak istiyor.</p>
    <ul><li>Erişebildiğiniz platformları, loglarını, izlemesini ve kodunu okuyabilir.</li>
    <li>Rolünüz izin veriyorsa salt okunur veritabanı sorgusu çalıştırabilir, yedek alabilir ve <strong>yalnız staging</strong> dalına kod gönderebilir.</li>
    <li>Production'a yazamaz. Bağlantıyı panelde <em>Ajan bağlantıları</em> ekranından kaldırabilirsiniz.</li></ul>
    {kim}<form method="post" action="/oauth/authorize">{gizli}{giris}
    <div class="dugmeler"><button type="submit" name="karar" value="hayir">Reddet</button>
    <button class="birincil" type="submit" name="karar" value="evet">İzin ver</button></div></form>"""
    _form_sayfasi(istek, "Ajan bağlantısı", govde)


def yetkilendir_onay(istek):
    P = _p()
    uzunluk = min(int(istek.headers.get("Content-Length") or 0), 16384)
    form = parse_qs(istek.rfile.read(uzunluk).decode("utf-8", "replace"))
    p, hata = _yetki_parametreleri(form)
    if hata:
        return _form_sayfasi(istek, "Bağlantı kurulamadı", f'<h1>Bağlantı kurulamadı</h1><p class="hata">{escape(hata)}</p>', 400)
    yonlendir = p["redirect_uri"]
    ek = {"state": p["state"]} if p.get("state") else {}
    ayrac = "&" if "?" in yonlendir else "?"
    if (form.get("karar") or [""])[0] != "evet":
        return _bos(istek, 302, {"Location": f"{yonlendir}{ayrac}{urlencode({'error': 'access_denied', **ek})}"})
    _anahtar, oturum = istek._oturum()
    if oturum:
        kullanici = oturum["kullanici"]
    else:
        kullanici = P.sifre_ile_dogrula(istek, (form.get("kullanici") or [""])[0], (form.get("sifre") or [""])[0])
        if not kullanici:
            return _form_sayfasi(istek, "Giriş başarısız", '<h1>Giriş başarısız</h1><p class="hata">Kullanıcı adı ya da şifre '
                                 'yanlış (ya da çok fazla deneme). Geri dönüp tekrar deneyin.</p>', 401)
    kod = secrets.token_urlsafe(32)
    with KILIT:
        for k in [k for k, v in KODLAR.items() if v["bitis"] < time.time()]:
            KODLAR.pop(k)
        KODLAR[kod] = {"istemci": p["client_id"], "adres": yonlendir, "challenge": p["code_challenge"],
                       "kullanici": kullanici, "bitis": time.time() + KOD_SURESI}
    P.islem_kaydet(kullanici, istek._ip(), f"JETON OAUTH {p['istemci_adi']}")
    _bos(istek, 302, {"Location": f"{yonlendir}{ayrac}{urlencode({'code': kod, **ek})}"})


def jeton_ver(istek):
    uzunluk = min(int(istek.headers.get("Content-Length") or 0), 16384)
    ham = istek.rfile.read(uzunluk).decode("utf-8", "replace")
    form = {k: v[0] for k, v in parse_qs(ham).items()} if "json" not in (istek.headers.get("Content-Type") or "") \
        else (json.loads(ham or "{}") if ham.strip().startswith("{") else {})
    tur = form.get("grant_type")
    hata = lambda kod, aciklama: _json(istek, 400, {"error": kod, "error_description": aciklama})  # noqa: E731
    if tur == "authorization_code":
        with KILIT:
            bilgi = KODLAR.pop(form.get("code") or "", None)
        if not bilgi or bilgi["bitis"] < time.time():
            return hata("invalid_grant", "Kod geçersiz ya da süresi dolmuş.")
        if bilgi["istemci"] != form.get("client_id") or bilgi["adres"] != form.get("redirect_uri"):
            return hata("invalid_grant", "İstemci ya da yönlendirme adresi eşleşmiyor.")
        dogrulayici = form.get("code_verifier") or ""
        beklenen = base64.urlsafe_b64encode(hashlib.sha256(dogrulayici.encode()).digest()).rstrip(b"=").decode()
        if not secrets.compare_digest(beklenen, bilgi["challenge"]):
            return hata("invalid_grant", "PKCE doğrulaması başarısız.")
        kullanici, istemci, aile = bilgi["kullanici"], bilgi["istemci"], None
    elif tur == "refresh_token":
        eski = jeton_dogrula(form.get("refresh_token") or "", tur=("yenileme",))
        if not eski or eski["jeton"].get("istemci") != form.get("client_id"):
            return hata("invalid_grant", "Yenileme jetonu geçersiz.")
        with KILIT:  # yenileme jetonu tek kullanımlık
            veri = _oku()
            veri["jetonlar"].pop(eski["ozet"], None)
            _yaz(veri)
        kullanici, istemci, aile = eski["kullanici"]["ad"], eski["jeton"]["istemci"], eski["jeton"]["aile"]
    else:
        return hata("unsupported_grant_type", "Yalnız authorization_code ve refresh_token.")
    aile = aile or secrets.token_hex(8)
    erisim = jeton_uret(kullanici, "erisim", istemci=istemci, sure=ERISIM_SURESI, aile=aile)
    yenileme = jeton_uret(kullanici, "yenileme", istemci=istemci, sure=YENILEME_SURESI, aile=aile)
    _json(istek, 200, {"access_token": erisim, "token_type": "Bearer", "expires_in": ERISIM_SURESI,
                       "refresh_token": yenileme, "scope": "mcp"}, {"Pragma": "no-cache"})


# ---------------------------------------------------------------- MCP

def _yetkisiz(istek, aciklama="Erişim jetonu gerekli."):
    taban = taban_adres(istek)
    _json(istek, 401, {"error": "invalid_token", "error_description": aciklama},
          {"WWW-Authenticate": f'Bearer resource_metadata="{taban}/.well-known/oauth-protected-resource", '
                              'error="invalid_token", error_description="token missing, invalid or expired"'})


def _cevap(kimlik, sonuc=None, hata=None):
    veri = {"jsonrpc": "2.0", "id": kimlik}
    if hata:
        veri["error"] = hata
    else:
        veri["result"] = sonuc
    return veri


def mcp(istek):
    """POST /mcp: JSON-RPC 2.0 (Streamable HTTP, tek mesaj, application/json yanıt)."""
    koken = istek.headers.get("Origin")
    if koken and koken.rstrip("/") != taban_adres(istek):  # tarayıcıdan başka siteden gelen istek (DNS rebinding)
        return _json(istek, 403, {"error": "Bu kökenden istek kabul edilmiyor."})
    baslik = istek.headers.get("Authorization", "")
    dogrulanan = jeton_dogrula(baslik[7:].strip() if baslik.lower().startswith("bearer ") else "")
    if not dogrulanan:
        return _yetkisiz(istek, "Erişim jetonu geçersiz ya da süresi dolmuş.")
    kullanici = dogrulanan["kullanici"]
    try:
        uzunluk = int(istek.headers.get("Content-Length") or 0)
        if uzunluk > 2 * 1024 * 1024:
            return _json(istek, 413, _cevap(None, hata={"code": -32600, "message": "İstek çok büyük."}))
        mesaj = json.loads(istek.rfile.read(uzunluk) or b"null")
    except ValueError:
        return _json(istek, 400, _cevap(None, hata={"code": -32700, "message": "JSON çözümlenemedi."}))
    if not isinstance(mesaj, dict) or mesaj.get("jsonrpc") != "2.0" or not isinstance(mesaj.get("method"), str):
        return _json(istek, 400, _cevap(None, hata={"code": -32600, "message": "Geçersiz JSON-RPC isteği."}))
    yontem, kimlik, params = mesaj["method"], mesaj.get("id"), mesaj.get("params") or {}
    if "id" not in mesaj:  # bildirim (ör. notifications/initialized)
        return _bos(istek, 202)
    if yontem == "initialize":
        istenen = params.get("protocolVersion")
        sonuc = {"protocolVersion": istenen if istenen in MCP_SURUMLERI else MCP_SURUMLERI[0],
                 "capabilities": {"tools": {"listChanged": False}},
                 "serverInfo": {"name": "odoo-yonetim-paneli", "title": "Odoo Yönetim Paneli", "version": "0.2.0"},
                 "instructions": "Odoo Yönetim Paneli: platformlar (Odoo kurulumları), ortamları (production/staging), "
                                 "loglar, izleme, kod ve salt okunur veritabanı. Önce platformlari_listele. Production'a "
                                 "yazan araç yoktur; kod değişikliği yalnız staging dalına gider."}
        return _json(istek, 200, _cevap(kimlik, sonuc))
    if yontem == "ping":
        return _json(istek, 200, _cevap(kimlik, {}))
    if yontem == "tools/list":
        return _json(istek, 200, _cevap(kimlik, {"tools": arac.mcp_tanimlari(kullanici)}))
    if yontem == "tools/call":
        ad, girdi = params.get("name"), params.get("arguments") or {}
        try:
            sonuc = arac.calistir(kullanici, ad, girdi, kaynak="MCP", ip=istek._ip())
            return _json(istek, 200, _cevap(kimlik, {"content": [{"type": "text", "text": arac.metne(sonuc)}],
                                                     "isError": False}))
        except arac.AracHatasi as hata:
            return _json(istek, 200, _cevap(kimlik, {"content": [{"type": "text", "text": str(hata)}], "isError": True}))
    if yontem in ("resources/list", "prompts/list"):
        return _json(istek, 200, _cevap(kimlik, {yontem.split("/")[0]: []}))
    return _json(istek, 200, _cevap(kimlik, hata={"code": -32601, "message": f"Desteklenmeyen yöntem: {yontem}"}))
