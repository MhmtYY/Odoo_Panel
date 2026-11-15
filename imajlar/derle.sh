#!/bin/bash
# Dört Odoo imajını sunucuda derler ve her birinde boş veritabanına kurulum dener.
#   vekosis/odoo19, vekosis/odoo19e, vekosis/odoo20, vekosis/odoo20e
# Kullanım: derle.sh <enterprise tar.gz klasörü>   (içinde enterprise19.tar.gz, enterprise20.tar.gz ve .commit dosyaları)
# Yalnız yeni imaj üretir: çalışan konteynerlere, ortamlara ve panele dokunmaz.
set -euo pipefail

ODOO_TARIH=20261102
SURUM=1
ETIKET="$ODOO_TARIH-$SURUM"
BURASI=$(cd "$(dirname "$0")" && pwd)
KAYNAK=${1:?Enterprise klasoru verilmeli}
AG=pnl-imaj-deneme
PG=pnl-imaj-deneme-pg

hata() { echo "HATA: $*" >&2; exit 1; }
adim() { printf '\n=== %s (%s)\n' "$1" "$(date +%H:%M:%S)"; }

[ "$(id -u)" = "0" ] || hata "root olarak calistirin"
for s in 19 20; do
    [ -s "$KAYNAK/enterprise$s.tar.gz" ] || hata "$KAYNAK/enterprise$s.tar.gz yok"
    [ -s "$KAYNAK/enterprise$s.commit" ] || hata "$KAYNAK/enterprise$s.commit yok"
    [ -d "$BURASI/addons$s" ] || hata "$BURASI/addons$s yok"
done

temizle() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$AG" >/dev/null 2>&1 || true
    # if/fi: BAGLAM boşken '[ ] && rm' 1 döndürür; set -e altında betik başarıyla bitse de 1 ile çıkar.
    if [ -n "${BAGLAM:-}" ]; then rm -rf "$BAGLAM"; fi
}
trap temizle EXIT

kur_listesi() {
    if [ "$1" = "20" ]; then echo "vekosis_web_html_lang,vekosis_tr_translations"; else echo "vekosis_web_html_lang"; fi
}

derle() {
    local s=$1 kur baglam_ce baglam_ee commit
    kur=$(kur_listesi "$s")
    commit=$(cat "$KAYNAK/enterprise$s.commit")
    BAGLAM=$(mktemp -d)

    adim "Odoo $s Community derleniyor"
    baglam_ce="$BAGLAM/ce"
    mkdir -p "$baglam_ce"
    cp "$BURASI/Dockerfile" "$baglam_ce/"
    cp -r "$BURASI/addons$s" "$baglam_ce/addons"
    docker build --pull -t "vekosis/odoo$s:$ETIKET" \
        --build-arg "ODOO_ETIKET=$s.0-$ODOO_TARIH" --build-arg "SERI=$s.0" \
        --build-arg "AD=Odoo $s Community" --build-arg "KUR=$kur" "$baglam_ce"

    adim "Odoo $s Enterprise derleniyor (commit ${commit:0:12})"
    baglam_ee="$BAGLAM/ee"
    mkdir -p "$baglam_ee/enterprise"
    cp "$BURASI/Dockerfile.enterprise" "$baglam_ee/Dockerfile"
    tar -xzf "$KAYNAK/enterprise$s.tar.gz" -C "$baglam_ee/enterprise"
    docker build -t "vekosis/odoo${s}e:$ETIKET" \
        --build-arg "TABAN=vekosis/odoo$s:$ETIKET" --build-arg "AD=Odoo $s Enterprise" \
        --build-arg "ENTERPRISE_COMMIT=$commit" "$baglam_ee"
    rm -rf "$BAGLAM"
    BAGLAM=
}

dene() {
    local imaj=$1 s=$2 yollar=$3 db kur sonuc beklenen
    db="deneme_$(echo "$imaj" | tr -c 'a-z0-9' '_' | cut -c1-40)"
    kur=$(kur_listesi "$s")
    adim "Deneniyor: $imaj"
    docker exec "$PG" createdb -U odoo "$db"
    if ! docker run --rm --network "$AG" --entrypoint odoo "$imaj" -d "$db" \
            --db_host="$PG" --db_user=odoo --db_password="$PG_SIFRE" --addons-path="$yollar" \
            -i "base,$kur" --load-language=tr_TR --stop-after-init --no-http > "/tmp/$db.log" 2>&1; then
        tail -30 "/tmp/$db.log"
        hata "$imaj kurulum denemesi basarisiz (kayit: /tmp/$db.log)"
    fi
    beklenen="$kur"
    case "$imaj" in *e:*) beklenen="$beklenen,web_enterprise" ;; esac
    for m in ${beklenen//,/ }; do
        sonuc=$(docker exec "$PG" psql -U odoo -d "$db" -Atc "SELECT state FROM ir_module_module WHERE name = '$m'")
        [ "$sonuc" = "installed" ] || hata "$imaj: $m kurulmadi (durum: ${sonuc:-yok})"
    done
    docker run --rm --network none --entrypoint sh "$imaj" -c 'command -v soffice >/dev/null' || hata "$imaj: soffice yok"
    rm -f "/tmp/$db.log"
    echo "Tamam: $imaj ($beklenen kurulu)"
}

derle 19
derle 20

adim "Deneme veritabani aciliyor"
PG_IMAJ=$(docker inspect -f '{{.Config.Image}}' vtest-postgres)
PG_SIFRE=$(openssl rand -hex 16)
docker network create "$AG" >/dev/null
docker run -d --name "$PG" --network "$AG" -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD="$PG_SIFRE" -e POSTGRES_DB=postgres "$PG_IMAJ" >/dev/null
for _ in $(seq 1 60); do
    docker exec "$PG" pg_isready -U odoo -d postgres >/dev/null 2>&1 && break
    sleep 2
done
docker exec "$PG" pg_isready -U odoo -d postgres >/dev/null || hata "deneme veritabani acilmadi"

dene "vekosis/odoo19:$ETIKET"  19 "/mnt/vekosis-addons"
dene "vekosis/odoo19e:$ETIKET" 19 "/mnt/enterprise-addons,/mnt/vekosis-addons"
dene "vekosis/odoo20:$ETIKET"  20 "/mnt/vekosis-addons"
dene "vekosis/odoo20e:$ETIKET" 20 "/mnt/enterprise-addons,/mnt/vekosis-addons"

printf '\n=== IMAJLAR HAZIR ===\n'
docker image ls --filter label=vekosis.imaj=1 --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}'
