"""Phase 0: probe the India Code DSpace REST API (site moved to indiacode.gov.in)."""
import json
import sys
import urllib.parse
import urllib.request

BASE = "https://indiacode.gov.in/server/api"
UA = {"User-Agent": "DocketPilot-research/0.1", "Accept": "application/json"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def search(query, size=5):
    url = f"{BASE}/discover/search/objects?query={urllib.parse.quote(query)}&size={size}"
    j = get(url)
    for o in j["_embedded"]["searchResult"]["_embedded"]["objects"]:
        it = o["_embedded"]["indexableObject"]
        md = {k: [v["value"] for v in vs][:2] for k, vs in it.get("metadata", {}).items()}
        print("-", it.get("type"), "|", it.get("name"), "|", it.get("handle"), "|", it.get("uuid"))
        for k, v in md.items():
            print(f"     {k}: {str(v)[:150]}")


if __name__ == "__main__":
    root = get(BASE)
    print("api root links:", list(root.get("_links", {}).keys())[:30])
    search(sys.argv[1] if len(sys.argv) > 1 else '"Negotiable Instruments Act"')
