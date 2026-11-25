@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo           SHORTS MAKER AI - GITHUB DEPLOYMENT HELPER
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/4] Checking Git status...
git status --short

echo.
echo [2/4] Adding files according to .gitignore (Secrets are protected)...
git add .

echo.
set /p COMMIT_MSG="Enter commit message (or press ENTER for default): "
if "%COMMIT_MSG%"=="" (
    set COMMIT_MSG="Enhance Shorts Maker AI: Razorpay subscription integration, Docker, and cloud readiness"
)

echo.
echo [3/4] Creating commit...
git commit -m "%COMMIT_MSG%"

echo.
echo [4/4] Pushing to GitHub (origin main)...
git push origin main

echo.
echo ============================================================
echo                     DEPLOYMENT FINISHED!
echo ============================================================
pause
