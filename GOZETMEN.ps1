# ok-czn gözetmeni (HinokamiDev çatalı).
# Yönetici olarak BİR KEZ açılır (GOZETMEN.cmd). Sonra bir istek dosyası görünce ok-czn'i kapatıp yeniden açar;
# ok-czn de yönetici olduğu için bu, her yeniden başlatmada UAC sormadan yapılabilsin diye vardır.
#
# İstek: %LOCALAPPDATA%\ok-czn-hd\yeniden-baslat.istek
#   İçeriği boş olabilir ya da başlatılacak modun adı olabilir: StoryMode, ChaosMode, SortieMode.
#   Mod adı varsa ok-czn açıldıktan sonra o mod kendiliğinden başlar (otomatik-baslat.json, tek kullanımlık).
# Kayıt: %LOCALAPPDATA%\ok-czn-hd\gozetmen.log
#
# Yalnız bu klasördeki .venv içinden çalışan python süreçlerini kapatır. Oyuna dokunmaz.

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root '.venv'
$dir = Join-Path $env:LOCALAPPDATA 'ok-czn-hd'
$request = Join-Path $dir 'yeniden-baslat.istek'
$autostart = Join-Path $dir 'otomatik-baslat.json'
$log = Join-Path $dir 'gozetmen.log'
$modes = @('StoryMode', 'ChaosMode', 'SortieMode')
New-Item -ItemType Directory -Force -Path $dir | Out-Null

function Write-Log($message) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $message
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Host $line
}

function Stop-OkCzn {
    $targets = Get-Process python, pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase) }
    foreach ($p in $targets) { taskkill /PID $p.Id /T | Out-Null }
    Start-Sleep -Seconds 5
    foreach ($p in $targets) {
        if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { taskkill /PID $p.Id /T /F | Out-Null }
    }
    return $targets.Count
}

Write-Log "gozetmen basladi ($root)"
while ($true) {
    if (Test-Path $request) {
        $mode = (Get-Content -Path $request -Raw -ErrorAction SilentlyContinue)
        if ($mode) { $mode = $mode.Trim() }
        Remove-Item -Path $request -Force -ErrorAction SilentlyContinue
        $stopped = Stop-OkCzn
        if ($mode -and ($modes -contains $mode)) {
            Set-Content -Path $autostart -Value ('{"mod": "' + $mode + '"}') -Encoding UTF8
        }
        Start-Sleep -Seconds 2
        Start-Process -FilePath (Join-Path $root 'BASLAT.cmd') -WorkingDirectory $root
        Write-Log "yeniden baslatildi (kapatilan surec: $stopped, mod: $mode)"
    }
    Start-Sleep -Seconds 2
}
