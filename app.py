from flask import Flask, request, jsonify, send_from_directory
import random
import math
import configuration 
import copy

class Gear:
    def __init__(self, name, slots, cost, properties):
        self.name = name
        self.slots = slots
        self.cost = cost
        self.properties = properties

class Weapon:
    def __init__(self, name, slots, cost, weapon_type, combat_range, damage, properties):
        self.name = name
        self.slots = slots
        self.cost = cost
        self.type = weapon_type
        self.range = combat_range
        self.damage = damage
        self.properties = properties

class Armor:
    def __init__(self, name, slots, cost, ac, properties):
        self.name = name
        self.slots = slots
        self.cost = cost
        self.ac = ac
        self.properties = properties

class Potion:
    def __init__(self, name, slots, cost, properties):
        self.name = name
        self.slots = slots
        self.cost = cost
        self.properties = properties

class Poison:
    def __init__(self, name, slots, rarity, cost, properties):
        self.name = name
        self.slots = slots
        self.rarity = rarity
        self.cost = cost
        self.properties = properties


def read_file_lines(name: str):
    with open(name, "r", encoding="utf-8") as f:
        return f.read().splitlines()

def read_from_file(filename, classname):
    objs = []
    for line in read_file_lines(filename):
        if not line.strip():
            continue
        args = line.split("    ")
        objs.append(classname(*args))
    return objs

def roll_count(weighted_counts, rng):
    counts, weights = zip(*weighted_counts)
    return rng.choices(counts, weights=weights, k=1)[0]

def pick_unique(pool, k, rng):
    k = max(0, min(int(k), len(pool)))
    return [copy.deepcopy(x) for x in rng.sample(pool, k)]

def convertcoins2int(value: str) -> float:
    value = str(value)
    value = value.strip()
    if value.endswith("cp"):
        return float(value[:-2]) / 100.0
    if value.endswith("sp"):
        return float(value[:-2]) / 10.0
    if value.endswith("gp"):
        return float(value[:-2])
    return float(value)

def calc_coins(cost: float) -> str:
    # gp.sp.cp where 1gp=10sp=100cp
    frac, whole = math.modf(cost)
    gp = int(whole)

    frac, sp_whole = math.modf(frac * 10)
    sp = int(sp_whole)

    frac, cp_whole = math.modf(frac * 10)
    cp = int(cp_whole)

    parts = []
    if gp: parts.append(f"{gp}gp")
    if sp: parts.append(f"{sp}sp")
    if cp: parts.append(f"{cp}cp")
    return " ".join(parts) if parts else "0gp"


class Shop:
    def __init__(self, size, prices, rng, gear_pool, weapons_pool, armors_pool, potions_pool, poisons_pool):
        self.size = size
        self.prices = prices

        self.rng = rng

        self.gear = self.populate("gear")
        self.weapons = self.populate("weapons")
        self.armors = self.populate("armors")
        self.potions = self.populate("potions")
        self.poisons = self.populate("poisons")

        # Apply price modifier
        for item in (self.gear + self.weapons + self.armors + self.potions + self.poisons):
            p = convertcoins2int(item.cost)
            if self.prices == "E":
                p += configuration.PERCENTAGE_EXPENSIVE * p
            elif self.prices == "C":
                p += configuration.PERCENTAGE_CHEAP * p
            item.cost = p

    def populate(self, kind: str):
        if self.size == "S":
            chances = getattr(configuration, f"CHANCES_{kind.upper()}_SMALL")
        elif self.size == "M":
            chances = getattr(configuration, f"CHANCES_{kind.upper()}_MEDIUM")
        else:
            chances = getattr(configuration, f"CHANCES_{kind.upper()}_LARGE")

        c = roll_count(chances, self.rng)
        pool = POOLS[kind]
        return pick_unique(pool, c, self.rng)


# ---- Load pools once on server startup ----
GEAR = read_from_file("gear.txt", Gear)
WEAPONS = read_from_file("weapons.txt", Weapon)
ARMORS = read_from_file("armors.txt", Armor)
POTIONS = read_from_file("potions.txt", Potion)
POISONS = read_from_file("poisons.txt", Poison)

POOLS = {
    "gear": GEAR,
    "weapons": WEAPONS,
    "armors": ARMORS,
    "potions": POTIONS,
    "poisons": POISONS,
}

# ---- Shopkeeper generator (your logic, fixed indexing) ----
name_table = [
    ['Ir','Van','Cyr','Den','Cor','Hil','Sal','Bri','Mar','Gar','Tin','Vor','Nel','Ri','Quor','Bal','Mur','Par','Tor','Lem'],
    ['an','ish','tos','zar','ven','sen','win','on','en','lin','sor','oc','vyn','al','osh','er','in','el','un','nar'],
    ['l','n','pil','g','z','bor','t','c','ar','q','v','iv','ov','b','den','k','s','r','jen','w'],
    ['int','us','ios','el','inne','os','ian','ius','iol','an','isk','erg','ent','ial','ant','iel','onne','org','enne','ynne']
]
ancestries = ['Dwarf', 'Elf', 'Goblin', 'Halfling', 'Half-Orc', 'Human']

def gen_shopkeeper(rng):
    parts = [rng.choice(name_table[i]) for i in range(4)]
    return "".join(parts), rng.choice(ancestries)

def serialize_item(x):
    d = {
        "name": x.name,
        "slots": getattr(x, "slots", None),
        "cost_gp": x.cost,
        "cost_str": calc_coins(x.cost),
    }
    # add optional fields
    for k in ["type", "range", "damage", "properties", "ac", "rarity"]:
        if hasattr(x, k):
            d[k] = getattr(x, k)
    return d


app = Flask(__name__, static_folder="static")

@app.get("/")
def home():
    return send_from_directory("static", "index.html")

@app.get("/api/shop")
def api_shop():
    size = (request.args.get("size", "R").upper() or "R")
    cost = (request.args.get("cost", "R").upper() or "R")

    # seed can be anything (number or string). If missing, generate one.
    seed_in = request.args.get("seed", None)
    if seed_in is None or str(seed_in).strip() == "":
        # generate a seed to return (so user can reproduce it)
        seed_in = str(random.randrange(0, 2**32))
    seed = str(seed_in)

    rng = random.Random(seed_in)

    shop_sizes = ["S", "M", "L"]
    shop_costs = ["C", "N", "E"]

    if size == "R":
        size = rng.choice(shop_sizes)
    if cost == "R":
        cost = rng.choice(shop_costs)

    if size not in shop_sizes or cost not in shop_costs:
        return jsonify({"error": "size must be S/M/L (or R), cost must be C/N/E (or R)"}), 400

    shop = Shop(size, cost, rng, GEAR, WEAPONS, ARMORS, POTIONS, POISONS)
    keeper_name, keeper_ancestry = gen_shopkeeper(shop.rng)

    payload = {
        "seed": seed,
        "shopkeeper": {"name": keeper_name, "ancestry": keeper_ancestry},
        "size": size,
        "cost_policy": cost,
        "gear": [serialize_item(i) for i in shop.gear],
        "weapons": [serialize_item(i) for i in shop.weapons],
        "armors": [serialize_item(i) for i in shop.armors],
        "poisons": [serialize_item(i) for i in shop.poisons],
        "potions": [serialize_item(i) for i in shop.potions],
    }
    return jsonify(payload)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
