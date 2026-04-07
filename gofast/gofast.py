import asyncio
import random

import discord
from redbot.core import commands, Config

from .challenges import CHALLENGE_GROUPS

WIN_POINTS = 20


async def _find_emoji(guild: discord.Guild, name: str, fallback: str):
    emoji = discord.utils.get(guild.emojis, name=name)
    return emoji if emoji else fallback


# ── Session ───────────────────────────────────────────────────────────────────

class GoFastSession:
    """Tracks the state of one running GoFast session in a channel."""

    def __init__(self, channel: discord.TextChannel, round_seconds: int):
        self.channel = channel
        self.round_seconds = round_seconds
        self.scores = {}         # member_id -> {"member": Member, "points": int}
        self.used_answers = {}   # challenge.key -> set of lowercase winning answers
        self.current_challenge = None
        self.current_params = {}
        self.round_task = None
        self.active = True

    # ── Scoring helpers ───────────────────────────────────────────────────────

    def record_win(self, member: discord.Member, answer: str) -> int:
        """Mark answer used, add a point, return the member's new total."""
        key = self.current_challenge.key
        self.used_answers.setdefault(key, set()).add(answer.lower())
        entry = self.scores.setdefault(member.id, {"member": member, "points": 0})
        entry["points"] += 1
        return entry["points"]

    def is_used(self, answer: str) -> bool:
        """Return True if this answer has already won a round of the current challenge type."""
        key = self.current_challenge.key
        return answer.lower() in self.used_answers.get(key, set())

    def top_score(self) -> int:
        return max((e["points"] for e in self.scores.values()), default=0)

    def scores_line(self) -> str:
        if not self.scores:
            return "No points yet"
        parts = sorted(self.scores.values(), key=lambda e: e["points"], reverse=True)
        return "  |  ".join(
            f"{e['member'].display_name}: {e['points']}" for e in parts
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class GoFast(commands.Cog):
    """First to Type — race to answer random word and trivia challenges!"""

    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}   # channel_id -> GoFastSession
        self.config = Config.get_conf(self, identifier=0x676F666173, force_registration=True)
        self.config.register_global(round_seconds=30)

    def cog_unload(self):
        for session in self.sessions.values():
            if session.round_task:
                session.round_task.cancel()
        self.sessions.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def gofast(self, ctx: commands.Context):
        """Start a GoFast session. First to 20 points wins!"""
        if ctx.channel.id in self.sessions:
            await ctx.send("A GoFast session is already running in this channel!")
            return

        if not CHALLENGE_GROUPS:
            await ctx.send("No challenges are loaded. Please contact the bot owner.")
            return

        round_seconds = await self.config.round_seconds()
        session = GoFastSession(ctx.channel, round_seconds)
        self.sessions[ctx.channel.id] = session

        embed = discord.Embed(
            title="GoFast — First to Type!",
            description=(
                "A challenge will appear each round.\n"
                f"**First to {WIN_POINTS} points wins the game!**\n\n"
                "Anyone can play — just type your answer in chat!\n"
                "Use `$gofast end` to stop early, `$gofast skip` to skip a round."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)
        await self._start_round(session)

    @gofast.command(name="end")
    async def gofast_end(self, ctx: commands.Context):
        """End the current GoFast session early."""
        session = self.sessions.pop(ctx.channel.id, None)
        if session is None:
            await ctx.send("No GoFast session is running in this channel.")
            return
        session.active = False
        if session.round_task:
            session.round_task.cancel()
        await self._announce_final(ctx.channel, session, ended_early=True)

    @gofast.command(name="skip")
    async def gofast_skip(self, ctx: commands.Context):
        """Skip the current round and start a new one."""
        session = self.sessions.get(ctx.channel.id)
        if session is None:
            await ctx.send("No GoFast session is running in this channel.")
            return
        if session.round_task:
            session.round_task.cancel()
        await ctx.send("Skipping this round…")
        await self._start_round(session)

    @gofast.command(name="time")
    @commands.is_owner()
    async def gofast_time(self, ctx: commands.Context, seconds: int):
        """(Bot owner) Set the global default round time in seconds."""
        seconds = max(10, min(seconds, 300))
        await self.config.round_seconds.set(seconds)
        await ctx.send(f"Default round time set to **{seconds} seconds**.")

    @gofast.command(name="score")
    async def gofast_score(self, ctx: commands.Context):
        """Show current scores for the running session."""
        session = self.sessions.get(ctx.channel.id)
        if session is None:
            await ctx.send("No GoFast session is running in this channel.")
            return
        await ctx.send(f"**Scores:** {session.scores_line()}")

    # ── Round management ──────────────────────────────────────────────────────

    async def _start_round(self, session: GoFastSession):
        if not session.active:
            return

        group = random.choice(CHALLENGE_GROUPS)
        challenge = random.choice(group)
        params, prompt = await challenge.async_generate()
        session.current_challenge = challenge
        session.current_params = params

        embed = discord.Embed(
            title="New Challenge!",
            description=prompt,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"{session.round_seconds}s to answer  •  {session.scores_line()}")
        await session.channel.send(embed=embed)

        session.round_task = asyncio.create_task(self._round_timer(session))

    async def _round_timer(self, session: GoFastSession):
        await asyncio.sleep(session.round_seconds)
        if (
            session.channel.id in self.sessions
            and self.sessions[session.channel.id] is session
        ):
            await session.channel.send("⏰ Time's up! No one answered. Starting next round…")
            await self._start_round(session)

    async def _announce_final(
        self,
        channel: discord.TextChannel,
        session: GoFastSession,
        ended_early: bool = False,
    ):
        if not session.scores:
            await channel.send("Game over! No points were scored.")
            return

        sorted_players = sorted(
            session.scores.values(), key=lambda e: e["points"], reverse=True
        )
        winner = sorted_players[0]

        if ended_early:
            title = "Game ended early!"
            desc = (
                f"**{winner['member'].display_name}** was in the lead "
                f"with **{winner['points']} pts**."
            )
        else:
            title = f"We have a winner!"
            desc = (
                f"**{winner['member'].display_name}** reached **{WIN_POINTS} points** — they win!"
            )

        embed = discord.Embed(title=title, description=desc, color=discord.Color.gold())

        medals = ["🥇", "🥈", "🥉"]
        board = []
        for i, entry in enumerate(sorted_players):
            medal = medals[i] if i < len(medals) else f"{i + 1}."
            board.append(f"{medal} **{entry['member'].display_name}** — {entry['points']} pts")

        embed.add_field(name="Final Scores", value="\n".join(board), inline=False)
        await channel.send(embed=embed)

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in self.sessions:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        session = self.sessions[message.channel.id]
        if session.current_challenge is None or not session.active:
            return

        answer = message.content.strip().lower()
        if not answer:
            return

        # Silently ignore previously-winning answers for this challenge type
        if session.is_used(answer):
            return

        # Ask the challenge to validate
        if not session.current_challenge.validate(answer, session.current_params):
            return

        # Valid — cancel timer, react, record point
        if session.round_task:
            session.round_task.cancel()

        check = await _find_emoji(message.guild, "check", "✅")
        try:
            await message.add_reaction(check)
        except discord.HTTPException:
            pass

        new_total = session.record_win(message.author, answer)

        if new_total >= WIN_POINTS:
            session.active = False
            self.sessions.pop(message.channel.id, None)
            await self._announce_final(message.channel, session)
        else:
            await self._start_round(session)
