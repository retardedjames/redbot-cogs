import asyncio
import random

import aiohttp
import discord
from redbot.core import commands

try:
    from _dev import DEV_LABEL
except ImportError:
    DEV_LABEL = ""


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
    "Eagle", "Eagle Ray", "Echidna", "Electric Eel", "Elephant", "Elk", "Emu",
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


# ── Game state ────────────────────────────────────────────────────────────────

def _scramble(name: str) -> str:
    """Scramble each word in the animal name independently."""
    words = name.split()
    scrambled = []
    for word in words:
        letters = list(word)
        random.shuffle(letters)
        scrambled.append("".join(letters))
    return " ".join(scrambled)


class AnimalGame:
    MAX_HINTS = 4

    def __init__(self, animal: str, images: list, task: asyncio.Task):
        self.animal = animal
        self.images = images          # list of image URLs fetched up front
        self.used: set = set()        # indices already shown this round
        self.hints_used = 0
        self.task = task

    def pop_image(self) -> str | None:
        if not self.images:
            return None
        unused = [i for i in range(len(self.images)) if i not in self.used]
        if not unused:                # exhausted all images — reset pool
            self.used.clear()
            unused = list(range(len(self.images)))
        idx = random.choice(unused)
        self.used.add(idx)
        return self.images[idx]


# ── Hint button ───────────────────────────────────────────────────────────────

class AnimalHintView(discord.ui.View):
    """Single-use green Hint button. Disables itself when clicked, then sends
    the next hint as a followup (with a fresh button if hints remain)."""

    def __init__(self, cog: "AnimalGuesser", channel_id: int):
        super().__init__(timeout=70)   # slightly longer than the 60-s game timer
        self.cog = cog
        self.channel_id = channel_id
        self._used = False

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.success)
    async def hint_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._used:
            await interaction.response.send_message(
                "Use the most recent Hint button!", ephemeral=True
            )
            return

        game = self.cog.games.get(self.channel_id)
        if not game:
            await interaction.response.send_message(
                "This game has already ended.", ephemeral=True
            )
            return
        if game.hints_used >= AnimalGame.MAX_HINTS:
            await interaction.response.send_message(
                f"All **{AnimalGame.MAX_HINTS}** hints have been used — keep guessing!",
                ephemeral=True,
            )
            return

        self._used = True
        button.disabled = True
        game.hints_used += 1
        remaining = AnimalGame.MAX_HINTS - game.hints_used
        footer = f"{remaining} hint(s) remaining." if remaining else "No more hints after this!"
        is_final = game.hints_used == AnimalGame.MAX_HINTS

        # Disable this button on the current message first
        await interaction.response.edit_message(view=self)

        if is_final:
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{AnimalGame.MAX_HINTS} — Final Hint!",
                description=f"The animal name scrambled: **{_scramble(game.animal)}**",
                color=discord.Color.red(),
            )
            embed.set_footer(text=footer)
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{AnimalGame.MAX_HINTS}",
                description="Here's another look!",
                color=discord.Color.gold(),
            )
            embed.set_image(url=game.pop_image())
            embed.set_footer(text=footer)
            await interaction.followup.send(
                embed=embed,
                view=AnimalHintView(self.cog, self.channel_id),
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class AnimalGuesser(commands.Cog):
    """Animal guessing game — who can identify the mystery animal from a photo?"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, AnimalGame] = {}   # channel_id → AnimalGame

    # ── Image fetching ────────────────────────────────────────────────────────

    async def _fetch_images(self, animal: str, max_count: int = 35) -> list[str]:
        """Return up to *max_count* photo URLs from the iNaturalist API.

        Two-step approach: first resolve the animal name to an exact taxon
        ID, then fetch research-grade observations for that specific taxon.
        This prevents mixing species when a common name maps to a broad
        group (e.g. 'Eagle' covers 68 species) and eliminates misidentified
        community observations.
        """
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "AnimalGuesserBot/1.0 (Discord Bot)"}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                # Step 1: resolve name → taxon_id
                async with session.get(
                    "https://api.inaturalist.org/v1/taxa",
                    params={"q": animal, "per_page": 1},
                    timeout=timeout,
                ) as resp:
                    taxa_data = await resp.json()

                taxa_results = taxa_data.get("results", [])
                if not taxa_results:
                    return []
                taxon_id = taxa_results[0]["id"]

                # Step 2: fetch research-grade observations for that exact taxon
                async with session.get(
                    "https://api.inaturalist.org/v1/observations",
                    params={
                        "taxon_id": taxon_id,
                        "photos": "true",
                        "per_page": 35,
                        "order_by": "votes",
                        "quality_grade": "research",
                    },
                    timeout=timeout,
                ) as resp:
                    obs_data = await resp.json()

            photos = []
            for obs in obs_data.get("results", []):
                for p in obs.get("photos", []):
                    url = p.get("url", "").replace("square", "medium")
                    if url.startswith("http"):
                        photos.append(url)

            random.shuffle(photos)
            return photos[:max_count]
        except Exception:
            return []

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, animal: str):
        """Background task that ends the round after 60 seconds."""
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return  # game was won; task cancelled by on_message handler

        if channel.id not in self.games:
            return

        del self.games[channel.id]
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The animal was **{animal}**.",
            color=discord.Color(0x99aab5),   # Discord greyple
        )
        await channel.send(embed=embed)

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    async def animalguesser(self, ctx: commands.Context):
        """Start an animal guessing game. 60 seconds — can you name it?"""
        if ctx.channel.id in self.games:
            await ctx.send(
                "A game is already running here! "
                "Type your guess or `$hint` for another image."
            )
            return

        animal = random.choice(ANIMALS)
        loading = await ctx.send("Searching for images...")

        images = await self._fetch_images(animal)
        if not images:
            await loading.edit(content="Couldn't fetch images right now. Please try again!")
            return

        task = asyncio.create_task(self._game_timer(ctx.channel, animal))
        game = AnimalGame(animal, images, task)
        self.games[ctx.channel.id] = game

        embed = discord.Embed(
            title=f"What animal is this?{DEV_LABEL}",
            description=(
                "Type your guess in chat — anyone can answer!\n"
                "You have **60 seconds**. Use the **Hint** button below *(4 max, last hint scrambles the name)*."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_image(url=game.pop_image())
        await loading.edit(content=None, embed=embed, view=AnimalHintView(self, ctx.channel.id))

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

        if message.content.strip().lower() != game.animal.lower():
            return

        # ── Correct guess ──────────────────────────────────────────────────
        game.task.cancel()
        del self.games[message.channel.id]

        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!\n\n"
                f"The animal was **{game.animal}**! Congratulations!"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Start a new game any time with $animalguesser!")
        await message.channel.send(embed=embed)

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
