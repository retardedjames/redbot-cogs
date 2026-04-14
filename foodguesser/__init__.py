from .foodguesser import FoodGuesser


async def setup(bot):
    await bot.add_cog(FoodGuesser(bot))
