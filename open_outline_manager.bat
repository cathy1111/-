@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
call :find_python
if not defined TASK_PY goto missing_python
if not exist "%~dp0outline_manager.py" goto missing_files
if not exist "%~dp0logs" mkdir "%~dp0logs"
"%TASK_PY%" -c "import tkinter; tkinter.Tcl()" >"%~dp0logs\outline_manager_startup.log" 2>&1
if errorlevel 1 goto missing_tk
set "TASK_PYW=%TASK_PY:python.exe=pythonw.exe%"
if exist "%TASK_PYW%" goto windowed
"%TASK_PY%" "%~dp0outline_manager.py"
if errorlevel 1 goto failed
exit /b 0
:windowed
start "" "%TASK_PYW%" "%~dp0outline_manager.py"
if errorlevel 1 goto failed
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
echo Python 3.9 64-bit not found. Use the original installed environment.
pause
exit /b 1
:missing_files
echo Missing outline_manager.py. Merge ALL update files into C:\pro.
pause
exit /b 1
:missing_tk
echo The Python tcl/tk component is missing or damaged.
echo Run the bundled Python installer, choose Modify, and enable tcl/tk.
echo Diagnostic log: logs\outline_manager_startup.log
type "%~dp0logs\outline_manager_startup.log"
pause
exit /b 1
:failed
echo Cannot start the outline manager. Check logs\outline_manager.log.
pause
exit /b 1
