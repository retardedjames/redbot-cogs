from datetime import timedelta

import discord
from redbot.core import commands


class SelfTime(commands.Cog):
    """Time yourself out for a specified number of minutes."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def selftime(self, ctx, minutes: int):
        """Time yourself out for the specified number of minutes.

        Usage: [p]selftime <minutes>
        Maximum: 40320 minutes (28 days)

        Note: Discord does not allow timing out server owners or members
        with the Administrator permission. You must first transfer ownership
        and/or remove your Administrator permission before this will work.
        """
        if minutes <= 0:
            await ctx.send("Please specify a positive number of minutes.")
            return

        if minutes > 40320:
            await ctx.send("Maximum timeout is 40320 minutes (28 days).")
            return

        member = ctx.author

        # Server owners cannot be timed out — Discord enforces this at the API level.
        if member.id == ctx.guild.owner_id:
            await ctx.send(
                "Discord does not allow timing out the server owner. "
                "Transfer server ownership to someone else first, then use this command."
            )
            return

        # Members with the Administrator permission cannot be timed out either.
        if member.guild_permissions.administrator:
            await ctx.send(
                "Discord does not allow timing out members with the Administrator permission. "
                "Remove your Administrator permission (or switch to a role without it) and try again."
            )
            return

        until = discord.utils.utcnow() + timedelta(minutes=minutes)

        try:
            await member.timeout(until, reason=f"Self-imposed timeout for {minutes} minute(s).")
            # Try to DM the confirmation since they won't be able to chat.
            try:
                await member.send(
                    f"You have timed yourself out for **{minutes} minute(s)**. "
                    f"Your timeout will expire <t:{int(until.timestamp())}:R>."
                )
            except discord.Forbidden:
                # DMs closed — send in channel instead (they can still read it).
                await ctx.send(
                    f"{member.mention} has been timed out for **{minutes} minute(s)**. "
                    f"Timeout expires <t:{int(until.timestamp())}:R>."
                )
        except discord.Forbidden:
            await ctx.send(
                "I was unable to time you out. Make sure:\n"
                "• I have the **Moderate Members** permission\n"
                "• My highest role is above your highest role in the role list"
            )
        except discord.HTTPException as e:
            await ctx.send(f"Something went wrong: {e}")
