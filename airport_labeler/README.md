# Airport Label Quest

A saved-progress airport-chart labelling game built in Python. It uses the supplied **Airport Blank** chart as the interactive canvas and the supplied **Airport Labelled** chart to define the runway and taxiway question locations.

## Run it

No third-party packages are required.

```bash
cd airport_labeler
python3 app.py
```

Open **http://localhost:8000** in a browser. To use a different port:

```bash
python3 app.py --port 8080
```

## Deployment

The project is GitHub-ready and includes a Dockerfile, Docker Compose configuration,
Render Blueprint, Procfile, runtime file, `.gitignore`, and GitHub Actions CI workflow.
Read **[`deploy-inst.txt`](deploy-inst.txt)** for complete GitHub publishing and public
deployment instructions.

> GitHub Pages cannot host this app because its Python backend stores user profiles,
> trends, validation drafts, and shared question-bank edits. Publish the source on
> GitHub, then deploy the running service through Render or another Docker/Python host
> with a persistent disk.

## Player profiles

The welcome screen asks for a username and shows saved usernames for quick switching.

- Practice sessions, saved in-progress games, incorrect-answer history, per-location statistics, and trend charts are stored **per username**.
- The selected username is remembered in the browser, but users can choose **Switch user** at any time.
- The question bank, validation route overrides, and validator-added questions are **shared**. Any user can open validation mode, update a route, or add questions; completed validation changes become available to all users.
- **Reset my profile** erases only the current user’s progress and trends. It deliberately preserves shared question-bank changes and every other user’s data.

## How the game works

- A new chart begins with **21 randomized location prompts**: three runways and 18 taxiways transcribed from the labelled diagram.
- Click any valid segment of the named route on the blank chart.
- A correct click places a persistent label on the chart.
- An incorrect click counts as a miss and returns that same item to a later, randomized position in the question queue.
- A game ends only when every location has been answered correctly at least once.
- The completion screen shows active time, attempts, misses, accuracy, and a cumulative incorrect-answer trend graph.
- **Study labelled chart** opens the supplied reference image. **Show route hint** briefly highlights the correct route without adding a miss.

## YYC Ground Sort Program

Choose **YYC Ground Sort Program** from the main menu to practice the supplied YYC
sector diagrams.

- First locate the named blank point on the YYC Ground Sort diagram.
- After the point is identified, answer **Who can use this point?** with **Jets**,
  **Props**, or **Jets or Props**.
- A point with an aircraft-use classification is completed only after both the
  location and aircraft-use answers are correct. An error at either step returns
  it to the randomized queue.
- Location-only points (the ADVOX, BIRKO, EBGAL, and IGVEP corner fixes) ask no
  follow-up: a correct click on the blank label completes them immediately.
- The mode has its own per-user progress, retry graph, and YYC Ground Sort trends.
- **Validate ground points** provides the same review, full-screen redraw, question
  editing, skip, and custom-point workflow as the other airport modes. It also lets
  validators change the Jets/Props classification for each point, or mark a point
  as location-only with the *No follow-up* option.

The supplied YYC answer key is stored as `assets/yyc_ground_filled.png`; the blank
exercise canvas is `assets/ground_sort_blank_new.png` (the earlier diagram is kept
as `assets/yyc_ground_blank.png`).

## Apron Ops

Choose **Apron Ops** from the main menu to practice CYYC apron control operations.

- Aircraft dynamically request either:
  - **Departure**: pushback from a gate to exit the apron for an assigned runway (17L, 17R, 35L, or 35R). The controller instructs the aircraft to push back to a parking spot, assigns an exit taxiway, and designates the contact ground frequency (West Ground 121.9 or East Ground 125.35).
  - **Arrival**: apron entry to park at a gate from an assigned runway (17L, 17R, 35L, or 35R). The controller assigns the entry taxiway.
- Gate numbers cover all 66 CYYC terminal gates: `1-6`, `11-24`, `31-40`, `50-59`, `70-76`, `78-92`, and `94-97`.
- Questions are generated randomly each time, selecting a runway, realistic CYYC aircraft callsign, operation request, and gate.
- If multiple spots or taxiway options are valid for a gate, selecting any valid option is considered correct.
- Includes `Gates.png` as a study guide reference, along with reference tabs for `Rules_17` and `Rules_35`.
- Incorrect clearances return to the queue until solved, and active session trends are saved per user profile.

## Flashcard decks

The **Flashcard decks** segment is a per-user Quizlet-style study area.

- Create decks with a title, then open a deck to add cards or begin a review.
- Each card requires a question and answer and can include an optional image on both the question and answer sides.
- New cards begin with the **New** tag.
- Before reviewing, filter the deck by **All**, **New**, **Easy**, **Mid**, or **Hard** cards.
- During a review, reveal the answer and rate each card **Easy**, **Mid**, or **Hard**. The latest rating becomes the card tag.
- Cards can be edited from the deck library or during a review.
- Each deck has independent counts, total recall ratings, review sessions, and a **Common mistakes** view. Hard ratings count most heavily when ranking forgotten cards.

Images are stored as compact data URLs in the user profile JSON. Keep each source image below roughly 1.8 MB; the server enforces a 2 MB image limit per card side.

### Import from Quizlet

**Import from Quizlet** sits beside **Create deck** and builds a whole deck from a Quizlet set.

1. Enter the set's print URL (for example `https://quizlet.com/123456789/print`; ordinary set links are accepted and converted) and a name for the new deck.
2. Open that print page in your browser, choose the **Table** (or Glossary) layout, print it and pick **Save as PDF**.
3. Attach the saved PDF and choose **Import deck**.

The server reads the PDF with its own dependency-free parser (`pdf_text.py` / `quizlet_import.py`), reconstructs the table rows, and creates one card per term/definition pair — the term becomes the question and the definition the answer. Every imported card starts with the **New** tag, the deck records its Quizlet source URL, and the PDF itself is discarded after parsing (only the cards are stored). The upload limit is 15 MB per PDF.

Quizlet blocks automated browsers and this app intentionally ships with no headless browser, which is why the print page is saved by you rather than fetched by the server.

## Airport locations learning mode

Choose **Learn airport locations** from the main menu to work with the supplied
`locations_blank.png` and `locations_labelled.png` charts.

- The lab uses the same randomized, retry-until-correct methodology as the route game.
- Prompts cover navigation aids, weather equipment, facilities, operations, safety sites, and reference points.
- Click the matching coloured marker or facility on the blank locations chart.
- Correct answers label the chart; misses return to the queue; a session ends only after every location is solved.
- The locations lab stores its own per-user progress, end-of-session incorrect-answer graph, and location-specific trend history.
- **Validate locations** opens the same review workflow used by the main chart: preview the saved marker, keep it or redraw it in the calibrated full-screen editor, edit the prompt details, skip to adding questions, and finish to apply changes shared by every user.

## Full data update and backup

Use **Update data** beside **Switch user** in the top bar to open the full import/export popup.

- **Export all data** creates one JSON backup containing every user profile, route, airport-locations, and YYC Ground Sort question bank, validation edits, custom questions, Jets/Props classifications, flashcard decks, cards, optional card images, Easy/Mid/Hard tags, deck stats, and game trends.
- **Import all data** accepts that single full backup file and replaces every current profile and shared field in one operation.
- Flashcard cards retain their tags, review counts, images, and common-mistake statistics through export/import.
- Importing a full-data backup is global: it replaces every user and shared bank, so export a backup before importing a replacement.
- The importer is backwards compatible with prior route-bank, locations-bank, and combined question-bank JSON exports. Those legacy files update only the contained shared bank and preserve current user profiles/decks.
- Older raw single-user memory JSON documents are restored as a `Guest` profile.
- The bundled `question_bank_curated.json` remains the default route bank parsed from the supplied `questions.txt` file.

## Validation game mode

Choose **Validate the question bank** from the main menu to audit the entire question bank in its fixed source order.

- Every prompt is reviewed exactly once; there are no misses or retries in this mode.
- The review screen previews the route that practice mode currently uses in blue and asks whether it needs editing. Choose **Yes — keep route** or **No — edit full screen**. You can also choose **Edit question details** to change the prompt label and description, or **Skip remaining routes → Add questions**; skipped routes retain their existing saved answers.
- Route editing opens a full-screen, calibrated route editor. The PNG background and SVG drawing layer share the same `803 × 922` coordinate origin and dimensions, and pointer coordinates are calculated from the rendered PNG itself. Draw one or more amber strokes; multiple strokes can represent disconnected sections.
- After all existing prompts are reviewed, choose **Add a question** to open that same full-screen editor again. Supply a label, select Runway or Taxiway, optionally add a clue, and draw the new answer route.
- Route edits and new questions are validation drafts while the review is in progress. They do **not** change practice-mode scoring until you select **Finish & apply validation**. Validation drafts belong to the user who created them.
- Finishing validation atomically promotes drawings to shared route overrides and adds staged questions to the shared persistent practice question bank. All users’ future practice sessions use those new paths, hints, and questions.
- Validation progress also saves automatically, so a review can be paused and resumed without applying incomplete drafts.
- The airport locations bank has an equivalent validation run, dedicated marker/detail overrides, location-specific custom questions, and separate validation history.

## Saved memory

All state is stored locally in:

```text
data/airport_labeler_memory.json
```

The file contains independent player profiles (each with their own active route game, active locations lab, active YYC Ground Sort run, validation drafts, flashcard decks/cards/images, completed-session summaries, answer events, and performance statistics) plus shared route/marker/ground-point overrides, question-detail overrides, custom questions, custom location points, and imported bank snapshots. The app automatically pauses and saves when a user returns to the main menu or closes the page. Each user’s route, locations, and YYC Ground Sort trend screens include only that user’s own time/miss history.

For a deployed container, set `AIRPORT_LABELER_DATA_DIR` to a persistent mounted volume. The Dockerfile and `render.yaml` already do this; see `deploy-inst.txt` for the deployment steps.

Use **Reset my profile** on the home screen only if the current user wants to erase their own saved practice progress, validation drafts, and history. It does not erase shared validated routes, custom questions, or other user profiles.

## Project layout

```text
airport_labeler/
├── app.py                     # Standard-library HTTP server + game rules + persistence
├── game_data.py               # Fallback main question bank and route hit areas
├── locations_data.py          # Locations-learning question bank and marker hit areas
├── yyc_ground_data.py         # YYC Ground Sort points and Jets/Props answers
├── pdf_text.py                # Dependency-free PDF text/table extraction
├── quizlet_import.py          # Quizlet print-PDF → term/definition card pairs
├── questions.txt              # Supplied curated main question/answer list
├── question_bank_curated.json # JSON form parsed from questions.txt at project setup
├── Dockerfile                 # Production container image
├── docker-compose.yml         # Local container deployment with a persistent volume
├── render.yaml                # Render GitHub deployment Blueprint
├── Procfile / runtime.txt     # Buildpack-compatible deployment metadata
├── deploy-inst.txt            # Full GitHub and deployment guide
├── .github/workflows/ci.yml   # GitHub Actions verification
├── assets/
│   ├── airport_blank.png      # Main blank route chart
│   ├── airport_labelled.png   # Main labelled route reference
│   ├── locations_blank.png    # Supplied blank locations chart
│   ├── locations_labelled.png # Supplied labelled locations reference
│   ├── yyc_ground_blank.png   # Earlier YYC Ground Sort blank diagram
│   ├── ground_sort_blank_new.png # Current YYC Ground Sort blank canvas (19 labels)
│   └── yyc_ground_filled.png  # YYC Ground Sort answer key
├── static/
│   ├── index.html
│   ├── styles.css
│   └── game.js
└── data/
    └── airport_labeler_memory.json  # Runtime-only; ignored by Git
```

## Customizing locations

`game_data.py` holds the source question bank. Each route has an ID, visible label, category, clue, one or more target paths, and a click tolerance. Coordinates use the `803 × 922` blank-chart image coordinate system. Add or edit entries there to expand the exercise for another airport chart. Validation-mode drawings are saved separately in memory as route overrides, leaving the supplied source bank intact; questions created in the validation editor are stored as persistent custom practice questions.
