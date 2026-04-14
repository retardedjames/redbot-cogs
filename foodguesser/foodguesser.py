import asyncio
import pathlib
import random
import re
import string
import time
import unicodedata

import discord
from redbot.core import commands

from .food_data import FOOD_DATA
from .foods import FOODS

TOTAL_FOODS = len(FOODS)

# ── Images directory ──────────────────────────────────────────────────────────
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_LOCAL = pathlib.Path(__file__).parent / "images"
_VPS   = pathlib.Path("/home/ubuntu/redbot/cogs/foodguesser/images")

if _LOCAL.is_dir():
    IMAGES_DIR = _LOCAL
elif _VPS.is_dir():
    IMAGES_DIR = _VPS
else:
    IMAGES_DIR = _LOCAL  # will return empty lists; triggers "no images" message

# ── Constants ─────────────────────────────────────────────────────────────────
_24H             = 86_400
MAX_EXTRA_IMAGES = 3       # 4 images downloaded per food; 1 shown initially → 3 via n
TIMEOUT_SECONDS  = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Match the sanitisation used by download_images.py."""
    s = name.lower()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _normalize(text: str) -> str:
    """Lowercase + strip accents + strip punctuation — for guess comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if ord(c) < 128)
    lower = ascii_only.lower()
    return lower.translate(str.maketrans("", "", string.punctuation)).strip()


def _scramble(name: str) -> str:
    """Scramble each word of the name independently, respecting spaces."""
    return " ".join(
        "".join(random.sample(list(w), len(w))) for w in name.split()
    )


# ── Play Again button ─────────────────────────────────────────────────────────

class PlayAgainView(discord.ui.View):
    def __init__(self, cog: "FoodGuesser", channel_id: int):
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


# ── Game state ────────────────────────────────────────────────────────────────

class FoodGame:
    def __init__(self, food: str, images: list, task: asyncio.Task):
        self.food = food
        self.images = images                   # list[pathlib.Path], pre-shuffled
        self.used_images: set[int] = set()     # indices already shown
        self.task = task
        self.extra_images_shown: int = 0
        self.hint_index: int = 0               # 0=origin+ingredients, 1=letter+length, 2=scrambled
        self.participants: set = set()

    def pop_image(self) -> "pathlib.Path | None":
        unused = [i for i in range(len(self.images)) if i not in self.used_images]
        if not unused:
            return None
        idx = random.choice(unused)
        self.used_images.add(idx)
        return self.images[idx]


# ── Cog ───────────────────────────────────────────────────────────────────────

class FoodGuesser(commands.Cog):
    """Guess the food from its photo — 30 seconds, up to 3 hints."""

    _IS_IMAGE_GUESSER = True
    _DISPLAY_NAME = "Food Guesser"

    # Shared across all channels: food name → timestamp of last use
    _used_recently: dict[str, float] = {}

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, FoodGame] = {}

    def _rival_game_running(self, channel_id: int) -> "str | None":
        for cog in self.bot.cogs.values():
            if cog is self:
                continue
            if getattr(cog, "_IS_IMAGE_GUESSER", False) and channel_id in getattr(cog, "games", {}):
                return getattr(cog, "_DISPLAY_NAME", type(cog).__name__)
        return None

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_images(self, food: str) -> list:
        folder = IMAGES_DIR / slugify(food)
        if not folder.is_dir():
            return []
        paths = [
            p for p in folder.iterdir()
            if p.suffix.lower() in _IMAGE_EXTS and p.is_file()
        ]
        random.shuffle(paths)
        return paths

    # ── Food selection ────────────────────────────────────────────────────────

    def _pick_food(self) -> "tuple[str, list] | None":
        now = time.time()
        FoodGuesser._used_recently = {
            k: v for k, v in FoodGuesser._used_recently.items()
            if now - v < _24H
        }

        fresh = [f for f in FOODS if f not in FoodGuesser._used_recently]
        pool = fresh if fresh else list(FOODS)

        random.shuffle(pool)
        for food in pool:
            imgs = self._load_images(food)
            if imgs:
                FoodGuesser._used_recently[food] = now
                return food, imgs
        return None

    # ── Game timer ────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, food: str):
        try:
            await asyncio.sleep(TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return

        game = self.games.pop(channel.id, None)
        if game is None:
            return

        tp = self.bot.get_cog("TrackPoints")
        if tp:
            await tp.record_game_result(None, game.participants)

        data = FOOD_DATA.get(food, {})
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The answer was **{food}**.",
            color=discord.Color(0x99aab5),
        )
        if data.get("origin"):
            embed.add_field(name="Origin", value=data["origin"], inline=False)
        if data.get("ingredients"):
            embed.add_field(
                name="Key Ingredients",
                value=", ".join(data["ingredients"]),
                inline=False,
            )
        await channel.send(embed=embed, view=PlayAgainView(self, channel.id))

    # ── Start a new game ──────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        rival = self._rival_game_running(channel.id)
        if rival:
            await channel.send(f"**{rival}** is already running here! Finish that game first.")
            return

        result = self._pick_food()
        if result is None:
            await channel.send(
                "No food images found on disk. "
                "Run the download script on the server to populate the image library."
            )
            return

        food, images = result
        task = asyncio.create_task(self._game_timer(channel, food))
        game = FoodGame(food, images, task)
        self.games[channel.id] = game

        first_image = game.pop_image()
        embed = discord.Embed(
            title="What food dish is this?",
            description=(
                f"Randomly chosen from **{TOTAL_FOODS:,}** dishes.\n\n"
                f"Type **`n`** — another photo (up to {MAX_EXTRA_IMAGES} extra)\n"
                f"Type **`h`** — hint\n"
                f"You have **{TIMEOUT_SECONDS} seconds**!"
            ),
            color=discord.Color.orange(),
        )
        embed.set_image(url="attachment://food.jpg")
        await channel.send(
            embed=embed,
            file=discord.File(first_image, filename="food.jpg"),
        )

    # ── $fg command ───────────────────────────────────────────────────────────

    @commands.command(name="fg")
    async def food_guesser(self, ctx: commands.Context):
        """Start a Food Guesser game. If one is running, reveal it and start fresh."""
        if ctx.channel.id in self.games:
            game = self.games.pop(ctx.channel.id)
            game.task.cancel()
            embed = discord.Embed(
                title="New round!",
                description=(
                    f"The answer was **{game.food}**.\n"
                    "Starting a new game..."
                ),
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)

        await self._start_game(ctx.channel)

    # ── on_message: n / h / guesses ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        lower = content.lower()

        # ── n: next image ─────────────────────────────────────────────────────
        if lower == "n":
            if game.extra_images_shown >= MAX_EXTRA_IMAGES:
                await message.channel.send(
                    f"No more extra images! (max {MAX_EXTRA_IMAGES} extra)"
                )
                return
            img = game.pop_image()
            if img is None:
                await message.channel.send("No more photos available for this dish.")
                return
            game.extra_images_shown += 1
            remaining = MAX_EXTRA_IMAGES - game.extra_images_shown
            embed = discord.Embed(
                title=f"Another look! ({game.extra_images_shown}/{MAX_EXTRA_IMAGES})",
                description=(
                    f"{remaining} more photo(s) available."
                    if remaining > 0 else "That's all the extra photos!"
                ),
                color=discord.Color.blue(),
            )
            embed.set_image(url="attachment://food.jpg")
            await message.channel.send(
                embed=embed,
                file=discord.File(img, filename="food.jpg"),
            )
            return

        # ── h: hint ───────────────────────────────────────────────────────────
        if lower == "h":
            idx = game.hint_index
            data = FOOD_DATA.get(game.food, {})

            if idx == 0:
                # Hint 1: country of origin + ingredients
                origin = data.get("origin", "Unknown")
                ingredients = data.get("ingredients", [])
                ing_str = ", ".join(ingredients) if ingredients else "Unknown"
                embed = discord.Embed(
                    title="Hint 1 — Origin & Ingredients",
                    color=discord.Color.gold(),
                )
                embed.add_field(name="Country of Origin", value=origin, inline=False)
                embed.add_field(name="Key Ingredients", value=ing_str, inline=False)

            elif idx == 1:
                # Hint 2: first letter + character count
                words = game.food.split()
                first_letter = game.food[0].upper()
                char_count = sum(len(w) for w in words)
                desc = f"Starts with **{first_letter}** — **{char_count}** characters"
                if len(words) > 1:
                    desc += f" ({len(words)} words)"
                embed = discord.Embed(
                    title="Hint 2 — Name",
                    description=desc,
                    color=discord.Color.gold(),
                )

            elif idx == 2:
                # Hint 3: scrambled name (respecting spaces)
                embed = discord.Embed(
                    title="Hint 3 — Scrambled Name",
                    description=f"**{_scramble(game.food)}**",
                    color=discord.Color.orange(),
                )
                embed.set_footer(text="No more hints after this one!")

            else:
                await message.channel.send("No more hints available!")
                return

            game.hint_index += 1
            await message.channel.send(embed=embed)
            return

        # ── Guess ─────────────────────────────────────────────────────────────
        guess = _normalize(content)
        answer = _normalize(game.food)

        game.participants.add(message.author)

        if guess != answer:
            return

        # Correct!
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
                f"The answer was **{game.food}**! Congratulations!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Start a new game with $fg!")
        await message.channel.send(embed=embed, view=PlayAgainView(self, message.channel.id))

    # ── Gamestop integration ──────────────────────────────────────────────────

    async def clear_recent_memory(self, guild=None) -> str:
        FoodGuesser._used_recently.clear()
        return "Food Guesser"

    async def force_stop_game(self, channel_id: int):
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()
        return "Food Guesser"

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
