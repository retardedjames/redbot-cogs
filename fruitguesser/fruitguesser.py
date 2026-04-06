import asyncio
import logging
import random

import aiohttp
import discord
from redbot.core import commands

log = logging.getLogger("red.cogs.fruitguesser")

try:
    import importlib.util as _ilu, pathlib as _pl
    _spec = _ilu.spec_from_file_location("_dev", _pl.Path(__file__).parent.parent / "_dev.py")
    _mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod)
    DEV_MODE, DEV_LABEL = _mod.DEV_MODE, _mod.DEV_LABEL
except Exception:
    DEV_MODE, DEV_LABEL = False, ""


# ── Fruit list (~120 fruits) ──────────────────────────────────────────────────

FRUITS = [
    # Apples
    "Apple", "Fuji Apple", "Honeycrisp Apple", "Granny Smith Apple",
    "Gala Apple", "Braeburn Apple", "Pink Lady Apple", "McIntosh Apple",
    # Pears
    "Pear", "Bartlett Pear", "Asian Pear", "Bosc Pear",
    # Citrus
    "Orange", "Blood Orange", "Clementine", "Tangerine", "Mandarin",
    "Grapefruit", "Pomelo", "Lemon", "Lime", "Meyer Lemon", "Kumquat",
    "Yuzu", "Bergamot", "Cara Cara Orange", "Satsuma", "Ugli Fruit",
    # Berries
    "Strawberry", "Raspberry", "Blueberry", "Blackberry", "Cranberry",
    "Gooseberry", "Boysenberry", "Elderberry", "Mulberry", "Huckleberry",
    "Lingonberry", "Cloudberry", "Acai",
    # Stone Fruits
    "Peach", "Nectarine", "Plum", "Cherry", "Apricot", "Damson Plum",
    # Tropical (common)
    "Banana", "Plantain", "Pineapple", "Mango", "Papaya", "Coconut",
    "Guava", "Passion Fruit", "Dragon Fruit", "Lychee", "Longan",
    "Rambutan", "Jackfruit", "Durian", "Mangosteen", "Starfruit",
    # Tropical (less common but recognizable)
    "Soursop", "Cherimoya", "Feijoa", "Tamarind", "Breadfruit",
    "Ackee", "Sapodilla", "Sugar Apple", "Mamey Sapote", "Jabuticaba",
    # Melons
    "Watermelon", "Cantaloupe", "Honeydew Melon", "Canary Melon",
    "Galia Melon", "Crenshaw Melon",
    # Grapes
    "Grape", "Concord Grape", "Moondrop Grape", "Cotton Candy Grape",
    "Muscat Grape",
    # Other common
    "Kiwi", "Golden Kiwi", "Fig", "Date", "Pomegranate", "Avocado",
    "Persimmon", "Quince", "Loquat", "Currant", "Olive", "Noni",
    "Finger Lime",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scramble(name: str) -> str:
    """Scramble each word in the fruit name independently."""
    words = name.split()
    scrambled = []
    for word in words:
        letters = list(word)
        random.shuffle(letters)
        scrambled.append("".join(letters))
    return " ".join(scrambled)


# ── Game state ────────────────────────────────────────────────────────────────

class FruitGame:
    MAX_HINTS = 3

    def __init__(self, fruit: str, images: list, task: asyncio.Task):
        self.fruit = fruit
        self.images = images          # list of image URLs fetched up front
        self.used: set = set()        # indices already shown this round
        self.hints_used = 0
        self.task = task

    def pop_image(self) -> str | None:
        if not self.images:
            return None
        unused = [i for i in range(len(self.images)) if i not in self.used]
        if not unused:                # exhausted all images — reset pool
            self.used.clear()
            unused = list(range(len(self.images)))
        idx = random.choice(unused)
        self.used.add(idx)
        return self.images[idx]


# ── Hint button ───────────────────────────────────────────────────────────────

class FruitHintView(discord.ui.View):
    """Single-use green Hint button. Disables itself when clicked, then sends
    the next hint as a followup (with a fresh button if hints remain)."""

    def __init__(self, cog: "FruitGuesser", channel_id: int):
        super().__init__(timeout=70)
        self.cog = cog
        self.channel_id = channel_id
        self._used = False

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.success)
    async def hint_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._used:
            await interaction.response.send_message(
                "Use the most recent Hint button!", ephemeral=True
            )
            return

        game = self.cog.games.get(self.channel_id)
        if not game:
            await interaction.response.send_message(
                "This game has already ended.", ephemeral=True
            )
            return
        if game.hints_used >= FruitGame.MAX_HINTS:
            await interaction.response.send_message(
                f"All **{FruitGame.MAX_HINTS}** hints have been used — keep guessing!",
                ephemeral=True,
            )
            return

        self._used = True
        button.disabled = True
        game.hints_used += 1
        remaining = FruitGame.MAX_HINTS - game.hints_used
        footer = f"{remaining} hint(s) remaining." if remaining else "No more hints after this!"
        is_final = game.hints_used == FruitGame.MAX_HINTS

        # Disable this button on the current message first
        await interaction.response.edit_message(view=self)

        if is_final:
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{FruitGame.MAX_HINTS} — Final Hint!",
                description=f"The fruit name scrambled: **{_scramble(game.fruit)}**",
                color=discord.Color.red(),
            )
            embed.set_footer(text=footer)
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(
                title=f"Hint {game.hints_used}/{FruitGame.MAX_HINTS}",
                description="Here's another look!",
                color=discord.Color.gold(),
            )
            embed.set_image(url=game.pop_image())
            embed.set_footer(text=footer)
            await interaction.followup.send(
                embed=embed,
                view=FruitHintView(self.cog, self.channel_id),
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class FruitGuesser(commands.Cog):
    """Fruit guessing game — who can identify the mystery fruit from a photo?"""

    def __init__(self, bot):
        self.bot = bot
        self.games: dict[int, FruitGame] = {}   # channel_id → FruitGame

    # ── Image fetching ────────────────────────────────────────────────────────

    # Keywords that indicate a file is NOT a fruit photo
    _SKIP_KEYWORDS = frozenset({
        "flag", "map", "logo", "icon", "coat_of_arms", "seal", "blank",
        "distribution", "chart", "diagram", "silhouette", "location",
        "outline", "locator", "signature", "portrait", "person",
    })

    @classmethod
    def _is_photo_title(cls, title: str) -> bool:
        t = title.lower().replace(" ", "_")
        if t.endswith((".svg", ".gif", ".ogg", ".ogv", ".webm", ".wav", ".mp3")):
            return False
        return not any(kw in t for kw in cls._SKIP_KEYWORDS)

    async def _urls_from_titles(
        self,
        session: aiohttp.ClientSession,
        titles: list[str],
        timeout: aiohttp.ClientTimeout,
    ) -> list[str]:
        """Resolve a list of File: titles to 800px thumbnail URLs."""
        photos = []
        for i in range(0, len(titles), 20):   # API max 20 titles per request
            batch = titles[i : i + 20]
            async with session.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "imageinfo",
                    "iiprop": "url|mime",
                    "iiurlwidth": "800",
                    "format": "json",
                    "formatversion": "2",
                },
                timeout=timeout,
            ) as resp:
                data = await resp.json()
            for page in data.get("query", {}).get("pages", []):
                for info in page.get("imageinfo", []):
                    if info.get("mime") not in ("image/jpeg", "image/png"):
                        continue
                    url = info.get("thumburl") or info.get("url", "")
                    if url.startswith("http"):
                        photos.append(url)
        return photos

    async def _fetch_from_wikipedia(
        self,
        session: aiohttp.ClientSession,
        fruit: str,
        timeout: aiohttp.ClientTimeout,
    ) -> list[str]:
        """Pull images from the Wikipedia article for *fruit* (always on-topic)."""
        async with session.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": fruit,
                "prop": "images",
                "imlimit": "30",
                "format": "json",
                "formatversion": "2",
                "redirects": "1",
            },
            timeout=timeout,
        ) as resp:
            data = await resp.json()

        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return []

        titles = [
            img["title"]
            for img in pages[0].get("images", [])
            if self._is_photo_title(img["title"])
        ]
        if not titles:
            return []
        return await self._urls_from_titles(session, titles, timeout)

    async def _fetch_from_commons_search(
        self,
        session: aiohttp.ClientSession,
        fruit: str,
        timeout: aiohttp.ClientTimeout,
    ) -> list[str]:
        """Text-search Wikimedia Commons, filtering by filename.

        Appends ' fruit' to the query when not already present so that
        e.g. 'kiwi' becomes 'kiwi fruit' — avoiding birds, people, etc.
        """
        query = fruit if "fruit" in fruit.lower() else f"{fruit} fruit"
        async with session.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": "6",
                "gsrlimit": "50",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": "800",
                "format": "json",
                "formatversion": "2",
            },
            timeout=timeout,
        ) as resp:
            data = await resp.json()

        # Only keep files whose name contains at least one word from the fruit name
        fruit_words = {w.lower() for w in fruit.split() if len(w) > 3}
        photos = []
        for page in data.get("query", {}).get("pages", []):
            title = page.get("title", "").lower()
            if not self._is_photo_title(title):
                continue
            if fruit_words and not any(w in title for w in fruit_words):
                continue
            for info in page.get("imageinfo", []):
                if info.get("mime") not in ("image/jpeg", "image/png"):
                    continue
                url = info.get("thumburl") or info.get("url", "")
                if url.startswith("http"):
                    photos.append(url)
        return photos

    async def _fetch_images(self, fruit: str, max_count: int = 35, dev_channel=None) -> list[str]:
        """Return up to *max_count* relevant photo URLs for *fruit*.

        Always combines Wikipedia article images (editor-curated) with a
        'fruit'-suffixed Commons text search for a larger, varied pool.
        """
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "FruitGuesserBot/1.0 (Discord Bot)"}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                results = await asyncio.gather(
                    self._fetch_from_wikipedia(session, fruit, timeout),
                    self._fetch_from_commons_search(session, fruit, timeout),
                    return_exceptions=True,
                )
            wiki_photos, commons_photos = results
            if isinstance(wiki_photos, Exception):
                log.error("Wikipedia fetch failed for %r: %s", fruit, wiki_photos)
                if DEV_MODE and dev_channel:
                    await dev_channel.send(f"🔴 **[DEV]** Wikipedia fetch failed for `{fruit}`:\n```{wiki_photos}```")
                wiki_photos = []
            if isinstance(commons_photos, Exception):
                log.error("Commons fetch failed for %r: %s", fruit, commons_photos)
                if DEV_MODE and dev_channel:
                    await dev_channel.send(f"🔴 **[DEV]** Commons fetch failed for `{fruit}`:\n```{commons_photos}```")
                commons_photos = []

            log.debug("Fetched %d wiki + %d commons images for %r", len(wiki_photos), len(commons_photos), fruit)
            if DEV_MODE and dev_channel:
                await dev_channel.send(
                    f"🟡 **[DEV]** `{fruit}`: {len(wiki_photos)} wiki + {len(commons_photos)} commons images fetched"
                )

            # Merge, deduplicate, Wikipedia results first
            seen: set[str] = set()
            photos: list[str] = []
            for url in wiki_photos + commons_photos:
                if url not in seen:
                    seen.add(url)
                    photos.append(url)

            if not photos:
                log.warning("No images found for fruit %r", fruit)
                if DEV_MODE and dev_channel:
                    await dev_channel.send(f"⚠️ **[DEV]** No images found for `{fruit}` after merging.")
            random.shuffle(photos)
            return photos[:max_count]
        except Exception as e:
            log.exception("Unexpected error fetching images for %r", fruit)
            if DEV_MODE and dev_channel:
                await dev_channel.send(f"🔴 **[DEV]** Unexpected error fetching images for `{fruit}`:\n```{e}```")
            return []

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _game_timer(self, channel: discord.TextChannel, fruit: str):
        """Background task that ends the round after 60 seconds."""
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return  # game was won; task cancelled by on_message handler

        if channel.id not in self.games:
            return

        del self.games[channel.id]
        embed = discord.Embed(
            title="Time's up!",
            description=f"Nobody guessed it. The fruit was **{fruit}**.",
            color=discord.Color(0x99aab5),   # Discord greyple
        )
        await channel.send(embed=embed)

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    async def fruitguesser(self, ctx: commands.Context):
        """Start a fruit guessing game. 60 seconds — can you name it?"""
        if ctx.channel.id in self.games:
            await ctx.send(
                "A game is already running here! "
                "Type your guess or `$fhint` for another image."
            )
            return

        fruit = random.choice(FRUITS)
        loading = await ctx.send("Searching for images...")

        images = await self._fetch_images(fruit, dev_channel=ctx.channel)
        if not images:
            await loading.edit(content="Couldn't fetch images right now. Please try again!")
            return

        task = asyncio.create_task(self._game_timer(ctx.channel, fruit))
        game = FruitGame(fruit, images, task)
        self.games[ctx.channel.id] = game

        embed = discord.Embed(
            title=f"What fruit is this??{DEV_LABEL}",
            description=(
                "Type your guess in chat — anyone can answer!\n"
                "You have **60 seconds**. Use the **Hint** button below *(3 max, last hint scrambles the name)*."
            ),
            color=discord.Color.green(),
        )
        embed.set_image(url=game.pop_image())
        await loading.edit(content=None, embed=embed, view=FruitHintView(self, ctx.channel.id))

    # ── Guess listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        game = self.games.get(message.channel.id)
        if not game:
            return

        # Ignore valid bot commands (e.g. $fruitguesser)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if message.content.strip().lower() != game.fruit.lower():
            return

        # ── Correct guess ──────────────────────────────────────────────────
        game.task.cancel()
        del self.games[message.channel.id]

        embed = discord.Embed(
            title="Correct!",
            description=(
                f"**{message.author.display_name}** got it!\n\n"
                f"The fruit was **{game.fruit}**! Congratulations!"
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Start a new game any time with $fruitguesser!")
        await message.channel.send(embed=embed)

    # ── Cleanup on unload ─────────────────────────────────────────────────────

    def cog_unload(self):
        for game in self.games.values():
            game.task.cancel()
        self.games.clear()
