@echo off
setlocal DisableDelayedExpansion
title Ultra LLM - Colibri STATUS
if /I not "%COMPUTERNAME%"=="DESKTOP-KT4G5SM" goto :wrong_host
pushd "%~dp0" || exit /b 1
py -3.12 -B "%~dp0ULTRA-CONTROL.py" status --logs --inspect-model %*
set "ULTRA_RC=%ERRORLEVEL%"
if not "%ULTRA_NOPAUSE%"=="1" pause
popd
exit /b %ULTRA_RC%
:wrong_host
echo Run this BAT locally ON DESKTOP-KT4G5SM, as the original Colibri user.
if not "%ULTRA_NOPAUSE%"=="1" pause
exit /b 3
