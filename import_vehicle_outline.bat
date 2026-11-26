@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call :find_python
if not defined TASK_PY goto missing_python
echo Import a full PDF outline for ONE vehicle family, A to F, or an exact vehicle ID.
set "TASK_VEHICLE="
set /p "TASK_VEHICLE=Vehicle family or ID (for example A or A204): "
if not defined TASK_VEHICLE goto no_file
echo Drag that vehicle's outline PDF, CSV, XLSX, DOCX or TXT file here.
set "TASK_OUTLINE="
set /p "TASK_OUTLINE=Outline path: "
set "TASK_OUTLINE=%TASK_OUTLINE:"=%"
set "TASK_VEHICLE=%TASK_VEHICLE:"=%"
if not defined TASK_OUTLINE goto no_file
if not exist "%TASK_OUTLINE%" goto no_file
"%TASK_PY%" split_experiments.py import-outline --input "%TASK_OUTLINE%" --vehicle "%TASK_VEHICLE%" --out "%~dp0."
if errorlevel 1 goto failed
echo DONE. Review outlines\vehicle_*.csv, then import the next vehicle or run preview.
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
echo Python 3.9 64-bit not found. Use the existing installed environment.
pause
exit /b 1
:no_file
echo Vehicle or outline file missing. Run again and enter one vehicle and one file.
pause
exit /b 1
:failed
echo Import failed. Keep the first error message for diagnosis.
pause
exit /b 1
