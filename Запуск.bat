@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Хранитель приключений

where py >nul 2>&1 && (set "PY=py -3")
if not defined PY where python >nul 2>&1 && (set "PY=python")
if not defined PY (
  echo Нужен Python.
  echo Скачайте его с https://www.python.org/downloads/
  echo При установке поставьте галочку Add python.exe to PATH.
  echo Потом запустите этот файл ещё раз.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Первый запуск. Ставлю библиотеки, подождите несколько минут.
  %PY% -m venv .venv
  if errorlevel 1 goto fail
)

".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto fail

if exist ".env" goto run
echo.
echo Вставьте токен бота от BotFather и нажмите Enter.
set /p TOKEN=Токен:
>".env" echo TELEGRAM_BOT_TOKEN=%TOKEN%
>>".env" echo ADMIN_IDS=

:run

".venv\Scripts\python.exe" -m khranitel
if errorlevel 2 goto badtoken
echo.
echo Бот остановился.
pause
exit /b 0

:badtoken
echo.
echo Вставьте новый токен и нажмите Enter.
set /p TOKEN=Токен:
>".env" echo TELEGRAM_BOT_TOKEN=%TOKEN%
>>".env" echo ADMIN_IDS=
goto run

:fail
echo.
echo Не получилось запустить. Сфотографируйте это окно и пришлите тому, кто дал вам бота.
pause
exit /b 1
