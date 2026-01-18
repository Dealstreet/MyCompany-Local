from django import forms
from django.contrib.auth.forms import UserCreationForm # [New]
from .models import Agent, Department, User, Organization, Stock

class AgentForm(forms.ModelForm):
    managed_stocks = forms.ModelMultipleChoiceField(
        queryset=Stock.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="담당 종목",
        help_text="종목 관리에서 추가된 종목만 선택할 수 있습니다."
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter stocks by organization if possible, currently Stock doesn't have Organization field?
        # Checking Stock model... it has no organization field? 
        # Wait, Stock is usually global or shared? Or did I miss it?
        # Model definition showed: Stock(name, code, ..., agent=ForeignKey)
        # It seems Stock is shared or implicit. 
        # However, to be safe, I will show ALL stocks for now as per "Stock Management" context.
        self.fields['managed_stocks'].queryset = Stock.objects.all().order_by('name')
        
        if self.instance.pk:
            self.fields['managed_stocks'].initial = self.instance.managed_stocks.all()

    def save(self, commit=True):
        agent = super().save(commit=commit)
        if commit:
            # Handle reverse relationship
            new_stocks = self.cleaned_data.get('managed_stocks', [])
            
            # 1. Clear agent from stocks that were previously managed but not anymore
            # "managed_stocks" related name on Stock model
            current_stocks = agent.managed_stocks.all()
            for stock in current_stocks:
                if stock not in new_stocks:
                    stock.agent = None
                    stock.save()
            
            # 2. Set agent for newly selected stocks
            for stock in new_stocks:
                stock.agent = agent
                stock.save()
        return agent

# [New] SaaS Forms
class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'last_name', 'first_name'] # Password handled by UserCreationForm
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '아이디'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': '이메일'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '성'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '이름'}),
        }
        labels = {
            'username': '아이디',
            'email': '이메일',
            'last_name': '성',
            'first_name': '이름',
        }

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

