# Demo script (Sandbox)

All people, phones, UPI IDs and businesses are fictional. Every screen shows the yellow **Sandbox** badge.

## Setup

```bash
make services && make migrate && make seed   # prints business IDs, phones and the fraud link
make dev-api    # terminal 1
make dev-web    # terminal 2, open http://localhost:5173
```

Log in with a seeded phone (keypad), read the Sandbox OTP on screen, PIN **4826**.

| Phone | Business | Story | Expected |
| --- | --- | --- | --- |
| 90000 00001 | Sharma Kirana Store, Rajwada | Bank linked 14 months, 3 ledger pages that match supplier payments, 3 suppliers confirmed with ₹1 proof, 3 presence checks | Band A, high confidence |
| 90000 00002 | Meena Namkeen Udyog, Sanyogitaganj (woman-owned) | 24 months with Diwali peaks compared with last Diwali, 2 confirmations | Band B |
| 90000 00003 | Ansari Tailors, Khajrana | Only a UPI statement PDF (wedding-season peaks), 1 confirmation | Band C (PDF cap), coaching says "Link your bank account" |
| 90000 00004 | Raju General Store, Bhawarkua | Fraud attempt | On hold |

## Scenes

1. **Join by voice** (fresh phone): language tap, OTP, PIN, consent read aloud, voice interview, shop photo from the live camera.
2. **Evidence**: photograph a ledger page (read-back of a low-confidence entry, amount in words), read an unreadable page aloud, add a Khatabook CSV, link the bank through the Sandbox Account Aggregator.
3. **Partners**: the system picks the top partners from payments; the owner only types phone numbers.
4. **Passport** (Sharma Kirana): band, headline ("…because 82% of your ledger matches…"), coaching, QR, Hindi PDF.
5. **Fraud attempt** (Raju General Store): Raju sent the invite for his real supplier *Agrawal Wholesale* to his friend. Open the printed `/confirm/...` link, tap "Pay ₹1", and in the Sandbox payer form enter `pappu.friend@okaxis` / `PAPPU KUMAR`. The ₹1 came from the wrong account, so the confirmation is rejected, refunded, and Raju's passport goes **on hold** for a reviewer. (`make seed` then `uv run python -m scripts.seed_demo --play-fraud` scripts the same scene.)
6. **Lender**: scan the QR, the signature verifies offline and live status shows valid / on hold.
