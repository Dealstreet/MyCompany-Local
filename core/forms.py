from django import forms
from .models import Agent, Department, User, Organization, PortfolioDisclosure

class AgentForm(forms.ModelForm):
    class Meta:
        model = Agent
        fields = ['organization', 'name', 'department_obj', 'position', 'role', 'persona', 'model_name', 'profile_image', 'employee_id']
        widgets = {
            'organization': forms.HiddenInput(),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '이름을 입력하세요'}),
            'department_obj': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: 팀장, 연구원'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: 백엔드 개발, 재무 분석'}),
            'persona': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': '이 직원의 행동 요령이나 성격을 정의하세요.'}),
            'model_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: gpt-4o'}),
            'profile_image': forms.FileInput(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '미입력 시 자동 생성'}),
        }
        labels = {
            'department_obj': '소속 부서',
        }

# [New] SaaS Forms
class UserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['last_name', 'first_name', 'birth_date', 'email']
        widgets = {
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '성'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '이름'}),
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': '이메일'}),
        }
        labels = {
            'last_name': '성',
            'first_name': '이름',
            'birth_date': '생년월일',
            'email': '이메일',
        }

class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'description', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
        }

