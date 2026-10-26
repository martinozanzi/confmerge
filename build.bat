@echo off
rem ============================================================================
rem  ConfMerge - build per Windows 10/11
rem  Uso:  build.bat [onefile|onedir|all]      (predefinito: all)
rem  Richiede solo Python 3.11-3.14 (python.org). Crea l'ambiente virtuale, installa
rem  le dipendenze, scarica ffmpeg/ffprobe statici (se mancano in bin\) e produce:
rem    dist\onefile\ConfMerge.exe     (un solo file, con splash screen)
rem    dist\onedir\ConfMerge\         (cartella: avvio piu' veloce)
rem ============================================================================
setlocal enableextensions
cd /d "%~dp0"
set TARGET=%1
if "%TARGET%"=="" set TARGET=all

rem --- Python: sceglie la versione piu' recente supportata (3.14 ... 3.11)
set PYEXE=
for %%V in (3.14 3.13 3.12 3.11) do if not defined PYEXE (py -%%V -c "import sys" >nul 2>nul && set PYEXE=py -%%V)
if not defined PYEXE (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,14) else 1)" >nul 2>nul && set PYEXE=python
)
if not defined PYEXE (
  echo ERRORE: serve Python 3.11, 3.12, 3.13 o 3.14 ^(trovate: versioni non supportate o nessuna^).
  echo Installalo da https://www.python.org/downloads/ ^(64 bit, spunta "Add python.exe to PATH"^).
  exit /b 1
)
echo Uso: %PYEXE%

rem --- ambiente virtuale e dipendenze
if not exist .venv\Scripts\python.exe (
  echo [1/5] Creazione dell'ambiente virtuale...
  %PYEXE% -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat
python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,14) else 1)" || (
  echo ERRORE: l'ambiente .venv usa una versione di Python non supportata. Cancella la cartella .venv e rilancia.
  exit /b 1)
echo [2/5] Installazione delle dipendenze...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || exit /b 1

rem --- ffmpeg statico (build GPL con x264). Per usare un'altra build: mettila in bin\ prima di lanciare.
if not exist bin mkdir bin
if not exist bin\ffmpeg.exe (
  echo [3/5] Download di ffmpeg statico...
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\get_ffmpeg.ps1 -Url "%FFMPEG_URL%"
  if errorlevel 1 (
    echo ERRORE: download di ffmpeg non riuscito. Copia ffmpeg.exe e ffprobe.exe in bin\ e rilancia.
    exit /b 1
  )
) else (
  echo [3/5] ffmpeg trovato in bin\ - uso quello.
)
bin\ffmpeg.exe -version > bin\ffmpeg-version.txt

rem --- asset (splash e icona)
if not exist assets\splash.png python tools\make_assets.py

rem --- opzioni comuni PyInstaller
set COMMON=--noconfirm --clean --windowed --name ConfMerge --icon assets\icon.ico --paths src ^
 --add-binary "bin\ffmpeg.exe;bin" --add-binary "bin\ffprobe.exe;bin" ^
 --add-data "src\confmerge\resources;confmerge\resources" ^
 --add-data "THIRD-PARTY-NOTICES.txt;." --add-data "LICENSE;." --add-data "bin\ffmpeg-version.txt;bin" ^
 --exclude-module tkinter.test --exclude-module matplotlib --exclude-module PySide6.QtWebEngineCore

rem splash: richiede tkinter (incluso nell'installer di python.org)
set SPLASH=--splash assets\splash.png
python -c "import tkinter" 2>nul || (set SPLASH= & echo ATTENZIONE: tkinter non disponibile - build senza splash screen.)

if /i "%TARGET%"=="onedir" goto onedir
echo [4/5] Build onefile...
python -m PyInstaller %COMMON% %SPLASH% --onefile --distpath dist\onefile --workpath build\onefile --specpath build run_confmerge.py || exit /b 1
copy /y THIRD-PARTY-NOTICES.txt dist\onefile\ >nul
copy /y LICENSE dist\onefile\LICENSE.txt >nul
if /i "%TARGET%"=="onefile" goto done

:onedir
echo [5/5] Build onedir...
python -m PyInstaller %COMMON% --onedir --distpath dist\onedir --workpath build\onedir --specpath build run_confmerge.py || exit /b 1
copy /y THIRD-PARTY-NOTICES.txt dist\onedir\ConfMerge\ >nul
copy /y LICENSE dist\onedir\ConfMerge\LICENSE.txt >nul

:done
echo.
echo Fatto. Risultati in dist\
exit /b 0
