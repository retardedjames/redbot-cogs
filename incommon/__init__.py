from .incommon import AreWeCompatible


async def setup(bot):
    await bot.add_cog(AreWeCompatible(bot))
