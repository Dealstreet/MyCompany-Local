import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Organization, Department

# Get the first organization (assuming single tenant usually, or just pick the first)
org = Organization.objects.first()
if not org:
    print("No organization found. Creating one.")
    org = Organization.objects.create(name="My Company", description="Default Org")

print(f"Using Organization: {org.name}")

# Hierarchy Definition
hierarchy = {
    '국내투자본부': ['코스피운용실', 'IPO투자실'],
    '해외투자본부': ['S&P운용실', '나스닥운용실', '배당금융실'],
    '영업지원본부': ['기획실', '재무실']
}

# Clear existing departments (optional, but good for idempotency if we assume this is a reset)
# But user might have data. Let's use get_or_create to be safe.
# Actually, for a clean slate as per user request "manage ... and put current departments", I will ensure they exist.

for hq_name, depts in hierarchy.items():
    hq_obj, created = Department.objects.get_or_create(
        organization=org, 
        name=hq_name, 
        defaults={'parent': None}
    )
    if created:
        print(f"Created HQ: {hq_name}")
    else:
        print(f"Found HQ: {hq_name}")
    
    for dept_name in depts:
        d_obj, d_created = Department.objects.get_or_create(
            organization=org,
            name=dept_name,
            defaults={'parent': hq_obj}
        )
        if d_created:
            print(f"  - Created Dept: {dept_name}")
        else:
            # If it exists but parent is different (e.g. was none), update it
            if d_obj.parent != hq_obj:
                d_obj.parent = hq_obj
                d_obj.save()
                print(f"  - Updated Parent for: {dept_name}")
            else:
                print(f"  - Found Dept: {dept_name}")

print("Department seeding completed.")
