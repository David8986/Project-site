@echo off
cd /d "%~dp0\.."
python "spectraleaf_esp32_integration\auto_capture_analyze.py" serve --host 127.0.0.1 --port 8765
