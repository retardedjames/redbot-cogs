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
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The animal was **{animal}**.",
            color=discord.Color(0x99aab5),
        )
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
        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!{pts_line}\n\n"
                f"The animal was **{game.animal}**! Congratulations!"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Start a new game any time with $animalguesser!")
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
