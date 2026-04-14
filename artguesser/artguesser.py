import asyncio
import pathlib
import random
import re
import time
import unicodedata
from typing import Optional

import discord
from redbot.core import commands

try:
    from .artists import ARTISTS
except ImportError:
    ARTISTS = {}

# Convert dict-format ARTISTS to list of dicts with 'name' key
ARTISTS_LIST = [{"name": name, **data} for name, data in ARTISTS.items()]

# Images live at /var/www/html/artimages/{artist_name}/ on the VPS
IMAGES_BASE_DIR = pathlib.Path("/var/www/html/artimages")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_USED_EXPIRY = 86400  # 24 hours in seconds

# Global 24-hour usage tracker: {artist_name: unix_timestamp}
_used_artists: dict = {}


# ── Name helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Strip accents, lowercase, remove punctuation."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", "", no_accents.lower()).strip()


def _get_answer_and_display(name: str) -> tuple:
    """
    Returns (answer, display_name):
    - Multi-word artist: last word is the answer, shown as escaped underscores.
    - Single-word artist: last half of chars is the answer, shown as escaped underscores.
    Underscores are escaped with \\ so Discord renders them literally.
    """
    words = name.split()
    if len(words) > 1:
        answer = words[-1]
        prefix = " ".join(words[:-1])
        blanks = r"\_" * len(answer)
        return answer, f"{prefix} {blanks}"
    else:
        mid = len(name) // 2
        answer = name[mid:]
        blanks = r"\_" * len(answer)
        return answer, f"{name[:mid]}{blanks}"


def _scramble(text: str) -> str:
    """Scramble each word independently, lowercase."""
    result = []
    for word in text.lower().split():
        letters = list(word)
        random.shuffle(letters)
        result.append("".join(letters))
    return " ".join(result)


# ── Local image loading ───────────────────────────────────────────────────────

def _load_artist_images(artist_name: str) -> list:
    """Return a shuffled list of image Paths from the artist's local folder."""
    folder = IMAGES_BASE_DIR / artist_name
    if not folder.is_dir():
        return []
    paths = sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in _IMAGE_EXTS and p.is_file()
    )
    random.shuffle(paths)
    return paths


# ── Play Again button ─────────────────────────────────────────────────────────

class ArtPlayAgainView(discord.ui.View):
    def __init__(self, cog: "ArtGuesser", channel_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green, emoji="🎨")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.channel_id in self.cog.games:
            await interaction.response.send_message(
                "A game is already running here!", ephemeral=True
            )
            return
        await interaction.response.defer()
        await self.cog._start_game(interaction.channel)


# ── Game state ────────────────────────────────────────────────────────────────

class ArtGame:
    def __init__(self, artist: dict, image_paths: list, task: asyncio.Task,
                 answer: str, display_name: str):
        self.artist = artist
        self.image_paths = image_paths       # list[pathlib.Path]
        self.used_indices: set = set()        # indices already shown
        self.task = task
        self.answer = answer                  # hidden part to guess
        self.display_name = display_name      # e.g. "Vincent van \_\_\_\_"
        self.hint_count = 0                   # 0=none, 1=bio+movements, 2=scramble
        self.participants: set = set()

    def pick_images(self, count: int = 4) -> list:
        """Pick `count` not-yet-shown image Paths, cycling if all exhausted."""
        available = [i for i in range(len(self.image_paths)) if i not in self.used_indices]
        if len(available) < count:
            # Cycle: clear used set and pull from all
            self.used_indices.clear()
            available = list(range(len(self.image_paths)))
        if not available:
            return []
        chosen = random.sample(available, min(count, len(available)))
        self.used_indices.update(chosen)
        return [self.image_paths[i] for i in chosen]


# ── Cog ───────────────────────────────────────────────────────────────────────

class ArtGuesser(commands.Cog):
    """Guess the artist from their artwork!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}   # channel_id → ArtGame

    # ── Artist picking ────────────────────────────────────────────────────────

    def _pick_artist(self) -> dict:
        """Return an artist dict, preferring artists not seen in the last 24h."""
        if not ARTISTS_LIST:
            return None

        now = time.time()
        for k in [k for k, ts in list(_used_artists.items()) if now - ts > _USED_EXPIRY]:
            del _used_artists[k]

        unused = [a for a in ARTISTS_LIST if a["name"] not in _used_artists]
        pool = unused if unused else ARTISTS_LIST

        artist = random.choice(pool)
        _used_artists[artist["name"]] = now
        return artist

    # ── Info embed builder ────────────────────────────────────────────────────

    def _build_info_embed(self, game: ArtGame, image_url: Optional[str] = None) -> discord.Embed:
        artist = game.artist
        meta_parts = []
        if artist.get("nationality"):
            meta_parts.append(artist["nationality"])
        if artist.get("medium"):
            meta_parts.append(artist["medium"].title())
        if artist.get("years_active"):
            meta_parts.append(f"Active {artist['years_active']}")
        if artist.get("main_movement"):
            meta_parts.append(artist["main_movement"])

        meta_line = " | ".join(meta_parts) if meta_parts else "Unknown"

        desc = (
            f"## {game.display_name}\n"
            f"{meta_line}\n\n"
            f"Type **`h`** for a hint  ·  Type **`n`** for new images"
        )

        embed = discord.Embed(
            title="Guess the Artist!",
            description=desc,
            color=discord.Color.blurple(),
        )
        if image_url:
            embed.set_image(url=image_url)
        return embed

    # ── Image sending helper ──────────────────────────────────────────────────

    async def _send_images(self, target, game: ArtGame, paths: list, info_first: bool = False):
        """Send images as Discord file attachments (triggers gallery view for multiple images)."""
        files = [discord.File(path, filename=f"art{i}.jpg") for i, path in enumerate(paths)]
        if info_first:
            embed = self._build_info_embed(game)  # no image_url — files appear as gallery below
            await target.send(embed=embed, files=files)
        else:
            await target.send(files=files)

    # ── Game start (shared by $arg and Play Again) ────────────────────────────

    async def _start_game(self, channel: discord.TextChannel, artist_name: Optional[str] = None):
        if not ARTISTS_LIST:
            await channel.send("No artists loaded. Add entries to `artists.py` to play!")
            return

        if artist_name:
            artist = next((a for a in ARTISTS_LIST if a["name"].lower() == artist_name.lower()), None)
            if artist is None:
                await channel.send(f"Artist `{artist_name}` not found in the list.")
                return
        else:
            artist = self._pick_artist()
        if artist is None:
            await channel.send("Could not pick an artist — please try again.")
            return

        answer, display_name = _get_answer_and_display(artist["name"])
        image_paths = _load_artist_images(artist["name"])

        task = asyncio.create_task(self._game_timer(channel, artist["name"]))
        game = ArtGame(artist, image_paths, task, answer, display_name)
        self.games[channel.id] = game

        if image_paths:
            chosen = game.pick_images(4)
            await self._send_images(channel, game, chosen, info_first=True)
        else:
            embed = self._build_info_embed(game)
            embed.set_footer(text="No images available for this artist yet.")
            await channel.send(embed=embed)

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, artist_name: str):
        try:
            await asyncio.sleep(120)
        except asyncio.CancelledError:
            return

        game = self.games.pop(channel.id, None)
        if game is None:
            return

        tp = self.bot.get_cog("TrackPoints")
        if tp:
            await tp.record_game_result(None, game.participants)

        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The artist was **{artist_name}**.",
            color=discord.Color(0x99aab5),
        )
        await channel.send(embed=embed, view=ArtPlayAgainView(self, channel.id))

    # ── $arg ──────────────────────────────────────────────────────────────────

    @commands.command(name="arg")
    async def arg(self, ctx: commands.Context):
        """Start an art guessing game. Running during a game reveals the answer and starts a new one."""
        # If a game is already running: reveal answer, then start a new game
        if ctx.channel.id in self.games:
            old = self.games.pop(ctx.channel.id)
            old.task.cancel()
            embed = discord.Embed(
                title="New game!",
                description=f"The previous artist was **{old.artist['name']}**.",
                color=discord.Color(0x99aab5),
            )
            await ctx.send(embed=embed)

        # To re-enable test mode: uncomment below and add `subcommand: Optional[str] = None` to arg()
        # if subcommand and subcommand.lower() == "test":
        #     await self._start_game(ctx.channel, artist_name="Zhang Daqian")
        # else:
        await self._start_game(ctx.channel)

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        # Let valid bot commands pass through
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        lower = content.lower()

        # ── n: show 4 new images ──────────────────────────────────────────────
        if lower == "n":
            if not game.image_paths:
                await message.channel.send("No images available for this artist.")
                return
            chosen = game.pick_images(4)
            if not chosen:
                await message.channel.send("No more new images available!")
                return
            await self._send_images(message.channel, game, chosen)
            return

        # ── h: hint ───────────────────────────────────────────────────────────
        if lower == "h":
            if game.hint_count == 0:
                # First hint: short bio + movements
                artist = game.artist
                bio = artist.get("short_bio", "")
                movements = artist.get("main_movement", "")
                subs = artist.get("sub_movements", "")
                if subs:
                    movements_line = f"{movements} — {subs}"
                else:
                    movements_line = movements

                embed = discord.Embed(
                    title="Hint — About this Artist",
                    color=discord.Color.gold(),
                )
                if bio:
                    embed.description = bio
                if movements_line:
                    embed.add_field(name="Movements", value=movements_line, inline=False)
                game.hint_count = 1
                await message.channel.send(embed=embed)

            elif game.hint_count == 1:
                # Second hint: scrambled answer (lowercase)
                scrambled = _scramble(game.answer)
                embed = discord.Embed(
                    title="Hint — Scrambled Letters",
                    description=f"**{scrambled}**\n*(these are the missing letters, scrambled)*",
                    color=discord.Color.orange(),
                )
                game.hint_count = 2
                await message.channel.send(embed=embed)

            else:
                await message.channel.send("No more hints! Make your best guess.")
            return

        # ── Guess ─────────────────────────────────────────────────────────────
        guess = _normalize(content)
        answer_norm = _normalize(game.answer)

        if not guess:
            return

        game.participants.add(message.author)

        if guess != answer_norm:
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
                f"The artist was **{game.artist['name']}**!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Play again below!")
        await message.channel.send(embed=embed, view=ArtPlayAgainView(self, message.channel.id))

    # ── Gamestop / $end integration ───────────────────────────────────────────

    async def force_stop_game(self, channel_id: int) -> Optional[str]:
        """Cancel any active game in this channel, revealing the answer. Returns 'Art Guesser' if stopped."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()

        channel = self.bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                description=f"The artist was **{game.artist['name']}**.",
                color=discord.Color(0x99aab5),
            )
            await channel.send(embed=embed)

        return "Art Guesser"

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
