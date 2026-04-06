from .ghostgame import GhostGame


async def setup(bot):
    await bot.add_cog(GhostGame(bot))
