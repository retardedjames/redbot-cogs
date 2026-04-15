import asyncio
import time
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

import aiosqlite
import discord
from discord.ui import Button, View
from redbot.core import commands
from redbot.core.data_manager import cog_data_path

from .items import ITEMS

# ── Constants ─────────────────────────────────────────────────────────────────

VOTING_WINDOW  = 20     # seconds each question stays open
ROUND_GAP      = 5      # seconds between questions
DEFAULT_COUNT  = 20
RECENT_WINDOW  = 86400  # 24-hour item dedup (seconds)
MIN_SHARED     = 5      # minimum shared questions for a pair to appear in results
MAX_SELECT     = 25     # Discord select-menu hard limit

CHOICE_GROUPS = {
    "hate":      "negative",
    "dont_like": "negative",
    "like":      "positive",
    "love":      "positive",
}

CHOICE_LABELS = {
    "hate":      "Hate",
    "dont_like": "Dislike",
    "like":      "Like",
    "love":      "Love",
}

EXACT_LABELS = {
    "hate":      "hate",
    "dont_like": "dislike",
    "like":      "like",
    "love":      "love",
}


# ── Views ─────────────────────────────────────────────────────────────────────

class ItemView(View):
    """Four gray buttons — open to anyone in the channel."""

    def __init__(self, cog: "AreWeCompatible", channel_id: int, question_index: int):
        super().__init__(timeout=VOTING_WINDOW + 3)   # slight buffer over sleep
        self.cog = cog
        self.channel_id = channel_id
        self.question_index = question_index

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        game = self.cog.active_games.get(self.channel_id)
        if not game:
            await interaction.response.send_message("No game running here.", ephemeral=True)
            return

        # Reject clicks that arrive after the task already advanced
        if game["current_index"] != self.question_index:
            await interaction.response.send_message(
                "That question already closed — catch the next one!", ephemeral=True
            )
            return

        uid = interaction.user.id
        prev = game["current_responses"].get(uid)
        game["current_responses"][uid] = choice
        # Cache display name so we still have it if they leave before game ends
        game["user_names"][uid] = interaction.user.display_name

        await interaction.response.defer()

        # Update shared message with live response count (no choices revealed)
        count = len(game["current_responses"])
        index = game["current_index"]
        item  = game["items"][index]
        total = len(game["items"])
        noun  = "response" if count == 1 else "responses"
        try:
            await game["current_message"].edit(
                content=(
                    f"# {item['text']}\n"
                    f"Question **{index + 1}** of **{total}** · {count} {noun}"
                )
            )
        except Exception:
            pass

    @discord.ui.button(label="Like",    style=discord.ButtonStyle.secondary, row=0)
    async def like_it(self, interaction: discord.Interaction, button: Button):
        await self.handle_choice(interaction, "like")

    @discord.ui.button(label="Love",    style=discord.ButtonStyle.secondary, row=0)
    async def love_it(self, interaction: discord.Interaction, button: Button):
        await self.handle_choice(interaction, "love")

    @discord.ui.button(label="Dislike", style=discord.ButtonStyle.secondary, row=1)
    async def dont_like_it(self, interaction: discord.Interaction, button: Button):
        await self.handle_choice(interaction, "dont_like")

    @discord.ui.button(label="Hate",    style=discord.ButtonStyle.secondary, row=1)
    async def hate_it(self, interaction: discord.Interaction, button: Button):
        await self.handle_choice(interaction, "hate")

    async def on_timeout(self):
        pass   # the game task handles everything; view just goes stale naturally


class PairSelect(discord.ui.Select):
    """Dropdown that prints a full breakdown for the chosen pair."""

    def __init__(self, pairs: list):
        self.pairs = pairs
        options = []
        for i, p in enumerate(pairs[:MAX_SELECT]):
            label = f"{p['name1']} & {p['name2']}"[:100]
            desc  = f"{p['pct']}%  —  {p['matches']}/{p['shared']} matched"[:100]
            options.append(discord.SelectOption(label=label, value=str(i), description=desc))
        super().__init__(placeholder="Select a pair to see their full breakdown…", options=options)

    async def callback(self, interaction: discord.Interaction):
        pair = self.pairs[int(self.values[0])]

        negatives = [r for r in pair["items"] if r["match"] and r["group"] == "negative"]
        positives = [r for r in pair["items"] if r["match"] and r["group"] == "positive"]

        lines = [
            f"**{pair['name1']} & {pair['name2']} — {pair['pct']}% Compatible**",
            f"*{pair['matches']} of {pair['shared']} shared questions matched*",
            "",
        ]

        if negatives:
            lines.append("**👎 Both negative about:**")
            for r in negatives:
                if r["choice1"] == r["choice2"]:
                    lines.append(f"• **{r['item']}** ({EXACT_LABELS[r['choice1']]})")
                else:
                    lines.append(f"• {r['item']}")
            lines.append("")

        if positives:
            lines.append("**💚 Both positive about:**")
            for r in positives:
                if r["choice1"] == r["choice2"]:
                    lines.append(f"• **{r['item']}** ({EXACT_LABELS[r['choice1']]})")
                else:
                    lines.append(f"• {r['item']}")

        if not negatives and not positives:
            lines.append("*These two matched on nothing — somehow.*")

        content = "\n".join(lines)

        # Discord message cap — chunk if needed
        chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
        await interaction.response.send_message(chunks[0])
        for chunk in chunks[1:]:
            await interaction.channel.send(chunk)


class PairSelectView(View):
    def __init__(self, pairs: list):
        super().__init__(timeout=600)
        self.add_item(PairSelect(pairs))


# ── Cog ───────────────────────────────────────────────────────────────────────

class AreWeCompatible(commands.Cog):
    """Open compatibility game. Anyone in chat votes; see who has the most in common."""

    def __init__(self, bot):
        self.bot = bot
        self.active_games: dict = {}
        self.recent_items: dict = {}   # guild_id -> {item_text: timestamp}
        self._db_ready = False
        bot.loop.create_task(self._init_db())

    @property
    def db_path(self) -> Path:
        return cog_data_path(self) / "incommon.db"

    # ── DB ────────────────────────────────────────────────────────────────────

    async def _init_db(self):
        await self.bot.wait_until_ready()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    text     TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS games (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id   INTEGER NOT NULL,
                    played_at  TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS responses (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id   INTEGER NOT NULL,
                    user_id   INTEGER NOT NULL,
                    item_text TEXT    NOT NULL,
                    choice    TEXT    NOT NULL,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                );
            """)
            await db.commit()

            cur = await db.execute("SELECT COUNT(*) FROM items")
            if (await cur.fetchone())[0] == 0:
                await db.executemany(
                    "INSERT OR IGNORE INTO items (text, category) VALUES (?, ?)",
                    [(it["text"], it["category"]) for it in ITEMS],
                )
                await db.commit()

        self._db_ready = True

    # ── gamestop / clearmemory hooks ──────────────────────────────────────────

    async def force_stop_game(self, channel_id: int) -> Optional[str]:
        game = self.active_games.pop(channel_id, None)
        if not game:
            return None
        task = game.get("task")
        if task and not task.done():
            task.cancel()
        if game.get("current_message"):
            try:
                await game["current_message"].edit(view=None)
            except Exception:
                pass
        return "Are We Compatible"

    async def clear_recent_memory(self, guild: discord.Guild) -> Optional[str]:
        if guild.id in self.recent_items:
            self.recent_items[guild.id] = {}
            return "Are We Compatible"
        return None

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    @commands.guild_only()
    async def fd(self, ctx, count: int = DEFAULT_COUNT):
        """Start an Are We Compatible game — anyone in chat can vote!

        $fd          — 20 questions (default)
        $fd 40       — 40 questions
        """
        if not self._db_ready:
            await ctx.send("Still warming up — try again in a moment!")
            return
        if ctx.channel.id in self.active_games:
            await ctx.send("A game is already running here. Wait for it to finish.")
            return

        count = max(5, min(count, 100))
        await ctx.send(
            f"**Are We Compatible** — {count} questions, {VOTING_WINDOW}s each.\n"
            f"Anyone can vote. Choices are secret until the end. Starting now…"
        )
        await asyncio.sleep(3)
        await self.start_game(ctx.channel, count)

    @commands.command()
    @commands.guild_only()
    async def incommonstats(self, ctx, member: discord.Member):
        """See your all-time In Common history with another user."""
        if not self._db_ready:
            await ctx.send("Still warming up!")
            return

        uid1, uid2 = ctx.author.id, member.id

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT r1.item_text, r1.choice, r2.choice
                FROM responses r1
                JOIN responses r2
                  ON r1.game_id = r2.game_id AND r1.item_text = r2.item_text
                WHERE r1.user_id = ? AND r2.user_id = ?
                """,
                (uid1, uid2),
            )
            rows = await cur.fetchall()

        if not rows:
            await ctx.send(
                f"No shared game history between {ctx.author.mention} and {member.mention}."
            )
            return

        total   = len(rows)
        matches = sum(1 for _, c1, c2 in rows if CHOICE_GROUPS[c1] == CHOICE_GROUPS[c2])
        pct     = round((matches / total) * 100) if total else 0

        embed = discord.Embed(
            title=f"{pct}% Compatible — All Time",
            description=f"**{ctx.author.display_name}** & **{member.display_name}**",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Questions Shared", value=str(total),   inline=True)
        embed.add_field(name="Matched",          value=str(matches),  inline=True)
        embed.add_field(name="Score",            value=f"{pct}%",     inline=True)
        await ctx.send(embed=embed)

    # ── Game engine ───────────────────────────────────────────────────────────

    async def start_game(self, channel: discord.TextChannel, count: int):
        guild_id = channel.guild.id
        now = time.time()

        # Prune stale recent-items cache
        guild_recent = {
            t: ts for t, ts in self.recent_items.get(guild_id, {}).items()
            if now - ts < RECENT_WINDOW
        }
        self.recent_items[guild_id] = guild_recent
        exclude = list(guild_recent.keys())

        # Fetch random items, avoiding recently shown ones
        async with aiosqlite.connect(self.db_path) as db:
            if exclude:
                ph = ",".join("?" * len(exclude))
                cur = await db.execute(
                    f"SELECT text, category FROM items "
                    f"WHERE text NOT IN ({ph}) ORDER BY RANDOM() LIMIT ?",
                    (*exclude, count),
                )
            else:
                cur = await db.execute(
                    "SELECT text, category FROM items ORDER BY RANDOM() LIMIT ?",
                    (count,),
                )
            rows = await cur.fetchall()

        # Top up if not enough fresh items
        if len(rows) < count:
            already = {r[0] for r in rows}
            need = count - len(rows)
            async with aiosqlite.connect(self.db_path) as db:
                ph = ",".join("?" * len(already)) if already else "''"
                cur = await db.execute(
                    f"SELECT text, category FROM items "
                    f"WHERE text NOT IN ({ph}) ORDER BY RANDOM() LIMIT ?",
                    (*already, need),
                )
                rows = list(rows) + list(await cur.fetchall())

        items = [{"text": r[0], "category": r[1]} for r in rows]
        for item in items:
            self.recent_items[guild_id][item["text"]] = now

        game: dict = {
            "items":            items,
            "current_index":    0,
            "current_responses": {},        # uid -> choice  (current question)
            "all_responses":    {},         # uid -> {idx -> choice}
            "user_names":       {},         # uid -> display_name
            "channel":          channel,
            "current_message":  None,
            "task":             None,
        }
        self.active_games[channel.id] = game

        task = asyncio.ensure_future(self._game_loop(channel.id))
        game["task"] = task

    async def _game_loop(self, channel_id: int):
        """Drives question timing. Runs as a background task."""
        try:
            for i in range(len(self.active_games.get(channel_id, {}).get("items", []))):
                game = self.active_games.get(channel_id)
                if not game:
                    return

                game["current_index"] = i
                await self._show_item(channel_id)

                # Voting window
                await asyncio.sleep(VOTING_WINDOW)

                game = self.active_games.get(channel_id)
                if not game:
                    return

                # Disable buttons on the just-closed question
                if game["current_message"]:
                    try:
                        await game["current_message"].edit(view=None)
                    except Exception:
                        pass

                # Archive responses for this question
                for uid, choice in game["current_responses"].items():
                    game["all_responses"].setdefault(uid, {})[i] = choice
                game["current_responses"] = {}

                # Gap before next question (or results)
                await asyncio.sleep(ROUND_GAP)

            await self._finish_game(channel_id)

        except asyncio.CancelledError:
            pass   # $end was called — already cleaned up by force_stop_game

    async def _show_item(self, channel_id: int):
        game = self.active_games.get(channel_id)
        if not game:
            return

        index = game["current_index"]
        item  = game["items"][index]
        total = len(game["items"])

        view = ItemView(self, channel_id, index)
        msg  = await game["channel"].send(
            content=(
                f"# {item['text']}\n"
                f"Question **{index + 1}** of **{total}** · 0 responses"
            ),
            view=view,
        )
        game["current_message"] = msg

    async def _finish_game(self, channel_id: int):
        game = self.active_games.pop(channel_id, None)
        if not game:
            return

        channel    = game["channel"]
        all_resp   = game["all_responses"]    # uid -> {idx -> choice}
        user_names = game["user_names"]       # uid -> display_name
        items      = game["items"]

        # ── Compute all pairs ─────────────────────────────────────────────────
        uid_list = list(all_resp.keys())
        if len(uid_list) < 2:
            await channel.send("Not enough people voted to compute any pair results. Next time!")
            return

        pairs = []
        for uid1, uid2 in combinations(uid_list, 2):
            resp1 = all_resp[uid1]
            resp2 = all_resp[uid2]
            shared_indices = sorted(set(resp1) & set(resp2))

            if len(shared_indices) < MIN_SHARED:
                continue

            match_count = 0
            item_data   = []
            for idx in shared_indices:
                c1 = resp1[idx]
                c2 = resp2[idx]
                g1 = CHOICE_GROUPS[c1]
                g2 = CHOICE_GROUPS[c2]
                matched = g1 == g2
                if matched:
                    match_count += 1
                item_data.append({
                    "item":    items[idx]["text"],
                    "choice1": c1,
                    "choice2": c2,
                    "match":   matched,
                    "group":   g1 if matched else None,
                })

            pct = round((match_count / len(shared_indices)) * 100)

            name1 = user_names.get(uid1) or f"<@{uid1}>"
            name2 = user_names.get(uid2) or f"<@{uid2}>"

            pairs.append({
                "uid1":    uid1,
                "uid2":    uid2,
                "name1":   name1,
                "name2":   name2,
                "pct":     pct,
                "matches": match_count,
                "shared":  len(shared_indices),
                "items":   item_data,
            })

        if not pairs:
            await channel.send(
                "No pair shared enough questions to score. "
                f"*(Need at least {MIN_SHARED} in common.)*"
            )
            return

        # Sort by percentage descending
        pairs.sort(key=lambda p: p["pct"], reverse=True)

        # ── Save to DB ────────────────────────────────────────────────────────
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO games (guild_id, played_at) VALUES (?, ?)",
                (channel.guild.id, datetime.now(timezone.utc).isoformat()),
            )
            game_id = cur.lastrowid

            for uid, resp in all_resp.items():
                for idx, choice in resp.items():
                    await db.execute(
                        "INSERT INTO responses (game_id, user_id, item_text, choice) "
                        "VALUES (?, ?, ?, ?)",
                        (game_id, uid, items[idx]["text"], choice),
                    )
            await db.commit()

        # ── Results message ───────────────────────────────────────────────────
        medal = ["🥇", "🥈", "🥉"]
        lines = ["## Are We Compatible — Results\n"]
        for i, p in enumerate(pairs):
            prefix = medal[i] if i < 3 else "▪"
            lines.append(
                f"{prefix} **{p['name1']} & {p['name2']}** — "
                f"**{p['pct']}%** *(matched {p['matches']}/{p['shared']})*"
            )

        if len(pairs) > MAX_SELECT:
            lines.append(f"\n*Showing top {MAX_SELECT} pairs in the dropdown below.*")

        content = "\n".join(lines)

        # Use select-menu view for pair breakdowns
        view = PairSelectView(pairs)
        await channel.send(content=content, view=view)
