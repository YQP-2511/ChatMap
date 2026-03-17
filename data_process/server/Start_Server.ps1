# start_server.ps1
$ErrorActionPreference = "Stop"

Write-Host "正在启动 CSV 管理服务..." -ForegroundColor Green

# Check for Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "检测到 Python: $pythonVersion" -ForegroundColor Gray
} catch {
    Write-Error "未检测到 Python，请先安装 Python。"
    Pause
    Exit
}

# Install dependencies
Write-Host "正在检查并安装依赖..." -ForegroundColor Yellow
try {
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
} catch {
    Write-Error "安装依赖失败，请检查网络或 Python 环境。"
    Pause
    Exit
}

# Start Server
Write-Host "正在启动服务器..." -ForegroundColor Green
Write-Host "请在浏览器中访问: http://127.0.0.1:8000" -ForegroundColor Cyan

# Start the browser automatically
Start-Process "http://127.0.0.1:8000"

# Run uvicorn
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8005
