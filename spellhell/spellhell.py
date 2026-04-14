import asyncio
import random
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Optional

import discord
from redbot.core import Config, commands

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

# ── Dictionary & Prefix Set ───────────────────────────────────────────────────

def _load_dictionary() -> frozenset:
    base: set = set()
    try:
        from english_words import get_english_words_set
        base = get_english_words_set(["web2"], lower=True)
    except Exception:
        try:
            from english_words import english_words_lower_set  # type: ignore
            base = english_words_lower_set
        except ImportError:
            pass
    return frozenset(w for w in base if w.isalpha())


def _build_prefix_set(dictionary: frozenset) -> frozenset:
    prefixes: set = set()
    for word in dictionary:
        for i in range(1, len(word) + 1):
            prefixes.add(word[:i])
    return frozenset(prefixes)


DICTIONARY: frozenset = _load_dictionary()
PREFIX_SET: frozenset = _build_prefix_set(DICTIONARY)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_LIVES = 4
EXPLOSION_GIF = "https://tenor.com/view/cat-explode-cat-meme-cat-exploding-explode-cat-meme-cat-meme-explosion-gif-9983525941267276580"

# ── Word helpers ──────────────────────────────────────────────────────────────

def _is_complete_word(fragment: str, min_len: int) -> bool:
    return len(fragment) >= min_len and fragment.lower() in DICTIONARY


def _is_valid_prefix(fragment: str) -> bool:
    return fragment.lower() in PREFIX_SET


def _safe_next_letters(fragment: str, min_len: int) -> list:
    """Letters that extend fragment to a valid prefix without completing a word >= min_len."""
    f = fragment.lower()
    return [
        c for c in "abcdefghijklmnopqrstuvwxyz"
        if (f + c) in PREFIX_SET and not _is_complete_word(f + c, min_len)
    ]


def _valid_next_letters(fragment: str) -> list:
    """Letters that keep fragment as a valid prefix of any dictionary word."""
    f = fragment.lower()
    return [c for c in "abcdefghijklmnopqrstuvwxyz" if (f + c) in PREFIX_SET]


def _lives_display(lives_lost: int) -> str:
    remaining = MAX_LIVES - lives_lost
    return "❤️" * remaining + "🖤" * lives_lost


def _fragment_display(fragment: str) -> str:
    if not fragment:
        return "*empty — new round!*"
    return f"**`{fragment.upper()}`**  ({len(fragment)} letter{'s' if len(fragment) != 1 else ''})"

# ── Player ────────────────────────────────────────────────────────────────────

@dataclass
class SpellPlayer:
    member: Optional[discord.Member]
    lives_lost: int = 0
    is_cpu: bool = False

    @property
    def alive(self) -> bool:
        return self.lives_lost < MAX_LIVES

    @property
    def display_name(self) -> str:
        return "Spell Bot" if self.is_cpu else self.member.display_name

    @property
    def mention(self) -> str:
        return "**Spell Bot** 🤖" if self.is_cpu else self.member.mention

# ── Game State ────────────────────────────────────────────────────────────────

class SpellHellState:
    def __init__(self, channel, turn_time: int, min_word_len: int):
        self.channel = channel
        self.turn_time = turn_time
        self.min_word_len = min_word_len

        self.players: list = []
        self.current_idx: int = 0
        self.prev_idx: Optional[int] = None
        self.fragment: str = ""
        self.phase: str = "joining"

        self.turn_event: asyncio.Event = asyncio.Event()
        self.challenge_event: asyncio.Event = asyncio.Event()
        self.pending_letter: Optional[str] = None
        self.challenge_issued: bool = False
        self.challenge_response: Optional[str] = None

        self.join_message: Optional[discord.Message] = None
        self.game_task: Optional[asyncio.Task] = None

    def alive_players(self) -> list:
        return [p for p in self.players if p.alive]

    def advance_turn(self) -> None:
        n = len(self.players)
        for i in range(1, n + 1):
            nxt = (self.current_idx + i) % n
            if self.players[nxt].alive:
                self.current_idx = nxt
                return

    def advance_from(self, idx: int) -> None:
        """Advance current_idx to the next alive player after the given index."""
        self.current_idx = idx
        self.advance_turn()

# ── Views ─────────────────────────────────────────────────────────────────────

class JoinView(discord.ui.View):
    def __init__(self, game: SpellHellState):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="✋")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.phase != "joining":
            await interaction.response.send_message("The join phase is over!", ephemeral=True)
            return
        if any(p.member and p.member.id == interaction.user.id for p in self.game.players):
            await interaction.response.send_message("You're already in!", ephemeral=True)
            return
        self.game.players.append(SpellPlayer(member=interaction.user))
        await interaction.response.send_message("You've joined Spell Hell! 🔥", ephemeral=True)
        with suppress(discord.HTTPException):
            await interaction.message.edit(embed=_join_embed(self.game))


class TurnView(discord.ui.View):
    def __init__(self, game: SpellHellState, current_player: SpellPlayer):
        super().__init__(timeout=None)
        self.game = game
        self.current_player = current_player

        btn = discord.ui.Button(
            label="Challenge!",
            style=discord.ButtonStyle.danger,
            emoji="❓",
            disabled=(game.prev_idx is None),
        )
        btn.callback = self._on_challenge
        self.add_item(btn)

    async def _on_challenge(self, interaction: discord.Interaction):
        if self.game.phase != "playing":
            await interaction.response.send_message("Can't challenge right now!", ephemeral=True)
            return
        if self.game.prev_idx is None:
            await interaction.response.send_message("No previous move to challenge!", ephemeral=True)
            return
        if interaction.user.id != self.current_player.member.id:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        if self.game.turn_event.is_set():
            await interaction.response.send_message("Turn already resolved!", ephemeral=True)
            return
        self.game.challenge_issued = True
        self.game.turn_event.set()
        await interaction.response.send_message("Challenge issued! 🎯", ephemeral=True)

# ── Embeds ────────────────────────────────────────────────────────────────────

def _join_embed(game: SpellHellState) -> discord.Embed:
    if game.players:
        plist = "\n".join(f"• {p.display_name}" for p in game.players)
    else:
        plist = "*No one yet — be the first!*"
    return discord.Embed(
        title=f"🔥  Spell Hell{DEV_LABEL}",
        description=(
            "Take turns adding **one letter** to a growing word fragment.\n"
            "Complete a real word and you **lose a life** — lose all 4 and you're out! 💀\n"
            "You can also **Challenge** the previous player — if their letter leads nowhere, they lose a life; false challenge and you do!\n\n"
            f"**Players ({len(game.players)}):**\n{plist}"
        ),
        color=discord.Color.red(),
    ).add_field(
        name="Settings",
        value=(
            f"⏱ **{game.turn_time}s** per turn  ·  "
            f"📏 Min word: **{game.min_word_len}** letters"
        ),
        inline=False,
    )


def _turn_embed(game: SpellHellState, current: SpellPlayer, remaining: Optional[int] = None) -> discord.Embed:
    countdown = f"\n⏳ **{remaining}s** remaining" if remaining is not None and remaining <= 10 else ""
    status_lines = []
    for p in game.players:
        if not p.alive:
            status_lines.append(f"~~{p.display_name}~~ 💀")
        else:
            marker = "▶ " if p == current else "\u00a0\u00a0"
            status_lines.append(f"{marker}{p.display_name}: {_lives_display(p.lives_lost)}")

    challenge_hint = (
        "\n*Click **Challenge!** if you think the previous player's letter leads nowhere.*"
        if game.prev_idx is not None else ""
    )

    return discord.Embed(
        title="🔥  Spell Hell",
        description=(
            f"**Fragment:** {_fragment_display(game.fragment)}\n\n"
            f"{current.mention} — type a **single letter** to add to the fragment!"
            + challenge_hint
            + countdown
        ),
        color=discord.Color.red(),
    ).add_field(name="Players", value="\n".join(status_lines) or "—", inline=False)


def _lost_life_embed(player: SpellPlayer) -> discord.Embed:
    return discord.Embed(
        description=(
            f"💔 **{player.display_name}** loses a life!\n"
            f"Lives: {_lives_display(player.lives_lost)}"
        ),
        color=discord.Color.orange(),
    )


def _eliminated_embed(player: SpellPlayer) -> discord.Embed:
    return discord.Embed(
        description=f"💀 **{player.display_name}** has lost all their lives and is **eliminated**!",
        color=discord.Color.red(),
    )


def _winner_embed(winner: SpellPlayer, wins: int, games: int) -> discord.Embed:
    return discord.Embed(
        title=f"🎉  {winner.display_name} wins Spell Hell!",
        description=(
            f"{winner.mention} is the last one standing!\n\n"
            f"They've won **{wins}** out of **{games}** game{'s' if games != 1 else ''}!"
        ),
        color=discord.Color.gold(),
    )


def _word_completed_embed(player: SpellPlayer, word: str) -> discord.Embed:
    return discord.Embed(
        description=(
            f"🔤 **{player.display_name}** completed the word **{word.upper()}**! "
            "Losing a life..."
        ),
        color=discord.Color.orange(),
    )


def _challenge_embed(challenger: SpellPlayer, challenged: SpellPlayer, fragment: str, min_word_len: int) -> discord.Embed:
    return discord.Embed(
        title="❓  Challenge!",
        description=(
            f"{challenger.mention} challenges {challenged.mention}!\n\n"
            f"**{challenged.display_name}**, you have **30 seconds** — type a real word of "
            f"**{min_word_len}+** letters starting with **`{fragment.upper()}`**!"
        ),
        color=discord.Color.yellow(),
    )


def _challenge_result_embed(loser: SpellPlayer, fragment: str, word: Optional[str], challenger_won: bool) -> discord.Embed:
    if challenger_won:
        desc = (
            f"❌ **{loser.display_name}** couldn't name a valid word starting with **`{fragment.upper()}`**!\n"
            "The bluff has been called! Losing a life..."
        )
    else:
        desc = (
            f"✅ **{loser.display_name}** issued a false challenge! "
            f"**{word.upper()}** is a valid word starting with **`{fragment.upper()}`**!\n"
            "False challenge — losing a life..."
        )
    return discord.Embed(description=desc, color=discord.Color.orange())

# ── Cog ───────────────────────────────────────────────────────────────────────

class SpellHell(commands.Cog):
    """Spell Hell — add letters without completing a word, or lose a life!"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=9381047562, force_registration=True)
        self.config.register_guild(turn_time=45, min_word_len=4)
        self.config.register_member(wins=0, games_played=0)

    def cog_unload(self):
        for game in self.games.values():
            if game.game_task:
                game.game_task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="spellhell")
    async def spellhell(self, ctx: commands.Context):
        """Start a Spell Hell word game. Players have 20 seconds to join."""
        if ctx.channel.id in self.games:
            await ctx.send("A Spell Hell game is already running in this channel!")
            return

        gc = self.config.guild(ctx.guild)
        game = SpellHellState(
            channel=ctx.channel,
            turn_time=await gc.turn_time(),
            min_word_len=await gc.min_word_len(),
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
        return "Spell Hell"

    @commands.command(name="spellhelltime")
    async def spellhelltime(self, ctx: commands.Context, seconds: int):
        """Set the turn time in seconds (15–120). Example: `$spellhelltime 30`"""
        seconds = max(15, min(seconds, 120))
        await self.config.guild(ctx.guild).turn_time.set(seconds)
        await ctx.send(f"Turn time set to **{seconds}** seconds.")

    @commands.command(name="spellhellmin")
    async def spellhellmin(self, ctx: commands.Context, length: int):
        """Set the minimum word length that counts as losing (3–6). Example: `$spellhellmin 4`"""
        length = max(3, min(length, 6))
        await self.config.guild(ctx.guild).min_word_len.set(length)
        await ctx.send(f"Minimum word length set to **{length}** letters.")

    @commands.command(name="spellhellstats")
    async def spellhellstats(self, ctx: commands.Context, member: discord.Member = None):
        """Show Spell Hell win stats for yourself or another player."""
        target = member or ctx.author
        wins = await self.config.member(target).wins()
        games = await self.config.member(target).games_played()
        await ctx.send(embed=discord.Embed(
            title=f"🔥  {target.display_name}'s Spell Hell Stats",
            description=(
                f"**Wins:** {wins}\n"
                f"**Games played:** {games}\n"
                f"**Win rate:** {wins/games*100:.1f}%" if games else "No games played yet!"
            ),
            color=discord.Color.red(),
        ))

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: SpellHellState):
        try:
            # Join phase (20 seconds)
            await asyncio.sleep(20)
            game.phase = "ended"
            with suppress(discord.HTTPException):
                await game.join_message.edit(view=discord.ui.View())

            if len(game.players) == 0:
                await ctx.send(embed=discord.Embed(
                    description="Nobody joined Spell Hell. Game cancelled.",
                    color=discord.Color.orange(),
                ))
                return

            # Add CPU bot for solo testing
            if len(game.players) == 1:
                game.players.append(SpellPlayer(member=None, is_cpu=True))
                await ctx.send(embed=discord.Embed(
                    description="🔥 Only one player — **Spell Bot** has joined to keep you company!",
                    color=discord.Color.red(),
                ))

            game.phase = "playing"
            random.shuffle(game.players)
            game.current_idx = 0

            order_str = " → ".join(p.display_name for p in game.players) + " → *(repeats)*"
            await ctx.send(embed=discord.Embed(
                title="🔥  Spell Hell — Game Start!",
                description=(
                    f"**Turn order:** {order_str}\n\n"
                    f"First turn: **{game.players[0].display_name}**\n"
                    f"Min word: **{game.min_word_len}** letters  ·  Turn time: **{game.turn_time}s**\n\n"
                    "Type a **single letter** on your turn to add to the fragment.\n"
                    f"Complete a real word ≥ min length → you **lose a life** (4 lives total)!\n"
                    "You can also **Challenge** if you think someone is bluffing!\n"
                    "Lose all 4 lives = eliminated. Last survivor wins!"
                ),
                color=discord.Color.red(),
            ))

            # Main game loop
            while len(game.alive_players()) > 1:
                current = game.players[game.current_idx]
                if not current.alive:
                    game.advance_turn()
                    continue

                loser = await self._do_turn(game, current)

                if loser is not None:
                    loser_idx = game.players.index(loser)
                    loser.lives_lost += 1
                    if not loser.alive:
                        await game.channel.send(embed=_eliminated_embed(loser))
                        await game.channel.send(EXPLOSION_GIF)
                    else:
                        await game.channel.send(embed=_lost_life_embed(loser))
                    game.fragment = ""
                    game.prev_idx = None
                    game.advance_from(loser_idx)
                else:
                    game.advance_turn()

            # Winner
            alive = game.alive_players()
            if alive:
                winner = alive[0]
                if winner.is_cpu:
                    await game.channel.send(embed=discord.Embed(
                        title="🔥  Spell Bot wins!",
                        description="The bot outlasted everyone! Better luck next time!",
                        color=discord.Color.gold(),
                    ))
                else:
                    wins, games_played = await self._record_result(
                        [p for p in game.players if not p.is_cpu], winner
                    )
                    await game.channel.send(embed=_winner_embed(winner, wins, games_played))

        except asyncio.CancelledError:
            pass
        finally:
            self.games.pop(ctx.channel.id, None)

    async def _do_turn(self, game: SpellHellState, current: SpellPlayer) -> Optional[SpellPlayer]:
        """Run one turn. Returns the player who loses a life, or None."""
        if current.is_cpu:
            return await self._do_cpu_turn(game, current)

        # Human turn
        game.turn_event.clear()
        game.pending_letter = None
        game.challenge_issued = False

        view = TurnView(game, current)
        msg = await game.channel.send(embed=_turn_embed(game, current), view=view)

        for remaining in range(game.turn_time, 0, -1):
            if remaining <= 10:
                with suppress(discord.HTTPException):
                    await msg.edit(embed=_turn_embed(game, current, remaining))
            try:
                await asyncio.wait_for(game.turn_event.wait(), timeout=1.0)
                break
            except asyncio.TimeoutError:
                pass

        with suppress(discord.HTTPException):
            await msg.edit(view=discord.ui.View())

        if game.challenge_issued:
            return await self._resolve_challenge(game, current)

        if not game.turn_event.is_set():
            await game.channel.send(embed=discord.Embed(
                description=f"⏰ **{current.display_name}** ran out of time!",
                color=discord.Color.orange(),
            ))
            return current

        letter = game.pending_letter
        new_fragment = game.fragment + letter

        if _is_complete_word(new_fragment, game.min_word_len):
            await game.channel.send(embed=_word_completed_embed(current, new_fragment))
            return current

        # Letter accepted — valid or bluff, challenges will sort it out
        game.fragment = new_fragment
        game.prev_idx = game.current_idx
        return None

    async def _do_cpu_turn(self, game: SpellHellState, current: SpellPlayer) -> Optional[SpellPlayer]:
        """CPU player takes a turn."""
        await asyncio.sleep(random.uniform(1.5, 3.0))

        # Prefer letters that don't complete a word
        safe = _safe_next_letters(game.fragment, game.min_word_len)
        if safe:
            letter = random.choice(safe)
        else:
            valid = _valid_next_letters(game.fragment)
            letter = random.choice(valid) if valid else random.choice(list("abcdefghijklmnopqrstuvwxyz"))

        new_fragment = game.fragment + letter
        await game.channel.send(
            f"🤖 **Spell Bot** adds **{letter.upper()}** → {_fragment_display(new_fragment)}"
        )

        if _is_complete_word(new_fragment, game.min_word_len):
            await game.channel.send(embed=_word_completed_embed(current, new_fragment))
            return current

        game.fragment = new_fragment
        game.prev_idx = game.current_idx
        return None

    async def _resolve_challenge(self, game: SpellHellState, challenger: SpellPlayer) -> SpellPlayer:
        """Handle a challenge. Returns the player who loses a life."""
        challenged = game.players[game.prev_idx]
        fragment = game.fragment

        game.phase = "challenge"
        game.challenge_event.clear()
        game.challenge_response = None

        await game.channel.send(embed=_challenge_embed(challenger, challenged, fragment, game.min_word_len))

        if challenged.is_cpu:
            asyncio.create_task(self._cpu_respond_to_challenge(game, fragment))

        try:
            await asyncio.wait_for(game.challenge_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass

        game.phase = "playing"

        response = game.challenge_response
        if (
            response
            and response.lower().startswith(fragment.lower())
            and response.lower() in DICTIONARY
            and len(response) >= game.min_word_len
        ):
            # Challenged proved their word — challenger issued a false challenge
            await game.channel.send(embed=_challenge_result_embed(challenger, fragment, response, challenger_won=False))
            return challenger
        else:
            # Challenged couldn't prove it — the bluff is busted
            await game.channel.send(embed=_challenge_result_embed(challenged, fragment, None, challenger_won=True))
            return challenged

    async def _cpu_respond_to_challenge(self, game: SpellHellState, fragment: str):
        """CPU finds a word starting with fragment to defend against a challenge."""
        await asyncio.sleep(random.uniform(1.5, 2.5))
        f = fragment.lower()
        candidates = [
            w for w in DICTIONARY
            if w.startswith(f) and len(w) >= game.min_word_len
        ]
        if candidates:
            word = random.choice(candidates[:20])
            game.challenge_response = word
            await game.channel.send(f"🤖 **Spell Bot** responds: **{word.upper()}**")
        else:
            game.challenge_response = None
            await game.channel.send("🤖 **Spell Bot** has no response...")
        game.challenge_event.set()

    async def _record_result(self, human_players: list, winner: SpellPlayer):
        """Record games played for all humans, win for winner. Returns (wins, games_played)."""
        for p in human_players:
            gp = await self.config.member(p.member).games_played()
            await self.config.member(p.member).games_played.set(gp + 1)
        w = await self.config.member(winner.member).wins()
        await self.config.member(winner.member).wins.set(w + 1)
        gp = await self.config.member(winner.member).games_played()
        return w + 1, gp

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

        if game.phase == "playing":
            current = game.players[game.current_idx]
            if current.is_cpu or message.author.id != current.member.id:
                return
            if game.turn_event.is_set():
                return

            text = message.content.strip().lower()
            if len(text) == 1 and text.isalpha():
                game.pending_letter = text
                game.turn_event.set()

        elif game.phase == "challenge":
            if game.prev_idx is None:
                return
            challenged = game.players[game.prev_idx]
            if challenged.is_cpu or message.author.id != challenged.member.id:
                return
            if game.challenge_event.is_set():
                return

            text = message.content.strip().lower()
            if text.isalpha() and len(text) >= 2:
                game.challenge_response = text
                game.challenge_event.set()
