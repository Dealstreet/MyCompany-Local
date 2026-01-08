import requests
import json

url = 'http://127.0.0.1:8000/api/webhook/sms/'
data = {
    "secret_key": "OcR5YK8-0_OASYmnUdGWddW-TQem6CX9K7j4OMVoRyo",
    "sms_content": """
    [미래에셋증권]
    종목명: 테스터(005930)
    매매구분: 매수
    체결수량: 10주
    체결단가: 50,000원
    주문번호: 99999
    """,
    "received_at": "2024-01-01 12:00:00"
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
