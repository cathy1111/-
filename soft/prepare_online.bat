@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0.."
call :find_python
if not defined TASK_PY goto no_python
echo Preparing a complete offline package. Internet connection is required here.
echo Use C:\pro to avoid non-ASCII model path issues on Windows.
"%TASK_PY%" "%~dp0offline_bundle.py" prepare
if errorlevel 1 goto failed
echo DONE. Copy offline-package.zip to the offline computer.
pause
exit /b 0
:find_python
set "TASK_PY="
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
:no_python
echo ERROR: Python 3.9 64-bit not found. Use the PC where installation already succeeded.
pause
exit /b 1
:failed
echo FAILED. No valid new offline ZIP has been generated. Send the first error for diagnosis.
pause
exit /b 1
