"""Apron Ops game mode data, rules, and question generator for CYYC.

Aircraft request either:
- Pushback from a Gate to depart from an assigned runway (departure) -> Controller assigns pushback spot, exit taxiway, ground frequency.
- Apron entry to park at a Gate arriving from an assigned runway (arrival) -> Controller assigns entry taxiway.

Gates:
1-6; 11-24; 31-40; 50-59; 70-76; 78-92; 94-97 (66 gates total).

Runways:
17L, 17R, 35L, 35R.

Rules source:
uploads/Rules_17.png and uploads/Rules_35.png.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from gates_data import GATES_QUESTION_BANK

APRON_OPS_DEFAULT_COUNT = 15

# Load gate coordinates from gates_data for map highlighting
GATE_COORDINATES: dict[int, list[float]] = {}
for _entry in GATES_QUESTION_BANK:
    try:
        _g_num = int(_entry["id"].replace("gate_", ""))
        GATE_COORDINATES[_g_num] = _entry["paths"][0][0]
    except (ValueError, KeyError, IndexError):
        pass

# Gate numbers: 1-6; 11-24; 31-40; 50-59; 70-76; 78-92; 94-97 = 66 gates
GATE_NUMBERS: list[int] = (
    list(range(1, 7))
    + list(range(11, 25))
    + list(range(31, 41))
    + list(range(50, 60))
    + list(range(70, 77))
    + list(range(78, 93))
    + list(range(94, 98))
)

# Concourse mapping for CYYC gates
def gate_concourse(gate: int) -> str:
    if gate in range(1, 7) or gate in range(11, 25):
        return "Concourse A"
    if gate in range(31, 41):
        return "Concourse B"
    if gate in range(50, 60):
        return "Concourse C"
    if gate in range(70, 80):
        return "Concourse D"
    return "Concourse E"

# Gate grouping from Rules_17 and Rules_35:
# Group 1: 1-6, 12, 14, 16, 18, 20
# Group 2: 21-24, 11, 13, 15, 17, 19
# Group 3: 31-40, 50, 52, 54, 56, 58
# Group 4: 51, 53, 55, 57, 59, 70-73, 76
# Group 5: 79, 78, 75, 74, 80, 81, 84, 85, 88, 89, 92
# Group 6: 82, 83, 86, 87, 90, 91, 93, 94, 95, 96, 97
GATE_GROUPS: dict[int, set[int]] = {
    1: {1, 2, 3, 4, 5, 6, 12, 14, 16, 18, 20},
    2: {11, 13, 15, 17, 19, 21, 22, 23, 24},
    3: set(range(31, 41)) | {50, 52, 54, 56, 58},
    4: {51, 53, 55, 57, 59, 70, 71, 72, 73, 76},
    5: {74, 75, 78, 79, 80, 81, 84, 85, 88, 89, 92},
    6: {82, 83, 86, 87, 90, 91, 94, 95, 96, 97},
}

GATE_TO_GROUP: dict[int, int] = {}
for _group_id, _gates in GATE_GROUPS.items():
    for _g in _gates:
        GATE_TO_GROUP[_g] = _group_id

RUNWAYS = ["17L", "17R", "35L", "35R"]

# Pushback spot options
ALL_PUSHBACK_SPOTS = ["4", "5", "6", "7", "10", "11", "14", "15", "16", "17", "23", "24"]

# Apron taxiways
ALL_TAXIWAYS = ["BA", "BC", "E", "EA", "G", "HB", "HD", "JR", "JS", "JT", "K"]

# Ground frequencies
GROUND_WEST = "West Ground (121.9)"
GROUND_EAST = "East Ground (125.35)"
ALL_GROUND_FREQS = [GROUND_WEST, GROUND_EAST]

# Departure Rules: (runway, group_id) -> {"taxiways": [...], "spots": [...], "ground": "..."}
DEPARTURE_RULES: dict[tuple[str, int], dict[str, Any]] = {
    # Departure from 17R
    ("17R", 1): {"taxiways": ["K"], "spots": ["4", "5"], "ground": GROUND_WEST},
    ("17R", 2): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("17R", 3): {"taxiways": ["G"], "spots": ["10", "11"], "ground": GROUND_WEST},
    ("17R", 4): {"taxiways": ["G"], "spots": ["10", "11"], "ground": GROUND_WEST},
    ("17R", 5): {"taxiways": ["JR"], "spots": ["17"], "ground": GROUND_EAST},
    ("17R", 6): {"taxiways": ["BC"], "spots": ["23", "24"], "ground": GROUND_EAST},

    # Departure from 17L
    ("17L", 1): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("17L", 2): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("17L", 3): {"taxiways": ["G"], "spots": ["10", "11"], "ground": GROUND_WEST},
    ("17L", 4): {"taxiways": ["JS"], "spots": ["15"], "ground": GROUND_EAST},
    ("17L", 5): {"taxiways": ["JR"], "spots": ["17"], "ground": GROUND_EAST},
    ("17L", 6): {"taxiways": ["BC"], "spots": ["23", "24"], "ground": GROUND_EAST},

    # Departure from 35L
    ("35L", 1): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("35L", 2): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("35L", 3): {"taxiways": ["G"], "spots": ["10", "11"], "ground": GROUND_WEST},
    ("35L", 4): {"taxiways": ["JT"], "spots": ["14"], "ground": GROUND_WEST},
    ("35L", 5): {"taxiways": ["JR"], "spots": ["17"], "ground": GROUND_EAST},
    ("35L", 6): {"taxiways": ["BC"], "spots": ["23", "24"], "ground": GROUND_EAST},

    # Departure from 35R
    ("35R", 1): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("35R", 2): {"taxiways": ["HB"], "spots": ["6", "7"], "ground": GROUND_WEST},
    ("35R", 3): {"taxiways": ["G"], "spots": ["10", "11"], "ground": GROUND_WEST},
    ("35R", 4): {"taxiways": ["E"], "spots": ["16"], "ground": GROUND_EAST},
    ("35R", 5): {"taxiways": ["JR"], "spots": ["17"], "ground": GROUND_EAST},
    ("35R", 6): {"taxiways": ["BC"], "spots": ["23", "24"], "ground": GROUND_EAST},
}

# Arrival Rules: (runway, group_id) -> list of valid entry taxiways
# Note: For Group 5, "EA/BA" means either EA or BA is valid.
ARRIVAL_RULES: dict[tuple[str, int], list[str]] = {
    # Arrival from 17L / 17R
    ("17L", 1): ["HB"],
    ("17L", 2): ["HB"],
    ("17L", 3): ["HD"],
    ("17L", 4): ["JT"],
    ("17L", 5): ["EA", "BA", "EA/BA"],
    ("17L", 6): ["BA"],

    ("17R", 1): ["HB"],
    ("17R", 2): ["HB"],
    ("17R", 3): ["HD"],
    ("17R", 4): ["JT"],
    ("17R", 5): ["EA", "BA", "EA/BA"],
    ("17R", 6): ["BA"],

    # Arrival from 35L / 35R
    ("35L", 1): ["K"],
    ("35L", 2): ["HB"],
    ("35L", 3): ["HD"],
    ("35L", 4): ["JS"],
    ("35L", 5): ["EA", "BA", "EA/BA"],
    ("35L", 6): ["BA"],

    ("35R", 1): ["K"],
    ("35R", 2): ["HB"],
    ("35R", 3): ["HD"],
    ("35R", 4): ["JS"],
    ("35R", 5): ["EA", "BA", "EA/BA"],
    ("35R", 6): ["BA"],
}

# Realistic aircraft call signs operating at CYYC
CYYC_AIRCRAFT_CALLSIGNS: list[dict[str, str]] = [
    {"callsign": "WestJet 124", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 208", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 224", "aircraft": "B737", "airline": "WestJet"},
    {"callsign": "WestJet 402", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 452", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 655", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 672", "aircraft": "B789", "airline": "WestJet"},
    {"callsign": "WestJet 706", "aircraft": "B789", "airline": "WestJet"},
    {"callsign": "WestJet 1502", "aircraft": "B738", "airline": "WestJet"},
    {"callsign": "WestJet 1740", "aircraft": "B737", "airline": "WestJet"},
    {"callsign": "WestJet 3204", "aircraft": "DH8D", "airline": "WestJet Encore"},
    {"callsign": "Encore 3144", "aircraft": "DH8D", "airline": "WestJet Encore"},
    {"callsign": "Encore 3255", "aircraft": "DH8D", "airline": "WestJet Encore"},
    {"callsign": "Encore 3381", "aircraft": "DH8D", "airline": "WestJet Encore"},
    {"callsign": "Encore 3192", "aircraft": "DH8D", "airline": "WestJet Encore"},
    {"callsign": "Air Canada 115", "aircraft": "A321", "airline": "Air Canada"},
    {"callsign": "Air Canada 137", "aircraft": "A220", "airline": "Air Canada"},
    {"callsign": "Air Canada 204", "aircraft": "B738", "airline": "Air Canada"},
    {"callsign": "Air Canada 221", "aircraft": "A320", "airline": "Air Canada"},
    {"callsign": "Jazz 8214", "aircraft": "CRJ9", "airline": "Air Canada Express"},
    {"callsign": "Jazz 8352", "aircraft": "DH8D", "airline": "Air Canada Express"},
    {"callsign": "Jazz 8412", "aircraft": "CRJ9", "airline": "Air Canada Express"},
    {"callsign": "Flair 201", "aircraft": "B738", "airline": "Flair Airlines"},
    {"callsign": "Flair 302", "aircraft": "B738", "airline": "Flair Airlines"},
    {"callsign": "Flair 508", "aircraft": "B738", "airline": "Flair Airlines"},
    {"callsign": "Porter 311", "aircraft": "E195", "airline": "Porter Airlines"},
    {"callsign": "Porter 452", "aircraft": "E195", "airline": "Porter Airlines"},
    {"callsign": "Delta 1852", "aircraft": "A319", "airline": "Delta Air Lines"},
    {"callsign": "Delta 2419", "aircraft": "B738", "airline": "Delta Air Lines"},
    {"callsign": "United 548", "aircraft": "A320", "airline": "United Airlines"},
    {"callsign": "United 1520", "aircraft": "B739", "airline": "United Airlines"},
    {"callsign": "American 1205", "aircraft": "A319", "airline": "American Airlines"},
    {"callsign": "American 2341", "aircraft": "B738", "airline": "American Airlines"},
    {"callsign": "KLM 677", "aircraft": "B772", "airline": "KLM"},
    {"callsign": "Lufthansa 494", "aircraft": "A359", "airline": "Lufthansa"},
    {"callsign": "Empress 410", "aircraft": "B737", "airline": "Canadian North"},
    {"callsign": "Glacier 112", "aircraft": "DH8C", "airline": "Central Mountain Air"},
]

def generate_apron_ops_question(
    gate: int | None = None,
    runway: str | None = None,
    request_type: str | None = None,
    flight: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a single randomized Apron Ops question."""
    rng = random.SystemRandom()

    if gate is None:
        gate = rng.choice(GATE_NUMBERS)
    if runway is None:
        runway = rng.choice(RUNWAYS)
    if request_type is None:
        request_type = rng.choice(["departure", "arrival"])
    if flight is None:
        flight = rng.choice(CYYC_AIRCRAFT_CALLSIGNS)

    group_id = GATE_TO_GROUP[gate]
    concourse = gate_concourse(gate)
    callsign = flight["callsign"]
    aircraft = flight["aircraft"]
    airline = flight.get("airline", "")

    if request_type == "departure":
        rule = DEPARTURE_RULES[(runway, group_id)]
        correct_taxiways = rule["taxiways"]
        correct_spots = rule["spots"]
        correct_ground = rule["ground"]
        transmission = f"Calgary Apron, {callsign} ({aircraft}) at Gate {gate}, ready for pushback, departing Runway {runway}."
        prompt_title = f"{callsign} · Gate {gate} → Runway {runway}"
        clue = f"Aircraft at Gate {gate} ({concourse}) requesting pushback to exit Apron for Runway {runway}. Assign pushback spot, exit taxiway, and ground frequency."
    else:
        correct_taxiways = ARRIVAL_RULES[(runway, group_id)]
        correct_spots = []
        correct_ground = ""
        transmission = f"Calgary Apron, {callsign} ({aircraft}) inbound on Runway {runway}, requesting apron entry to Gate {gate}."
        prompt_title = f"{callsign} · Runway {runway} → Gate {gate}"
        clue = f"Aircraft on Runway {runway} requesting apron entry to park at Gate {gate} ({concourse}). Assign entry taxiway."

    question_id = f"apron_{uuid.uuid4().hex[:10]}"

    return {
        "id": question_id,
        "label": prompt_title,
        "category": f"Apron {request_type.capitalize()}",
        "request_type": request_type,
        "runway": runway,
        "gate": gate,
        "gate_label": f"Gate {gate}",
        "concourse": concourse,
        "group_id": group_id,
        "callsign": callsign,
        "aircraft": aircraft,
        "airline": airline,
        "transmission": transmission,
        "clue": clue,
        "correct_spots": correct_spots,
        "correct_taxiways": correct_taxiways,
        "correct_ground": correct_ground,
    }


def generate_apron_ops_session(count: int = APRON_OPS_DEFAULT_COUNT) -> list[dict[str, Any]]:
    """Build a balanced list of randomized Apron Ops questions."""
    rng = random.SystemRandom()
    questions: list[dict[str, Any]] = []

    # Distribute between departures and arrivals (approx half each)
    departure_count = count // 2
    arrival_count = count - departure_count

    req_types = (["departure"] * departure_count) + (["arrival"] * arrival_count)
    rng.shuffle(req_types)

    # Pick runways and gates ensuring good variety
    available_gates = list(GATE_NUMBERS)
    rng.shuffle(available_gates)
    gate_idx = 0

    available_flights = list(CYYC_AIRCRAFT_CALLSIGNS)
    rng.shuffle(available_flights)
    flight_idx = 0

    # Ensure all 4 runways are represented
    runway_cycle = list(RUNWAYS)
    rng.shuffle(runway_cycle)

    for i in range(count):
        req = req_types[i]
        runway = runway_cycle[i % len(runway_cycle)]
        gate = available_gates[gate_idx % len(available_gates)]
        gate_idx += 1
        flight = available_flights[flight_idx % len(available_flights)]
        flight_idx += 1

        q = generate_apron_ops_question(
            gate=gate,
            runway=runway,
            request_type=req,
            flight=flight,
        )
        questions.append(q)

    rng.shuffle(questions)
    return questions


def check_apron_ops_answer(question: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    """Verify player's selection against CYYC apron rules.

    For departure:
      Requires spot, taxiway, and ground.
      If multiple spots or taxiways are valid, any valid choice is considered correct.
    For arrival:
      Requires taxiway.
      If multiple taxiways are valid (e.g. EA or BA for EA/BA), any valid choice is considered correct.
    """
    req_type = question.get("request_type", "departure")
    gate = question.get("gate")
    runway = question.get("runway")
    callsign = question.get("callsign", "Aircraft")

    selected_taxiway = str(answer.get("taxiway") or "").strip().upper()
    correct_taxiways = [t.upper() for t in question.get("correct_taxiways", [])]

    # Handle EA/BA split check: if correct_taxiways has "EA/BA", both "EA" and "BA" are valid
    valid_taxiways = set(correct_taxiways)
    if "EA/BA" in valid_taxiways:
        valid_taxiways.add("EA")
        valid_taxiways.add("BA")

    taxiway_correct = selected_taxiway in valid_taxiways

    if req_type == "departure":
        selected_spot = str(answer.get("spot") or "").strip()
        correct_spots = [str(s).strip() for s in question.get("correct_spots", [])]
        spot_correct = selected_spot in correct_spots

        selected_ground = str(answer.get("ground") or "").strip()
        correct_ground = str(question.get("correct_ground", "")).strip()

        # Relax ground frequency matching (allow e.g. "121.9" or "West Ground" or "West Ground (121.9)")
        def normalise_freq(freq: str) -> str:
            f = freq.casefold().replace(" ", "").replace("(", "").replace(")", "")
            return f

        ground_correct = (
            selected_ground == correct_ground
            or normalise_freq(selected_ground) == normalise_freq(correct_ground)
        )

        overall_correct = spot_correct and taxiway_correct and ground_correct

        breakdown = {
            "spot_correct": spot_correct,
            "taxiway_correct": taxiway_correct,
            "ground_correct": ground_correct,
            "selected_spot": selected_spot,
            "selected_taxiway": selected_taxiway,
            "selected_ground": selected_ground,
            "correct_spots": correct_spots,
            "correct_taxiways": question.get("correct_taxiways", []),
            "correct_ground": correct_ground,
        }

        if overall_correct:
            feedback = (
                f"Correct clearance! {callsign} at Gate {gate} instructed to push back to Spot {selected_spot}, "
                f"exit Apron via Taxiway {selected_taxiway}, and contact {correct_ground}."
            )
        else:
            errors = []
            if not spot_correct:
                errors.append(f"Spot: chose '{selected_spot}', expected {' or '.join(correct_spots)}")
            if not taxiway_correct:
                errors.append(f"Exit Taxiway: chose '{selected_taxiway}', expected {' or '.join(question.get('correct_taxiways', []))}")
            if not ground_correct:
                errors.append(f"Ground: chose '{selected_ground}', expected {correct_ground}")
            feedback = (
                f"Incorrect clearance for Gate {gate} departing Runway {runway}. "
                + "; ".join(errors) + "."
            )

        return {
            "correct": overall_correct,
            "feedback": feedback,
            "breakdown": breakdown,
        }

    else:
        # Arrival
        overall_correct = taxiway_correct
        display_expected = [t for t in question.get("correct_taxiways", []) if t != "EA/BA"] or question.get("correct_taxiways", [])

        breakdown = {
            "taxiway_correct": taxiway_correct,
            "selected_taxiway": selected_taxiway,
            "correct_taxiways": display_expected,
        }

        if overall_correct:
            feedback = (
                f"Correct clearance! {callsign} instructed to enter Apron via Taxiway {selected_taxiway} to Gate {gate}."
            )
        else:
            feedback = (
                f"Incorrect entry taxiway for Gate {gate} arriving from Runway {runway}. "
                f"Chose '{selected_taxiway}', expected {' or '.join(display_expected)}."
            )

        return {
            "correct": overall_correct,
            "feedback": feedback,
            "breakdown": breakdown,
        }


def public_apron_ops_question(q: dict[str, Any]) -> dict[str, Any]:
    """Strip secret answers for public client view."""
    return {
        "id": q["id"],
        "label": q["label"],
        "category": q["category"],
        "request_type": q["request_type"],
        "runway": q["runway"],
        "gate": q["gate"],
        "gate_label": q["gate_label"],
        "concourse": q["concourse"],
        "callsign": q["callsign"],
        "aircraft": q["aircraft"],
        "airline": q["airline"],
        "transmission": q["transmission"],
        "clue": q["clue"],
        "coords": GATE_COORDINATES.get(q["gate"]),
        # Provide selectable option lists to the client
        "options": {
            "spots": ALL_PUSHBACK_SPOTS,
            "taxiways": ALL_TAXIWAYS,
            "ground_freqs": ALL_GROUND_FREQS,
        },
    }
