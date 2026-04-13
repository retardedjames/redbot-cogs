from .selftime import SelfTime


async def setup(bot):
    await bot.add_cog(SelfTime(bot))
