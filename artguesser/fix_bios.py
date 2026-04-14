"""
Strip artist names from their own bio fields in artists.py.
Rules:
- Remove full name, first name, last name (and any meaningful sub-part)
- Skip common particles: de, van, la, le, el, al, bin, ibn, von, du, del, di, da, los, las, the
- If after removal the bio starts with a conjugated verb, prepend "They"
- Do NOT rewrite sentences - just remove the name tokens
"""
import re
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PARTICLES = {'de', 'van', 'la', 'le', 'el', 'al', 'bin', 'ibn', 'von', 'du', 'del', 'di', 'da', 'los', 'las', 'the', 'of', 'mac', 'mc'}
VERB_STARTERS = {
    'was', 'is', 'became', 'had', 'has', 'created', 'worked', 'lived', 'painted',
    'born', 'died', 'studied', 'developed', 'made', 'produced', 'spent', 'began',
    'started', 'emerged', 'trained', 'explored', 'established', 'gained', 'achieved',
    'pioneered', 'combined', 'blended', 'moved', 'fled', 'returned', 'focused',
    'used', 'drew', 'built', 'left', 'taught', 'influenced', 'collaborated',
    'received', 'won', 'exhibited', 'settled', 'joined', 'formed', 'founded',
    'dedicated', 'designed', 'worked', 'served', 'helped', 'created', 'produced',
    'developed', 'introduced', 'brought', 'transformed', 'shaped', 'led', 'led',
    'co-founded', 'cofounded', 'apprenticed',
}


def get_name_tokens(artist_name):
    """Return list of name strings to strip, longest first."""
    parts = artist_name.split()
    tokens = set()
    tokens.add(artist_name)  # full name

    # Add meaningful parts (not particles, length > 2)
    for part in parts:
        clean = part.strip('-').strip("'")
        if len(clean) > 2 and clean.lower() not in PARTICLES:
            tokens.add(clean)

    # Also add hyphenated sub-parts (e.g. "Cheng-po" → "Cheng", "po")
    for part in parts:
        if '-' in part:
            subparts = part.split('-')
            for sp in subparts:
                if len(sp) > 2 and sp.lower() not in PARTICLES:
                    tokens.add(sp)

    # Sort longest first to avoid partial replacements
    return sorted(tokens, key=len, reverse=True)


def strip_name_from_bio(artist_name, bio):
    """Remove artist name tokens from bio text."""
    tokens = get_name_tokens(artist_name)
    new_bio = bio
    for token in tokens:
        # Word-boundary aware replacement (case-insensitive)
        pattern = r'(?<!\w)' + re.escape(token) + r'(?!\w)'
        new_bio = re.sub(pattern, '', new_bio, flags=re.IGNORECASE)

    # Clean up: collapse multiple spaces, fix space before comma/period
    new_bio = re.sub(r'  +', ' ', new_bio)
    new_bio = re.sub(r' ([,\.;:!?])', r'\1', new_bio)
    new_bio = new_bio.strip()

    # If bio now starts with a verb, prepend "They" and fix conjugation
    first_word = new_bio.split()[0].lower() if new_bio.split() else ''
    if first_word in VERB_STARTERS:
        # Fix singular→plural conjugation for "they"
        CONJUGATION_FIXES = {'was': 'were', 'is': 'are', 'has': 'have'}
        for singular, plural in CONJUGATION_FIXES.items():
            if new_bio.startswith(singular + ' ') or new_bio == singular:
                new_bio = plural + new_bio[len(singular):]
                break
            elif new_bio.lower().startswith(singular + ' ') or new_bio.lower() == singular:
                new_bio = plural + new_bio[len(singular):]
                break
        new_bio = 'They ' + new_bio

    return new_bio


def main():
    filepath = 'artguesser/artists.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Execute to get ARTISTS dict
    namespace = {}
    exec(compile(content, filepath, 'exec'), namespace)
    ARTISTS = namespace['ARTISTS']

    changes = []
    new_content = content

    for artist_name, data in ARTISTS.items():
        bio = data.get('short_bio', '')
        if not bio:
            continue

        new_bio = strip_name_from_bio(artist_name, bio)

        if new_bio != bio:
            changes.append((artist_name, bio, new_bio))
            # Replace in file content - find exact string and replace
            # The bio is stored as either '...' or "..."
            for quote in ["'", '"']:
                old_str = f'"short_bio": {quote}{bio}{quote}'
                new_str = f'"short_bio": {quote}{new_bio}{quote}'
                if old_str in new_content:
                    new_content = new_content.replace(old_str, new_str, 1)
                    break

    print(f"Modified {len(changes)} bios:")
    for artist_name, old_bio, new_bio in changes:
        print(f"\n  Artist: {artist_name}")
        print(f"  OLD: {old_bio}")
        print(f"  NEW: {new_bio}")

    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\nDone. {len(changes)} bios updated.")

    # Verify: check no names remain
    print("\n--- Verification pass ---")
    namespace2 = {}
    exec(compile(new_content, filepath, 'exec'), namespace2)
    ARTISTS2 = namespace2['ARTISTS']
    violations = []
    for artist_name, data in ARTISTS2.items():
        bio = data.get('short_bio', '')
        tokens = get_name_tokens(artist_name)
        for token in tokens:
            pattern = r'(?<!\w)' + re.escape(token) + r'(?!\w)'
            if re.search(pattern, bio, re.IGNORECASE):
                violations.append((artist_name, token, bio))
    if violations:
        print(f"WARNING: {len(violations)} remaining name occurrences in bios:")
        for artist_name, token, bio in violations:
            print(f"  {artist_name!r}: token {token!r} in bio: {bio}")
    else:
        print("All clear — no artist names remain in any bio field.")


if __name__ == '__main__':
    main()
