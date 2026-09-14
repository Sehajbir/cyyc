"""YYC Ground Sort Program question data.

Coordinates use the 550 x 701 supplied yyc_ground_blank.png diagram. Each point is
the centre of the matching blank label box. After locating a point, the learner must
classify it by permitted traffic type using the supplied answer key.
"""

from __future__ import annotations

YYC_GROUND_CANVAS_WIDTH = 550
YYC_GROUND_CANVAS_HEIGHT = 701

YYC_GROUND_QUESTION_BANK = [
    {
        "id": "pevlu",
        "label": "PEVLU",
        "category": "YYC ground point",
        "clue": "The north-west point in the upper row of blank labels.",
        "paths": [[[236, 215]]],
        "tolerance": 29,
        "use": "Props",
    },
    {
        "id": "bitga",
        "label": "BITGA",
        "category": "YYC ground point",
        "clue": "The second point in the upper row of blank labels.",
        "paths": [[[290, 227]]],
        "tolerance": 29,
        "use": "Jets",
    },
    {
        "id": "avrom",
        "label": "AVROM",
        "category": "YYC ground point",
        "clue": "The third point in the upper row of blank labels.",
        "paths": [[[344, 227]]],
        "tolerance": 29,
        "use": "Jets",
    },
    {
        "id": "saxol",
        "label": "SAXOL",
        "category": "YYC ground point",
        "clue": "The eastmost point in the upper row of blank labels.",
        "paths": [[[397, 234]]],
        "tolerance": 29,
        "use": "Props",
    },
    {
        "id": "ipsit",
        "label": "IPSIT",
        "category": "YYC ground point",
        "clue": "The upper-left point just west of the blue runway sector.",
        "paths": [[[174, 264]]],
        "tolerance": 29,
        "use": "Jets",
    },
    {
        "id": "agmak",
        "label": "AGMAK",
        "category": "YYC ground point",
        "clue": "The point on the west side near the central blue sector.",
        "paths": [[[137, 335]]],
        "tolerance": 29,
        "use": "Props",
    },
    {
        "id": "vetbi",
        "label": "VETBI",
        "category": "YYC ground point",
        "clue": "The high point on the east side of the yellow runway sector.",
        "paths": [[[462, 310]]],
        "tolerance": 29,
        "use": "Props",
    },
    {
        "id": "botag",
        "label": "BOTAG",
        "category": "YYC ground point",
        "clue": "The middle-west point below the blue runway-sector label.",
        "paths": [[[124, 404]]],
        "tolerance": 29,
        "use": "Jets",
    },
    {
        "id": "lomlo",
        "label": "LOMLO",
        "category": "YYC ground point",
        "clue": "The middle-east point beside the yellow runway-sector label.",
        "paths": [[[428, 405]]],
        "tolerance": 29,
        "use": "Jets",
    },
    {
        "id": "nosiv",
        "label": "NOSIV",
        "category": "YYC ground point",
        "clue": "The lower-east point near the outside edge of the yellow sector.",
        "paths": [[[451, 441]]],
        "tolerance": 29,
        "use": "Jets or Props",
    },
    {
        "id": "rovma",
        "label": "ROVMA",
        "category": "YYC ground point",
        "clue": "The lower-west point below BOTAG.",
        "paths": [[[140, 447]]],
        "tolerance": 29,
        "use": "Props",
    },
    {
        "id": "gadki",
        "label": "GADKI",
        "category": "YYC ground point",
        "clue": "The east-side point in the lower row of blank labels.",
        "paths": [[[365, 540]]],
        "tolerance": 29,
        "use": "Jets or Props",
    },
    {
        "id": "ubval",
        "label": "UBVAL",
        "category": "YYC ground point",
        "clue": "The central point in the lower row of blank labels.",
        "paths": [[[314, 553]]],
        "tolerance": 29,
        "use": "Jets or Props",
    },
    {
        "id": "otara",
        "label": "OTARA",
        "category": "YYC ground point",
        "clue": "The westmost point in the lower centre row.",
        "paths": [[[262, 560]]],
        "tolerance": 29,
        "use": "Jets or Props",
    },
    {
        "id": "dumra",
        "label": "DUMRA",
        "category": "YYC ground point",
        "clue": "The low western point above the Fortresses/Foothills sector line.",
        "paths": [[[195, 591]]],
        "tolerance": 29,
        "use": "Jets or Props",
    },
]

YYC_GROUND_BY_ID = {question["id"]: question for question in YYC_GROUND_QUESTION_BANK}
