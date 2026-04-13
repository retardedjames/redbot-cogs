from .spellhell import SpellHell


async def setup(bot):
    await bot.add_cog(SpellHell(bot))
