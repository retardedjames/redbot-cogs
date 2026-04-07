from .famouswords import FamousWords


async def setup(bot):
    await bot.add_cog(FamousWords(bot))
