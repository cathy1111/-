@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call :find_python
if not defined TASK_PY goto missing_python
if not exist "split_experiments.py" goto missing_script
echo Export from the reviewed preview.csv; OCR will not overwrite your edits.
echo Drag the SAME original PDF used for preview, then press Enter.
set "TASK_PDF="
set /p "TASK_PDF=PDF path: "
set "TASK_PDF=%TASK_PDF:"=%"
if not defined TASK_PDF goto no_file
if not exist "%TASK_PDF%" goto no_file
"%TASK_PY%" split_experiments.py split --input "%TASK_PDF%" --out "%~dp0out" --version V011 --top-ratio 0.4
if errorlevel 1 goto failed
echo DONE. Open the out folder for results.
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
echo Python 3.9 64-bit not found. Run soft\install_offline.bat first.
pause
exit /b 1
:missing_script
echo Place this launcher in the pro folder beside split_experiments.py.
pause
exit /b 1
:no_file
echo PDF file not found. Run again and drag one PDF into this window.
pause
exit /b 1
:failed
echo FAILED. Take a screenshot including the first error above.
pause
exit /b 1
