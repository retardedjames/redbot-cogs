import asyncio
import json
import random
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import discord
from redbot.core import Config, commands

DATA_PATH = Path(__file__).parent
QUESTIONS_FILE = DATA_PATH / "questions.json"
STATE_FILE = DATA_PATH / "state.json"
COMPLIMENTS_FILE = DATA_PATH / "Random Compliments.txt"
INSULTS_FILE = DATA_PATH / "Random Insults.txt"

DEFAULT_TIME = 30
DEFAULT_QUESTIONS = 100

async def _find_emoji(guild: discord.Guild, name: str, fallback: str):
    emoji = discord.utils.get(guild.emojis, name=name)
    return emoji if emoji else fallback


def _format_blank(answer: str) -> str:
    """Return `\_ \_ \_ \_` style blank matching the answer's character count.
    Underscores are backslash-escaped so Discord doesn't treat them as italic markdown.
    Multi-word answers get double-space between word blanks."""
    words = answer.split()
    return "  ".join(" ".join(r"\_" for _ in word) for word in words)


def _load_questions() -> list:
    return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))


def _load_state() -> tuple:
    """Return (order, index), creating a fresh shuffle if state is missing/invalid."""
    questions = _load_questions()
    n = len(questions)
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            order, idx = state["order"], state["index"]
            if len(order) == n and 0 <= idx <= n:
                return order, idx
        except Exception:
            pass
    order = list(range(n))
    random.shuffle(order)
    return order, 0


def _save_state(order: list, index: int) -> None:
    STATE_FILE.write_text(json.dumps({"order": order, "index": index}), encoding="utf-8")


def _get_next_questions(num: int) -> list:
    """Fetch `num` questions in shuffle order, reshuffling when the deck runs out."""
    all_q = _load_questions()
    n = len(all_q)
    order, idx = _load_state()
    result = []
    for _ in range(num):
        if idx >= n:
            order = list(range(n))
            random.shuffle(order)
            idx = 0
        result.append(all_q[order[idx]])
        idx += 1
    _save_state(order, idx)
    return result


def _random_line(path: Path, fallback: str) -> str:
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return random.choice(lines) if lines else fallback
    except Exception:
        return fallback


@dataclass
class TriviaGame:
    channel: discord.TextChannel
    questions: list
    total: int
    current_q_idx: int = 0          # 1-indexed; 0 = between questions
    scores: dict = field(default_factory=dict)   # user_id -> int score
    names: dict = field(default_factory=dict)    # user_id -> display_name
    answer_event: asyncio.Event = field(default_factory=asyncio.Event)
    correct_guesser: Optional[discord.Member] = None
    task: Optional[asyncio.Task] = None
    phase: str = "playing"


class Trivia(commands.Cog):
    """Trivia For Retards — fill-in-the-blank trivia game."""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=7734219856, force_registration=True)
        self.config.register_guild(question_time=DEFAULT_TIME)

    def cog_unload(self):
        for game in self.games.values():
            if game.task:
                game.task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="tr")
    @commands.guild_only()
    async def tr(self, ctx: commands.Context, num: int = DEFAULT_QUESTIONS):
        """Start a trivia game. $tr for 100 questions, $tr [number] for custom count."""
        if ctx.channel.id in self.games:
            await ctx.send("A trivia game is already running here! Use $end to stop it.")
            return
        num = max(1, min(num, 500))
        questions = _get_next_questions(num)
        game = TriviaGame(channel=ctx.channel, questions=questions, total=num)
        self.games[ctx.channel.id] = game
        game.task = asyncio.create_task(self._run_game(ctx, game))

    @commands.command(name="trtime")
    @commands.guild_only()
    async def trtime(self, ctx: commands.Context, seconds: int):
        """Permanently change the time per question. Example: $trtime 40"""
        seconds = max(5, min(seconds, 120))
        await self.config.guild(ctx.guild).question_time.set(seconds)
        await ctx.send(f"Trivia question time set to **{seconds}** seconds.")

    async def force_stop_game(self, channel_id: int):
        """Called by $end — stop any running trivia game in channel_id."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        game.phase = "ended"
        if game.task:
            game.task.cancel()
        return "Trivia"

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: TriviaGame):
        try:
            q_time = await self.config.guild(ctx.guild).question_time()

            for i, q_data in enumerate(game.questions):
                if game.phase == "ended":
                    break

                answer = q_data["a"]
                blank = _format_blank(answer)
                display_q = q_data["q"].replace("{BLANK}", blank)

                game.current_q_idx = i + 1
                game.answer_event.clear()
                game.correct_guesser = None

                def _q_text(remaining: int) -> str:
                    return (
                        f"-# Question {i + 1} out of {game.total}  ·  ⏱ {remaining}s\n"
                        f"# {display_q}"
                    )

                msg = await ctx.send(_q_text(q_time))

                # Countdown — update message every second
                for remaining in range(q_time - 1, -1, -1):
                    try:
                        await asyncio.wait_for(game.answer_event.wait(), timeout=1.0)
                        break
                    except asyncio.TimeoutError:
                        with suppress(discord.HTTPException):
                            await msg.edit(content=_q_text(remaining))

                if game.phase == "ended":
                    break

                if game.answer_event.is_set() and game.correct_guesser:
                    member = game.correct_guesser
                    uid = member.id
                    game.scores[uid] = game.scores.get(uid, 0) + 1
                    game.names[uid] = member.display_name
                    pts = game.scores[uid]
                    compliment = _random_line(COMPLIMENTS_FILE, "Nice one!")
                    result_embed = discord.Embed(
                        description=(
                            f"{member.display_name} got it!  {pts} pts  —  "
                            f"**{answer}** was correct.  {compliment}"
                        ),
                        color=discord.Color.green(),
                    )
                else:
                    insult = _random_line(INSULTS_FILE, "Nobody got it.")
                    result_embed = discord.Embed(
                        description=f"The answer was **{answer}**.  {insult}",
                        color=discord.Color.red(),
                    )

                await ctx.send(embed=result_embed)

                if i < game.total - 1 and game.phase != "ended":
                    await asyncio.sleep(2)
                    await ctx.send("\u200b")

            if game.phase != "ended":
                await self._show_final_scores(ctx, game)

        except asyncio.CancelledError:
            pass
        finally:
            self.games.pop(ctx.channel.id, None)

    async def _show_final_scores(self, ctx: commands.Context, game: TriviaGame):
        if not game.scores:
            await ctx.send(embed=discord.Embed(
                title="Game Over!",
                description="Nobody got any correct answers!",
                color=discord.Color.orange(),
            ))
            return

        sorted_scores = sorted(game.scores.items(), key=lambda x: x[1], reverse=True)
        winner_id, _ = sorted_scores[0]
        winner_name = game.names.get(winner_id, "???")

        rows = "\n".join(
            f"**{rank + 1}.** {game.names.get(uid, '???')} — {pts} pts"
            for rank, (uid, pts) in enumerate(sorted_scores)
        )
        embed = discord.Embed(
            title=f"🎉  {winner_name} WINS! 🎉",
            description=f"**Final Scores:**\n{rows}",
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    # ── Message Listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.games.get(message.channel.id)
        if not game or game.phase != "playing" or game.current_q_idx == 0:
            return
        # Ignore bot commands
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        # Only first correct answer counts
        if game.answer_event.is_set():
            return

        q_data = game.questions[game.current_q_idx - 1]
        if message.content.strip().lower() == q_data["a"].strip().lower():
            game.correct_guesser = message.author
            game.answer_event.set()
            check = await _find_emoji(message.guild, "check", "✅")
            with suppress(discord.HTTPException):
                await message.add_reaction(check)
