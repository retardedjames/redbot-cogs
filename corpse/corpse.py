import asyncio
from contextlib import suppress
from typing import Optional

import discord
from redbot.core import Config, commands

# ── Dev mode ──────────────────────────────────────────────────────────────────
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

MIN_SENTENCES = 7
DEFAULT_TURN_TIMEOUT = 300  # 5 minutes


def _last_n_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[-n:]) if words else ""


# ── Game State ────────────────────────────────────────────────────────────────

class CorpseGameState:
    def __init__(self, channel, turn_timeout: int):
        self.channel = channel
        self.turn_timeout = turn_timeout
        self.players: list = []         # list of discord.Member
        self.sentences: list = []       # list of (member, str); str may be "[...]" for skip
        self.current_idx: int = 0
        self.phase: str = "joining"

        self.sentence_event: asyncio.Event = asyncio.Event()
        self.pending_sentence: Optional[str] = None
        self.join_message: Optional[discord.Message] = None
        self.game_task: Optional[asyncio.Task] = None

    @property
    def current_player(self) -> discord.Member:
        return self.players[self.current_idx]

    def advance_turn(self):
        self.current_idx = (self.current_idx + 1) % len(self.players)

    def should_end(self) -> bool:
        n = len(self.sentences)
        return n >= MIN_SENTENCES and n % len(self.players) == 0

    def hint_for_next(self) -> str:
        """Last 4 words of the most recent non-skipped sentence."""
        for _, sent in reversed(self.sentences):
            if sent != "[...]":
                return _last_n_words(sent, 4)
        return ""


# ── Modal ─────────────────────────────────────────────────────────────────────

class SentenceModal(discord.ui.Modal):
    def __init__(self, game: CorpseGameState, hint: str):
        super().__init__(title="Exquisite Corpse ✍️")
        self.game = game

        label = "Continue the story..." if hint else "Start the story!"
        placeholder = f'Last 4 words: "{hint}"' if hint else "Write the opening sentence of the story!"

        self.sentence_input = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder=placeholder[:100],
            min_length=5,
            max_length=500,
        )
        self.add_item(self.sentence_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.game.phase != "playing" or self.game.sentence_event.is_set():
            await interaction.response.send_message(
                "This submission is no longer valid.", ephemeral=True
            )
            return
        self.game.pending_sentence = self.sentence_input.value.strip()
        self.game.sentence_event.set()
        await interaction.response.send_message(
            "Your sentence has been woven into the story! ✍️", ephemeral=True
        )


# ── Views ─────────────────────────────────────────────────────────────────────

class JoinView(discord.ui.View):
    def __init__(self, game: CorpseGameState):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="✋")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.phase != "joining":
            await interaction.response.send_message("The join phase is over!", ephemeral=True)
            return
        if any(p.id == interaction.user.id for p in self.game.players):
            await interaction.response.send_message("You're already in!", ephemeral=True)
            return
        self.game.players.append(interaction.user)
        await interaction.response.send_message("You've joined Exquisite Corpse! 📜", ephemeral=True)
        with suppress(discord.HTTPException):
            await interaction.message.edit(embed=_join_embed(self.game))


class WriteView(discord.ui.View):
    def __init__(self, game: CorpseGameState, player: discord.Member, hint: str):
        super().__init__(timeout=None)
        self.game = game
        self.player = player
        self.hint = hint

    @discord.ui.button(label="Write Your Sentence", style=discord.ButtonStyle.primary, emoji="✍️")
    async def write_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return
        if self.game.sentence_event.is_set():
            await interaction.response.send_message(
                "You've already submitted your sentence!", ephemeral=True
            )
            return
        modal = SentenceModal(self.game, self.hint)
        await interaction.response.send_modal(modal)


# ── Embeds ────────────────────────────────────────────────────────────────────

def _join_embed(game: CorpseGameState) -> discord.Embed:
    plist = "\n".join(f"• {p.display_name}" for p in game.players) or "*No one yet — be the first!*"
    timeout_min = game.turn_timeout // 60
    return discord.Embed(
        title=f"📜  Exquisite Corpse{DEV_LABEL}",
        description=(
            "A collaborative blind storytelling game!\n"
            "Take turns writing sentences to build a story — "
            "but you can only see the **last 4 words** of what came before.\n\n"
            f"**Players ({len(game.players)}):**\n{plist}"
        ),
        color=discord.Color.blurple(),
    ).add_field(
        name="How to play",
        value=(
            "When it's your turn, click **Write Your Sentence** and type one sentence in the popup.\n"
            f"You have **{timeout_min} minute{'s' if timeout_min != 1 else ''}** per turn.\n"
            f"The game ends after at least **{MIN_SENTENCES}** sentences once all players "
            "have had equal turns.\nThe full story is revealed at the end — surprises guaranteed! 🎭"
        ),
        inline=False,
    )


def _turn_embed(game: CorpseGameState, player: discord.Member, hint: str, turn_num: int) -> discord.Embed:
    timeout_min = game.turn_timeout // 60
    if hint:
        context_line = f"**Last 4 words:** *\"...{hint}\"*"
    else:
        context_line = "*You're first — start the story however you like!*"

    sentences_written = len(game.sentences)
    if sentences_written >= MIN_SENTENCES:
        progress = f"**{sentences_written}** sentences written — finishing this round, then the story ends!"
    else:
        progress = f"**{sentences_written}** / {MIN_SENTENCES}+ sentences written"

    return discord.Embed(
        title="📜  Exquisite Corpse",
        description=(
            f"**Sentence #{turn_num}** — {player.mention}, it's your turn!\n\n"
            f"{context_line}\n\n"
            "Click **Write Your Sentence** to open the writing prompt.\n"
            f"*You have {timeout_min} minute{'s' if timeout_min != 1 else ''} to respond.*"
        ),
        color=discord.Color.blurple(),
    ).add_field(name="Progress", value=progress, inline=False)


def _story_reveal_embed(game: CorpseGameState) -> discord.Embed:
    lines = []
    for member, sentence in game.sentences:
        if sentence == "[...]":
            lines.append(f"**{member.display_name}:** *(skipped)*")
        else:
            lines.append(f"**{member.display_name}:** {sentence}")

    story = "\n\n".join(lines)
    if len(story) > 4000:
        story = story[:3950] + "\n\n*[story continues beyond Discord's limit...]*"

    contributors = ", ".join(p.display_name for p in game.players)
    return discord.Embed(
        title="📖  The Complete Story",
        description=story,
        color=discord.Color.gold(),
    ).set_footer(
        text=f"Written by: {contributors}  ·  {len(game.sentences)} sentences"
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class ExquisiteCorpse(commands.Cog):
    """Exquisite Corpse — blind collaborative storytelling game."""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}
        self.config = Config.get_conf(self, identifier=7391820465, force_registration=True)
        self.config.register_guild(turn_timeout=DEFAULT_TURN_TIMEOUT)

    def cog_unload(self):
        for game in self.games.values():
            if game.game_task:
                game.game_task.cancel()
        self.games.clear()

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="corpse")
    async def corpse(self, ctx: commands.Context):
        """Start an Exquisite Corpse storytelling game. Players have 30 seconds to join."""
        if ctx.channel.id in self.games:
            await ctx.send("An Exquisite Corpse game is already running in this channel!")
            return

        turn_timeout = await self.config.guild(ctx.guild).turn_timeout()
        game = CorpseGameState(channel=ctx.channel, turn_timeout=turn_timeout)
        self.games[ctx.channel.id] = game

        view = JoinView(game)
        join_msg = await ctx.send(embed=_join_embed(game), view=view)
        game.join_message = join_msg

        game.game_task = asyncio.create_task(self._run_game(ctx, game))

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in this channel. Returns game name if stopped, else None."""
        game = self.games.pop(channel_id, None)
        if game is None:
            return None
        if game.game_task:
            game.game_task.cancel()
        game.phase = "ended"
        return "Exquisite Corpse"

    @commands.command(name="corpsetime")
    async def corpsetime(self, ctx: commands.Context, minutes: int):
        """Set the per-turn time limit in minutes (1–10). Example: `$corpsetime 3`"""
        minutes = max(1, min(minutes, 10))
        await self.config.guild(ctx.guild).turn_timeout.set(minutes * 60)
        await ctx.send(f"Turn time limit set to **{minutes}** minute{'s' if minutes != 1 else ''}.")

    # ── Game Runner ───────────────────────────────────────────────────────────

    async def _run_game(self, ctx: commands.Context, game: CorpseGameState):
        try:
            # Join phase — 30 seconds
            await asyncio.sleep(30)
            game.phase = "ended"
            with suppress(discord.HTTPException):
                await game.join_message.edit(view=discord.ui.View())

            if len(game.players) < 2:
                await ctx.send(embed=discord.Embed(
                    description="Not enough players joined (need at least **2**). Game cancelled.",
                    color=discord.Color.orange(),
                ))
                return

            game.phase = "playing"
            order_str = " → ".join(p.display_name for p in game.players) + " → *(repeats)*"
            await ctx.send(embed=discord.Embed(
                title="📜  Exquisite Corpse — Begin!",
                description=(
                    f"**Player order:** {order_str}\n\n"
                    "Each player sees only the **last 4 words** of the previous sentence "
                    "and writes the next one.\n"
                    f"The story ends after **{MIN_SENTENCES}+** sentences "
                    "once all players have had equal turns.\n\n"
                    "Watch for your turn prompt! 👀"
                ),
                color=discord.Color.blurple(),
            ))

            # Main loop
            while not game.should_end():
                player = game.current_player
                turn_num = len(game.sentences) + 1
                hint = game.hint_for_next()

                game.sentence_event.clear()
                game.pending_sentence = None

                view = WriteView(game, player, hint)
                msg = await game.channel.send(
                    embed=_turn_embed(game, player, hint, turn_num),
                    view=view,
                )

                try:
                    await asyncio.wait_for(game.sentence_event.wait(), timeout=game.turn_timeout)
                except asyncio.TimeoutError:
                    with suppress(discord.HTTPException):
                        await msg.edit(view=discord.ui.View())
                    await game.channel.send(embed=discord.Embed(
                        description=f"⏭️ **{player.display_name}** took too long and was skipped!",
                        color=discord.Color.orange(),
                    ))
                    game.sentences.append((player, "[...]"))
                    game.advance_turn()
                    continue

                with suppress(discord.HTTPException):
                    await msg.edit(view=discord.ui.View())

                sentence = game.pending_sentence
                game.sentences.append((player, sentence))
                game.advance_turn()

                await game.channel.send(embed=discord.Embed(
                    description=(
                        f"✅ **{player.display_name}** has written their sentence! "
                        f"(**{len(game.sentences)}** written so far)"
                    ),
                    color=discord.Color.blurple(),
                ))

            # Reveal
            await game.channel.send(embed=discord.Embed(
                description="🎭 The story is complete... behold what you have created together!",
                color=discord.Color.gold(),
            ))
            await asyncio.sleep(2)
            await game.channel.send(embed=_story_reveal_embed(game))

        except asyncio.CancelledError:
            pass
        finally:
            self.games.pop(ctx.channel.id, None)
