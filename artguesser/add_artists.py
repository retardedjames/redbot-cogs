import re, csv, io, os, sys
sys.stdout.reconfigure(encoding='utf-8')

# Step 1: Read original artists.py
# Original file: lines 0-3768 = content (last is "    },\n" closing Giovanni Bellini)
# Line 3769 was "}" (closing ARTISTS dict) but is now corrupted
# So take lines[:3769] as the original content (everything before closing })
with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

original_lines = all_lines[:3769]  # lines 0-3768, ending with "    },\n"
existing_names = set(re.findall(r'"([^"]+)":\s*\{', ''.join(original_lines)))
print(f"Existing artists: {len(existing_names)}")

# Step 2: Parse all CSV blocks from the two/ folder
folder = r"c:/Users/james/redbot-cogs/artguesser/two"
new_artists = []
seen = set()

for fname in sorted(os.listdir(folder)):
    fpath = os.path.join(folder, fname)
    with open(fpath, 'r', encoding='cp1252') as f:
        content = f.read()
    blocks = re.findall(r'```csv\n(.*?)```', content, re.DOTALL)
    for block in blocks:
        reader = csv.DictReader(io.StringIO(block.strip()))
        for row in reader:
            name = row.get('Name', '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            if name not in existing_names:
                new_artists.append(row)

print(f"New artists to add: {len(new_artists)}")

def parse_year(val):
    if not val or not val.strip():
        return None
    m = re.search(r'\d{4}', val)
    return int(m.group()) if m else None

def py_str(s):
    """Return a Python repr of a string, using double quotes."""
    if not s:
        s = ''
    s = s.strip()
    # Manually escape for a double-quoted Python string
    result = ''
    for ch in s:
        if ch == '\\':
            result += '\\\\'
        elif ch == '"':
            result += '\\"'
        elif ch == '\n':
            result += '\\n'
        elif ch == '\r':
            result += '\\r'
        else:
            result += ch
    return '"' + result + '"'

# Step 3: Build new entries as a list of lines
new_lines = []
for row in new_artists:
    name = row.get('Name', '').strip()
    year_born = parse_year(row.get('YearBorn', ''))
    year_died = parse_year(row.get('YearDied', ''))

    nationality = py_str(row.get('Nationality', ''))
    medium = py_str(row.get('Medium', ''))
    short_bio = py_str(row.get('ShortBio', ''))
    years_active = py_str(row.get('YearsActive', ''))
    main_movement = py_str(row.get('MainMovementOrPeriod', ''))
    sub_movements = py_str(row.get('SubMovements', ''))
    era_category = py_str(row.get('ActiveCategory', ''))
    image_search_term = py_str(row.get('ImageSearchTerm', ''))

    name_safe = name.replace('\\', '\\\\').replace('"', '\\"')
    year_born_str = str(year_born) if year_born is not None else 'None'
    year_died_str = str(year_died) if year_died is not None else 'None'

    new_lines.append('    ' + '"' + name_safe + '": {')
    new_lines.append('        "nationality": ' + nationality + ',')
    new_lines.append('        "year_born": ' + year_born_str + ',')
    new_lines.append('        "year_died": ' + year_died_str + ',')
    new_lines.append('        "medium": ' + medium + ',')
    new_lines.append('        "short_bio": ' + short_bio + ',')
    new_lines.append('        "years_active": ' + years_active + ',')
    new_lines.append('        "main_movement": ' + main_movement + ',')
    new_lines.append('        "sub_movements": ' + sub_movements + ',')
    new_lines.append('        "era_category": ' + era_category + ',')
    new_lines.append('        "image_search_term": ' + image_search_term + ',')
    new_lines.append('    },')

# Step 4: Reconstruct artists.py
# Original last line should be '}' (closing ARTISTS dict)
# Strip it and add new entries, then close
assert original_lines[-1].strip() == '},', f"Unexpected last line: {repr(original_lines[-1])}"

output_lines = list(original_lines)  # all original content (ends with "    },\n")
output_lines += [line + '\n' for line in new_lines]
output_lines.append('}\n')

with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print("Written successfully.")

# Step 5: Verify
with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'r', encoding='utf-8') as f:
    final = f.read()

try:
    compile(final, 'artists.py', 'exec')
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error at line {e.lineno}: {e.msg}")
    lines = final.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+3)):
        print(f"  {i+1}: {repr(lines[i])}")

all_names = re.findall(r'"([^"]+)":\s*\{', final)
print(f"Total artists: {len(all_names)}")
