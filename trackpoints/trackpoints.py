import discord
from redbot.core import commands, Config


def _fmt_pts(pts: float) -> str:
    """Format a point total cleanly — whole numbers show no decimal, fractions show up to 2 places."""
    return f"{pts:.2f}".rstrip("0").rstrip(".")


class TrackPoints(commands.Cog):
    """Persistent points leaderboard — win games to earn points!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0x547261636B507473, force_registration=True)
        self.config.register_member(points=0, games_played=0)

    # ── Public API (called by game cogs) ──────────────────────────────────────

    async def record_game_result(
        self,
        winner: "discord.Member | None",
        participants: "set",
    ) -> None:
        """
        Award points and participation credit for a finished game.

        winner:       the discord.Member who won, or None if nobody guessed.
        participants: set of discord.Member objects who typed a guess during
                      the game (the winner should be included if there is one).
        """
        for member in participants:
            try:
                gp = await self.config.member(member).games_played()
                await self.config.member(member).games_played.set(gp + 1)
            except Exception:
                pass

        if winner is not None:
            try:
                pts = await self.config.member(winner).points()
                await self.config.member(winner).points.set(pts + 1)
            except Exception:
                pass

    async def get_points(self, member: "discord.Member") -> float:
        """Return the current point total for a guild member."""
        return await self.config.member(member).points()

    async def add_points(self, member: "discord.Member", amount: float) -> None:
        """Add an arbitrary point amount (supports fractions) to a member's total."""
        try:
            pts = await self.config.member(member).points()
            await self.config.member(member).points.set(pts + amount)
        except Exception:
            pass

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command(name="mypoints")
    @commands.guild_only()
    async def mypoints(self, ctx: commands.Context):
        """Show your total points and how many games you've played."""
        pts = await self.config.member(ctx.author).points()
        gp = await self.config.member(ctx.author).games_played()
        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Stats",
            description=(
                f"**Points:** {_fmt_pts(pts)}\n"
                f"**Games Played:** {gp:,}"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """Show the top 20 players by total points."""
        all_data = await self.config.all_members(ctx.guild)
        if not all_data:
            await ctx.send("No points recorded yet — play some games!")
            return

        ranked = sorted(
            all_data.items(),
            key=lambda x: (x[1].get("points", 0), x[1].get("games_played", 0)),
            reverse=True,
        )[:20]

        lines = []
        for i, (user_id, data) in enumerate(ranked, 1):
            member = ctx.guild.get_member(int(user_id))
            name = member.display_name if member else f"User #{user_id}"
            pts = data.get("points", 0)
            gp = data.get("games_played", 0)
            lines.append(f"**{i}.** {name} — **{_fmt_pts(pts)}** pts ({gp:,} games)")

        embed = discord.Embed(
            title="Points Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Earn points by winning games!")
        await ctx.send(embed=embed)

    @commands.command(name="nukepoints")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def nukepoints(self, ctx: commands.Context):
        """Clear all points and participation records for this server (admin only)."""
        all_data = await self.config.all_members(ctx.guild)
        if not all_data:
            await ctx.send("There are no records to clear.")
            return
        for user_id in list(all_data.keys()):
            await self.config.member_from_ids(ctx.guild.id, user_id).clear()
        await ctx.send("All points and game records have been wiped. Starting fresh!")
