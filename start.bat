@echo off
setlocal
cd /d "%~dp0"

if not exist "env_name\Scripts\python.exe" (
    echo [start.bat] Virtual environment not found. Run: uv sync --extra dev
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [start.bat] Created .env from .env.example
)

if not exist "secrets\private_key.pem" (
    echo [start.bat] Generating JWT key pair...
    "env_name\Scripts\python.exe" -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; key = rsa.generate_private_key(public_exponent=65537, key_size=2048); open('secrets/private_key.pem','wb').write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())); open('secrets/public_key.pem','wb').write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))"
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo [start.bat] Freeing port 8000 - stopping PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [start.bat] Starting PawGuard API on http://localhost:8000 ...
"env_name\Scripts\uvicorn.exe" pawguard.main:app --host 0.0.0.0 --port 8000
