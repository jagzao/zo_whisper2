@echo off
cd /d "C:\Dev\Zo\whisper"
chcp 65001 >nul

echo.
echo ========================================================================
echo   PROCESADOR DE TRANSCRIPCIONES - MAXIMA CALIDAD
echo ========================================================================
echo.
echo   Modelo: large-v2 - beam_size=10 - best_of=5 - VAD - es/en auto
echo.

REM 1. Entorno virtual local
if exist "watcher\venv\Scripts\python.exe" (
    set PYTHON_EXE=watcher\venv\Scripts\python.exe
    echo [OK] Usando Python del entorno virtual local
    goto :run_script
)

REM 2. Miniconda en ProgramData
if exist "C:\ProgramData\miniconda3\python.exe" (
    set PYTHON_EXE=C:\ProgramData\miniconda3\python.exe
    echo [OK] Usando Python de Miniconda (ProgramData)
    goto :run_script
)

REM 3. Miniconda en el usuario
if exist "%USERPROFILE%\miniconda3\python.exe" (
    set PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe
    echo [OK] Usando Python de Miniconda (usuario)
    goto :run_script
)

REM 4. Python desde el PATH
python --version >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_EXE=python
    echo [OK] Usando Python del PATH del sistema
    goto :run_script
)

echo [ERROR] No se encontro Python instalado.
echo.
echo Instala Python desde: https://www.python.org/downloads/
echo O instala Miniconda desde: https://docs.conda.io/en/latest/miniconda.html
echo.
pause
exit /b 1


:run_script
echo.
echo ========================================================================
echo   PASO 1: COMPRESION DE VIDEOS
echo ========================================================================
echo.
%PYTHON_EXE% compress_and_move.py
if %ERRORLEVEL% NEQ 0 echo [WARNING] Hubo problemas en compresion, continuando...

echo.
echo ========================================================================
echo   PASO 2: ORGANIZACION + TRANSCRIPCION
echo ========================================================================
echo.
%PYTHON_EXE% master_processor.py
set MASTER_RESULT=%ERRORLEVEL%

echo.
echo ========================================================================
echo   PROCESO FINALIZADO
echo ========================================================================
echo.
echo Resultados en: C:\Dev\Zo\whisper\CarpetaTranscripciones\
echo Log en:        C:\Dev\Zo\whisper\simple_scan.log
echo.

if %MASTER_RESULT% NEQ 0 (
    echo [ERROR] El proceso termino con errores. Revisa simple_scan.log
) else (
    echo [OK] Transcripciones completadas exitosamente.
)

echo.
pause
