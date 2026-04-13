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
        chunk = ""
        for entry in entries:
            candidate = chunk + "\n\n" + entry
            if len(candidate.strip()) > 1990:
                await ctx.send(chunk.strip())
                chunk = entry
            else:
                chunk = candidate
        if chunk.strip():
            await ctx.send(chunk.strip())
