from .animalguesser import AnimalGuesser


async def setup(bot):
    await bot.add_cog(AnimalGuesser(bot))
