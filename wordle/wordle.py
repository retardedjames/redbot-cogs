import io
import random

import discord
from PIL import Image, ImageDraw, ImageFont
from redbot.core import commands

from .words import WORDS

# ── Colour palette (Wordle dark theme) ───────────────────────────────────────
_BG     = (18,  18,  19)   # board / empty cell background
_BORDER = (58,  58,  60)   # empty cell border
_GREEN  = (83,  141, 78)   # correct letter, correct position
_YELLOW = (181, 159, 59)   # correct letter, wrong position
_GRAY   = (58,  58,  60)   # letter not in word
_WHITE  = (255, 255, 255)

_COLOR_MAP = {"green": _GREEN, "yellow": _YELLOW, "gray": _GRAY}

# ── Board geometry ────────────────────────────────────────────────────────────
_CELL = 81   # px per cell (square)
_GAP  = 8    # px gap between cells
_PAD  = 26   # px outer padding

# ── Keyboard geometry ─────────────────────────────────────────────────────────
_KEY_W        = 39   # key width
_KEY_H        = 47   # key height
_KEY_GAP      = 5    # gap between keys in a row
_KEY_ROW_GAP  = 8    # gap between keyboard rows
_KBD_TOP      = 18   # space between bottom of board and top of keyboard

_KEY_UNUSED   = (58,  58,  60)    # letter not yet guessed
_KEY_ABSENT   = (129, 131, 132)   # guessed and not in word
_KEY_PRESENT  = (181, 159, 59)    # guessed, wrong position (same as _YELLOW)
_KEY_CORRECT  = (83,  141, 78)    # guessed, correct position (same as _GREEN)

_KEY_COLOR_MAP = {"green": _KEY_CORRECT, "yellow": _KEY_PRESENT, "gray": _KEY_ABSENT}

_KEYBOARD_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]

_SOLO_MAX_GUESSES  = 5   # classic Wordle: only the starter guesses
_MULTI_MAX_GUESSES = 6   # multiplayer: anyone can guess


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_font(size: int = 36) -> ImageFont.FreeTypeFont:
    candidates = [
        "arialbd.ttf",                                                    # Windows
        "arial.ttf",                                                      # Windows
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",          # Debian/Ubuntu
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Fedora/RHEL
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",           # Alpine
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",              # NotoSans
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    # PIL ≥ 10 supports a size kwarg on the built-in bitmap font
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _letter_states(guesses: list) -> dict:
    """
    Return a dict mapping each guessed letter to its best colour state.
    Priority: green > yellow > gray.
    """
    priority = {"green": 3, "yellow": 2, "gray": 1}
    states: dict = {}
    for word, colours in guesses:
        for letter, colour in zip(word, colours):
            if priority[colour] > priority.get(states.get(letter), 0):
                states[letter] = colour
    return states


def _score_guess(guess: str, answer: str) -> list:
    """
    Return a list of 5 colour strings (green / yellow / gray) comparing
    *guess* against *answer*.  Handles duplicate letters correctly using
    a two-pass algorithm.
    """
    result    = ["gray"] * 5
    remaining = list(answer)   # letters still available for yellow matching

    # Pass 1 – mark greens and consume those letters
    for i in range(5):
        if guess[i] == answer[i]:
            result[i]    = "green"
            remaining[i] = ""

    # Pass 2 – mark yellows from what's left
    for i in range(5):
        if result[i] == "green":
            continue
        if guess[i] in remaining:
            result[i] = "yellow"
            remaining[remaining.index(guess[i])] = ""

    return result


def _draw_board(guesses: list, total_rows: int) -> io.BytesIO:
    """Render the Wordle grid + alphabet keyboard and return it as a PNG byte-stream."""
    cols = 5

    # ── Dimensions ────────────────────────────────────────────────────────────
    img_w   = cols * _CELL + (cols - 1) * _GAP + 2 * _PAD
    board_h = total_rows * _CELL + (total_rows - 1) * _GAP + 2 * _PAD
    kbd_h   = len(_KEYBOARD_ROWS) * _KEY_H + (len(_KEYBOARD_ROWS) - 1) * _KEY_ROW_GAP
    img_h   = board_h + _KBD_TOP + kbd_h + _PAD

    img  = Image.new("RGB", (img_w, img_h), _BG)
    draw = ImageDraw.Draw(img)
    font     = _load_font(47)
    key_font = _load_font(21)

    # ── Guess grid ────────────────────────────────────────────────────────────
    for row in range(total_rows):
        for col in range(cols):
            x = _PAD + col * (_CELL + _GAP)
            y = _PAD + row * (_CELL + _GAP)
            x2, y2 = x + _CELL - 1, y + _CELL - 1

            if row < len(guesses):
                word, colours = guesses[row]
                letter = word[col]
                fill   = _COLOR_MAP[colours[col]]
                draw.rectangle([x, y, x2, y2], fill=fill)
                bbox   = draw.textbbox((0, 0), letter, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text(
                    (x + (_CELL - tw) // 2 - bbox[0],
                     y + (_CELL - th) // 2 - bbox[1]),
                    letter, fill=_WHITE, font=font,
                )
            else:
                draw.rectangle([x, y, x2, y2], fill=_BG, outline=_BORDER, width=2)

    # ── Keyboard ──────────────────────────────────────────────────────────────
    letter_states = _letter_states(guesses)
    kbd_y = board_h + _KBD_TOP

    for row_keys in _KEYBOARD_ROWS:
        row_w = len(row_keys) * _KEY_W + (len(row_keys) - 1) * _KEY_GAP
        x     = (img_w - row_w) // 2   # centre each row

        for letter in row_keys:
            state = letter_states.get(letter)
            fill  = _KEY_COLOR_MAP.get(state, _KEY_UNUSED)
            x2, y2 = x + _KEY_W - 1, kbd_y + _KEY_H - 1
            draw.rectangle([x, kbd_y, x2, y2], fill=fill)
            bbox   = draw.textbbox((0, 0), letter, font=key_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (x + (_KEY_W - tw) // 2 - bbox[0],
                 kbd_y + (_KEY_H - th) // 2 - bbox[1]),
                letter, fill=_WHITE, font=key_font,
            )
            x += _KEY_W + _KEY_GAP

        kbd_y += _KEY_H + _KEY_ROW_GAP

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Game state ────────────────────────────────────────────────────────────────

class WordleGame:
    def __init__(self, word: str, max_guesses: int):
        self.word        = word.upper()
        self.max_guesses = max_guesses
        self.guesses     = []   # list of (WORD, [colour, …])
        self.won         = False

    def submit(self, guess: str) -> list:
        guess  = guess.upper()
        result = _score_guess(guess, self.word)
        self.guesses.append((guess, result))
        if guess == self.word:
            self.won = True
        return result

    @property
    def over(self) -> bool:
        return self.won or len(self.guesses) >= self.max_guesses

    @property
    def remaining(self) -> int:
        return self.max_guesses - len(self.guesses)


# ── Cog ───────────────────────────────────────────────────────────────────────

class Wordle(commands.Cog):
    """Wordle games — solo ($wordle) and multiplayer ($mwordle)."""

    def __init__(self, bot):
        self.bot        = bot
        self.solo_games:  dict = {}   # channel_id → (WordleGame, starter_id)
        self.multi_games: dict = {}   # channel_id → WordleGame

    def _any_game(self, channel_id: int) -> bool:
        return channel_id in self.solo_games or channel_id in self.multi_games

    # ── Commands ──────────────────────────────────────────────────────────────

    @commands.command()
    async def wordle(self, ctx: commands.Context):
        """Start a solo Wordle game. Only you can submit guesses."""
        if self._any_game(ctx.channel.id):
            await ctx.send("A Wordle game is already running here.")
            return

        word = random.choice(WORDS).upper()
        game = WordleGame(word, max_guesses=_SOLO_MAX_GUESSES)
        self.solo_games[ctx.channel.id] = (game, ctx.author.id)
        await ctx.send(
            f"**Wordle started!** Good luck, {ctx.author.mention}!\n"
            f"Guess the 5-letter word. You have **{_SOLO_MAX_GUESSES} guesses** — only you can play.\n"
            "Just type any 5-letter word in chat."
        )

    @commands.command()
    async def mwordle(self, ctx: commands.Context):
        """Start a multiplayer Wordle game — anyone in chat can guess."""
        if self._any_game(ctx.channel.id):
            await ctx.send("A Wordle game is already running here.")
            return

        word = random.choice(WORDS).upper()
        game = WordleGame(word, max_guesses=_MULTI_MAX_GUESSES)
        self.multi_games[ctx.channel.id] = game
        await ctx.send(
            "**Multiplayer Wordle started!** Guess the 5-letter word.\n"
            f"You have **{_MULTI_MAX_GUESSES} guesses** — anyone can play!\n"
            "Just type any 5-letter word in chat."
        )

    async def force_stop_game(self, channel_id: int):
        """Stop any active game in channel_id. Returns game name if stopped, else None."""
        if channel_id in self.solo_games:
            del self.solo_games[channel_id]
            return "Wordle"
        if channel_id in self.multi_games:
            del self.multi_games[channel_id]
            return "Wordle"
        return None

    # ── Guess listener ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        channel_id = message.channel.id
        in_solo  = channel_id in self.solo_games
        in_multi = channel_id in self.multi_games

        if not in_solo and not in_multi:
            return

        word = message.content.strip()

        # Must be exactly 5 alphabetic characters
        if len(word) != 5 or not word.isalpha():
            return

        # Don't steal bot commands (e.g. `$wordle`, `$mwordle`)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if in_solo:
            game, starter_id = self.solo_games[channel_id]
            if message.author.id != starter_id:
                return   # silently ignore — only the starter may guess
            result = game.submit(word)
            buf    = _draw_board(game.guesses, total_rows=game.max_guesses)
            file   = discord.File(buf, filename="wordle.png")

            if game.won:
                del self.solo_games[channel_id]
                await message.channel.send(
                    f"Congratulations {message.author.mention}! "
                    f"The word was **{game.word}** — solved in "
                    f"**{len(game.guesses)}** guess(es)!",
                    file=file,
                )
            elif game.over:
                del self.solo_games[channel_id]
                await message.channel.send(
                    f"No more guesses! The word was **{game.word}**.",
                    file=file,
                )
            else:
                await message.channel.send(
                    f"**{game.remaining}** guess(es) remaining.",
                    file=file,
                )

        else:  # multiplayer
            game   = self.multi_games[channel_id]
            result = game.submit(word)
            buf    = _draw_board(game.guesses, total_rows=game.max_guesses)
            file   = discord.File(buf, filename="wordle.png")

            if game.won:
                del self.multi_games[channel_id]
                await message.channel.send(
                    f"Congratulations {message.author.mention}! "
                    f"The word was **{game.word}** — solved in "
                    f"**{len(game.guesses)}** guess(es)!",
                    file=file,
                )
            elif game.over:
                del self.multi_games[channel_id]
                await message.channel.send(
                    f"No more guesses! The word was **{game.word}**.",
                    file=file,
                )
            else:
                await message.channel.send(
                    f"**{game.remaining}** guess(es) remaining.",
                    file=file,
                )
