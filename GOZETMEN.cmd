@echo off
rem ok-czn gozetmenini yonetici olarak bir kez acar. Pencereyi kapatana kadar calisir.
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0GOZETMEN.ps1"
