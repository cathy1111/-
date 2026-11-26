@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call :find_python
if not defined TASK_PY goto missing_python
echo Import a real test outline, or examples\sample_outline.csv for a DEMO.
echo Supported: CSV, XLSX, DOCX, PDF, TXT. Scanned PDFs use local OCR.
echo Drag one outline file into this window, then press Enter.
set "TASK_OUTLINE="
set /p "TASK_OUTLINE=Outline path: "
set "TASK_OUTLINE=%TASK_OUTLINE:"=%"
if not defined TASK_OUTLINE goto no_file
if not exist "%TASK_OUTLINE%" goto no_file
"%TASK_PY%" split_experiments.py import-outline --input "%TASK_OUTLINE%" --out "%~dp0."
if errorlevel 1 goto failed
echo DONE. Check outline_catalog.csv, then close it and run run_preview.bat.
pause
exit /b 0
:find_python
set "TASK_PY="
call :try_python "%~dp0.venv\Scripts\python.exe"
if defined TASK_PY exit /b
call :try_python "%LocalAppData%\Programs\Python\Python39\python.exe"
if defined TASK_PY exit /b
call :try_python "%ProgramFiles%\Python39\python.exe"
if defined TASK_PY exit /b
call :try_python "C:\Python39\python.exe"
if defined TASK_PY exit /b
for /f "delims=" %%P in ('py -3.9 -c "import sys; print(sys.executable)" 2^>nul') do call :try_python "%%P"
if defined TASK_PY exit /b
for /f "delims=" %%P in ('where python 2^>nul') do call :try_python "%%P"
exit /b
:try_python
if defined TASK_PY exit /b
if not exist "%~1" exit /b
"%~1" -c "import sys,struct; sys.exit(0 if sys.version_info[:2]==(3,9) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 set "TASK_PY=%~1"
exit /b

:missing_python
echo Python 3.9 64-bit not found. Install the original environment first.
pause
exit /b 1
:no_file
echo Outline file not found. Drag a single existing outline file and retry.
pause
exit /b 1
:failed
echo IMPORT FAILED. Take a screenshot including the first error above.
pause
exit /b 1
