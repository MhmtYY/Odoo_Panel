"""Bağlı ajanlar: MCP sunucusu, OAuth 2.1 (PKCE), kişisel jetonlar ve panel içi asistan (sahte Claude istemcisiyle)."""
import base64
import hashlib
import json
import time
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

from panel import asistan
from panel import panel as P

from . import test_panel as tp

CLAUDE_DONUS = "https://claude.ai/api/mcp/auth_callback"


class YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class McpTesti(unittest.TestCase):
    setUp = tp.PanelTesti.setUp
    tearDown = tp.PanelTesti.tearDown
    istek = tp.PanelTesti.istek
    giris = tp.PanelTesti.giris

    # -- yardımcılar
    def mcp(self, jeton, yontem, params=None, kimlik=1):
        govde = {"jsonrpc": "2.0", "method": yontem, **({"id": kimlik} if kimlik is not None else {}),
                 **({"params": params} if params is not None else {})}
        b = {"Authorization": f"Bearer {jeton}"} if jeton else {}
        return self.istek("POST", "/mcp", govde, basliklar=b)

    def jeton(self, ad, sifre):
        o = self.giris(ad, sifre)
        kod, veri, _ = self.istek("POST", "/api/baglantilar", {"ad": "Codex dizüstü"}, oturum=o)
        self.assertEqual(kod, 200, veri)
        self.assertTrue(veri["jeton"].startswith("pnl_pat_"))
        return veri["jeton"], o

    def ham(self, yontem, yol, veri=None, basliklar=None):
        istek = urllib.request.Request(self.adres + yol, data=veri, method=yontem, headers=basliklar or {})
        acici = urllib.request.build_opener(YonlendirmeYok)
        try:
            with acici.open(istek, timeout=30) as y:
                return y.status, y.read().decode(), y.headers
        except urllib.error.HTTPError as h:
            return h.code, h.read().decode(), h.headers

    # -- testler
    def test_jetonsuz_istek_kesif_belgesini_gosterir(self):
        kod, veri, basliklar = self.mcp(None, "initialize")
        self.assertEqual(kod, 401)
        self.assertIn('resource_metadata="http://127.0.0.1:', basliklar["WWW-Authenticate"])
        kod, kaynak, _ = self.istek("GET", "/.well-known/oauth-protected-resource")
        self.assertEqual(kaynak["resource"], self.adres + "/mcp")
        kod, sunucu, _ = self.istek("GET", "/.well-known/oauth-authorization-server")
        self.assertEqual((sunucu["code_challenge_methods_supported"], sunucu["registration_endpoint"]),
                         (["S256"], self.adres + "/oauth/register"))
        self.assertEqual(self.mcp("pnl_pat_uydurma", "ping")[0], 401)

    def test_kisisel_jeton_ve_araclar(self):
        jeton, o = self.jeton("ayse", "ayse-sifresi1")
        kod, veri, _ = self.mcp(jeton, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                       "clientInfo": {"name": "codex", "version": "1"}})
        self.assertEqual((kod, veri["result"]["protocolVersion"]), (200, "2025-06-18"))
        self.assertEqual(self.mcp(jeton, "notifications/initialized", kimlik=None)[0], 202)
        adlar = [a["name"] for a in self.mcp(jeton, "tools/list")[1]["result"]["tools"]]
        self.assertIn("sql_sorgu", adlar)
        self.assertIn("staging_degisikligi_gonder", adlar)
        # kapsam: ayşe yalnız "deneme"yi görür
        sonuc = self.mcp(jeton, "tools/call", {"name": "platformlari_listele", "arguments": {}})[1]["result"]
        self.assertEqual([p["id"] for p in json.loads(sonuc["content"][0]["text"])["platformlar"]], ["deneme"])
        sonuc = self.mcp(jeton, "tools/call", {"name": "ortam_durumu", "arguments": {"platform": "tekstil", "ortam": "production"}})
        self.assertTrue(sonuc[1]["result"]["isError"])
        sonuc = self.mcp(jeton, "tools/call", {"name": "ortam_durumu", "arguments": {"platform": "deneme", "ortam": "production"}})
        self.assertFalse(sonuc[1]["result"]["isError"])
        self.assertEqual(tp.SahteAjan.istekler[-1]["yol"], "/odoolar/deneme/production/durum")
        self.assertEqual(tp.SahteAjan.istekler[-1]["basliklar"]["X-Panel-Kullanici"], "ayse")
        # kod değişikliği yalnız staging dalına
        self.mcp(jeton, "tools/call", {"name": "staging_degisikligi_gonder", "arguments": {
            "platform": "deneme", "dosyalar": [{"yol": "m/a.py", "icerik": "x"}], "mesaj": "[FIX] m"}})
        self.assertEqual(tp.SahteAjan.istekler[-1]["yol"], "/odoolar/deneme/staging/asistan-commit")
        # denetim kaydında
        kod, d, _ = self.istek("GET", "/api/denetim", oturum=o)
        olaylar = [k["olay"] for k in d["kayitlar"]]
        self.assertIn("MCP ortam_durumu", olaylar)
        self.assertIn("JETON URETTI Codex dizüstü", olaylar)
        # bilinmeyen yöntem
        self.assertEqual(self.mcp(jeton, "sampling/createMessage")[1]["error"]["code"], -32601)

    def test_rol_araclari_suzer_ve_jeton_kaldirilir(self):
        jeton, o = self.jeton("destek", "destek-sifre1")
        adlar = [a["name"] for a in self.mcp(jeton, "tools/list")[1]["result"]["tools"]]
        self.assertIn("loglar", adlar)
        self.assertNotIn("sql_sorgu", adlar)
        self.assertNotIn("staging_degisikligi_gonder", adlar)
        sonuc = self.mcp(jeton, "tools/call", {"name": "sql_sorgu", "arguments": {"platform": "deneme", "ortam": "production",
                                                                                   "sorgu": "SELECT 1"}})[1]["result"]
        self.assertTrue(sonuc["isError"])
        liste = self.istek("GET", "/api/baglantilar", oturum=o)[1]["baglantilar"]
        self.assertEqual(self.istek("POST", f"/api/baglantilar/{liste[0]['id']}/sil", {}, oturum=o)[0], 200)
        self.assertEqual(self.mcp(jeton, "ping")[0], 401)

    def test_kullanici_silinince_jeton_gecersiz(self):
        jeton, _ = self.jeton("destek", "destek-sifre1")
        p = self.giris("platform", "platform-sifre")
        self.assertEqual(self.istek("POST", "/api/kullanicilar/destek/sil", {}, oturum=p)[0], 200)
        self.assertEqual(self.mcp(jeton, "ping")[0], 401)

    def test_oauth_pkce_akisi(self):
        kod, veri, _ = self.istek("POST", "/oauth/register", {"client_name": "Claude", "redirect_uris": ["https://kotu.example/cb"]})
        self.assertEqual(kod, 400)
        kod, istemci, _ = self.istek("POST", "/oauth/register", {"client_name": "Claude", "redirect_uris": [CLAUDE_DONUS]})
        self.assertEqual(kod, 201)
        dogrulayici = "d" * 64
        meydan = base64.urlsafe_b64encode(hashlib.sha256(dogrulayici.encode()).digest()).rstrip(b"=").decode()
        p = {"response_type": "code", "client_id": istemci["client_id"], "redirect_uri": CLAUDE_DONUS,
             "code_challenge": meydan, "code_challenge_method": "S256", "state": "durum-1", "scope": "mcp"}
        kod, sayfa, basliklar = self.ham("GET", "/oauth/authorize?" + urlencode(p))
        self.assertEqual(kod, 200)
        self.assertIn("Claude", sayfa)
        self.assertIn("https://claude.ai", basliklar["Content-Security-Policy"])
        # yanlış şifre -> kod verilmez
        kod, _, _ = self.ham("POST", "/oauth/authorize", urlencode({**p, "karar": "evet", "kullanici": "ayse", "sifre": "yanlis"}).encode(),
                             {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(kod, 401)
        kod, _, basliklar = self.ham("POST", "/oauth/authorize",
                                     urlencode({**p, "karar": "evet", "kullanici": "ayse", "sifre": "ayse-sifresi1"}).encode(),
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(kod, 302)
        donus = urlsplit(basliklar["Location"])
        q = {k: v[0] for k, v in parse_qs(donus.query).items()}
        self.assertEqual((f"{donus.scheme}://{donus.netloc}{donus.path}", q["state"]), (CLAUDE_DONUS, "durum-1"))
        form = {"Content-Type": "application/x-www-form-urlencoded"}
        kotu = urlencode({"grant_type": "authorization_code", "code": q["code"], "redirect_uri": CLAUDE_DONUS,
                          "client_id": istemci["client_id"], "code_verifier": "x" * 64}).encode()
        self.assertEqual(json.loads(self.ham("POST", "/oauth/token", kotu, form)[1])["error"], "invalid_grant")
        # kod tek kullanımlık: yanlış doğrulayıcıyla denenen kod artık geçmez; yeni kod al
        kod, _, basliklar = self.ham("POST", "/oauth/authorize",
                                     urlencode({**p, "karar": "evet", "kullanici": "ayse", "sifre": "ayse-sifresi1"}).encode(), form)
        q = {k: v[0] for k, v in parse_qs(urlsplit(basliklar["Location"]).query).items()}
        iyi = urlencode({"grant_type": "authorization_code", "code": q["code"], "redirect_uri": CLAUDE_DONUS,
                         "client_id": istemci["client_id"], "code_verifier": dogrulayici}).encode()
        kod, govde, basliklar = self.ham("POST", "/oauth/token", iyi, form)
        jetonlar = json.loads(govde)
        self.assertEqual((kod, jetonlar["token_type"], basliklar["Cache-Control"]), (200, "Bearer", "no-store"))
        adlar = [a["name"] for a in self.mcp(jetonlar["access_token"], "tools/list")[1]["result"]["tools"]]
        self.assertIn("kod_oku", adlar)
        # yenileme: eski yenileme jetonu tek kullanımlık
        yenile = urlencode({"grant_type": "refresh_token", "refresh_token": jetonlar["refresh_token"],
                            "client_id": istemci["client_id"]}).encode()
        kod, govde, _ = self.ham("POST", "/oauth/token", yenile, form)
        self.assertEqual(kod, 200)
        self.assertEqual(self.ham("POST", "/oauth/token", yenile, form)[0], 400)
        yeni = json.loads(govde)["access_token"]
        self.assertEqual(self.mcp(yeni, "ping")[0], 200)
        # reddetme -> access_denied
        kod, _, basliklar = self.ham("POST", "/oauth/authorize", urlencode({**p, "karar": "hayir"}).encode(), form)
        self.assertIn("error=access_denied", basliklar["Location"])
        # bağlantılar ekranında OAuth istemcisi görünür ve kaldırılabilir
        o = self.giris("ayse", "ayse-sifresi1")
        liste = self.istek("GET", "/api/baglantilar", oturum=o)[1]["baglantilar"]
        oauth = [b for b in liste if b["tur"] == "oauth"]
        self.assertEqual(oauth[0]["ad"], "Claude")
        self.istek("POST", f"/api/baglantilar/{oauth[0]['id']}/sil", {}, oturum=o)
        self.assertEqual(self.mcp(yeni, "ping")[0], 401)


def _blok(**k):
    return SimpleNamespace(**k)


class SahteClaude:
    """beta.messages.create çağrılarını sırayla yanıtlar; gelen istekleri saklar."""

    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.istekler = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._olustur))

    def _olustur(self, **istek):
        self.istekler.append({**istek, "messages": list(istek["messages"])})
        icerik, neden = self.yanitlar.pop(0)
        return SimpleNamespace(content=icerik, stop_reason=neden,
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))


class AsistanSohbetTesti(unittest.TestCase):
    setUp = tp.PanelTesti.setUp
    tearDown = tp.PanelTesti.tearDown
    istek = tp.PanelTesti.istek
    giris = tp.PanelTesti.giris

    def bekle(self, o, yol):
        for _ in range(100):
            v = self.istek("GET", yol, oturum=o)[1]
            if not v["mesgul"]:
                return v
            time.sleep(0.05)
        self.fail("asistan bitmedi")

    def test_ayar_yalniz_platform(self):
        a = self.giris("ayse", "ayse-sifresi1")
        self.assertEqual(self.istek("POST", "/api/baglantilar/asistan-ayar", {"anahtar": "sk-ant-x"}, oturum=a)[0], 403)
        p = self.giris("platform", "platform-sifre")
        kod, v, _ = self.istek("POST", "/api/baglantilar/asistan-ayar", {"anahtar": "sk-ant-deneme-1234", "effort": "medium"}, oturum=p)
        self.assertEqual((kod, v["anahtar_var"], v["anahtar_son"], v["effort"]), (200, True, "1234", "medium"))
        self.assertNotIn("sk-ant-deneme", json.dumps(self.istek("GET", "/api/baglantilar", oturum=p)[1]))
        self.assertEqual(self.istek("POST", "/api/baglantilar/asistan-ayar", {"anahtar": "yanlis"}, oturum=p)[0], 400)

    def test_sohbet_arac_ve_onay(self):
        p = self.giris("platform", "platform-sifre")
        self.istek("POST", "/api/baglantilar/asistan-ayar", {"anahtar": "sk-ant-deneme-1234"}, oturum=p)
        sahte = SahteClaude([
            ([_blok(type="text", text="Duruma bakıyorum."),
              _blok(type="tool_use", id="t1", name="ortam_durumu", input={"platform": "deneme", "ortam": "production"})], "tool_use"),
            ([_blok(type="tool_use", id="t2", name="staging_degisikligi_gonder",
                    input={"platform": "deneme", "dosyalar": [{"yol": "m/a.py", "icerik": "x = 2\n"}], "mesaj": "[FIX] m"})], "tool_use"),
            ([_blok(type="text", text="Değişikliği onayınıza sundum.")], "end_turn"),
        ])
        eski = asistan.istemci_olustur
        asistan.istemci_olustur = lambda anahtar: sahte
        try:
            a = self.giris("ayse", "ayse-sifresi1")
            yol = "/api/asistan/deneme/production"
            self.assertEqual(self.istek("GET", "/api/asistan/tekstil/production", oturum=a)[0], 404)  # kapsam dışı
            kod, v, _ = self.istek("POST", yol + "/mesaj", {"metin": "Neden yavaş?"}, oturum=a)
            self.assertEqual(kod, 200, v)
            v = self.bekle(a, yol)
        finally:
            asistan.istemci_olustur = eski
        self.assertEqual([x["tur"] for x in v["akis"]], ["ben", "cevap", "adim", "adim", "cevap"])
        self.assertEqual(v["oneri"]["dosyalar"][0]["yol"], "m/a.py")
        ilk = sahte.istekler[0]
        self.assertEqual((ilk["model"], ilk["thinking"], ilk["fallbacks"]), ("claude-opus-5-5", {"type": "adaptive"}, "default"))
        self.assertIn("[Platform: deneme, ortam: production]", ilk["messages"][0]["content"])
        sonuc = sahte.istekler[1]["messages"][-1]["content"][0]
        self.assertEqual((sonuc["type"], sonuc["tool_use_id"]), ("tool_result", "t1"))
        # öneri onaylanmadan ajana commit gitmez
        self.assertFalse([i for i in tp.SahteAjan.istekler if i["yol"].endswith("asistan-commit")])
        kod, v, _ = self.istek("POST", yol + "/onay", {"evet": True}, oturum=a)
        self.assertEqual(kod, 202)
        self.assertEqual(tp.SahteAjan.istekler[-1]["yol"], "/odoolar/deneme/staging/asistan-commit")
        # yetkisiz rol
        d = self.giris("destek", "destek-sifre1")
        self.assertEqual(self.istek("GET", yol, oturum=d)[0], 403)
