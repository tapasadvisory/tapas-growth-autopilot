$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv")) {
  py -3 -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env. Add the Gemini key, encryption key and provider app credentials."
  & ".\.venv\Scripts\python.exe" -c "from cryptography.fernet import Fernet; print('TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
  Write-Host "Copy the generated TOKEN_ENCRYPTION_KEY into .env. Then configure OAuth callback URLs."
  exit 0
}

& ".\.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
