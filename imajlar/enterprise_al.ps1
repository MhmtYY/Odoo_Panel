# Fetches Odoo Enterprise with your own GitHub access (19.0 and 20.0, the commit matching the image date) and packs it.
# Output: D:\Proje\Odoo_Yonetim_Paneli\enterprise_kaynak\enterprise19.tar.gz, enterprise20.tar.gz and .commit files.
# Licensed code: this folder never goes into git; it only goes into the image on our own server.
# Runs on Windows PowerShell 5.1.
$ErrorActionPreference = "Stop"
$Tarih = "2026-11-02 23:59:59 +0000"
$Kok = "D:\Proje\Odoo_Yonetim_Paneli\enterprise_kaynak"
$Depo = Join-Path $Kok "enterprise.git"
New-Item -ItemType Directory -Force $Kok | Out-Null

function Git-Calistir {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git hatasi: git $args" }
}

if (-not (Test-Path $Depo)) {
    Write-Host "Depo hazirlaniyor..."
    Git-Calistir init -q --bare $Depo
    Git-Calistir -C $Depo remote add origin git@github.com:odoo/enterprise.git
}
Write-Host "19.0 ve 20.0 aliniyor..."
Git-Calistir -C $Depo fetch -q --shallow-since=2026-10-15 origin "+refs/heads/19.0:refs/heads/19.0" "+refs/heads/20.0:refs/heads/20.0"

foreach ($Seri in "19", "20") {
    $Commit = (& git -C $Depo rev-list -1 "--before=$Tarih" "$Seri.0")
    if (-not $Commit) { throw "$Seri.0 icin $Tarih oncesi commit bulunamadi" }
    $Commit = $Commit.Trim()
    $Hedef = Join-Path $Kok "enterprise$Seri.tar.gz"
    Write-Host "enterprise $Seri.0 -> $Commit"
    Git-Calistir -C $Depo archive --format=tar.gz -o $Hedef $Commit
    [System.IO.File]::WriteAllText((Join-Path $Kok "enterprise$Seri.commit"), "$Commit`n", (New-Object System.Text.UTF8Encoding $false))
    $Boyut = [math]::Round((Get-Item $Hedef).Length / 1MB)
    Write-Host "TAMAM: $Hedef ($Boyut MB)"
}
