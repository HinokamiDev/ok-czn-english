@echo off
setlocal
cd /d "%~dp0"
rem HinokamiDev catali: ok-czn'i kaynaktan, otomatik guncelleme OLMADAN calistirir.
rem Oyun yonetici yetkisiyle calistigi icin ok-czn de yonetici olmali; yoksa tiklamalar oyuna ulasmaz.

net session >nul 2>&1
if errorlevel 1 (
  echo Yonetici izni isteniyor...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

if exist ".venv\Scripts\python.exe" goto deps
echo Ilk kurulum: Python 3.12 ortami hazirlaniyor...
py -3.12 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo Python 3.12 bulunamadi. Kur: winget install -e --id Python.Python.3.12
  pause
  exit /b 1
)

:deps
rem Paketler yalniz requirements.txt degistiginde yeniden kurulur.
fc /b requirements.txt ".venv\kurulu-requirements.txt" >nul 2>&1
if not errorlevel 1 goto run
echo Paketler kuruluyor (ilk seferde birkac dakika surer)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Paket kurulumu basarisiz oldu.
  pause
  exit /b 1
)
copy /y requirements.txt ".venv\kurulu-requirements.txt" >nul

:run
echo ok-czn baslatiliyor...
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
