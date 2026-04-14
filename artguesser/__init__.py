from .artguesser import ArtGuesser


async def setup(bot):
    await bot.add_cog(ArtGuesser(bot))
