import asyncio
import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

import discord
from redbot.core import commands

from .words import WORD_DEFINITIONS

try:
    from _dev import DEV_LABEL
except ImportError:
    DEV_LABEL = ""

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

    @commands.command(name="wordguesser")
    async def wordguesser(self, ctx: commands.Context):
        """Start a Word Guesser round. First to type the correct word wins!"""
        # Cancel any running game in this channel and start fresh
        existing = self.games.pop(ctx.channel.id, None)
        if existing and existing.task:
            existing.task.cancel()

        word, definition = random.choice(WORD_DEFINITIONS)
        game = WordGame(channel=ctx.channel, word=word, definition=definition)
        self.games[ctx.channel.id] = game

        await ctx.send(embed=_round_embed(definition))
        game.task = asyncio.create_task(self._run_round(ctx, game))

    @commands.command(name="wgend")
    async def wgend(self, ctx: commands.Context):
        """Cancel the current Word Guesser round."""
        game = self.games.pop(ctx.channel.id, None)
        if game is None:
            await ctx.send("No Word Guesser round is running in this channel.")
            return
        if game.task:
            game.task.cancel()
        await ctx.send(embed=discord.Embed(
            description=f"🛑  Round cancelled. The word was **{game.word}**.",
            color=discord.Color.red(),
        ))

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_round(self, ctx: commands.Context, game: WordGame):
        try:
            # Hint after HINT_AT seconds
            await asyncio.sleep(HINT_AT)
            if self.games.get(ctx.channel.id) is game:
                hint = (
                    f"💡  Hint: **{len(game.word)}** letters, "
                    f"starts with **{game.word[0].upper()}**"
                )
                await ctx.send(hint)

            # Timeout for the remaining time
            await asyncio.sleep(TIMEOUT - HINT_AT)
            if self.games.get(ctx.channel.id) is game:
                self.games.pop(ctx.channel.id, None)
                await ctx.send(embed=_timeout_embed(game.word, game.definition))

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
                embed=_winner_embed(message.author, game.word, game.definition)
            )
