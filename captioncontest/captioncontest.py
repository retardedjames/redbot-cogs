import asyncio
import hashlib
import random
import time
from urllib.parse import quote

import aiohttp
import discord
from discord import ui
from redbot.core import Config, commands
from redbot.core.bot import Red


# Appended to every scenario prompt to enforce the visual style
STYLE = (
    "New Yorker magazine cartoon, black and white ink line art, "
    "single panel, simple clean lines, crosshatching shading, "
    "white background, no text, no speech bubbles, no caption text, no words"
)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
MAX_CAPTIONS = 10
MAX_CAPTION_LEN = 200

# ---------------------------------------------------------------------------
# Scenarios
# Each is (scene_description, type) where type is:
#   "speaker" — a character is clearly positioned to say something
#   "scene"   — the situation itself is the joke setup, caption goes below
# ---------------------------------------------------------------------------
SCENARIOS = [
    # ── Speaker scenarios ──────────────────────────────────────────────────
    ("a shark in a business suit presenting quarterly earnings charts to visibly terrified coworkers at a conference table", "speaker"),
    ("the Grim Reaper lying on a therapist's couch, the therapist nearby holding a clipboard and taking notes", "speaker"),
    ("a medieval knight furiously jabbing at a grocery store self-checkout machine while items pile up on the belt", "speaker"),
    ("two skeletons seated at a bar, one gesturing dramatically mid-explanation", "speaker"),
    ("a caveman delivering a TED talk to other seated cavemen in a cave, pointing at a crude stick figure drawing on the wall", "speaker"),
    ("God seated behind a complaints desk, an extremely long winding line of people stretching out through heaven's gate", "speaker"),
    ("a ghost nervously seated across from a hiring manager in a corporate job interview, interviewer looking skeptical", "speaker"),
    ("an elderly wizard jabbing his wand furiously at a broken laptop that refuses to work, useless sparks flying", "speaker"),
    ("an alien at a grocery store checkout with completely incomprehensible alien items on the conveyor belt, cashier bewildered", "speaker"),
    ("a robot and a human seated on opposite ends of a couch at couples therapy, therapist between them", "speaker"),
    ("a penguin in a tiny business suit pitching to three bored venture capitalists seated at a long table", "speaker"),
    ("a Viking warrior at a yoga class, deeply confused, attempting downward dog with terrible form", "speaker"),
    ("a pirate with an eyepatch at an eye doctor's office trying to read the letter chart, doctor looking puzzled", "speaker"),
    ("a full-size dinosaur standing at a tiny door labeled 'Evolution Department', clearly too large to enter", "speaker"),
    ("a mermaid at a DMV counter filling out paperwork, fin dangling awkwardly off the stool", "speaker"),
    ("a vampire staring at a blood bank ATM screen reading 'TRANSACTION DECLINED', fist raised", "speaker"),
    ("a bewildered time traveler in Victorian clothes arguing with a hotel receptionist holding the wrong century's ledger", "speaker"),
    ("an intense philosopher and a barista locked in a heated debate over a very simple coffee order", "speaker"),
    ("Santa Claus seated across from a very stern IRS auditor surrounded by enormous ledgers of gift deliveries", "speaker"),
    ("the devil at a desk reviewing a towering stack of employee satisfaction surveys with growing disappointment", "speaker"),
    ("an angel at an HR department filing a formal complaint, enormous stack of papers on the desk between them", "speaker"),
    ("Bigfoot at a passport control booth, officer squinting skeptically at the passport photo", "speaker"),
    ("a mummy tangled in its own unraveling bandages trying to fill out health insurance paperwork", "speaker"),
    ("a fortune teller at a career counseling session, crystal ball on the desk, career counselor taking notes", "speaker"),
    ("a large bear in a suit delivering annual performance reviews to a nervous smaller bear across a desk", "speaker"),
    ("a giant sea monster politely raising one enormous tentacle to be recognized in a small claims courtroom", "speaker"),
    ("a werewolf in a barber's chair, barber studying the result with profound uncertainty and a comb", "speaker"),
    ("a dog on a psychiatrist's couch earnestly explaining its complicated feelings about the mailman", "speaker"),
    ("a centaur visibly struggling to sit at a normal office desk and chair, coworkers pretending not to notice", "speaker"),
    ("a tiny devil on one person's shoulder arguing loudly with a tiny angel on the other shoulder, person between them looking completely exhausted", "speaker"),
    ("Frankenstein's monster on a first date at a fancy restaurant, date gripping menu nervously", "speaker"),
    ("a plague doctor at a modern hospital new employee orientation, clearly out of place among the others", "speaker"),
    ("a sphinx blocking a subway turnstile demanding a riddle from frustrated morning commuters behind her", "speaker"),
    ("two astronauts crammed in a very tiny elevator, one has brought an absurd amount of luggage", "speaker"),
    ("a talking parrot on a witness stand in court being cross-examined, one lawyer looking smug, the other horrified", "speaker"),
    ("a witch at a department of motor vehicles getting her broomstick registered, clerk filling out forms", "speaker"),
    ("two penguins at a couples counselor, one has brought a fish to the session as supporting evidence", "speaker"),
    ("a very small knight in full armor explaining something earnestly to a completely uninterested enormous bear", "speaker"),
    ("the sun and the moon in marriage counseling, earth sitting uncomfortably between them", "speaker"),
    ("a cat sitting across from a job interviewer, resume on the desk lists 'knocking things off shelves' under relevant experience", "speaker"),
    ("a life coach writing 'STEP 1: TRY' on a whiteboard to a single deeply unimpressed turtle seated in a folding chair", "speaker"),
    ("a dragon in a tiny office cubicle, fire suppression system going off above it, dragon looking guilty", "speaker"),
    ("a skeleton at a pharmacy counter trying to fill a prescription for calcium supplements, pharmacist looking skeptical", "speaker"),
    ("an octopus at a job interview struggling to shake hands with the interviewer, papers flying everywhere", "speaker"),
    ("a tiny fairy godmother reading her performance review, her supervisor tapping on a chart labeled 'Wishes Granted Per Quarter'", "speaker"),
    ("a robot at a wine tasting, swirling and sniffing the glass with mechanical precision, sommelier raising an eyebrow", "speaker"),
    ("a zombie in a real estate agent's office, agent presenting fixer-upper listings with great enthusiasm", "speaker"),
    ("a mole at an eye doctor, the doctor gesturing to the very blurry letter chart, mole squinting desperately", "speaker"),
    ("Poseidon at a city pool board meeting, dripping wet, explaining something to very dry and uncomfortable trustees", "speaker"),
    ("a cloud on a psychiatrist's couch explaining its complicated feelings about sunshine", "speaker"),
    ("Hercules filing a workers' compensation claim at a small government office window, enormous stack of forms in hand", "speaker"),
    ("the Easter Bunny at an accountant's office during tax season, surrounded by cartons of receipts for eggs and baskets", "speaker"),
    ("an enormous troll trying to squeeze through a tiny door labeled 'Human Resources'", "speaker"),
    ("a very formal butler presenting a single small rock on a silver tray to an unimpressed cat", "speaker"),
    ("a knight in full armor in a modern spin class, instructor pointing firmly at the resistance dial", "speaker"),
    ("a groundhog in a suit testifying before a congressional committee, senators leaning forward with urgent questions", "speaker"),
    ("a fairy at the TSA security checkpoint, wand confiscated in a bin, fairy looking extremely put out", "speaker"),
    ("a cyclops at an optometrist, only one lens on the trial frame, doctor making careful notes", "speaker"),
    ("a werewolf at a dog groomer being told to sit still, groomer holding scissors very nervously", "speaker"),
    ("a leprechaun at a gold exchange window, a very long skeptical line forming behind him", "speaker"),
    ("a time-traveler from the past at a modern gym, utterly confused by the equipment, personal trainer gesturing helpfully", "speaker"),
    ("Medusa at a photo studio for a headshot, photographer setting up nervously behind a large polished shield", "speaker"),
    ("a very nervous squirrel presenting its financial plan to a skeptical bank loan officer", "speaker"),
    ("a tooth fairy with a briefcase full of teeth arguing with a dentist about fair market pricing", "speaker"),
    ("a kraken at the DMV attempting to fill out a boat registration form with one tentacle, clerk watching helplessly", "speaker"),
    ("two robots on a first date at a restaurant, one reading the menu with a visible error message on its face", "speaker"),
    ("Santa's elf presenting its resignation letter across a desk to a stunned Santa at the North Pole HR office", "speaker"),
    ("a genie sitting across from a financial advisor, lamp on the desk between them, discussing wish portfolio diversification", "speaker"),
    ("a phoenix at an insurance office, agent surrounded by enormous 'PRIOR CLAIM' folders stacked to the ceiling", "speaker"),
    ("a dragon in traffic school seated at a tiny desk, instructor pointing at a 'NO OPEN FLAMES' sign", "speaker"),
    ("Death waiting in an extremely long line at the DMV, scythe resting on the counter, clerk waving him forward", "speaker"),
    ("a minotaur in an escape room, staff watching nervously through the one-way mirror as the clock runs down", "speaker"),
    ("a goblin at a pawn shop trying to sell a large pile of suspiciously identical gold coins, owner squinting", "speaker"),
    ("a griffin at a car rental counter, agent struggling to find an appropriate vehicle class on the computer", "speaker"),
    ("a centaur at a tailor shop, tailor on knees measuring the horse half with a measuring tape, looking overwhelmed", "speaker"),
    ("a poltergeist at an apartment showing, realtor nervously trying to explain the floating furniture to prospective tenants", "speaker"),
    ("a phoenix applying to re-enroll at a university after burning out mid-semester, dean looking carefully at the file", "speaker"),
    ("an apologetic tornado meeting with the mayor at a small conference table, tiny funnel cloud still spinning gently behind it", "speaker"),
    ("a skeleton arguing with a doctor about whether it needs a full physical, doctor holding up a completely transparent x-ray", "speaker"),
    ("a mime at a podium during a speaking engagement, audience growing visibly frustrated", "speaker"),
    ("a giant snail presenting its five-year business plan to an impatient venture capitalist checking a watch", "speaker"),
    ("an alien exchange student at show-and-tell presenting a family photo that causes visible alarm among the class", "speaker"),
    ("a goldfish at a real estate open house, fishbowl under one fin, asking the agent very detailed questions about water pressure", "speaker"),
    ("a snowman in a doctor's office, thermometer in mouth, nurse wearing a very concerned expression", "speaker"),
    ("a very large volcano at a neighborhood community board meeting about noise complaints and light pollution", "speaker"),
    ("a tiny elf presenting its timesheet to a giant skeptical manager, several hours circled in red", "speaker"),
    ("a medieval court jester performing at a corporate all-hands meeting, all employees staring ahead blankly", "speaker"),
    ("two cats at a corporate retreat trust fall exercise, neither making any effort to catch the other", "speaker"),
    ("a sea captain arguing with Google Maps on a phone, standing at a harbor looking baffled", "speaker"),
    ("a haunted portrait in an art gallery being interviewed by a detective about what it has witnessed over the centuries", "speaker"),
    ("a very small fairy riding public transit, standing on a seat trying to reach the overhead grip, commuters pretending not to notice", "speaker"),
    ("a sphinx at a game show buzzing in before the host has finished reading the question, host looking startled", "speaker"),
    ("a large friendly monster at a kindergarten career day, children raising hands with enormous enthusiasm", "speaker"),
    ("a tree at a therapy session earnestly explaining its complicated feelings about a nearby lumberjack", "speaker"),
    # ── Scene scenarios ────────────────────────────────────────────────────
    ("a deserted island with two castaways on opposite sides: one side has a full mansion and swimming pool, the other a tiny stick hut, the mansion owner is crossing the beach holding a clipboard labeled 'HOA VIOLATION NOTICE'", "scene"),
    ("Noah's ark boarding two of every animal; at the gangplank a bouncer is checking a list while two confused humans argue they should qualify", "scene"),
    ("a small person trapped inside a snow globe, knocking on the glass while a gentle snowstorm swirls around them inside and bright sun shines in the normal world outside", "scene"),
    ("heaven's front gate with a large real-estate FOR SALE sign out front and a bright red SOLD sticker on it, smaller text reads 'sold as-is, no warranty'", "scene"),
    ("a dinosaur peering through a backyard telescope at a tiny incoming meteor, checking it off a to-do list on a clipboard", "scene"),
    ("a cheerful children's lemonade stand staffed entirely by wolves in business attire, one nervous human adult customer approaches with exact change", "scene"),
    ("two goldfish in a fishbowl, one fish has drawn elaborate multi-phase escape tunnel diagrams all over the glass in permanent marker", "scene"),
    ("a museum exhibit behind a velvet rope, placard reads 'Modern Man In Natural Habitat', displaying a man in a recliner holding a TV remote, surrounded by snacks", "scene"),
    ("a protest picket line outside the gates of heaven, signs read 'UNFAIR HOURS', 'CLOUDS NOT ERGONOMIC', 'HALO GIVES ME A HEADACHE'", "scene"),
    ("a vending machine in hell where every snack costs one dollar five cents; a demon holds only a dollar bill, staring at the machine", "scene"),
    ("a forked road in a dark forest; both paths have wooden signs pointing in opposite directions but both signs say 'REGRET'", "scene"),
    ("a corporate boardroom PowerPoint presentation on a large screen showing the Titanic hitting an iceberg, slide title reads 'Q3 RESULTS'", "scene"),
    ("two thunderclouds having a shouting argument, a lightning bolt crackling between them mid-debate, a smaller cloud off to the side rolling its eyes", "scene"),
    ("a fish looking up at a fisherman's lure dangling in the water, a second fish leaning over and whispering a warning", "scene"),
    ("raccoons in tiny tuxedos gathered formally around an overturned trash can set up as a fine dining table, complete with candelabra and cloth napkins", "scene"),
    ("a single ordinary door floating in the middle of empty outer space; an astronaut in a spacesuit approaches it, about to knock politely", "scene"),
    ("a framed obituary hung alone on a large bare wall, it reads in large elegant letters only: 'HE DID HIS BEST'", "scene"),
    ("a museum exhibit showing the classic evolution-of-man chart, but the final modern human at the end is hunched over a smartphone, with a small arrow curving back to the first hunched ape at the beginning", "scene"),
    ("a cemetery with identical neat gravestones in perfect rows; one headstone has a shiny gold 'PARTICIPATION AWARD' ribbon pinned to it", "scene"),
    ("a motivational poster on an office wall showing a man triumphantly falling off a cliff into fog; the caption area below the image is completely blank", "scene"),
    ("a waiting room in purgatory where everyone has clearly been sitting so long that they have started decorating, hanging pictures, and rearranging the furniture", "scene"),
    ("a very small embarrassed dragon standing under a prominent 'NO OPEN FLAMES' sign at the entrance to a public library", "scene"),
    ("a fully-stocked survival prepper's underground bunker that has been carefully set up for a dinner party; one confused normal dinner guest is descending the hatch ladder", "scene"),
    ("a man looking at his reflection in a bathroom mirror; the reflection is looking at its phone instead of looking back", "scene"),
    ("an 'EXIT' sign glowing above a door in a dark hallway; a smaller handwritten sign taped below it reads 'just kidding'", "scene"),
    ("a 'BEFORE and AFTER' advertisement poster; both panels are identical", "scene"),
    ("a doomsday clock on a wall showing one second to midnight, a sticky note on it reads 'REMINDER: change batteries'", "scene"),
    ("two mountains side by side; one has a dramatic flag planted on the summit, the other has a tiny 'CLOSED FOR MAINTENANCE' sign", "scene"),
    ("a broken office coffee machine with a long mourning queue of coworkers wearing black armbands, a small floral tribute arranged on the counter beneath it", "scene"),
    ("a protest outside a zoo; the animals inside are holding signs reading 'FREE THE HUMANS'", "scene"),
    ("a trophy case at a school filled with gleaming first-place trophies; a small shelf at the very bottom labeled 'Effort' holds a single bent participation ribbon", "scene"),
    ("a luxury hotel lobby for clouds; a large nimbus cloud checks in with a tiny cloud suitcase, a cumulus cloud bellhop waiting nearby", "scene"),
    ("a 'happy hour' sign outside a bar in purgatory; every item on the menu board is listed as 'pending'", "scene"),
    ("a graveyard with only tech company names on the headstones: 'MySpace', 'Vine', 'Google+', one very fresh plot just dug", "scene"),
    ("a pie chart titled 'How I Spend My Time' where 99% is labeled 'thinking about making the pie chart'", "scene"),
    ("a glass jar on a desk labeled 'PROBLEMS TO DEAL WITH LATER', so completely overflowing that the lid cannot close", "scene"),
    ("a job posting tacked to a corkboard: the requirements section fills the entire page; the compensation section reads simply 'exposure'", "scene"),
    ("a 'KEEP CALM' poster hung on a wall where everything in the room is clearly on fire", "scene"),
    ("an urgent memo pinned to a bulletin board reading: 'Regarding the previous memo: disregard. Regarding this memo: see previous memo.'", "scene"),
    ("a city billboard advertising 'NEW! RESPONSIBILITY — now in fun sizes'", "scene"),
    ("a list of New Year's resolutions where every item has been crossed out except the last one, which reads 'write better list'", "scene"),
    ("a very crowded elevator with a single button labeled 'SAME FLOOR'", "scene"),
    ("an office plant with a laminated card taped to its pot reading 'DO NOT WATER — currently thriving'", "scene"),
    ("an instruction manual open to a complex diagram whose very last step simply reads 'ask someone'", "scene"),
    ("a tiny emergency glass case mounted on a wall that contains, behind the 'BREAK IN CASE OF EMERGENCY' label, a single bite of chocolate", "scene"),
    ("a 'things to be grateful for' whiteboard in an office; employees have contributed only 'technically still employed'", "scene"),
    ("a 'TODAY'S SPECIALS' chalkboard at a diner where every item has been crossed off and replaced with the word 'soup'", "scene"),
    ("a street where every house has a 'FOR SALE' sign except one in the middle, which has a 'GOOD LUCK' sign", "scene"),
    ("a very long staircase to heaven with an 'OUT OF ORDER' sign on the escalator beside it, an exhausted queue stretching down out of sight", "scene"),
    ("a graduation stage where the single diploma on the podium reads 'DEGREE IN HINDSIGHT'", "scene"),
    ("a hotel lost-and-found shelf neatly labeled 'THINGS PEOPLE FORGOT ON PURPOSE'", "scene"),
    ("a 'CAUTION: WET FLOOR' sign placed in a very small square in the center of a massive, completely dry ballroom", "scene"),
    ("a bus stop with a posted schedule where every departure time simply reads 'eventually'", "scene"),
    ("a library 'most overdue' board; the top entry shows a book that has been out for 47 years, fine listed as 'immeasurable'", "scene"),
    ("a welcome mat that reads 'GO AWAY' in elegant gold script, a formal wreath on the door above it", "scene"),
    ("a crossword puzzle where every answer entered is 'I DON'T KNOW'", "scene"),
    ("a to-do list that has been fully crossed out; the final item at the bottom is 'make to-do list' with a small arrow pointing back up to the top", "scene"),
    ("a door labeled 'PUSH' that has been pulled so hard it has come entirely off its hinges and is leaning against the frame", "scene"),
    ("two adjacent signs on a building entrance: one reads 'OPEN 24 HOURS', the other reads 'CLOSED'", "scene"),
    ("an iceberg floating in calm water with a 'SEA LEVEL' marker midway down; below the waterline an elaborate fully-furnished office is visible", "scene"),
    ("a piggy bank on a shelf wearing a tiny hand-lettered 'DO NOT DISTURB' sign", "scene"),
    ("a bulletin board labeled 'WINS THIS QUARTER' — entirely empty except a single sticky note that reads 'this sticky note'", "scene"),
    ("a tiny scroll labeled 'Terms and Conditions' unrolling off a desk, out the door, and disappearing down the street", "scene"),
    ("a dumpster with a bronze commemorative plaque mounted on its side reading 'EMPLOYEE OF THE MONTH — 14 YEARS RUNNING'", "scene"),
    ("two signs on a front lawn side by side: one reads 'FIXER UPPER', the other reads 'MOVE-IN READY'", "scene"),
    ("a large 'THINK OUTSIDE THE BOX' motivational poster hung on the wall inside a very small windowless cubicle", "scene"),
    ("a tiny chair at a tiny desk in the center of a vast empty room; the desk has a nameplate reading 'LAST REMAINING RESPONSIBILITY'", "scene"),
    ("a 'COMPLAINT DEPARTMENT' door in a hallway that has been completely bricked over; a small sign on the bricks reads 'see website'", "scene"),
    ("a message in a bottle that has washed ashore; nearby on the beach a sign reads 'COMPLAINT BOX'", "scene"),
    ("a scoreboard at a sporting event showing the score: HUMANS 0 — EVERYTHING ELSE ∞", "scene"),
    ("a very large empty canvas on a museum wall, explanatory placard reading 'Untitled, Oil on Canvas — The artist had not yet started'", "scene"),
    ("a family portrait in a living room where everyone poses normally except one member whose face has been replaced with a motivational poster", "scene"),
    ("a corporate logo on a building facade with the tagline 'WE ARE LISTENING' and a tiny asterisk leading to a footnote in impossibly small print", "scene"),
    ("a park with two benches facing away from each other, a single figure sitting alone on each one, both reading identical books", "scene"),
    ("a map with a 'YOU ARE HERE' sticker placed ambiguously directly between two unlabeled locations", "scene"),
    ("a 'SMART HOME' control panel with every button labeled; one large button simply reads 'OVERTHINK'", "scene"),
    ("a 'BEFORE AND AFTER' diet advertisement where both photos are identical, the subject in each looking mildly confused", "scene"),
]


def _scenario_hash(text: str) -> str:
    """Short stable identifier for a scenario string."""
    return hashlib.md5(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# UI: Modal + Button View
# ---------------------------------------------------------------------------

class SubmitCaptionModal(ui.Modal, title="Submit Your Caption"):
    caption_input = ui.TextInput(
        label="Your caption",
        placeholder="Write your caption here...",
        max_length=MAX_CAPTION_LEN,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, cog: "CaptionContest", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        game = self.cog._games.get(self.guild_id)
        if not game or game["phase"] != "submitting":
            await interaction.response.send_message("Submissions are closed!", ephemeral=True)
            return

        uid = interaction.user.id
        captions = game["captions"]
        text = self.caption_input.value.strip()

        if uid not in captions and len(captions) >= MAX_CAPTIONS:
            await interaction.response.send_message(
                f"Maximum captions ({MAX_CAPTIONS}) already reached!", ephemeral=True
            )
            return

        updating = uid in captions
        captions[uid] = text

        verb = "updated" if updating else "submitted"
        await interaction.response.send_message(
            f"Caption {verb}! You can update it by clicking the button again.",
            ephemeral=True,
        )
        await interaction.channel.send(
            f"{interaction.user.mention} {verb} a caption! ({len(captions)} total)",
            delete_after=8,
        )


class SubmitCaptionView(ui.View):
    def __init__(self, cog: "CaptionContest", guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @ui.button(label="Submit Caption", style=discord.ButtonStyle.primary, emoji="✏️")
    async def submit_btn(self, interaction: discord.Interaction, button: ui.Button):
        game = self.cog._games.get(self.guild_id)
        if not game or game["phase"] != "submitting":
            await interaction.response.send_message("Submissions are closed!", ephemeral=True)
            return
        await interaction.response.send_modal(SubmitCaptionModal(self.cog, self.guild_id))


class VoteView(ui.View):
    """Private button-based voting — responses are ephemeral so nobody can see who voted."""

    def __init__(self, cog: "CaptionContest", guild_id: int, caption_list: list):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        for i, (_author_id, _text) in enumerate(caption_list):
            btn = ui.Button(
                label=f"Caption {i + 1}",
                style=discord.ButtonStyle.secondary,
                emoji=NUMBER_EMOJIS[i],
                custom_id=f"cc_vote_{guild_id}_{i}",
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            game = self.cog._games.get(self.guild_id)
            if not game or game["phase"] != "voting":
                await interaction.response.send_message("Voting is closed!", ephemeral=True)
                return

            voter_id = interaction.user.id
            votes = game["votes"]
            caption_list = game["caption_list"]
            text = caption_list[idx][1]

            prev = votes.get(voter_id)
            if prev == idx:
                await interaction.response.send_message(
                    f"You're already voting for {NUMBER_EMOJIS[idx]} Caption {idx + 1}. "
                    f"Click a different one to change your vote.",
                    ephemeral=True,
                )
                return

            votes[voter_id] = idx
            if prev is not None:
                msg = f"Vote changed to {NUMBER_EMOJIS[idx]} **Caption {idx + 1}**: {text}"
            else:
                msg = f"Voted for {NUMBER_EMOJIS[idx]} **Caption {idx + 1}**: {text}"
            await interaction.response.send_message(msg, ephemeral=True)

        return callback


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class CaptionContest(commands.Cog):
    """Caption Contest — a cartoon is generated and players compete for the best caption."""

    SUBMIT_SECONDS = 60   # 1 minute to submit
    VOTE_SECONDS = 90     # 90 seconds to vote

    def __init__(self, bot: Red):
        self.bot = bot
        self._games: dict[int, dict] = {}  # guild_id -> game state
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)
        self.config.register_guild(used_scenarios=[])  # list of [hash_str, timestamp_float]

    def cog_unload(self):
        for game in self._games.values():
            for key in ("submit_task", "vote_task"):
                t = game.get(key)
                if t:
                    t.cancel()
            for vkey in ("submit_view", "vote_view"):
                v = game.get(vkey)
                if v:
                    v.stop()

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    async def _fetch_image(self, scenario: str) -> str | None:
        full_prompt = f"{scenario}, {STYLE}"
        seed = random.randint(1, 999999)
        url = (
            "https://image.pollinations.ai/prompt/"
            + quote(full_prompt)
            + f"?width=1024&height=768&nologo=true&model=flux&seed={seed}"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        return url
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Scenario selection with 24-hour repeat prevention
    # ------------------------------------------------------------------

    async def _pick_scenario(self, guild) -> tuple[str, str]:
        """Pick a scenario not used in the last 24 hours for this guild."""
        now = time.time()
        cutoff = now - 86400  # 24 hours

        used_data = await self.config.guild(guild).used_scenarios()
        recent_hashes = {entry[0] for entry in used_data if entry[1] > cutoff}

        available = [s for s in SCENARIOS if _scenario_hash(s[0]) not in recent_hashes]
        if not available:
            # All scenarios used in the last 24 hours — reset and use full list
            available = SCENARIOS

        scenario, stype = random.choice(available)

        # Prune stale entries and record this usage
        new_used = [[h, t] for h, t in used_data if t > cutoff]
        new_used.append([_scenario_hash(scenario), now])
        await self.config.guild(guild).used_scenarios.set(new_used)

        return scenario, stype

    # ------------------------------------------------------------------
    # Game flow
    # ------------------------------------------------------------------

    async def _submit_timeout(self, guild_id: int):
        await asyncio.sleep(self.SUBMIT_SECONDS)
        game = self._games.get(guild_id)
        if not game or game["phase"] != "submitting":
            return
        ch = self.bot.get_channel(game["channel_id"])
        if ch:
            await ch.send("Time's up! Moving to voting...")
        await self._begin_voting(guild_id)

    async def _vote_timeout(self, guild_id: int):
        await asyncio.sleep(self.VOTE_SECONDS)
        await self._finish_game(guild_id)

    async def _disable_submit_button(self, game: dict):
        """Edit the submit message to show a disabled closed button."""
        ch = self.bot.get_channel(game["channel_id"])
        msg_id = game.get("submit_message_id")
        view = game.get("submit_view")
        if view:
            view.stop()
        if ch and msg_id:
            try:
                msg = await ch.fetch_message(msg_id)
                closed_view = ui.View()
                btn = ui.Button(
                    label="Submissions Closed",
                    style=discord.ButtonStyle.secondary,
                    emoji="🔒",
                    disabled=True,
                )
                closed_view.add_item(btn)
                await msg.edit(view=closed_view)
            except Exception:
                pass

    async def _begin_voting(self, guild_id: int):
        game = self._games.get(guild_id)
        if not game:
            return
        ch = self.bot.get_channel(game["channel_id"])
        if not ch:
            self._games.pop(guild_id, None)
            return

        await self._disable_submit_button(game)

        captions = game["captions"]
        if len(captions) < 2:
            await ch.send("Not enough captions submitted (need at least 2). Game cancelled.")
            self._games.pop(guild_id, None)
            return

        game["phase"] = "voting"
        caption_list = list(captions.items())  # [(user_id, text), ...] — order is stable
        game["caption_list"] = caption_list
        game["votes"] = {}  # voter_id -> caption index (private until reveal)

        embed = discord.Embed(
            title="Vote for the best caption!",
            description=(
                f"Click a button to cast your vote — your choice stays **private** until the reveal.\n"
                f"Voting closes in **{self.VOTE_SECONDS} seconds**."
            ),
            color=discord.Color.gold(),
        )
        embed.set_image(url=game["image_url"])

        lines = [f"{NUMBER_EMOJIS[i]}  {text}" for i, (_, text) in enumerate(caption_list)]
        embed.add_field(name="The Captions", value="\n".join(lines), inline=False)

        vote_view = VoteView(self, guild_id, caption_list)
        game["vote_view"] = vote_view
        vote_msg = await ch.send(embed=embed, view=vote_view)
        game["vote_message_id"] = vote_msg.id

        game["vote_task"] = asyncio.create_task(self._vote_timeout(guild_id))

    async def _finish_game(self, guild_id: int):
        game = self._games.pop(guild_id, None)
        if not game:
            return
        ch = self.bot.get_channel(game["channel_id"])
        if not ch:
            return

        caption_list = game.get("caption_list", [])
        if not caption_list:
            await ch.send("No captions were submitted. Game over.")
            return

        # Disable vote buttons
        vote_view = game.get("vote_view")
        if vote_view:
            vote_view.stop()
            vote_msg_id = game.get("vote_message_id")
            if vote_msg_id:
                try:
                    vote_msg = await ch.fetch_message(vote_msg_id)
                    closed_view = ui.View()
                    for i in range(len(caption_list)):
                        closed_view.add_item(ui.Button(
                            label=f"Caption {i + 1}",
                            style=discord.ButtonStyle.secondary,
                            emoji=NUMBER_EMOJIS[i],
                            disabled=True,
                        ))
                    await vote_msg.edit(view=closed_view)
                except Exception:
                    pass

        # Tally votes from private votes dict (no self-vote restriction)
        votes = game.get("votes", {})  # voter_id -> caption index
        vote_counts = {uid: 0 for uid, _ in caption_list}
        # voters_per_caption[idx] = list of voter display names
        voters_per_caption: dict[int, list[str]] = {i: [] for i in range(len(caption_list))}
        for voter_id, idx in votes.items():
            if idx < len(caption_list):
                author_id = caption_list[idx][0]
                vote_counts[author_id] += 1
                member = ch.guild.get_member(voter_id)
                voters_per_caption[idx].append(member.display_name if member else f"User {voter_id}")

        sorted_results = sorted(caption_list, key=lambda x: vote_counts[x[0]], reverse=True)
        winner_uid = sorted_results[0][0]
        winner_votes = vote_counts[winner_uid]

        embed = discord.Embed(title="Caption Contest — Results!", color=discord.Color.green())
        embed.set_image(url=game["image_url"])

        sorted_lines = []
        for uid, text in sorted_results:
            orig_idx = next(j for j, (u, _) in enumerate(caption_list) if u == uid)
            member = ch.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            v = vote_counts[uid]
            trophy = "🏆 " if (uid == winner_uid and winner_votes > 0) else ""
            voter_names = voters_per_caption[orig_idx]
            voter_str = f"\n    ↳ voted by: {', '.join(voter_names)}" if voter_names else ""
            sorted_lines.append(f"{trophy}**{name}** — {text}  *({v} vote{'s' if v != 1 else ''})*{voter_str}")

        embed.add_field(name="Results", value="\n".join(sorted_lines), inline=False)

        if winner_votes == 0:
            embed.set_footer(text="No votes cast — everyone's a winner (or loser).")
        else:
            member = ch.guild.get_member(winner_uid)
            name = member.display_name if member else f"User {winner_uid}"
            embed.set_footer(text=f"🏆 Winner: {name}")

        await ch.send(embed=embed)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.group(name="captioncontest", aliases=["cc"], invoke_without_command=True)
    @commands.guild_only()
    async def captioncontest(self, ctx: commands.Context):
        """Start a Caption Contest. A cartoon is generated; players compete for the best caption."""
        await ctx.invoke(self.cc_start)

    @captioncontest.command(name="start")
    async def cc_start(self, ctx: commands.Context):
        """Start a caption contest."""
        gid = ctx.guild.id
        if gid in self._games:
            await ctx.send("A caption contest is already running!")
            return

        self._games[gid] = {
            "channel_id": ctx.channel.id,
            "host_id": ctx.author.id,
            "image_url": None,
            "phase": "submitting",
            "captions": {},
            "caption_list": None,
            "votes": {},
            "submit_message_id": None,
            "submit_view": None,
            "vote_message_id": None,
            "vote_view": None,
            "submit_task": None,
            "vote_task": None,
        }

        wait_msg = await ctx.send("Generating cartoon, please wait...")
        scenario, stype = await self._pick_scenario(ctx.guild)
        url = await self._fetch_image(scenario)

        if not url:
            self._games.pop(gid, None)
            await wait_msg.edit(content="Image generation failed. Try again in a moment.")
            return

        self._games[gid]["image_url"] = url

        if stype == "speaker":
            hint = "Someone in this scene has something to say — what is it?"
        else:
            hint = "What's the caption for this scene?"

        embed = discord.Embed(
            title="Caption Contest!",
            description=(
                f"{hint}\n\n"
                f"Click the button to submit your caption.\n"
                f"You have **{self.SUBMIT_SECONDS} seconds**. Captions are anonymous until the reveal."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_image(url=url)

        view = SubmitCaptionView(self, gid)
        self._games[gid]["submit_view"] = view

        await wait_msg.delete()
        submit_msg = await ctx.send(embed=embed, view=view)
        self._games[gid]["submit_message_id"] = submit_msg.id

        self._games[gid]["submit_task"] = asyncio.create_task(
            self._submit_timeout(gid)
        )

    @captioncontest.command(name="end")
    async def cc_end(self, ctx: commands.Context):
        """Force end the current caption contest (host or admin only)."""
        gid = ctx.guild.id
        game = self._games.get(gid)
        if not game:
            await ctx.send("No caption contest is running.")
            return
        if ctx.author.id != game["host_id"] and not ctx.author.guild_permissions.manage_guild:
            await ctx.send("Only the host or a server admin can end the game early.")
            return

        for key in ("submit_task", "vote_task"):
            t = game.get(key)
            if t:
                t.cancel()

        if game["phase"] == "submitting":
            await ctx.send("Ending submissions early, moving to voting...")
            await self._begin_voting(gid)
        elif game["phase"] == "voting":
            await ctx.send("Ending voting early...")
            await self._finish_game(gid)

    @captioncontest.command(name="status")
    async def cc_status(self, ctx: commands.Context):
        """Check how many captions have been submitted."""
        gid = ctx.guild.id
        game = self._games.get(gid)
        if not game:
            await ctx.send("No caption contest is running.")
            return
        if game["phase"] == "submitting":
            n = len(game["captions"])
            await ctx.send(f"{n} caption{'s' if n != 1 else ''} submitted so far.")
        else:
            await ctx.send("Voting is in progress.")

    async def clear_recent_memory(self, guild=None) -> str:
        """Clear the 24-hour scenario repeat-prevention memory for this guild."""
        if guild is not None:
            await self.config.guild(guild).used_scenarios.set([])
        return "Caption Contest"
