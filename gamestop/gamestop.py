import discord
from redbot.core import commands


class GameStop(commands.Cog):
    """Universal command to stop any active game in the current channel."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="end")
    @commands.guild_only()
    async def end(self, ctx: commands.Context):
        """Stop any active game running in this channel."""
        stopped = []
        for cog in self.bot.cogs.values():
            if hasattr(cog, "force_stop_game"):
                name = await cog.force_stop_game(ctx.channel.id)
                if name:
                    stopped.append(name)

        if not stopped:
            await ctx.send("No games are running in this channel.")
        else:
            games_str = ", ".join(stopped)
            await ctx.send(embed=discord.Embed(
                description=f"🛑 Stopped: {games_str}",
                color=discord.Color.red(),
            ))

    @commands.command(name="clearmemory")
    @commands.guild_only()
    async def clearmemory(self, ctx: commands.Context):
        """Clear the recent-item memory for all games so nothing is excluded from the next round."""
        cleared = []
        for cog in self.bot.cogs.values():
            if hasattr(cog, "clear_recent_memory"):
                name = await cog.clear_recent_memory(guild=ctx.guild)
                if name:
                    cleared.append(name)

        if not cleared:
            await ctx.send("No games have recent memory to clear.")
        else:
            games_str = ", ".join(cleared)
            await ctx.send(embed=discord.Embed(
                description=f"🧹 Memory cleared: {games_str}",
                color=discord.Color.green(),
            ))
