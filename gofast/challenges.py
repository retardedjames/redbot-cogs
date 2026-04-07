"""
GoFast challenge registry.

Each challenge class implements:
  key      : str  — groups used-answer tracking across rounds of the same type
  generate()      -> (params: dict, prompt: str)
  validate(answer: str, params: dict) -> bool
"""

import asyncio
import random
from abc import ABC, abstractmethod


# ── Shared dictionary ─────────────────────────────────────────────────────────

def _load_dictionary():
    base = set()
    try:
        from english_words import get_english_words_set
        base = get_english_words_set(["web2"], lower=True)
    except Exception:
        try:
            from english_words import english_words_lower_set
            base = set(english_words_lower_set)
        except ImportError:
            pass
    # Keep only purely alphabetic entries
    return frozenset(w for w in base if w.isalpha())


DICTIONARY = _load_dictionary()


# ── Base class ────────────────────────────────────────────────────────────────

class BaseChallenge(ABC):
    key = ""

    @abstractmethod
    def generate(self):
        """Return (params_dict, prompt_string). Sync version."""
        ...

    async def async_generate(self):
        """Async version — override for challenges that need network calls."""
        return self.generate()

    @abstractmethod
    def validate(self, answer, params):
        """Return True if the answer is valid for this round."""
        ...


# ── Game 1: Any valid word over 15 letters ────────────────────────────────────

class LongWordChallenge(BaseChallenge):
    key = "long_word"

    def generate(self):
        return {}, "Type any valid English word with **more than 12 letters**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        return len(w) > 12 and w.isalpha() and w in DICTIONARY


# ── Game 2: Country starting with [letter] ───────────────────────────────────

COUNTRIES = frozenset([
    "afghanistan", "albania", "algeria", "andorra", "angola",
    "argentina", "armenia", "australia", "austria", "azerbaijan",
    "bahamas", "bahrain", "bangladesh", "barbados", "belarus",
    "belgium", "belize", "benin", "bhutan", "bolivia",
    "bosnia", "botswana", "brazil", "brunei", "bulgaria",
    "burkina", "burundi", "cambodia", "cameroon", "canada",
    "chad", "chile", "china", "colombia", "comoros",
    "congo", "croatia", "cuba", "cyprus", "czechia",
    "denmark", "djibouti", "dominica", "ecuador", "egypt",
    "eritrea", "estonia", "eswatini", "ethiopia", "fiji",
    "finland", "france", "gabon", "gambia", "georgia",
    "germany", "ghana", "greece", "grenada", "guatemala",
    "guinea", "guyana", "haiti", "honduras", "hungary",
    "iceland", "india", "indonesia", "iran", "iraq",
    "ireland", "israel", "italy", "jamaica", "japan",
    "jordan", "kazakhstan", "kenya", "kiribati", "kuwait",
    "kyrgyzstan", "laos", "latvia", "lebanon", "lesotho",
    "liberia", "libya", "liechtenstein", "lithuania", "luxembourg",
    "madagascar", "malawi", "malaysia", "maldives", "mali",
    "malta", "mauritania", "mauritius", "mexico", "micronesia",
    "moldova", "monaco", "mongolia", "montenegro", "morocco",
    "mozambique", "myanmar", "namibia", "nauru", "nepal",
    "netherlands", "newzealand", "nicaragua", "niger", "nigeria",
    "norway", "oman", "pakistan", "palau", "panama",
    "paraguay", "peru", "philippines", "poland", "portugal",
    "qatar", "romania", "russia", "rwanda", "samoa",
    "senegal", "serbia", "seychelles", "singapore", "slovakia",
    "slovenia", "somalia", "spain", "sudan", "suriname",
    "sweden", "switzerland", "syria", "taiwan", "tajikistan",
    "tanzania", "thailand", "togo", "tonga", "tunisia",
    "turkey", "turkmenistan", "tuvalu", "uganda", "ukraine",
    "uruguay", "uzbekistan", "vanuatu", "venezuela", "vietnam",
    "yemen", "zambia", "zimbabwe",
    # multi-word stored with spaces for display, matched stripped
    "new zealand", "new guinea", "north korea", "south korea",
    "north macedonia", "south africa", "south sudan",
    "sierra leone", "sri lanka", "el salvador", "costa rica",
    "cape verde", "central african republic", "democratic republic of the congo",
    "dominican republic", "equatorial guinea", "marshall islands",
    "papua new guinea", "saint kitts and nevis", "saint lucia",
    "saint vincent and the grenadines", "san marino", "sao tome and principe",
    "saudi arabia", "solomon islands", "timor-leste", "trinidad and tobago",
    "united arab emirates", "united kingdom", "united states",
])

# Build a letter -> list-of-countries index at import time
_COUNTRIES_BY_LETTER: dict = {}
for _c in COUNTRIES:
    _first = _c[0]
    _COUNTRIES_BY_LETTER.setdefault(_first, []).append(_c)

# Letters that actually have countries
_COUNTRY_LETTERS = [l for l in _COUNTRIES_BY_LETTER if len(_COUNTRIES_BY_LETTER[l]) >= 1]


class CountryByLetterChallenge(BaseChallenge):
    key = "country_by_letter"

    def generate(self):
        letter = random.choice(_COUNTRY_LETTERS)
        return {"letter": letter}, (
            f"Name a **country** that starts with the letter **{letter.upper()}**!"
        )

    def validate(self, answer, params):
        letter = params["letter"]
        a = answer.strip().lower()
        return a.startswith(letter) and a in COUNTRIES


# ── Game 3: X-letter animal ───────────────────────────────────────────────────

ANIMALS = frozenset([
    # 3 letters
    "ant", "ape", "ass", "bat", "bee", "boa", "bug", "cat", "cod", "cow",
    "cub", "cur", "doe", "dog", "eel", "elk", "emu", "ewe", "fly", "fox",
    "gnu", "hen", "hog", "jay", "kid", "koi", "ram", "rat", "ray", "yak",
    # 4 letters
    "bear", "bird", "boar", "buck", "bull", "clam", "colt", "crab", "crow",
    "dace", "dart", "deer", "dodo", "dove", "duck", "fawn", "flea", "frog",
    "gnat", "goat", "gull", "hare", "hawk", "ibis", "kite", "lamb", "lark",
    "lion", "loon", "lynx", "mink", "mite", "mole", "moth", "mule", "musk",
    "newt", "pony", "puma", "roach", "seal", "slug", "snail", "swan", "toad",
    "vole", "wasp", "worm", "wren",
    # 5 letters
    "bison", "crane", "dingo", "eagle", "finch", "gecko", "goose", "grebe",
    "heron", "hippo", "horse", "hyena", "kaola", "koala", "lemur", "llama",
    "loach", "macaw", "moose", "mouse", "otter", "panda", "quail", "raven",
    "robin", "shark", "shrew", "skunk", "sloth", "snipe", "squid", "stork",
    "swift", "tapir", "tiger", "trout", "viper", "whale", "zebra",
    # 6 letters
    "badger", "beagle", "beaver", "bobcat", "canary", "condor", "coyote",
    "donkey", "falcon", "ferret", "gibbon", "gopher", "iguana", "impala",
    "jaguar", "lizard", "magpie", "marmot", "martin", "monkey", "osprey",
    "parrot", "pigeon", "python", "rabbit", "salmon", "spider", "toucan",
    "turkey", "turtle", "walrus", "weasel", "wombat",
    # 7 letters
    "buffalo", "buzzard", "caribou", "cat bird", "cheetah", "dolphin",
    "gorilla", "hamster", "leopard", "lobster", "manatee", "mudfish",
    "octopus", "opossum", "panther", "peacock", "penguin", "pheasant",
    "piranha", "polecat", "raccoon", "redfish", "sawfish", "sculpin",
    "sparrow", "squirrel", "vulture", "wallaby", "warbler", "wildcat",
    # 8 letters
    "aardvark", "anteater", "antelope", "cardinal", "chipmunk", "cockatoo",
    "elephant", "flamingo", "hedgehog", "kangaroo", "kingfish", "mongoose",
    "nighthawk", "parakeet", "platypus", "reindeer", "ringtail", "scorpion",
    "squirrel", "starfish", "stingray", "tortoise", "warthog",
])

# Pre-bucket by length
_ANIMALS_BY_LEN: dict = {}
for _a in ANIMALS:
    _ANIMALS_BY_LEN.setdefault(len(_a), set()).add(_a)


class XLetterAnimalChallenge(BaseChallenge):
    def __init__(self, length: int):
        self.length = length
        self.key = f"animal_{length}"

    def generate(self):
        return {"length": self.length}, (
            f"Name any animal with exactly **{self.length} letters**!"
        )

    def validate(self, answer, params):
        a = answer.strip().lower()
        length = params["length"]
        return len(a) == length and a in ANIMALS


# ── Game 4: X-letter fruit ────────────────────────────────────────────────────

FRUITS = frozenset([
    # 3 letters
    "fig", "kiwi",
    # 4 letters
    "kiwi", "lime", "pear", "plum",
    # 5 letters
    "apple", "grape", "guava", "lemon", "mango", "melon", "olive", "peach",
    "prune",
    # 6 letters
    "banana", "cherry", "citron", "damson", "durian", "lychee", "orange",
    "papaya", "pomelo", "quince",
    # 7 letters
    "apricot", "avocado", "coconut", "kumquat", "pumpkin", "satsuma",
    "soursop", "tamarind",
    # 8 letters
    "bilberry", "blueberry", "dewberry", "mulberry", "date palm", "mandarin",
    "persimmon", "plantain", "rambutan", "starfruit", "tamarind",
    # 9+ kept out — only 5-8 are used in challenges but list can be larger
    "blackberry", "boysenberry", "breadfruit", "cantaloupe", "clementine",
    "elderberry", "gooseberry", "grapefruit", "honeydew", "jackfruit",
    "loganberry", "nectarine", "passionfruit", "raspberry", "strawberry",
    "tangerine", "watermelon",
])

_FRUITS_BY_LEN: dict = {}
for _f in FRUITS:
    _FRUITS_BY_LEN.setdefault(len(_f), set()).add(_f)


class XLetterFruitChallenge(BaseChallenge):
    def __init__(self, length: int):
        self.length = length
        self.key = f"fruit_{length}"

    def generate(self):
        return {"length": self.length}, (
            f"Name any fruit with exactly **{self.length} letters**!"
        )

    def validate(self, answer, params):
        a = answer.strip().lower()
        length = params["length"]
        return len(a) == length and a in FRUITS


# ── Game 5: Word with no repeated letters ────────────────────────────────────

class NoRepeatedLettersChallenge(BaseChallenge):
    key = "no_repeated_letters"

    def generate(self):
        return {}, (
            "Type any valid English word where **no letter appears more than once**!"
        )

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or w not in DICTIONARY:
            return False
        return len(w) == len(set(w))


# ── Game 6: Capital city ─────────────────────────────────────────────────────

CAPITALS = frozenset([
    "kabul", "tirana", "algiers", "andorra la vella", "luanda", "buenos aires",
    "yerevan", "canberra", "vienna", "baku", "nassau", "manama", "dhaka",
    "bridgetown", "minsk", "brussels", "belmopan", "porto novo", "thimphu",
    "sucre", "sarajevo", "gaborone", "brasilia", "bandar seri begawan",
    "sofia", "ouagadougou", "bujumbura", "phnom penh", "yaounde", "ottawa",
    "praia", "bangui", "ndjamena", "santiago", "beijing", "bogota", "moroni",
    "kinshasa", "brazzaville", "san jose", "zagreb", "havana", "nicosia",
    "prague", "copenhagen", "djibouti", "roseau", "santo domingo", "quito",
    "cairo", "san salvador", "malabo", "asmara", "tallinn", "mbabane",
    "addis ababa", "suva", "helsinki", "paris", "libreville", "banjul",
    "tbilisi", "berlin", "accra", "athens", "saint george", "guatemala city",
    "conakry", "bissau", "georgetown", "port au prince", "tegucigalpa",
    "budapest", "reykjavik", "new delhi", "jakarta", "tehran", "baghdad",
    "dublin", "jerusalem", "rome", "kingston", "tokyo", "amman", "astana",
    "nairobi", "tarawa", "seoul", "pristina", "kuwait city", "bishkek",
    "vientiane", "riga", "beirut", "maseru", "monrovia", "tripoli",
    "vaduz", "vilnius", "luxembourg", "skopje", "antananarivo", "lilongwe",
    "kuala lumpur", "male", "bamako", "valletta", "majuro", "nouakchott",
    "port louis", "mexico city", "palikir", "chisinau", "monaco",
    "ulaanbaatar", "podgorica", "rabat", "maputo", "naypyidaw", "windhoek",
    "yaren", "kathmandu", "amsterdam", "wellington", "managua", "niamey",
    "abuja", "oslo", "muscat", "islamabad", "ngerulmud", "panama city",
    "port moresby", "asuncion", "lima", "manila", "warsaw", "lisbon",
    "doha", "bucharest", "moscow", "kigali", "basseterre", "castries",
    "kingstown", "apia", "san marino", "sao tome", "riyadh", "dakar",
    "belgrade", "victoria", "freetown", "singapore", "bratislava",
    "ljubljana", "honiara", "mogadishu", "pretoria", "madrid", "colombo",
    "khartoum", "paramaribo", "mbabane", "stockholm", "bern", "damascus",
    "taipei", "dushanbe", "dodoma", "bangkok", "lome", "nukualofa",
    "port of spain", "tunis", "ankara", "ashgabat", "funafuti", "kampala",
    "kyiv", "abu dhabi", "london", "washington", "montevideo", "tashkent",
    "port vila", "caracas", "hanoi", "sanaa", "lusaka", "harare",
])


class CapitalCityChallenge(BaseChallenge):
    key = "capital_city"

    def generate(self):
        return {}, "Name any **world capital city**!"

    def validate(self, answer, params):
        return answer.strip().lower() in CAPITALS


# ── Game 7: Word starting and ending with the same letter ────────────────────

class SameStartEndChallenge(BaseChallenge):
    key = "same_start_end"

    def generate(self):
        return {}, (
            "Type any valid English word that **starts and ends with the same letter**!"
        )

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or len(w) < 2 or w not in DICTIONARY:
            return False
        return w[0] == w[-1]


# ── Game 8: Animal that's also a verb ────────────────────────────────────────

ANIMAL_VERBS = frozenset([
    "bear", "buck", "bug", "crane", "crow", "dog", "duck", "ferret",
    "fish", "fawn", "fly", "fox", "goose", "hawk", "hound", "jay",
    "lark", "louse", "lynx", "mole", "monkey", "moose", "mouse",
    "mule", "parrot", "pig", "ram", "rat", "skunk", "snake", "snipe",
    "sow", "squirrel", "stag", "wolf", "worm", "badger", "bat",
    "buffalo", "colt", "crab", "cuckoo", "dove", "finch", "grouse",
    "hare", "horse", "hog", "kid", "kitten", "leech", "locust",
    "magpie", "pony", "pup", "robin", "rook", "seal", "slug", "wasp",
])


class AnimalVerbChallenge(BaseChallenge):
    key = "animal_verb"

    def generate(self):
        return {}, "Name an animal that is **also a verb**!"

    def validate(self, answer, params):
        return answer.strip().lower() in ANIMAL_VERBS


# ── Game 9: Word with 3 vowels in a row ──────────────────────────────────────

_VOWELS = set("aeiou")


def _has_three_vowels_in_row(word: str) -> bool:
    count = 0
    for ch in word:
        if ch in _VOWELS:
            count += 1
            if count >= 3:
                return True
        else:
            count = 0
    return False


class ThreeVowelsInRowChallenge(BaseChallenge):
    key = "three_vowels_row"

    def generate(self):
        return {}, "Type any valid English word that contains **3 vowels in a row**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or w not in DICTIONARY:
            return False
        return _has_three_vowels_in_row(w)


# ── Game 10: Palindrome ───────────────────────────────────────────────────────

PALINDROMES = frozenset([
    "civic", "deed", "kayak", "level", "madam", "minim", "noon", "pup",
    "radar", "refer", "repaper", "reviver", "rotator", "rotor", "sagas",
    "sexes", "shahs", "solos", "stats", "tenet", "toot", "wow",
    "bib", "bob", "did", "dud", "eke", "ere", "eve", "ewe", "eye",
    "gag", "gig", "nun", "pep", "pip", "pop", "sis", "tit",
    "deified", "racecar", "redder", "repaper", "reviver",
])


class PalindromeChallenge(BaseChallenge):
    key = "palindrome"

    def generate(self):
        return {}, "Type any word that is spelled the **same forwards and backwards**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or len(w) < 2:
            return False
        return w == w[::-1] and w in PALINDROMES


# ── Game 11: Country in [continent] ──────────────────────────────────────────

COUNTRIES_BY_CONTINENT = {
    "Africa": frozenset([
        "algeria", "angola", "benin", "botswana", "burkina faso", "burundi",
        "cameroon", "cape verde", "central african republic", "chad", "comoros",
        "democratic republic of the congo", "djibouti", "egypt", "equatorial guinea",
        "eritrea", "eswatini", "ethiopia", "gabon", "gambia", "ghana", "guinea",
        "guinea-bissau", "kenya", "lesotho", "liberia", "libya", "madagascar",
        "malawi", "mali", "mauritania", "mauritius", "morocco", "mozambique",
        "namibia", "niger", "nigeria", "rwanda", "sao tome and principe",
        "senegal", "seychelles", "sierra leone", "somalia", "south africa",
        "south sudan", "sudan", "tanzania", "togo", "tunisia", "uganda",
        "zambia", "zimbabwe", "congo",
    ]),
    "Asia": frozenset([
        "afghanistan", "armenia", "azerbaijan", "bahrain", "bangladesh", "bhutan",
        "brunei", "cambodia", "china", "cyprus", "georgia", "india", "indonesia",
        "iran", "iraq", "israel", "japan", "jordan", "kazakhstan", "kuwait",
        "kyrgyzstan", "laos", "lebanon", "malaysia", "maldives", "mongolia",
        "myanmar", "nepal", "north korea", "oman", "pakistan", "philippines",
        "qatar", "russia", "saudi arabia", "singapore", "south korea", "sri lanka",
        "syria", "taiwan", "tajikistan", "thailand", "timor-leste", "turkey",
        "turkmenistan", "united arab emirates", "uzbekistan", "vietnam", "yemen",
    ]),
    "Europe": frozenset([
        "albania", "andorra", "austria", "belarus", "belgium", "bosnia",
        "bulgaria", "croatia", "cyprus", "czechia", "denmark", "estonia",
        "finland", "france", "germany", "greece", "hungary", "iceland",
        "ireland", "italy", "latvia", "liechtenstein", "lithuania", "luxembourg",
        "malta", "moldova", "monaco", "montenegro", "netherlands", "norway",
        "poland", "portugal", "romania", "russia", "san marino", "serbia",
        "slovakia", "slovenia", "spain", "sweden", "switzerland", "ukraine",
        "united kingdom", "vatican",
    ]),
    "North America": frozenset([
        "antigua and barbuda", "bahamas", "barbados", "belize", "canada",
        "costa rica", "cuba", "dominica", "dominican republic", "el salvador",
        "grenada", "guatemala", "haiti", "honduras", "jamaica", "mexico",
        "nicaragua", "panama", "saint kitts and nevis", "saint lucia",
        "saint vincent and the grenadines", "trinidad and tobago",
        "united states",
    ]),
    "South America": frozenset([
        "argentina", "bolivia", "brazil", "chile", "colombia", "ecuador",
        "guyana", "paraguay", "peru", "suriname", "uruguay", "venezuela",
    ]),
    "Oceania": frozenset([
        "australia", "fiji", "kiribati", "marshall islands", "micronesia",
        "nauru", "new zealand", "palau", "papua new guinea", "samoa",
        "solomon islands", "tonga", "tuvalu", "vanuatu",
    ]),
}

_CONTINENTS = list(COUNTRIES_BY_CONTINENT.keys())


class CountryByContinentChallenge(BaseChallenge):
    key = "country_by_continent"

    def generate(self):
        continent = random.choice(_CONTINENTS)
        return {"continent": continent}, (
            f"Name a **country in {continent}**!"
        )

    def validate(self, answer, params):
        continent = params["continent"]
        return answer.strip().lower() in COUNTRIES_BY_CONTINENT[continent]


# ── Game 12: Adjective ending in -ful ────────────────────────────────────────

class EndsInFulChallenge(BaseChallenge):
    key = "ends_in_ful"

    def generate(self):
        return {}, "Type any valid English **adjective ending in -ful**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or not w.endswith("ful"):
            return False
        # Accept if the word itself is in the dictionary, or its stem is
        if w in DICTIONARY:
            return True
        stem = w[:-3]  # remove "ful"
        return stem in DICTIONARY or (stem + "y") in DICTIONARY


# ── Game 13: Word with double letters ────────────────────────────────────────

def _has_double_letters(word: str) -> bool:
    for i in range(len(word) - 1):
        if word[i] == word[i + 1]:
            return True
    return False


class DoubleLettersChallenge(BaseChallenge):
    key = "double_letters"

    def generate(self):
        return {}, "Type any valid English word that contains **double letters**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or w not in DICTIONARY:
            return False
        return _has_double_letters(w)


# ── Game 14: Planet, moon, or star name ──────────────────────────────────────

SPACE_BODIES = frozenset([
    # Planets
    "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune",
    # Dwarf planets
    "pluto", "eris", "ceres", "makemake", "haumea",
    # Major moons of Solar System
    "moon", "phobos", "deimos",
    "io", "europa", "ganymede", "callisto", "amalthea",
    "titan", "rhea", "dione", "tethys", "enceladus", "mimas", "hyperion", "iapetus", "phoebe",
    "miranda", "ariel", "umbriel", "titania", "oberon",
    "triton", "nereid", "proteus",
    "charon", "nix", "hydra",
    # Famous stars
    "sun", "sirius", "canopus", "arcturus", "vega", "capella", "rigel",
    "procyon", "achernar", "betelgeuse", "altair", "aldebaran", "antares",
    "spica", "pollux", "fomalhaut", "deneb", "regulus", "castor", "mimosa",
    "polaris", "acrux", "gacrux", "alioth", "dubhe", "mirfak", "wezen",
    "sargas", "kaus", "shaula", "alkaid", "alnair", "mizar", "nunki",
    "menkent", "alphard", "hamal", "diphda", "saiph", "alhena", "peacock",
    "zubenelgenubi", "zubeneschamali",
])


class SpaceBodyChallenge(BaseChallenge):
    key = "space_body"

    def generate(self):
        return {}, (
            "Name any **planet, moon, or star** from our solar system or the known universe!"
        )

    def validate(self, answer, params):
        return answer.strip().lower() in SPACE_BODIES


# ── Game 15: Word containing an animal inside it ──────────────────────────────

# Short animals only — must be at least 3 letters to avoid trivial matches
_HIDDEN_ANIMALS = [
    "ant", "ape", "ass", "bat", "bear", "bee", "boar", "bug", "bull",
    "cat", "cod", "cow", "crab", "crow", "deer", "doe", "dog", "dove",
    "duck", "eel", "elk", "emu", "ewe", "fly", "fox", "frog", "gnu",
    "goat", "hen", "hog", "lion", "lynx", "mink", "mole", "moth", "mule",
    "newt", "owl", "pig", "puma", "ram", "rat", "seal", "slug", "swan",
    "toad", "wasp", "wolf", "worm", "wren", "yak",
    "crane", "eagle", "finch", "gecko", "heron", "horse", "hyena", "koala",
    "lemur", "llama", "moose", "mouse", "otter", "panda", "quail", "raven",
    "robin", "shark", "shrew", "skunk", "sloth", "snipe", "squid", "stork",
    "swift", "tapir", "tiger", "trout", "viper", "whale", "zebra",
]


def _animal_hidden_in(word: str):
    """Return the first animal found hidden inside word, or None."""
    w = word.lower()
    for animal in _HIDDEN_ANIMALS:
        if animal in w and animal != w:
            return animal
    return None


class HiddenAnimalChallenge(BaseChallenge):
    key = "hidden_animal"

    def generate(self):
        return {}, "Type any valid English word that has an **animal hidden inside it**!"

    def validate(self, answer, params):
        w = answer.strip().lower()
        if not w.isalpha() or w not in DICTIONARY:
            return False
        return _animal_hidden_in(w) is not None


# ── Game 16: Rhymes with [word] ───────────────────────────────────────────────

# Seed words — common, short, with lots of rhymes
_RHYME_SEEDS = [
    "cake", "day", "night", "time", "song", "love", "moon", "rain",
    "light", "blue", "star", "door", "hand", "fire", "stone", "sun",
    "run", "sea", "tree", "dream", "ring", "king", "way", "play",
    "sound", "ground", "high", "sky", "bright", "white", "dance",
    "chance", "grace", "place", "mine", "shine", "free", "see",
]

_DATAMUSE_URL = "https://api.datamuse.com/words?rel_rhy={word}&max=200"


async def _fetch_rhymes(word: str) -> set:
    """Call Datamuse and return a set of words that rhyme with word."""
    try:
        import aiohttp
        url = _DATAMUSE_URL.format(word=word)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return set()
                data = await resp.json()
                return {entry["word"].lower() for entry in data if "word" in entry}
    except Exception:
        return set()


class RhymeChallenge(BaseChallenge):
    key = "rhyme"

    def generate(self):
        # Fallback if async_generate can't be awaited for some reason
        return {"seed": "cake", "rhymes": set()}, "Type any word that **rhymes with cake**!"

    async def async_generate(self):
        seed = random.choice(_RHYME_SEEDS)
        rhymes = await _fetch_rhymes(seed)
        if not rhymes:
            # Datamuse failed — skip this challenge by returning a simple fallback
            seed = "cake"
            rhymes = {
                "bake", "fake", "lake", "make", "rake", "sake", "take",
                "wake", "flake", "shake", "snake", "stake", "brake",
            }
        params = {"seed": seed, "rhymes": rhymes}
        prompt = f"Type any word that **rhymes with {seed}**!"
        return params, prompt

    def validate(self, answer, params):
        return answer.strip().lower() in params.get("rhymes", set())


# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry is a list of challenge variants for one activity type.
# A random group is picked first (equal weight per activity), then a random
# variant within that group is picked — so animal×4 and fruit×4 each still
# only count as one activity.

CHALLENGE_GROUPS = [
    [LongWordChallenge()],
    [CountryByLetterChallenge()],
    # [XLetterAnimalChallenge(4), XLetterAnimalChallenge(5), XLetterAnimalChallenge(6), XLetterAnimalChallenge(7)],
    # [XLetterFruitChallenge(5), XLetterFruitChallenge(6), XLetterFruitChallenge(7), XLetterFruitChallenge(8)],
    [NoRepeatedLettersChallenge()],
    [CapitalCityChallenge()],
    [SameStartEndChallenge()],
    [AnimalVerbChallenge()],
    [ThreeVowelsInRowChallenge()],
    [PalindromeChallenge()],
    [CountryByContinentChallenge()],
    [EndsInFulChallenge()],
    [DoubleLettersChallenge()],
    [SpaceBodyChallenge()],
    [HiddenAnimalChallenge()],
    [RhymeChallenge()],
]
