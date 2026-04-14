import asyncio
import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

import discord
from redbot.core import Config, commands

from .slang import SLANG_WORDS
from .proper_nouns import PROPER_NOUNS

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

# ── Dictionary ────────────────────────────────────────────────────────────────

def _load_dictionary() -> frozenset:
    base: set = set()
    try:
        from english_words import get_english_words_set
        base = get_english_words_set(["web2"], lower=True)
    except (ImportError, Exception):
        try:
            from english_words import english_words_lower_set  # type: ignore
            base = english_words_lower_set
        except ImportError:
            pass
    return frozenset(base | {w.lower() for w in SLANG_WORDS} | PROPER_NOUNS)


def _build_trigram_list(dictionary: frozenset) -> list:
    """Return alphabetic trigrams sorted descending by how many words contain them."""
    from collections import Counter
    counts: Counter = Counter()
    for word in dictionary:
        if len(word) >= 3:
            seen: set = set()
            for i in range(len(word) - 2):
                tri = word[i : i + 3]
                if tri.isalpha() and tri not in seen:
                    counts[tri] += 1
                    seen.add(tri)
    return sorted(counts.keys(), key=lambda t: -counts[t])


DICTIONARY: frozenset = _load_dictionary()
TRIGRAMS: list = _build_trigram_list(DICTIONARY)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _hearts(n: int) -> str:
    return "❤️" * n if n > 0 else "💀"


async def _find_emoji(guild: discord.Guild, name: str, fallback: str):
    emoji = discord.utils.get(guild.emojis, name=name)
    return emoji if emoji else fallback


# ── Join UI ───────────────────────────────────────────────────────────────────

class JoinView(discord.ui.View):
    def __init__(self, game: "WordRushGame"):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="✋")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.phase != "joining":
            await interaction.response.send_message("The join phase is over!", ephemeral=True)
            return
        if any(p.member.id == interaction.user.id for p in self.game.players):
            await interaction.response.send_message("You're already in!", ephemeral=True)
            return
        self.game.players.append(Player(interaction.user, self.game.max_lives))
        await interaction.response.send_message("You've joined Word Rush! ✋", ephemeral=True)
        with suppress(discord.HTTPException):
            await interaction.message.edit(embed=_join_embed(self.game))


# ── Game state ────────────────────────────────────────────────────────────────

@dataclass
class Player:
    member: discord.Member
    lives: int

    @property
    def alive(self) -> bool:
        return self.lives > 0


class WordRushGame:
    def __init__(self, channel, round_time: int, max_lives: int, syll: int):
        self.channel = channel
        self.round_time = round_time
        self.max_lives = max_lives
        self.syll = syll

        self.players: list = []
        self.current_idx: int = 0
        self.current_trigram: str = ""
        self.used_words: set = set()
        self.phase: str = "joining"
        self.turn_event: asyncio.Event = asyncio.Event()
        self.join_message: Optional[discord.Message] = None
        self.game_task: Optional[asyncio.Task] = None

    def alive_players(self) -> list:
        return [p for p in self.players if p.alive]

    def advance_to_next_alive(self) -> None:
        n = len(self.players)
        if not self.alive_players():
            return
        for i in range(1, n + 1):
            nxt = (self.current_idx + i) % n
            if self.players[nxt].alive:
                self.current_idx = nxt
                return

    def pick_trigram(self) -> str:
        cap = min(self.syll, len(TRIGRAMS)) if TRIGRAMS else 0
        pool = TRIGRAMS[:cap] if cap else ["ING", "AND", "ENT", "ION", "ATE", "PRE", "CON"]
        return random.choice(pool).upper()

    def is_valid_word(self, word: str) -> bool:
        w = word.lower()
        t = self.current_trigram.lower()
        return (
            len(w) >= 3
            and w.isalpha()
            and t in w
            and w in DICTIONARY
            and w not in self.used_words
        )


# ── Embeds ────────────────────────────────────────────────────────────────────

def _join_embed(game: WordRushGame) -> discord.Embed:
    if game.players:
        plist = "\n".join(f"• {p.member.display_name}" for p in game.players)
    else:
        plist = "*No one yet — be the first!*"
    embed = discord.Embed(
        title=f"Word Rush{DEV_LABEL}",
        description=(
            "Find a word containing the 3 displayed letters before time runs out!\n"
            "Click **Join Game** to play!\n\n"
            f"**Players ({len(game.players)}):**\n{plist}"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Settings",
        value=(
            f"⏱ **{game.round_time}s** per turn  ·  "
            f"❤️ **{game.max_lives}** {'life' if game.max_lives == 1 else 'lives'}  ·  "
            f"📚 SYLL **{game.syll}**"
        ),
        inline=False,
    )
    return embed


def _turn_text(player: Player, trigram: str, remaining: Optional[int] = None) -> str:
    countdown = f"  ⏳ **{remaining}**s" if remaining is not None and remaining <= 8 else ""
    return f"{player.member.mention} type a word containing **{trigram}**{countdown}"


def _lost_life_embed(player: Player) -> discord.Embed:
    remaining = player.lives
    return discord.Embed(
        description=(
            f"💣  **{player.member.display_name}** lost a life! "
            f"({remaining} {'life' if remaining == 1 else 'lives'} remaining)"
        ),
        color=discord.Color.blurple(),
    )


def _eliminated_embed(player: Player) -> discord.Embed:
    return discord.Embed(
        description=f"💣  **{player.member.display_name}** has been eliminated! 💀",
        color=discord.Color.blurple(),
    )


def _winner_embed(winner: Player, wins: int, games: int) -> discord.Embed:
    return discord.Embed(
        title=f"🎉  {winner.member.display_name} wins Word Rush!",
        description=(
            f"{winner.member.mention} is the last one standing!\n\n"
            f"They've now won **{wins}** out of **{games}** "
            f"completed game{'s' if games != 1 else ''}!"
        ),
        color=discord.Color.blurple(),
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class WordRush(commands.Cog):
    """Word Rush — find words containing the 3 displayed letters before time runs out!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=7391048201, force_registration=True)
        self.config.register_guild(round_time=26, lives=2, syll=2000)
        self.config.register_member(wins=0, games_played=0)

    def cog_unload(self):
        for game in self.games.values():
            if game.game_task:
                game.game_task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="wr")
    async def wr(self, ctx: commands.Context):
        """Start a Word Rush game. Players have 20 seconds to click Join."""
        if ctx.channel.id in self.games:
            await ctx.send("A Word Rush game is already running in this channel!")
            return

        gc = self.config.guild(ctx.guild)
        game = WordRushGame(
            channel=ctx.channel,
            round_time=await gc.round_time(),
            max_lives=await gc.lives(),
            syll=await gc.syll(),
        )
        self.games[ctx.channel.id] = game

        view = JoinView(game)
        join_msg = await ctx.send(embed=_join_embed(game), view=view)
        game.join_message = join_msg

        game.game_task = asyncio.create_task(self._run_game(ctx, game))

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        if game.game_task:
            game.game_task.cancel()
        game.phase = "ended"
        return "Word Rush"

    @commands.command(name="wrtime")
    async def wrtime(self, ctx: commands.Context, seconds: int):
        """Set the turn time in seconds (10–120). Example: `$wrtime 40`"""
        seconds = max(10, min(seconds, 120))
        await self.config.guild(ctx.guild).round_time.set(seconds)
        await ctx.send(f"Turn time set to **{seconds}** seconds.")

    @commands.command(name="wrlives")
    async def wrlives(self, ctx: commands.Context, lives: int):
        """Set the number of lives per player (1–5). Example: `$wrlives 3`"""
        lives = max(1, min(lives, 5))
        await self.config.guild(ctx.guild).lives.set(lives)
        await ctx.send(f"Lives set to **{lives}**.")

    @commands.command(name="wrsyll")
    async def wrsyll(self, ctx: commands.Context, syll: int):
        """Set syllable difficulty 100–5000 (lower = easier). Example: `$wrsyll 3000`"""
        syll = max(100, min(syll, 5000))
        await self.config.guild(ctx.guild).syll.set(syll)
        await ctx.send(f"SYLL set to **{syll}** (drawing from top {syll} letter combinations).")

    # ── Game runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: WordRushGame):
        try:
            # ── Join phase (20 seconds) ─────────────────────────────────────
            await asyncio.sleep(20)
            game.phase = "ended"  # disables the join button handler

            with suppress(discord.HTTPException):
                await game.join_message.edit(view=discord.ui.View())

            if len(game.players) < 2:
                await ctx.send(embed=discord.Embed(
                    description="Not enough players joined (need at least 2). Game cancelled.",
                    color=discord.Color.orange(),
                ))
                return

            game.phase = "playing"
            random.shuffle(game.players)
            game.current_idx = 0

            # ── Round loop ──────────────────────────────────────────────────
            while len(game.alive_players()) > 1:
                current = game.players[game.current_idx]
                if not current.alive:
                    game.advance_to_next_alive()
                    continue

                trigram = game.pick_trigram()
                success = await self._run_turn(game, current, trigram)

                if not success:
                    current.lives -= 1
                    if not current.alive:
                        await game.channel.send(embed=_eliminated_embed(current))
                        await game.channel.send("https://tenor.com/view/house-explosion-explode-boom-kaboom-gif-19506150")
                    else:
                        await game.channel.send(embed=_lost_life_embed(current))
                        await game.channel.send("https://tenor.com/view/cat-explosion-ellie-cat-explosion-cat-explode-meme-nuclear-explosion-nuclear-ellie-gif-11491440842155618054")

                game.advance_to_next_alive()

            # ── Winner ──────────────────────────────────────────────────────
            alive = game.alive_players()
            if alive:
                winner = alive[0]
                wins, games_played = await self._record_result(game.players, winner)
                await game.channel.send(embed=_winner_embed(winner, wins, games_played))

        except asyncio.CancelledError:
            pass
        finally:
            self.games.pop(ctx.channel.id, None)

    async def _run_turn(self, game: WordRushGame, player: Player, trigram: str) -> bool:
        """Post the turn embed, count down the last 8 seconds. Return True if player guessed."""
        game.current_trigram = trigram
        game.turn_event.clear()

        msg = await game.channel.send(_turn_text(player, trigram))

        for remaining in range(game.round_time, 0, -1):
            # Check if on_message already resolved this turn
            if game.turn_event.is_set():
                return True

            # Edit countdown in the last 8 seconds
            if remaining <= 8:
                with suppress(discord.HTTPException):
                    await msg.edit(content=_turn_text(player, trigram, remaining))

            # Wait up to 1 second for a correct guess
            try:
                await asyncio.wait_for(game.turn_event.wait(), timeout=1.0)
                return True
            except asyncio.TimeoutError:
                pass

        return False

    async def _record_result(self, participants: list, winner: Player):
        """Increment games_played for all participants and wins for winner. Returns (wins, games)."""
        for p in participants:
            gp = await self.config.member(p.member).games_played()
            await self.config.member(p.member).games_played.set(gp + 1)
        w = await self.config.member(winner.member).wins()
        await self.config.member(winner.member).wins.set(w + 1)
        gp = await self.config.member(winner.member).games_played()
        return w + 1, gp

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.games.get(message.channel.id)
        if not game or game.phase != "playing":
            return
        if game.turn_event.is_set():
            return  # turn already resolved

        current = game.players[game.current_idx]
        if not current.alive or message.author.id != current.member.id:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        word = message.content.strip().lower()
        if not word.isalpha():
            return

        if game.is_valid_word(word):
            game.used_words.add(word)
            game.turn_event.set()
            check = await _find_emoji(message.guild, "check", "✅")
            with suppress(discord.HTTPException):
                await message.add_reaction(check)
