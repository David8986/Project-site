@echo off
cd /d "%~dp0"
python -m plant_health_mvp_new_data.analysis_app.main --output "plant_health_mvp_new_data\runs\analysis_export" --language en
pause
