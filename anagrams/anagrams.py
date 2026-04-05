import asyncio
import random
from collections import Counter

import discord
from redbot.core import commands

from .slang import SLANG_WORDS
from .source_words import SOURCE_WORDS

# ── Dictionary ────────────────────────────────────────────────────────────────

def _load_dictionary() -> frozenset:
    base: set = set()
    try:
        from english_words import get_english_words_set
        base = get_english_words_set(["web2"], lower=True)
    except (ImportError, Exception):
        try:
            from english_words import english_words_lower_set
            base = english_words_lower_set  # type: ignore
        except ImportError:
            pass
    return frozenset(base | {w.lower() for w in SLANG_WORDS})


DICTIONARY: frozenset = _load_dictionary()

# ── Scoring ───────────────────────────────────────────────────────────────────
#   3 letters → 40 pts, each extra letter → +20 pts, full-word bonus → +300

FULL_WORD_BONUS = 300


def _score(word: str) -> int:
    return 40 + max(0, len(word) - 3) * 20


# ── Helpers ───────────────────────────────────────────────────────────────────

def _can_make(guess: str, source: str) -> bool:
    """True if every letter in guess appears in source with sufficient count."""
    pool = Counter(source.lower())
    for ch in guess.lower():
        if pool[ch] <= 0:
            return False
        pool[ch] -= 1
    return True


def _jumble(word: str) -> str:
    """Shuffle word's letters, guaranteed to differ from the original."""
    letters = list(word.upper())
    for _ in range(200):
        random.shuffle(letters)
        if "".join(letters) != word.upper():
            return "".join(letters)
    random.shuffle(letters)          # give up guaranteeing difference for 1-char words
    return "".join(letters)


async def _find_emoji(guild: discord.Guild, name: str, fallback: str):
    """Return a custom guild emoji matching *name*, or the fallback string."""
    emoji = discord.utils.get(guild.emojis, name=name)
    return emoji if emoji else fallback


# ── Game state ────────────────────────────────────────────────────────────────

class AnagramGame:
    def __init__(self, word: str, duration: int):
        self.word     = word.upper()
        self.jumbled  = _jumble(word)
        self.duration = duration
        # word.upper() → (discord.Member, points_earned)
        self.found:  dict = {}
        # member.id  → {"points": int, "words": list[str], "member": Member}
        self.scores: dict = {}

    def already_found(self, word: str) -> bool:
        return word.upper() in self.found

    def is_valid(self, word: str) -> bool:
        """Word is in the dictionary and constructible from the source letters."""
        return word.lower() in DICTIONARY and _can_make(word, self.word)

    def record(self, word: str, member: discord.Member) -> int:
        """Save a valid find and return the points awarded."""
        up  = word.upper()
        pts = _score(word)
        if up == self.word:
            pts += FULL_WORD_BONUS
        self.found[up] = (member, pts)
        entry = self.scores.setdefault(
            member.id, {"points": 0, "words": [], "member": member}
        )
        entry["points"] += pts
        entry["words"].append(up)
        return pts


# ── Cog ───────────────────────────────────────────────────────────────────────

class Anagrams(commands.Cog):
    """Multiplayer anagram game — find words hidden in the scrambled letters!"""

    def __init__(self, bot):
        self.bot    = bot
        self.games: dict = {}   # channel_id → AnagramGame
        self._tasks: dict = {}  # channel_id → asyncio.Task

    def cog_unload(self):
        for task in self._tasks.values():
            task.cancel()
        self.games.clear()
        self._tasks.clear()

    # ── $anagrams [seconds] ───────────────────────────────────────────────────

    @commands.group(invoke_without_command=True)
    async def anagrams(self, ctx: commands.Context, duration: int = 60):
        """
        Start an anagram round. Anyone in chat can find words.
        Optionally set the round length: `$anagrams 120`
        """
        if ctx.channel.id in self.games:
            await ctx.send("An anagram round is already running in this channel!")
            return

        if not DICTIONARY:
            await ctx.send(
                "The word dictionary isn't loaded. "
                "Please ask an admin to run `[p]pipinstall english-words` and reload the cog."
            )
            return

        duration = max(10, min(duration, 600))   # clamp: 10 s – 10 min
        word     = random.choice(SOURCE_WORDS)
        game     = AnagramGame(word, duration)
        self.games[ctx.channel.id] = game

        embed = discord.Embed(
            title="🔤  Anagram Round!",
            description=(
                f"## {' '.join(game.jumbled)}\n\n"
                f"Find words using these letters! You have **{duration} seconds**!\n\n"
                "**Scoring**\n"
                "3 letters = 40 pts  |  +20 pts per extra letter\n"
                f"Guess the full word = word score **+ {FULL_WORD_BONUS} bonus pts!**"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

        task = asyncio.create_task(self._run_round(ctx.channel, game))
        self._tasks[ctx.channel.id] = task

    @anagrams.command(name="stop")
    async def anagrams_stop(self, ctx: commands.Context):
        """Stop the current anagram round in this channel."""
        game = self.games.pop(ctx.channel.id, None)
        task = self._tasks.pop(ctx.channel.id, None)
        if task:
            task.cancel()
        if game is None:
            await ctx.send("No anagram round is running in this channel.")
            return
        embed = discord.Embed(
            title="🛑  Round Ended",
            description=f"The anagram round has been stopped.\nThe word was: **{game.word}**",
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed)

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _run_round(self, channel: discord.TextChannel, game: AnagramGame):
        await asyncio.sleep(game.duration)
        if self.games.get(channel.id) is game:
            self.games.pop(channel.id, None)
            self._tasks.pop(channel.id, None)
            await self._end_round(channel, game)

    async def _end_round(self, channel: discord.TextChannel, game: AnagramGame):
        if not game.scores:
            embed = discord.Embed(
                title="⏰  Time's Up!",
                description=f"No words were found this round.\nThe answer was: **{game.word}**",
                color=discord.Color.orange(),
            )
            await channel.send(embed=embed)
            return

        sorted_players = sorted(
            game.scores.values(), key=lambda e: e["points"], reverse=True
        )
        winner = sorted_players[0]

        embed = discord.Embed(
            title=f"⏰  Time's Up!   🏆  {winner['member'].display_name} wins!",
            color=discord.Color.gold(),
        )
        embed.add_field(name="The Word", value=f"**{game.word}**", inline=False)

        board = []
        medals = ["🥇", "🥈", "🥉"]
        for i, entry in enumerate(sorted_players):
            medal     = medals[i] if i < len(medals) else f"**{i + 1}.**"
            words_str = "  ·  ".join(entry["words"])
            board.append(
                f"{medal} **{entry['member'].display_name}** — "
                f"**{entry['points']} pts**\n"
                f"\u200b    {words_str}"   # zero-width space for indent
            )

        embed.add_field(name="Scoreboard", value="\n".join(board), inline=False)
        await channel.send(embed=embed)

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in self.games:
            return

        # Don't intercept bot commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        word = message.content.strip().lower()
        if len(word) < 3 or not word.isalpha():
            return

        game = self.games[message.channel.id]

        # ── Word already found ────────────────────────────────────────────────
        if game.already_found(word):
            emoji = await _find_emoji(message.guild, "retweet", "🔁")
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                pass
            return

        # ── Not a valid anagram word ──────────────────────────────────────────
        if not game.is_valid(word):
            return

        # ── Valid find ────────────────────────────────────────────────────────
        pts     = game.record(word, message.author)
        is_full = word.upper() == game.word

        check = await _find_emoji(message.guild, "check", "✅")
        try:
            await message.add_reaction(check)
        except discord.HTTPException:
            pass

        if is_full:
            embed = discord.Embed(
                title="🎊  Full Word Found!",
                description=(
                    f"{message.author.mention} cracked it — **{game.word}**!\n"
                    f"That earns **{pts} points** "
                    f"(word score + {FULL_WORD_BONUS} bonus)!"
                ),
                color=discord.Color.green(),
            )
            await message.channel.send(embed=embed)
        else:
            embed = discord.Embed(
                description=(
                    f"**{message.author.display_name}** found "
                    f"**{word.upper()}** for **{pts} pts**"
                ),
                color=0x95a5a6,   # gray left border
            )
            await message.channel.send(embed=embed)

        # ── Repost letters every 8 valid finds ───────────────────────────────
        if len(game.found) % 8 == 0:
            reminder = discord.Embed(
                description=f"🔤  **Letters:** {' '.join(game.jumbled)}",
                color=discord.Color.blurple(),
            )
            await message.channel.send(embed=reminder)
