# Odoo Yönetim Paneli

GitHub'a bağlı, çok Odoo'lu yönetim paneli. Sunucuda `panel.vekosis.com` adresinde çalışır.

## Parçalar

| Klasör | Ne | Nerede çalışır |
|---|---|---|
| `ajan/` | Docker, PostgreSQL ve git işlerini yapan hizmet. Yalnız panel konteynerinden, gizli anahtarla istek kabul eder. | Sunucuda root, systemd hizmeti `odoo-panel-ajan` |
| `panel/` | Web arayüzü ve API: giriş, roller, Odoo başına yetki, işlem kaydı. GitHub webhook'unu da karşılar. | Konteyner `pnl-panel`, root yetkisi yok, Docker'a erişemez |
| `sunucu/` | Kurulum betiği, systemd birimleri, Caddy bloğu | Sunucu |
| `testler/` | Docker gerektirmeyen birim ve akış testleri | Geliştirici makinesi |

Ajan yalnız standart Python kitaplığını kullanır (Python 3.12). Panelin tek dış paketi, panel içi asistan için resmî Claude SDK'sıdır (`anthropic==2.8.0`, panel imajında kurulur).

## Ad alanı

Yeni panelin açtığı her şey eski test platformundan ayrı adlarla açılır. Eski platformun betikleri yarım kalan kurulumda aynı adlı konteyneri, birimi ve veritabanını sildiği için adlar kesişmemeli.

| Ne | Biçim | Örnek |
|---|---|---|
| Adres | `<ad>.panel.vekosis.com`, `<ad>-staging.panel.vekosis.com` | `deneme.panel.vekosis.com` |
| Konteyner | `pnl-<ad>`, `pnl-<ad>-staging` | `pnl-deneme` |
| Dosya deposu birimi | `pnl-<ad>-data`, `pnl-<ad>-staging-data` | |
| Veritabanı | `pnl_<ad>`, `pnl_<ad>_staging` | `pnl_deneme` |
| Veritabanı rolü | `pnl_<ad>`, `pnl_<ad>_st` | |

Sunucuda durum klasörü `/opt/odoo-panel`:

```
ayar/            anahtarlar, GitHub App bilgisi, webhook sırrı (yalnız root)
depolar/         GitHub depolarının çıplak aynaları
odoolar/<ad>/    odoo.json; production/ ve staging/ altında ortam.json, compose.yml, odoo.conf, kod/<commit>, deploylar/
yedekler/<ad>/<ortam>/
isler/           iş kayıtları ve günlükleri
```

## Sunucuya kurulum

1. Dizüstünde paketleyin: `python araclar/paketle.py`. Sonuç `../dagitim/odoo_panel_<sürüm>.tar.gz` ve `.sha256` olur.
   - Paket yalnız `ajan/`, `panel/` ve `sunucu/` klasörlerini içerir; satır sonları LF yapılır.
   - Sürüm commit özetidir. Commit'lenmemiş değişiklik varsa ardına içerik özeti eklenir.
2. Paketi sunucuya kopyalayın, `/opt/odoo-panel/paket/<sürüm>` altına açın ve `odoo-panel/sunucu/kur.sh` betiğini root olarak çalıştırın.

`kur.sh` tekrar çalıştırılabilir; güncelleme de aynı yoldan yapılır. Ayarlara, kullanıcılara ve ortamlara dokunmaz. Yaptıkları:

- ajanı systemd hizmeti olarak kurar (`odoo-panel-ajan`, vtest ağ geçidi:8098) ve gece yedeği zamanlayıcısını açar (04:20);
- `pnl-panel` konteynerini açar;
- Caddy'ye `panel.caddy` dosyasını ve Caddyfile'a tek bir `import` satırını ekler:
  - önce yedek alır ve yeni yapılandırmayı doğrular;
  - değişiklikten önce 200 dönen ERP, test ve müşteri adreslerinden biri sonra dönmezse eski Caddyfile'ı geri koyar;
  - DNS'te `panel.vekosis.com` bu sunucuyu göstermiyorsa bu adımı atlar.
- ilk platform yöneticisini (`vekosis`) açar. Şifresi `/opt/odoo-panel/panel/ILK-KULLANICI.txt` dosyasına yazılır, ekrana basılmaz.

Geri dönüş: `bash /opt/odoo-panel/kod/sunucu/kaldir.sh`. Caddy satırını çıkarır, panel konteynerini ve ajanı durdurur; veriye ve ortam konteynerlerine dokunmaz.

Eski test platformunun `kur.sh` betiği Caddyfile'ı baştan yazar. O çalışırsa paneldeki `import` satırı gider. Panelin `kur.sh` betiğini tekrar çalıştırmak satırı geri koyar.

## Bağlanan kurulumlar

Panelin kurmadığı Odoo'lar (erp.vekosis.com, test platformundaki ortamlar) "bağlanır". Bağlarken hiçbir şey yeniden başlatılmaz, compose dosyalarına dokunulmaz. Bağlanan kurulumda panel şunları yapar:

- izler;
- kendi yedeğini alır;
- production'dan staging açar.

Durdurma ve başlatma, kuruluma ayrıca izin verilince açılır. Deploy yalnız panelin kurduğu Odoo'larda var.

## Arayüz

Kaynak `panel/arayuz/` altında; tasarım önizlemedeki petrol-turkuaz tasarımın aynısıdır. Derlenmiş hali `panel/static/` altındadır ve panel konteyneri yalnız onu sunar. Kaynağı değiştirdikten sonra derleyin:

```
python araclar/arayuz_derle.py
```

Arayüzde yalnız arka ucu olan işlevler var:

- Odoo kurma, mevcut Odoo'yu bağlama ve silme;
- ortam hattı ve production'a alma;
- deploy, geri alma (kod ya da kod + veri) ve uyumluluk denetimi;
- staging oluşturma, yenileme ve kaldırma; yedek alma, indirme, geri yükleme ve yedeği staging'de açma;
- modül listesi ve zip → depo;
- loglar ve izleme (aşağıda);
- depo bağlama (GitHub App, deploy key, herkese açık);
- asistan ve ajan bağlantıları (aşağıda);
- kullanıcılar, roller ve platform başına erişim; denetim kaydı (hata metni ve arka plan işinin sonucuyla).

Uzun işler (deploy, staging, yedek) pencerede adım adım izlenir. Pencere kapanırsa iş sürer ve bitince bildirim gelir. Hata bildirimi kapatılana kadar durur; komut ve çıktısı "Teknik ayrıntı" altında görünür.

## İzleme

Ajan dakikada bir her ortamı ölçer (`ajan/izleme.py`) ve `/opt/odoo-panel/izleme/<platform>/<ortam>/<gün>.jsonl` dosyalarına yazar (8 gün; günlük erişilebilirlik özeti 35 gün):

- konteyner: durum, işlemci, bellek; Odoo süreç sayısı;
- sağlık: sunucudan konteynere `/web/health` ve yanıt süresi;
- istekler: son ölçümden beri konteyner çıktısındaki istek satırları (istek/dakika, 5xx, p95 yanıt süresi, en yavaş uçlar). Odoo logu dosyaya yazıyorsa bu bölüm boş kalır;
- veritabanı: bağlantı sayısı, 10 dakikada bir boyut.

İzleme sekmesinde 1 saat / 24 saat / 7 gün grafikleri, en yavaş uçlar, zamanlanmış işler (`ir_cron`, hata sayısıyla) ve 30 günlük erişilebilirlik şeridi gösterilir.

## Asistan ve ajan bağlantıları

Araçlar `panel/arac.py` içinde tanımlıdır; panel içi sohbet ve MCP aynı araçları kullanır. Her çağrıda kullanıcının rolü (yetki.py) ve platform kapsamı denetlenir, çağrı denetim kaydına yazılır.

- **Okuyan araçlar:** platform listesi, ortam durumu, izleme özeti, loglar, modüller, deploy geçmişi, yedekler, iş durumu; rol izin veriyorsa çalışan kod (listeleme, okuma, arama) ve salt okunur SQL.
- **Yazan araçlar:** yedek alma ve yalnız **staging** dalına kod değişikliği. Production'a yazan araç yoktur.
- **Salt okunur SQL:** süper kullanıcı olmayan `pnl_okuyucu` rolüyle, `BEGIN TRANSACTION READ ONLY` içinde, 15 sn ve 200 satır sınırıyla. Rolün yetkisi sütun düzeyindedir; adı şifre/anahtar/jeton benzeri sütunlar ve `ir_config_parameter` okunamaz.
- **Kod:** ortamda çalışan kod; lisanslı (enterprise) klasörler, `odoo.conf`, `.env` ve anahtar dosyaları görünmez.

**Panel içi asistan** (platform sayfasında Asistan sekmesi): Claude API ile çalışır. API anahtarı, model ve effort'u platform yöneticisi *Ajan bağlantıları* ekranından girer (`/veri/asistan.json`, tarayıcıya gitmez). Asistanın önerdiği kod değişikliği kullanıcı onaylamadan gönderilmez.

**MCP** (`https://panel.vekosis.com/mcp`, Streamable HTTP, JSON yanıt):

- Claude Desktop / claude.ai: özel bağlayıcı olarak eklenir; giriş OAuth 2.1 ile (PKCE S256, dinamik istemci kaydı; yalnız claude.ai / claude.com ve yerel yönlendirme adresleri kaydolabilir). Erişim jetonu 1 saat, yenileme jetonu 30 gün ve tek kullanımlık.
- Codex ve jeton kabul eden istemciler: *Ajan bağlantıları* ekranında üretilen kişisel jeton (`Authorization: Bearer`).
- Jetonlar `/veri/ajan_baglantilari.json` dosyasında yalnız SHA-256 özetiyle durur; kullanıcı silinince ya da bağlantı kaldırılınca erişim hemen biter.

## Yerel geliştirme sunucusu

```
python araclar/gelistirme.py --port 18080
```

Gerçek ajan ve gerçek panel yerelde açılır. Docker ve PostgreSQL komutları taklittir (`testler/sahte.py`), git gerçektir. Örnek durum her açılışta gerçek akışlardan geçirilerek `yerel/gelistirme/` altında sıfırdan kurulur:

- depoya bağlı, staging'i olan bir Odoo; production'a alınmayı bekleyen bir commit;
- depoya bağlı olmayan bir Odoo;
- bağlanmış bir test platformu ortamı ve bağlanmayı bekleyen bir ERP konteyneri.

Giriş bilgileri dosyanın başında, `GELISTIRME_KULLANICILARI` içinde. Rolleri platform, yönetici ve kullanıcı; yalnız bu yerel sunucu içindir. İzleme ekranı için son 7 günün örnek ölçümleri yazılır; asistan gerçek Claude yerine araçları gerçekten çağıran ama hazır metinle yanıt veren taklit istemciyle çalışır.

## Testler

```
python -m unittest discover -s testler -t .
```

Testler Docker çalıştırmaz. Docker ve PostgreSQL komutları sahte çalıştırıcıyla denetlenir. git komutları gerçek git ile, geçici depolarda çalışır.
