# Golden set

Put real ledger pages here (with the owners' written consent), one image and one label per page:

- `page-001.jpg` and `page-001.json` (the `LedgerExtraction` schema in `app/adapters/ai_schemas.py`: entries with date, party, amount in paise, direction; page total; script).
- Aim for 50+ pages: Hindi, English and Hinglish, neat and messy handwriting, a few Mahajani/Sarrafi pages.
- For speech-to-text: audio files plus `transcripts.json` = `[{"audio": "a1.wav", "text": "...", "language": "hi"}]`.

Do not commit pages without consent. Images here are ignored by git unless force-added.
