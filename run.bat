@echo off
setlocal enabledelayedexpansion

:: Default values
set "MODE=development"
set "STORAGE_TYPE=file"
set "STORAGE_PATH=./cache"
set "PORT=15151"
set "HOST=0.0.0.0"
set "LOG_LEVEL=INFO"
set "WORKERS=4"

:: Parse command line arguments
:parse_args
if "%~1"=="" goto :done_parsing
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="--prod" set "MODE=production" & shift & goto :parse_args
if /i "%~1"=="--dev" set "MODE=development" & shift & goto :parse_args
if /i "%~1"=="--port" set "PORT=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--host" set "HOST=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--storage" set "STORAGE_TYPE=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--path" set "STORAGE_PATH=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--log-level" set "LOG_LEVEL=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--workers" set "WORKERS=%~2" & shift & shift & goto :parse_args
if /i "%~1"=="--docker" goto :run_docker
if /i "%~1"=="--docker-dev" goto :run_docker_dev
echo Unknown parameter: %~1
goto :show_help
:done_parsing

:: Show help
:show_help
if "%~1"=="--help" (
    echo Usage: run.bat [options]
    echo.
    echo Options:
    echo   --help          Show this help message
    echo   --prod          Run in production mode
    echo   --dev           Run in development mode ^(default^)
    echo   --port ^<port^>   Set port number ^(default: 15151^)
    echo   --host ^<host^>   Set host address ^(default: 0.0.0.0^)
    echo   --storage ^<type^> Set storage type ^(file/minio^)
    echo   --path ^<path^>   Set storage path for file storage
    echo   --log-level ^<level^> Set log level ^(DEBUG/INFO/WARNING/ERROR^)
    echo   --workers ^<num^> Set number of workers ^(default: 4^)
    echo   --docker        Run using Docker
    echo   --docker-dev    Run using Docker in development mode
    echo.
    echo Examples:
    echo   run.bat --dev --port 8080
    echo   run.bat --prod --storage minio
    echo   run.bat --docker
    exit /b 0
)

:: Check Python installation
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Python is not installed or not in PATH
    exit /b 1
)

:: Create and activate virtual environment if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo Failed to create virtual environment
        exit /b 1
    )
)

:: Activate virtual environment
call .venv\Scripts\activate

:: Install requirements if needed
if not exist .venv\Scripts\uvicorn.exe (
    echo Installing requirements...
    pip install -r requirements.txt
    if !ERRORLEVEL! neq 0 (
        echo Failed to install requirements
        exit /b 1
    )
)

:: Create necessary directories
if not exist "%STORAGE_PATH%" (
    mkdir "%STORAGE_PATH%"
)
if not exist "logs" (
    mkdir "logs"
)

:: Set environment variables
set "VCPKG_HOST=%HOST%"
set "VCPKG_PORT=%PORT%"
set "VCPKG_STORAGE_TYPE=%STORAGE_TYPE%"
set "VCPKG_STORAGE_PATH=%STORAGE_PATH%"
set "VCPKG_LOG_LEVEL=%LOG_LEVEL%"
set "VCPKG_WORKERS=%WORKERS%"

:: Run the application
if "%MODE%"=="development" (
    echo Starting vcpkg-harbor in development mode...
    python -m uvicorn main:app --host %HOST% --port %PORT% --reload --log-level debug
) else (
    echo Starting vcpkg-harbor in production mode...
    python main.py
)

goto :eof

:run_docker
echo Starting vcpkg-harbor using Docker...
docker compose up -d
goto :eof

:run_docker_dev
echo Starting vcpkg-harbor using Docker in development mode...
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
goto :eof

endlocal