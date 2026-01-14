# 1. Redis 상태 확인
Write-Host "--- Checking Redis Status ---" -ForegroundColor Cyan
$redisCheck = redis-cli ping
if ($redisCheck -eq "PONG") {
    Write-Host "Redis is Running." -ForegroundColor Green
}
else {
    Write-Host "Warning: Redis is NOT running. Please start Redis server first." -ForegroundColor Red
}

# 2. Django Server 실행 (새 창)
Write-Host "--- Starting Django Server ---" -ForegroundColor Cyan
Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "manage.py runserver" -NoNewWindow

# 3. Celery Worker 실행 (현재 창)
# Windows 환경이므로 eventlet 풀을 사용합니다.
Write-Host "--- Starting Celery Worker ---" -ForegroundColor Cyan
Start-Process -FilePath ".\venv\Scripts\celery.exe" -ArgumentList "-A config worker --loglevel=info -P eventlet" -NoNewWindow

Write-Host "--- All systems are launching ---" -ForegroundColor Yellow

# 4. Ngrok 실행 (새 창)
# 외부 접속 URL을 확인하기 위해 새 창에서 실행합니다.
if (Test-Path ".\ngrok.exe") {
    Write-Host "--- Starting Ngrok ---" -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList "-Command & .\ngrok.exe http 8000 --log=stdout > ngrok.log" -WindowStyle Hidden
}
else {
    Write-Host "Warning: ngrok.exe not found in current directory." -ForegroundColor Red
}