
import os

file_path = 'core/views.py'
target_line_part = "return JsonResponse({'error': str(e), 'quotes': []})"

with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

cutoff = -1
for i, line in enumerate(lines):
    if target_line_part in line:
        cutoff = i
        break

if cutoff != -1:
    print(f"Truncating file at line {cutoff+1}")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines[:cutoff+1])
        f.write("\n")
else:
    print("Target line not found, no truncation performed.")
