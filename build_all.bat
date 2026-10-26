@echo off
title TikTok Farm - Build Executable & Installer
color 0b

echo ========================================================
echo   TIKTOK AUTO FARM & AI VIDEO ENGINE - BUILD PIPELINE
echo ========================================================
echo.

REM 1. PyInstaller Build
echo [1/3] Dang dong goi Executable voi PyInstaller...
python -m PyInstaller --clean --noconfirm TikTokFarm.spec
if %errorlevel% neq 0 (
    echo [LOI] Qua trinh dong goi PyInstaller that bai!
    pause
    exit /b 1
)

REM 2. Code Signing & Inno Setup
echo [2/3] Dang ky so Authenticode va bien dich Installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$cert = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -match 'TikTok Farm' } | Select-Object -First 1;" ^
    "if (-not $cert) { $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=TikTok Farm Developer, O=TikTok Farm Systems' -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5); }" ^
    "Set-AuthenticodeSignature -FilePath 'dist\TikTokFarm\TikTokFarm.exe' -Certificate $cert -HashAlgorithm SHA256 | Out-Null;" ^
    "& 'C:\Users\datng\AppData\Local\Programs\Inno Setup 6\ISCC.exe' installer.iss;" ^
    "if (Test-Path 'dist_installer\TikTokAutoFarm_Setup_v1.0.0.exe') {" ^
    "    Set-AuthenticodeSignature -FilePath 'dist_installer\TikTokAutoFarm_Setup_v1.0.0.exe' -Certificate $cert -HashAlgorithm SHA256 | Out-Null;" ^
    "    Export-Certificate -Cert $cert -FilePath 'dist_installer\TikTokFarm_Developer.cer' -Force | Out-Null;" ^
    "}"

if %errorlevel% neq 0 (
    echo [LOI] Qua trinh bien dich Installer that bai!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo [HOAN TAT THU MUC OUTPUT]:
echo 1. Bo cai dat: dist_installer\TikTokAutoFarm_Setup_v1.0.0.exe
echo 2. File chay truc tiep: dist\TikTokFarm\TikTokFarm.exe
echo 3. Chung chi so: dist_installer\TikTokFarm_Developer.cer
echo ========================================================
echo.
pause
