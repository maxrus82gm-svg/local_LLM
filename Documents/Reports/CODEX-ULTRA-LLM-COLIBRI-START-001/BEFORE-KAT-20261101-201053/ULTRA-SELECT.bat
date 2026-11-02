@echo off
setlocal DisableDelayedExpansion
title Ultra LLM - Colibri MODEL SELECT
if /I not "%COMPUTERNAME%"=="DESKTOP-KT4G5SM" goto :wrong_host
pushd "%~dp0" || exit /b 1
echo.
echo Choose ONE model. The active Colibri session will be stopped first.
echo 1 - Qwen3-Coder-30B-A3B
echo 2 - DeepSeek-V4-Flash-REAP-150B - experimental, disk streaming
echo 3 - Cancel
echo.
choice /C 123 /N /M "Select [1/2/3]: "
if errorlevel 3 goto :cancel
if errorlevel 2 goto :deepseek
if errorlevel 1 goto :qwen
goto :cancel
:deepseek
set "ULTRA_MODEL=deepseek"
goto :run
:qwen
set "ULTRA_MODEL=qwen"
:run
py -3.12 -B "%~dp0ULTRA-CONTROL.py" start --switch --model %ULTRA_MODEL% %*
set "ULTRA_RC=%ERRORLEVEL%"
if not "%ULTRA_NOPAUSE%"=="1" pause
popd
exit /b %ULTRA_RC%
:cancel
popd
exit /b 0
:wrong_host
echo Run this BAT locally ON DESKTOP-KT4G5SM, as the original Colibri user.
echo A BAT opened over SMB on another PC runs on that other PC.
if not "%ULTRA_NOPAUSE%"=="1" pause
exit /b 3
