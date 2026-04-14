import re, csv, io, os, sys
sys.stdout.reconfigure(encoding='utf-8')

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
            new_artists.append(row)

# Just show first entry
row = new_artists[0]
name = row.get('Name', '').strip()
lines = [
    '    "' + name + '": {',
    '        "nationality": "test",',
    '    },',
]
entry = '\n'.join(lines)
print("Entry repr:", repr(entry))
print("---")
print(entry)
print("---")
print(f"Entry 0 first line: {repr(entry.split(chr(10))[0])}")
