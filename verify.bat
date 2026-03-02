@echo off
REM Quick verification script for PLM setup

echo ==========================================
echo PLM Setup Verification
echo ==========================================
echo.

python verify_setup.py

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo Ready to use! Next steps:
    echo ==========================================
    echo.
    echo 1. Review topics in configs\config.yaml
    echo 2. Run: python main.py validate
    echo 3. Run: python main.py generate
    echo.
    echo See QUICKSTART.md for details
    echo.
) else (
    echo.
    echo ==========================================
    echo Setup incomplete - please fix issues above
    echo ==========================================
    echo.
    echo See INSTALL.md for help
    echo.
)

pause
