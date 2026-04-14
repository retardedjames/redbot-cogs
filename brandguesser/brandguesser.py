"""
brandguesser.py — BrandGuesser Discord cog.

Pick a random brand → pick a random image style (img-001/002/003) → show
progressive reveal stages every 10 s → reveal original on win or timeout.

Commands during game:
  n — swap to a different image style (max 2 times)
  s — skip: reveal answer + original, start new game immediately

Command : $bg
"""

import asyncio
import pathlib
import random
import string
import time
import unicodedata

import discord
from redbot.core import commands

try:
    from .brands import BRANDS
except ImportError:
    BRANDS = {}

# ── Paths ─────────────────────────────────────────────────────────────────────
_LOCAL = pathlib.Path(__file__).parent / "images"
_VPS   = pathlib.Path("/home/ubuntu/redbot/cogs/brandguesser/images")

if _LOCAL.is_dir():
    IMAGES_DIR = _LOCAL
elif _VPS.is_dir():
    IMAGES_DIR = _VPS
else:
    IMAGES_DIR = _LOCAL   # graceful "no images" errors

# ── Constants ─────────────────────────────────────────────────────────────────
TOTAL_BRANDS    = len(BRANDS)
STAGE_INTERVAL  = 6    # seconds between consecutive stage reveals
NUM_STAGES      = 5    # s1 … s5
GRACE_SECONDS   = 16   # extra seconds after stage 5 before timeout
TIMEOUT_SECONDS = (NUM_STAGES - 1) * STAGE_INTERVAL + GRACE_SECONDS   # 40 s
_24H            = 86_400


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, strip accents, remove punctuation and extra whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(c for c in nfkd if ord(c) < 128)
    lower = ascii_only.lower()
    no_punct = lower.translate(str.maketrans("", "", string.punctuation))
    return " ".join(no_punct.split())


def _build_display(name: str) -> tuple:
    """
    Returns (display_str, letter_count).
    Each letter → escaped underscore, word boundaries shown with · separator,
    non-letter non-space chars shown as-is inline.
    """
    letter_count = 0
    words = name.split(" ")
    word_displays = []
    for word in words:
        parts = []
        for ch in word:
            if ch.isalpha():
                parts.append(r"\_")
                letter_count += 1
            else:
                parts.append(ch)
        word_displays.append(" ".join(parts))
    display = "  ·  ".join(word_displays)
    return display, letter_count


def _game_embed(game: "BrandGame", next_stage_in: "int | None" = STAGE_INTERVAL) -> discord.Embed:
    """Build the standard in-game embed.

    next_stage_in: seconds until next stage (counts down each second),
                   or None when stage 5 is showing (no more stages).
    """
    swaps_left = len(game.remaining_stems)
    if next_stage_in is not None:
        stage_text = f"new stage in **{next_stage_in}s**"
    else:
        stage_text = "final stage!"
    embed = discord.Embed(
        title="Guess the Brand!",
        description=(
            f"## {game.display}\n"
            f"**{game.letter_count} letters** · {stage_text}"
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(
        text=(
            f"n — swap image style ({swaps_left} swap{'s' if swaps_left != 1 else ''} left)  ·  "
            f"s — skip & reveal answer"
        )
    )
    embed.set_image(url="attachment://brand.jpg")
    return embed


# ── Play Again button ─────────────────────────────────────────────────────────

class BrandPlayAgainView(discord.ui.View):
    def __init__(self, cog: "BrandGuesser", channel_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green, emoji="🏷️")
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

class BrandGame:
    def __init__(
        self,
        brand_name: str,
        accepted: list,           # normalised accepted answers (name + aliases)
        display: str,             # underscore display string
        letter_count: int,
        img_stem: str,            # currently active stem, e.g. "img-002"
        remaining_stems: list,    # other available stems not yet shown
        brand_dir: pathlib.Path,
        task: asyncio.Task,
    ):
        self.brand_name      = brand_name
        self.accepted        = accepted
        self.display         = display
        self.letter_count    = letter_count
        self.img_stem        = img_stem
        self.remaining_stems = remaining_stems   # mutable list; shrinks as n is pressed
        self.brand_dir       = brand_dir
        self.task            = task
        self.participants: set = set()
        self.msg: "discord.Message | None" = None   # set after initial send

    @property
    def original_path(self) -> pathlib.Path:
        return self.brand_dir / f"{self.img_stem}.jpg"

    def stage_path(self, n: int) -> pathlib.Path:
        return self.brand_dir / "stages" / f"{self.img_stem}_s{n}.jpg"


# ── Cog ───────────────────────────────────────────────────────────────────────

class BrandGuesser(commands.Cog):
    """Guess the brand from a progressively revealed logo!"""

    _used_recently: dict = {}   # brand_name → timestamp (shared across channels)

    def __init__(self, bot):
        self.bot  = bot
        self.games: dict = {}   # channel_id → BrandGame

    # ── Brand / image selection ───────────────────────────────────────────────

    def _pick_brand(self) -> "tuple | None":
        """Return (brand_name, brand_data), preferring brands not seen in 24 h."""
        if not BRANDS:
            return None

        now = time.time()
        BrandGuesser._used_recently = {
            k: v for k, v in BrandGuesser._used_recently.items()
            if now - v < _24H
        }

        all_names = list(BRANDS.keys())
        fresh = [n for n in all_names if n not in BrandGuesser._used_recently]
        pool  = fresh if fresh else all_names

        random.shuffle(pool)
        for name in pool:
            if (IMAGES_DIR / name).is_dir():
                BrandGuesser._used_recently[name] = now
                return name, BRANDS[name]

        return None

    def _available_stems(self, brand_dir: pathlib.Path) -> list:
        """Return all img stems (img-001/002/003) that have an original + s1 stage."""
        candidates = []
        for n in range(1, 4):
            stem = f"img-{n:03d}"
            if (brand_dir / f"{stem}.jpg").exists() and \
               (brand_dir / "stages" / f"{stem}_s1.jpg").exists():
                candidates.append(stem)
        return candidates

    # ── Game runner ───────────────────────────────────────────────────────────

    async def _game_runner(self, channel: discord.TextChannel, brand_name: str):
        """Counts down to each new stage (editing the message every second),
        then times out after the grace period."""
        try:
            for stage_num in range(2, NUM_STAGES + 1):
                # Countdown: edit embed every second (image stays, only text changes)
                for secs_left in range(STAGE_INTERVAL - 1, 0, -1):
                    await asyncio.sleep(1)
                    game = self.games.get(channel.id)
                    if game is None:
                        return
                    if game.msg is not None:
                        await game.msg.edit(embed=_game_embed(game, next_stage_in=secs_left))
                # Final second — swap in the new stage image
                await asyncio.sleep(1)
                game = self.games.get(channel.id)
                if game is None:
                    return
                path = game.stage_path(stage_num)
                is_last = (stage_num == NUM_STAGES)
                if path.exists() and game.msg is not None:
                    await game.msg.edit(
                        embed=_game_embed(game, next_stage_in=None if is_last else STAGE_INTERVAL),
                        attachments=[discord.File(path, filename="brand.jpg")],
                    )
            await asyncio.sleep(GRACE_SECONDS)
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
            description=f"Nobody guessed it. The brand was **{brand_name}**.",
            color=discord.Color(0x99aab5),
        )
        orig = game.original_path
        if orig.exists():
            embed.set_image(url="attachment://brand_original.jpg")
            await channel.send(
                embed=embed,
                file=discord.File(orig, filename="brand_original.jpg"),
                view=BrandPlayAgainView(self, channel.id),
            )
        else:
            await channel.send(embed=embed, view=BrandPlayAgainView(self, channel.id))

    # ── Start game ────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        if not BRANDS:
            await channel.send("No brands loaded. Add entries to `brands.py` to play!")
            return

        result = self._pick_brand()
        if result is None:
            await channel.send(
                "No brand images found on disk. "
                "Run the pipeline script on the server to populate images."
            )
            return

        brand_name, brand_data = result
        brand_dir = IMAGES_DIR / brand_name
        stems = self._available_stems(brand_dir)
        if not stems:
            await channel.send(
                f"No ready stage images for **{brand_name}**. Try `$bg` again."
            )
            return

        random.shuffle(stems)
        img_stem        = stems[0]
        remaining_stems = stems[1:]   # the other styles available via n

        # Accepted answers (full name + aliases, normalised)
        accepted = [_normalize(brand_name)]
        for alias in brand_data.get("aliases", []):
            n = _normalize(alias)
            if n not in accepted:
                accepted.append(n)

        display, letter_count = _build_display(brand_name)

        task = asyncio.create_task(self._game_runner(channel, brand_name))
        game = BrandGame(
            brand_name, accepted, display, letter_count,
            img_stem, remaining_stems, brand_dir, task,
        )
        self.games[channel.id] = game

        stage1 = game.stage_path(1)
        if stage1.exists():
            msg = await channel.send(
                embed=_game_embed(game),
                file=discord.File(stage1, filename="brand.jpg"),
            )
        else:
            msg = await channel.send(embed=_game_embed(game))
        game.msg = msg

    # ── $bg command ──────────────────────────────────────────────────────────

    @commands.command(name="bg")
    async def bg(self, ctx: commands.Context):
        """Start a Brand Guesser game. Running during a game skips to a new one."""
        if ctx.channel.id in self.games:
            old = self.games.pop(ctx.channel.id)
            old.task.cancel()
            embed = discord.Embed(
                title="New game!",
                description=f"The previous brand was **{old.brand_name}**.",
                color=discord.Color(0x99aab5),
            )
            orig = old.original_path
            if orig.exists():
                embed.set_image(url="attachment://brand_original.jpg")
                await ctx.send(
                    embed=embed,
                    file=discord.File(orig, filename="brand_original.jpg"),
                )
            else:
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

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        lower   = content.lower()

        # ── n: swap to a different image style ───────────────────────────────
        if lower == "n":
            if not game.remaining_stems:
                await message.channel.send(
                    "No more image styles available!", delete_after=5
                )
                return
            # Pick next stem, cancel current runner, restart timer from scratch
            game.task.cancel()
            game.img_stem = game.remaining_stems.pop(
                random.randrange(len(game.remaining_stems))
            )
            stage1 = game.stage_path(1)
            if stage1.exists() and game.msg is not None:
                await game.msg.edit(
                    embed=_game_embed(game),
                    attachments=[discord.File(stage1, filename="brand.jpg")],
                )
            game.task = asyncio.create_task(
                self._game_runner(message.channel, game.brand_name)
            )
            return

        # ── s: skip — reveal answer + original, start new game immediately ───
        if lower == "s":
            old = self.games.pop(message.channel.id)
            old.task.cancel()
            embed = discord.Embed(
                title="Skipped!",
                description=f"The brand was **{old.brand_name}**.",
                color=discord.Color(0x99aab5),
            )
            orig = old.original_path
            if orig.exists():
                embed.set_image(url="attachment://brand_original.jpg")
                await message.channel.send(
                    embed=embed,
                    file=discord.File(orig, filename="brand_original.jpg"),
                )
            else:
                await message.channel.send(embed=embed)
            await self._start_game(message.channel)
            return

        # ── Guess ─────────────────────────────────────────────────────────────
        guess = _normalize(content)
        if not guess:
            return

        game.participants.add(message.author)

        if guess not in game.accepted:
            return

        # Correct!
        game.task.cancel()
        del self.games[message.channel.id]

        tp = self.bot.get_cog("TrackPoints")
        total_pts = None
        if tp:
            await tp.record_game_result(message.author, game.participants)
            total_pts = await tp.get_points(message.author)
        pts_line = (
            f"\nYou now have **{total_pts:,}** total points!"
            if total_pts is not None else ""
        )
        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!{pts_line}\n\n"
                f"The brand was **{game.brand_name}**!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Play again below!")
        orig = game.original_path
        if orig.exists():
            embed.set_image(url="attachment://brand_original.jpg")
            await message.channel.send(
                embed=embed,
                file=discord.File(orig, filename="brand_original.jpg"),
                view=BrandPlayAgainView(self, message.channel.id),
            )
        else:
            await message.channel.send(
                embed=embed,
                view=BrandPlayAgainView(self, message.channel.id),
            )

    # ── Gamestop / $end integration ───────────────────────────────────────────

    async def clear_recent_memory(self, guild=None) -> str:
        """Clear the 24-hour repeat-prevention memory. Returns cog display name."""
        BrandGuesser._used_recently.clear()
        return "Brand Guesser"

    async def force_stop_game(self, channel_id: int) -> "str | None":
        """Cancel any active game, revealing the answer. Returns cog name if stopped."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.task.cancel()

        channel = self.bot.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                description=f"The brand was **{game.brand_name}**.",
                color=discord.Color(0x99aab5),
            )
            orig = game.original_path
            if orig.exists():
                embed.set_image(url="attachment://brand_original.jpg")
                await channel.send(
                    embed=embed,
                    file=discord.File(orig, filename="brand_original.jpg"),
                )
            else:
                await channel.send(embed=embed)

        return "Brand Guesser"

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
