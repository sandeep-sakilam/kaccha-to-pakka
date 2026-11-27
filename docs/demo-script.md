# Demo video script (3 minutes, Sandbox)

Everything in the video is fictional: people, phone numbers, UPI IDs and businesses. Every screen shows the yellow **Sandbox** badge; say so once at the start.

## Before recording

```bash
make services && make migrate && make seed
```

```bash
make dev-api
```

```bash
make dev-worker
```

```bash
make dev-web
```

Open http://localhost:5173 on a phone-sized browser window (or the deployed site). `make seed` prints the business IDs and the **replay link** for the fraud scene (`/confirm/<token>`); keep it in a second tab. Logins: phone keypad → OTP shown on screen in Sandbox → PIN **4826**.

| Phone | Business | What the seed built | Band today |
| --- | --- | --- | --- |
| 90000 00001 | Sharma Kirana Store, Rajwada | Bank linked 14 months, 3 ledger pages matching supplier payments, 3 suppliers confirmed with ₹1 proof, 3 presence checks | **B**, high confidence |
| 90000 00002 | Meena Namkeen Udyog, Sanyogitaganj (woman-owned) | 24 months with Diwali peaks, compared with last Diwali; 2 confirmations | **B**, high confidence |
| 90000 00003 | Ansari Tailors, Khajrana | UPI statement PDF only, wedding-season peaks; 1 confirmation | **C** (a PDF alone is capped at C) |
| 90000 00004 | Raju General Store, Bhawarkua | A friend posed as his supplier; the ₹1 came from the wrong account | **On hold** for review |

Sharma Kirana is B, not A, because its three confirmers are new on the platform: a confirmation counts for more as the confirmer's own history grows.

## Scenes

| Time | Scene | On screen | Say (voice-over) |
| --- | --- | --- | --- |
| 0:00–0:15 | Problem | Welcome screen in Hindi, Sandbox badge | "7.9 crore small businesses in India can't prove they are real. Kaccha to Pakka builds a Trust Passport from evidence that must agree. This is a Sandbox demo." |
| 0:15–0:40 | Join by voice | Tap हिन्दी → Start → keypad phone → OTP → PIN → consent read aloud (press Listen) → interview: say or type "Sharma Kirana", tap Kirana, "2012 se", "Rajwada" → shop photo with the live camera | "No typing needed. A PIN per profile because families share phones. Consent is read aloud. Only the live camera: no gallery photos." |
| 0:40–1:05 | Evidence | Home → Photograph ledger page → read-back: "Sharma ji, चार हज़ार रुपये, 12 अक्टूबर को मिले: सही?" → Yes → Link bank → Sandbox Account Aggregator → Approve | "AI reads the page, rules decide. Unsure entries are read back in words. Bank data comes straight from the bank and can't be edited." |
| 1:05–1:25 | Trading partners | Partners screen: system-picked list with masked UPI IDs → enter a phone number | "The owner can't choose who confirms. We pick the top partners from the payments; the owner only sends the invite." |
| 1:25–1:55 | Passport (log in as 90000 00001) | My Trust Passport: band **B**, headline, coaching "Ask more partners", QR, Hindi PDF | "A band with a confidence level and plain reasons, never a bare number. Signed, so it can't be forged." |
| 1:55–2:15 | Lender | Share with "SBI Rajwada branch" → open the link in another tab: watermark, evidence → back on the owner phone: "SBI Rajwada branch viewed your passport" | "One lender, a scope and an expiry. Every view is shown to the owner. The QR verifies offline." |
| 2:15–2:45 | **Fraud attempt** | Open the replay link `/confirm/<token>` → "Raju General Store says you are their supplier" → Pay ₹1 → in the Sandbox payer form enter `pappu.friend@okaxis` / `PAPPU KUMAR` → result. Then log in as 90000 00004 → My Trust Passport | The screen shows: **"The ₹1 came from a different account than the one in their payments, so we cannot accept this confirmation."** (Hindi: "₹1 उनके भुगतानों वाले खाते से नहीं, किसी और खाते से आया, इसलिए यह पुष्टि नहीं मानी जा सकती।") Raju's passport shows **"On hold for review"** and "Your passport is on hold while we check something." Say: "Raju sent his real supplier's invite to a friend. The friend can pay ₹1, but not from the supplier's account, so the confirmation is rejected, the ₹1 is refunded, and Raju's passport goes on hold for a reviewer." |
| 2:45–3:00 | Close | Passport screen with QR | "We verify evidence; the lender decides. We built this so that no honest small business in India is denied credit because it couldn't prove it was real." |

## If something goes wrong while recording

- The OTP is printed on screen in Sandbox; if a login fails, request a new OTP.
- The fraud replay link works once. To record it again, run `make seed` and use the new link (this erases the local database).
- Internal reason code for the rejection, for reviewers: `account_mismatch`.
