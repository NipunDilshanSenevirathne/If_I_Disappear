# Held-out sets

Examples the app was never tuned on. They were written, labelled and **frozen on 29 October 2026,
before the first run on them**: `MANIFEST.json` holds the SHA-256 of every file, and
`evals/run_heldout.py` refuses to run if any file has changed since. The development sets the
prompts and rules were tuned against are in `evals/data/`; nothing here appears there.

| File | What | How many |
|---|---|---|
| `photo_pairs.json` + `photos/` | "Show me": an owner's photo of an object and a family member's photo, each pair labelled before the run | 29 pairs: 12 of the same object, 10 of a different object of the same kind, 7 hard to tell (old black-and-white photos, an odd angle, the object small in a group, blurred and dark, nothing to see) |
| `walkthroughs.json` | Reading facts from what an owner said | 8 transcripts (5 English, 2 Sinhala, 1 Sinhala in Latin letters), 17 facts a correct reading finds, 8 mistakes it must not make: a correction mid-sentence, negations, a spoken code, a medicine sentence, a date the speaker isn't sure of |
| `tell_answers.jsonl` | "Tell me": a family member's explanation of a sample-home job | 20 answers (9 Sinhala, 11 English or Sinhala in Latin letters); 8 should pass, 12 should not (omissions, negations, the wrong day, time, person or place, the right words with no instructions) |
| `help_questions.jsonl` | Questions to the help line | 32: 18 about recorded jobs, 8 about things never recorded, 4 emergencies, 2 about medicine |

**The photos are independent photographs.** The development photo set is crops and turns of single
stock photos, so "the same object" there is the same photograph framed again. Here every pair is
two photographs the Metropolitan Museum of Art took of one object (often years apart), or of two
different objects of the same kind, all public domain (CC0): see `SOURCES.md`. Museum photos have
plain backgrounds, which is easier than a family member's photo in a real room, and the objects
(padlocks, kettles, teapots, clocks, oil lamps) stand in for the household's own.

**How each answer is judged** is fixed in the files: the photo labels (`expect`); for reading, the
patterns a correct fact must match and the patterns that make a fact wrong; for tell and help, the
expected result. After a run, every fact the reading suite produced is also read by a person, and
any place the patterns judged differently from that reading is reported with the results.

These sets are small. They show how the checks behave on cases written to probe them, not how
often the app is right in real homes.
