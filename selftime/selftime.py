import asyncio
from datetime import timedelta

import discord
from redbot.core import commands


class SelfTime(commands.Cog):
    """Time yourself out for a specified number of minutes."""

    def __init__(self, bot):
        self.bot = bot
        # Tracks pending role-restore tasks keyed by member id.
        self._pending_restores: dict[int, asyncio.Task] = {}

    def cog_unload(self):
        for task in self._pending_restores.values():
            task.cancel()

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def selftime(self, ctx, minutes: int):
        """Time yourself out for the specified number of minutes.

        Usage: [p]selftime <minutes>
        Maximum: 40320 minutes (28 days)

        If you have the Administrator permission the bot will temporarily
        remove your admin role(s), apply the timeout, then restore your
        roles automatically once the timeout expires.

        Warning: if the bot restarts while you are timed out your admin
        roles will not be restored automatically — ask someone to add them
        back manually.
        """
        if minutes <= 0:
            await ctx.send("Please specify a positive number of minutes.")
            return

        if minutes > 40320:
            await ctx.send("Maximum timeout is 40320 minutes (28 days).")
            return

        member = ctx.author

        # Server owners cannot be timed out — Discord enforces this at the API level
        # regardless of roles, so there is no workaround.
        if member.id == ctx.guild.owner_id:
            await ctx.send(
                "Discord does not allow timing out the server owner at the API level — "
                "no workaround exists. Transfer server ownership to someone else first."
            )
            return

        until = discord.utils.utcnow() + timedelta(minutes=minutes)

        # Collect any roles that grant Administrator so we can temporarily remove them.
        admin_roles = [
            r for r in member.roles
            if r.permissions.administrator and r != ctx.guild.default_role
        ]

        # --- Step 1: strip admin roles if needed ---
        if admin_roles:
            try:
                await member.remove_roles(
                    *admin_roles,
                    reason="Temporary removal for self-timeout workaround",
                )
            except discord.Forbidden:
                await ctx.send(
                    "I was unable to remove your admin role(s). "
                    "Make sure my highest role is above yours in the role list."
                )
                return
            except discord.HTTPException as e:
                await ctx.send(f"Something went wrong removing your roles: {e}")
                return

        # --- Step 2: apply the timeout ---
        try:
            await member.timeout(until, reason=f"Self-imposed timeout for {minutes} minute(s).")
        except discord.Forbidden:
            # Restore roles before bailing out.
            if admin_roles:
                try:
                    await member.add_roles(*admin_roles, reason="Restoring roles after failed self-timeout")
                except discord.HTTPException:
                    pass
            await ctx.send(
                "I was unable to time you out. Make sure I have the **Moderate Members** permission."
            )
            return
        except discord.HTTPException as e:
            if admin_roles:
                try:
                    await member.add_roles(*admin_roles, reason="Restoring roles after failed self-timeout")
                except discord.HTTPException:
                    pass
            await ctx.send(f"Something went wrong applying the timeout: {e}")
            return

        # --- Step 3: schedule role restoration after the timeout expires ---
        if admin_roles:
            async def restore_roles(m: discord.Member, roles: list[discord.Role], delay: float):
                try:
                    await asyncio.sleep(delay)
                    await m.add_roles(*roles, reason="Restoring roles after self-timeout expired")
                except (asyncio.CancelledError, discord.HTTPException):
                    pass
                finally:
                    self._pending_restores.pop(m.id, None)

            task = asyncio.create_task(
                restore_roles(member, admin_roles, minutes * 60)
            )
            self._pending_restores[member.id] = task

        # --- Channel embed ---
        hours, mins = divmod(minutes, 60)
        duration_str = (
            f"{hours}h {mins}m" if hours and mins
            else f"{hours}h" if hours
            else f"{mins}m"
        )
        embed = discord.Embed(
            title="Self-Timeout",
            description=f"{member.mention} has timed themselves out for **{duration_str}**.",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Expires", value=f"<t:{int(until.timestamp())}:R>", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Requested by {member.display_name}")
        await ctx.send(embed=embed)

        # --- DM confirmation (includes role/restart warnings if applicable) ---
        dm_parts = [
            f"You have timed yourself out for **{duration_str}**.",
            f"Your timeout will expire <t:{int(until.timestamp())}:R>.",
        ]
        if admin_roles:
            dm_parts.append(
                f"Your admin role(s) ({', '.join(r.name for r in admin_roles)}) have been "
                f"temporarily removed and will be restored automatically when the timeout expires."
            )
            dm_parts.append(
                "**Warning:** if the bot restarts before your timeout expires your admin "
                "roles will not be restored automatically — ask someone to re-add them."
            )
        try:
            await member.send("\n\n".join(dm_parts))
        except discord.Forbidden:
            pass
