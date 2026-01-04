# 1. Redis 상태 확인
Write-Host "--- Checking Redis Status ---" -ForegroundColor Cyan
$redisCheck = redis-cli ping
if ($redisCheck -eq "PONG") {
    Write-Host "Redis is Running." -ForegroundColor Green
} else {
    Write-Host "Warning: Redis is NOT running. Please start Redis server first." -ForegroundColor Red
}

# 2. Django Server 실행 (새 창)
Write-Host "--- Starting Django Server ---" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\activate; Write-Host 'Starting Django Server...'; python manage.py runserver"

# 3. Celery Worker 실행 (새 창)
# Windows 환경이므로 eventlet 풀을 사용합니다.
Write-Host "--- Starting Celery Worker ---" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\venv\Scripts\activate; Write-Host 'Starting Celery Worker...'; celery -A core worker --loglevel=info -P eventlet"

Write-Host "--- All systems are launching ---" -ForegroundColor Yellow