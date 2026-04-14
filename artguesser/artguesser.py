import asyncio
import random
import re
import time
import unicodedata
from typing import Optional
from urllib.parse import quote

import aiohttp
import discord
from redbot.core import commands

try:
    from .artists import ARTISTS
except ImportError:
    ARTISTS = {}

# Convert dict-format ARTISTS to list of dicts with 'name' key
ARTISTS_LIST = [{"name": name, **data} for name, data in ARTISTS.items()]

# VPS image server — images live at /var/www/html/artimages/{artist_name}/
VPS_IMAGES_URL = "http://150.136.40.239:8888/artimages/"

_IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
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
    - Multi-word artist: last word is the answer, shown as underscores.
    - Single-word artist: last half of chars is the answer, shown as underscores.
    """
    words = name.split()
    if len(words) > 1:
        answer = words[-1]
        prefix = " ".join(words[:-1])
        return answer, f"{prefix} {'_' * len(answer)}"
    else:
        mid = len(name) // 2
        answer = name[mid:]
        return answer, f"{name[:mid]}{'_' * len(answer)}"


def _scramble(text: str) -> str:
    """Scramble each word independently, lowercase."""
    result = []
    for word in text.lower().split():
        letters = list(word)
        random.shuffle(letters)
        result.append("".join(letters))
    return " ".join(result)


# ── VPS image fetching ────────────────────────────────────────────────────────

async def _fetch_artist_images(artist_name: str) -> list:
    """Fetch image URLs for an artist from the VPS nginx autoindex."""
    folder_url = VPS_IMAGES_URL + quote(artist_name, safe="") + "/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(folder_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
    except Exception:
        return []

    # nginx autoindex HTML: href="filename.jpg"
    matches = re.findall(
        r'href="([^"?/]+\.(' + "|".join(_IMAGE_EXTS) + r'))"',
        html, re.IGNORECASE
    )
    return [folder_url + quote(fname, safe="") for fname, _ in matches]


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
    def __init__(self, artist: dict, image_urls: list, task: asyncio.Task,
                 answer: str, display_name: str):
        self.artist = artist
        self.image_urls = image_urls         # all available URLs
        self.used_indices: set = set()        # indices already shown
        self.task = task
        self.answer = answer                  # hidden part to guess
        self.display_name = display_name      # e.g. "Vincent van ____"
        self.hint_count = 0                   # 0=none, 1=bio+movements, 2=scramble
        self.participants: set = set()

    def pick_images(self, count: int = 4) -> list:
        """Pick `count` not-yet-shown image URLs, cycling if all exhausted."""
        available = [i for i in range(len(self.image_urls)) if i not in self.used_indices]
        if len(available) < count:
            # Cycle: clear used set and pull from all
            self.used_indices.clear()
            available = list(range(len(self.image_urls)))
        if not available:
            return []
        chosen = random.sample(available, min(count, len(available)))
        self.used_indices.update(chosen)
        return [self.image_urls[i] for i in chosen]


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
            meta_parts.append(artist["years_active"])
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

    # ── Game start (shared by $arg and Play Again) ────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        if not ARTISTS_LIST:
            await channel.send("No artists loaded. Add entries to `artists.py` to play!")
            return

        artist = self._pick_artist()
        if artist is None:
            await channel.send("Could not pick an artist — please try again.")
            return

        answer, display_name = _get_answer_and_display(artist["name"])
        image_urls = await _fetch_artist_images(artist["name"])

        task = asyncio.create_task(self._game_timer(channel, artist["name"]))
        game = ArtGame(artist, image_urls, task, answer, display_name)
        self.games[channel.id] = game

        if image_urls:
            chosen = game.pick_images(4)
            # Build embeds: first has the info text + image, rest are pure images
            embeds = []
            embeds.append(self._build_info_embed(game, chosen[0] if chosen else None))
            for url in chosen[1:]:
                e = discord.Embed(color=discord.Color.blurple())
                e.set_image(url=url)
                embeds.append(e)
            await channel.send(embeds=embeds)
        else:
            # No images available yet — show text-only embed
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
            if not game.image_urls:
                await message.channel.send("No images available for this artist.")
                return
            chosen = game.pick_images(4)
            if not chosen:
                await message.channel.send("No more new images available!")
                return
            embeds = []
            for url in chosen:
                e = discord.Embed(color=discord.Color.blue())
                e.set_image(url=url)
                embeds.append(e)
            await message.channel.send(embeds=embeds)
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
        if tp:
            await tp.record_game_result(message.author, game.participants)

        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!\n\n"
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
