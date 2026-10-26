@echo off
title TikTok Auto Farm & AI Video Engine
color 0b

echo ========================================================
echo   TIKTOK BETA AUTO FARM & AI VIDEO ENGINE (GPM LOGIN)
echo ========================================================
echo.

REM Kiem tra moi truong Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python tren may tinh cua ban!
    echo Vui long cai dat Python 3.10 tro len va tich chon "Add Python to PATH".
    pause
    exit /b
)

echo [1/3] Kiem tra va cai dat thu vien phu thuoc...
python -m pip install -r requirements.txt --quiet

echo [2/3] Khoi tao co so du lieu Local SQLite...
python -c "from backend.database import init_db; init_db()"

echo [3/3] Dang khoi dong Desktop App va mo Dashboard...
echo.
python main.py

pause
