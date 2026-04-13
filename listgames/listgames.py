import discord
from redbot.core import commands
from pathlib import Path


class ListGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def listgames(self, ctx):
        """List all games available on this server."""
        games_file = Path(__file__).parent / "games.md"
        content = games_file.read_text(encoding="utf-8")

        entries = content.strip().split("\n\n")
        chunk = "# Games You Can Play Here"
        for entry in entries:
            candidate = chunk + "\n\n" + entry
            if len(candidate) > 1990:
                await ctx.send(chunk)
                chunk = entry
            else:
                chunk = candidate
        if chunk:
            await ctx.send(chunk)
