$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectDirectory ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    throw "Virtual environment not found. Follow the Windows setup in README.md."
}

Set-Location $ProjectDirectory
& $PythonPath "app.py"

