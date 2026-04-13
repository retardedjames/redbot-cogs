import asyncio
import random
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

import discord
from redbot.core import Config, commands

from wordrush.slang import SLANG_WORDS
from wordrush.proper_nouns import PROPER_NOUNS

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


def _build_good_trigrams(dictionary: frozenset) -> frozenset:
    """Return trigrams that appear as a substring in at least 100 words."""
    counts: Counter = Counter()
    for word in dictionary:
        if len(word) >= 3 and word.isalpha():
            seen: set = set()
            for i in range(len(word) - 2):
                tri = word[i : i + 3]
                if tri not in seen:
                    counts[tri] += 1
                    seen.add(tri)
    return frozenset(t for t, c in counts.items() if c >= 100)


DICTIONARY: frozenset = _load_dictionary()
GOOD_TRIGRAMS: frozenset = _build_good_trigrams(DICTIONARY)


def _pick_start_word() -> tuple:
    """Return (display_word, trigram) where trigram is the last 3 letters."""
    candidates = [
        w for w in DICTIONARY
        if len(w) >= 5 and w.isalpha() and w[-3:] in GOOD_TRIGRAMS
    ]
    if not candidates:
        candidates = [w for w in DICTIONARY if len(w) >= 4 and w.isalpha()]
    word = random.choice(candidates)
    return word, word[-3:].upper()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _find_emoji(guild: discord.Guild, name: str, fallback: str):
    emoji = discord.utils.get(guild.emojis, name=name)
    return emoji if emoji else fallback


# ── Join UI ───────────────────────────────────────────────────────────────────

class JoinView(discord.ui.View):
    def __init__(self, game: "WordSpiralGame"):
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
        await interaction.response.send_message("You've joined Word Spiral!", ephemeral=True)
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


class WordSpiralGame:
    def __init__(self, channel, round_time: int, max_lives: int):
        self.channel = channel
        self.round_time = round_time
        self.max_lives = max_lives

        self.players: list = []
        self.current_idx: int = 0
        self.current_trigram: str = ""
        self.used_words: set = set()
        self.phase: str = "joining"
        self.turn_event: asyncio.Event = asyncio.Event()
        self.last_word_submitted: Optional[str] = None
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


# ── Embeds / messages ─────────────────────────────────────────────────────────

def _join_embed(game: WordSpiralGame) -> discord.Embed:
    if game.players:
        plist = "\n".join(f"• {p.member.display_name}" for p in game.players)
    else:
        plist = "*No one yet — be the first!*"
    embed = discord.Embed(
        title="Word Spiral 🌀",
        description=(
            "The bot starts with a word. Each player must type a valid word **containing the last 3 letters** of the previous word!\n"
            "Fail to answer in time and you lose a life. Last one standing wins!\n"
            "Click **Join Game** to play!\n\n"
            f"**Players ({len(game.players)}):**\n{plist}"
        ),
        color=discord.Color.purple(),
    )
    embed.add_field(
        name="Settings",
        value=(
            f"⏱ **{game.round_time}s** per turn  ·  "
            f"❤️ **{game.max_lives}** {'life' if game.max_lives == 1 else 'lives'}"
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
        color=discord.Color.purple(),
    )


def _eliminated_embed(player: Player) -> discord.Embed:
    return discord.Embed(
        description=f"💣  **{player.member.display_name}** has been eliminated! 💀",
        color=discord.Color.purple(),
    )


def _winner_embed(winner: Player, wins: int, games: int) -> discord.Embed:
    return discord.Embed(
        title=f"🎉  {winner.member.display_name} wins Word Spiral!",
        description=(
            f"{winner.member.mention} is the last one standing!\n\n"
            f"They've now won **{wins}** out of **{games}** "
            f"completed game{'s' if games != 1 else ''}!"
        ),
        color=discord.Color.purple(),
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class WordSpiral(commands.Cog):
    """Word Spiral — chain words using the last 3 letters of the previous word!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=8201948372, force_registration=True)
        self.config.register_global(round_time=26, lives=2)
        self.config.register_member(wins=0, games_played=0)

    def cog_unload(self):
        for game in self.games.values():
            if game.game_task:
                game.game_task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="ws")
    async def ws(self, ctx: commands.Context):
        """Start a Word Spiral game. Players have 20 seconds to click Join."""
        if ctx.channel.id in self.games:
            await ctx.send("A Word Spiral game is already running in this channel!")
            return

        round_time = await self.config.round_time()
        max_lives = await self.config.lives()

        game = WordSpiralGame(
            channel=ctx.channel,
            round_time=round_time,
            max_lives=max_lives,
        )
        self.games[ctx.channel.id] = game

        view = JoinView(game)
        join_msg = await ctx.send(embed=_join_embed(game), view=view)
        game.join_message = join_msg

        game.game_task = asyncio.create_task(self._run_game(ctx, game))

    @commands.is_owner()
    @commands.command(name="wstime")
    async def wstime(self, ctx: commands.Context, seconds: int):
        """[Owner] Set the global turn time in seconds (10–120). Example: `$wstime 40`"""
        seconds = max(10, min(seconds, 120))
        await self.config.round_time.set(seconds)
        await ctx.send(f"Word Spiral turn time set to **{seconds}** seconds globally.")

    @commands.is_owner()
    @commands.command(name="wslives")
    async def wslives(self, ctx: commands.Context, lives: int):
        """[Owner] Set the global number of lives per player (1–5). Example: `$wslives 3`"""
        lives = max(1, min(lives, 5))
        await self.config.lives.set(lives)
        await ctx.send(f"Word Spiral lives set to **{lives}** globally.")

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        if game.game_task:
            game.game_task.cancel()
        return "Word Spiral"

    # ── Game runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: WordSpiralGame):
        try:
            # ── Join phase (20 seconds) ─────────────────────────────────────
            await asyncio.sleep(20)
            game.phase = "ended"  # disables join button

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

            # ── Pick and announce starting word ─────────────────────────────
            start_word, trigram = _pick_start_word()
            game.current_trigram = trigram
            game.used_words.add(start_word.lower())

            first_player = game.players[game.current_idx]
            await ctx.send(
                f"🌀 **Word Spiral begins!**\n"
                f"Starting word: **{start_word.upper()}**\n"
                f"Last three letters: **{trigram}**\n"
                f"{first_player.member.mention}, you're up first! "
                f"Type a word containing **{trigram}**"
            )

            # ── Round loop ──────────────────────────────────────────────────
            first_turn = True
            while len(game.alive_players()) > 1:
                current = game.players[game.current_idx]
                if not current.alive:
                    game.advance_to_next_alive()
                    continue

                success, word = await self._run_turn(game, current, skip_initial_send=first_turn)
                first_turn = False

                if not success:
                    current.lives -= 1
                    # Trigram stays the same — passes to next player
                    if not current.alive:
                        await game.channel.send(embed=_eliminated_embed(current))
                        await game.channel.send("https://tenor.com/view/cat-cat-meme-explosion-explode-exploding-gif-3642346701878996431")
                    else:
                        await game.channel.send(embed=_lost_life_embed(current))
                        await game.channel.send("https://tenor.com/view/cat-explosion-ellie-cat-explosion-cat-explode-meme-nuclear-explosion-nuclear-ellie-gif-11491440842155618054")
                else:
                    # Update trigram to last 3 letters of submitted word
                    game.current_trigram = word[-3:].upper()

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

    async def _run_turn(self, game: WordSpiralGame, player: Player, skip_initial_send: bool = False):
        """Post the turn prompt, count down the last 8 seconds. Return (True, word) or (False, None)."""
        game.turn_event.clear()
        game.last_word_submitted = None

        if skip_initial_send:
            msg = None
        else:
            msg = await game.channel.send(_turn_text(player, game.current_trigram))

        for remaining in range(game.round_time, 0, -1):
            if game.turn_event.is_set():
                return True, game.last_word_submitted

            if remaining <= 8:
                with suppress(discord.HTTPException):
                    if msg is None:
                        msg = await game.channel.send(_turn_text(player, game.current_trigram, remaining))
                    else:
                        await msg.edit(content=_turn_text(player, game.current_trigram, remaining))

            try:
                await asyncio.wait_for(game.turn_event.wait(), timeout=1.0)
                return True, game.last_word_submitted
            except asyncio.TimeoutError:
                pass

        return False, None

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
            game.last_word_submitted = word
            game.turn_event.set()
            check = await _find_emoji(message.guild, "check", "✅")
            with suppress(discord.HTTPException):
                await message.add_reaction(check)
