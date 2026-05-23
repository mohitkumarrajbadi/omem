"""BharatSearch - Farmer agent demo using OMem memory."""

from omem import OMem

print("BharatSearch: Farmer Agent Memory Demo")
print("=" * 50)

omem = OMem()

# ----- Biographical / Semantic memories -----
omem.add("User is Ramesh, a sugarcane farmer from Kolhapur, Maharashtra")
omem.add("Ramesh owns 5 acres of irrigated farmland")
omem.add("Primary crop is sugarcane; secondary crops are soybean and turmeric")
omem.add("Ramesh's Aadhaar is linked to PM-Kisan account")

# ----- Episodic memories -----
omem.add("Yesterday Ramesh checked PNR status for train 12127 Pune-Mumbai")
omem.add("Last week Ramesh visited the Krishi Vigyan Kendra for soil testing")
omem.add("Ramesh experienced crop loss due to unseasonal rain in October 2024")

# ----- Decision memories -----
omem.add("Ramesh decided to switch from chemical urea to organic compost")
omem.add("Ramesh chose drip irrigation over flood irrigation to save water")

# ----- Procedural memories -----
omem.add(
    "To apply for PM-Kisan: step 1 visit pmkisan.gov.in, step 2 register Aadhaar, step 3 verify bank details"
)
omem.add(
    "How to check soil health card: visit soilhealth.dac.gov.in and enter survey number"
)

# ----- Causal memories -----
omem.add("Crop failure in kharif 2024 caused Ramesh to take a Rs2 lakh bank loan")
omem.add("Switching to organic fertilizer resulted in 15% yield improvement")

# ----- Working / Active -----
omem.add("Ramesh is currently preparing land for rabi season sowing")
omem.add("Urgent: Ramesh needs to renew crop insurance before December 31")

# Causal links
ids = omem.all()
if len(ids) >= 13:
    omem.link(ids[6].id, ids[11].id, label="crop_loss->loan")
    omem.link(ids[7].id, ids[12].id, label="organic_switch->yield_up")

print(f"\nLoaded {omem.stats()['total']} memories")
print(f"Types: {omem.stats()['types']}\n")

# ----- RAG queries a farmer agent would make -----
queries = [
    "What crops does the farmer grow?",
    "train PNR status",
    "How to apply for PM-Kisan?",
    "Why did the farmer take a loan?",
    "farmer irrigation decision",
    "urgent tasks",
]

for q in queries:
    print(f'Query: "{q}"')
    results = omem.recall(q, top_k=3)
    for r in results:
        print(f"   [{r.type.name:<12}] {r.score:.3f}  {r.content[:70]}")
    print()
