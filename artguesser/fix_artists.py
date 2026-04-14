import re, csv, io, os, sys
sys.stdout.reconfigure(encoding='utf-8')

# Get existing artist names from ORIGINAL 265 (first 3770 lines)
with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'r', encoding='utf-8') as f:
    all_lines = f.readlines()

# Find the original 265 artists (before our additions)
# The original file was 3770 lines
original_content = ''.join(all_lines[:3770])
existing_names = set(re.findall(r'"([^"]+)":\s*\{', original_content))
print(f"Existing artists in original: {len(existing_names)}")

# Parse CSV blocks
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

def esc_dq(s):
    """Escape for use in double-quoted Python strings"""
    if not s:
        return ''
    s = s.strip()
    # Replace backslash first, then double quotes
    s = s.replace('\\', r'\\')
    s = s.replace('"', r'\"')
    return s

entries = []
for row in new_artists:
    name = row.get('Name', '').strip()
    year_born = parse_year(row.get('YearBorn', ''))
    year_died = parse_year(row.get('YearDied', ''))

    nationality = esc_dq(row.get('Nationality', ''))
    medium = esc_dq(row.get('Medium', ''))
    short_bio = esc_dq(row.get('ShortBio', ''))
    years_active = esc_dq(row.get('YearsActive', ''))
    main_movement = esc_dq(row.get('MainMovementOrPeriod', ''))
    sub_movements = esc_dq(row.get('SubMovements', ''))
    era_category = esc_dq(row.get('ActiveCategory', ''))
    image_search_term = esc_dq(row.get('ImageSearchTerm', ''))

    name_esc = name.replace('\\', r'\\').replace('"', r'\"')
    year_born_str = str(year_born) if year_born is not None else 'None'
    year_died_str = str(year_died) if year_died is not None else 'None'

    lines = [
        f'    "{name_esc}": {{',
        f'        "nationality": "{nationality}",',
        f'        "year_born": {year_born_str},',
        f'        "year_died": {year_died_str},',
        f'        "medium": "{medium}",',
        f'        "short_bio": "{short_bio}",',
        f'        "years_active": "{years_active}",',
        f'        "main_movement": "{main_movement}",',
        f'        "sub_movements": "{sub_movements}",',
        f'        "era_category": "{era_category}",',
        f'        "image_search_term": "{image_search_term}",',
        f'    }},',
    ]
    entries.append('\n'.join(lines))

new_block = '\n'.join(entries)

# Strip trailing } from original content and append new entries
base = original_content.rstrip()[:-1]  # remove final }
updated = base + new_block + '\n}'

with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'w', encoding='utf-8') as f:
    f.write(updated)

print("Written to artists.py")

# Verify syntax
with open(r"c:/Users/james/redbot-cogs/artguesser/artists.py", 'r', encoding='utf-8') as f:
    final = f.read()

try:
    compile(final, 'artists.py', 'exec')
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error at line {e.lineno}: {e.msg}")
    lines = final.split('\n')
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        print(f"  {i+1}: {repr(lines[i])}")

all_names = re.findall(r'"([^"]+)":\s*\{', final)
print(f"Total artists: {len(all_names)}")
