import json
import glob
from engine.grounding import get_active_offer

# Search the whole dataset/ and expanded/ trees for a merchant record
# mentioning Studio11, whatever the exact file layout turns out to be.
candidates = glob.glob("dataset/**/*.json", recursive=True) + glob.glob("expanded/**/*.json", recursive=True)

merchant = None
merchant_path = None
for path in candidates:
    try:
        data = json.load(open(path))
    except Exception:
        continue
    # handle both a single merchant object and a list/dict of merchants
    records = data if isinstance(data, list) else data.get("merchants", [data])
    for rec in records:
        if isinstance(rec, dict) and "Studio11" in json.dumps(rec):
            merchant = rec
            merchant_path = path
            break
    if merchant:
        break

if not merchant:
    print("Could not find a Studio11 record — paste the output of:")
    print("  find . -iname '*.json' | xargs grep -l Studio11")
else:
    print(f"Found merchant record in: {merchant_path}")
    print("---- offers field ----")
    print(json.dumps(merchant.get("offers"), indent=2))

    category = {"slug": "salons"}
    print("---- get_active_offer(merchant, category) ----")
    print(get_active_offer(merchant, category))