@echo off
chcp 65001 >NUL
title Ashen Crown
cd /d "%~dp0"
where python >NUL 2>NUL
if errorlevel 1 goto single
echo Starting local server on http://localhost:5186/ ...
start "Ashen Crown server" /min python tools\devserver.py 5186
timeout /t 2 /nobreak >NUL
start "" http://localhost:5186/
exit /b
:single
echo Python not found - opening the single-file build instead.
start "" "dist\ashen-crown.html"
