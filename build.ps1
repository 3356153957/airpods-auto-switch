param(
    [string]$Python = '',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist'),
    [switch]$Package
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not $Python) {
        foreach ($candidate in @('.venv/Scripts/python.exe', '../.venv/Scripts/python.exe')) {
            if (Test-Path -LiteralPath $candidate) { $Python = (Resolve-Path -LiteralPath $candidate).Path; break }
        }
        if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
    }
    $airpodsOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
    $airpodsVendor = Join-Path $PSScriptRoot 'vendor/BluetoothDevicePairing.exe'
    if ((Get-FileHash -LiteralPath $airpodsVendor -Algorithm SHA256).Hash -ne '6558860924D2DD9DC2A8A6EB6F8B3C6080F762AEC1C57A91CBDCACD3259B9621') {
        throw 'BluetoothDevicePairing.exe checksum mismatch'
    }
    $airpodsIcon = Join-Path $PSScriptRoot 'app.ico'
    & $Python -c "from ui_styles import app_icon; app_icon(256).save('app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if ($LASTEXITCODE -ne 0) { throw 'Icon build failed' }
    $airpodsVersion = (& $Python -c 'from app_version import VERSION; print(VERSION)').Trim()
    & $Python -m PyInstaller --noconfirm --onedir --windowed --name AirPodsSwitch --icon $airpodsIcon --distpath $airpodsOutput --workpath build --specpath build --add-binary "$airpodsVendor;vendor" --add-data "$airpodsIcon;." --collect-all customtkinter --hidden-import pystray._win32 main.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    $airpodsApp = Join-Path $airpodsOutput 'AirPodsSwitch'
    Copy-Item -LiteralPath README.md,README.zh-CN.md,THIRD-PARTY-NOTICES.md -Destination $airpodsApp
    Copy-Item -LiteralPath vendor/BluetoothDevicePairing.LICENSE.txt -Destination $airpodsApp
    & $Python tools/collect_licenses.py (Join-Path $airpodsApp 'licenses')
    if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
    if ($Package) {
        $airpodsZip = Join-Path $airpodsOutput "AirPodsSwitch-v$airpodsVersion-windows-x64.zip"
        Compress-Archive -LiteralPath $airpodsApp -DestinationPath $airpodsZip -Force
        $airpodsHash = (Get-FileHash -LiteralPath $airpodsZip -Algorithm SHA256).Hash.ToLowerInvariant()
        "$airpodsHash  $([System.IO.Path]::GetFileName($airpodsZip))" | Set-Content -LiteralPath (Join-Path $airpodsOutput 'SHA256SUMS.txt') -Encoding ascii
        Write-Output $airpodsZip
    }
} finally {
    Pop-Location
}
