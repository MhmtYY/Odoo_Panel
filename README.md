# Odoo Yönetim Paneli

GitHub'a bağlı, çok Odoo'lu yönetim paneli. Sunucuda `panel.vekosis.com` adresinde çalışır.

## Parçalar

| Klasör | Ne | Nerede çalışır |
|---|---|---|
| `ajan/` | Docker, PostgreSQL ve git işlerini yapan hizmet. Yalnız panel konteynerinden, gizli anahtarla istek kabul eder. | Sunucuda root, systemd hizmeti `odoo-panel-ajan` |
| `panel/` | Web arayüzü ve API: giriş, roller, Odoo başına yetki, işlem kaydı. GitHub webhook'unu da karşılar. | Konteyner `pnl-panel`, root yetkisi yok, Docker'a erişemez |
| `sunucu/` | Kurulum betiği, systemd birimleri, Caddy bloğu | Sunucu |
| `testler/` | Docker gerektirmeyen birim ve akış testleri | Geliştirici makinesi |

Ajan ve panel yalnız standart Python kitaplığını kullanır (Python 3.12).

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
- loglar ve anlık izleme;
- depo bağlama (GitHub App, deploy key, herkese açık);
- kullanıcılar, roller ve Odoo başına erişim; denetim kaydı.

Uzun işler (deploy, staging, yedek) pencerede adım adım izlenir. Pencere kapanırsa iş sürer ve bitince bildirim gelir.

## Yerel geliştirme sunucusu

```
python araclar/gelistirme.py --port 18080
```

Gerçek ajan ve gerçek panel yerelde açılır. Docker ve PostgreSQL komutları taklittir (`testler/sahte.py`), git gerçektir. Örnek durum her açılışta gerçek akışlardan geçirilerek `yerel/gelistirme/` altında sıfırdan kurulur:

- depoya bağlı, staging'i olan bir Odoo; production'a alınmayı bekleyen bir commit;
- depoya bağlı olmayan bir Odoo;
- bağlanmış bir test platformu ortamı ve bağlanmayı bekleyen bir ERP konteyneri.

Giriş bilgileri dosyanın başında, `GELISTIRME_KULLANICILARI` içinde. Rolleri platform, yönetici ve kullanıcı; yalnız bu yerel sunucu içindir.

## Testler

```
python -m unittest discover -s testler -t .
```

Testler Docker çalıştırmaz. Docker ve PostgreSQL komutları sahte çalıştırıcıyla denetlenir. git komutları gerçek git ile, geçici depolarda çalışır.
