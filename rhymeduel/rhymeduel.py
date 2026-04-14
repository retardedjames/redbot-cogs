import asyncio
import random
import re
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Optional

import discord
from redbot.core import Config, commands

from .wordbank import RHYME_WORDS

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

# ── Rhyme checking ────────────────────────────────────────────────────────────

def _rhyme_key_phonetic(word: str) -> Optional[str]:
    """Return the CMU rhyming part (last stressed vowel + rest), or None."""
    try:
        import pronouncing  # type: ignore
        phones_list = pronouncing.phones_for_word(word.lower())
        if phones_list:
            return pronouncing.rhyming_part(phones_list[0])
    except (ImportError, Exception):
        pass
    return None


def _rhymes_with(word: str, target: str) -> bool:
    """
    Lenient rhyme check.
    1. Use CMU pronouncing dict if available for both words.
    2. If either word isn't in CMU, fall back to shared 2-char ending.
    The word must differ from the target.
    """
    w = word.lower()
    t = target.lower()
    if w == t:
        return False

    wk = _rhyme_key_phonetic(w)
    tk = _rhyme_key_phonetic(t)

    if wk and tk:
        return wk == tk

    # Fallback: last 2 characters match (catches most slang/online words)
    if len(w) >= 2 and len(t) >= 2:
        return w[-2:] == t[-2:]
    return False


def _clean(text: str) -> str:
    """Strip to lowercase alpha only (removes apostrophes, hyphens, spaces)."""
    return re.sub(r"[^a-z]", "", text.strip().lower())


# ── Game state ────────────────────────────────────────────────────────────────

@dataclass
class RhymeDuelGame:
    channel: discord.TextChannel
    challenger: discord.Member
    challenged: discord.Member
    turn_time: int
    target_word: str = ""
    used_words: set = field(default_factory=set)     # normalized (clean) words
    current_idx: int = 0                              # 0 = challenger, 1 = challenged
    phase: str = "pending"                            # pending | playing | ended
    accept_event: asyncio.Event = field(default_factory=asyncio.Event)
    turn_event: asyncio.Event = field(default_factory=asyncio.Event)
    accept_message: Optional[discord.Message] = None
    game_task: Optional[asyncio.Task] = None
    accepted: bool = False

    @property
    def players(self) -> list:
        return [self.challenger, self.challenged]

    @property
    def current_player(self) -> discord.Member:
        return self.players[self.current_idx]

    @property
    def other_player(self) -> discord.Member:
        return self.players[1 - self.current_idx]


# ── Accept UI ─────────────────────────────────────────────────────────────────

class AcceptView(discord.ui.View):
    def __init__(self, game: RhymeDuelGame):
        super().__init__(timeout=60)
        self.game = game

    @discord.ui.button(label="Accept Duel!", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.phase != "pending":
            await interaction.response.send_message("This duel is no longer pending!", ephemeral=True)
            return
        if interaction.user.id != self.game.challenged.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
        self.game.accepted = True
        self.game.accept_event.set()
        await interaction.response.send_message("Challenge accepted! ⚔️", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🏃")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.phase != "pending":
            await interaction.response.send_message("This duel is no longer pending!", ephemeral=True)
            return
        if interaction.user.id != self.game.challenged.id:
            await interaction.response.send_message("This challenge isn't for you!", ephemeral=True)
            return
        self.game.accepted = False
        self.game.accept_event.set()
        await interaction.response.send_message("Challenge declined.", ephemeral=True)
        self.stop()


# ── Cog ───────────────────────────────────────────────────────────────────────

class RhymeDuel(commands.Cog):
    """Rhyme Duel — two players battle to rhyme a word before time runs out!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=5839201847, force_registration=True)
        self.config.register_guild(turn_time=20)
        self.config.register_member(wins=0)

    def cog_unload(self):
        for game in self.games.values():
            if game.game_task:
                game.game_task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="rhymeduel")
    @commands.guild_only()
    async def rhymeduel(self, ctx: commands.Context, opponent: discord.Member):
        """Challenge someone to a Rhyme Duel! Example: `$rhymeduel @user`"""
        if opponent.bot:
            await ctx.send("You can't duel a bot!")
            return
        if opponent.id == ctx.author.id:
            await ctx.send("You can't duel yourself!")
            return
        if ctx.channel.id in self.games:
            await ctx.send("There's already a Rhyme Duel happening in this channel!")
            return

        turn_time = await self.config.guild(ctx.guild).turn_time()
        game = RhymeDuelGame(
            channel=ctx.channel,
            challenger=ctx.author,
            challenged=opponent,
            turn_time=turn_time,
        )
        self.games[ctx.channel.id] = game

        view = AcceptView(game)
        msg = await ctx.send(
            f"{opponent.mention} — **{ctx.author.display_name}** challenges you to a Rhyme Duel!{DEV_LABEL} ⚔️\n"
            f"You have 60 seconds to accept or decline.",
            view=view,
        )
        game.accept_message = msg
        game.game_task = asyncio.create_task(self._run_game(ctx, game))

    @commands.command(name="rdtime")
    @commands.guild_only()
    async def rdtime(self, ctx: commands.Context, seconds: int):
        """Set Rhyme Duel turn time in seconds (10–120). Example: `$rdtime 30`"""
        seconds = max(10, min(seconds, 120))
        await self.config.guild(ctx.guild).turn_time.set(seconds)
        await ctx.send(f"Rhyme Duel turn time set to **{seconds}** seconds.")

    @commands.command(name="rdstats")
    @commands.guild_only()
    async def rdstats(self, ctx: commands.Context, member: discord.Member = None):
        """Show Rhyme Duel win count for yourself or another player."""
        target = member or ctx.author
        wins = await self.config.member(target).wins()
        noun = "duel" if wins == 1 else "duels"
        await ctx.send(f"⚔️ **{target.display_name}** has won **{wins}** Rhyme {noun}!")

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if not game:
            return None
        if game.game_task:
            game.game_task.cancel()
        game.phase = "ended"
        return "Rhyme Duel"

    # ── Game runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: RhymeDuelGame):
        try:
            # ── Wait for accept / decline (60s) ────────────────────────────
            try:
                await asyncio.wait_for(game.accept_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

            with suppress(discord.HTTPException):
                await game.accept_message.edit(view=discord.ui.View())

            if not game.accepted:
                if game.phase == "pending":
                    await ctx.send(
                        f"⏰ {game.challenged.mention} didn't respond in time. Duel cancelled."
                    )
                else:
                    await ctx.send(
                        f"{game.challenged.mention} declined the duel. 🏃"
                    )
                return

            # ── Set up the game ────────────────────────────────────────────
            game.target_word = random.choice(RHYME_WORDS)
            game.current_idx = random.randint(0, 1)
            game.phase = "playing"

            await ctx.send(embed=discord.Embed(
                title=f"⚔️ Rhyme Duel!{DEV_LABEL}",
                description=(
                    f"Word to rhyme: **{game.target_word.upper()}**\n\n"
                    f"{game.current_player.mention} goes first!\n"
                    f"**{game.turn_time}s** per turn — no repeating rhymes.\n"
                    f"First one to time out loses!"
                ),
                color=discord.Color.blurple(),
            ))

            # ── Turn loop ──────────────────────────────────────────────────
            while game.phase == "playing":
                current = game.current_player
                answered = await self._run_turn(game, current)

                if not answered:
                    winner = game.other_player
                    wins = await self._record_win(winner)
                    noun = "duel" if wins == 1 else "duels"
                    await ctx.send(embed=discord.Embed(
                        title="🏆 Rhyme Duel Over!",
                        description=(
                            f"⏰ {current.mention} ran out of time!\n\n"
                            f"{winner.mention} wins the Rhyme Duel!\n"
                            f"They've now won **{wins}** {noun}!"
                        ),
                        color=discord.Color.gold(),
                    ))
                    break

                # Swap turns
                game.current_idx = 1 - game.current_idx

        except asyncio.CancelledError:
            pass
        finally:
            self.games.pop(ctx.channel.id, None)

    async def _run_turn(self, game: RhymeDuelGame, player: discord.Member) -> bool:
        """Ping the player and wait for a valid rhyme. Returns True if they answered in time."""
        game.turn_event.clear()

        used_count = len(game.used_words)
        if used_count == 0:
            used_note = ""
        elif used_count <= 8:
            used_note = f"\nUsed so far: {', '.join(sorted(game.used_words))}"
        else:
            used_note = f"\n{used_count} words used so far."

        def _msg_text(remaining: Optional[int] = None) -> str:
            countdown = f" ⏳ **{remaining}s**" if remaining is not None else f" ({game.turn_time}s)"
            return (
                f"{player.mention} — rhyme **{game.target_word.upper()}**!{countdown}{used_note}"
            )

        msg = await game.channel.send(_msg_text())

        for remaining in range(game.turn_time, 0, -1):
            if game.turn_event.is_set():
                return True
            if remaining <= 8:
                with suppress(discord.HTTPException):
                    await msg.edit(content=_msg_text(remaining))
            try:
                await asyncio.wait_for(game.turn_event.wait(), timeout=1.0)
                return True
            except asyncio.TimeoutError:
                pass

        return False

    async def _record_win(self, winner: discord.Member) -> int:
        w = await self.config.member(winner).wins()
        await self.config.member(winner).wins.set(w + 1)
        return w + 1

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.games.get(message.channel.id)
        if not game or game.phase != "playing":
            return
        if game.turn_event.is_set():
            return
        if message.author.id != game.current_player.id:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        raw = message.content.strip()
        if not raw:
            return

        word = _clean(raw)
        if not word:
            return

        if word in game.used_words:
            with suppress(discord.HTTPException):
                await message.add_reaction("🔁")
            return

        if _rhymes_with(word, game.target_word):
            game.used_words.add(word)
            game.turn_event.set()
            with suppress(discord.HTTPException):
                await message.add_reaction("✅")
        else:
            with suppress(discord.HTTPException):
                await message.add_reaction("❌")
