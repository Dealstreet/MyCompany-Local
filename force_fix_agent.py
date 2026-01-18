
path = r'c:\Users\jaeho\Desktop\MyCompany-Local\core\templates\agent_management.html'
try:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        # Check for the specific split line pattern
        # Line 33: ... {{ agent.position
        # Line 34:       }} ...
        
        if '{{ agent.position' in line and '}}' not in line:
            # Found the start of the split tag
            # Check next line for closure
            if i + 1 < len(lines) and '}}' in lines[i+1]:
                # Merge them
                combined = line.strip() + ' }}</span></h5>\n'
                # Use regex to clean up if needed, but exact replacement is safer for this specific case
                # The original line has <h5...> ... {{ agent.position
                # We want to replace it with valid single line.
                
                # Reconstruct the line accurately
                # Existing Line 33 usually looks like: <h5 ...> ... {{ agent.position\n
                # We want: <h5 ...> ... {{ agent.position }}</span></h5>\n
                
                # Let's just find the part before {{ and append the correct suffix
                pre_part = line.split('{{ agent.position')[0]
                new_line = f'{pre_part}{{{{ agent.position }}}}</span></h5>\n'
                new_lines.append(new_line)
                skip_next = True # Skip the next line which contains only "}}" and span close
                print(f"Fixed split tag at line {i+1}")
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("File saved.")

except Exception as e:
    print(f"Error: {e}")
