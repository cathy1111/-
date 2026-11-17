@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "TASK_SOFT=%~dp0"
cd /d "%TASK_SOFT%.."
echo Online dependency repair - uses PyPI for missing packages
echo Internet connection is required to download missing dependencies.
echo Keep this file in pro\soft. Do not run inside a ZIP file.
echo.
if not exist "%TASK_SOFT%requirements-win.txt" goto missing
if not exist "%TASK_SOFT%wheels\paddlepaddle-2.6.1-cp39-cp39-win_amd64.whl" goto missing

echo [1/5] Checking Visual C++ runtime...
if not exist "%TASK_SOFT%vcredist\vc_redist.x64.exe" goto no_vc
"%TASK_SOFT%vcredist\vc_redist.x64.exe" /install /quiet /norestart
set "TASK_RC=%ERRORLEVEL%"
if "%TASK_RC%"=="0" goto vc_done
if "%TASK_RC%"=="1638" goto vc_done
if "%TASK_RC%"=="3010" goto vc_done
echo WARNING: VC++ installer returned %TASK_RC%. DLL imports may fail.
goto vc_done
:no_vc
echo WARNING: VC++ installer missing. Existing runtime may still work.
:vc_done

echo [2/5] Finding Python 3.9 64-bit...
call :find_python
if defined TASK_PY goto python_ready
if not exist "%TASK_SOFT%python\python-3.9.13-amd64.exe" goto missing
echo Complete the Python installation wizard, then return to this window.
start /wait "" "%TASK_SOFT%python\python-3.9.13-amd64.exe" InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
call :find_python
if not defined TASK_PY goto no_python
:python_ready
echo Using: "%TASK_PY%"
"%TASK_PY%" -V

echo [3/5] Installing dependencies; missing packages will be downloaded...
"%TASK_PY%" -m pip --version >nul 2>&1
if errorlevel 1 "%TASK_PY%" -m ensurepip
if errorlevel 1 goto failed
"%TASK_PY%" -m pip install --index-url=https://pypi.org/simple --find-links="%TASK_SOFT%wheels" "%TASK_SOFT%wheels\paddlepaddle-2.6.1-cp39-cp39-win_amd64.whl"
if errorlevel 1 goto failed
"%TASK_PY%" -m pip install --index-url=https://pypi.org/simple --find-links="%TASK_SOFT%wheels" -r "%TASK_SOFT%requirements-win.txt"
if errorlevel 1 goto failed

echo [4/5] Checking local OCR model files...
call :check_model ch_PP-OCRv4_det_infer det\ch\ch_PP-OCRv4_det_infer
if errorlevel 1 goto model_missing
call :check_model ch_PP-OCRv4_rec_infer rec\ch\ch_PP-OCRv4_rec_infer
if errorlevel 1 goto model_missing
call :check_model ch_ppocr_mobile_v2.0_cls_infer cls\ch_ppocr_mobile_v2.0_cls_infer
if errorlevel 1 goto model_missing

echo [5/5] Checking Python imports...
"%TASK_PY%" -c "import fitz, paddle; from paddleocr import PaddleOCR; print('Dependency imports OK')"
if errorlevel 1 goto failed
echo.
echo SUCCESS: dependency installation and model-file checks passed.
echo Open pro\run_preview.bat to recognize a PDF.
echo OCR model initialization will be checked when recognition starts.
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
:check_model
if exist "%TASK_SOFT%paddleocr_models\%~1\inference.pdmodel" if exist "%TASK_SOFT%paddleocr_models\%~1\inference.pdiparams" exit /b 0
if exist "%TASK_SOFT%paddleocr_models\from_cache\%~2\inference.pdmodel" if exist "%TASK_SOFT%paddleocr_models\from_cache\%~2\inference.pdiparams" exit /b 0
if exist "%USERPROFILE%\.paddleocr\whl\%~2\inference.pdmodel" if exist "%USERPROFILE%\.paddleocr\whl\%~2\inference.pdiparams" exit /b 0
echo Missing model: %~1
exit /b 1
:missing
echo ERROR: required package files are missing.
echo Extract the original full pro.zip, then apply this repair package.
echo Keep python, vcredist, wheels and paddleocr_models inside soft.
pause
exit /b 1
:no_python
echo ERROR: Python 3.9 64-bit was not found after installation.
echo Close this window and run this installer again.
pause
exit /b 1
:model_missing
echo ERROR: OCR model files are incomplete. Screenshot the model folder.
pause
exit /b 1
:failed
echo.
echo FAILED: installation stopped. Do not treat this as a successful install.
echo Take a screenshot including the first ERROR above and send it for diagnosis.
pause
exit /b 1
