
path = r'c:\Users\jaeho\Desktop\MyCompany-Local\core\templates\index.html'
try:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'favorites.count>=' in content:
        print("Found error string. Fixing...")
        new_content = content.replace('favorites.count>=', 'favorites.count >=')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Fixed and saved.")
    else:
        print("Error string not found. It might have been fixed or content is different.")
        # Debugging: check for nearby strings
        idx = content.find('favorites.count')
        if idx != -1:
            print(f"Context around favorites.count: '{content[idx:idx+20]}'")

except Exception as e:
    print(f"Error: {e}")
