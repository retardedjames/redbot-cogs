from .trivia import Trivia


async def setup(bot):
    await bot.add_cog(Trivia(bot))
