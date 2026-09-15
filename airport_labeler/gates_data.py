"""Gates identification question data.

Source image: uploads/Gates.png (1377x857).
Gates numbered: 1-6, 11-24, 31-40, 50-59, 70-76, 78-92, 94-97 = 66 total.
Coordinates are in original image pixels, precisely detected via blue-circle color threshold.
Each gate is a single-point target with tolerance.
"""

from __future__ import annotations

GATES_CANVAS_WIDTH = 1377
GATES_CANVAS_HEIGHT = 857

GATES_QUESTION_BANK = [
    {"id": "gate_01", "label": "Gate 1", "category": "Concourse A", "clue": "Locate Gate 1 on the airport diagram.", "paths": [[[261.4, 207.4]]], "tolerance": 26},
    {"id": "gate_02", "label": "Gate 2", "category": "Concourse A", "clue": "Locate Gate 2 on the airport diagram.", "paths": [[[262.0, 155.4]]], "tolerance": 26},
    {"id": "gate_03", "label": "Gate 3", "category": "Concourse A", "clue": "Locate Gate 3 on the airport diagram.", "paths": [[[260.6, 123.0]]], "tolerance": 26},
    {"id": "gate_04", "label": "Gate 4", "category": "Concourse A", "clue": "Locate Gate 4 on the airport diagram.", "paths": [[[259.5, 89.0]]], "tolerance": 26},
    {"id": "gate_05", "label": "Gate 5", "category": "Concourse A", "clue": "Locate Gate 5 on the airport diagram.", "paths": [[[260.2, 55.4]]], "tolerance": 26},
    {"id": "gate_06", "label": "Gate 6", "category": "Concourse A", "clue": "Locate Gate 6 on the airport diagram.", "paths": [[[259.5, 22.0]]], "tolerance": 26},
    {"id": "gate_11", "label": "Gate 11", "category": "Concourse A", "clue": "Locate Gate 11 on the airport diagram.", "paths": [[[199.0, 359.5]]], "tolerance": 26},
    {"id": "gate_12", "label": "Gate 12", "category": "Concourse A", "clue": "Locate Gate 12 on the airport diagram.", "paths": [[[233.9, 245.3]]], "tolerance": 26},
    {"id": "gate_13", "label": "Gate 13", "category": "Concourse A", "clue": "Locate Gate 13 on the airport diagram.", "paths": [[[157.1, 355.2]]], "tolerance": 26},
    {"id": "gate_14", "label": "Gate 14", "category": "Concourse A", "clue": "Locate Gate 14 on the airport diagram.", "paths": [[[188.6, 245.4]]], "tolerance": 26},
    {"id": "gate_15", "label": "Gate 15", "category": "Concourse A", "clue": "Locate Gate 15 on the airport diagram.", "paths": [[[109.0, 365.9]]], "tolerance": 26},
    {"id": "gate_16", "label": "Gate 16", "category": "Concourse A", "clue": "Locate Gate 16 on the airport diagram.", "paths": [[[136.7, 237.9]]], "tolerance": 26},
    {"id": "gate_17", "label": "Gate 17", "category": "Concourse A", "clue": "Locate Gate 17 on the airport diagram.", "paths": [[[68.6, 347.0]]], "tolerance": 26},
    {"id": "gate_18", "label": "Gate 18", "category": "Concourse A", "clue": "Locate Gate 18 on the airport diagram.", "paths": [[[94.9, 242.0]]], "tolerance": 26},
    {"id": "gate_19", "label": "Gate 19", "category": "Concourse A", "clue": "Locate Gate 19 on the airport diagram.", "paths": [[[54.6, 306.9]]], "tolerance": 26},
    {"id": "gate_20", "label": "Gate 20", "category": "Concourse A", "clue": "Locate Gate 20 on the airport diagram.", "paths": [[[60.8, 268.0]]], "tolerance": 26},
    {"id": "gate_21", "label": "Gate 21", "category": "Concourse A", "clue": "Locate Gate 21 on the airport diagram.", "paths": [[[250.1, 372.1]]], "tolerance": 26},
    {"id": "gate_22", "label": "Gate 22", "category": "Concourse A", "clue": "Locate Gate 22 on the airport diagram.", "paths": [[[262.8, 410.5]]], "tolerance": 26},
    {"id": "gate_23", "label": "Gate 23", "category": "Concourse A", "clue": "Locate Gate 23 on the airport diagram.", "paths": [[[269.6, 449.0]]], "tolerance": 26},
    {"id": "gate_24", "label": "Gate 24", "category": "Concourse A", "clue": "Locate Gate 24 on the airport diagram.", "paths": [[[293.9, 482.6]]], "tolerance": 26},
    {"id": "gate_31", "label": "Gate 31", "category": "Concourse B", "clue": "Locate Gate 31 on the airport diagram.", "paths": [[[393.1, 616.2]]], "tolerance": 26},
    {"id": "gate_32", "label": "Gate 32", "category": "Concourse B", "clue": "Locate Gate 32 on the airport diagram.", "paths": [[[298.6, 572.5]]], "tolerance": 26},
    {"id": "gate_33", "label": "Gate 33", "category": "Concourse B", "clue": "Locate Gate 33 on the airport diagram.", "paths": [[[369.5, 647.9]]], "tolerance": 26},
    {"id": "gate_34", "label": "Gate 34", "category": "Concourse B", "clue": "Locate Gate 34 on the airport diagram.", "paths": [[[263.7, 610.3]]], "tolerance": 26},
    {"id": "gate_35", "label": "Gate 35", "category": "Concourse B", "clue": "Locate Gate 35 on the airport diagram.", "paths": [[[338.2, 675.3]]], "tolerance": 26},
    {"id": "gate_36", "label": "Gate 36", "category": "Concourse B", "clue": "Locate Gate 36 on the airport diagram.", "paths": [[[229.8, 631.4]]], "tolerance": 26},
    {"id": "gate_37", "label": "Gate 37", "category": "Concourse B", "clue": "Locate Gate 37 on the airport diagram.", "paths": [[[320.5, 715.1]]], "tolerance": 26},
    {"id": "gate_38", "label": "Gate 38", "category": "Concourse B", "clue": "Locate Gate 38 on the airport diagram.", "paths": [[[218.0, 667.0]]], "tolerance": 26},
    {"id": "gate_39", "label": "Gate 39", "category": "Concourse B", "clue": "Locate Gate 39 on the airport diagram.", "paths": [[[266.2, 726.3]]], "tolerance": 26},
    {"id": "gate_40", "label": "Gate 40", "category": "Concourse B", "clue": "Locate Gate 40 on the airport diagram.", "paths": [[[232.7, 702.7]]], "tolerance": 26},
    {"id": "gate_50", "label": "Gate 50", "category": "Concourse C", "clue": "Locate Gate 50 on the airport diagram.", "paths": [[[496.9, 648.8]]], "tolerance": 26},
    {"id": "gate_51", "label": "Gate 51", "category": "Concourse C", "clue": "Locate Gate 51 on the airport diagram.", "paths": [[[603.2, 665.1]]], "tolerance": 26},
    {"id": "gate_52", "label": "Gate 52", "category": "Concourse C", "clue": "Locate Gate 52 on the airport diagram.", "paths": [[[494.5, 683.8]]], "tolerance": 26},
    {"id": "gate_53", "label": "Gate 53", "category": "Concourse C", "clue": "Locate Gate 53 on the airport diagram.", "paths": [[[605.1, 708.2]]], "tolerance": 26},
    {"id": "gate_54", "label": "Gate 54", "category": "Concourse C", "clue": "Locate Gate 54 on the airport diagram.", "paths": [[[489.4, 721.0]]], "tolerance": 26},
    {"id": "gate_55", "label": "Gate 55", "category": "Concourse C", "clue": "Locate Gate 55 on the airport diagram.", "paths": [[[607.9, 743.4]]], "tolerance": 26},
    {"id": "gate_56", "label": "Gate 56", "category": "Concourse C", "clue": "Locate Gate 56 on the airport diagram.", "paths": [[[489.8, 763.4]]], "tolerance": 26},
    {"id": "gate_57", "label": "Gate 57", "category": "Concourse C", "clue": "Locate Gate 57 on the airport diagram.", "paths": [[[599.6, 783.1]]], "tolerance": 26},
    {"id": "gate_58", "label": "Gate 58", "category": "Concourse C", "clue": "Locate Gate 58 on the airport diagram.", "paths": [[[518.7, 795.3]]], "tolerance": 26},
    {"id": "gate_59", "label": "Gate 59", "category": "Concourse C", "clue": "Locate Gate 59 on the airport diagram.", "paths": [[[559.3, 799.0]]], "tolerance": 26},
    {"id": "gate_70", "label": "Gate 70", "category": "Concourse D", "clue": "Locate Gate 70 on the airport diagram.", "paths": [[[728.2, 634.1]]], "tolerance": 26},
    {"id": "gate_71", "label": "Gate 71", "category": "Concourse D", "clue": "Locate Gate 71 on the airport diagram.", "paths": [[[760.5, 655.2]]], "tolerance": 26},
    {"id": "gate_72", "label": "Gate 72", "category": "Concourse D", "clue": "Locate Gate 72 on the airport diagram.", "paths": [[[766.2, 696.0]]], "tolerance": 26},
    {"id": "gate_73", "label": "Gate 73", "category": "Concourse D", "clue": "Locate Gate 73 on the airport diagram.", "paths": [[[782.9, 733.9]]], "tolerance": 26},
    {"id": "gate_74", "label": "Gate 74", "category": "Concourse D", "clue": "Locate Gate 74 on the airport diagram.", "paths": [[[913.7, 758.9]]], "tolerance": 26},
    {"id": "gate_75", "label": "Gate 75", "category": "Concourse D", "clue": "Locate Gate 75 on the airport diagram.", "paths": [[[929.9, 705.5]]], "tolerance": 26},
    {"id": "gate_76", "label": "Gate 76", "category": "Concourse D", "clue": "Locate Gate 76 on the airport diagram.", "paths": [[[789.5, 812.6]]], "tolerance": 32},
    {"id": "gate_78", "label": "Gate 78", "category": "Concourse D", "clue": "Locate Gate 78 on the airport diagram.", "paths": [[[927.2, 834.9]]], "tolerance": 26},
    {"id": "gate_79", "label": "Gate 79", "category": "Concourse D", "clue": "Locate Gate 79 on the airport diagram.", "paths": [[[894.7, 808.6]]], "tolerance": 32},
    {"id": "gate_80", "label": "Gate 80", "category": "Concourse E", "clue": "Locate Gate 80 on the airport diagram.", "paths": [[[986.4, 703.0]]], "tolerance": 26},
    {"id": "gate_81", "label": "Gate 81", "category": "Concourse E", "clue": "Locate Gate 81 on the airport diagram.", "paths": [[[1018.9, 669.5]]], "tolerance": 26},
    {"id": "gate_82", "label": "Gate 82", "category": "Concourse E", "clue": "Locate Gate 82 on the airport diagram.", "paths": [[[957.1, 530.8]]], "tolerance": 26},
    {"id": "gate_83", "label": "Gate 83", "category": "Concourse E", "clue": "Locate Gate 83 on the airport diagram.", "paths": [[[1004.5, 516.0]]], "tolerance": 26},
    {"id": "gate_84", "label": "Gate 84", "category": "Concourse E", "clue": "Locate Gate 84 on the airport diagram.", "paths": [[[1083.5, 680.9]]], "tolerance": 26},
    {"id": "gate_85", "label": "Gate 85", "category": "Concourse E", "clue": "Locate Gate 85 on the airport diagram.", "paths": [[[1115.2, 645.4]]], "tolerance": 26},
    {"id": "gate_86", "label": "Gate 86", "category": "Concourse E", "clue": "Locate Gate 86 on the airport diagram.", "paths": [[[1072.5, 549.0]]], "tolerance": 26},
    {"id": "gate_87", "label": "Gate 87", "category": "Concourse E", "clue": "Locate Gate 87 on the airport diagram.", "paths": [[[1111.2, 507.8]]], "tolerance": 26},
    {"id": "gate_88", "label": "Gate 88", "category": "Concourse E", "clue": "Locate Gate 88 on the airport diagram.", "paths": [[[1154.8, 683.9]]], "tolerance": 26},
    {"id": "gate_89", "label": "Gate 89", "category": "Concourse E", "clue": "Locate Gate 89 on the airport diagram.", "paths": [[[1192.4, 651.4]]], "tolerance": 26},
    {"id": "gate_90", "label": "Gate 90", "category": "Concourse E", "clue": "Locate Gate 90 on the airport diagram.", "paths": [[[1149.2, 550.0]]], "tolerance": 26},
    {"id": "gate_91", "label": "Gate 91", "category": "Concourse E", "clue": "Locate Gate 91 on the airport diagram.", "paths": [[[1184.1, 505.9]]], "tolerance": 26},
    {"id": "gate_92", "label": "Gate 92", "category": "Concourse E", "clue": "Locate Gate 92 on the airport diagram.", "paths": [[[1260.0, 662.2]]], "tolerance": 26},
    {"id": "gate_94", "label": "Gate 94", "category": "Concourse E", "clue": "Locate Gate 94 on the airport diagram.", "paths": [[[1230.7, 550.6]]], "tolerance": 26},
    {"id": "gate_95", "label": "Gate 95", "category": "Concourse E", "clue": "Locate Gate 95 on the airport diagram.", "paths": [[[1269.5, 510.1]]], "tolerance": 26},
    {"id": "gate_96", "label": "Gate 96", "category": "Concourse E", "clue": "Locate Gate 96 on the airport diagram.", "paths": [[[1312.0, 501.2]]], "tolerance": 26},
    {"id": "gate_97", "label": "Gate 97", "category": "Concourse E", "clue": "Locate Gate 97 on the airport diagram.", "paths": [[[1338.0, 530.7]]], "tolerance": 26},
]

GATES_BY_ID = {q["id"]: q for q in GATES_QUESTION_BANK}

def public_gates_question(qid: str) -> dict:
    q = GATES_BY_ID[qid]
    return {"id": q["id"], "label": q["label"], "category": q["category"], "clue": q["clue"]}

def public_gates_hint(qid: str) -> dict:
    q = GATES_BY_ID[qid]
    return {"id": q["id"], "label": q["label"], "paths": q["paths"], "tolerance": q["tolerance"]}
