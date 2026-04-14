import asyncio
import random
from dataclasses import dataclass, field
from typing import Optional

import discord
from redbot.core import commands

from .movies import MOVIES

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

CAST_HINT_AT = 20      # seconds until cast hint
SCRAMBLE_HINT_AT = 40  # seconds until scrambled title hint
TIMEOUT = 60           # seconds until game ends

_STRIP_ARTICLES = ("the ", "a ", "an ")


def _normalize(s: str) -> str:
    """Lowercase and strip a leading article for flexible matching."""
    s = s.strip().lower()
    for article in _STRIP_ARTICLES:
        if s.startswith(article):
            return s[len(article):]
    return s


def _scramble_title(title: str) -> str:
    """Shuffle letters within each word, keeping short/non-alpha tokens intact."""
    words = title.split()
    result = []
    for word in words:
        if word.isalpha() and len(word) > 3:
            chars = list(word)
            random.shuffle(chars)
            result.append("".join(chars))
        else:
            result.append(word)
    return " ".join(result)


@dataclass
class MovieGame:
    channel: discord.TextChannel
    title: str
    year: int
    synopsis: str
    cast: list
    task: Optional[asyncio.Task] = None
    participants: set = field(default_factory=set)


# ── Embeds ────────────────────────────────────────────────────────────────────

def _round_embed(game: MovieGame) -> discord.Embed:
    return discord.Embed(
        title=f"Movie Guesser{DEV_LABEL} 🎬",
        description=game.synopsis,
        color=discord.Color.blurple(),
    ).set_footer(text="Type the movie title to win!  Cast hint in 20 seconds.")


def _cast_hint_embed(game: MovieGame) -> discord.Embed:
    return discord.Embed(
        title="💡 Hint — Top Cast",
        description=f"**{game.cast[0]}** and **{game.cast[1]}**",
        color=discord.Color.blurple(),
    ).set_footer(text="Scrambled title hint in 20 seconds.")


def _scramble_hint_embed(game: MovieGame) -> discord.Embed:
    scrambled = _scramble_title(game.title)
    return discord.Embed(
        title="💡 Hint — Scrambled Title",
        description=f"**{scrambled}**",
        color=discord.Color.blurple(),
    ).set_footer(text="Time's almost up!  20 seconds remaining.")


def _winner_embed(winner: discord.Member, game: MovieGame, total_pts=None) -> discord.Embed:
    pts_line = f"\nYou now have **{total_pts:,}** total points!" if total_pts is not None else ""
    return discord.Embed(
        title=f"🎉  {winner.display_name} got it!",
        description=(
            f"The movie was **{game.title}** ({game.year}).{pts_line}\n\n"
            f"Starring **{game.cast[0]}** and **{game.cast[1]}**."
        ),
        color=discord.Color.gold(),
    )


def _timeout_embed(game: MovieGame) -> discord.Embed:
    return discord.Embed(
        title="⏰  Time's up!",
        description=(
            f"Nobody guessed it. The movie was **{game.title}** ({game.year}).\n\n"
            f"Starring **{game.cast[0]}** and **{game.cast[1]}**.\n\n"
            f"*{game.synopsis}*"
        ),
        color=discord.Color.orange(),
    )


# ── Play Again button ─────────────────────────────────────────────────────────

class MoviePlayAgainView(discord.ui.View):
    def __init__(self, cog: "MovieGuesser", channel_id: int):
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

class MovieGuesser(commands.Cog):
    """Movie Guesser — a plot synopsis is posted and the first person to type the correct movie title wins!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}  # channel_id -> MovieGame

    def cog_unload(self):
        for game in self.games.values():
            if game.task:
                game.task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        data = random.choice(MOVIES)
        game = MovieGame(
            channel=channel,
            title=data["title"],
            year=data["year"],
            synopsis=data["synopsis"],
            cast=data["cast"],
        )
        self.games[channel.id] = game
        await channel.send(embed=_round_embed(game))
        game.task = asyncio.create_task(self._run_round(channel, game))

    @commands.command(name="movieguesser", aliases=["mg", "movie"])
    async def movieguesser(self, ctx: commands.Context):
        """Start a Movie Guesser round. First to type the correct movie title wins!"""
        if ctx.channel.id in self.games:
            await ctx.send("A game is already in progress in this channel!")
            return
        await self._start_game(ctx.channel)

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in this channel. Returns cog name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        if game.task:
            game.task.cancel()
        return "Movie Guesser"

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_round(self, channel: discord.TextChannel, game: MovieGame):
        try:
            await asyncio.sleep(CAST_HINT_AT)
            if self.games.get(channel.id) is game:
                await channel.send(embed=_cast_hint_embed(game))

            await asyncio.sleep(SCRAMBLE_HINT_AT - CAST_HINT_AT)
            if self.games.get(channel.id) is game:
                await channel.send(embed=_scramble_hint_embed(game))

            await asyncio.sleep(TIMEOUT - SCRAMBLE_HINT_AT)
            if self.games.get(channel.id) is game:
                self.games.pop(channel.id, None)
                tp = self.bot.get_cog("TrackPoints")
                if tp:
                    await tp.record_game_result(None, game.participants)
                await channel.send(
                    embed=_timeout_embed(game),
                    view=MoviePlayAgainView(self, channel.id),
                )

        except asyncio.CancelledError:
            pass

    # ── Message Listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        game.participants.add(message.author)

        if _normalize(message.content) == _normalize(game.title):
            self.games.pop(message.channel.id, None)
            if game.task:
                game.task.cancel()
            tp = self.bot.get_cog("TrackPoints")
            total_pts = None
            if tp:
                await tp.record_game_result(message.author, game.participants)
                total_pts = await tp.get_points(message.author)
            await message.channel.send(
                embed=_winner_embed(message.author, game, total_pts),
                view=MoviePlayAgainView(self, message.channel.id),
            )
