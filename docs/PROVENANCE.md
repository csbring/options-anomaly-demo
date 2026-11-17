# Provenance

This is a new standalone demonstration based on the author's options-flow research project, not a claim that the historical WhatsApp deployment has been recovered.

Extracted engine modules: `constants.py`, `cleaning.py`, `quality.py`, `scoring.py`, `utils.py`, and `quotes.py`. These contain feature definitions, robust transforms, separate call/put Isolation Forest scoring and quality/reason rules. No collector directory, messaging bot file, private workspace, data cache or model binary was copied.

New demo code provides deterministic fixtures, a strict ticker parser, plots, browser chat, follow-ups, CLI exports, optional Ollama narration and a bounded `ib_async` adapter. A stricter preprocessing step rejects invalid/crossed quotes and calculates midpoint/spread from the bid and ask. The quality-pass count additionally excludes missing Greeks and OI. The demo uses 150 trees instead of the original engine default of 300.

The browser does not mimic a WhatsApp session or claim to send messages. Its purpose is to let someone try the ticker → analysis → plots conversation without credentials. Default fixtures contain planted activity for demonstrability; they are not evidence of predictive performance. Only generated demo results appear in documentation screenshots.
