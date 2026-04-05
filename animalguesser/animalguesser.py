import asyncio
import random

import aiohttp
import discord
from redbot.core import commands


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

class AnimalGame:
    MAX_HINTS = 3

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


# ── Cog ───────────────────────────────────────────────────────────────────────

class AnimalGuesser(commands.Cog):
    """Animal guessing game — who can identify the mystery animal from a photo?"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, AnimalGame] = {}   # channel_id → AnimalGame

    # ── Image fetching ────────────────────────────────────────────────────────

    async def _fetch_images(self, animal: str, max_count: int = 35) -> list[str]:
        """Return up to *max_count* photo URLs from the iNaturalist API."""
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "AnimalGuesserBot/1.0 (Discord Bot)"}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    "https://api.inaturalist.org/v1/observations",
                    params={
                        "taxon_name": animal,
                        "photos": "true",
                        "per_page": 35,
                        "order_by": "votes",
                    },
                    timeout=timeout,
                ) as resp:
                    data = await resp.json()

            photos = []
            for obs in data.get("results", []):
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
            title="What animal is this?",
            description=(
                "Type your guess in chat — anyone can answer!\n"
                "You have **60 seconds**. Type `$hint` for another image *(3 max)*."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_image(url=game.pop_image())
        await loading.edit(content=None, embed=embed)

    @commands.command()
    async def hint(self, ctx: commands.Context):
        """Get a new image clue for the current animal guessing game."""
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No game is running here. Start one with `$animalguesser`!")
            return
        if game.hints_used >= AnimalGame.MAX_HINTS:
            await ctx.send("All **3** hints have been used — keep guessing!")
            return

        game.hints_used += 1
        remaining = AnimalGame.MAX_HINTS - game.hints_used
        footer = f"{remaining} hint(s) remaining." if remaining else "No more hints after this!"

        embed = discord.Embed(
            title=f"Hint {game.hints_used}/{AnimalGame.MAX_HINTS}",
            description="Here's another look!",
            color=discord.Color.gold(),
        )
        embed.set_image(url=game.pop_image())
        embed.set_footer(text=footer)
        await ctx.send(embed=embed)

    # ── Guess listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        # Ignore valid bot commands (e.g. $hint, $animalguesser)
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
