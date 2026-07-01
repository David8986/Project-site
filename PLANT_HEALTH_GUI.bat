@echo off
cd /d "%~dp0"
echo Launching the dedicated Viewer app. For processing, use PLANT_HEALTH_ANALYSIS.bat.
python -m plant_health_mvp.viewer_app.main --input "D:\downloads\feuille1\feuille1_mildiou42_15jan_3dpi_test_2018-01-18_22-07-48" --wavelengths "C:\Users\david\OneDrive\Desktop\wave_lengths .csv" --output "plant_health_mvp\runs\viewer_export"
pause
