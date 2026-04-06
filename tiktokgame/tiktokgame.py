"""TikTok Dance Tournament cog for Redbot.

50 well-known female TikTok dance creators. Each round two are shown
side-by-side; players vote to keep one. The creator with fewer votes is
eliminated. Last one standing has her age revealed.

Data notes:
  - dob: used only for the final age reveal.
  - image_url / videos: optional. Add real URLs here to show profile
    pictures and Watch links in the voting embeds.
"""
import asyncio
import random
from datetime import date

import discord
from redbot.core import commands
from redbot.core.bot import Red

try:
    import importlib.util as _ilu, pathlib as _pl
    _spec = _ilu.spec_from_file_location("_dev", _pl.Path(__file__).parent.parent / "_dev.py")
    _mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
    DEV_MODE, DEV_LABEL = _mod.DEV_MODE, _mod.DEV_LABEL
except Exception:
    DEV_MODE, DEV_LABEL = False, ""


# ---------------------------------------------------------------------------
# Creator data — update image_url and videos as desired
# ---------------------------------------------------------------------------
CREATORS = [
    {"name": "Charli D'Amelio",    "username": "charlidamelio",    "dob": "2004-05-01", "image_url": None, "videos": []},
    {"name": "Addison Rae",        "username": "addisonre",         "dob": "2000-10-06", "image_url": None, "videos": []},
    {"name": "Dixie D'Amelio",     "username": "dixiedamelio",      "dob": "2001-08-12", "image_url": None, "videos": []},
    {"name": "Avani Gregg",        "username": "avani",             "dob": "2002-11-23", "image_url": None, "videos": []},
    {"name": "Loren Gray",         "username": "lorengray",         "dob": "2002-04-19", "image_url": None, "videos": []},
    {"name": "Nessa Barrett",      "username": "nessabarrett",      "dob": "2002-08-06", "image_url": None, "videos": []},
    {"name": "Bella Poarch",       "username": "bellapoarch",       "dob": "1997-02-08", "image_url": None, "videos": []},
    {"name": "Ellie Zeiler",       "username": "elliezeiler",       "dob": "2006-03-31", "image_url": None, "videos": []},
    {"name": "Olivia Ponton",      "username": "oliviaponton",      "dob": "2002-05-30", "image_url": None, "videos": []},
    {"name": "Sienna Mae Gomez",   "username": "siennamaegomez",    "dob": "2004-12-15", "image_url": None, "videos": []},
    {"name": "Bailey Spinn",       "username": "baileyspinn",       "dob": "2001-03-26", "image_url": None, "videos": []},
    {"name": "Paige Niemann",      "username": "paigeniemann",      "dob": "2005-03-26", "image_url": None, "videos": []},
    {"name": "Madi Monroe",        "username": "madimonroe",        "dob": "2002-10-12", "image_url": None, "videos": []},
    {"name": "Amelie Zilber",      "username": "ameliezilber",      "dob": "2002-06-15", "image_url": None, "videos": []},
    {"name": "Danielle Cohn",      "username": "daniellecohn",      "dob": "2004-03-07", "image_url": None, "videos": []},
    {"name": "Hannah Stocking",    "username": "hannahstocking",    "dob": "1992-11-04", "image_url": None, "videos": []},
    {"name": "Savannah LaBrant",   "username": "savannahlabrant",   "dob": "1993-03-02", "image_url": None, "videos": []},
    {"name": "Lexi Rivera",        "username": "lexibrook",         "dob": "2000-06-07", "image_url": None, "videos": []},
    {"name": "Sophie Michelle",    "username": "sophiemichele",     "dob": "1999-09-07", "image_url": None, "videos": []},
    {"name": "Nailea Devora",      "username": "naileadevora",      "dob": "2001-08-08", "image_url": None, "videos": []},
    {"name": "Kalani Hilliker",    "username": "kalanihilliker",    "dob": "2000-09-23", "image_url": None, "videos": []},
    {"name": "Jalaiah Harmon",     "username": "jalaiah",           "dob": "2005-01-28", "image_url": None, "videos": []},
    {"name": "Chloe Lukasiak",     "username": "chloelukasiak",     "dob": "2001-05-25", "image_url": None, "videos": []},
    {"name": "JoJo Siwa",          "username": "itsjojosiwa",       "dob": "2003-05-19", "image_url": None, "videos": []},
    {"name": "Sommer Ray",         "username": "sommerray",         "dob": "1996-09-15", "image_url": None, "videos": []},
    {"name": "Annie LeBlanc",      "username": "annieleblanc",      "dob": "2004-12-05", "image_url": None, "videos": []},
    {"name": "Piper Rockelle",     "username": "piperrockelle",     "dob": "2007-08-21", "image_url": None, "videos": []},
    {"name": "Tana Mongeau",       "username": "tanamongeau",       "dob": "1998-06-24", "image_url": None, "videos": []},
    {"name": "Brooke Monk",        "username": "brookemonk",        "dob": "2003-01-31", "image_url": None, "videos": []},
    {"name": "Maddie Ziegler",     "username": "maddieziegler",     "dob": "2002-09-30", "image_url": None, "videos": []},
    {"name": "Brittany Broski",    "username": "brittany_broski",   "dob": "1997-04-10", "image_url": None, "videos": []},
    {"name": "Zoe LaVerne",        "username": "zoelaverne",        "dob": "2001-06-03", "image_url": None, "videos": []},
    {"name": "Kylie Cantrall",     "username": "kyliecantrall",     "dob": "2003-11-03", "image_url": None, "videos": []},
    {"name": "Lauren Godwin",      "username": "laurengodwin",      "dob": "1999-07-26", "image_url": None, "videos": []},
    {"name": "Megan Eugenio",      "username": "overtime.megan",    "dob": "2000-03-17", "image_url": None, "videos": []},
    {"name": "Kira Kosarin",       "username": "kirakosarin",       "dob": "1997-10-07", "image_url": None, "videos": []},
    {"name": "Riley Hubatka",      "username": "rileyhubatka",      "dob": "2000-10-29", "image_url": None, "videos": []},
    {"name": "GiaNina Paolantonio","username": "gianina_p",         "dob": "2007-04-21", "image_url": None, "videos": []},
    {"name": "Gabby Morrison",     "username": "gabbymorr",         "dob": "2002-06-20", "image_url": None, "videos": []},
    {"name": "Rachel Brockman",    "username": "rachelbrockman",    "dob": "2000-12-07", "image_url": None, "videos": []},
    {"name": "Kenzie Elizabeth",   "username": "kenzieelizabethh",  "dob": "2001-08-14", "image_url": None, "videos": []},
    {"name": "Alisha Marie",       "username": "alishamarie",       "dob": "1993-11-05", "image_url": None, "videos": []},
    {"name": "Eva Gutowski",       "username": "mylifeaseva",       "dob": "1994-09-29", "image_url": None, "videos": []},
    {"name": "Jayda Cheaves",      "username": "jaydacheaves",      "dob": "1997-09-25", "image_url": None, "videos": []},
    {"name": "Mia Challiner",      "username": "miachalliner",      "dob": "2004-02-14", "image_url": None, "videos": []},
    {"name": "Sofia Wylie",        "username": "sofiawylie",        "dob": "2004-08-07", "image_url": None, "videos": []},
    {"name": "Mikayla Nogueira",   "username": "mikaylanogueira",   "dob": "1998-07-19", "image_url": None, "videos": []},
    {"name": "Alix Earle",         "username": "alixearle",         "dob": "2000-12-16", "image_url": None, "videos": []},
    {"name": "Makayla Brewster",   "username": "makaylabrewster",   "dob": "2001-05-15", "image_url": None, "videos": []},
    {"name": "Gabby Surfas",       "username": "gabbysurf",         "dob": "2002-03-10", "image_url": None, "videos": []},
    {"name": "Lauren Kettering",   "username": "laurenkettering",   "dob": "2001-11-08", "image_url": None, "videos": []},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _calculate_age(dob_str: str) -> int:
    dob = date.fromisoformat(dob_str)
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _creator_embed(creator: dict, color: discord.Color, label: str) -> discord.Embed:
    username = creator["username"]
    embed = discord.Embed(
        title=creator["name"],
        description=f"**[{username}](https://www.tiktok.com/@{username})**",
        color=color,
    )
    embed.set_author(name=label)
    if creator.get("image_url"):
        embed.set_image(url=creator["image_url"])
    if creator.get("videos"):
        video = random.choice(creator["videos"])
        embed.add_field(name="🎬 Video", value=f"[Watch on TikTok]({video})", inline=False)
    return embed


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------

class GameInstance:
    def __init__(self):
        self.running = True
        self.current_view: "VoteView | None" = None

    def stop(self):
        self.running = False
        if self.current_view is not None:
            self.current_view._all_voted.set()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class LobbyView(discord.ui.View):
    def __init__(self, host: discord.Member):
        super().__init__(timeout=120)
        self.host = host
        self.players: set[int] = set()
        self._started = asyncio.Event()

    def _make_embed(self) -> discord.Embed:
        count = len(self.players)
        embed = discord.Embed(
            title=f"🎵 TikTok Dance Tournament{DEV_LABEL}",
            description=(
                "50 TikTok dancers enter — only one survives!\n\n"
                "Each round you vote for who **stays**. "
                "The dancer with fewer votes is eliminated.\n\n"
                "Click **Join Game** to participate."
            ),
            color=discord.Color.from_rgb(238, 29, 82),
        )
        embed.add_field(
            name=f"Players ({count})",
            value=f"{count} joined" if count else "No players yet — be first!",
        )
        embed.set_footer(text="Host clicks Start Game to begin • Lobby closes in 2 minutes")
        return embed

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success, emoji="🎮")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("You already joined!", ephemeral=True)
            return
        self.players.add(interaction.user.id)
        await interaction.response.edit_message(embed=self._make_embed())

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("Only the host can start!", ephemeral=True)
            return
        if not self.players:
            await interaction.response.send_message(
                "At least one player must join first!", ephemeral=True
            )
            return
        self.stop()
        self._started.set()
        await interaction.response.defer()

    async def on_timeout(self):
        self._started.set()


class VoteView(discord.ui.View):
    def __init__(self, creator1: dict, creator2: dict, players: set[int]):
        super().__init__(timeout=60)
        self.creators = [creator1, creator2]
        self.players = players
        self.votes: dict[int, int] = {}  # user_id -> 0 or 1
        self._all_voted = asyncio.Event()

        self.add_item(self._make_button(creator1, 0, discord.ButtonStyle.danger))
        self.add_item(self._make_button(creator2, 1, discord.ButtonStyle.primary))

    def _make_button(
        self, creator: dict, index: int, style: discord.ButtonStyle
    ) -> discord.ui.Button:
        raw = f"Choose {creator['name']}"
        label = raw[:80] if len(raw) <= 80 else raw[:77] + "…"
        btn = discord.ui.Button(label=label, style=style)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in self.players:
                await interaction.response.send_message(
                    "You're not in this game!", ephemeral=True
                )
                return
            if interaction.user.id in self.votes:
                await interaction.response.send_message(
                    "You already voted this round!", ephemeral=True
                )
                return
            self.votes[interaction.user.id] = index
            await interaction.response.send_message(
                f"Voted for **{creator['name']}**!", ephemeral=True
            )
            if len(self.votes) >= len(self.players):
                self._all_voted.set()

        btn.callback = callback
        return btn

    async def on_timeout(self):
        self._all_voted.set()
        for item in self.children:
            item.disabled = True


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TikTokGameCog(commands.Cog):
    """TikTok Dance Tournament — vote out dancers until one champion remains."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.games: dict[int, GameInstance] = {}

    @commands.command(name="tiktokgame")
    @commands.guild_only()
    async def tiktok_game(self, ctx: commands.Context):
        """Start a TikTok Dance Tournament in this channel."""
        if ctx.channel.id in self.games:
            await ctx.send(
                "A tournament is already running here! "
                "Use `$tiktokstop` to end it early."
            )
            return

        lobby = LobbyView(ctx.author)
        msg = await ctx.send(embed=lobby._make_embed(), view=lobby)

        await lobby._started.wait()
        await msg.edit(view=None)

        if not lobby.players:
            await ctx.send("Nobody joined. Tournament cancelled.")
            return

        game = GameInstance()
        self.games[ctx.channel.id] = game
        try:
            await self._run_game(ctx, game, set(lobby.players))
        finally:
            self.games.pop(ctx.channel.id, None)

    @commands.command(name="tiktokstop")
    @commands.guild_only()
    async def tiktok_stop(self, ctx: commands.Context):
        """Stop the TikTok Dance Tournament running in this channel."""
        if ctx.channel.id not in self.games:
            await ctx.send("No tournament is running in this channel.")
            return
        self.games[ctx.channel.id].stop()
        await ctx.send("🛑 Tournament stopped.")

    # ------------------------------------------------------------------
    # Internal game loop
    # ------------------------------------------------------------------

    async def _run_game(
        self, ctx: commands.Context, game: GameInstance, players: set[int]
    ):
        pool = list(CREATORS)
        random.shuffle(pool)
        round_num = 0

        await ctx.send(
            f"🎮 **TikTok Dance Tournament begins!**\n"
            f"{len(pool)} dancers · {len(players)} voter{'s' if len(players) != 1 else ''}\n"
            "Vote for who **stays** — fewer votes means elimination!"
        )

        while len(pool) > 1 and game.running:
            round_num += 1
            c1, c2 = random.sample(pool, 2)

            embed1 = _creator_embed(c1, discord.Color.from_rgb(220, 50, 50), "Contestant 1")
            embed2 = _creator_embed(c2, discord.Color.from_rgb(50, 100, 220), "Contestant 2")

            view = VoteView(c1, c2, players)
            game.current_view = view

            await ctx.send(
                f"**Round {round_num}** — {len(pool)} dancers remain | 60 seconds to vote!",
                embeds=[embed1, embed2],
                view=view,
            )

            try:
                await asyncio.wait_for(view._all_voted.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

            view.stop()
            game.current_view = None

            if not game.running:
                break

            # Tally votes
            tally = [0, 0]
            for choice in view.votes.values():
                tally[choice] += 1

            if tally[0] < tally[1]:
                loser_i, survivor_i = 0, 1
            elif tally[1] < tally[0]:
                loser_i, survivor_i = 1, 0
            else:
                loser_i = random.randint(0, 1)
                survivor_i = 1 - loser_i

            loser = [c1, c2][loser_i]
            survivor = [c1, c2][survivor_i]
            was_tie = tally[0] == tally[1]

            pool.remove(loser)

            result_embed = discord.Embed(
                title=f"❌ {loser['name']} eliminated!",
                description=(
                    f"**{survivor['name']}** — {tally[survivor_i]} vote{'s' if tally[survivor_i] != 1 else ''}\n"
                    f"**{loser['name']}** — {tally[loser_i]} vote{'s' if tally[loser_i] != 1 else ''}\n\n"
                    f"{len(pool)} dancer{'s' if len(pool) != 1 else ''} remaining"
                ),
                color=discord.Color.dark_red(),
            )
            if was_tie:
                result_embed.set_footer(text="It was a tie — eliminated by random draw!")

            await ctx.send(embed=result_embed)

            if len(pool) > 1 and game.running:
                await asyncio.sleep(4)

        if not game.running:
            await ctx.send("🛑 Tournament ended early.")
            return

        # Reveal the champion
        champion = pool[0]
        age = _calculate_age(champion["dob"])

        win_embed = discord.Embed(
            title=f"🏆 {champion['name']} wins the TikTok Dance Tournament!",
            description=(
                f"**[{champion['username']}](https://www.tiktok.com/@{champion['username']})**\n\n"
                f"🎂 **Age: {age} years old**\n"
                f"📅 Born: {champion['dob']}"
            ),
            color=discord.Color.gold(),
        )
        if champion.get("image_url"):
            win_embed.set_image(url=champion["image_url"])
        win_embed.set_footer(text="TikTok Dance Tournament • Thanks for playing!")

        await ctx.send("🎊 **We have a champion!**", embed=win_embed)
