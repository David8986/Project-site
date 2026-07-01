@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\check-openai-key.ps1" %*
exit /b %ERRORLEVEL%
