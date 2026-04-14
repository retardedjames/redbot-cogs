import asyncio
import re
import random
from collections import deque

import discord
from redbot.core import commands, Config

# ── Dev mode — set DEV_MODE = False for production ───────────────────────────
DEV_MODE = False

if DEV_MODE:
    import subprocess as _sp, pathlib as _pl
    try:
        _sha = _sp.check_output(
            ["git", "-C", str(_pl.Path(__file__).parent), "rev-parse", "--short", "HEAD"],
            stderr=_sp.DEVNULL, text=True,
        ).strip()
    except Exception:
        _sha = "dev"
    DEV_LABEL = f"  [{_sha}]"
else:
    DEV_LABEL = ""
# ─────────────────────────────────────────────────────────────────────────────

# Each entry: (quote with {BLANK} placeholder, answer word, attribution)
# Quotes are under 150 characters (original text). Answer words are meaningful
# nouns/verbs/adjectives — never short conjunctions or prepositions.

QUOTES = [
    # ── Oscar Wilde ───────────────────────────────────────────────────────────
    ("Be yourself; everyone else is already {BLANK}.", "taken", "Oscar Wilde"),
    ("I can resist everything except {BLANK}.", "temptation", "Oscar Wilde"),
    ("I am not young enough to know {BLANK}.", "everything", "Oscar Wilde"),
    ("We are all in the gutter, but some of us are looking at the {BLANK}.", "stars", "Oscar Wilde"),
    ("Always forgive your enemies; nothing annoys them so {BLANK}.", "much", "Oscar Wilde"),
    ("The truth is rarely pure and never {BLANK}.", "simple", "Oscar Wilde"),
    ("A good friend will always stab you in the {BLANK}.", "front", "Oscar Wilde"),
    ("The only way to get rid of a temptation is to {BLANK} to it.", "yield", "Oscar Wilde"),
    ("Experience is simply the name we give our {BLANK}.", "mistakes", "Oscar Wilde"),
    ("I have nothing to declare except my {BLANK}.", "genius", "Oscar Wilde"),
    ("Nowadays people know the price of everything and the value of {BLANK}.", "nothing", "Oscar Wilde"),
    ("To lose one parent is misfortune; to lose both looks like {BLANK}.", "carelessness", "Oscar Wilde"),
    ("The books that the world calls immoral show the world its own {BLANK}.", "shame", "Oscar Wilde"),
    ("I have the simplest tastes. I am always satisfied with the {BLANK}.", "best", "Oscar Wilde"),
    ("The only difference between genius and stupidity is that genius has its {BLANK}.", "limits", "Oscar Wilde"),
    ("I always pass on good advice. It is the only thing to do with it.", "advice", "Oscar Wilde"),
    ("To define is to {BLANK}.", "limit", "Oscar Wilde"),
    ("The world is a stage, but the play is badly {BLANK}.", "cast", "Oscar Wilde"),
    ("I am so clever that sometimes I don't understand a single word of what I am {BLANK}.", "saying", "Oscar Wilde"),
    ("Fashion is a form of ugliness so intolerable that we have to alter it every six {BLANK}.", "months", "Oscar Wilde"),

    # ── Mark Twain ────────────────────────────────────────────────────────────
    ("The secret of getting ahead is getting {BLANK}.", "started", "Mark Twain"),
    ("If you tell the truth, you don't have to remember {BLANK}.", "anything", "Mark Twain"),
    ("Go to heaven for the climate, hell for the {BLANK}.", "company", "Mark Twain"),
    ("Age is an issue of mind over matter. If you don't mind, it doesn't {BLANK}.", "matter", "Mark Twain"),
    ("Never let your schooling interfere with your {BLANK}.", "education", "Mark Twain"),
    ("The man who does not read has no advantage over the man who {BLANK}.", "cannot", "Mark Twain"),
    ("The reports of my death are greatly {BLANK}.", "exaggerated", "Mark Twain"),
    ("Never argue with stupid people, they'll drag you down to their level and beat you with {BLANK}.", "experience", "Mark Twain"),
    ("The human race has one really effective weapon, and that is {BLANK}.", "laughter", "Mark Twain"),
    ("I used to think I was indecisive, but now I'm not so {BLANK}.", "sure", "Mark Twain"),
    ("I am an old man and have known many troubles, but most of them never {BLANK}.", "happened", "Mark Twain"),
    ("Whenever you find yourself on the side of the majority, it is time to {BLANK}.", "pause", "Mark Twain"),
    ("Worrying is like paying a {BLANK} you don't owe.", "debt", "Mark Twain"),
    ("If you don't read the newspaper you are uninformed. If you do, you are {BLANK}.", "misinformed", "Mark Twain"),
    ("Kindness is a language the deaf can hear and the blind can {BLANK}.", "see", "Mark Twain"),
    ("It's not the size of the dog in the fight; it's the size of the {BLANK} in the dog.", "fight", "Mark Twain"),
    ("Clothes make the man. Naked people have little or no influence in {BLANK}.", "society", "Mark Twain"),
    ("The two most important days in your life: the day you are born and the day you find out {BLANK}.", "why", "Mark Twain"),

    # ── Albert Einstein ───────────────────────────────────────────────────────
    ("Two things are infinite: the universe and human {BLANK}.", "stupidity", "Albert Einstein"),
    ("In the middle of difficulty lies {BLANK}.", "opportunity", "Albert Einstein"),
    ("Life is like riding a bicycle. To keep your balance you must keep {BLANK}.", "moving", "Albert Einstein"),
    ("Imagination is more important than {BLANK}.", "knowledge", "Albert Einstein"),
    ("The measure of intelligence is the ability to {BLANK}.", "change", "Albert Einstein"),
    ("Insanity is doing the same thing over and over and expecting different {BLANK}.", "results", "Albert Einstein"),
    ("The world as we have created it is a process of our {BLANK}.", "thinking", "Albert Einstein"),
    ("I have no special talent. I am only passionately {BLANK}.", "curious", "Albert Einstein"),
    ("Creativity is intelligence having {BLANK}.", "fun", "Albert Einstein"),
    ("Science without religion is lame, religion without science is {BLANK}.", "blind", "Albert Einstein"),
    ("If you can't explain it simply, you don't understand it well {BLANK}.", "enough", "Albert Einstein"),
    ("Try not to become a man of success, but rather a man of {BLANK}.", "value", "Albert Einstein"),
    ("Logic will get you from A to Z; {BLANK} will get you everywhere.", "imagination", "Albert Einstein"),
    ("Not everything that can be counted counts, and not everything that counts can be {BLANK}.", "counted", "Albert Einstein"),
    ("A person who never made a mistake never tried anything {BLANK}.", "new", "Albert Einstein"),
    ("I have no special talents. I am only passionately {BLANK}.", "curious", "Albert Einstein"),

    # ── Winston Churchill ─────────────────────────────────────────────────────
    ("Success is stumbling from failure to failure with no loss of {BLANK}.", "enthusiasm", "Winston Churchill"),
    ("Success is not final, failure is not fatal: it is the courage to continue that {BLANK}.", "counts", "Winston Churchill"),
    ("If you're going through hell, keep {BLANK}.", "going", "Winston Churchill"),
    ("To improve is to change; to be perfect is to change {BLANK}.", "often", "Winston Churchill"),
    ("The price of greatness is {BLANK}.", "responsibility", "Winston Churchill"),
    ("We make a living by what we get, but we make a life by what we {BLANK}.", "give", "Winston Churchill"),
    ("Courage is what it takes to stand up and speak; it's also what it takes to sit down and {BLANK}.", "listen", "Winston Churchill"),
    ("A lie gets halfway around the world before the {BLANK} has a chance to get its pants on.", "truth", "Winston Churchill"),
    ("History will be kind to me for I intend to {BLANK} it.", "write", "Winston Churchill"),
    ("Success consists of going from failure to failure without loss of {BLANK}.", "enthusiasm", "Winston Churchill"),
    ("We shall never {BLANK}.", "surrender", "Winston Churchill"),
    ("Attitude is a little thing that makes a big {BLANK}.", "difference", "Winston Churchill"),
    ("Tact is the ability to tell someone to go to hell in such a way that they look forward to the {BLANK}.", "trip", "Winston Churchill"),

    # ── Abraham Lincoln ───────────────────────────────────────────────────────
    ("Better to remain silent and be thought a fool than to speak out and remove all {BLANK}.", "doubt", "Abraham Lincoln"),
    ("Give me six hours to chop down a tree and I will spend the first four sharpening the {BLANK}.", "axe", "Abraham Lincoln"),
    ("In the end, it's not the years in your life that count. It's the life in your {BLANK}.", "years", "Abraham Lincoln"),
    ("No man has a good enough memory to be a successful {BLANK}.", "liar", "Abraham Lincoln"),
    ("I am a slow walker, but I never walk {BLANK}.", "back", "Abraham Lincoln"),
    ("The ballot is stronger than the {BLANK}.", "bullet", "Abraham Lincoln"),
    ("Whatever you are, be a good {BLANK}.", "one", "Abraham Lincoln"),
    ("I destroy my enemies when I make them my {BLANK}.", "friends", "Abraham Lincoln"),
    ("Give me six hours to chop a tree, I'll spend four sharpening the {BLANK}.", "axe", "Abraham Lincoln"),

    # ── Benjamin Franklin ─────────────────────────────────────────────────────
    ("An investment in knowledge pays the best {BLANK}.", "interest", "Benjamin Franklin"),
    ("Well done is better than well {BLANK}.", "said", "Benjamin Franklin"),
    ("Early to bed and early to rise makes a man healthy, wealthy, and {BLANK}.", "wise", "Benjamin Franklin"),
    ("By failing to prepare, you are preparing to {BLANK}.", "fail", "Benjamin Franklin"),
    ("In this world, nothing is certain except death and {BLANK}.", "taxes", "Benjamin Franklin"),
    ("Three may keep a secret, if two of them are {BLANK}.", "dead", "Benjamin Franklin"),
    ("Lost time is never found {BLANK}.", "again", "Benjamin Franklin"),
    ("Either write something worth reading or do something worth {BLANK}.", "writing", "Benjamin Franklin"),
    ("Tell me and I forget, teach me and I may remember, involve me and I {BLANK}.", "learn", "Benjamin Franklin"),
    ("Whatever is begun in anger ends in {BLANK}.", "shame", "Benjamin Franklin"),

    # ── Mahatma Gandhi ────────────────────────────────────────────────────────
    ("Be the change you wish to see in the {BLANK}.", "world", "Mahatma Gandhi"),
    ("First they ignore you, then they laugh at you, then they fight you, then you {BLANK}.", "win", "Mahatma Gandhi"),
    ("An eye for an eye will make the whole world {BLANK}.", "blind", "Mahatma Gandhi"),
    ("The weak can never {BLANK}. Forgiveness is the attribute of the strong.", "forgive", "Mahatma Gandhi"),
    ("Strength does not come from physical capacity. It comes from an indomitable {BLANK}.", "will", "Mahatma Gandhi"),
    ("Be the change that you wish to see in the {BLANK}.", "world", "Mahatma Gandhi"),
    ("Live as if you were to die tomorrow. Learn as if you were to live {BLANK}.", "forever", "Mahatma Gandhi"),

    # ── Theodore Roosevelt ────────────────────────────────────────────────────
    ("Do what you can, with what you have, where you {BLANK}.", "are", "Theodore Roosevelt"),
    ("Speak softly and carry a big {BLANK}.", "stick", "Theodore Roosevelt"),
    ("Keep your eyes on the stars, and your feet on the {BLANK}.", "ground", "Theodore Roosevelt"),
    ("Believe you can and you're {BLANK} there.", "halfway", "Theodore Roosevelt"),
    ("It is hard to fail, but it is worse never to have {BLANK}.", "tried", "Theodore Roosevelt"),
    ("Comparison is the thief of {BLANK}.", "joy", "Theodore Roosevelt"),

    # ── Eleanor Roosevelt ─────────────────────────────────────────────────────
    ("No one can make you feel inferior without your {BLANK}.", "consent", "Eleanor Roosevelt"),
    ("The future belongs to those who believe in the beauty of their {BLANK}.", "dreams", "Eleanor Roosevelt"),
    ("Great minds discuss ideas; average minds discuss events; small minds discuss {BLANK}.", "people", "Eleanor Roosevelt"),
    ("It is not fair to ask of others what you are not willing to do {BLANK}.", "yourself", "Eleanor Roosevelt"),
    ("Beautiful young people are accidents of nature, but beautiful old people are works of {BLANK}.", "art", "Eleanor Roosevelt"),
    ("The purpose of life, after all, is to live it and to taste experience to the utmost.", "experience", "Eleanor Roosevelt"),

    # ── Maya Angelou ──────────────────────────────────────────────────────────
    ("You will face many defeats in life, but never let yourself be {BLANK}.", "defeated", "Maya Angelou"),
    ("If you don't like something, change it. If you can't change it, change your {BLANK}.", "attitude", "Maya Angelou"),
    ("A bird doesn't sing because it has an answer, it sings because it has a {BLANK}.", "song", "Maya Angelou"),
    ("I've learned that people will never forget how you made them {BLANK}.", "feel", "Maya Angelou"),
    ("Nothing will work unless you {BLANK}.", "do", "Maya Angelou"),
    ("We delight in the beauty of the butterfly, but rarely admit the changes it has gone through.", "changes", "Maya Angelou"),

    # ── Nelson Mandela ────────────────────────────────────────────────────────
    ("It always seems impossible until it's {BLANK}.", "done", "Nelson Mandela"),
    ("Education is the most powerful weapon you can use to change the {BLANK}.", "world", "Nelson Mandela"),
    ("Resentment is like drinking poison and hoping it will kill your {BLANK}.", "enemies", "Nelson Mandela"),
    ("I learned that courage was not the absence of fear, but the {BLANK} over it.", "triumph", "Nelson Mandela"),
    ("A winner is a {BLANK} who never gives up.", "dreamer", "Nelson Mandela"),
    ("May your choices reflect your hopes, not your {BLANK}.", "fears", "Nelson Mandela"),

    # ── Martin Luther King Jr. ────────────────────────────────────────────────
    ("Darkness cannot drive out darkness; only {BLANK} can do that.", "light", "Martin Luther King Jr."),
    ("Injustice anywhere is a threat to justice {BLANK}.", "everywhere", "Martin Luther King Jr."),
    ("The time is always right to do what is {BLANK}.", "right", "Martin Luther King Jr."),
    ("If you can't fly then run, if you can't run then walk, if you can't walk then {BLANK}.", "crawl", "Martin Luther King Jr."),
    ("Life's most persistent question is: what are you doing for {BLANK}?", "others", "Martin Luther King Jr."),
    ("Faith is taking the first step even when you don't see the whole {BLANK}.", "staircase", "Martin Luther King Jr."),
    ("Intelligence plus character — that is the goal of true {BLANK}.", "education", "Martin Luther King Jr."),
    ("We must accept finite disappointment, but never lose infinite {BLANK}.", "hope", "Martin Luther King Jr."),

    # ── John F. Kennedy ───────────────────────────────────────────────────────
    ("Ask not what your country can do for you — ask what you can do for your {BLANK}.", "country", "John F. Kennedy"),
    ("Efforts and courage are not enough without purpose and {BLANK}.", "direction", "John F. Kennedy"),
    ("Change is the law of life, and those who look only to the past are certain to miss the {BLANK}.", "future", "John F. Kennedy"),
    ("The best road to progress is freedom's {BLANK}.", "road", "John F. Kennedy"),

    # ── William Shakespeare ───────────────────────────────────────────────────
    ("To be or not to be, that is the {BLANK}.", "question", "William Shakespeare"),
    ("All the world's a stage, and all the men and women merely {BLANK}.", "players", "William Shakespeare"),
    ("{BLANK} die many times before their deaths; the valiant never taste of death but once.", "Cowards", "William Shakespeare"),
    ("The course of true love never did run {BLANK}.", "smooth", "William Shakespeare"),
    ("Brevity is the soul of {BLANK}.", "wit", "William Shakespeare"),
    ("What's in a name? That which we call a rose by any other name would smell as {BLANK}.", "sweet", "William Shakespeare"),
    ("This above all: to thine own self be {BLANK}.", "true", "William Shakespeare"),
    ("The lady doth protest too {BLANK}, methinks.", "much", "William Shakespeare"),
    ("Uneasy lies the head that wears a {BLANK}.", "crown", "William Shakespeare"),
    ("We are such stuff as dreams are made on, and our little life is rounded with a {BLANK}.", "sleep", "William Shakespeare"),
    ("How sharper than a serpent's tooth it is to have a thankless {BLANK}.", "child", "William Shakespeare"),
    ("The quality of mercy is not {BLANK}.", "strained", "William Shakespeare"),
    ("Good night, good night! Parting is such sweet {BLANK}.", "sorrow", "William Shakespeare"),
    ("Love all, trust a few, do wrong to {BLANK}.", "none", "William Shakespeare"),

    # ── Confucius ─────────────────────────────────────────────────────────────
    ("Choose a job you love, and you will never have to work a day in your {BLANK}.", "life", "Confucius"),
    ("It does not matter how slowly you go as long as you do not {BLANK}.", "stop", "Confucius"),
    ("Our greatest glory is not in never falling, but in rising every time we {BLANK}.", "fall", "Confucius"),
    ("Life is really simple, but we insist on making it {BLANK}.", "complicated", "Confucius"),
    ("Before you embark on a journey of revenge, dig two {BLANK}.", "graves", "Confucius"),
    ("Real knowledge is to know the extent of one's {BLANK}.", "ignorance", "Confucius"),
    ("I hear and I forget. I see and I remember. I do and I {BLANK}.", "understand", "Confucius"),
    ("Wisdom, compassion, and courage are the three universally recognized moral qualities of {BLANK}.", "men", "Confucius"),

    # ── Aristotle ─────────────────────────────────────────────────────────────
    ("Happiness depends upon {BLANK}.", "ourselves", "Aristotle"),
    ("Knowing yourself is the beginning of all {BLANK}.", "wisdom", "Aristotle"),
    ("We are what we repeatedly do. Excellence, then, is not an act, but a {BLANK}.", "habit", "Aristotle"),
    ("The secret to humor is {BLANK}.", "surprise", "Aristotle"),
    ("No great mind has ever existed without a touch of {BLANK}.", "madness", "Aristotle"),
    ("Whosoever is delighted in solitude is either a wild beast or a {BLANK}.", "god", "Aristotle"),
    ("Count your age by friends, not years. Count your life by smiles, not {BLANK}.", "tears", "Aristotle"),

    # ── Socrates ──────────────────────────────────────────────────────────────
    ("An unexamined life is not worth {BLANK}.", "living", "Socrates"),
    ("The only true wisdom is in knowing you know {BLANK}.", "nothing", "Socrates"),
    ("Be kind, for everyone you meet is fighting a harder {BLANK}.", "battle", "Socrates"),
    ("Wonder is the beginning of {BLANK}.", "wisdom", "Socrates"),

    # ── Plato ─────────────────────────────────────────────────────────────────
    ("Wise men speak because they have something to say; fools because they have to say {BLANK}.", "something", "Plato"),
    ("The price good men pay for indifference to public affairs is to be ruled by evil {BLANK}.", "men", "Plato"),
    ("Courage is knowing what not to {BLANK}.", "fear", "Plato"),

    # ── Friedrich Nietzsche ───────────────────────────────────────────────────
    ("That which does not kill us makes us {BLANK}.", "stronger", "Friedrich Nietzsche"),
    ("Without music, life would be a {BLANK}.", "mistake", "Friedrich Nietzsche"),
    ("The higher we soar, the smaller we appear to those who cannot {BLANK}.", "fly", "Friedrich Nietzsche"),
    ("It is not a lack of love, but a lack of {BLANK} that makes unhappy marriages.", "friendship", "Friedrich Nietzsche"),
    ("In individuals, insanity is rare; but in groups it is the {BLANK}.", "rule", "Friedrich Nietzsche"),
    ("He who has a why to live can bear almost any {BLANK}.", "how", "Friedrich Nietzsche"),

    # ── Lao Tzu ───────────────────────────────────────────────────────────────
    ("A journey of a thousand miles begins with a single {BLANK}.", "step", "Lao Tzu"),
    ("Nature does not hurry, yet everything is {BLANK}.", "accomplished", "Lao Tzu"),
    ("Mastering others is strength; mastering yourself is true {BLANK}.", "power", "Lao Tzu"),
    ("He who knows others is wise; he who knows himself is {BLANK}.", "enlightened", "Lao Tzu"),

    # ── Sun Tzu ───────────────────────────────────────────────────────────────
    ("Appear weak when you are strong, and strong when you are {BLANK}.", "weak", "Sun Tzu"),
    ("In the midst of chaos, there is also {BLANK}.", "opportunity", "Sun Tzu"),
    ("The supreme art of war is to subdue the enemy without {BLANK}.", "fighting", "Sun Tzu"),

    # ── Marcus Aurelius ───────────────────────────────────────────────────────
    ("You have power over your mind, not outside events. Realize this, and you will find {BLANK}.", "strength", "Marcus Aurelius"),
    ("The happiness of your life depends upon the quality of your {BLANK}.", "thoughts", "Marcus Aurelius"),
    ("Very little is needed to make a happy life; it is all within yourself, in your way of {BLANK}.", "thinking", "Marcus Aurelius"),
    ("Reject your sense of injury and the injury itself {BLANK}.", "disappears", "Marcus Aurelius"),
    ("If it is not right, do not do it; if it is not true, do not {BLANK} it.", "say", "Marcus Aurelius"),

    # ── Seneca ────────────────────────────────────────────────────────────────
    ("We suffer more in {BLANK} than in reality.", "imagination", "Seneca"),
    ("Luck is what happens when preparation meets {BLANK}.", "opportunity", "Seneca"),
    ("Difficulties strengthen the mind, as labor does the {BLANK}.", "body", "Seneca"),
    ("It is not the man who has too little, but the man who craves {BLANK}, that is poor.", "more", "Seneca"),

    # ── Epictetus ─────────────────────────────────────────────────────────────
    ("It's not what happens to you, but how you react to it that {BLANK}.", "matters", "Epictetus"),
    ("Seek not the good in external things; seek it in {BLANK}.", "yourself", "Epictetus"),

    # ── Voltaire ──────────────────────────────────────────────────────────────
    ("Common sense is not so {BLANK}.", "common", "Voltaire"),
    ("Judge a man by his questions rather than his {BLANK}.", "answers", "Voltaire"),
    ("God is a comedian playing to an audience too afraid to {BLANK}.", "laugh", "Voltaire"),
    ("The perfect is the enemy of the {BLANK}.", "good", "Voltaire"),
    ("It is dangerous to be right when the government is {BLANK}.", "wrong", "Voltaire"),
    ("God gave us the gift of life; it is up to us to give ourselves the gift of living {BLANK}.", "well", "Voltaire"),

    # ── Ralph Waldo Emerson ───────────────────────────────────────────────────
    ("Do not go where the path may lead; go instead where there is no path and leave a {BLANK}.", "trail", "Ralph Waldo Emerson"),
    ("To be yourself in a world that is constantly trying to make you something else is the greatest {BLANK}.", "accomplishment", "Ralph Waldo Emerson"),
    ("Every artist was first an {BLANK}.", "amateur", "Ralph Waldo Emerson"),
    ("What lies behind us and what lies before us are tiny matters compared to what lies within {BLANK}.", "us", "Ralph Waldo Emerson"),
    ("In every walk with nature, one receives far more than he {BLANK}.", "seeks", "Ralph Waldo Emerson"),

    # ── Henry David Thoreau ───────────────────────────────────────────────────
    ("Go confidently in the direction of your {BLANK}. Live the life you have imagined.", "dreams", "Henry David Thoreau"),
    ("I went to the woods because I wished to live {BLANK}.", "deliberately", "Henry David Thoreau"),
    ("Not all those who wander are {BLANK}.", "lost", "J.R.R. Tolkien"),

    # ── Victor Hugo ───────────────────────────────────────────────────────────
    ("Even the darkest night will end and the sun will {BLANK}.", "rise", "Victor Hugo"),
    ("Laughter is the sun that drives {BLANK} from the human face.", "winter", "Victor Hugo"),
    ("He who opens a school door, closes a {BLANK}.", "prison", "Victor Hugo"),
    ("There is nothing more powerful than an idea whose time has {BLANK}.", "come", "Victor Hugo"),

    # ── Albert Camus ──────────────────────────────────────────────────────────
    ("In the depths of winter, I finally learned that within me there lay an invincible {BLANK}.", "summer", "Albert Camus"),
    ("The only way to deal with an unfree world is to become so absolutely free your existence is an act of {BLANK}.", "rebellion", "Albert Camus"),

    # ── Jean-Paul Sartre ──────────────────────────────────────────────────────
    ("We are our {BLANK}.", "choices", "Jean-Paul Sartre"),
    ("Hell is — other {BLANK}.", "people", "Jean-Paul Sartre"),

    # ── Bertrand Russell ──────────────────────────────────────────────────────
    ("The good life is one inspired by love and guided by {BLANK}.", "knowledge", "Bertrand Russell"),
    ("The whole problem with the world is that fools are always so certain and wiser people so full of {BLANK}.", "doubts", "Bertrand Russell"),

    # ── Groucho Marx ──────────────────────────────────────────────────────────
    ("I find television very educational. Every time someone turns it on, I go read a {BLANK}.", "book", "Groucho Marx"),
    ("Outside of a dog, a book is man's best friend. Inside of a dog, it's too dark to {BLANK}.", "read", "Groucho Marx"),
    ("I never forget a face, but in your case I'll be glad to make an {BLANK}.", "exception", "Groucho Marx"),
    ("I refuse to join any club that would have me as a {BLANK}.", "member", "Groucho Marx"),
    ("The secret of life is honesty and fair dealing. If you can fake that, you've got it {BLANK}.", "made", "Groucho Marx"),
    ("Time flies like an arrow; fruit flies like a {BLANK}.", "banana", "Groucho Marx"),
    ("I intend to live forever, or die {BLANK}.", "trying", "Groucho Marx"),
    ("Getting older is no problem. You just have to live long {BLANK}.", "enough", "Groucho Marx"),
    ("I've had a perfectly wonderful evening, but this wasn't {BLANK}.", "it", "Groucho Marx"),
    ("Those are my principles, and if you don't like them... well, I have {BLANK}.", "others", "Groucho Marx"),

    # ── Woody Allen ───────────────────────────────────────────────────────────
    ("If you want to make God laugh, tell him about your {BLANK}.", "plans", "Woody Allen"),
    ("I am not afraid of death, I just don't want to be there when it {BLANK}.", "happens", "Woody Allen"),
    ("I don't want to achieve immortality through my work. I want to achieve it through not {BLANK}.", "dying", "Woody Allen"),
    ("Eighty percent of success is showing {BLANK}.", "up", "Woody Allen"),

    # ── Will Rogers ───────────────────────────────────────────────────────────
    ("Even if you're on the right track, you'll get run over if you just sit {BLANK}.", "there", "Will Rogers"),
    ("Too many people spend money they haven't earned to buy things they don't want to impress people they don't {BLANK}.", "like", "Will Rogers"),
    ("Everything is funny, as long as it's happening to {BLANK}.", "someone", "Will Rogers"),
    ("The trouble with practical jokes is that very often they get {BLANK}.", "elected", "Will Rogers"),

    # ── Yogi Berra ────────────────────────────────────────────────────────────
    ("It ain't over till it's {BLANK}.", "over", "Yogi Berra"),
    ("You can observe a lot by just {BLANK}.", "watching", "Yogi Berra"),
    ("I never said most of the things I {BLANK}.", "said", "Yogi Berra"),
    ("It's like déjà vu all over {BLANK}.", "again", "Yogi Berra"),
    ("When you come to a fork in the road, {BLANK} it.", "take", "Yogi Berra"),
    ("The future ain't what it used to {BLANK}.", "be", "Yogi Berra"),

    # ── George Bernard Shaw ───────────────────────────────────────────────────
    ("Life is not about finding yourself. Life is about creating {BLANK}.", "yourself", "George Bernard Shaw"),
    ("A life spent making mistakes is more honorable than a life spent doing {BLANK}.", "nothing", "George Bernard Shaw"),
    ("Progress is impossible without change, and those who cannot change their minds cannot change {BLANK}.", "anything", "George Bernard Shaw"),
    ("Youth is wasted on the {BLANK}.", "young", "George Bernard Shaw"),
    ("If you cannot get rid of the family skeleton, you may as well make it {BLANK}.", "dance", "George Bernard Shaw"),
    ("Two percent of the people think; three percent think they think; the rest would rather die than {BLANK}.", "think", "George Bernard Shaw"),

    # ── Helen Keller ──────────────────────────────────────────────────────────
    ("Life is either a daring adventure or {BLANK}.", "nothing", "Helen Keller"),
    ("Alone we can do so little; together we can do so {BLANK}.", "much", "Helen Keller"),
    ("Optimism is the faith that leads to {BLANK}.", "achievement", "Helen Keller"),
    ("The only thing worse than being blind is having sight but no {BLANK}.", "vision", "Helen Keller"),
    ("The best and most beautiful things cannot be seen or touched — they must be felt with the {BLANK}.", "heart", "Helen Keller"),

    # ── Steve Jobs ────────────────────────────────────────────────────────────
    ("Stay hungry, stay {BLANK}.", "foolish", "Steve Jobs"),
    ("Innovation distinguishes between a leader and a {BLANK}.", "follower", "Steve Jobs"),
    ("Design is not just what it looks like. Design is how it {BLANK}.", "works", "Steve Jobs"),
    ("Your time is limited, so don't waste it living someone else's {BLANK}.", "life", "Steve Jobs"),
    ("Have the courage to follow your heart and {BLANK}.", "intuition", "Steve Jobs"),

    # ── Warren Buffett ────────────────────────────────────────────────────────
    ("Price is what you pay. {BLANK} is what you get.", "Value", "Warren Buffett"),
    ("Risk comes from not knowing what you're {BLANK}.", "doing", "Warren Buffett"),
    ("It takes 20 years to build a reputation and five minutes to ruin it.", "reputation", "Warren Buffett"),

    # ── Henry Ford ────────────────────────────────────────────────────────────
    ("Whether you think you can, or you think you can't — you're {BLANK}.", "right", "Henry Ford"),
    ("Coming together is a beginning; keeping together is progress; working together is {BLANK}.", "success", "Henry Ford"),
    ("Failure is simply the opportunity to begin again, this time more {BLANK}.", "intelligently", "Henry Ford"),
    ("Anyone who stops learning is old, whether twenty or eighty. Anyone who keeps learning stays {BLANK}.", "young", "Henry Ford"),

    # ── Thomas Edison ─────────────────────────────────────────────────────────
    ("Genius is one percent inspiration and ninety-nine percent {BLANK}.", "perspiration", "Thomas Edison"),
    ("I have not failed. I've just found 10,000 ways that won't {BLANK}.", "work", "Thomas Edison"),
    ("Many fail because they don't realize how close they were to {BLANK} when they gave up.", "success", "Thomas Edison"),
    ("Opportunity is missed by most because it looks like hard {BLANK}.", "work", "Thomas Edison"),

    # ── Marie Curie ───────────────────────────────────────────────────────────
    ("Nothing in life is to be feared, it is only to be {BLANK}.", "understood", "Marie Curie"),
    ("Be less curious about people and more curious about {BLANK}.", "ideas", "Marie Curie"),
    ("I was taught that the way of progress is neither swift nor {BLANK}.", "easy", "Marie Curie"),

    # ── Carl Sagan ────────────────────────────────────────────────────────────
    ("Somewhere, something incredible is waiting to be {BLANK}.", "known", "Carl Sagan"),
    ("We are made of star {BLANK}.", "stuff", "Carl Sagan"),
    ("Extraordinary claims require extraordinary {BLANK}.", "evidence", "Carl Sagan"),

    # ── Richard Feynman ───────────────────────────────────────────────────────
    ("The first principle is that you must not fool yourself — and you are the easiest person to {BLANK}.", "fool", "Richard Feynman"),
    ("I would rather have questions that can't be answered than answers that can't be {BLANK}.", "questioned", "Richard Feynman"),

    # ── Charles Darwin ────────────────────────────────────────────────────────
    ("It is not the strongest that survive, nor the most intelligent, but the most responsive to {BLANK}.", "change", "Charles Darwin"),
    ("A man who dares to waste one hour of time has not discovered the value of {BLANK}.", "life", "Charles Darwin"),

    # ── Isaac Newton ──────────────────────────────────────────────────────────
    ("If I have seen further, it is by standing on the shoulders of {BLANK}.", "giants", "Isaac Newton"),
    ("What we know is a drop; what we don't know is an {BLANK}.", "ocean", "Isaac Newton"),

    # ── Nikola Tesla ──────────────────────────────────────────────────────────
    ("The present is theirs; the future, for which I really worked, is {BLANK}.", "mine", "Nikola Tesla"),
    ("If you want to find the secrets of the universe, think in terms of energy, frequency and {BLANK}.", "vibration", "Nikola Tesla"),

    # ── Napoleon Bonaparte ────────────────────────────────────────────────────
    ("Impossible is a word to be found only in the dictionary of {BLANK}.", "fools", "Napoleon Bonaparte"),
    ("Never interrupt your enemy when he is making a {BLANK}.", "mistake", "Napoleon Bonaparte"),
    ("A leader is a dealer in {BLANK}.", "hope", "Napoleon Bonaparte"),
    ("I came, I saw, I {BLANK}.", "conquered", "Julius Caesar"),

    # ── Rumi ──────────────────────────────────────────────────────────────────
    ("Yesterday I was clever, so I wanted to change the world. Today I am wise, so I am changing {BLANK}.", "myself", "Rumi"),
    ("The wound is the place where the light enters {BLANK}.", "you", "Rumi"),
    ("Don't grieve. Anything you lose comes round in another {BLANK}.", "form", "Rumi"),
    ("Raise your words, not your {BLANK}. It is rain that grows flowers, not thunder.", "voice", "Rumi"),
    ("Let yourself be silently drawn by the strange pull of what you really {BLANK}.", "love", "Rumi"),

    # ── Khalil Gibran ─────────────────────────────────────────────────────────
    ("Out of suffering have emerged the strongest {BLANK}.", "souls", "Khalil Gibran"),
    ("Your children are not your children. They are Life's longing for {BLANK}.", "itself", "Khalil Gibran"),

    # ── Dalai Lama ────────────────────────────────────────────────────────────
    ("Happiness is not something ready-made. It comes from your own {BLANK}.", "actions", "Dalai Lama"),
    ("If you want others to be happy, practice compassion. If you want to be happy, practice {BLANK}.", "compassion", "Dalai Lama"),
    ("Remember that not getting what you want is sometimes a wonderful stroke of {BLANK}.", "luck", "Dalai Lama"),
    ("If you think you are too small to make a difference, try sleeping with a {BLANK}.", "mosquito", "Dalai Lama"),

    # ── Paulo Coelho ──────────────────────────────────────────────────────────
    ("There is only one thing that makes a dream impossible to achieve: the fear of {BLANK}.", "failure", "Paulo Coelho"),
    ("The secret of life, though, is to fall seven times and to get up eight {BLANK}.", "times", "Paulo Coelho"),

    # ── Carl Jung ─────────────────────────────────────────────────────────────
    ("Who looks outside, dreams; who looks inside, {BLANK}.", "awakes", "Carl Jung"),
    ("You are what you do, not what you say you'll {BLANK}.", "do", "Carl Jung"),

    # ── George Carlin ─────────────────────────────────────────────────────────
    ("The reason I talk to myself is that I'm the only one whose answers I {BLANK}.", "accept", "George Carlin"),
    ("Some people see the glass half full. Others see it half {BLANK}.", "empty", "George Carlin"),
    ("Have you ever noticed anyone going faster than you is a maniac and slower is an {BLANK}?", "idiot", "George Carlin"),
    ("Weather forecast for tonight: {BLANK}.", "dark", "George Carlin"),
    ("Inside every cynical person is a disappointed {BLANK}.", "idealist", "George Carlin"),

    # ── Steven Wright ─────────────────────────────────────────────────────────
    ("I intend to live forever. So far, so {BLANK}.", "good", "Steven Wright"),
    ("A clear conscience is usually the sign of a bad {BLANK}.", "memory", "Steven Wright"),
    ("I used to think I was indecisive, but now I'm not so {BLANK}.", "sure", "Steven Wright"),
    ("Everywhere is within walking distance if you have the {BLANK}.", "time", "Steven Wright"),
    ("If at first you don't succeed, then skydiving definitely isn't for {BLANK}.", "you", "Steven Wright"),

    # ── Mitch Hedberg ─────────────────────────────────────────────────────────
    ("I'm sick of following my dreams. I'm just going to ask where they're going and hook up with them {BLANK}.", "later", "Mitch Hedberg"),
    ("Rice is great if you're really hungry and want to eat two thousand of {BLANK}.", "something", "Mitch Hedberg"),

    # ── Rodney Dangerfield ────────────────────────────────────────────────────
    ("I told my doctor I broke my arm in two places. He told me to quit going to those {BLANK}.", "places", "Rodney Dangerfield"),
    ("My doctor told me to watch my drinking. Now I drink in front of a {BLANK}.", "mirror", "Rodney Dangerfield"),
    ("I get no respect. If I was a politician, my luck is I'd be {BLANK}.", "honest", "Rodney Dangerfield"),

    # ── Bob Hope ──────────────────────────────────────────────────────────────
    ("A bank is a place that will lend you money if you can prove that you don't {BLANK} it.", "need", "Bob Hope"),

    # ── Henny Youngman ────────────────────────────────────────────────────────
    ("Take my wife... {BLANK}.", "please", "Henny Youngman"),
    ("If you had your life to live over, you'd need more {BLANK}.", "money", "Henny Youngman"),

    # ── Dorothy Parker ────────────────────────────────────────────────────────
    ("What fresh hell is {BLANK}?", "this", "Dorothy Parker"),
    ("I don't care what is written about me so long as it isn't {BLANK}.", "true", "Dorothy Parker"),
    ("The cure for boredom is {BLANK}. There is no cure for curiosity.", "curiosity", "Dorothy Parker"),

    # ── Joan Rivers ───────────────────────────────────────────────────────────
    ("I enjoy life when things are happening. I don't care if it's good or bad. That means I'm {BLANK}.", "alive", "Joan Rivers"),
    ("Age is just a number. It's totally irrelevant unless you happen to be a bottle of {BLANK}.", "wine", "Joan Rivers"),

    # ── Phyllis Diller ────────────────────────────────────────────────────────
    ("A smile is a curve that sets everything {BLANK}.", "straight", "Phyllis Diller"),
    ("The reason women don't play football is because eleven of them would never wear the same outfit in {BLANK}.", "public", "Phyllis Diller"),

    # ── Robert Frost ──────────────────────────────────────────────────────────
    ("Two roads diverged in a wood, and I — I took the one less {BLANK}.", "traveled", "Robert Frost"),
    ("In three words I can sum up everything I've learned about life: it goes {BLANK}.", "on", "Robert Frost"),

    # ── Charles Dickens ───────────────────────────────────────────────────────
    ("It was the best of times, it was the worst of {BLANK}.", "times", "Charles Dickens"),
    ("No one is useless in this world who lightens the {BLANK} of another.", "burdens", "Charles Dickens"),
    ("My advice is to never do tomorrow what you can do today. Procrastination is the thief of {BLANK}.", "time", "Charles Dickens"),

    # ── Jane Austen ───────────────────────────────────────────────────────────
    ("The person who has not pleasure in a good novel must be intolerably {BLANK}.", "stupid", "Jane Austen"),
    ("It is a truth universally acknowledged, that a single man in possession of a good fortune must be in want of a {BLANK}.", "wife", "Jane Austen"),

    # ── F. Scott Fitzgerald ───────────────────────────────────────────────────
    ("Never confuse a single defeat with a final {BLANK}.", "defeat", "F. Scott Fitzgerald"),
    ("So we beat on, boats against the current, borne back ceaselessly into the {BLANK}.", "past", "F. Scott Fitzgerald"),

    # ── Ernest Hemingway ──────────────────────────────────────────────────────
    ("The world breaks everyone, and afterward, some are strong at the broken {BLANK}.", "places", "Ernest Hemingway"),
    ("There is no friend as loyal as a {BLANK}.", "book", "Ernest Hemingway"),
    ("Courage is grace under {BLANK}.", "pressure", "Ernest Hemingway"),
    ("The first draft of anything is {BLANK}.", "garbage", "Ernest Hemingway"),

    # ── Virginia Woolf ────────────────────────────────────────────────────────
    ("You cannot find peace by avoiding {BLANK}.", "life", "Virginia Woolf"),
    ("One cannot think well, love well, sleep well, if one has not {BLANK} well.", "dined", "Virginia Woolf"),

    # ── John Steinbeck ────────────────────────────────────────────────────────
    ("A journey is a person in itself; no two are {BLANK}.", "alike", "John Steinbeck"),
    ("Ideas are like rabbits. You get a couple and learn how to handle them, and pretty soon you have a {BLANK}.", "dozen", "John Steinbeck"),

    # ── Kurt Vonnegut ─────────────────────────────────────────────────────────
    ("Laughter and tears are both responses to frustration and exhaustion. I prefer to {BLANK}.", "laugh", "Kurt Vonnegut"),
    ("We are what we pretend to be, so we must be careful about what we pretend to {BLANK}.", "be", "Kurt Vonnegut"),

    # ── Douglas Adams ─────────────────────────────────────────────────────────
    ("In the beginning the universe was created. This has made a lot of people very angry and been widely regarded as a bad {BLANK}.", "move", "Douglas Adams"),
    ("The answer to life, the universe and everything is {BLANK}.", "42", "Douglas Adams"),

    # ── J.K. Rowling / Dumbledore ─────────────────────────────────────────────
    ("It does not do to dwell on dreams and forget to {BLANK}.", "live", "Albus Dumbledore"),
    ("Happiness can be found even in the darkest of times, if one only remembers to turn on the {BLANK}.", "light", "Albus Dumbledore"),
    ("It is our choices that show what we truly are, far more than our {BLANK}.", "abilities", "Albus Dumbledore"),

    # ── Star Wars / Pop Culture ───────────────────────────────────────────────
    ("Do or do not. There is no {BLANK}.", "try", "Yoda"),
    ("I'm gonna make him an offer he can't {BLANK}.", "refuse", "The Godfather"),
    ("You can't handle the {BLANK}.", "truth", "A Few Good Men"),
    ("To infinity and {BLANK}.", "beyond", "Buzz Lightyear"),
    ("There's no place like {BLANK}.", "home", "The Wizard of Oz"),
    ("With great power comes great {BLANK}.", "responsibility", "Spider-Man"),
    ("The greatest trick the devil ever pulled was convincing the world he didn't {BLANK}.", "exist", "The Usual Suspects"),
    ("Houston, we have a {BLANK}.", "problem", "Apollo 13"),
    ("Just keep {BLANK}.", "swimming", "Finding Nemo"),
    ("I am not in danger. I am the {BLANK}.", "danger", "Breaking Bad"),
    ("Elementary, my dear {BLANK}.", "Watson", "Sherlock Holmes"),
    ("I'll be {BLANK}.", "back", "The Terminator"),

    # ── Muhammad Ali ──────────────────────────────────────────────────────────
    ("Float like a butterfly, sting like a {BLANK}.", "bee", "Muhammad Ali"),
    ("I am the greatest. I said that even before I knew I {BLANK}.", "was", "Muhammad Ali"),
    ("Don't count the days; make the days {BLANK}.", "count", "Muhammad Ali"),
    ("Impossible is not a fact. It's an {BLANK}.", "opinion", "Muhammad Ali"),
    ("Service to others is the rent you pay for your room here on {BLANK}.", "earth", "Muhammad Ali"),

    # ── Sports figures ────────────────────────────────────────────────────────
    ("You miss 100% of the shots you don't {BLANK}.", "take", "Wayne Gretzky"),
    ("Hard work beats talent when talent doesn't work {BLANK}.", "hard", "Tim Notke"),
    ("Champions keep playing until they get it {BLANK}.", "right", "Billie Jean King"),
    ("Pain is temporary. Quitting lasts {BLANK}.", "forever", "Lance Armstrong"),
    ("It ain't about how hard you hit. It's about how hard you can get hit and keep moving {BLANK}.", "forward", "Rocky Balboa"),

    # ── Various proverbs & wisdom ─────────────────────────────────────────────
    ("A smooth sea never made a skilled {BLANK}.", "sailor", "English Proverb"),
    ("The road to hell is paved with good {BLANK}.", "intentions", "Proverb"),
    ("Actions speak louder than {BLANK}.", "words", "Proverb"),
    ("A chain is only as strong as its weakest {BLANK}.", "link", "Proverb"),
    ("You can lead a horse to water, but you can't make it {BLANK}.", "drink", "Proverb"),
    ("The early bird catches the {BLANK}.", "worm", "Proverb"),
    ("Give a man a fish, feed him for a day. Teach a man to fish, feed him for a {BLANK}.", "lifetime", "Chinese Proverb"),
    ("The nail that sticks out gets {BLANK} down.", "hammered", "Japanese Proverb"),
    ("When in Rome, do as the {BLANK} do.", "Romans", "Proverb"),
    ("May you be in heaven a full half hour before the devil knows you're {BLANK}.", "dead", "Irish Proverb"),
    ("You'll never plow a field by turning it over in your {BLANK}.", "mind", "Irish Proverb"),

    # ── Miscellaneous wisdom ──────────────────────────────────────────────────
    ("The truth will set you {BLANK}.", "free", "The Bible"),
    ("Good judgment comes from experience, and experience comes from bad {BLANK}.", "judgment", "Rita Mae Brown"),
    ("Change your thoughts and you change your {BLANK}.", "world", "Norman Vincent Peale"),
    ("Knowledge is knowing a tomato is a fruit; wisdom is not putting it in a fruit {BLANK}.", "salad", "Miles Kington"),
    ("When life gives you lemons, make {BLANK}.", "lemonade", "Elbert Hubbard"),
    ("The meaning of life is to find your gift. The purpose is to give it {BLANK}.", "away", "Pablo Picasso"),
    ("Good teaching is one-fourth preparation and three-fourths {BLANK}.", "theatre", "Gail Godwin"),
    ("The secret of happiness is not in doing what one likes, but in liking what one {BLANK}.", "does", "J.M. Barrie"),
    ("Life is a mirror: if you frown at it, it frowns back; smile and it returns the {BLANK}.", "greeting", "William Thackeray"),
    ("Every moment is a fresh {BLANK}.", "beginning", "T.S. Eliot"),
    ("Keep your face always toward the sunshine — and shadows will fall {BLANK} you.", "behind", "Walt Whitman"),
    ("When nothing goes right, go {BLANK}.", "left", "Anonymous"),
    ("Always borrow money from a pessimist. They don't expect to be paid {BLANK}.", "back", "Anonymous"),
    ("When tempted to fight fire with fire, remember that the fire department usually uses {BLANK}.", "water", "Anonymous"),
    ("The best revenge is massive {BLANK}.", "success", "Frank Sinatra"),
    ("Behind every great man is a woman rolling her {BLANK}.", "eyes", "Jim Carrey"),
    ("A day without sunshine is like, you know, {BLANK}.", "night", "Steve Martin"),
    ("You don't have to be great to start, but you have to start to be {BLANK}.", "great", "Zig Ziglar"),
    ("The best view comes after the hardest {BLANK}.", "climb", "Anonymous"),
    ("Surround yourself with only people who are going to lift you {BLANK}.", "higher", "Oprah Winfrey"),
    ("Turn your wounds into {BLANK}.", "wisdom", "Oprah Winfrey"),
    ("When they go low, we go {BLANK}.", "high", "Michelle Obama"),
    ("You become what you {BLANK}.", "believe", "Oprah Winfrey"),
    ("Be who you are and say what you feel, because those who mind don't matter and those who matter don't {BLANK}.", "mind", "Dr. Seuss"),
    ("All generalizations are false, including this {BLANK}.", "one", "Mark Twain"),
    ("The only ship that doesn't sail is {BLANK}.", "friendship", "Anonymous"),
    ("Wine is bottled {BLANK}.", "poetry", "Robert Louis Stevenson"),
    ("Act as if what you do makes a {BLANK}. It does.", "difference", "William James"),
    ("Think before you speak. Read before you {BLANK}.", "think", "Fran Lebowitz"),
    ("Food is an important part of a balanced {BLANK}.", "diet", "Fran Lebowitz"),
    ("I love criticism just so long as it's unqualified {BLANK}.", "praise", "Noel Coward"),
    ("Comedy is simply a funny way of being {BLANK}.", "serious", "Peter Ustinov"),
    ("Inaction breeds doubt and fear. Action breeds confidence and {BLANK}.", "courage", "Dale Carnegie"),
    ("Don't be afraid of enemies who attack you. Be afraid of the friends who {BLANK} you.", "flatter", "Dale Carnegie"),
    ("Whatever the mind can conceive and believe, it can {BLANK}.", "achieve", "Napoleon Hill"),
    ("We are all connected; to each other biologically, to the earth chemically, to the universe {BLANK}.", "atomically", "Neil deGrasse Tyson"),
    ("The universe is under no obligation to make sense to {BLANK}.", "you", "Neil deGrasse Tyson"),
    ("Intelligence is the ability to adapt to {BLANK}.", "change", "Stephen Hawking"),
    ("Life would be tragic if it weren't {BLANK}.", "funny", "Stephen Hawking"),

    # ── John Muir ─────────────────────────────────────────────────────────────
    ("In every walk with nature, one receives far more than he {BLANK}.", "seeks", "John Muir"),
    ("The mountains are calling and I must {BLANK}.", "go", "John Muir"),

    # ── Walt Disney ───────────────────────────────────────────────────────────
    ("All our dreams can come true, if we have the courage to {BLANK} them.", "pursue", "Walt Disney"),
    ("It's kind of fun to do the {BLANK}.", "impossible", "Walt Disney"),
    ("The way to get started is to quit talking and begin {BLANK}.", "doing", "Walt Disney"),

    # ── C.S. Lewis ────────────────────────────────────────────────────────────
    ("You are never too old to set another goal or to dream a new {BLANK}.", "dream", "C.S. Lewis"),
    ("Hardships often prepare ordinary people for an extraordinary {BLANK}.", "destiny", "C.S. Lewis"),
    ("Humility is not thinking less of yourself, but thinking of yourself {BLANK}.", "less", "C.S. Lewis"),

    # ── Paulo Freire / others ─────────────────────────────────────────────────
    ("Education is not the filling of a pail, but the lighting of a {BLANK}.", "fire", "W.B. Yeats"),
    ("The two most common elements in the universe are hydrogen and {BLANK}.", "stupidity", "Harlan Ellison"),
    ("I am not afraid of storms, for I am learning how to sail my {BLANK}.", "ship", "Louisa May Alcott"),
    ("Well-behaved women seldom make {BLANK}.", "history", "Laurel Thatcher Ulrich"),
    ("A woman is like a tea bag — you can't tell how strong she is until you put her in hot {BLANK}.", "water", "Eleanor Roosevelt"),
    ("If you want something done, ask a busy {BLANK}.", "person", "Lucille Ball"),
    ("Behind every successful man is a surprised {BLANK}.", "woman", "Maryon Pearson"),
    ("I am woman, hear me {BLANK}.", "roar", "Helen Reddy"),
    ("You can't use up creativity. The more you use, the more you {BLANK}.", "have", "Maya Angelou"),
    ("I've been absolutely terrified every moment of my life — and I've never let it keep me from doing a single thing I {BLANK}.", "wanted", "Georgia O'Keeffe"),
    ("The most courageous act is still to think for {BLANK}.", "yourself", "Coco Chanel"),
    ("I don't design clothes, I design {BLANK}.", "dreams", "Ralph Lauren"),
    ("Fashion fades, only style remains the {BLANK}.", "same", "Coco Chanel"),
]
# ─────────────────────────────────────────────────────────────────────────────

# Avoid repeating quotes too soon; keep a rolling exclusion window
_RECENT_SIZE = min(60, len(QUOTES) // 4)
_recent_indices: deque = deque(maxlen=_RECENT_SIZE)


def _pick_quote():
    available = [i for i in range(len(QUOTES)) if i not in _recent_indices]
    if not available:
        available = list(range(len(QUOTES)))
    idx = random.choice(available)
    _recent_indices.append(idx)
    return QUOTES[idx]


def _make_blank(word: str) -> str:
    """Return a backtick-wrapped underscore string matching the word length."""
    return f"`{'_' * len(word)}`"


def _normalize(text: str) -> str:
    """Lowercase and strip leading/trailing non-alphanumeric characters for comparison."""
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", text.lower())


# ── Play Again button ─────────────────────────────────────────────────────────

class FamousPlayAgainView(discord.ui.View):
    def __init__(self, cog: "FamousWords", channel_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green, emoji="🎮")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.channel_id in self.cog.games:
            await interaction.response.send_message(
                "A game is already running here!", ephemeral=True
            )
            return
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._start_game(interaction.channel)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class FamousWords(commands.Cog):
    """Famous Words — fill in the missing word from a famous quote!"""

    DEFAULT_DURATION = 30

    def __init__(self, bot):
        self.bot = bot
        self.games: dict = {}   # channel_id → game dict
        self._tasks: dict = {}  # channel_id → asyncio.Task
        self.config = Config.get_conf(self, identifier=0x4661776F726473)
        self.config.register_guild(duration=self.DEFAULT_DURATION)

    def cog_unload(self):
        for task in self._tasks.values():
            task.cancel()
        self.games.clear()
        self._tasks.clear()

    # ── Start game ────────────────────────────────────────────────────────────

    async def _start_game(self, channel: discord.TextChannel):
        duration = await self.config.guild(channel.guild).duration()
        quote_text, answer, attribution = _pick_quote()

        blank = _make_blank(answer)
        display = quote_text.replace("{BLANK}", blank)

        game = {
            "answer": _normalize(answer),
            "raw_answer": answer,
            "attribution": attribution,
            "quote_text": quote_text,
            "participants": set(),
        }
        self.games[channel.id] = game

        embed = discord.Embed(
            title=f"📜  Famous Words!{DEV_LABEL}",
            description=(
                f"*\"{display}\"*\n"
                f"— {attribution}\n\n"
                f"Type the missing word! You have **{duration} seconds**."
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Missing word: {len(answer)} letter{'s' if len(answer) != 1 else ''}")
        await channel.send(embed=embed)

        task = asyncio.create_task(self._run_round(channel, game, duration))
        self._tasks[channel.id] = task

    # ── $famouswords ──────────────────────────────────────────────────────────

    @commands.group(name="famouswords", invoke_without_command=True)
    @commands.guild_only()
    async def famouswords(self, ctx: commands.Context):
        """
        Start a Famous Words round.
        A famous quote appears with one key word missing — first to type it wins!
        """
        if ctx.channel.id in self.games:
            await ctx.send("A Famous Words round is already running in this channel!")
            return
        await self._start_game(ctx.channel)

    # ── $famouswords settime <seconds> ───────────────────────────────────────

    @famouswords.command(name="settime")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def famouswords_settime(self, ctx: commands.Context, seconds: int):
        """Set the round duration for Famous Words (admins only).
        Example: `$famouswords settime 20`
        """
        seconds = max(10, min(seconds, 300))
        await self.config.guild(ctx.guild).duration.set(seconds)
        await ctx.send(f"Famous Words round time set to **{seconds} seconds**.")

    # ── force_stop_game (called by $end / GameStop cog) ───────────────────────

    async def clear_recent_memory(self, guild=None) -> str:
        """Clear the recent-quotes exclusion window. Returns cog display name."""
        _recent_indices.clear()
        return "Famous Words"

    async def force_stop_game(self, channel_id: int):
        game = self.games.pop(channel_id, None)
        task = self._tasks.pop(channel_id, None)
        if task:
            task.cancel()
        return "Famous Words" if game is not None else None

    # ── Timer ─────────────────────────────────────────────────────────────────

    async def _run_round(self, channel: discord.TextChannel, game: dict, duration: int):
        await asyncio.sleep(duration)
        if self.games.get(channel.id) is game:
            self.games.pop(channel.id, None)
            self._tasks.pop(channel.id, None)
            await self._timeout(channel, game)

    async def _timeout(self, channel: discord.TextChannel, game: dict):
        tp = self.bot.get_cog("TrackPoints")
        if tp:
            await tp.record_game_result(None, game.get("participants", set()))
        revealed = game["quote_text"].replace("{BLANK}", f"**{game['raw_answer']}**")
        embed = discord.Embed(
            title="⏰  Time's Up!",
            description=(
                f"The missing word was **{game['raw_answer']}**!\n\n"
                f"*\"{revealed}\"*\n"
                f"— {game['attribution']}"
            ),
            color=discord.Color.orange(),
        )
        await channel.send(embed=embed, view=FamousPlayAgainView(self, channel.id))

    # ── Message listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in self.games:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        guess = _normalize(message.content.strip())
        if not guess:
            return

        game = self.games[message.channel.id]
        game["participants"].add(message.author)

        if guess != game["answer"]:
            return

        # ── Correct answer! ───────────────────────────────────────────────────
        self.games.pop(message.channel.id, None)
        task = self._tasks.pop(message.channel.id, None)
        if task:
            task.cancel()

        tp = self.bot.get_cog("TrackPoints")
        total_pts = None
        if tp:
            await tp.record_game_result(message.author, game["participants"])
            total_pts = await tp.get_points(message.author)
        pts_line = f"\nYou now have **{total_pts:,}** total points!\n" if total_pts is not None else "\n"
        revealed = game["quote_text"].replace("{BLANK}", f"**{game['raw_answer']}**")
        embed = discord.Embed(
            title=f"🎉  {message.author.display_name} got it!",
            description=(
                f"The missing word was **{game['raw_answer']}**!{pts_line}"
                f"\n*\"{revealed}\"*\n"
                f"— {game['attribution']}"
            ),
            color=discord.Color.green(),
        )
        await message.channel.send(embed=embed, view=FamousPlayAgainView(self, message.channel.id))
