import os

file_path = r'c:\Users\jaeho\Desktop\MyCompany-Local\core\templates\account_management.html'

try:
    with open(file_path, 'rb') as f:
        content = f.read()
        print(f"File size: {len(content)} bytes")
        print(f"First 100 bytes: {content[:100]}")
        
        # Check for specific suspicious bytes
        # 123 is '{'
        # look for matches of {{
        import re
        text = content.decode('utf-8', errors='replace')
        
        # Find fragments that look like template tags
        matches = re.findall(r'(\{\{\s*account\.account_number\s*\}\})', text)
        print(f"Found {len(matches)} matches for account_number tag.")
        for m in matches:
            print(f"Match: '{m}'")
            # Print hex of the match
            print(f"Hex: {' '.join(hex(ord(c)) for c in m)}")

except Exception as e:
    print(f"Error: {e}")
