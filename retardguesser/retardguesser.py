import asyncio
import pathlib
import random
import re
import string
import time
import unicodedata

import discord
from redbot.core import commands

# ── People database ───────────────────────────────────────────────────────────
from .people_data import PEOPLE as _P1
from .csv_people_data import CSV_PEOPLE as _P2

PEOPLE: dict = {**_P1, **_P2}
TOTAL_PEOPLE = len(PEOPLE)

# ── Images directory ──────────────────────────────────────────────────────────
# Primary: next to the installed cog file.
# Fallback: VPS working directory used when images aren't copied into the cog.
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_LOCAL = pathlib.Path(__file__).parent / "images"
_VPS   = pathlib.Path("/home/ubuntu/redbot/cogs/retardguesser/images")

if _LOCAL.is_dir():
    IMAGES_DIR = _LOCAL
elif _VPS.is_dir():
    IMAGES_DIR = _VPS
else:
    IMAGES_DIR = _LOCAL  # will return empty lists; triggers the "no images" message

# ── Constants ─────────────────────────────────────────────────────────────────
_24H             = 86_400          # seconds in 24 hours
MAX_EXTRA_IMAGES = 5               # extra photos per game
TIMEOUT_SECONDS  = 90              # seconds until round ends


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_folder(name: str) -> str:
    """Match the sanitisation used by download_images.py."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ") or "unknown"


def _normalize(text: str) -> str:
    """Strip accents, lowercase, strip punctuation — for guess comparison."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = no_accent.lower()
    no_punct = lower.translate(str.maketrans("", "", string.punctuation))
    return no_punct.strip()


def _scramble(name: str) -> str:
    """Scramble each word of the name independently."""
    return " ".join(
        "".join(random.sample(list(w), len(w))) for w in name.split()
    )


# ── Game state ────────────────────────────────────────────────────────────────

class PersonGame:
    def __init__(self, person: dict, images: list, task: asyncio.Task):
        self.person = person                   # full dict from PEOPLE
        self.images = images                   # list[pathlib.Path], pre-shuffled
        self.used_images: set[int] = set()     # indices already shown
        self.task = task                       # timeout asyncio.Task
        self.extra_images_shown: int = 0       # how many 'n' images sent
        self.hint_index: int = 0              # next hint slot (0–3; 4 = exhausted)

    def pop_image(self) -> "pathlib.Path | None":
        unused = [i for i in range(len(self.images)) if i not in self.used_images]
        if not unused:
            return None
        idx = random.choice(unused)
        self.used_images.add(idx)
        return self.images[idx]


# ── Cog ───────────────────────────────────────────────────────────────────────

class RetardGuesser(commands.Cog):
    """Guess the famous person — photos, hints, 90 seconds."""

    # Shared across all channels: name → timestamp of last use
    _used_recently: dict[str, float] = {}

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, PersonGame] = {}   # channel_id → PersonGame

    # ── Image loading ─────────────────────────────────────────────────────────

    def _load_images(self, name: str) -> list:
        folder = IMAGES_DIR / _safe_folder(name)
        if not folder.is_dir():
            return []
        paths = [
            p for p in folder.iterdir()
            if p.suffix.lower() in _IMAGE_EXTS and p.is_file()
        ]
        random.shuffle(paths)
        return paths

    # ── Person selection ──────────────────────────────────────────────────────

    def _pick_person(self) -> "tuple[dict, list] | None":
        now = time.time()
        # Purge stale entries
        RetardGuesser._used_recently = {
            k: v for k, v in RetardGuesser._used_recently.items()
            if now - v < _24H
        }

        all_names = list(PEOPLE.keys())
        fresh = [n for n in all_names if n not in RetardGuesser._used_recently]
        pool = fresh if fresh else all_names   # reset if all exhausted

        random.shuffle(pool)
        for name in pool:
            imgs = self._load_images(name)
            if imgs:
                RetardGuesser._used_recently[name] = now
                return PEOPLE[name], imgs
        return None

    # ── Game timer ────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, person_name: str):
        try:
            await asyncio.sleep(TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return

        if channel.id not in self.games:
            return

        del self.games[channel.id]
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The answer was **{person_name}**.",
            color=discord.Color(0x99aab5),
        )
        await channel.send(embed=embed)

    # ── Start a new game ──────────────────────────────────────────────────────

    async def _start_game(self, ctx: commands.Context):
        result = self._pick_person()
        if result is None:
            await ctx.send(
                "No person images found on disk. "
                "Run the download script on the server to populate the image library."
            )
            return

        person, images = result
        task = asyncio.create_task(self._game_timer(ctx.channel, person["name"]))
        game = PersonGame(person, images, task)
        self.games[ctx.channel.id] = game

        first_image = game.pop_image()
        embed = discord.Embed(
            title="Who is this person?",
            description=(
                f"Randomly chosen from **{TOTAL_PEOPLE:,}** famous people.\n\n"
                f"Type **`n`** — another photo (up to {MAX_EXTRA_IMAGES} extra)\n"
                f"Type **`h`** — show a hint\n"
                f"You have **{TIMEOUT_SECONDS} seconds**!"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_image(url="attachment://person.jpg")
        await ctx.send(
            embed=embed,
            file=discord.File(first_image, filename="person.jpg"),
        )

    # ── $rg command ───────────────────────────────────────────────────────────

    @commands.command(name="rg")
    async def retard_guesser(self, ctx: commands.Context):
        """Start a Retard Guesser game. If one is running, reveal it and start fresh."""
        if ctx.channel.id in self.games:
            # Reveal current answer, then immediately start a new game
            game = self.games.pop(ctx.channel.id)
            game.task.cancel()
            embed = discord.Embed(
                title="New round!",
                description=(
                    f"The answer was **{game.person['name']}**.\n"
                    "Starting a new game..."
                ),
                color=discord.Color.orange(),
            )
            await ctx.send(embed=embed)

        await self._start_game(ctx)

    # ── on_message: n / h / guesses ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        # Ignore valid bot commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        lower = content.lower()

        # ── n: next image ─────────────────────────────────────────────────────
        if lower == "n":
            if game.extra_images_shown >= MAX_EXTRA_IMAGES:
                await message.channel.send(
                    f"No more extra images! (max {MAX_EXTRA_IMAGES} shown)"
                )
                return
            img = game.pop_image()
            if img is None:
                await message.channel.send("No more photos available for this person.")
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
            embed.set_image(url="attachment://person.jpg")
            await message.channel.send(
                embed=embed,
                file=discord.File(img, filename="person.jpg"),
            )
            return

        # ── h: hint ───────────────────────────────────────────────────────────
        if lower == "h":
            p = game.person
            idx = game.hint_index

            if idx == 0:
                embed = discord.Embed(
                    title="Hint 1 — Profession",
                    description=f"**{p['profession'].capitalize()}**",
                    color=discord.Color.gold(),
                )
            elif idx == 1:
                embed = discord.Embed(
                    title="Hint 2 — Known For",
                    description=p["known_for"],
                    color=discord.Color.gold(),
                )
            elif idx == 2:
                embed = discord.Embed(
                    title="Hint 3 — Bio",
                    description=p["bio"],
                    color=discord.Color.gold(),
                )
            elif idx == 3:
                embed = discord.Embed(
                    title="Hint 4 — Scrambled Name",
                    description=f"**{_scramble(p['name'])}**",
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
        if _normalize(content) != _normalize(game.person["name"]):
            return

        # Correct answer!
        game.task.cancel()
        del self.games[message.channel.id]

        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!\n\n"
                f"The answer was **{game.person['name']}**! Congratulations!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Start a new game with $rg!")
        await message.channel.send(embed=embed)

    # ── Gamestop integration ──────────────────────────────────────────────────

    async def force_stop_game(self, channel_id: int):
        """Called by the $end (gamestop) command. Returns cog name if stopped."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()
        return "Retard Guesser"

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
