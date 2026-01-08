# ngrok을 실행하여 로컬 8000번 포트를 외부로 노출합니다.
Write-Host "--- Starting ngrok Tunnel ---" -ForegroundColor Cyan
Write-Host "잠시 후 나타나는 'Forwarding' 주소(https://....ngrok-free.app)를 복사해서 아이폰 단축어에 넣으세요." -ForegroundColor Yellow
.\ngrok.exe http 8000
