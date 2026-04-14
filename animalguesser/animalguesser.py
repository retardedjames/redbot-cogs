import asyncio
import pathlib
import random

import discord
from redbot.core import commands

# ── Dev mode — set DEV_MODE = False for production ───────────────────────────
DEV_MODE = False

if DEV_MODE:
    import subprocess as _sp, pathlib as _pl
    try:
        _sha = _sp.check_output(
            ["git", "-C", str(_pl.Path(__file__).parent), "rev-parse", "--short", "HEAD"],
            stderr=_sp.DEVNULL, text=True,
        ).strip()
    except Exception:
        _sha = "dev"
    DEV_LABEL = f"  [{_sha}]"
else:
    DEV_LABEL = ""
# ─────────────────────────────────────────────────────────────────────────────


# ── Animal list (~250 common animals) ────────────────────────────────────────

ANIMALS = [
    # A
    "Aardvark", "African Buffalo", "African Elephant", "African Wild Dog",
    "Albatross", "Alligator", "Alpaca", "Anaconda", "Anteater", "Antelope",
    "Arctic Fox", "Arctic Wolf", "Armadillo", "Axolotl",
    # B
    "Baboon", "Bald Eagle", "Barn Owl", "Barracuda", "Bat", "Bearded Dragon",
    "Beaver", "Beluga Whale", "Bengal Tiger", "Bighorn Sheep", "Bison",
    "Black Bear", "Black Mamba", "Blue Jay", "Blue Whale", "Boa Constrictor",
    "Bobcat", "Box Jellyfish", "Brown Bear", "Bullfrog", "Bushbaby",
    # C
    "Caiman", "Camel", "Capybara", "Caracal", "Cat", "Catfish", "Chameleon",
    "Cheetah", "Chicken", "Chimpanzee", "Chinchilla", "Chipmunk", "Clownfish",
    "Clouded Leopard", "Cobra", "Cockatoo", "Condor", "Cormorant", "Cougar",
    "Coyote", "Crab", "Crane", "Crocodile", "Crow", "Cuttlefish",
    # D
    "Deer", "Dhole", "Dingo", "Dolphin", "Donkey", "Duck", "Dugong",
    # E
    "Eagle", "Echidna", "Electric Eel", "Elephant", "Elk", "Emu",
    # F
    "Falcon", "Ferret", "Finch", "Flamingo", "Flying Squirrel", "Fossa",
    "Fox", "Frigate Bird", "Frog",
    # G
    "Gaur", "Gazelle", "Gecko", "Giant Panda", "Giant Squid", "Gila Monster",
    "Giraffe", "Gnu", "Goat", "Golden Eagle", "Goose", "Gorilla",
    "Grizzly Bear", "Groundhog", "Guinea Pig",
    # H
    "Hammerhead Shark", "Hamster", "Hare", "Hawk", "Hedgehog", "Heron",
    "Hippopotamus", "Honey Badger", "Horse", "Hummingbird",
    "Humpback Whale", "Hyena",
    # I
    "Ibis", "Iguana", "Impala",
    # J
    "Jackrabbit", "Jaguar", "Jellyfish",
    # K
    "Kangaroo", "King Cobra", "Kinkajou", "Kiwi", "Koala",
    "Komodo Dragon", "Kookaburra", "Kudu",
    # L
    "Leafy Sea Dragon", "Lemur", "Leopard", "Leopard Seal", "Lion",
    "Llama", "Lobster", "Lynx",
    # M
    "Macaw", "Magpie", "Manatee", "Mandrill", "Manta Ray", "Marmoset",
    "Marmot", "Meerkat", "Mongoose", "Monitor Lizard", "Moose",
    "Mountain Goat", "Mouse", "Mule", "Musk Ox",
    # N
    "Narwhal", "Numbat",
    # O
    "Ocelot", "Octopus", "Opossum", "Orangutan", "Orca", "Oryx",
    "Ostrich", "Otter", "Owl",
    # P
    "Pangolin", "Parrot", "Peacock", "Pelican", "Penguin",
    "Peregrine Falcon", "Pheasant", "Pig", "Pika", "Pigeon", "Piranha",
    "Platypus", "Polar Bear", "Porcupine", "Prairie Dog", "Proboscis Monkey",
    "Pronghorn", "Puffin", "Puma", "Python",
    # Q
    "Quail", "Quokka",
    # R
    "Rabbit", "Raccoon", "Rat", "Rattlesnake", "Red Fox", "Red Panda",
    "Reindeer", "Rhinoceros", "Ring-Tailed Lemur", "Robin", "Rock Hyrax",
    "Rooster",
    # S
    "Salamander", "Scorpion", "Sea Horse", "Sea Lion", "Sea Otter",
    "Sea Turtle", "Seal", "Secretary Bird", "Serval", "Shark", "Skunk",
    "Sloth", "Sloth Bear", "Snapping Turtle", "Snow Leopard", "Snowy Owl",
    "Sperm Whale", "Springbok", "Squirrel", "Starfish", "Stingray", "Stoat",
    "Stork", "Sun Bear", "Swan", "Swordfish",
    # T
    "Tapir", "Tarantula", "Tarsier", "Tasmanian Devil", "Tiger",
    "Tiger Shark", "Toad", "Toucan", "Tree Frog", "Tuna", "Turkey", "Turtle",
    # U
    "Uakari",
    # V
    "Vampire Bat", "Viper", "Vulture",
    # W
    "Walrus", "Warthog", "Water Buffalo", "Weasel", "Whale", "Whale Shark",
    "White-Tailed Deer", "Wild Boar", "Wildebeest", "Wolf", "Wolverine",
    "Wombat", "Woodpecker",
    # Y – Z
    "Yak", "Zebra",
]

# ── Animal habitat factoids ───────────────────────────────────────────────────

ANIMAL_FACTS = {
    "Aardvark":           "Native to sub-Saharan Africa.",
    "African Buffalo":    "Found throughout sub-Saharan Africa.",
    "African Elephant":   "Native to sub-Saharan Africa and parts of West Africa.",
    "African Wild Dog":   "Found in sub-Saharan Africa, especially eastern and southern regions.",
    "Albatross":          "Found in the Southern Ocean and North Pacific.",
    "Alligator":          "Native to the southeastern United States and central China.",
    "Alpaca":             "Native to the Andes mountains of South America, particularly Peru.",
    "Anaconda":           "Native to South America, especially the Amazon rainforest.",
    "Anteater":           "Native to Central and South America.",
    "Antelope":           "Found across Africa and parts of Asia.",
    "Arctic Fox":         "Native to Arctic regions of North America, Europe, and Asia.",
    "Arctic Wolf":        "Found in the Canadian Arctic and Greenland.",
    "Armadillo":          "Native to the Americas, ranging from the southern United States to Argentina.",
    "Axolotl":            "Native to Lake Xochimilco near Mexico City, Mexico.",
    "Baboon":             "Native to Africa and parts of the Arabian Peninsula.",
    "Bald Eagle":         "Native to North America, particularly the United States and Canada.",
    "Barn Owl":           "Found worldwide on every continent except Antarctica.",
    "Barracuda":          "Found in tropical and subtropical oceans worldwide.",
    "Bat":                "Found worldwide except the most extreme polar and desert environments.",
    "Bearded Dragon":     "Native to Australia.",
    "Beaver":             "Found in North America and Eurasia.",
    "Beluga Whale":       "Found in Arctic and sub-Arctic waters around Canada, Russia, and Alaska.",
    "Bengal Tiger":       "Native to the Indian subcontinent, mainly India and Bangladesh.",
    "Bighorn Sheep":      "Native to the Rocky Mountains and deserts of western North America.",
    "Bison":              "Native to North America (Great Plains) and Europe (forests of Poland and Belarus).",
    "Black Bear":         "Native to North America.",
    "Black Mamba":        "Found in eastern and southern sub-Saharan Africa.",
    "Blue Jay":           "Native to eastern and central North America.",
    "Blue Whale":         "Found in oceans worldwide, migrating between polar and tropical waters.",
    "Boa Constrictor":    "Native to Central and South America and some Caribbean islands.",
    "Bobcat":             "Native to North America.",
    "Box Jellyfish":      "Found in coastal waters of the Pacific and Indian Oceans, especially northern Australia.",
    "Brown Bear":         "Found across North America, Europe, and Asia.",
    "Bullfrog":           "Native to eastern North America; introduced widely worldwide.",
    "Bushbaby":           "Found in sub-Saharan Africa.",
    "Caiman":             "Native to Central and South America.",
    "Camel":              "Native to Central Asia (Bactrian) and the Arabian Peninsula and North Africa (Dromedary).",
    "Capybara":           "Native to South America.",
    "Caracal":            "Found across Africa, the Middle East, and parts of Central and South Asia.",
    "Cat":                "Domesticated worldwide; wild ancestors from the Middle East and North Africa.",
    "Catfish":            "Found on every continent except Antarctica.",
    "Chameleon":          "Native primarily to Africa and Madagascar, with some species in southern Europe and Asia.",
    "Cheetah":            "Found mainly in sub-Saharan Africa, with a small population in Iran.",
    "Chicken":            "Domesticated worldwide; originally from Southeast Asia.",
    "Chimpanzee":         "Native to the forests and savannas of Central and West Africa.",
    "Chinchilla":         "Native to the Andes mountains of South America.",
    "Chipmunk":           "Native to North America; one species (Siberian chipmunk) found in Asia.",
    "Clownfish":          "Found in the warm waters of the Indian and Pacific Oceans.",
    "Clouded Leopard":    "Native to the Himalayan foothills through mainland Southeast Asia.",
    "Cobra":              "Found across Africa and Asia.",
    "Cockatoo":           "Native to Australia, Indonesia, and nearby Pacific islands.",
    "Condor":             "Found in the Andes of South America and the coastal mountains of California.",
    "Cormorant":          "Found on coastlines worldwide.",
    "Cougar":             "Found throughout North and South America.",
    "Coyote":             "Native to North and Central America.",
    "Crab":               "Found in oceans worldwide and some freshwater and land environments.",
    "Crane":              "Found on every continent except Antarctica and South America.",
    "Crocodile":          "Found in tropical regions of Africa, Asia, Australia, and the Americas.",
    "Crow":               "Found on every continent except Antarctica and South America.",
    "Cuttlefish":         "Found in coastal waters of the eastern Atlantic, Mediterranean, and Indo-Pacific.",
    "Deer":               "Found throughout the Americas, Europe, Asia, and northern Africa.",
    "Dhole":              "Native to Central, South, and Southeast Asia.",
    "Dingo":              "Native to Australia.",
    "Dolphin":            "Found in oceans worldwide.",
    "Donkey":             "Domesticated worldwide; originally from the Horn of Africa.",
    "Duck":               "Found worldwide on every continent except Antarctica.",
    "Dugong":             "Found in coastal waters from East Africa to Australia across the Indo-Pacific.",
    "Eagle":              "Found on every continent except Antarctica.",
    "Echidna":            "Native to Australia and New Guinea.",
    "Electric Eel":       "Native to rivers and lakes of South America, especially the Amazon basin.",
    "Elephant":           "Native to sub-Saharan Africa and South and Southeast Asia.",
    "Elk":                "Found in North America and eastern Asia.",
    "Emu":                "Native to Australia.",
    "Falcon":             "Found on every continent except Antarctica.",
    "Ferret":             "Domesticated worldwide; the wild ancestor (polecat) is from Europe.",
    "Finch":              "Found worldwide, especially diverse in the Americas and Africa.",
    "Flamingo":           "Found in parts of Africa, southern Europe, the Caribbean, and South America.",
    "Flying Squirrel":    "Found in North America, Europe, and Asia.",
    "Fossa":              "Native to Madagascar.",
    "Fox":                "Found on every continent except Antarctica.",
    "Frigate Bird":       "Found in tropical and subtropical oceans worldwide.",
    "Frog":               "Found worldwide except Antarctica.",
    "Gaur":               "Native to South and Southeast Asia.",
    "Gazelle":            "Found in Africa, the Middle East, and parts of Central Asia.",
    "Gecko":              "Found on every continent except Antarctica, most diverse in tropical regions.",
    "Giant Panda":        "Native to central China, primarily Sichuan province.",
    "Giant Squid":        "Found in deep oceans worldwide.",
    "Gila Monster":       "Native to the southwestern United States and northwestern Mexico.",
    "Giraffe":            "Native to sub-Saharan Africa.",
    "Gnu":                "Native to eastern and southern Africa.",
    "Goat":               "Domesticated worldwide; originally from the Middle East.",
    "Golden Eagle":       "Found across the Northern Hemisphere including North America, Europe, and Asia.",
    "Goose":              "Found worldwide except Antarctica.",
    "Gorilla":            "Native to the forests of central sub-Saharan Africa.",
    "Grizzly Bear":       "Native to North America and parts of Europe and Asia.",
    "Groundhog":          "Native to North America.",
    "Guinea Pig":         "Native to the Andes of South America; domesticated worldwide.",
    "Hammerhead Shark":   "Found in warm coastal waters worldwide.",
    "Hamster":            "Native to parts of Europe, the Middle East, and Central Asia.",
    "Hare":               "Found across Europe, Asia, North America, and Africa.",
    "Hawk":               "Found worldwide on every continent except Antarctica.",
    "Hedgehog":           "Native to Europe, Africa, and Asia; introduced to New Zealand.",
    "Heron":              "Found on every continent except Antarctica.",
    "Hippopotamus":       "Native to sub-Saharan Africa.",
    "Honey Badger":       "Found across sub-Saharan Africa, the Middle East, and South Asia.",
    "Horse":              "Domesticated worldwide; originally from Central Asia.",
    "Hummingbird":        "Native to the Americas.",
    "Humpback Whale":     "Found in oceans worldwide.",
    "Hyena":              "Found in Africa and parts of Asia.",
    "Ibis":               "Found on every continent except Antarctica.",
    "Iguana":             "Native to Central and South America and some Caribbean islands.",
    "Impala":             "Native to eastern and southern Africa.",
    "Jackrabbit":         "Native to western North America.",
    "Jaguar":             "Native to Central and South America, from Mexico to Argentina.",
    "Jellyfish":          "Found in oceans worldwide.",
    "Kangaroo":           "Native to Australia.",
    "King Cobra":         "Native to South and Southeast Asia.",
    "Kinkajou":           "Native to the tropical forests of Central and South America.",
    "Kiwi":               "Native to New Zealand.",
    "Koala":              "Native to eastern and southern Australia.",
    "Komodo Dragon":      "Native to the Indonesian islands of Komodo, Rinca, and Flores.",
    "Kookaburra":         "Native to Australia and parts of New Guinea.",
    "Kudu":               "Native to eastern and southern Africa.",
    "Leafy Sea Dragon":   "Native to the coastal waters of southern and western Australia.",
    "Lemur":              "Native to Madagascar.",
    "Leopard":            "Found across sub-Saharan Africa and parts of Asia.",
    "Leopard Seal":       "Found in Antarctic and sub-Antarctic waters.",
    "Lion":               "Native to sub-Saharan Africa, with a small population in the Gir Forest of India.",
    "Llama":              "Native to the Andes mountains of South America.",
    "Lobster":            "Found in oceans worldwide.",
    "Lynx":               "Found across North America, Europe, and Asia.",
    "Macaw":              "Native to the forests of Central and South America.",
    "Magpie":             "Found across Europe, Asia, and western North America.",
    "Manatee":            "Found in the Caribbean, Gulf of Mexico, Amazon basin, and West Africa.",
    "Mandrill":           "Native to the rainforests of Central Africa.",
    "Manta Ray":          "Found in tropical and subtropical oceans worldwide.",
    "Marmoset":           "Native to South America, particularly Brazil.",
    "Marmot":             "Found in mountainous regions of Europe, Asia, and North America.",
    "Meerkat":            "Native to the Kalahari Desert of southern Africa.",
    "Mongoose":           "Found in Africa, southern Europe, and Asia.",
    "Monitor Lizard":     "Found across Africa, Asia, and Australia.",
    "Moose":              "Found in North America, Europe, and Asia.",
    "Mountain Goat":      "Native to the Rocky Mountains of North America.",
    "Mouse":              "Found worldwide on every continent except Antarctica.",
    "Mule":               "Found worldwide as a domesticated animal.",
    "Musk Ox":            "Native to the Arctic regions of Canada, Greenland, Alaska, and Russia.",
    "Narwhal":            "Found in Arctic waters around Canada, Greenland, Norway, and Russia.",
    "Numbat":             "Native to southwestern Australia.",
    "Ocelot":             "Native to Central and South America, ranging into the southwestern United States.",
    "Octopus":            "Found in oceans worldwide.",
    "Opossum":            "Found throughout the Americas.",
    "Orangutan":          "Native to the rainforests of Borneo and Sumatra, Indonesia.",
    "Orca":               "Found in oceans worldwide, most abundant in polar regions.",
    "Oryx":               "Found in the deserts and grasslands of Africa and the Arabian Peninsula.",
    "Ostrich":            "Native to the savannas and deserts of Africa.",
    "Otter":              "Found on every continent except Australia and Antarctica.",
    "Owl":                "Found worldwide on every continent except Antarctica.",
    "Pangolin":           "Found across sub-Saharan Africa and South and Southeast Asia.",
    "Parrot":             "Found in tropical and subtropical regions worldwide.",
    "Peacock":            "Native to South Asia, particularly India and Sri Lanka.",
    "Pelican":            "Found on every continent except Antarctica.",
    "Penguin":            "Found in the Southern Hemisphere, mainly Antarctica and sub-Antarctic islands.",
    "Peregrine Falcon":   "Found worldwide on every continent except Antarctica.",
    "Pheasant":           "Native to Asia; introduced across Europe and North America.",
    "Pig":                "Domesticated worldwide; originally from Europe and Asia.",
    "Pika":               "Found in mountainous regions of Central Asia and western North America.",
    "Pigeon":             "Found worldwide on every continent except Antarctica.",
    "Piranha":            "Native to rivers of South America, especially the Amazon basin.",
    "Platypus":           "Native to eastern Australia.",
    "Polar Bear":         "Found in the Arctic regions of Canada, Russia, Norway, Greenland, and Alaska.",
    "Porcupine":          "Found in the Americas, Africa, and Asia.",
    "Prairie Dog":        "Native to the grasslands of North America.",
    "Proboscis Monkey":   "Native to the island of Borneo in Southeast Asia.",
    "Pronghorn":          "Native to the grasslands of western North America.",
    "Puffin":             "Found in the North Atlantic and North Pacific oceans.",
    "Puma":               "Found throughout North and South America.",
    "Python":             "Found in Africa, Asia, and Australia.",
    "Quail":              "Found across North America, Europe, Asia, and Africa.",
    "Quokka":             "Native to southwestern Australia.",
    "Rabbit":             "Found on every continent except Antarctica; originally from southern Europe and North Africa.",
    "Raccoon":            "Native to North America; introduced to Europe and Japan.",
    "Rat":                "Found worldwide on every continent except Antarctica.",
    "Rattlesnake":        "Native to the Americas.",
    "Red Fox":            "Found across the Northern Hemisphere and Australia.",
    "Red Panda":          "Native to the Eastern Himalayas and southwestern China.",
    "Reindeer":           "Found in Arctic and sub-Arctic regions of Europe, Asia, and North America.",
    "Rhinoceros":         "Found in sub-Saharan Africa and South and Southeast Asia.",
    "Ring-Tailed Lemur":  "Native to the island of Madagascar.",
    "Robin":              "Found across North America, Europe, and parts of Asia.",
    "Rock Hyrax":         "Found in Africa and the Middle East.",
    "Rooster":            "Domesticated worldwide; originally from Southeast Asia.",
    "Salamander":         "Found in temperate regions of the Northern Hemisphere, especially North America.",
    "Scorpion":           "Found on every continent except Antarctica.",
    "Sea Horse":          "Found in shallow tropical and temperate waters worldwide.",
    "Sea Lion":           "Found along the coasts of the Pacific Ocean.",
    "Sea Otter":          "Found in coastal waters of the northern Pacific, from Japan to California.",
    "Sea Turtle":         "Found in tropical and subtropical oceans worldwide.",
    "Seal":               "Found in oceans worldwide, especially polar and sub-polar regions.",
    "Secretary Bird":     "Native to the open grasslands and savannas of sub-Saharan Africa.",
    "Serval":             "Native to the grasslands and savannas of sub-Saharan Africa.",
    "Shark":              "Found in oceans worldwide.",
    "Skunk":              "Native to the Americas.",
    "Sloth":              "Native to the tropical forests of Central and South America.",
    "Sloth Bear":         "Native to the Indian subcontinent.",
    "Snapping Turtle":    "Native to North America.",
    "Snow Leopard":       "Native to the mountain ranges of Central Asia and the Himalayas.",
    "Snowy Owl":          "Native to Arctic regions of North America, Europe, and Asia.",
    "Sperm Whale":        "Found in oceans worldwide.",
    "Springbok":          "Native to the open plains of southwestern Africa.",
    "Squirrel":           "Found on every continent except Australia and Antarctica.",
    "Starfish":           "Found in oceans worldwide.",
    "Stingray":           "Found in tropical and subtropical coastal waters worldwide.",
    "Stoat":              "Found across North America, Europe, and northern Asia.",
    "Stork":              "Found across Europe, Africa, and Asia.",
    "Sun Bear":           "Native to the tropical forests of Southeast Asia.",
    "Swan":               "Found in North America, Europe, Asia, and parts of Australia.",
    "Swordfish":          "Found in tropical and temperate oceans worldwide.",
    "Tapir":              "Found in Central and South America and Southeast Asia.",
    "Tarantula":          "Found in tropical and subtropical regions worldwide.",
    "Tarsier":            "Native to the islands of Southeast Asia, including the Philippines and Indonesia.",
    "Tasmanian Devil":    "Native to the island of Tasmania, Australia.",
    "Tiger":              "Native to South and Southeast Asia.",
    "Tiger Shark":        "Found in tropical and temperate oceans worldwide.",
    "Toad":               "Found worldwide except Antarctica.",
    "Toucan":             "Native to the tropical forests of Central and South America.",
    "Tree Frog":          "Found on every continent except Antarctica.",
    "Tuna":               "Found in oceans worldwide.",
    "Turkey":             "Native to North America; domesticated worldwide.",
    "Turtle":             "Found on every continent except Antarctica.",
    "Uakari":             "Native to the Amazon rainforest of South America.",
    "Vampire Bat":        "Native to Mexico, Central America, and South America.",
    "Viper":              "Found across Europe, Asia, Africa, and the Americas.",
    "Vulture":            "Found in Africa, Asia, Europe, and the Americas.",
    "Walrus":             "Found in Arctic waters of the North Atlantic and North Pacific.",
    "Warthog":            "Native to sub-Saharan Africa.",
    "Water Buffalo":      "Native to South and Southeast Asia; domesticated worldwide.",
    "Weasel":             "Found across North America, Europe, and Asia.",
    "Whale":              "Found in oceans worldwide.",
    "Whale Shark":        "Found in tropical and warm temperate seas worldwide.",
    "White-Tailed Deer":  "Native to North and Central America and northern South America.",
    "Wild Boar":          "Found across Europe, Asia, North Africa, and parts of the Americas.",
    "Wildebeest":         "Native to eastern and southern Africa.",
    "Wolf":               "Found across North America, Europe, and Asia.",
    "Wolverine":          "Found in the boreal forests and tundra of North America, Europe, and Asia.",
    "Wombat":             "Native to Australia.",
    "Woodpecker":         "Found on every continent except Antarctica and Australia.",
    "Yak":                "Native to the Himalayan region of Central Asia.",
    "Zebra":              "Native to eastern and southern Africa.",
}

# ── Image library ─────────────────────────────────────────────────────────────

IMAGES_DIR = pathlib.Path(__file__).parent / "images"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ── Helpers ───────────────────────────────────────────────────────────────────

_WORD_COUNT_NAMES = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}


def _scramble(name: str) -> str:
    """Scramble each word in the animal name independently."""
    words = name.split()
    scrambled = []
    for word in words:
        letters = list(word)
        random.shuffle(letters)
        scrambled.append("".join(letters))
    return " ".join(scrambled)


def _build_first_hint(animal: str) -> str:
    """Return the first hint string: first letter, letter count, word count."""
    words = animal.split()
    first_letter = animal[0].upper()
    letter_count = sum(len(w) for w in words)
    line = f"Starts with letter **{first_letter}** and is **{letter_count}** letters long"
    if len(words) > 1:
        word_label = _WORD_COUNT_NAMES.get(len(words), str(len(words)))
        line += f"\n{word_label} words"
    return line


# ── Game state ────────────────────────────────────────────────────────────────

class AnimalGame:
    def __init__(self, animal: str, images: list, task: asyncio.Task):
        self.animal = animal
        self.images = images          # list[pathlib.Path]
        self.used: set = set()
        self.task = task
        self.participants: set = set()

    def pop_image(self) -> "pathlib.Path | None":
        if not self.images:
            return None
        unused = [i for i in range(len(self.images)) if i not in self.used]
        if not unused:                # exhausted all images — reset pool
            self.used.clear()
            unused = list(range(len(self.images)))
        idx = random.choice(unused)
        self.used.add(idx)
        return self.images[idx]


# ── Game view (two buttons + hint timer) ─────────────────────────────────────

class AnimalGameView(discord.ui.View):
    MAX_NEXT_IMAGES = 3   # how many extra images the button can reveal

    def __init__(self, cog: "AnimalGuesser", channel_id: int):
        super().__init__(timeout=75)
        self.cog = cog
        self.channel_id = channel_id
        self.next_image_uses = 0
        self.hint_stage = 0           # 0 = none used, 1 = first given, 2 = both given
        self.message: "discord.Message | None" = None
        self._hint_task: "asyncio.Task | None" = None
        # Hint starts locked; unlocks after 20 s
        self.hint_btn.disabled = True

    # ── Timer ──────────────────────────────────────────────────────────────────

    def start_hint_timer(self):
        self._hint_task = asyncio.create_task(self._enable_hint_after_delay())

    async def _enable_hint_after_delay(self):
        await asyncio.sleep(20)
        game = self.cog.games.get(self.channel_id)
        if not game or self.hint_stage >= 2 or not self.message:
            return
        self.hint_btn.disabled = False
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    # ── Timeout cleanup ────────────────────────────────────────────────────────

    async def on_timeout(self):
        if self._hint_task:
            self._hint_task.cancel()
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    # ── Next Image button ──────────────────────────────────────────────────────

    @discord.ui.button(label="Next Image", style=discord.ButtonStyle.primary)
    async def next_image_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self.cog.games.get(self.channel_id)
        if not game:
            await interaction.response.send_message("This game has already ended.", ephemeral=True)
            return

        path = game.pop_image()
        if path is None:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return

        self.next_image_uses += 1
        remaining = self.MAX_NEXT_IMAGES - self.next_image_uses
        if self.next_image_uses >= self.MAX_NEXT_IMAGES:
            button.disabled = True

        embed = discord.Embed(
            title=f"Another look! ({self.next_image_uses}/{self.MAX_NEXT_IMAGES})",
            description=(
                f"{remaining} more image(s) available."
                if remaining > 0 else "That's all the extra images!"
            ),
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://animal.jpg")

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            embed=embed,
            file=discord.File(path, filename="animal.jpg"),
        )

    # ── Hint button ────────────────────────────────────────────────────────────

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.success, disabled=True)
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self.cog.games.get(self.channel_id)
        if not game:
            await interaction.response.send_message("This game has already ended.", ephemeral=True)
            return

        button.disabled = True
        self.hint_stage += 1

        if self.hint_stage == 1:
            embed = discord.Embed(
                title="Hint 1 of 2",
                description=_build_first_hint(game.animal),
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Hint 2 unlocks in 20 seconds...")
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=embed)
            # Schedule unlock for second hint
            self._hint_task = asyncio.create_task(self._enable_hint_after_delay())

        else:  # hint_stage == 2 — final hint
            embed = discord.Embed(
                title="Hint 2 of 2 — Final Hint!",
                description=f"Scrambled: **{_scramble(game.animal)}**",
                color=discord.Color.orange(),
            )
            embed.set_footer(text="No more hints — good luck!")
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=embed)
            # Button stays disabled; no further timer needed


# ── Play Again button ─────────────────────────────────────────────────────────

class AnimalPlayAgainView(discord.ui.View):
    def __init__(self, cog: "AnimalGuesser", channel_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green, emoji="🎮")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.channel_id in self.cog.games:
            await interaction.response.send_message(
                "A game is already running here!", ephemeral=True
            )
            return
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._start_game(interaction.channel)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class AnimalGuesser(commands.Cog):
    """Animal guessing game — who can identify the mystery animal from a photo?"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, AnimalGame] = {}   # channel_id → AnimalGame

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_images(self, animal: str) -> list:
        """Return a shuffled list of image Paths from the animal's folder."""
        folder = IMAGES_DIR / animal
        if not folder.is_dir():
            return []
        paths = [p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_EXTS and p.is_file()]
        random.shuffle(paths)
        return paths

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, animal: str):
        """Background task that ends the round after 60 seconds."""
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return  # game was won; task cancelled by on_message handler

        game = self.games.pop(channel.id, None)
        if game is None:
            return

        tp = self.bot.get_cog("TrackPoints")
        if tp:
            await tp.record_game_result(None, game.participants)
        fact = ANIMAL_FACTS.get(animal, "")
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The animal was **{animal}**.",
            color=discord.Color(0x99aab5),
        )
        if fact:
            embed.set_footer(text=f"📍 {fact}")
        await channel.send(embed=embed, view=AnimalPlayAgainView(self, channel.id))

    # ── Start game ────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        animal, images = None, []
        for candidate in random.sample(ANIMALS, len(ANIMALS)):
            imgs = self._load_images(candidate)
            if imgs:
                animal, images = candidate, imgs
                break

        if animal is None:
            await channel.send(
                "No animal images found on disk. "
                "Run `python animalguesser/download_images.py` to download the image library first."
            )
            return

        task = asyncio.create_task(self._game_timer(channel, animal))
        game = AnimalGame(animal, images, task)
        self.games[channel.id] = game

        game_view = AnimalGameView(self, channel.id)

        embed = discord.Embed(
            title=f"What animal is this?{DEV_LABEL}",
            description=(
                "Type your guess in chat — anyone can answer!\n"
                "You have **60 seconds**."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Next Image: up to 3 extra photos  |  Hint unlocks after 20 seconds")
        embed.set_image(url="attachment://animal.jpg")

        first_image = game.pop_image()
        msg = await channel.send(
            embed=embed,
            file=discord.File(first_image, filename="animal.jpg"),
            view=game_view,
        )
        game_view.message = msg
        game_view.start_hint_timer()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    async def animalguesser(self, ctx: commands.Context):
        """Start an animal guessing game. 60 seconds — can you name it?"""
        if ctx.channel.id in self.games:
            await ctx.send("A game is already running here! Type your guess in chat.")
            return
        await self._start_game(ctx.channel)

    # ── Guess listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        # Ignore valid bot commands (e.g. $animalguesser)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        game.participants.add(message.author)

        if message.content.strip().lower() != game.animal.lower():
            return

        # ── Correct guess ──────────────────────────────────────────────────
        game.task.cancel()
        del self.games[message.channel.id]

        tp = self.bot.get_cog("TrackPoints")
        total_pts = None
        if tp:
            await tp.record_game_result(message.author, game.participants)
            total_pts = await tp.get_points(message.author)
        pts_line = f"\nYou now have **{total_pts:,}** total points!" if total_pts is not None else ""
        fact = ANIMAL_FACTS.get(game.animal, "")
        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!{pts_line}\n\n"
                f"The animal was **{game.animal}**! Congratulations!"
            ),
            color=discord.Color.blurple(),
        )
        footer = f"📍 {fact}" if fact else "Start a new game any time with $animalguesser!"
        embed.set_footer(text=footer)
        await message.channel.send(embed=embed, view=AnimalPlayAgainView(self, message.channel.id))

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()
        return "Animal Guesser"

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
