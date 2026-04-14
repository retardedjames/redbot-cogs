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


# ── Fruit list (~120 fruits) ──────────────────────────────────────────────────

FRUITS = [
    # Apples
    "Apple", "Fuji Apple", "Honeycrisp Apple", "Granny Smith Apple",
    "Gala Apple", "Braeburn Apple", "Pink Lady Apple", "McIntosh Apple",
    # Pears
    "Pear", "Bartlett Pear", "Asian Pear", "Bosc Pear",
    # Citrus
    "Orange", "Blood Orange", "Clementine", "Tangerine", "Mandarin",
    "Grapefruit", "Pomelo", "Lemon", "Lime", "Meyer Lemon", "Kumquat",
    "Yuzu", "Bergamot", "Cara Cara Orange", "Satsuma", "Ugli Fruit",
    # Berries
    "Strawberry", "Raspberry", "Blueberry", "Blackberry", "Cranberry",
    "Gooseberry", "Boysenberry", "Elderberry", "Mulberry", "Huckleberry",
    "Lingonberry", "Cloudberry", "Acai",
    # Stone Fruits
    "Peach", "Nectarine", "Plum", "Cherry", "Apricot", "Damson Plum",
    # Tropical (common)
    "Banana", "Plantain", "Pineapple", "Mango", "Papaya", "Coconut",
    "Guava", "Passion Fruit", "Dragon Fruit", "Lychee", "Longan",
    "Rambutan", "Jackfruit", "Durian", "Mangosteen", "Starfruit",
    # Tropical (less common but recognizable)
    "Soursop", "Cherimoya", "Feijoa", "Tamarind", "Breadfruit",
    "Ackee", "Sapodilla", "Sugar Apple", "Mamey Sapote", "Jabuticaba",
    # Melons
    "Watermelon", "Cantaloupe", "Honeydew Melon", "Canary Melon",
    "Galia Melon", "Crenshaw Melon",
    # Grapes
    "Grape", "Concord Grape", "Moondrop Grape", "Cotton Candy Grape",
    "Muscat Grape",
    # Other common
    "Kiwi", "Golden Kiwi", "Fig", "Date", "Pomegranate", "Avocado",
    "Persimmon", "Quince", "Loquat", "Currant", "Olive", "Noni",
    "Finger Lime",
]

# ── Image library ─────────────────────────────────────────────────────────────

IMAGES_DIR = pathlib.Path(__file__).parent / "images"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ── Helpers ───────────────────────────────────────────────────────────────────

_WORD_COUNT_NAMES = {2: "Two", 3: "Three", 4: "Four", 5: "Five"}


def _scramble(name: str) -> str:
    """Scramble each word in the fruit name independently."""
    words = name.split()
    scrambled = []
    for word in words:
        letters = list(word)
        random.shuffle(letters)
        scrambled.append("".join(letters))
    return " ".join(scrambled)


def _build_first_hint(fruit: str) -> str:
    """Return the first hint string: first letter, letter count, word count."""
    words = fruit.split()
    first_letter = fruit[0].upper()
    letter_count = sum(len(w) for w in words)
    line = f"Starts with letter **{first_letter}** and is **{letter_count}** letters long"
    if len(words) > 1:
        word_label = _WORD_COUNT_NAMES.get(len(words), str(len(words)))
        line += f"\n{word_label} words"
    return line


# ── Game state ────────────────────────────────────────────────────────────────

class FruitGame:
    MAX_HINTS = 3

    def __init__(self, fruit: str, images: list, task: asyncio.Task):
        self.fruit = fruit
        self.images = images          # list[pathlib.Path]
        self.used: set = set()        # indices already shown this round
        self.hints_used = 0
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


# ── Hint button ───────────────────────────────────────────────────────────────

class FruitHintView(discord.ui.View):
    """Single-use green Hint button. Disables itself when clicked, then sends
    the next hint as a followup (with a fresh button if hints remain)."""

    def __init__(self, cog: "FruitGuesser", channel_id: int):
        super().__init__(timeout=70)
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
        if game.hints_used >= FruitGame.MAX_HINTS:
            await interaction.response.send_message(
                f"All **{FruitGame.MAX_HINTS}** hints have been used — keep guessing!",
                ephemeral=True,
            )
            return

        self._used = True
        button.disabled = True
        game.hints_used += 1
        remaining = FruitGame.MAX_HINTS - game.hints_used
        footer = f"{remaining} hint(s) remaining." if remaining else "No more hints after this!"
        is_final = game.hints_used == FruitGame.MAX_HINTS

        await interaction.response.edit_message(view=self)

        if game.hints_used == 1:
            # First hint: letter / word count info
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{FruitGame.MAX_HINTS}",
                description=_build_first_hint(game.fruit),
                color=discord.Color.gold(),
            )
            embed.set_footer(text=footer)
            await interaction.followup.send(
                embed=embed,
                view=FruitHintView(self.cog, self.channel_id),
            )
        elif is_final:
            # Last hint: scrambled name
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{FruitGame.MAX_HINTS} — Final Hint!",
                description=f"The fruit name scrambled: **{_scramble(game.fruit)}**",
                color=discord.Color.red(),
            )
            embed.set_footer(text=footer)
            await interaction.followup.send(embed=embed)
        else:
            # Middle hints: another image
            path = game.pop_image()
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{FruitGame.MAX_HINTS}",
                description="Here's another look!",
                color=discord.Color.gold(),
            )
            embed.set_footer(text=footer)
            embed.set_image(url="attachment://hint.jpg")
            await interaction.followup.send(
                embed=embed,
                file=discord.File(path, filename="hint.jpg"),
                view=FruitHintView(self.cog, self.channel_id),
            )


# ── Play Again button ─────────────────────────────────────────────────────────

class FruitPlayAgainView(discord.ui.View):
    def __init__(self, cog: "FruitGuesser", channel_id: int):
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

class FruitGuesser(commands.Cog):
    """Fruit guessing game — who can identify the mystery fruit from a photo?"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, FruitGame] = {}   # channel_id → FruitGame

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_images(self, fruit: str) -> list:
        """Return a shuffled list of image Paths from the fruit's folder."""
        folder = IMAGES_DIR / fruit
        if not folder.is_dir():
            return []
        paths = [p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_EXTS and p.is_file()]
        random.shuffle(paths)
        return paths

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, fruit: str):
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
            description=f"Nobody guessed it. The fruit was **{fruit}**.",
            color=discord.Color(0x99aab5),
        )
        await channel.send(embed=embed, view=FruitPlayAgainView(self, channel.id))

    # ── Start game ────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        fruit, images = None, []
        for candidate in random.sample(FRUITS, len(FRUITS)):
            imgs = self._load_images(candidate)
            if imgs:
                fruit, images = candidate, imgs
                break

        if fruit is None:
            await channel.send(
                "No fruit images found on disk. "
                "Run `python fruitguesser/download_images.py` to download the image library first."
            )
            return

        task = asyncio.create_task(self._game_timer(channel, fruit))
        game = FruitGame(fruit, images, task)
        self.games[channel.id] = game

        embed = discord.Embed(
            title=f"What fruit is this??{DEV_LABEL}",
            description=(
                "Type your guess in chat — anyone can answer!\n"
                "You have **60 seconds**. Use the **Hint** button below *(3 max)*."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Hint 1: letter/length info  |  Hint 2: another image  |  Hint 3: scrambled name")
        embed.set_image(url="attachment://fruit.jpg")

        first_image = game.pop_image()
        await channel.send(
            embed=embed,
            file=discord.File(first_image, filename="fruit.jpg"),
            view=FruitHintView(self, channel.id),
        )

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    async def fruitguesser(self, ctx: commands.Context):
        """Start a fruit guessing game. 60 seconds — can you name it?"""
        if ctx.channel.id in self.games:
            await ctx.send(
                "A game is already running here! "
                "Type your guess or use the Hint button for another image."
            )
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

        # Ignore valid bot commands (e.g. $fruitguesser)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        game.participants.add(message.author)

        if message.content.strip().lower() != game.fruit.lower():
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
                f"The fruit was **{game.fruit}**! Congratulations!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Start a new game any time with $fruitguesser!")
        await message.channel.send(embed=embed, view=FruitPlayAgainView(self, message.channel.id))

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()
        return "Fruit Guesser"

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
