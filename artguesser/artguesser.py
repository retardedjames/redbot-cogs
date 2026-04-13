import asyncio
import pathlib
import random
import re
import time
import unicodedata
from typing import Optional

import discord
from redbot.core import commands

# ── Dev mode ──────────────────────────────────────────────────────────────────
DEV_MODE = True

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

try:
    from .artists import ARTISTS
except ImportError:
    ARTISTS = []

IMAGES_DIR = pathlib.Path(__file__).parent / "images"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_VALID_CATEGORIES = {"modern", "1800s", "old", "ancient"}

# Global 24-hour usage tracker: {artist_name: unix_timestamp}
_used_artists: dict = {}
_USED_EXPIRY = 86400  # 24 hours in seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Strip accents, lowercase, remove punctuation."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = no_accents.lower()
    return re.sub(r"[^\w\s]", "", lower).strip()


def _scramble(name: str) -> str:
    """Scramble each word in the name independently."""
    words = name.split()
    scrambled = []
    for word in words:
        letters = list(word)
        random.shuffle(letters)
        scrambled.append("".join(letters))
    return " ".join(scrambled)


def _blank_name(artist: dict, bio: str) -> str:
    """Replace artist name/surname occurrences in bio with ___."""
    result = bio
    name = artist["name"]
    # Blank full name first
    result = re.sub(re.escape(name), "___", result, flags=re.IGNORECASE)
    # Blank each name part that's meaningfully long (skip particles like "van", "de")
    for part in name.split():
        if len(part) > 2:
            result = re.sub(r"\b" + re.escape(part) + r"\b", "___", result, flags=re.IGNORECASE)
    return result


def _build_hint_order(artist: dict) -> list:
    """
    Build hint sequence for this game.
    Hints 1-7: metadata fields, shuffled, skipping missing/empty.
    Hint 8: bio with name blanked (if bio exists).
    Hint 9: scrambled name (always last).
    """
    meta = []
    if artist.get("nationality"):
        meta.append("nationality")
    if artist.get("year_born") is not None:
        meta.append("year_born")
    if artist.get("year_died") is not None:
        meta.append("year_died")
    if artist.get("medium"):
        meta.append("medium")
    if artist.get("years_active"):
        meta.append("years_active")
    if artist.get("movement"):
        meta.append("movement")
    if artist.get("sub_movements"):
        meta.append("sub_movements")

    random.shuffle(meta)

    order = meta[:]
    if artist.get("bio"):
        order.append("bio")
    order.append("scramble")
    return order


def _render_hint(artist: dict, key: str, hint_num: int, total: int) -> discord.Embed:
    """Build a hint embed for the given hint key."""
    label_map = {
        "nationality":   ("Nationality",    artist.get("nationality", "Unknown")),
        "year_born":     ("Year Born",      str(artist.get("year_born", "Unknown"))),
        "year_died":     ("Year Died",      str(artist.get("year_died", "Unknown"))),
        "medium":        ("Medium",         artist.get("medium", "Unknown")),
        "years_active":  ("Years Active",   artist.get("years_active", "Unknown")),
        "movement":      ("Movement",       artist.get("movement", "Unknown")),
        "sub_movements": ("Sub-movements",  ", ".join(artist.get("sub_movements", []))),
        "bio":           ("About the Artist", _blank_name(artist, artist.get("bio", ""))),
        "scramble":      ("Scrambled Name", f"**{_scramble(artist['name'])}**  *(each word scrambled)*"),
    }

    title_label, value = label_map.get(key, ("Hint", "?"))

    if key == "scramble":
        color = discord.Color.red()
    elif key == "bio":
        color = discord.Color.orange()
    else:
        color = discord.Color.gold()

    embed = discord.Embed(
        title=f"Hint {hint_num}/{total} — {title_label}",
        description=value,
        color=color,
    )
    if key == "scramble":
        embed.set_footer(text="Final hint — good luck!")
    return embed


# ── Game state ────────────────────────────────────────────────────────────────

class ArtGame:
    def __init__(self, artist: dict, images: list, task: asyncio.Task):
        self.artist = artist
        self.images = images                           # list[pathlib.Path]
        self.used_images: set = set()
        self.task = task
        self.hints_given: list = []
        self.hint_order: list = _build_hint_order(artist)
        self.extra_images_shown: int = 0

    def pop_image(self) -> "pathlib.Path | None":
        """Return a not-yet-shown image, cycling if all have been shown."""
        unused = [i for i in range(len(self.images)) if i not in self.used_images]
        if not unused:
            self.used_images.clear()
            unused = list(range(len(self.images)))
        if not unused:
            return None
        idx = random.choice(unused)
        self.used_images.add(idx)
        return self.images[idx]

    def next_hint(self) -> "str | None":
        """Return the next hint key, or None if all hints exhausted."""
        remaining = [h for h in self.hint_order if h not in self.hints_given]
        if not remaining:
            return None
        key = remaining[0]
        self.hints_given.append(key)
        return key


# ── Cog ───────────────────────────────────────────────────────────────────────

class ArtGuesser(commands.Cog):
    """Guess the artist from their artwork!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}   # channel_id → ArtGame

    # ── Artist/image loading ──────────────────────────────────────────────────

    def _load_images(self, artist_name: str) -> list:
        folder = IMAGES_DIR / artist_name
        if not folder.is_dir():
            return []
        paths = [
            p for p in folder.iterdir()
            if p.suffix.lower() in _IMAGE_EXTS and p.is_file()
        ]
        random.shuffle(paths)
        return paths

    def _eligible_artists(self, category: Optional[str]) -> list:
        eligible = []
        for artist in ARTISTS:
            if category and artist.get("category") != category:
                continue
            if self._load_images(artist["name"]):
                eligible.append(artist)
        return eligible

    def _pick_artist(self, category: Optional[str]) -> "tuple":
        """Return (artist_dict, images) preferring artists not used in 24h."""
        eligible = self._eligible_artists(category)
        if not eligible:
            return None, None

        now = time.time()
        # Expire old usage entries
        for k in [k for k, ts in _used_artists.items() if now - ts > _USED_EXPIRY]:
            del _used_artists[k]

        unused = [a for a in eligible if a["name"] not in _used_artists]
        pool = unused if unused else eligible  # if all used, allow any

        artist = random.choice(pool)
        _used_artists[artist["name"]] = now

        images = self._load_images(artist["name"])
        return artist, images

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, artist_name: str):
        """Reveal the answer after 90 seconds if nobody guesses."""
        try:
            await asyncio.sleep(90)
        except asyncio.CancelledError:
            return

        if channel.id not in self.games:
            return

        del self.games[channel.id]
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The artist was **{artist_name}**.",
            color=discord.Color(0x99aab5),
        )
        await channel.send(embed=embed)

    # ── $art ──────────────────────────────────────────────────────────────────

    @commands.command(name="art")
    async def art(self, ctx: commands.Context, category: Optional[str] = None):
        """Start an art guessing game. Optional category: modern, 1800s, old, ancient."""
        if category and category.lower() not in _VALID_CATEGORIES:
            await ctx.send(
                f"Unknown category **{category}**. "
                f"Valid: {', '.join(sorted(_VALID_CATEGORIES))}"
            )
            return
        if category:
            category = category.lower()

        # If a game is already running: reveal answer, then immediately start new game
        if ctx.channel.id in self.games:
            old = self.games.pop(ctx.channel.id)
            old.task.cancel()
            embed = discord.Embed(
                title="New game starting!",
                description=f"The previous artist was **{old.artist['name']}**.",
                color=discord.Color(0x99aab5),
            )
            await ctx.send(embed=embed)

        if not ARTISTS:
            await ctx.send(
                "No artists loaded yet. Add artists to `artguesser/artists.py` to play!"
            )
            return

        artist, images = self._pick_artist(category)
        if artist is None:
            msg = "No artists with local images found"
            if category:
                msg += f" for category **{category}**"
            await ctx.send(msg + ".")
            return

        task = asyncio.create_task(self._game_timer(ctx.channel, artist["name"]))
        game = ArtGame(artist, images, task)
        self.games[ctx.channel.id] = game

        first_image = game.pop_image()

        embed = discord.Embed(
            title=f"Guess the Artist!{DEV_LABEL}",
            description=(
                "Who created this artwork? Type your guess in chat!\n"
                "You have **90 seconds**.\n\n"
                "`$img` — show another artwork by this artist *(up to 5)*\n"
                "`$hint` — reveal a hint about the artist"
            ),
            color=discord.Color.blurple(),
        )
        if category:
            embed.set_footer(text=f"Category: {category}")
        embed.set_image(url="attachment://art.jpg")

        await ctx.send(
            embed=embed,
            file=discord.File(first_image, filename="art.jpg"),
        )

    # ── $img ──────────────────────────────────────────────────────────────────

    @commands.command(name="img")
    async def img(self, ctx: commands.Context):
        """Show another artwork image from the current mystery artist (up to 5 extra)."""
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No art game is running here. Start one with `$art`!")
            return

        MAX_EXTRA = 5
        if game.extra_images_shown >= MAX_EXTRA:
            await ctx.send(f"Already shown {MAX_EXTRA} extra images — no more available!")
            return

        path = game.pop_image()
        if path is None:
            await ctx.send("No more images available for this artist.")
            return

        game.extra_images_shown += 1
        remaining = MAX_EXTRA - game.extra_images_shown

        embed = discord.Embed(
            title=f"Another artwork ({game.extra_images_shown}/{MAX_EXTRA})",
            description=(
                f"{remaining} more available with `$img`."
                if remaining > 0 else "That's the last extra image!"
            ),
            color=discord.Color.blue(),
        )
        embed.set_image(url="attachment://art.jpg")
        await ctx.send(embed=embed, file=discord.File(path, filename="art.jpg"))

    # ── $hint ─────────────────────────────────────────────────────────────────

    @commands.command(name="hint")
    async def hint(self, ctx: commands.Context):
        """Reveal the next hint about the mystery artist."""
        game = self.games.get(ctx.channel.id)
        if not game:
            await ctx.send("No art game is running here. Start one with `$art`!")
            return

        key = game.next_hint()
        if key is None:
            await ctx.send("No more hints! Make your best guess.")
            return

        total = len(game.hint_order)
        given = len(game.hints_given)
        embed = _render_hint(game.artist, key, given, total)
        await ctx.send(embed=embed)

    # ── Guess listener ────────────────────────────────────────────────────────

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

        guess = _normalize(message.content.strip())
        answer = game.artist["name"]
        answer_norm = _normalize(answer)

        correct = (guess == answer_norm)

        # Accept partial surname match (e.g. "van Gogh" matches "Vincent van Gogh")
        if not correct:
            parts = answer.split()
            for start in range(1, len(parts)):
                partial = _normalize(" ".join(parts[start:]))
                if partial and guess == partial:
                    correct = True
                    break

        if not correct:
            return

        # Correct guess!
        game.task.cancel()
        del self.games[message.channel.id]

        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!\n\n"
                f"The artist was **{answer}**! Congratulations!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Start a new game with $art!")
        await message.channel.send(embed=embed)

    # ── Gamestop integration ──────────────────────────────────────────────────

    async def force_stop_game(self, channel_id: int) -> "Optional[str]":
        """Cancel any active game in this channel. Returns 'Art Guesser' if stopped."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()
        return "Art Guesser"

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
