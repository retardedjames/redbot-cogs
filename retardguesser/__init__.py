from .retardguesser import RetardGuesser


async def setup(bot):
    await bot.add_cog(RetardGuesser(bot))
