# config/celery.py
import os
from celery import Celery

# Django 설정을 불러옵니다.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Celery 앱(직원)을 생성합니다.
app = Celery('config')

# Django 설정 파일에서 'CELERY_'로 시작하는 설정을 다 가져옵니다.
app.config_from_object('django.conf:settings', namespace='CELERY')

# 자동으로 tasks.py(업무 매뉴얼)를 찾아서 등록합니다.
app.autodiscover_tasks()