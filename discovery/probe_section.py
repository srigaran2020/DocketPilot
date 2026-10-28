"""Phase 0: dump everything India Code holds for one NI Act section (default: s.138)."""
import json
import sys
import urllib.parse

from probe_indiacode import BASE, get

ACT_ID = "AC_CEN_2_33_00042_00042_1523271998701"
query = sys.argv[1] if len(sys.argv) > 1 else '"Dishonour of cheque for insufficiency"'

j = get(f"{BASE}/discover/search/objects?query={urllib.parse.quote(query)}&size=10")
for o in j["_embedded"]["searchResult"]["_embedded"]["objects"]:
    it = o["_embedded"]["indexableObject"]
    md = it.get("metadata", {})
    if md.get("dc.identifier.act_id", [{}])[0].get("value") != ACT_ID:
        continue
    print("==", it["name"], it["uuid"])
    for k, vs in md.items():
        for v in vs:
            print(f"  {k}: {v['value'][:1500]}")
    bundles = get(f"{BASE}/core/items/{it['uuid']}/bundles")
    for b in bundles["_embedded"]["bundles"]:
        bs = get(b["_links"]["bitstreams"]["href"])
        for s in bs["_embedded"]["bitstreams"]:
            print(f"  bitstream [{b['name']}]: {s['name']} {s.get('sizeBytes')} {s['_links']['content']['href']}")
    break
