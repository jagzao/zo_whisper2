@echo off
REM Single entrypoint for the US-001 manual acceptance demo (READY_FOR_JUAN_ACCEPTANCE_TEST).
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo ========================================================================
echo   ZO MEDIA INTELLIGENCE - DEMO (datos 100%% sinteticos, sin LLM externo)
echo ========================================================================
echo.

if exist "watcher\venv\Scripts\python.exe" (
    set PYTHON_EXE=watcher\venv\Scripts\python.exe
    goto :have_python
)
if exist "C:\ProgramData\miniconda3\python.exe" (
    set PYTHON_EXE=C:\ProgramData\miniconda3\python.exe
    goto :have_python
)
if exist "%USERPROFILE%\miniconda3\python.exe" (
    set PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe
    goto :have_python
)
python --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_EXE=python
    goto :have_python
)

echo [ERROR] No se encontro Python instalado.
pause
exit /b 1

:have_python
echo [1/2] Generando video demo sintetico (si no existe)...
%PYTHON_EXE% scripts\generate_demo_video.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se pudo generar el video demo.
    pause
    exit /b 1
)

echo.
echo [2/2] Arrancando el dashboard...
echo.
echo ========================================================================
echo   3 PASOS PARA LA PRUEBA MANUAL:
echo   1. Abri en el navegador:  http://127.0.0.1:5000
echo   2. Arrastra este archivo al DROP AREA:
echo      demo\en_demo_zo_media_intelligence_tutorial.mp4
echo   3. Click en "RUN Full" y segui el pipeline
echo ========================================================================
echo.
echo (Ctrl+C para detener el dashboard)
echo.

%PYTHON_EXE% dashboard.py
pause
