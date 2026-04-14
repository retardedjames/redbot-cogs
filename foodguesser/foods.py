# ── Food / dish list (250 items) ──────────────────────────────────────────────
# Sorted roughly by global recognition so the list can be trimmed from the
# bottom if 250 turns out to be too many.

FOODS = [
    # ── Tier 1: Universal icons ──────────────────────────────────────────────────
    "Pizza", "Hamburger", "Sushi", "Tacos", "Pasta",
    "Fried Chicken", "Hot Dog", "French Fries", "Burrito", "Sandwich",

    # ── Tier 2: Very widely known ────────────────────────────────────────────────
    "Cheeseburger", "Lasagna", "Ramen", "Dumplings", "Mac and Cheese",
    "Pancakes", "Waffles", "Croissant", "Cheesecake", "Donut",
    "Grilled Cheese Sandwich", "Caesar Salad", "Scrambled Eggs",
    "Pad Thai", "Apple Pie", "Steak", "Fish and Chips",
    "Chicken Curry", "Crepes", "Omelette",

    # ── American ─────────────────────────────────────────────────────────────────
    "BBQ Ribs", "Buffalo Wings", "Philly Cheesesteak", "Clam Chowder",
    "Corn Dog", "Bacon and Eggs", "Eggs Benedict", "BLT Sandwich",
    "Club Sandwich", "Lobster Roll", "Pulled Pork Sandwich",
    "Biscuits and Gravy", "Meatloaf", "Pot Roast", "Turkey and Stuffing",
    "Reuben Sandwich", "Cobb Salad", "Chicken and Waffles", "French Toast",
    "Cinnamon Roll", "Banana Split", "Brownie", "Pecan Pie", "Corn Bread",
    "Potato Skins", "Deviled Eggs", "Sloppy Joe", "Funnel Cake",
    "Lobster Bisque", "Jalapeño Poppers",

    # ── Italian ──────────────────────────────────────────────────────────────────
    "Margherita Pizza", "Pepperoni Pizza", "Mushroom Pizza",
    "Carbonara", "Spaghetti Bolognese", "Risotto", "Tiramisu",
    "Chicken Parmigiana", "Gnocchi", "Cannoli", "Fettuccine Alfredo",
    "Focaccia", "Minestrone", "Ravioli", "Osso Buco", "Bruschetta",
    "Calzone", "Panna Cotta", "Arancini", "Polenta",

    # ── French ───────────────────────────────────────────────────────────────────
    "French Onion Soup", "Coq au Vin", "Crème Brûlée", "Ratatouille",
    "Bouillabaisse", "Beef Bourguignon", "Éclair", "Macarons",
    "Soufflé", "Quiche", "Croque Monsieur",

    # ── Japanese ─────────────────────────────────────────────────────────────────
    "Sashimi", "Tempura", "Udon", "Miso Soup", "Teriyaki Chicken",
    "Yakitori", "Tonkatsu", "Okonomiyaki", "Takoyaki", "Onigiri",
    "Soba", "Gyoza", "Yakisoba", "Katsu Curry", "Mochi",
    "Karaage", "Sukiyaki",

    # ── Chinese ──────────────────────────────────────────────────────────────────
    "Peking Duck", "Dim Sum", "Kung Pao Chicken", "Sweet and Sour Pork",
    "Hot Pot", "Mapo Tofu", "Char Siu", "General Tso's Chicken",
    "Wonton Soup", "Spring Rolls", "Egg Fried Rice", "Sesame Chicken",
    "Chow Mein", "Pork Bao", "Xiaolongbao", "Dan Dan Noodles", "Congee",

    # ── Mexican ──────────────────────────────────────────────────────────────────
    "Enchiladas", "Tamales", "Quesadilla", "Guacamole", "Pozole",
    "Chiles Rellenos", "Carnitas", "Chilaquiles", "Mole Chicken",
    "Huevos Rancheros", "Elote",

    # ── Indian ───────────────────────────────────────────────────────────────────
    "Butter Chicken", "Chicken Tikka Masala", "Biryani", "Samosa",
    "Dal", "Tandoori Chicken", "Palak Paneer", "Chana Masala",
    "Aloo Gobi", "Korma", "Dosa", "Lamb Rogan Josh", "Gulab Jamun",

    # ── Greek / Mediterranean ────────────────────────────────────────────────────
    "Moussaka", "Spanakopita", "Gyros", "Souvlaki", "Baklava",
    "Falafel", "Hummus", "Shawarma", "Kebab", "Dolmas", "Greek Salad",

    # ── Spanish ──────────────────────────────────────────────────────────────────
    "Paella", "Gazpacho", "Tortilla Española", "Churros", "Patatas Bravas",

    # ── Thai ─────────────────────────────────────────────────────────────────────
    "Green Curry", "Tom Yum Soup", "Som Tam", "Massaman Curry",
    "Tom Kha Gai", "Mango Sticky Rice",

    # ── Vietnamese ───────────────────────────────────────────────────────────────
    "Pho", "Banh Mi", "Bun Bo Hue", "Vietnamese Spring Rolls",

    # ── Korean ───────────────────────────────────────────────────────────────────
    "Bibimbap", "Bulgogi", "Tteokbokki", "Korean Fried Chicken",
    "Japchae", "Korean BBQ",

    # ── German / Central European ────────────────────────────────────────────────
    "Bratwurst", "Schnitzel", "Pretzel", "Goulash",
    "Black Forest Cake", "Apple Strudel", "Paprikash",

    # ── Eastern European ─────────────────────────────────────────────────────────
    "Borscht", "Beef Stroganoff", "Pierogies", "Blini", "Pelmeni",

    # ── Turkish ──────────────────────────────────────────────────────────────────
    "Doner Kebab", "Lahmacun", "Börek",

    # ── Middle Eastern ───────────────────────────────────────────────────────────
    "Shakshuka", "Mansaf", "Kabsa", "Knafeh",

    # ── Brazilian ────────────────────────────────────────────────────────────────
    "Feijoada", "Churrasco", "Coxinha", "Brigadeiro",

    # ── African ──────────────────────────────────────────────────────────────────
    "Jollof Rice", "Suya", "Tagine", "Doro Wat",
    "Bobotie", "Peri Peri Chicken", "Couscous",

    # ── Southeast Asian ──────────────────────────────────────────────────────────
    "Nasi Goreng", "Satay", "Adobo", "Sinigang",
    "Laksa", "Rendang", "Hainanese Chicken Rice",

    # ── British / Irish ──────────────────────────────────────────────────────────
    "Shepherd's Pie", "Bangers and Mash", "Full English Breakfast",
    "Scones", "Sticky Toffee Pudding", "Yorkshire Pudding",
    "Beef Wellington", "Scotch Eggs",

    # ── Caribbean / Latin American ───────────────────────────────────────────────
    "Jerk Chicken", "Ropa Vieja", "Mofongo", "Ackee and Saltfish",
    "Empanadas", "Ceviche", "Arepa", "Lomo Saltado",

    # ── Caucasus / Georgian ──────────────────────────────────────────────────────
    "Khachapuri", "Khinkali",

    # ── Rounding out to 250 (less universal but food-lover recognized) ───────────
    "Chocolate Chip Cookies", "Pigs in a Blanket",     # American
    "Saltimbocca", "Penne Arrabbiata",                 # Italian
    "Unagi Don",                                        # Japanese
    "Braised Pork Belly",                               # Chinese
    "Chole Bhature",                                    # Indian
    "Steak Tartare", "Eggs Florentine",                 # French / classic
    "Croque Madame",                                    # French
    "Harissa Chicken",                                  # North African
    "Bigos",                                            # Polish
    "Jamaican Patty",                                   # Caribbean
    "Chili Con Carne",                                  # Tex-Mex
]

assert len(FOODS) == 250, f"Expected 250 foods, got {len(FOODS)}"
