# Privacy and safety

A handover video is about as private as data gets: the inside of a home, a family's voices, where the deeds are kept, who to call when something breaks. This page says plainly what If I Disappear keeps, what it removes, who can see what, and where its limits are.

## What is kept

For each household, on the server that runs the app, in one folder:

- the log of events (`ledger.jsonl`): facts, checks, decisions, proofs, help questions and answers;
- each walk-through video (re-encoded smaller), its stills, and short clips cut from it;
- each job's own clip (`derived/`), cut from the video as it is after the privacy pass: the first time someone opens the job, or in the background shortly after the owner's decisions on Review;
- photos and answers from **Prove it**.

While a recording is still arriving, its pieces wait in one file in the server's `uploads` folder; when the last piece is in, the file goes to the pipeline and is deleted when the pipeline is done with it. An upload never finished is deleted after a day. The pipeline works on the recording in a `staging` folder of its own: the video, its stills and its sound are moved into the household's media only after the privacy pass, so if any step fails, nothing of that recording is kept and nothing of it can be opened. The error says which step failed, never what was said.

Nothing else. Model output reaches the disk only through that log, after the privacy pass: the server keeps no copies of model requests or responses anywhere else. (An early version kept them in a debugging folder; the live check found a spoken gate code there, in the raw speech text, after its household had been deleted. That folder no longer exists, and a test checks that a spoken secret never reaches the disk.)

No accounts, no email addresses, no phone numbers (except WhatsApp numbers a family adds for the help line), no analytics, no third-party scripts or fonts. The web app loads everything from its own origin, enforced by a Content-Security-Policy.

## What is removed before anything is kept

**Secrets in the words.** Every transcript, in English and Sinhala, goes through `privacy/scrub.py` before it is stored or sent to a reading model. It hides the value and keeps the fact that a secret exists: *"the ATM PIN is [hidden]"* still tells the family it is something only the person leaving knows.

| Hidden | How it is found |
|---|---|
| PINs and one-time codes | after the word (PIN, OTP, passcode, පින් අංකය, රහස් අංකය), written or spoken digits, in English or Sinhala |
| Passwords | after the word (password, මුරපදය, පාස්වර්ඩ්), when the value looks like a password or ends the sentence, so *"the password is written in the blue book"* keeps its meaning |
| Gate, lock and alarm codes | after a named lock and the word code or combination (*"the gate code is …"*, *"the code for the alarm is …"*, ගේට්ටුවේ කෝඩ් එක, අගුලේ අංකය). The lock must be named, so postal codes, area codes and door numbers stay |
| Card numbers | 13 to 19 digits that pass the Luhn check |
| Sri Lankan NIC numbers | old (9 digits and V or X) and new (12 digits) formats |
| Bank account numbers | after the words for an account number |

**Secrets in the sound.** A secret hidden from the words would still be audible in the video, so the whole speaking turn it was said in is silenced in the stored video (`media/ffmpeg.mute_spans`).

**Cards and screens in the picture.** SAM 3.1 looks through the whole video for credit cards, identity cards and phone screens: one request for each, on a copy at two frames a second (one a second past three minutes), made from the upload itself at up to 1280 pixels. Code blurs each box it finds in the video, padded, for half a second either side of every frame it was seen in, and in every still taken in that time; the poster is made from a blurred still. When a card is first seen touching the frame's edge, as it comes into view, the strip between it and that edge is blurred for the three seconds before as well, and the same after the last sighting of a card going out at an edge: in the live run of 1 November, SAM 3.1 first found the test card at 34.5 seconds, at the right edge, while its edge, with eight of its digits, had been in the frame since about 31.5 seconds. If the video request fails, SAM 3.1 checks the stills one by one instead; if that can't run either, the recording is not kept. The copy is made from the upload, not from the smaller video that is kept, because of a live run on 29 October: in the kept 960-pixel video SAM 3.1 found no card in the whole walk-through, while in a 1280-pixel copy it found the card in every frame it was in.

The separate audio file used for speech recognition is deleted as soon as the words are written out.

## Who sees what

Three kinds of link, each signed by the server. The server checks every request against this table, the media included (`scope.py`, tested route by route in `test_access_matrix.py`):

| | The person leaving (owner link) | A person staying (their own link) | A sticker (one QR code) |
|---|---|---|---|
| Jobs and their steps | all | the jobs made from facts the owner accepted | its one job |
| Video and sound | the whole walk-through | each job's own clip: the stretch where its facts were said, with any speech no accepted fact came from silenced | its job's clip |
| Stills | all | each job's own still | its job's still |
| Transcripts, the review queue, what was left out | yes | no | no |
| The log (*How we know*) | yes | no | no |
| Proof photos | all | the ones they took | none |
| Other people's WhatsApp numbers | yes | no | no |
| Prove a job, ask the help line | for anyone | as themselves | no (the sticker page shows the emergency numbers) |
| People, links, deleting the home | yes | no | no |

The whole walk-through is the owner's alone because its sound holds everything that was said: facts she rejected, facts still waiting for review, and sentences the rules refused. When she rejects a fact, its words fall silent in every clip that covered them; if she changes her mind, the clip is cut again.

Removing a person in **People** stops their link at once, and their phone lets go of the home the next time it opens it. **Card → Private links → Replace** stops every old link and sticker at once.

## What the models see

Meta's models are called through the Meta Model API with the server's key; nothing goes to a model from the phone directly. The speech models hear the audio (they have to). The reading model sees the scrubbed transcript and stills. SAM 3.1 sees stills, photos and short clips. The app uses Standard mode only, never Contributor mode, because Contributor mode lets Meta train on the data, and these are a family's recordings. Sinhala speech goes to the app's own Omnilingual ASR service, not to a third party.

## Things the app refuses to hold

- **Medical instructions.** Medicine, doses, prescriptions, insulin, in English and Sinhala. The reader is told to skip them, the rules refuse any fact that mentions them, and the review page lists any sentence that was left out and why. Those belong on paper from the doctor or pharmacy.
- **Advice it wasn't given.** The help line can only answer with a job the owner recorded, checked by code. It will not invent a step for a gas leak; it shows the emergency numbers instead (Fire and rescue 110, Ambulance 1990, Police 119).

## Deleting

**People → Delete this home** removes the household's whole folder: the log, every video, still, clip and photo. Sample homes delete themselves after 24 hours.

The offline copy lives on each phone that saved it (**Card → Offline**), not on the server. **Remove from this phone**, on the same page or under **People → This phone**, deletes it; a phone whose link was removed deletes the home's copy the next time it opens it.

## Limits, said plainly

- The scrubber works on patterns. It caught every secret in its evaluation set (16 of 16, with no ordinary sentence hidden), and the gate code in the live check, but a secret said in an unusual way can get through. Say "only I know the PIN" rather than the PIN.
- Blurring is only as good as SAM 3.1's search, and the live run above shows it can miss a card it finds in a sharper copy. It looks at two frames a second, so something on screen for less than half a second can be missed, and a box is padded rather than traced. Keep cards and screens out of the shot; the recording page says so. Nobody but the owner sees any part of a recording until she has accepted facts from it.
- The piece of speech that holds a secret is silenced, from the pause before it to the pause after (3.5 seconds for the gate code in the live check), so a clip can have a short quiet gap. Someone who talks for a long time without pausing gets a longer gap.
- The server owner can read the household folder. Run it yourself, or on a host you trust. Use a long random `IID_LINK_SECRET` and keep the server's key in a secret manager (`deploy/cloud-run.sh` does both).

## Security notes

- Keys only exist on the server, read from the environment; none has a default, and none is ever sent to the browser.
- The server's access log leaves out link tokens (`/l/…`, `/api/s/…`, `?t=…`), and errors from a model say only what failed, never the request. After the browser checks (one of them types a PIN into the help line), CI searches the servers' logs for that PIN, the sample home's codes and any link token.
- Every WhatsApp webhook is checked against `X-Hub-Signature-256` before it is read. It is answered at once and the replies are made after, so a slow model can't make Meta send the message again; one message that can't be answered doesn't stop the others, and the log says only what kind of error it was, never the message.
- Per-client rate limits on everything that can start work or call a model (new homes, uploads, proofs, help questions); a daily spending cap (and an optional lifetime cap) stops model calls before they are made.
- Uploads have a size limit; media paths can't leave the household folder; household ids are validated.
- ffmpeg opens every upload only as an audio or video file, and only from disk (`-format_whitelist`, `-protocol_whitelist file`). Without that, an "upload" that is really a playlist or a concat script (ffmpeg knows a concat script by its first line, whatever the file is called) could make the server read its other files into a video the uploader then gets back. Found while reading the code on 1 November; a test now tries both.
- Responses carry `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, a strict referrer policy and, over HTTPS, `Strict-Transport-Security`. On a Hugging Face Space, whose page shows the app in a frame, `IID_FRAME_ANCESTORS` lets that one site frame it, and nobody else.

Found a problem? Please open an issue without the details, or contact the author directly, and give a little time for a fix before sharing it.
