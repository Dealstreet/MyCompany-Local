
path = r'c:\Users\jaeho\Desktop\MyCompany-Local\core\templates\agent_management.html'
try:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Target the specific multi-line string
    target = '{{ agent.position\n                            }}'
    replacement = '{{ agent.position }}'
    
    if target in content:
        print("Found multi-line tag. Fixing...")
        new_content = content.replace(target, replacement)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Fixed and saved.")
    else:
        print("Target string not found directly.")
        # Fallback: Regex or looser search if needed, but let's try exact first
        # Since reading file might have different newline chars, let's normalize
        import re
        # Regex to match {{ agent.position [whitespace] }}
        pattern = re.compile(r'\{\{\s*agent\.position\s*\}\}')
        if pattern.search(content):
             print("Found using regex (already single line or similar).")
        else:
             # Try matching the multi-line with regex
             pattern_multi = re.compile(r'\{\{\s*agent\.position\s*\n\s*\}\}')
             if pattern_multi.search(content):
                 print("Found multi-line using regex. Fixing...")
                 new_content = pattern_multi.sub('{{ agent.position }}', content)
                 with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                 print("Fixed and saved via regex.")
             else:
                 print("Could not find the pattern.")

except Exception as e:
    print(f"Error: {e}")
