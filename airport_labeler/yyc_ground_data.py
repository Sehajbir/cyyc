"""YYC Ground Sort Program question data.

Coordinates use the 657 x 727 supplied ground_sort_blank_new.png diagram. Each
answer path is a horizontal segment spanning the centre of the matching blank
label box, and the tolerance is tuned so the clickable area covers the whole
box - including its inset corners - without reaching into neighbouring boxes.
After locating a point that carries an aircraft-use classification, the learner
must classify it by permitted traffic type using the supplied answer key.
Corner fixes ADVOX, BIRKO, EBGAL and IGVEP are location-only: their ``use`` is
None and they ask no Jets / Props follow-up question.
"""

from __future__ import annotations

YYC_GROUND_CANVAS_WIDTH = 657
YYC_GROUND_CANVAS_HEIGHT = 727

YYC_GROUND_QUESTION_BANK = [
    {
        "id": "pevlu",
        "label": "PEVLU",
        "category": "YYC ground point",
        "clue": "The north-west point in the upper row of blank labels.",
        "paths": [[[268, 256], [301, 256]]],
        "tolerance": 14,
        "use": "Props",
    },
    {
        "id": "bitga",
        "label": "BITGA",
        "category": "YYC ground point",
        "clue": "The second point in the upper row of blank labels.",
        "paths": [[[336, 262], [359, 262]]],
        "tolerance": 16,
        "use": "Jets",
    },
    {
        "id": "avrom",
        "label": "AVROM",
        "category": "YYC ground point",
        "clue": "The third point in the upper row of blank labels.",
        "paths": [[[393, 270], [422, 270]]],
        "tolerance": 15,
        "use": "Jets",
    },
    {
        "id": "saxol",
        "label": "SAXOL",
        "category": "YYC ground point",
        "clue": "The eastmost point in the upper row of blank labels.",
        "paths": [[[459, 276], [495, 276]]],
        "tolerance": 15,
        "use": "Props",
    },
    {
        "id": "ipsit",
        "label": "IPSIT",
        "category": "YYC ground point",
        "clue": "The upper-left point just west of the blue runway sector.",
        "paths": [[[196, 318], [239, 318]]],
        "tolerance": 13,
        "use": "Jets",
    },
    {
        "id": "agmak",
        "label": "AGMAK",
        "category": "YYC ground point",
        "clue": "The point on the west side near the central blue sector.",
        "paths": [[[113, 398], [170, 398]]],
        "tolerance": 13,
        "use": "Props",
    },
    {
        "id": "vetbi",
        "label": "VETBI",
        "category": "YYC ground point",
        "clue": "The high point on the east side of the yellow runway sector.",
        "paths": [[[540, 364], [573, 364]]],
        "tolerance": 13,
        "use": "Props",
    },
    {
        "id": "botag",
        "label": "BOTAG",
        "category": "YYC ground point",
        "clue": "The middle-west point below the blue runway-sector label.",
        "paths": [[[170, 455], [218, 455]]],
        "tolerance": 13,
        "use": "Jets",
    },
    {
        "id": "lomlo",
        "label": "LOMLO",
        "category": "YYC ground point",
        "clue": "The middle-east point beside the yellow runway-sector label.",
        "paths": [[[490, 472.5], [524, 472.5]]],
        "tolerance": 13,
        "use": "Jets",
    },
    {
        "id": "nosiv",
        "label": "NOSIV",
        "category": "YYC ground point",
        "clue": "The lower-east point near the outside edge of the yellow sector.",
        "paths": [[[508, 516.5], [550, 516.5]]],
        "tolerance": 13,
        "use": "Jets or Props",
    },
    {
        "id": "rovma",
        "label": "ROVMA",
        "category": "YYC ground point",
        "clue": "The lower-west point below BOTAG.",
        "paths": [[[146, 479.5], [197, 479.5]]],
        "tolerance": 13,
        "use": "Props",
    },
    {
        "id": "gadki",
        "label": "GADKI",
        "category": "YYC ground point",
        "clue": "The east-side point in the lower row of blank labels.",
        "paths": [[[421, 631], [456, 631]]],
        "tolerance": 15,
        "use": "Jets or Props",
    },
    {
        "id": "ubval",
        "label": "UBVAL",
        "category": "YYC ground point",
        "clue": "The central point in the lower row of blank labels.",
        "paths": [[[362, 650.5], [390, 650.5]]],
        "tolerance": 13,
        "use": "Jets or Props",
    },
    {
        "id": "otara",
        "label": "OTARA",
        "category": "YYC ground point",
        "clue": "The westmost point in the lower centre row.",
        "paths": [[[303, 655.5], [332, 655.5]]],
        "tolerance": 15,
        "use": "Jets or Props",
    },
    {
        "id": "dumra",
        "label": "DUMRA",
        "category": "YYC ground point",
        "clue": "The low western point above the Fortresses/Foothills sector line.",
        "paths": [[[219, 690], [255, 690]]],
        "tolerance": 13,
        "use": "Jets or Props",
    },
    {
        "id": "advox",
        "label": "ADVOX",
        "category": "YYC ground point",
        "clue": "The blank corner label at the top-west of the diagram, above the blue sector.",
        "paths": [[[178, 167.5], [221, 167.5]]],
        "tolerance": 19,
        "use": None,
    },
    {
        "id": "birko",
        "label": "BIRKO",
        "category": "YYC ground point",
        "clue": "The blank corner label at the top-east of the diagram, beside the yellow sector.",
        "paths": [[[579, 275.5], [620, 275.5]]],
        "tolerance": 17,
        "use": None,
    },
    {
        "id": "ebgal",
        "label": "EBGAL",
        "category": "YYC ground point",
        "clue": "The blank corner label at the bottom-east of the diagram, below the yellow sector.",
        "paths": [[[567, 621.5], [612, 621.5]]],
        "tolerance": 15,
        "use": None,
    },
    {
        "id": "igvep",
        "label": "IGVEP",
        "category": "YYC ground point",
        "clue": "The blank corner label at the bottom-west of the diagram, left of the blue sector.",
        "paths": [[[88, 606], [136, 606]]],
        "tolerance": 15,
        "use": None,
    },
]

YYC_GROUND_BY_ID = {question["id"]: question for question in YYC_GROUND_QUESTION_BANK}
