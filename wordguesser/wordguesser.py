import asyncio
import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

import discord
from redbot.core import commands

from .words import WORD_DEFINITIONS

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

TIMEOUT = 60   # seconds before the answer is revealed
HINT_AT = 30   # seconds before a letter-count + first-letter hint is shown


@dataclass
class WordGame:
    channel: discord.TextChannel
    word: str
    definition: str
    task: Optional[asyncio.Task] = None


# ── Embeds ────────────────────────────────────────────────────────────────────

def _round_embed(definition: str) -> discord.Embed:
    return discord.Embed(
        title=f"Word Guesser{DEV_LABEL}",
        description=definition,
        color=discord.Color.blurple(),
    ).set_footer(text="Type your guess in chat! A hint appears after 30 seconds.")


def _winner_embed(winner: discord.Member, word: str, definition: str) -> discord.Embed:
    return discord.Embed(
        title=f"🎉  {winner.display_name} got it!",
        description=f"The word was **{word}**.\n\n*{definition}*",
        color=discord.Color.gold(),
    )


def _timeout_embed(word: str, definition: str) -> discord.Embed:
    return discord.Embed(
        title="⏰  Time's up!",
        description=f"Nobody guessed it. The word was **{word}**.\n\n*{definition}*",
        color=discord.Color.orange(),
    )


# ── Play Again button ─────────────────────────────────────────────────────────

class WordPlayAgainView(discord.ui.View):
    def __init__(self, cog: "WordGuesser", channel_id: int):
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

class WordGuesser(commands.Cog):
    """Word Guesser — a definition is posted and the first person to type the correct word wins!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}  # channel_id -> WordGame

    def cog_unload(self):
        for game in self.games.values():
            if game.task:
                game.task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        existing = self.games.pop(channel.id, None)
        if existing and existing.task:
            existing.task.cancel()

        word, definition = random.choice(WORD_DEFINITIONS)
        game = WordGame(channel=channel, word=word, definition=definition)
        self.games[channel.id] = game

        await channel.send(embed=_round_embed(definition))
        game.task = asyncio.create_task(self._run_round(channel, game))

    @commands.command(name="wordguesser")
    async def wordguesser(self, ctx: commands.Context):
        """Start a Word Guesser round. First to type the correct word wins!"""
        await self._start_game(ctx.channel)

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        if game.task:
            game.task.cancel()
        return "Word Guesser"

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_round(self, channel: discord.TextChannel, game: WordGame):
        try:
            await asyncio.sleep(HINT_AT)
            if self.games.get(channel.id) is game:
                hint = (
                    f"💡  Hint: **{len(game.word)}** letters, "
                    f"starts with **{game.word[0].upper()}**"
                )
                await channel.send(hint)

            await asyncio.sleep(TIMEOUT - HINT_AT)
            if self.games.get(channel.id) is game:
                self.games.pop(channel.id, None)
                await channel.send(
                    embed=_timeout_embed(game.word, game.definition),
                    view=WordPlayAgainView(self, channel.id),
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

        guess = message.content.strip().lower()
        if guess == game.word.lower():
            self.games.pop(message.channel.id, None)
            if game.task:
                game.task.cancel()
            await message.channel.send(
                embed=_winner_embed(message.author, game.word, game.definition),
                view=WordPlayAgainView(self, message.channel.id),
            )
