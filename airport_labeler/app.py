#!/usr/bin/env python3
"""Airport Label Quest — dependency-free local web game.

Run with:
    python app.py

Then open http://localhost:8000 in a browser. The shared question bank and each
player's progress are saved in data/airport_labeler_memory.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import mimetypes
import os
import random
import tempfile
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from game_data import CANVAS_HEIGHT, CANVAS_WIDTH, QUESTION_BANK
from locations_data import LOCATIONS_CANVAS_HEIGHT, LOCATIONS_CANVAS_WIDTH, LOCATION_QUESTION_BANK
from yyc_ground_data import YYC_GROUND_CANVAS_HEIGHT, YYC_GROUND_CANVAS_WIDTH, YYC_GROUND_QUESTION_BANK
from gates_data import GATES_CANVAS_HEIGHT, GATES_CANVAS_WIDTH, GATES_QUESTION_BANK
from apron_ops_data import (
    generate_apron_ops_session,
    check_apron_ops_answer,
    public_apron_ops_question,
    APRON_OPS_DEFAULT_COUNT,
)
from quizlet_import import QuizletImportError, normalise_quizlet_url, parse_quizlet_pdf

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
ASSETS_DIR = ROOT / "assets"
UPLOADS_DIR = ROOT.parent / "uploads" if (ROOT.parent / "uploads").exists() else ROOT / "assets"
# Deployments should point this at a persistent mounted volume. Local development
# keeps the original project-relative data directory by default.
DATA_DIR = Path(os.environ.get("AIRPORT_LABELER_DATA_DIR", str(ROOT / "data"))).expanduser()
MEMORY_FILE = DATA_DIR / "airport_labeler_memory.json"
CURATED_MAIN_BANK_FILE = ROOT / "question_bank_curated.json"
FLASHCARD_STATES = {"new", "easy", "mid", "hard"}
FLASHCARD_IMAGE_PATTERN = re.compile(r"^data:image/(?:png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=]+)$", re.IGNORECASE)
QUIZLET_PDF_PATTERN = re.compile(r"^data:application/(?:pdf|octet-stream);base64,([A-Za-z0-9+/=]+)$", re.IGNORECASE)
QUIZLET_PDF_MAX_BYTES = 15_000_000


class APIError(Exception):
    """An error which can be shown safely in the browser."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.status = int(status)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise APIError(f"{label} must be a number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise APIError(f"{label} must be a number.") from error
    if not math.isfinite(result):
        raise APIError(f"{label} must be finite.")
    return result


def cleaned_text(value: Any, label: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        if required:
            raise APIError(f"{label} is required.")
        return ""
    result = " ".join(value.strip().split())
    if required and not result:
        raise APIError(f"{label} is required.")
    if len(result) > maximum:
        raise APIError(f"{label} must be {maximum} characters or fewer.")
    return result


def point_to_segment_distance(x: float, y: float, a: list[float], b: list[float]) -> float:
    """Shortest Euclidean distance between point (x, y) and segment a-b."""
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(x - ax, y - ay)
    t = ((x - ax) * dx + (y - ay) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    nearest_x = ax + t * dx
    nearest_y = ay + t * dy
    return math.hypot(x - nearest_x, y - nearest_y)


def hit_test(question: dict[str, Any], x: float, y: float) -> bool:
    """Return True when the clicked point is close to one of a route's paths."""
    tolerance = float(question["tolerance"])
    for path in question["paths"]:
        if len(path) == 1 and math.hypot(x - path[0][0], y - path[0][1]) <= tolerance:
            return True
        for start, end in zip(path, path[1:]):
            if point_to_segment_distance(x, y, start, end) <= tolerance:
                return True
    return False


def normalise_drawn_paths(
    raw_paths: Any,
    canvas_width: int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
    allow_point_paths: bool = False,
) -> list[list[list[float]]]:
    """Validate and compact route strokes for a specific map canvas."""
    if not isinstance(raw_paths, list) or not raw_paths:
        raise APIError("Draw at least one route stroke before saving it.")
    if len(raw_paths) > 12:
        raise APIError("A route can contain at most 12 separate strokes.")

    paths: list[list[list[float]]] = []
    total_points = 0
    for path_index, raw_path in enumerate(raw_paths, start=1):
        if not isinstance(raw_path, list):
            raise APIError(f"Route stroke {path_index} is invalid.")
        if len(raw_path) > 500:
            raise APIError(f"Route stroke {path_index} has too many points.")

        compact: list[list[float]] = []
        for point_index, raw_point in enumerate(raw_path, start=1):
            if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
                raise APIError(f"Point {point_index} in route stroke {path_index} is invalid.")
            x = finite_number(raw_point[0], "route x")
            y = finite_number(raw_point[1], "route y")
            if not (-8 <= x <= canvas_width + 8 and -8 <= y <= canvas_height + 8):
                raise APIError("A drawn route must stay on the airport chart.")
            point = [round(x, 1), round(y, 1)]
            # Ignore tiny freehand jitters while preserving the intended shape.
            if not compact or math.hypot(point[0] - compact[-1][0], point[1] - compact[-1][1]) >= 1.8:
                compact.append(point)

        if len(compact) < 2 and not (allow_point_paths and len(compact) == 1):
            raise APIError(f"Route stroke {path_index} needs a visible length.")
        if len(compact) >= 2:
            route_length = sum(
                math.hypot(end[0] - start[0], end[1] - start[1])
                for start, end in zip(compact, compact[1:])
            )
            if route_length < 5:
                raise APIError(f"Route stroke {path_index} is too short to use as an answer.")
        paths.append(compact)
        total_points += len(compact)

    if total_points > 1500:
        raise APIError("That route contains too many points.")
    return paths


class GameStore:
    """Thread-safe persistent store for a shared question bank and user profiles."""

    def __init__(self, memory_file: Path):
        self.memory_file = memory_file
        self.lock = threading.RLock()
        self.memory = self._load()

    # ------------------------------------------------------------------
    # Schema and user profiles
    # ------------------------------------------------------------------
    @staticmethod
    def _empty_profile(display_name: str) -> dict[str, Any]:
        now = utc_now()
        return {
            "display_name": display_name,
            "created_at": now,
            "last_active_at": now,
            "active_game": None,
            "active_locations_game": None,
            "active_yyc_ground_game": None,
            "active_gates_game": None,
            "active_apron_ops_game": None,
            "active_validation": None,
            "active_locations_validation": None,
            "active_yyc_ground_validation": None,
            "sessions": [],
            "location_sessions": [],
            "yyc_ground_sessions": [],
            "gates_sessions": [],
            "apron_ops_sessions": [],
            "validation_sessions": [],
            "locations_validation_sessions": [],
            "yyc_ground_validation_sessions": [],
            "question_stats": {},
            "location_question_stats": {},
            "yyc_ground_question_stats": {},
            "gates_question_stats": {},
            "apron_ops_question_stats": {},
            "last_completed": None,
            "last_locations_completed": None,
            "last_yyc_ground_completed": None,
            "last_gates_completed": None,
            "last_apron_ops_completed": None,
            "last_validation": None,
            "last_locations_validation": None,
            "last_yyc_ground_validation": None,
            "flashcard_decks": [],
        }

    @staticmethod
    def _empty_memory() -> dict[str, Any]:
        return {
            "schema_version": 11,
            # Profiles hold user-specific game progress, trends, and validation
            # drafts. The bank configuration below is shared by every user.
            "users": {},
            "route_overrides": {},
            "question_overrides": {},
            "custom_questions": [],
            "location_route_overrides": {},
            "location_question_overrides": {},
            "location_custom_questions": [],
            "yyc_ground_route_overrides": {},
            "yyc_ground_question_overrides": {},
            "yyc_ground_custom_questions": [],
            # Imported bank snapshots replace these sources globally when present.
            "question_bank_override": None,
            "location_bank_override": None,
            "yyc_ground_bank_override": None
        }

    @staticmethod
    def _legacy_has_user_data(loaded: dict[str, Any]) -> bool:
        keys = (
            "active_game", "active_locations_game", "active_yyc_ground_game", "active_gates_game", "active_apron_ops_game",
            "active_validation", "active_locations_validation", "active_yyc_ground_validation",
            "sessions", "location_sessions", "yyc_ground_sessions", "gates_sessions", "apron_ops_sessions",
            "validation_sessions", "locations_validation_sessions", "yyc_ground_validation_sessions",
            "question_stats", "location_question_stats", "yyc_ground_question_stats", "gates_question_stats", "apron_ops_question_stats",
            "last_completed", "last_locations_completed", "last_yyc_ground_completed", "last_gates_completed", "last_apron_ops_completed",
            "last_validation", "last_locations_validation", "last_yyc_ground_validation", "flashcard_decks",
        )
        for key in keys:
            value = loaded.get(key)
            if value not in (None, [], {}, ""):
                return True
        return False

    def _legacy_profile(self, loaded: dict[str, Any]) -> dict[str, Any]:
        profile = self._empty_profile("Guest")
        for key in (
            "active_game", "active_locations_game", "active_yyc_ground_game", "active_gates_game", "active_apron_ops_game",
            "active_validation", "active_locations_validation", "active_yyc_ground_validation",
            "sessions", "location_sessions", "yyc_ground_sessions", "gates_sessions", "apron_ops_sessions",
            "validation_sessions", "locations_validation_sessions", "yyc_ground_validation_sessions",
            "question_stats", "location_question_stats", "yyc_ground_question_stats", "gates_question_stats", "apron_ops_question_stats",
            "last_completed", "last_locations_completed", "last_yyc_ground_completed", "last_gates_completed", "last_apron_ops_completed",
            "last_validation", "last_locations_validation", "last_yyc_ground_validation", "flashcard_decks",
        ):
            if key in loaded:
                profile[key] = deepcopy(loaded[key])
        return profile

    def _normalise_loaded_profile(self, raw: Any, fallback_name: str) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        display_name = raw.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = fallback_name
        try:
            display_name = cleaned_text(display_name, "Username", 32)
        except APIError:
            return None
        profile = self._empty_profile(display_name)
        for key in profile:
            if key in raw:
                profile[key] = deepcopy(raw[key])
        profile["display_name"] = display_name
        for list_key in ("sessions", "location_sessions", "yyc_ground_sessions", "gates_sessions", "apron_ops_sessions", "apron_ops_sessions", "validation_sessions", "locations_validation_sessions", "yyc_ground_validation_sessions", "flashcard_decks"):
            if not isinstance(profile[list_key], list):
                profile[list_key] = []
        for dict_key in ("question_stats", "location_question_stats", "yyc_ground_question_stats", "gates_question_stats", "apron_ops_question_stats", "apron_ops_question_stats"):
            if not isinstance(profile[dict_key], dict):
                profile[dict_key] = {}
        if profile["active_game"] is not None and not isinstance(profile["active_game"], dict):
            profile["active_game"] = None
        if profile["active_locations_game"] is not None and not isinstance(profile["active_locations_game"], dict):
            profile["active_locations_game"] = None
        if profile["active_yyc_ground_game"] is not None and not isinstance(profile["active_yyc_ground_game"], dict):
            profile["active_yyc_ground_game"] = None
        if profile["active_gates_game"] is not None and not isinstance(profile["active_gates_game"], dict):
            profile["active_gates_game"] = None
        if profile["active_apron_ops_game"] is not None and not isinstance(profile["active_apron_ops_game"], dict):
            profile["active_apron_ops_game"] = None
        if profile["active_validation"] is not None and not isinstance(profile["active_validation"], dict):
            profile["active_validation"] = None
        if profile["active_locations_validation"] is not None and not isinstance(profile["active_locations_validation"], dict):
            profile["active_locations_validation"] = None
        if profile["active_yyc_ground_validation"] is not None and not isinstance(profile["active_yyc_ground_validation"], dict):
            profile["active_yyc_ground_validation"] = None
        if profile["active_game"]:
            profile["active_game"]["running_since"] = None
        if profile["active_locations_game"]:
            profile["active_locations_game"]["running_since"] = None
        if profile["active_yyc_ground_game"]:
            profile["active_yyc_ground_game"]["running_since"] = None
        if profile["active_gates_game"]:
            profile["active_gates_game"]["running_since"] = None
        if profile["active_apron_ops_game"]:
            profile["active_apron_ops_game"]["running_since"] = None
        if profile["active_validation"]:
            profile["active_validation"]["running_since"] = None
            profile["active_validation"].setdefault("phase", "review")
            profile["active_validation"].setdefault("draft_custom_questions", [])
            profile["active_validation"].setdefault("draft_question_overrides", {})
            profile["active_validation"].setdefault("skipped_count", 0)
        if profile["active_locations_validation"]:
            profile["active_locations_validation"]["running_since"] = None
            profile["active_locations_validation"].setdefault("phase", "review")
            profile["active_locations_validation"].setdefault("draft_custom_questions", [])
            profile["active_locations_validation"].setdefault("draft_question_overrides", {})
            profile["active_locations_validation"].setdefault("skipped_count", 0)
        if profile["active_yyc_ground_validation"]:
            profile["active_yyc_ground_validation"]["running_since"] = None
            profile["active_yyc_ground_validation"].setdefault("phase", "review")
            profile["active_yyc_ground_validation"].setdefault("draft_custom_questions", [])
            profile["active_yyc_ground_validation"].setdefault("draft_question_overrides", {})
            profile["active_yyc_ground_validation"].setdefault("skipped_count", 0)
        return profile

    def _load(self) -> dict[str, Any]:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            return self._empty_memory()
        try:
            with self.memory_file.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            if not isinstance(loaded, dict):
                raise ValueError("Memory root is not an object")
        except (OSError, ValueError, json.JSONDecodeError):
            try:
                backup = self.memory_file.with_suffix(".corrupt.json")
                self.memory_file.replace(backup)
            except OSError:
                pass
            return self._empty_memory()

        # Versions 1–4 stored one user's data at the root. Preserve it as Guest
        # rather than silently losing progress during the multi-user migration.
        if not isinstance(loaded.get("users"), dict):
            memory = self._empty_memory()
            memory["route_overrides"] = loaded.get("route_overrides", {})
            memory["question_overrides"] = loaded.get("question_overrides", {})
            memory["custom_questions"] = loaded.get("custom_questions", [])
            memory["location_route_overrides"] = loaded.get("location_route_overrides", {})
            memory["location_question_overrides"] = loaded.get("location_question_overrides", {})
            memory["location_custom_questions"] = loaded.get("location_custom_questions", [])
            memory["yyc_ground_route_overrides"] = loaded.get("yyc_ground_route_overrides", {})
            memory["yyc_ground_question_overrides"] = loaded.get("yyc_ground_question_overrides", {})
            memory["yyc_ground_custom_questions"] = loaded.get("yyc_ground_custom_questions", [])
            memory["question_bank_override"] = loaded.get("question_bank_override")
            memory["location_bank_override"] = loaded.get("location_bank_override")
            memory["yyc_ground_bank_override"] = loaded.get("yyc_ground_bank_override")
            if self._legacy_has_user_data(loaded):
                memory["users"]["guest"] = self._legacy_profile(loaded)
        else:
            memory = self._empty_memory()
            memory["route_overrides"] = loaded.get("route_overrides", {})
            memory["question_overrides"] = loaded.get("question_overrides", {})
            memory["custom_questions"] = loaded.get("custom_questions", [])
            memory["location_route_overrides"] = loaded.get("location_route_overrides", {})
            memory["location_question_overrides"] = loaded.get("location_question_overrides", {})
            memory["location_custom_questions"] = loaded.get("location_custom_questions", [])
            memory["yyc_ground_route_overrides"] = loaded.get("yyc_ground_route_overrides", {})
            memory["yyc_ground_question_overrides"] = loaded.get("yyc_ground_question_overrides", {})
            memory["yyc_ground_custom_questions"] = loaded.get("yyc_ground_custom_questions", [])
            memory["question_bank_override"] = loaded.get("question_bank_override")
            memory["location_bank_override"] = loaded.get("location_bank_override")
            memory["yyc_ground_bank_override"] = loaded.get("yyc_ground_bank_override")
            for stored_key, raw_profile in loaded["users"].items():
                profile = self._normalise_loaded_profile(raw_profile, str(stored_key))
                if not profile:
                    continue
                key = profile["display_name"].casefold()
                # If malformed legacy data contains duplicate case-insensitive names,
                # retain the first profile rather than merging unrelated histories.
                memory["users"].setdefault(key, profile)

        memory["schema_version"] = 11
        if not isinstance(memory["route_overrides"], dict):
            memory["route_overrides"] = {}
        if not isinstance(memory["question_overrides"], dict):
            memory["question_overrides"] = {}
        if not isinstance(memory["custom_questions"], list):
            memory["custom_questions"] = []
        if not isinstance(memory["location_route_overrides"], dict):
            memory["location_route_overrides"] = {}
        if not isinstance(memory["location_question_overrides"], dict):
            memory["location_question_overrides"] = {}
        if not isinstance(memory["location_custom_questions"], list):
            memory["location_custom_questions"] = []
        if not isinstance(memory["yyc_ground_route_overrides"], dict):
            memory["yyc_ground_route_overrides"] = {}
        if not isinstance(memory["yyc_ground_question_overrides"], dict):
            memory["yyc_ground_question_overrides"] = {}
        if not isinstance(memory["yyc_ground_custom_questions"], list):
            memory["yyc_ground_custom_questions"] = []
        return memory

    def _save(self) -> None:
        """Write atomically so a power loss cannot leave a half-written save file."""
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".airport_labeler_", suffix=".json", dir=self.memory_file.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(self.memory, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_name, self.memory_file)
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError:
                pass

    def _username_parts(self, raw_username: Any) -> tuple[str, str]:
        display_name = cleaned_text(raw_username, "Username", 32)
        return display_name.casefold(), display_name

    def _profile(self, raw_username: Any, create: bool = True) -> tuple[str, dict[str, Any]]:
        key, display_name = self._username_parts(raw_username)
        profile = self.memory["users"].get(key)
        if not profile:
            if not create:
                raise APIError("Choose a username to continue.", HTTPStatus.UNAUTHORIZED)
            profile = self._empty_profile(display_name)
            self.memory["users"][key] = profile
        return key, profile

    @staticmethod
    def _touch(profile: dict[str, Any]) -> None:
        profile["last_active_at"] = utc_now()

    def users(self) -> dict[str, Any]:
        with self.lock:
            users = []
            for profile in self.memory["users"].values():
                users.append(
                    {
                        "name": profile.get("display_name", "Player"),
                        "last_active_at": profile.get("last_active_at"),
                        "session_count": len(profile.get("sessions", [])),
                    }
                )
            users.sort(key=lambda item: (item.get("last_active_at") or "", item["name"].casefold()), reverse=True)
            return {"users": users}

    def select_user(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    # ------------------------------------------------------------------
    # Shared question bank
    # ------------------------------------------------------------------
    @staticmethod
    def _elapsed(session: dict[str, Any]) -> float:
        elapsed = float(session.get("elapsed_seconds", 0.0))
        running_since = session.get("running_since")
        if isinstance(running_since, (int, float)):
            elapsed += max(0.0, time.time() - float(running_since))
        return elapsed

    def _capture_elapsed(self, session: dict[str, Any], keep_running: bool) -> float:
        elapsed = self._elapsed(session)
        session["elapsed_seconds"] = elapsed
        session["running_since"] = time.time() if keep_running else None
        return elapsed

    def _pause_game_if_running(self, profile: dict[str, Any]) -> bool:
        game = profile.get("active_game")
        if game and game.get("running_since") is not None:
            self._capture_elapsed(game, keep_running=False)
            return True
        return False

    def _pause_validation_if_running(self, profile: dict[str, Any]) -> bool:
        validation = profile.get("active_validation")
        if validation and validation.get("running_since") is not None:
            self._capture_elapsed(validation, keep_running=False)
            return True
        return False

    def _pause_locations_if_running(self, profile: dict[str, Any]) -> bool:
        game = profile.get("active_locations_game")
        if game and game.get("running_since") is not None:
            self._capture_elapsed(game, keep_running=False)
            return True
        return False

    def _pause_locations_validation_if_running(self, profile: dict[str, Any]) -> bool:
        validation = profile.get("active_locations_validation")
        if validation and validation.get("running_since") is not None:
            self._capture_elapsed(validation, keep_running=False)
            return True
        return False

    def _pause_yyc_ground_game_if_running(self, profile: dict[str, Any]) -> bool:
        game = profile.get("active_yyc_ground_game")
        if game and game.get("running_since") is not None:
            self._capture_elapsed(game, keep_running=False)
            return True
        return False

    def _pause_yyc_ground_validation_if_running(self, profile: dict[str, Any]) -> bool:
        validation = profile.get("active_yyc_ground_validation")
        if validation and validation.get("running_since") is not None:
            self._capture_elapsed(validation, keep_running=False)
            return True
        return False

    def _pause_gates_if_running(self, profile: dict[str, Any]) -> bool:
        game = profile.get("active_gates_game")
        if game and game.get("running_since") is not None:
            self._capture_elapsed(game, keep_running=False)
            return True
        return False

    def _pause_apron_ops_if_running(self, profile: dict[str, Any]) -> bool:
        game = profile.get("active_apron_ops_game")
        if game and game.get("running_since") is not None:
            self._capture_elapsed(game, keep_running=False)
            return True
        return False

    def _normalise_bank_question(
        self,
        raw: Any,
        canvas_width: int,
        canvas_height: int,
        bank_name: str,
    ) -> dict[str, Any]:
        """Validate an importable question/answer record for either game mode."""
        if not isinstance(raw, dict):
            raise APIError(f"A {bank_name} question must be an object.")
        question_id = cleaned_text(raw.get("id"), "Question ID", 80)
        label = cleaned_text(raw.get("label"), "Question label", 100)
        category = cleaned_text(raw.get("category", "Location"), "Category", 40)
        clue = cleaned_text(raw.get("clue", ""), "Description", 280, required=False)
        paths = normalise_drawn_paths(
            raw.get("paths"),
            canvas_width,
            canvas_height,
            allow_point_paths=(bank_name in {"locations", "yyc_ground"}),
        )
        tolerance_value = finite_number(raw.get("tolerance", 20), "Click tolerance")
        if not 4 <= tolerance_value <= 100:
            raise APIError("Click tolerance must be between 4 and 100.")
        return {
            "id": question_id,
            "label": label,
            "category": category,
            "clue": clue,
            "paths": paths,
            "tolerance": round(tolerance_value, 1),
        }

    def _normalise_bank_list(
        self,
        raw_questions: Any,
        canvas_width: int,
        canvas_height: int,
        bank_name: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_questions, list) or not raw_questions:
            raise APIError(f"The {bank_name} question bank must contain at least one question.")
        if len(raw_questions) > 250:
            raise APIError(f"The {bank_name} question bank is too large.")
        questions = [
            self._normalise_bank_question(item, canvas_width, canvas_height, bank_name)
            for item in raw_questions
        ]
        ids = [question["id"] for question in questions]
        labels = [question["label"].casefold() for question in questions]
        if len(ids) != len(set(ids)):
            raise APIError(f"The {bank_name} question bank has duplicate IDs.")
        if len(labels) != len(set(labels)):
            raise APIError(f"The {bank_name} question bank has duplicate labels.")
        return questions

    def _main_source_questions(self) -> list[dict[str, Any]]:
        override = self.memory.get("question_bank_override")
        if isinstance(override, list):
            try:
                return self._normalise_bank_list(override, CANVAS_WIDTH, CANVAS_HEIGHT, "main")
            except APIError:
                pass
        # The bundled JSON is generated directly from the user's curated questions.txt
        # input. Fall back to game_data.py only if a deployment omits that source file.
        try:
            curated = json.loads(CURATED_MAIN_BANK_FILE.read_text(encoding="utf-8"))
            records = curated.get("questions") if isinstance(curated, dict) else None
            if isinstance(records, list):
                return self._normalise_bank_list(records, CANVAS_WIDTH, CANVAS_HEIGHT, "main")
        except (OSError, json.JSONDecodeError, APIError):
            pass
        return [deepcopy(question) for question in QUESTION_BANK]

    def _locations_base_questions(self) -> list[dict[str, Any]]:
        override = self.memory.get("location_bank_override")
        if isinstance(override, list):
            try:
                return self._normalise_bank_list(
                    override,
                    LOCATIONS_CANVAS_WIDTH,
                    LOCATIONS_CANVAS_HEIGHT,
                    "locations",
                )
            except APIError:
                pass
        return [deepcopy(question) for question in LOCATION_QUESTION_BANK]

    def _normalise_location_custom_question(self, raw: Any) -> dict[str, Any]:
        question = self._normalise_bank_question(
            raw,
            LOCATIONS_CANVAS_WIDTH,
            LOCATIONS_CANVAS_HEIGHT,
            "locations",
        )
        if not question["id"].startswith("loc_custom_"):
            raise APIError("A custom locations question ID is invalid.")
        question["created_at"] = raw.get("created_at") if isinstance(raw, dict) else None
        question["source"] = "custom"
        return question

    def _locations_source_questions(self) -> list[dict[str, Any]]:
        questions = self._locations_base_questions()
        seen_ids = {question["id"] for question in questions}
        for raw_question in self.memory.get("location_custom_questions", []):
            try:
                question = self._normalise_location_custom_question(raw_question)
            except APIError:
                continue
            if question["id"] not in seen_ids:
                questions.append(question)
                seen_ids.add(question["id"])
        return questions

    def _normalise_yyc_ground_question(self, raw: Any, require_custom_id: bool = False) -> dict[str, Any]:
        question = self._normalise_bank_question(
            raw,
            YYC_GROUND_CANVAS_WIDTH,
            YYC_GROUND_CANVAS_HEIGHT,
            "yyc_ground",
        )
        if require_custom_id and not question["id"].startswith("yyc_custom_"):
            raise APIError("A custom YYC Ground Sort question ID is invalid.")
        use = cleaned_text(raw.get("use"), "Who can use this point", 30)
        if use not in {"Jets", "Props", "Jets or Props"}:
            raise APIError("YYC Ground Sort use must be Jets, Props, or Jets or Props.")
        question["use"] = use
        question["created_at"] = raw.get("created_at") if isinstance(raw, dict) else None
        question["source"] = "custom" if require_custom_id else "source"
        return question

    def _normalise_yyc_ground_bank(self, raw_questions: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_questions, list) or not raw_questions:
            raise APIError("The YYC Ground Sort question bank must contain at least one question.")
        if len(raw_questions) > 250:
            raise APIError("The YYC Ground Sort question bank is too large.")
        questions = [self._normalise_yyc_ground_question(question) for question in raw_questions]
        ids = [question["id"] for question in questions]
        labels = [question["label"].casefold() for question in questions]
        if len(ids) != len(set(ids)):
            raise APIError("The YYC Ground Sort question bank has duplicate IDs.")
        if len(labels) != len(set(labels)):
            raise APIError("The YYC Ground Sort question bank has duplicate labels.")
        return questions

    def _yyc_ground_base_questions(self) -> list[dict[str, Any]]:
        override = self.memory.get("yyc_ground_bank_override")
        if isinstance(override, list):
            try:
                return self._normalise_yyc_ground_bank(override)
            except APIError:
                pass
        return [deepcopy(question) for question in YYC_GROUND_QUESTION_BANK]

    def _yyc_ground_questions(self) -> list[dict[str, Any]]:
        questions = self._yyc_ground_base_questions()
        seen_ids = {question["id"] for question in questions}
        for raw_question in self.memory.get("yyc_ground_custom_questions", []):
            try:
                question = self._normalise_yyc_ground_question(raw_question, require_custom_id=True)
            except APIError:
                continue
            if question["id"] not in seen_ids:
                questions.append(question)
                seen_ids.add(question["id"])
        return questions

    def _gates_questions(self) -> list[dict[str, Any]]:
        return [deepcopy(q) for q in GATES_QUESTION_BANK]

    def _gates_question_by_id(self, qid: str) -> dict[str, Any]:
        for q in self._gates_questions():
            if q["id"] == qid:
                return q
        raise APIError("This gate is no longer available.", HTTPStatus.CONFLICT)

    def _effective_gates_question(self, qid: str) -> dict[str, Any]:
        return self._gates_question_by_id(qid)

    def _public_gates_question(self, qid: str) -> dict[str, Any]:
        q = self._effective_gates_question(qid)
        return {"id": q["id"], "label": q["label"], "category": q["category"], "clue": q["clue"]}

    def _configured_gates_answer_view(self, qid: str) -> dict[str, Any]:
        q = self._effective_gates_question(qid)
        return {"paths": deepcopy(q["paths"]), "tolerance": q["tolerance"], "source_label": "Supplied gates marker"}

    def _normalise_custom_question(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise APIError("A saved custom question is invalid.")
        question_id = cleaned_text(raw.get("id"), "Question ID", 80)
        if not question_id.startswith("custom_"):
            raise APIError("A custom question ID is invalid.")
        label = cleaned_text(raw.get("label"), "Question label", 80)
        category = cleaned_text(raw.get("category"), "Category", 20)
        if category not in {"Runway", "Taxiway"}:
            raise APIError("Custom question category must be Runway or Taxiway.")
        clue = cleaned_text(raw.get("clue", ""), "Clue", 220, required=False)
        if not clue:
            clue = "A validator-defined airport route."
        paths = normalise_drawn_paths(raw.get("paths"))
        tolerance_value = finite_number(raw.get("tolerance", 20), "Route tolerance")
        if not 4 <= tolerance_value <= 80:
            raise APIError("Route tolerance must be between 4 and 80.")
        return {
            "id": question_id,
            "label": label,
            "category": category,
            "clue": clue,
            "paths": paths,
            "tolerance": round(tolerance_value, 1),
            "created_at": raw.get("created_at"),
            "source": "custom",
        }

    def _all_questions(self) -> list[dict[str, Any]]:
        questions = self._main_source_questions()
        seen_ids = {question["id"] for question in questions}
        for raw_question in self.memory.get("custom_questions", []):
            try:
                question = self._normalise_custom_question(raw_question)
            except APIError:
                # A manually damaged custom record should not prevent the source
                # chart from opening. It remains in memory for later repair.
                continue
            if question["id"] not in seen_ids:
                questions.append(question)
                seen_ids.add(question["id"])
        return questions

    def _question_by_id(self, question_id: str) -> dict[str, Any]:
        for question in self._all_questions():
            if question["id"] == question_id:
                return question
        raise APIError("This question is no longer available.", HTTPStatus.CONFLICT)

    def _is_custom_question(self, question_id: str) -> bool:
        source_ids = {question["id"] for question in self._main_source_questions()}
        return question_id not in source_ids

    def _effective_question(self, question_id: str) -> dict[str, Any]:
        """Combine a source/custom question with its shared validation overrides."""
        question = self._question_by_id(question_id)
        metadata_override = self.memory.get("question_overrides", {}).get(question_id)
        if isinstance(metadata_override, dict):
            try:
                question["label"] = cleaned_text(metadata_override.get("label"), "Question label", 80)
                question["clue"] = cleaned_text(metadata_override.get("clue", ""), "Description", 220, required=False)
            except APIError:
                pass
        route_override = self.memory.get("route_overrides", {}).get(question_id)
        if isinstance(route_override, dict) and isinstance(route_override.get("paths"), list):
            try:
                question["paths"] = normalise_drawn_paths(route_override["paths"])
                tolerance_value = finite_number(route_override.get("tolerance", question["tolerance"]), "route tolerance")
                if 4 <= tolerance_value <= 80:
                    question["tolerance"] = round(tolerance_value, 1)
            except APIError:
                pass
        return question

    @staticmethod
    def _apply_validation_detail_draft(question: dict[str, Any], validation: dict[str, Any], question_id: str) -> dict[str, Any]:
        """Apply this user's uncommitted label/clue change for validation display."""
        draft = validation.get("draft_question_overrides", {}).get(question_id)
        if isinstance(draft, dict):
            if isinstance(draft.get("label"), str):
                question["label"] = draft["label"]
            if isinstance(draft.get("clue"), str):
                question["clue"] = draft["clue"]
        return question

    def _public_question(self, question_id: str) -> dict[str, Any]:
        question = self._effective_question(question_id)
        return {
            "id": question["id"],
            "label": question["label"],
            "category": question["category"],
            "clue": question["clue"],
            "is_custom": self._is_custom_question(question_id),
        }

    def _configured_answer_view(self, question_id: str) -> dict[str, Any]:
        question = self._effective_question(question_id)
        is_custom = self._is_custom_question(question_id)
        is_override = question_id in self.memory.get("route_overrides", {})
        if is_custom:
            source_label = "Custom question"
        elif is_override:
            source_label = "Saved validation route"
        else:
            source_label = "Supplied source route"
        return {
            "paths": deepcopy(question["paths"]),
            "tolerance": question["tolerance"],
            "is_override": is_override,
            "is_custom": is_custom,
            "source_label": source_label,
        }

    def _location_question_by_id(self, question_id: str) -> dict[str, Any]:
        for question in self._locations_source_questions():
            if question["id"] == question_id:
                return question
        raise APIError("This location question is no longer available.", HTTPStatus.CONFLICT)

    def _is_custom_location_question(self, question_id: str) -> bool:
        source_ids = {question["id"] for question in self._locations_base_questions()}
        return question_id not in source_ids

    def _effective_location_question(self, question_id: str) -> dict[str, Any]:
        question = self._location_question_by_id(question_id)
        metadata_override = self.memory.get("location_question_overrides", {}).get(question_id)
        if isinstance(metadata_override, dict):
            try:
                question["label"] = cleaned_text(metadata_override.get("label"), "Question label", 100)
                question["clue"] = cleaned_text(metadata_override.get("clue", ""), "Description", 280, required=False)
            except APIError:
                pass
        route_override = self.memory.get("location_route_overrides", {}).get(question_id)
        if isinstance(route_override, dict) and isinstance(route_override.get("paths"), list):
            try:
                question["paths"] = normalise_drawn_paths(
                    route_override["paths"],
                    LOCATIONS_CANVAS_WIDTH,
                    LOCATIONS_CANVAS_HEIGHT,
                    allow_point_paths=True,
                )
                tolerance_value = finite_number(route_override.get("tolerance", question["tolerance"]), "click tolerance")
                if 4 <= tolerance_value <= 100:
                    question["tolerance"] = round(tolerance_value, 1)
            except APIError:
                pass
        return question

    def _public_location_question(self, question_id: str) -> dict[str, Any]:
        question = self._effective_location_question(question_id)
        return {
            "id": question["id"],
            "label": question["label"],
            "category": question["category"],
            "clue": question["clue"],
            "is_custom": self._is_custom_location_question(question_id),
        }

    @staticmethod
    def _apply_locations_validation_detail_draft(question: dict[str, Any], validation: dict[str, Any], question_id: str) -> dict[str, Any]:
        draft = validation.get("draft_question_overrides", {}).get(question_id)
        if isinstance(draft, dict):
            if isinstance(draft.get("label"), str):
                question["label"] = draft["label"]
            if isinstance(draft.get("clue"), str):
                question["clue"] = draft["clue"]
        return question

    def _configured_location_answer_view(self, question_id: str) -> dict[str, Any]:
        question = self._effective_location_question(question_id)
        is_custom = self._is_custom_location_question(question_id)
        is_override = question_id in self.memory.get("location_route_overrides", {})
        return {
            "paths": deepcopy(question["paths"]),
            "tolerance": question["tolerance"],
            "is_override": is_override,
            "is_custom": is_custom,
            "source_label": "Custom airport location" if is_custom else ("Saved validation marker" if is_override else "Supplied locations marker"),
        }

    def _yyc_ground_question_by_id(self, question_id: str) -> dict[str, Any]:
        for question in self._yyc_ground_questions():
            if question["id"] == question_id:
                return question
        raise APIError("This YYC Ground Sort point is no longer available.", HTTPStatus.CONFLICT)

    def _is_custom_yyc_ground_question(self, question_id: str) -> bool:
        source_ids = {question["id"] for question in self._yyc_ground_base_questions()}
        return question_id not in source_ids

    def _effective_yyc_ground_question(self, question_id: str) -> dict[str, Any]:
        question = self._yyc_ground_question_by_id(question_id)
        detail_override = self.memory.get("yyc_ground_question_overrides", {}).get(question_id)
        if isinstance(detail_override, dict):
            try:
                question["label"] = cleaned_text(detail_override.get("label"), "Question label", 100)
                question["clue"] = cleaned_text(detail_override.get("clue", ""), "Description", 280, required=False)
                use = cleaned_text(detail_override.get("use", question["use"]), "Who can use this point", 30)
                if use in {"Jets", "Props", "Jets or Props"}:
                    question["use"] = use
            except APIError:
                pass
        route_override = self.memory.get("yyc_ground_route_overrides", {}).get(question_id)
        if isinstance(route_override, dict) and isinstance(route_override.get("paths"), list):
            try:
                question["paths"] = normalise_drawn_paths(
                    route_override["paths"],
                    YYC_GROUND_CANVAS_WIDTH,
                    YYC_GROUND_CANVAS_HEIGHT,
                    allow_point_paths=True,
                )
                tolerance = finite_number(route_override.get("tolerance", question["tolerance"]), "click tolerance")
                if 4 <= tolerance <= 100:
                    question["tolerance"] = round(tolerance, 1)
            except APIError:
                pass
        return question

    def _public_yyc_ground_question(self, question_id: str) -> dict[str, Any]:
        question = self._effective_yyc_ground_question(question_id)
        return {
            "id": question["id"],
            "label": question["label"],
            "category": question["category"],
            "clue": question["clue"],
            "is_custom": self._is_custom_yyc_ground_question(question_id),
        }

    @staticmethod
    def _apply_yyc_validation_detail_draft(question: dict[str, Any], validation: dict[str, Any], question_id: str) -> dict[str, Any]:
        draft = validation.get("draft_question_overrides", {}).get(question_id)
        if isinstance(draft, dict):
            for field in ("label", "clue", "use"):
                if isinstance(draft.get(field), str):
                    question[field] = draft[field]
        return question

    def _configured_yyc_ground_answer_view(self, question_id: str) -> dict[str, Any]:
        question = self._effective_yyc_ground_question(question_id)
        is_custom = self._is_custom_yyc_ground_question(question_id)
        is_override = question_id in self.memory.get("yyc_ground_route_overrides", {})
        return {
            "paths": deepcopy(question["paths"]),
            "tolerance": question["tolerance"],
            "use": question["use"],
            "is_override": is_override,
            "is_custom": is_custom,
            "source_label": "Custom YYC ground point" if is_custom else ("Saved YYC validation point" if is_override else "Supplied YYC ground point"),
        }

    # ------------------------------------------------------------------
    # Views and snapshots
    # ------------------------------------------------------------------
    @staticmethod
    def _session_summary(game: dict[str, Any]) -> dict[str, Any]:
        attempts = int(game.get("attempts", 0))
        incorrect = int(game.get("incorrect", 0))
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "finished_at": game.get("finished_at"),
            "duration_seconds": int(round(float(game.get("elapsed_seconds", 0.0)))),
            "question_total": int(game["question_total"]),
            "attempts": attempts,
            "incorrect": incorrect,
            "correct": max(0, attempts - incorrect),
            "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else 0.0,
            "events": deepcopy(game.get("events", [])),
        }

    def _validation_summary(self, validation: dict[str, Any], override_count: int, bank_count: int) -> dict[str, Any]:
        return {
            "id": validation["id"],
            "started_at": validation["started_at"],
            "finished_at": validation.get("finished_at"),
            "duration_seconds": int(round(float(validation.get("elapsed_seconds", 0.0)))),
            "question_total": int(validation["question_total"]),
            "reviewed_count": len(validation.get("reviewed", [])),
            "skipped_count": int(validation.get("skipped_count", 0)),
            "changed_count": len(validation.get("draft_overrides", {})),
            "detail_changed_count": len(validation.get("draft_question_overrides", {})),
            "added_count": len(validation.get("draft_custom_questions", [])),
            "configured_override_count": override_count,
            "practice_question_count": bank_count,
            "events": deepcopy(validation.get("events", [])),
        }

    def _active_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        game = profile.get("active_game")
        if not game:
            return None
        queue = game.get("queue", [])
        current = self._public_question(queue[0]) if queue else None
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "question_total": int(game["question_total"]),
            "completed_count": len(game.get("completed", [])),
            "remaining_count": len(queue),
            "attempts": int(game.get("attempts", 0)),
            "incorrect": int(game.get("incorrect", 0)),
            "elapsed_seconds": int(round(self._elapsed(game))),
            "is_running": game.get("running_since") is not None,
            "current": current,
            "placements": deepcopy(game.get("placements", [])),
        }

    def _locations_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        game = profile.get("active_locations_game")
        if not game:
            return None
        queue = game.get("queue", [])
        current = self._public_location_question(queue[0]) if queue else None
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "question_total": int(game["question_total"]),
            "completed_count": len(game.get("completed", [])),
            "remaining_count": len(queue),
            "attempts": int(game.get("attempts", 0)),
            "incorrect": int(game.get("incorrect", 0)),
            "elapsed_seconds": int(round(self._elapsed(game))),
            "is_running": game.get("running_since") is not None,
            "current": current,
            "placements": deepcopy(game.get("placements", [])),
        }

    def _yyc_ground_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        game = profile.get("active_yyc_ground_game")
        if not game:
            return None
        queue = game.get("queue", [])
        current = self._public_yyc_ground_question(queue[0]) if queue else None
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "question_total": int(game["question_total"]),
            "completed_count": len(game.get("completed", [])),
            "remaining_count": len(queue),
            "attempts": int(game.get("attempts", 0)),
            "incorrect": int(game.get("incorrect", 0)),
            "elapsed_seconds": int(round(self._elapsed(game))),
            "is_running": game.get("running_since") is not None,
            "phase": game.get("phase", "locate"),
            "current": current,
            "placements": deepcopy(game.get("placements", [])),
        }

    def _gates_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        game = profile.get("active_gates_game")
        if not game:
            return None
        queue = game.get("queue", [])
        current = self._public_gates_question(queue[0]) if queue else None
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "question_total": int(game["question_total"]),
            "completed_count": len(game.get("completed", [])),
            "remaining_count": len(queue),
            "attempts": int(game.get("attempts", 0)),
            "incorrect": int(game.get("incorrect", 0)),
            "elapsed_seconds": int(round(self._elapsed(game))),
            "is_running": game.get("running_since") is not None,
            "current": current,
            "placements": deepcopy(game.get("placements", [])),
        }

    def _apron_ops_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        game = profile.get("active_apron_ops_game")
        if not game:
            return None
        queue = game.get("queue", [])
        current = public_apron_ops_question(queue[0]) if queue else None
        return {
            "id": game["id"],
            "started_at": game["started_at"],
            "question_total": int(game["question_total"]),
            "completed_count": len(game.get("completed", [])),
            "remaining_count": len(queue),
            "attempts": int(game.get("attempts", 0)),
            "incorrect": int(game.get("incorrect", 0)),
            "elapsed_seconds": int(round(self._elapsed(game))),
            "is_running": game.get("running_since") is not None,
            "current": current,
        }

    def _locations_validation_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        validation = profile.get("active_locations_validation")
        if not validation:
            return None
        queue = validation.get("queue", [])
        phase = validation.get("phase", "review")
        if phase == "review" and not queue:
            phase = "add_questions"
        current = None
        if phase == "review" and queue:
            question_id = queue[0]
            current = self._public_location_question(question_id)
            current = self._apply_locations_validation_detail_draft(current, validation, question_id)
            current["configured_answer"] = self._configured_location_answer_view(question_id)
        return {
            "id": validation["id"],
            "started_at": validation["started_at"],
            "phase": phase,
            "question_total": int(validation["question_total"]),
            "reviewed_count": len(validation.get("reviewed", [])),
            "skipped_count": int(validation.get("skipped_count", 0)),
            "remaining_count": len(queue),
            "changed_count": len(validation.get("draft_overrides", {})),
            "detail_changed_count": len(validation.get("draft_question_overrides", {})),
            "added_count": len(validation.get("draft_custom_questions", [])),
            "elapsed_seconds": int(round(self._elapsed(validation))),
            "is_running": validation.get("running_since") is not None,
            "current": current,
        }

    def _yyc_ground_validation_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        validation = profile.get("active_yyc_ground_validation")
        if not validation:
            return None
        queue = validation.get("queue", [])
        phase = validation.get("phase", "review")
        if phase == "review" and not queue:
            phase = "add_questions"
        current = None
        if phase == "review" and queue:
            question_id = queue[0]
            current = self._public_yyc_ground_question(question_id)
            current = self._apply_yyc_validation_detail_draft(current, validation, question_id)
            current["configured_answer"] = self._configured_yyc_ground_answer_view(question_id)
            # The use classification is editable in validation and should reflect
            # this user's uncommitted draft before final promotion.
            draft = validation.get("draft_question_overrides", {}).get(question_id, {})
            if isinstance(draft, dict) and isinstance(draft.get("use"), str):
                current["configured_answer"]["use"] = draft["use"]
        return {
            "id": validation["id"],
            "started_at": validation["started_at"],
            "phase": phase,
            "question_total": int(validation["question_total"]),
            "reviewed_count": len(validation.get("reviewed", [])),
            "skipped_count": int(validation.get("skipped_count", 0)),
            "remaining_count": len(queue),
            "changed_count": len(validation.get("draft_overrides", {})),
            "detail_changed_count": len(validation.get("draft_question_overrides", {})),
            "added_count": len(validation.get("draft_custom_questions", [])),
            "elapsed_seconds": int(round(self._elapsed(validation))),
            "is_running": validation.get("running_since") is not None,
            "current": current,
        }

    def _validation_view(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        validation = profile.get("active_validation")
        if not validation:
            return None
        queue = validation.get("queue", [])
        phase = validation.get("phase", "review")
        if phase == "review" and not queue:
            phase = "add_questions"
        current = None
        if phase == "review" and queue:
            question_id = queue[0]
            current = self._public_question(question_id)
            current = self._apply_validation_detail_draft(current, validation, question_id)
            current["configured_answer"] = self._configured_answer_view(question_id)
        return {
            "id": validation["id"],
            "started_at": validation["started_at"],
            "phase": phase,
            "question_total": int(validation["question_total"]),
            "reviewed_count": len(validation.get("reviewed", [])),
            "skipped_count": int(validation.get("skipped_count", 0)),
            "remaining_count": len(queue),
            "changed_count": len(validation.get("draft_overrides", {})),
            "detail_changed_count": len(validation.get("draft_question_overrides", {})),
            "added_count": len(validation.get("draft_custom_questions", [])),
            "elapsed_seconds": int(round(self._elapsed(validation))),
            "is_running": validation.get("running_since") is not None,
            "current": current,
        }

    def _memory_snapshot(self, user_key: str, profile: dict[str, Any]) -> dict[str, Any]:
        custom_count = len(self._all_questions()) - len(self._main_source_questions())
        return {
            "user": {"name": profile["display_name"]},
            "active": self._active_view(profile),
            "locations": self._locations_view(profile),
            "yyc_ground": self._yyc_ground_view(profile),
            "gates": self._gates_view(profile),
            "apron_ops": self._apron_ops_view(profile),
            "validation": self._validation_view(profile),
            "locations_validation": self._locations_validation_view(profile),
            "yyc_ground_validation": self._yyc_ground_validation_view(profile),
            "history": {
                "session_count": len(profile.get("sessions", [])),
                "last_completed": deepcopy(profile.get("last_completed")),
                "location_session_count": len(profile.get("location_sessions", [])),
                "last_locations_completed": deepcopy(profile.get("last_locations_completed")),
                "yyc_ground_session_count": len(profile.get("yyc_ground_sessions", [])),
                "last_yyc_ground_completed": deepcopy(profile.get("last_yyc_ground_completed")),
                "gates_session_count": len(profile.get("gates_sessions", [])),
                "last_gates_completed": deepcopy(profile.get("last_gates_completed")),
                "apron_ops_session_count": len(profile.get("apron_ops_sessions", [])),
                "last_apron_ops_completed": deepcopy(profile.get("last_apron_ops_completed")),
                "locations_validation_count": len(profile.get("locations_validation_sessions", [])),
                "yyc_ground_validation_count": len(profile.get("yyc_ground_validation_sessions", [])),
                "last_yyc_ground_validation": deepcopy(profile.get("last_yyc_ground_validation")),
                "last_locations_validation": deepcopy(profile.get("last_locations_validation")),
                "validation_count": len(profile.get("validation_sessions", [])),
                "last_validation": deepcopy(profile.get("last_validation")),
                "configured_override_count": len(self.memory.get("route_overrides", {})),
                "question_override_count": len(self.memory.get("question_overrides", {})),
                "custom_question_count": custom_count,
                "location_configured_override_count": len(self.memory.get("location_route_overrides", {})),
                "location_question_override_count": len(self.memory.get("location_question_overrides", {})),
                "location_custom_question_count": len(self._locations_source_questions()) - len(self._locations_base_questions()),
                "yyc_ground_configured_override_count": len(self.memory.get("yyc_ground_route_overrides", {})),
                "yyc_ground_question_override_count": len(self.memory.get("yyc_ground_question_overrides", {})),
                "yyc_ground_custom_question_count": len(self._yyc_ground_questions()) - len(self._yyc_ground_base_questions()),
                "flashcard_deck_count": len(profile.get("flashcard_decks", [])),
            },
            "question_total": len(self._all_questions()),
            "locations_question_total": len(self._locations_source_questions()),
            "yyc_ground_question_total": len(self._yyc_ground_questions()),
            "gates_question_total": len(self._gates_questions()),
            "apron_ops_question_total": APRON_OPS_DEFAULT_COUNT,
        }

    def state(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            return self._memory_snapshot(key, profile)

    # ------------------------------------------------------------------
    # User-specific practice game
    # ------------------------------------------------------------------
    def start_new_game(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_game") and not replace_active:
                raise APIError(
                    "A saved game is already in progress. Resume it or explicitly discard it first.",
                    HTTPStatus.CONFLICT,
                )
            self._pause_validation_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            question_ids = [question["id"] for question in self._all_questions()]
            if not question_ids:
                raise APIError("There are no questions in the practice bank.", HTTPStatus.CONFLICT)
            random.SystemRandom().shuffle(question_ids)
            profile["active_game"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "question_total": len(question_ids),
                "queue": question_ids,
                "completed": [],
                "placements": [],
                "attempts": 0,
                "incorrect": 0,
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_game")
            if not game:
                raise APIError("There is no saved game to resume.", HTTPStatus.NOT_FOUND)
            self._pause_validation_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_game_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def _update_question_stat(self, profile: dict[str, Any], question_id: str, correct: bool) -> None:
        question = self._effective_question(question_id)
        stats = profile.setdefault("question_stats", {}).setdefault(
            question_id,
            {
                "id": question_id,
                "label": question["label"],
                "category": question["category"],
                "attempts": 0,
                "incorrect": 0,
                "correct": 0,
                "last_seen": None,
            },
        )
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if correct:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["incorrect"] = int(stats.get("incorrect", 0)) + 1
        stats["last_seen"] = utc_now()

    def _finish_active_game(self, profile: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(game, keep_running=False)
        game["finished_at"] = utc_now()
        summary = self._session_summary(game)
        profile.setdefault("sessions", []).append(summary)
        profile["last_completed"] = deepcopy(summary)
        profile["active_game"] = None
        return summary

    def answer(self, raw_username: Any, x: Any, y: Any) -> dict[str, Any]:
        x = finite_number(x, "x")
        y = finite_number(y, "y")
        if not (-20 <= x <= CANVAS_WIDTH + 20 and -20 <= y <= CANVAS_HEIGHT + 20):
            raise APIError("That click falls outside the airport chart.")

        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_game")
            if not game or not game.get("queue"):
                raise APIError("No active question is available.", HTTPStatus.CONFLICT)

            self._pause_validation_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)
            question_id = game["queue"][0]
            question = self._effective_question(question_id)
            correct = hit_test(question, x, y)

            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append(
                {
                    "sequence": len(game.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "correct": correct,
                    "elapsed_seconds": int(round(elapsed)),
                    "answered_at": utc_now(),
                }
            )
            self._update_question_stat(profile, question_id, correct)
            game["queue"].pop(0)

            if correct:
                game.setdefault("completed", []).append(question_id)
                game.setdefault("placements", []).append(
                    {
                        "question_id": question_id,
                        "label": question["label"],
                        "category": question["category"],
                        "x": round(x, 1),
                        "y": round(y, 1),
                    }
                )
                feedback = f"Correct — {question['label']} is now labelled."
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                remaining = game["queue"]
                insertion_minimum = 1 if remaining else 0
                insertion_index = random.SystemRandom().randint(insertion_minimum, len(remaining))
                remaining.insert(insertion_index, question_id)
                feedback = f"Not quite. {question['label']} has been returned to the queue."

            finished_summary = None
            if not game["queue"]:
                finished_summary = self._finish_active_game(profile, game)

            self._touch(profile)
            self._save()
            return {
                "correct": correct,
                "feedback": feedback,
                "clicked": {"x": round(x, 1), "y": round(y, 1)},
                "question": self._public_question(question_id),
                "finished": finished_summary is not None,
                "summary": finished_summary,
                "state": self._memory_snapshot(key, profile),
            }

    def hint(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            game = profile.get("active_game")
            if not game or not game.get("queue"):
                raise APIError("No active question is available.", HTTPStatus.CONFLICT)
            question = self._effective_question(game["queue"][0])
            return {
                "id": question["id"],
                "label": question["label"],
                "paths": deepcopy(question["paths"]),
                "tolerance": question["tolerance"],
            }

    # ------------------------------------------------------------------
    # Airport locations learning game
    # ------------------------------------------------------------------
    def start_locations_game(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_locations_game") and not replace_active:
                raise APIError(
                    "A saved locations game is already in progress. Resume it or explicitly discard it first.",
                    HTTPStatus.CONFLICT,
                )
            self._pause_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            question_ids = [question["id"] for question in self._locations_source_questions()]
            if not question_ids:
                raise APIError("There are no airport-location questions in the bank.", HTTPStatus.CONFLICT)
            random.SystemRandom().shuffle(question_ids)
            profile["active_locations_game"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "question_total": len(question_ids),
                "queue": question_ids,
                "completed": [],
                "placements": [],
                "attempts": 0,
                "incorrect": 0,
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_locations_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_locations_game")
            if not game:
                raise APIError("There is no saved locations game to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_locations_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_locations_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def _update_location_question_stat(self, profile: dict[str, Any], question_id: str, correct: bool) -> None:
        question = self._effective_location_question(question_id)
        stats = profile.setdefault("location_question_stats", {}).setdefault(
            question_id,
            {
                "id": question_id,
                "label": question["label"],
                "category": question["category"],
                "attempts": 0,
                "incorrect": 0,
                "correct": 0,
                "last_seen": None,
            },
        )
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if correct:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["incorrect"] = int(stats.get("incorrect", 0)) + 1
        stats["last_seen"] = utc_now()

    def _finish_locations_game(self, profile: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(game, keep_running=False)
        game["finished_at"] = utc_now()
        summary = self._session_summary(game)
        profile.setdefault("location_sessions", []).append(summary)
        profile["last_locations_completed"] = deepcopy(summary)
        profile["active_locations_game"] = None
        return summary

    def answer_location(self, raw_username: Any, x: Any, y: Any) -> dict[str, Any]:
        x = finite_number(x, "x")
        y = finite_number(y, "y")
        if not (-20 <= x <= LOCATIONS_CANVAS_WIDTH + 20 and -20 <= y <= LOCATIONS_CANVAS_HEIGHT + 20):
            raise APIError("That click falls outside the airport locations chart.")

        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_locations_game")
            if not game or not game.get("queue"):
                raise APIError("No active locations question is available.", HTTPStatus.CONFLICT)

            self._pause_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)
            question_id = game["queue"][0]
            question = self._effective_location_question(question_id)
            correct = hit_test(question, x, y)

            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append(
                {
                    "sequence": len(game.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "correct": correct,
                    "elapsed_seconds": int(round(elapsed)),
                    "answered_at": utc_now(),
                }
            )
            self._update_location_question_stat(profile, question_id, correct)
            game["queue"].pop(0)

            if correct:
                game.setdefault("completed", []).append(question_id)
                game.setdefault("placements", []).append(
                    {
                        "question_id": question_id,
                        "label": question["label"],
                        "category": question["category"],
                        "x": round(x, 1),
                        "y": round(y, 1),
                    }
                )
                feedback = f"Correct — {question['label']} is now labelled."
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                remaining = game["queue"]
                insertion_minimum = 1 if remaining else 0
                insertion_index = random.SystemRandom().randint(insertion_minimum, len(remaining))
                remaining.insert(insertion_index, question_id)
                feedback = f"Not quite. {question['label']} has been returned to the queue."

            finished_summary = None
            if not game["queue"]:
                finished_summary = self._finish_locations_game(profile, game)

            self._touch(profile)
            self._save()
            return {
                "correct": correct,
                "feedback": feedback,
                "clicked": {"x": round(x, 1), "y": round(y, 1)},
                "question": self._public_location_question(question_id),
                "finished": finished_summary is not None,
                "summary": finished_summary,
                "state": self._memory_snapshot(key, profile),
            }

    def location_hint(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            game = profile.get("active_locations_game")
            if not game or not game.get("queue"):
                raise APIError("No active locations question is available.", HTTPStatus.CONFLICT)
            question = self._effective_location_question(game["queue"][0])
            return {
                "id": question["id"],
                "label": question["label"],
                "paths": deepcopy(question["paths"]),
                "tolerance": question["tolerance"],
            }

    # ------------------------------------------------------------------
    # YYC Ground Sort Program
    # ------------------------------------------------------------------
    def start_yyc_ground_game(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_yyc_ground_game") and not replace_active:
                raise APIError("A saved YYC Ground Sort run is already in progress. Resume it or explicitly discard it first.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            question_ids = [question["id"] for question in self._yyc_ground_questions()]
            random.SystemRandom().shuffle(question_ids)
            profile["active_yyc_ground_game"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "question_total": len(question_ids),
                "queue": question_ids,
                "completed": [],
                "placements": [],
                "attempts": 0,
                "incorrect": 0,
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
                "phase": "locate",
                "pending_placement": None,
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_yyc_ground_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_yyc_ground_game")
            if not game:
                raise APIError("There is no saved YYC Ground Sort run to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_yyc_ground_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_yyc_ground_game_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def _update_yyc_ground_stat(self, profile: dict[str, Any], question_id: str, correct: bool, stage: str) -> None:
        question = self._effective_yyc_ground_question(question_id)
        stats = profile.setdefault("yyc_ground_question_stats", {}).setdefault(
            question_id,
            {
                "id": question_id,
                "label": question["label"],
                "category": question["category"],
                "attempts": 0,
                "incorrect": 0,
                "correct": 0,
                "locate_incorrect": 0,
                "use_incorrect": 0,
                "last_seen": None,
            },
        )
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if correct:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["incorrect"] = int(stats.get("incorrect", 0)) + 1
            stats[f"{stage}_incorrect"] = int(stats.get(f"{stage}_incorrect", 0)) + 1
        stats["last_seen"] = utc_now()

    def _finish_yyc_ground_game(self, profile: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(game, keep_running=False)
        game["finished_at"] = utc_now()
        summary = self._session_summary(game)
        profile.setdefault("yyc_ground_sessions", []).append(summary)
        profile["last_yyc_ground_completed"] = deepcopy(summary)
        profile["active_yyc_ground_game"] = None
        return summary

    def _requeue_yyc_question(self, game: dict[str, Any], question_id: str) -> None:
        remaining = game["queue"]
        insert_minimum = 1 if remaining else 0
        insert_at = random.SystemRandom().randint(insert_minimum, len(remaining))
        remaining.insert(insert_at, question_id)
        game["phase"] = "locate"
        game["pending_placement"] = None

    def answer_yyc_ground_location(self, raw_username: Any, x: Any, y: Any) -> dict[str, Any]:
        x = finite_number(x, "x")
        y = finite_number(y, "y")
        if not (-20 <= x <= YYC_GROUND_CANVAS_WIDTH + 20 and -20 <= y <= YYC_GROUND_CANVAS_HEIGHT + 20):
            raise APIError("That click falls outside the YYC Ground Sort diagram.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_yyc_ground_game")
            if not game or not game.get("queue"):
                raise APIError("No active YYC Ground Sort question is available.", HTTPStatus.CONFLICT)
            if game.get("phase", "locate") != "locate":
                raise APIError("Answer the aircraft-use follow-up before selecting another point.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)
            question_id = game["queue"][0]
            question = self._effective_yyc_ground_question(question_id)
            correct = hit_test(question, x, y)
            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append(
                {
                    "sequence": len(game.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "stage": "locate",
                    "correct": correct,
                    "elapsed_seconds": int(round(elapsed)),
                    "answered_at": utc_now(),
                }
            )
            self._update_yyc_ground_stat(profile, question_id, correct, "locate")
            if correct:
                game["phase"] = "use"
                game["pending_placement"] = {"x": round(x, 1), "y": round(y, 1)}
                feedback = f"Correct point — now classify who can use {question['label']}."
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                game["queue"].pop(0)
                self._requeue_yyc_question(game, question_id)
                feedback = f"Not quite. {question['label']} has been returned to the queue."
            self._touch(profile)
            self._save()
            return {
                "correct": correct,
                "follow_up": correct,
                "feedback": feedback,
                "clicked": {"x": round(x, 1), "y": round(y, 1)},
                "state": self._memory_snapshot(key, profile),
            }

    def answer_yyc_ground_use(self, raw_username: Any, use_value: Any) -> dict[str, Any]:
        use = cleaned_text(use_value, "Aircraft-use answer", 30)
        if use not in {"Jets", "Props", "Jets or Props"}:
            raise APIError("Choose Jets, Props, or Jets or Props.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_yyc_ground_game")
            if not game or not game.get("queue") or game.get("phase") != "use":
                raise APIError("Locate the point before answering its aircraft-use question.", HTTPStatus.CONFLICT)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)
            question_id = game["queue"][0]
            question = self._effective_yyc_ground_question(question_id)
            correct = use == question["use"]
            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append(
                {
                    "sequence": len(game.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "stage": "use",
                    "correct": correct,
                    "elapsed_seconds": int(round(elapsed)),
                    "answered_at": utc_now(),
                }
            )
            self._update_yyc_ground_stat(profile, question_id, correct, "use")
            finished_summary = None
            if correct:
                placement = game.get("pending_placement") or {"x": 0, "y": 0}
                game["queue"].pop(0)
                game.setdefault("completed", []).append(question_id)
                game.setdefault("placements", []).append(
                    {
                        "question_id": question_id,
                        "label": question["label"],
                        "category": question["category"],
                        "x": placement["x"],
                        "y": placement["y"],
                    }
                )
                game["phase"] = "locate"
                game["pending_placement"] = None
                feedback = f"Correct — {question['label']} is now labelled and classified."
                if not game["queue"]:
                    finished_summary = self._finish_yyc_ground_game(profile, game)
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                game["queue"].pop(0)
                self._requeue_yyc_question(game, question_id)
                feedback = f"Not quite. {question['label']} has been returned to the queue for another try."
            self._touch(profile)
            self._save()
            return {
                "correct": correct,
                "feedback": feedback,
                "finished": finished_summary is not None,
                "summary": finished_summary,
                "state": self._memory_snapshot(key, profile),
            }

    def yyc_ground_hint(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            game = profile.get("active_yyc_ground_game")
            if not game or not game.get("queue"):
                raise APIError("No active YYC Ground Sort question is available.", HTTPStatus.CONFLICT)
            if game.get("phase", "locate") != "locate":
                raise APIError("The point is already found; answer the aircraft-use follow-up.", HTTPStatus.CONFLICT)
            question = self._effective_yyc_ground_question(game["queue"][0])
            return {"id": question["id"], "label": question["label"], "paths": deepcopy(question["paths"]), "tolerance": question["tolerance"]}

    # ------------------------------------------------------------------
    # Gates identification game
    # ------------------------------------------------------------------
    def start_gates_game(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_gates_game") and not replace_active:
                raise APIError("A saved gates game is already in progress. Resume it or explicitly discard it first.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            question_ids = [q["id"] for q in self._gates_questions()]
            random.SystemRandom().shuffle(question_ids)
            profile["active_gates_game"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "question_total": len(question_ids),
                "queue": question_ids,
                "completed": [],
                "placements": [],
                "attempts": 0,
                "incorrect": 0,
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_gates_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_gates_game")
            if not game:
                raise APIError("There is no saved gates game to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_gates_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_gates_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def _update_gates_stat(self, profile: dict[str, Any], qid: str, correct: bool) -> None:
        q = self._effective_gates_question(qid)
        stats = profile.setdefault("gates_question_stats", {}).setdefault(qid, {"id": qid, "label": q["label"], "category": q["category"], "attempts": 0, "incorrect": 0, "correct": 0, "last_seen": None})
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if correct:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["incorrect"] = int(stats.get("incorrect", 0)) + 1
        stats["last_seen"] = utc_now()

    def _finish_gates_game(self, profile: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(game, keep_running=False)
        game["finished_at"] = utc_now()
        summary = self._session_summary(game)
        profile.setdefault("gates_sessions", []).append(summary)
        profile["last_gates_completed"] = deepcopy(summary)
        profile["active_gates_game"] = None
        return summary

    def answer_gates(self, raw_username: Any, x: Any, y: Any) -> dict[str, Any]:
        x = finite_number(x, "x")
        y = finite_number(y, "y")
        if not (-20 <= x <= GATES_CANVAS_WIDTH + 20 and -20 <= y <= GATES_CANVAS_HEIGHT + 20):
            raise APIError("That click falls outside the gates chart.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_gates_game")
            if not game or not game.get("queue"):
                raise APIError("No active gates question is available.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)
            qid = game["queue"][0]
            question = self._effective_gates_question(qid)
            correct = hit_test(question, x, y)
            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append({"sequence": len(game.get("events", []))+1, "question_id": qid, "label": question["label"], "correct": correct, "elapsed_seconds": int(round(elapsed)), "answered_at": utc_now()})
            self._update_gates_stat(profile, qid, correct)
            game["queue"].pop(0)
            if correct:
                game.setdefault("completed", []).append(qid)
                game.setdefault("placements", []).append({"question_id": qid, "label": question["label"], "category": question["category"], "x": round(x,1), "y": round(y,1)})
                feedback = f"Correct — {question['label']} found. Marker removed, canvas blank again."
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                remaining = game["queue"]
                insertion_minimum = 1 if remaining else 0
                insertion_index = random.SystemRandom().randint(insertion_minimum, len(remaining))
                remaining.insert(insertion_index, qid)
                feedback = f"Not quite. {question['label']} has been returned to the queue."
            finished_summary = None
            if not game["queue"]:
                finished_summary = self._finish_gates_game(profile, game)
            self._touch(profile)
            self._save()
            return {"correct": correct, "feedback": feedback, "clicked": {"x": round(x,1), "y": round(y,1)}, "question": self._public_gates_question(qid), "finished": finished_summary is not None, "summary": finished_summary, "state": self._memory_snapshot(key, profile)}

    def gates_hint(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            game = profile.get("active_gates_game")
            if not game or not game.get("queue"):
                raise APIError("No active gates question is available.", HTTPStatus.CONFLICT)
            q = self._effective_gates_question(game["queue"][0])
            return {"id": q["id"], "label": q["label"], "paths": deepcopy(q["paths"]), "tolerance": q["tolerance"]}

    def gates_trends(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            sessions = []
            for session in profile.get("gates_sessions", []):
                attempts = int(session.get("attempts", 0))
                incorrect = int(session.get("incorrect", 0))
                sessions.append({"id": session.get("id"), "started_at": session.get("started_at"), "finished_at": session.get("finished_at"), "duration_seconds": int(session.get("duration_seconds", 0)), "question_total": int(session.get("question_total", len(self._gates_questions()))), "attempts": attempts, "incorrect": incorrect, "correct": max(0, attempts - incorrect), "accuracy": round((attempts - incorrect)/attempts*100,1) if attempts else 0.0, "events": deepcopy(session.get("events", []))})
            question_stats = []
            for q in self._gates_questions():
                stat = profile.get("gates_question_stats", {}).get(q["id"], {})
                attempts = int(stat.get("attempts", 0))
                incorrect = int(stat.get("incorrect", 0))
                question_stats.append({"id": q["id"], "label": q["label"], "category": q["category"], "attempts": attempts, "incorrect": incorrect, "correct": int(stat.get("correct",0)), "accuracy": round((attempts - incorrect)/attempts*100,1) if attempts else None})
            question_stats.sort(key=lambda item: (-item["incorrect"], -item["attempts"], item["label"]))
            total_attempts = sum(s["attempts"] for s in sessions)
            total_incorrect = sum(s["incorrect"] for s in sessions)
            total_duration = sum(s["duration_seconds"] for s in sessions)
            lifetime = {"sessions": len(sessions), "attempts": total_attempts, "incorrect": total_incorrect, "correct": max(0, total_attempts - total_incorrect), "accuracy": round((total_attempts - total_incorrect)/total_attempts*100,1) if total_attempts else 0.0, "average_duration_seconds": round(total_duration/len(sessions)) if sessions else 0, "total_duration_seconds": total_duration}
            return {"user": {"name": profile["display_name"]}, "lifetime": lifetime, "sessions": sessions, "question_stats": question_stats, "active": self._gates_view(profile), "configuration": {"question_count": len(self._gates_questions())}}

    # ------------------------------------------------------------------
    # Apron Ops game mode
    # ------------------------------------------------------------------
    def start_apron_ops_game(self, raw_username: Any, replace_active: bool = False, count: int = APRON_OPS_DEFAULT_COUNT) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_apron_ops_game") and not replace_active:
                raise APIError("A saved Apron Ops session is already in progress. Resume it or explicitly discard it first.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            questions = generate_apron_ops_session(count)
            profile["active_apron_ops_game"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "question_total": len(questions),
                "queue": questions,
                "completed": [],
                "attempts": 0,
                "incorrect": 0,
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_apron_ops_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_apron_ops_game")
            if not game:
                raise APIError("There is no saved Apron Ops session to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            if game.get("running_since") is None:
                game["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_apron_ops_game(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_apron_ops_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def _update_apron_ops_stat(self, profile: dict[str, Any], question: dict[str, Any], correct: bool) -> None:
        stat_id = f"gate_{question['gate']:02d}"
        label = f"Gate {question['gate']} ({question.get('concourse', '')})"
        category = f"Apron {question.get('request_type', '').capitalize()}"
        stats = profile.setdefault("apron_ops_question_stats", {}).setdefault(
            stat_id,
            {
                "id": stat_id,
                "gate": question["gate"],
                "label": label,
                "category": category,
                "attempts": 0,
                "incorrect": 0,
                "correct": 0,
                "last_seen": None,
            }
        )
        stats["attempts"] = int(stats.get("attempts", 0)) + 1
        if correct:
            stats["correct"] = int(stats.get("correct", 0)) + 1
        else:
            stats["incorrect"] = int(stats.get("incorrect", 0)) + 1
        stats["last_seen"] = utc_now()

    def _finish_apron_ops_game(self, profile: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(game, keep_running=False)
        game["finished_at"] = utc_now()
        summary = self._session_summary(game)
        profile.setdefault("apron_ops_sessions", []).append(summary)
        profile["last_apron_ops_completed"] = deepcopy(summary)
        profile["active_apron_ops_game"] = None
        return summary

    def answer_apron_ops(
        self,
        raw_username: Any,
        spot: Any = None,
        taxiway: Any = None,
        ground: Any = None,
    ) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            game = profile.get("active_apron_ops_game")
            if not game or not game.get("queue"):
                raise APIError("No active Apron Ops question is available.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)

            if game.get("running_since") is None:
                game["running_since"] = time.time()
            elapsed = self._capture_elapsed(game, keep_running=True)

            question = game["queue"][0]
            qid = question["id"]
            user_answer = {
                "spot": spot,
                "taxiway": taxiway,
                "ground": ground,
            }
            eval_result = check_apron_ops_answer(question, user_answer)
            correct = eval_result["correct"]
            feedback = eval_result["feedback"]
            breakdown = eval_result["breakdown"]

            game["attempts"] = int(game.get("attempts", 0)) + 1
            game.setdefault("events", []).append({
                "sequence": len(game.get("events", [])) + 1,
                "question_id": qid,
                "label": question["label"],
                "request_type": question["request_type"],
                "gate": question["gate"],
                "runway": question["runway"],
                "correct": correct,
                "elapsed_seconds": int(round(elapsed)),
                "answered_at": utc_now(),
            })
            self._update_apron_ops_stat(profile, question, correct)

            game["queue"].pop(0)
            if correct:
                game.setdefault("completed", []).append(qid)
            else:
                game["incorrect"] = int(game.get("incorrect", 0)) + 1
                remaining = game["queue"]
                insertion_minimum = 1 if remaining else 0
                insertion_index = random.SystemRandom().randint(insertion_minimum, len(remaining))
                remaining.insert(insertion_index, question)

            finished_summary = None
            if not game["queue"]:
                finished_summary = self._finish_apron_ops_game(profile, game)

            self._touch(profile)
            self._save()
            return {
                "correct": correct,
                "feedback": feedback,
                "breakdown": breakdown,
                "question": public_apron_ops_question(question),
                "finished": finished_summary is not None,
                "summary": finished_summary,
                "state": self._memory_snapshot(key, profile),
            }

    def apron_ops_trends(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            sessions = []
            for session in profile.get("apron_ops_sessions", []):
                attempts = int(session.get("attempts", 0))
                incorrect = int(session.get("incorrect", 0))
                sessions.append({
                    "id": session.get("id"),
                    "started_at": session.get("started_at"),
                    "finished_at": session.get("finished_at"),
                    "duration_seconds": int(session.get("duration_seconds", 0)),
                    "question_total": int(session.get("question_total", APRON_OPS_DEFAULT_COUNT)),
                    "attempts": attempts,
                    "incorrect": incorrect,
                    "correct": max(0, attempts - incorrect),
                    "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else 0.0,
                    "events": deepcopy(session.get("events", [])),
                })
            question_stats = []
            for stat_id, stat in profile.get("apron_ops_question_stats", {}).items():
                attempts = int(stat.get("attempts", 0))
                incorrect = int(stat.get("incorrect", 0))
                question_stats.append({
                    "id": stat_id,
                    "label": stat["label"],
                    "category": stat.get("category", "Apron Ops"),
                    "attempts": attempts,
                    "incorrect": incorrect,
                    "correct": int(stat.get("correct", 0)),
                    "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else None,
                })
            question_stats.sort(key=lambda item: (-item["incorrect"], -item["attempts"], item["label"]))
            total_attempts = sum(s["attempts"] for s in sessions)
            total_incorrect = sum(s["incorrect"] for s in sessions)
            total_duration = sum(s["duration_seconds"] for s in sessions)
            lifetime = {
                "sessions": len(sessions),
                "attempts": total_attempts,
                "incorrect": total_incorrect,
                "correct": max(0, total_attempts - total_incorrect),
                "accuracy": round((total_attempts - total_incorrect) / total_attempts * 100, 1) if total_attempts else 0.0,
                "average_duration_seconds": round(total_duration / len(sessions)) if sessions else 0,
                "total_duration_seconds": total_duration,
            }
            return {
                "user": {"name": profile["display_name"]},
                "lifetime": lifetime,
                "sessions": sessions,
                "question_stats": question_stats,
                "active": self._apron_ops_view(profile),
                "configuration": {"question_count": APRON_OPS_DEFAULT_COUNT},
            }

    # ------------------------------------------------------------------
    # Airport locations validation (shared-bank editor)
    # ------------------------------------------------------------------
    def start_locations_validation(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_locations_validation") and not replace_active:
                raise APIError(
                    "A locations validation run is already in progress for this user. Resume it or explicitly replace it first.",
                    HTTPStatus.CONFLICT,
                )
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            question_ids = [question["id"] for question in self._locations_source_questions()]
            profile["active_locations_validation"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "phase": "review",
                "question_total": len(question_ids),
                "queue": question_ids,
                "reviewed": [],
                "skipped_count": 0,
                "draft_overrides": {},
                "draft_question_overrides": {},
                "draft_custom_questions": [],
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_locations_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation:
                raise APIError("There is no saved locations validation run to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_locations_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_locations_validation_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def submit_locations_validation(self, raw_username: Any, action: Any, raw_paths: Any = None) -> dict[str, Any]:
        if action not in {"keep", "replace"}:
            raise APIError("Choose whether to keep the configured marker or apply a drawing.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("No locations validation review question is available.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            question_id = validation["queue"][0]
            question = self._effective_location_question(question_id)
            question = self._apply_locations_validation_detail_draft(question, validation, question_id)
            draw_paths: list[list[list[float]]] | None = None
            if action == "replace":
                draw_paths = normalise_drawn_paths(
                    raw_paths,
                    LOCATIONS_CANVAS_WIDTH,
                    LOCATIONS_CANVAS_HEIGHT,
                    allow_point_paths=True,
                )
                validation.setdefault("draft_overrides", {})[question_id] = {
                    "paths": draw_paths,
                    "tolerance": question["tolerance"],
                }
            validation["queue"].pop(0)
            validation.setdefault("reviewed", []).append(question_id)
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "action": action,
                    "path_count": len(draw_paths) if draw_paths else 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            review_complete = not validation["queue"]
            if review_complete:
                validation["phase"] = "add_questions"
            self._touch(profile)
            self._save()
            return {
                "action": action,
                "feedback": (
                    f"New marker drawing staged for {question['label']}."
                    if action == "replace"
                    else f"Kept the current marker for {question['label']}."
                ),
                "review_complete": review_complete,
                "finished": False,
                "state": self._memory_snapshot(key, profile),
            }

    def skip_locations_validation_to_add_questions(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation or validation.get("phase", "review") != "review":
                raise APIError("The locations validation review is not currently open.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            skipped = len(validation.get("queue", []))
            validation["skipped_count"] = int(validation.get("skipped_count", 0)) + skipped
            validation["queue"] = []
            validation["phase"] = "add_questions"
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": None,
                    "label": f"{skipped} remaining locations",
                    "action": "skip_to_add_questions",
                    "path_count": 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {
                "feedback": f"Skipped {skipped} remaining locations. Their existing answers will stay unchanged.",
                "state": self._memory_snapshot(key, profile),
            }

    def edit_locations_validation_question_details(
        self,
        raw_username: Any,
        label_value: Any,
        clue_value: Any,
    ) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("Open a locations review question before editing its details.", HTTPStatus.CONFLICT)
            question_id = validation["queue"][0]
            label = cleaned_text(label_value, "Question", 100)
            clue = cleaned_text(clue_value, "Description", 280, required=False)
            existing_labels = set()
            for existing in self._locations_source_questions():
                if existing["id"] == question_id:
                    continue
                existing_labels.add(self._effective_location_question(existing["id"])["label"].casefold())
            for draft_id, draft in validation.get("draft_question_overrides", {}).items():
                if draft_id != question_id and isinstance(draft, dict):
                    existing_labels.add(str(draft.get("label", "")).casefold())
            existing_labels.update(
                str(question.get("label", "")).casefold()
                for question in validation.get("draft_custom_questions", [])
            )
            if label.casefold() in existing_labels:
                raise APIError("A locations question with that label already exists. Choose a distinct question.")
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            validation.setdefault("draft_question_overrides", {})[question_id] = {"label": label, "clue": clue}
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": label,
                    "action": "edit_question_details",
                    "path_count": 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {"feedback": f"Location details staged for {label}.", "state": self._memory_snapshot(key, profile)}

    def add_locations_validation_question(
        self,
        raw_username: Any,
        label_value: Any,
        category_value: Any,
        clue_value: Any,
        raw_paths: Any,
    ) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish the locations review before adding a new location question.", HTTPStatus.CONFLICT)
            label = cleaned_text(label_value, "Question label", 100)
            category = cleaned_text(category_value, "Category", 40)
            clue = cleaned_text(clue_value, "Description", 280, required=False)
            paths = normalise_drawn_paths(
                raw_paths,
                LOCATIONS_CANVAS_WIDTH,
                LOCATIONS_CANVAS_HEIGHT,
                allow_point_paths=True,
            )
            existing_labels = {self._effective_location_question(q["id"])["label"].casefold() for q in self._locations_source_questions()}
            existing_labels.update(str(q.get("label", "")).casefold() for q in validation.get("draft_custom_questions", []))
            if label.casefold() in existing_labels:
                raise APIError("A locations question with that label already exists. Choose a distinct label.")
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            custom_question = {
                "id": f"loc_custom_{uuid.uuid4().hex[:12]}",
                "label": label,
                "category": category,
                "clue": clue,
                "paths": paths,
                "tolerance": 20,
                "created_at": utc_now(),
                "source": "custom",
            }
            validation.setdefault("draft_custom_questions", []).append(custom_question)
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": custom_question["id"],
                    "label": label,
                    "action": "add_question",
                    "path_count": len(paths),
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {"feedback": f"{label} is staged for the shared locations bank.", "state": self._memory_snapshot(key, profile)}

    def _finish_locations_validation(self, profile: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(validation, keep_running=False)
        validation["finished_at"] = utc_now()
        route_overrides = self.memory.setdefault("location_route_overrides", {})
        for question_id, draft in validation.get("draft_overrides", {}).items():
            route_overrides[question_id] = {
                "paths": deepcopy(draft["paths"]),
                "tolerance": draft["tolerance"],
                "updated_at": utc_now(),
                "source": "locations_validation",
                "updated_by": profile["display_name"],
            }
        detail_overrides = self.memory.setdefault("location_question_overrides", {})
        for question_id, draft in validation.get("draft_question_overrides", {}).items():
            if isinstance(draft, dict):
                detail_overrides[question_id] = {
                    "label": draft["label"],
                    "clue": draft["clue"],
                    "updated_at": utc_now(),
                    "source": "locations_validation",
                    "updated_by": profile["display_name"],
                }
        custom_bank = self.memory.setdefault("location_custom_questions", [])
        existing_ids = {q.get("id") for q in custom_bank if isinstance(q, dict)}
        added_ids: list[str] = []
        for draft_question in validation.get("draft_custom_questions", []):
            if draft_question.get("id") not in existing_ids:
                custom_bank.append(deepcopy(draft_question))
                existing_ids.add(draft_question.get("id"))
                added_ids.append(draft_question["id"])
        if added_ids:
            for other_profile in self.memory["users"].values():
                active_game = other_profile.get("active_locations_game")
                if not active_game:
                    continue
                completed_ids = set(active_game.get("completed", []))
                queued_ids = set(active_game.get("queue", []))
                for question_id in added_ids:
                    if question_id not in completed_ids and question_id not in queued_ids:
                        active_game.setdefault("queue", []).append(question_id)
                        active_game["question_total"] = int(active_game.get("question_total", 0)) + 1
        summary = self._validation_summary(
            validation,
            override_count=len(route_overrides),
            bank_count=len(self._locations_source_questions()),
        )
        profile.setdefault("locations_validation_sessions", []).append(summary)
        profile["last_locations_validation"] = deepcopy(summary)
        profile["active_locations_validation"] = None
        return summary

    def finish_locations_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_locations_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish reviewing the locations bank before committing validation.", HTTPStatus.CONFLICT)
            summary = self._finish_locations_validation(profile, validation)
            self._touch(profile)
            self._save()
            return {"finished": True, "summary": summary, "state": self._memory_snapshot(key, profile)}

    # ------------------------------------------------------------------
    # YYC Ground Sort validation (shared-bank editor)
    # ------------------------------------------------------------------
    def start_yyc_ground_validation(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_yyc_ground_validation") and not replace_active:
                raise APIError("A YYC Ground Sort validation run is already in progress. Resume it or explicitly replace it first.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            questions = [question["id"] for question in self._yyc_ground_questions()]
            profile["active_yyc_ground_validation"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "phase": "review",
                "question_total": len(questions),
                "queue": questions,
                "reviewed": [],
                "skipped_count": 0,
                "draft_overrides": {},
                "draft_question_overrides": {},
                "draft_custom_questions": [],
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_yyc_ground_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation:
                raise APIError("There is no saved YYC Ground Sort validation run to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_yyc_ground_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_yyc_ground_validation_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def submit_yyc_ground_validation(self, raw_username: Any, action: Any, raw_paths: Any = None) -> dict[str, Any]:
        if action not in {"keep", "replace"}:
            raise APIError("Choose whether to keep the configured point or apply a drawing.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("No YYC Ground Sort validation question is available.", HTTPStatus.CONFLICT)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_validation_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            question_id = validation["queue"][0]
            question = self._effective_yyc_ground_question(question_id)
            question = self._apply_yyc_validation_detail_draft(question, validation, question_id)
            paths = None
            if action == "replace":
                paths = normalise_drawn_paths(raw_paths, YYC_GROUND_CANVAS_WIDTH, YYC_GROUND_CANVAS_HEIGHT, allow_point_paths=True)
                validation.setdefault("draft_overrides", {})[question_id] = {"paths": paths, "tolerance": question["tolerance"]}
            validation["queue"].pop(0)
            validation.setdefault("reviewed", []).append(question_id)
            validation.setdefault("events", []).append({
                "sequence": len(validation.get("events", [])) + 1,
                "question_id": question_id,
                "label": question["label"],
                "action": action,
                "path_count": len(paths) if paths else 0,
                "elapsed_seconds": int(round(elapsed)),
                "reviewed_at": utc_now(),
            })
            review_complete = not validation["queue"]
            if review_complete:
                validation["phase"] = "add_questions"
            self._touch(profile)
            self._save()
            return {
                "action": action,
                "feedback": f"New point drawing staged for {question['label']}." if action == "replace" else f"Kept the current point for {question['label']}.",
                "review_complete": review_complete,
                "finished": False,
                "state": self._memory_snapshot(key, profile),
            }

    def skip_yyc_ground_validation_to_add_questions(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation or validation.get("phase", "review") != "review":
                raise APIError("The YYC Ground Sort validation review is not currently open.", HTTPStatus.CONFLICT)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            skipped = len(validation.get("queue", []))
            validation["skipped_count"] = int(validation.get("skipped_count", 0)) + skipped
            validation["queue"] = []
            validation["phase"] = "add_questions"
            validation.setdefault("events", []).append({
                "sequence": len(validation.get("events", [])) + 1,
                "question_id": None,
                "label": f"{skipped} remaining YYC points",
                "action": "skip_to_add_questions",
                "path_count": 0,
                "elapsed_seconds": int(round(elapsed)),
                "reviewed_at": utc_now(),
            })
            self._touch(profile)
            self._save()
            return {"feedback": f"Skipped {skipped} remaining points. Their existing answers will stay unchanged.", "state": self._memory_snapshot(key, profile)}

    def edit_yyc_ground_validation_question_details(self, raw_username: Any, label_value: Any, clue_value: Any, use_value: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("Open a YYC Ground Sort review point before editing its details.", HTTPStatus.CONFLICT)
            question_id = validation["queue"][0]
            label = cleaned_text(label_value, "Question", 100)
            clue = cleaned_text(clue_value, "Description", 280, required=False)
            use = cleaned_text(use_value, "Who can use this point", 30)
            if use not in {"Jets", "Props", "Jets or Props"}:
                raise APIError("Choose Jets, Props, or Jets or Props.")
            labels = set()
            for question in self._yyc_ground_questions():
                if question["id"] != question_id:
                    labels.add(self._effective_yyc_ground_question(question["id"])["label"].casefold())
            for draft_id, draft in validation.get("draft_question_overrides", {}).items():
                if draft_id != question_id and isinstance(draft, dict):
                    labels.add(str(draft.get("label", "")).casefold())
            labels.update(str(question.get("label", "")).casefold() for question in validation.get("draft_custom_questions", []))
            if label.casefold() in labels:
                raise APIError("A YYC Ground Sort point with that label already exists.")
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            validation.setdefault("draft_question_overrides", {})[question_id] = {"label": label, "clue": clue, "use": use}
            validation.setdefault("events", []).append({
                "sequence": len(validation.get("events", [])) + 1,
                "question_id": question_id,
                "label": label,
                "action": "edit_question_details",
                "path_count": 0,
                "elapsed_seconds": int(round(elapsed)),
                "reviewed_at": utc_now(),
            })
            self._touch(profile)
            self._save()
            return {"feedback": f"YYC point details staged for {label}.", "state": self._memory_snapshot(key, profile)}

    def add_yyc_ground_validation_question(self, raw_username: Any, label_value: Any, category_value: Any, clue_value: Any, use_value: Any, raw_paths: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish the YYC Ground Sort review before adding a new point.", HTTPStatus.CONFLICT)
            label = cleaned_text(label_value, "Question label", 100)
            category = cleaned_text(category_value, "Category", 40)
            clue = cleaned_text(clue_value, "Description", 280, required=False)
            use = cleaned_text(use_value, "Who can use this point", 30)
            if use not in {"Jets", "Props", "Jets or Props"}:
                raise APIError("Choose Jets, Props, or Jets or Props.")
            paths = normalise_drawn_paths(raw_paths, YYC_GROUND_CANVAS_WIDTH, YYC_GROUND_CANVAS_HEIGHT, allow_point_paths=True)
            labels = {self._effective_yyc_ground_question(q["id"])["label"].casefold() for q in self._yyc_ground_questions()}
            labels.update(str(q.get("label", "")).casefold() for q in validation.get("draft_custom_questions", []))
            if label.casefold() in labels:
                raise APIError("A YYC Ground Sort point with that label already exists.")
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            question = {
                "id": f"yyc_custom_{uuid.uuid4().hex[:12]}",
                "label": label,
                "category": category,
                "clue": clue,
                "paths": paths,
                "tolerance": 20,
                "use": use,
                "created_at": utc_now(),
                "source": "custom",
            }
            validation.setdefault("draft_custom_questions", []).append(question)
            validation.setdefault("events", []).append({
                "sequence": len(validation.get("events", [])) + 1,
                "question_id": question["id"],
                "label": label,
                "action": "add_question",
                "path_count": len(paths),
                "elapsed_seconds": int(round(elapsed)),
                "reviewed_at": utc_now(),
            })
            self._touch(profile)
            self._save()
            return {"feedback": f"{label} is staged for the shared YYC Ground Sort bank.", "state": self._memory_snapshot(key, profile)}

    def _finish_yyc_ground_validation(self, profile: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        self._capture_elapsed(validation, keep_running=False)
        validation["finished_at"] = utc_now()
        route_overrides = self.memory.setdefault("yyc_ground_route_overrides", {})
        for question_id, draft in validation.get("draft_overrides", {}).items():
            route_overrides[question_id] = {"paths": deepcopy(draft["paths"]), "tolerance": draft["tolerance"], "updated_at": utc_now(), "source": "yyc_validation", "updated_by": profile["display_name"]}
        detail_overrides = self.memory.setdefault("yyc_ground_question_overrides", {})
        for question_id, draft in validation.get("draft_question_overrides", {}).items():
            if isinstance(draft, dict):
                detail_overrides[question_id] = {"label": draft["label"], "clue": draft["clue"], "use": draft["use"], "updated_at": utc_now(), "source": "yyc_validation", "updated_by": profile["display_name"]}
        custom_bank = self.memory.setdefault("yyc_ground_custom_questions", [])
        existing_ids = {q.get("id") for q in custom_bank if isinstance(q, dict)}
        added_ids: list[str] = []
        for question in validation.get("draft_custom_questions", []):
            if question.get("id") not in existing_ids:
                custom_bank.append(deepcopy(question))
                existing_ids.add(question.get("id"))
                added_ids.append(question["id"])
        if added_ids:
            for other_profile in self.memory["users"].values():
                game = other_profile.get("active_yyc_ground_game")
                if not game:
                    continue
                completed = set(game.get("completed", []))
                queued = set(game.get("queue", []))
                for question_id in added_ids:
                    if question_id not in completed and question_id not in queued:
                        game.setdefault("queue", []).append(question_id)
                        game["question_total"] = int(game.get("question_total", 0)) + 1
        summary = self._validation_summary(validation, len(route_overrides), len(self._yyc_ground_questions()))
        profile.setdefault("yyc_ground_validation_sessions", []).append(summary)
        profile["last_yyc_ground_validation"] = deepcopy(summary)
        profile["active_yyc_ground_validation"] = None
        return summary

    def finish_yyc_ground_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_yyc_ground_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish reviewing the YYC Ground Sort bank before committing validation.", HTTPStatus.CONFLICT)
            summary = self._finish_yyc_ground_validation(profile, validation)
            self._touch(profile)
            self._save()
            return {"finished": True, "summary": summary, "state": self._memory_snapshot(key, profile)}

    # ------------------------------------------------------------------
    # User validation of the shared bank
    # ------------------------------------------------------------------
    def start_validation(self, raw_username: Any, replace_active: bool = False) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if profile.get("active_validation") and not replace_active:
                raise APIError(
                    "A validation run is already in progress for this user. Resume it or explicitly replace it first.",
                    HTTPStatus.CONFLICT,
                )
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            self._pause_gates_if_running(profile)
            self._pause_apron_ops_if_running(profile)
            question_ids = [question["id"] for question in self._all_questions()]
            profile["active_validation"] = {
                "id": uuid.uuid4().hex[:12],
                "started_at": utc_now(),
                "phase": "review",
                "question_total": len(question_ids),
                "queue": question_ids,
                "reviewed": [],
                "skipped_count": 0,
                # Drafts remain isolated from shared practice scoring until Finish.
                "draft_overrides": {},
                "draft_question_overrides": {},
                "draft_custom_questions": [],
                "events": [],
                "elapsed_seconds": 0.0,
                "running_since": time.time(),
            }
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def resume_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation:
                raise APIError("There is no saved validation run to resume.", HTTPStatus.NOT_FOUND)
            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            self._touch(profile)
            self._save()
            return self._memory_snapshot(key, profile)

    def pause_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if self._pause_validation_if_running(profile):
                self._touch(profile)
                self._save()
            return self._memory_snapshot(key, profile)

    def submit_validation(self, raw_username: Any, action: Any, raw_paths: Any = None) -> dict[str, Any]:
        if action not in {"keep", "replace"}:
            raise APIError("Choose whether to keep the configured route or apply a drawing.")

        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("No validation review question is available.", HTTPStatus.CONFLICT)

            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            question_id = validation["queue"][0]
            question = self._effective_question(question_id)
            question = self._apply_validation_detail_draft(question, validation, question_id)
            draw_paths: list[list[list[float]]] | None = None

            if action == "replace":
                draw_paths = normalise_drawn_paths(raw_paths)
                validation.setdefault("draft_overrides", {})[question_id] = {
                    "paths": draw_paths,
                    "tolerance": question["tolerance"],
                }

            validation["queue"].pop(0)
            validation.setdefault("reviewed", []).append(question_id)
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": question["label"],
                    "action": action,
                    "path_count": len(draw_paths) if draw_paths else 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )

            review_complete = not validation["queue"]
            if review_complete:
                validation["phase"] = "add_questions"

            self._touch(profile)
            self._save()
            feedback = (
                f"New route drawing staged for {question['label']}."
                if action == "replace"
                else f"Kept the current route for {question['label']}."
            )
            return {
                "action": action,
                "feedback": feedback,
                "review_complete": review_complete,
                "finished": False,
                "state": self._memory_snapshot(key, profile),
            }

    def skip_validation_to_add_questions(self, raw_username: Any) -> dict[str, Any]:
        """Leave remaining routes unchanged and move directly to custom questions."""
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation or validation.get("phase", "review") != "review":
                raise APIError("The validation review is not currently open.", HTTPStatus.CONFLICT)

            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            skipped = len(validation.get("queue", []))
            validation["skipped_count"] = int(validation.get("skipped_count", 0)) + skipped
            validation["queue"] = []
            validation["phase"] = "add_questions"
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": None,
                    "label": f"{skipped} remaining routes",
                    "action": "skip_to_add_questions",
                    "path_count": 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {
                "feedback": f"Skipped {skipped} remaining routes. Their existing answers will stay unchanged.",
                "state": self._memory_snapshot(key, profile),
            }

    def edit_validation_question_details(
        self,
        raw_username: Any,
        label_value: Any,
        clue_value: Any,
    ) -> dict[str, Any]:
        """Stage a label/description edit for the current validation prompt."""
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation or validation.get("phase", "review") != "review" or not validation.get("queue"):
                raise APIError("Open a route review question before editing its details.", HTTPStatus.CONFLICT)

            question_id = validation["queue"][0]
            label = cleaned_text(label_value, "Question", 80)
            clue = cleaned_text(clue_value, "Description", 220, required=False)

            # A final bank should not contain indistinguishable question labels.
            existing_labels = set()
            for existing in self._all_questions():
                if existing["id"] == question_id:
                    continue
                effective = self._effective_question(existing["id"])
                existing_labels.add(effective["label"].casefold())
            for draft_id, draft in validation.get("draft_question_overrides", {}).items():
                if draft_id != question_id and isinstance(draft, dict):
                    existing_labels.add(str(draft.get("label", "")).casefold())
            existing_labels.update(
                str(question.get("label", "")).casefold()
                for question in validation.get("draft_custom_questions", [])
            )
            if label.casefold() in existing_labels:
                raise APIError("A question with that label already exists. Choose a distinct question.")

            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            validation.setdefault("draft_question_overrides", {})[question_id] = {
                "label": label,
                "clue": clue,
            }
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": question_id,
                    "label": label,
                    "action": "edit_question_details",
                    "path_count": 0,
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {
                "feedback": f"Question details staged for {label}.",
                "state": self._memory_snapshot(key, profile),
            }

    def add_validation_question(
        self,
        raw_username: Any,
        label_value: Any,
        category_value: Any,
        clue_value: Any,
        raw_paths: Any,
    ) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish the route review before adding a new question.", HTTPStatus.CONFLICT)

            label = cleaned_text(label_value, "Question label", 80)
            category = cleaned_text(category_value, "Category", 20)
            if category not in {"Runway", "Taxiway"}:
                raise APIError("Category must be Runway or Taxiway.")
            clue = cleaned_text(clue_value, "Clue", 220, required=False)
            if not clue:
                clue = "A validator-defined airport route."
            paths = normalise_drawn_paths(raw_paths)

            existing_labels = {question["label"].casefold() for question in self._all_questions()}
            existing_labels.update(
                str(question.get("label", "")).casefold()
                for question in validation.get("draft_custom_questions", [])
            )
            if label.casefold() in existing_labels:
                raise APIError("A question with that label already exists. Choose a distinct label.")

            self._pause_game_if_running(profile)
            self._pause_locations_if_running(profile)
            self._pause_locations_validation_if_running(profile)
            self._pause_yyc_ground_game_if_running(profile)
            self._pause_yyc_ground_validation_if_running(profile)
            if validation.get("running_since") is None:
                validation["running_since"] = time.time()
            elapsed = self._capture_elapsed(validation, keep_running=True)
            custom_question = {
                "id": f"custom_{uuid.uuid4().hex[:12]}",
                "label": label,
                "category": category,
                "clue": clue,
                "paths": paths,
                "tolerance": 20,
                "created_at": utc_now(),
                "source": "custom",
            }
            validation.setdefault("draft_custom_questions", []).append(custom_question)
            validation.setdefault("events", []).append(
                {
                    "sequence": len(validation.get("events", [])) + 1,
                    "question_id": custom_question["id"],
                    "label": label,
                    "action": "add_question",
                    "path_count": len(paths),
                    "elapsed_seconds": int(round(elapsed)),
                    "reviewed_at": utc_now(),
                }
            )
            self._touch(profile)
            self._save()
            return {
                "feedback": f"{label} is staged for the shared practice question bank.",
                "state": self._memory_snapshot(key, profile),
            }

    def _finish_validation(self, profile: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
        """Promote the user's validation drafts to the shared route bank."""
        self._capture_elapsed(validation, keep_running=False)
        validation["finished_at"] = utc_now()
        overrides = self.memory.setdefault("route_overrides", {})
        for question_id, draft in validation.get("draft_overrides", {}).items():
            overrides[question_id] = {
                "paths": deepcopy(draft["paths"]),
                "tolerance": draft["tolerance"],
                "updated_at": utc_now(),
                "source": "validation",
                "updated_by": profile["display_name"],
            }

        question_overrides = self.memory.setdefault("question_overrides", {})
        for question_id, draft in validation.get("draft_question_overrides", {}).items():
            if not isinstance(draft, dict):
                continue
            question_overrides[question_id] = {
                "label": draft["label"],
                "clue": draft["clue"],
                "updated_at": utc_now(),
                "source": "validation",
                "updated_by": profile["display_name"],
            }

        custom_bank = self.memory.setdefault("custom_questions", [])
        existing_ids = {question.get("id") for question in custom_bank if isinstance(question, dict)}
        added_ids: list[str] = []
        for draft_question in validation.get("draft_custom_questions", []):
            if draft_question.get("id") not in existing_ids:
                custom_bank.append(deepcopy(draft_question))
                existing_ids.add(draft_question.get("id"))
                added_ids.append(draft_question["id"])

        # The shared bank changed. Append new questions to every paused/active user
        # game so users who started before validation are not left with stale queues.
        if added_ids:
            for other_profile in self.memory["users"].values():
                active_game = other_profile.get("active_game")
                if not active_game:
                    continue
                completed_ids = set(active_game.get("completed", []))
                queued_ids = set(active_game.get("queue", []))
                for question_id in added_ids:
                    if question_id not in completed_ids and question_id not in queued_ids:
                        active_game.setdefault("queue", []).append(question_id)
                        active_game["question_total"] = int(active_game.get("question_total", 0)) + 1

        summary = self._validation_summary(
            validation,
            override_count=len(overrides),
            bank_count=len(self._all_questions()),
        )
        profile.setdefault("validation_sessions", []).append(summary)
        profile["last_validation"] = deepcopy(summary)
        profile["active_validation"] = None
        return summary

    def finish_validation(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            validation = profile.get("active_validation")
            if not validation or validation.get("phase") != "add_questions":
                raise APIError("Finish reviewing the question bank before committing validation.", HTTPStatus.CONFLICT)
            summary = self._finish_validation(profile, validation)
            self._touch(profile)
            self._save()
            return {
                "finished": True,
                "summary": summary,
                "state": self._memory_snapshot(key, profile),
            }

    # ------------------------------------------------------------------
    # Shared question-bank import and export
    # ------------------------------------------------------------------
    def export_question_banks(self, raw_username: Any) -> dict[str, Any]:
        """Export the effective questions and answer geometry for both game modes."""
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            self._touch(profile)
            return {
                "format": "airport-label-quest/question-banks",
                "version": 1,
                "exported_at": utc_now(),
                "main_chart": {
                    "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
                    "questions": [
                        deepcopy(self._effective_question(question["id"]))
                        for question in self._all_questions()
                    ],
                },
                "locations_chart": {
                    "canvas": {
                        "width": LOCATIONS_CANVAS_WIDTH,
                        "height": LOCATIONS_CANVAS_HEIGHT,
                    },
                    "questions": [
                        deepcopy(self._effective_location_question(question["id"]))
                        for question in self._locations_source_questions()
                    ],
                },
            }

    def export_locations_question_bank(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            self._touch(profile)
            return {
                "format": "airport-label-quest/locations-question-bank",
                "version": 1,
                "exported_at": utc_now(),
                "canvas": {"width": LOCATIONS_CANVAS_WIDTH, "height": LOCATIONS_CANVAS_HEIGHT},
                "questions": [
                    deepcopy(self._effective_location_question(question["id"]))
                    for question in self._locations_source_questions()
                ],
            }

    def import_question_banks(self, raw_username: Any, raw_bank: Any) -> dict[str, Any]:
        """Replace shared banks from a portable JSON export/import document."""
        if not isinstance(raw_bank, dict):
            raise APIError("The imported file must contain a JSON object.")
        format_name = raw_bank.get("format")
        if format_name not in (
            None,
            "airport-label-quest/question-banks",
            "airport-label-quest/main-question-bank",
            "airport-label-quest/locations-question-bank",
        ):
            raise APIError("This is not a supported Airport Label Quest question-bank file.")

        main_section = raw_bank.get("main_chart")
        locations_section = raw_bank.get("locations_chart")
        if format_name == "airport-label-quest/locations-question-bank":
            main_raw = None
            locations_raw = raw_bank.get("questions")
        else:
            main_raw = main_section.get("questions") if isinstance(main_section, dict) else raw_bank.get("questions")
            locations_raw = locations_section.get("questions") if isinstance(locations_section, dict) else None
        if main_raw is None and locations_raw is None:
            raise APIError("The imported JSON does not contain a main or locations question bank.")

        main_questions = None
        locations_questions = None
        if main_raw is not None:
            main_questions = self._normalise_bank_list(main_raw, CANVAS_WIDTH, CANVAS_HEIGHT, "main")
        if locations_raw is not None:
            locations_questions = self._normalise_bank_list(
                locations_raw,
                LOCATIONS_CANVAS_WIDTH,
                LOCATIONS_CANVAS_HEIGHT,
                "locations",
            )

        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            if main_questions is not None:
                # Imported records already include their answer paths, labels, and
                # clues, so clear layered edits from the old shared main bank.
                self.memory["question_bank_override"] = deepcopy(main_questions)
                self.memory["route_overrides"] = {}
                self.memory["question_overrides"] = {}
                self.memory["custom_questions"] = []
            if locations_questions is not None:
                self.memory["location_bank_override"] = deepcopy(locations_questions)
                self.memory["location_route_overrides"] = {}
                self.memory["location_question_overrides"] = {}
                self.memory["location_custom_questions"] = []

            # Existing in-progress queues may point at removed IDs. Keep completed
            # history, but safely stop affected active games and validation drafts.
            for other_profile in self.memory["users"].values():
                if main_questions is not None:
                    other_profile["active_game"] = None
                    other_profile["active_validation"] = None
                if locations_questions is not None:
                    other_profile["active_locations_game"] = None
                    other_profile["active_locations_validation"] = None
            self._touch(profile)
            self._save()
            return {
                "feedback": "Shared question-bank data imported successfully.",
                "imported": {
                    "main_questions": len(main_questions) if main_questions is not None else None,
                    "locations_questions": len(locations_questions) if locations_questions is not None else None,
                },
                "state": self._memory_snapshot(key, profile),
            }

    # ------------------------------------------------------------------
    # Full application data import and export
    # ------------------------------------------------------------------
    def export_full_data(self, raw_username: Any) -> dict[str, Any]:
        """Create one portable backup containing users, banks, and flashcards."""
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            self._touch(profile)
            return {
                "format": "airport-label-quest/full-data",
                "version": 2,
                "exported_at": utc_now(),
                # Include effective snapshots so the backup is portable even when
                # default banks came from bundled Python files rather than memory.
                "banks": {
                    "main_chart": {
                        "canvas": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
                        "questions": [deepcopy(self._effective_question(q["id"])) for q in self._all_questions()],
                    },
                    "locations_chart": {
                        "canvas": {"width": LOCATIONS_CANVAS_WIDTH, "height": LOCATIONS_CANVAS_HEIGHT},
                        "questions": [deepcopy(self._effective_location_question(q["id"])) for q in self._locations_source_questions()],
                    },
                    "yyc_ground_chart": {
                        "canvas": {"width": YYC_GROUND_CANVAS_WIDTH, "height": YYC_GROUND_CANVAS_HEIGHT},
                        "questions": [deepcopy(self._effective_yyc_ground_question(q["id"])) for q in self._yyc_ground_questions()],
                    },
                },
                "data": deepcopy(self.memory),
            }

    def _normalise_imported_full_data(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise APIError("The imported backup must contain a JSON object.")
        if raw.get("format") == "airport-label-quest/full-data":
            document = raw.get("data")
        else:
            # Also accept a raw memory document from an earlier manual backup.
            document = raw
        if not isinstance(document, dict):
            raise APIError("The backup does not contain an application data document.")

        # Versions before multi-user support kept one profile at the root. Treat
        # such a JSON document as a legacy Guest profile rather than rejecting it.
        legacy_single_profile = not isinstance(document.get("users"), dict)
        if legacy_single_profile and not self._legacy_has_user_data(document) and "schema_version" not in document:
            raise APIError("The backup does not contain user profiles or recognizable legacy data.")
        if not legacy_single_profile and len(document["users"]) > 250:
            raise APIError("The backup contains too many user profiles.")

        memory = self._empty_memory()
        for key in (
            "route_overrides", "question_overrides", "custom_questions",
            "location_route_overrides", "location_question_overrides", "location_custom_questions",
            "yyc_ground_route_overrides", "yyc_ground_question_overrides", "yyc_ground_custom_questions",
            "question_bank_override", "location_bank_override", "yyc_ground_bank_override",
        ):
            if key in document:
                memory[key] = deepcopy(document[key])
        for dict_key in (
            "route_overrides", "question_overrides",
            "location_route_overrides", "location_question_overrides",
            "yyc_ground_route_overrides", "yyc_ground_question_overrides",
        ):
            if not isinstance(memory[dict_key], dict):
                raise APIError(f"Backup field {dict_key} is invalid.")
        for list_key in ("custom_questions", "location_custom_questions", "yyc_ground_custom_questions"):
            if not isinstance(memory[list_key], list):
                raise APIError(f"Backup field {list_key} is invalid.")
        for bank_key in ("question_bank_override", "location_bank_override", "yyc_ground_bank_override"):
            if memory[bank_key] is not None and not isinstance(memory[bank_key], list):
                raise APIError(f"Backup field {bank_key} is invalid.")

        # Full-data export v2 carries effective bank snapshots. Promote those into
        # portable source overrides so the imported backup does not depend on the
        # target deployment's bundled Python question files.
        bank_snapshots = raw.get("banks") if isinstance(raw, dict) and raw.get("format") == "airport-label-quest/full-data" else document.get("banks")
        if bank_snapshots is not None:
            if not isinstance(bank_snapshots, dict):
                raise APIError("Backup bank snapshots are invalid.")
            main_snapshot = bank_snapshots.get("main_chart")
            locations_snapshot = bank_snapshots.get("locations_chart")
            yyc_snapshot = bank_snapshots.get("yyc_ground_chart")
            if main_snapshot is not None:
                if not isinstance(main_snapshot, dict):
                    raise APIError("Main-chart bank snapshot is invalid.")
                memory["question_bank_override"] = self._normalise_bank_list(main_snapshot.get("questions"), CANVAS_WIDTH, CANVAS_HEIGHT, "main")
                memory["route_overrides"] = {}
                memory["question_overrides"] = {}
                memory["custom_questions"] = []
            if locations_snapshot is not None:
                if not isinstance(locations_snapshot, dict):
                    raise APIError("Locations bank snapshot is invalid.")
                memory["location_bank_override"] = self._normalise_bank_list(locations_snapshot.get("questions"), LOCATIONS_CANVAS_WIDTH, LOCATIONS_CANVAS_HEIGHT, "locations")
                memory["location_route_overrides"] = {}
                memory["location_question_overrides"] = {}
                memory["location_custom_questions"] = []
            if yyc_snapshot is not None:
                if not isinstance(yyc_snapshot, dict):
                    raise APIError("YYC Ground Sort bank snapshot is invalid.")
                memory["yyc_ground_bank_override"] = self._normalise_yyc_ground_bank(yyc_snapshot.get("questions"))
                memory["yyc_ground_route_overrides"] = {}
                memory["yyc_ground_question_overrides"] = {}
                memory["yyc_ground_custom_questions"] = []

        raw_profiles = (
            {"guest": self._legacy_profile(document)}
            if legacy_single_profile
            else document["users"]
        )
        for stored_key, raw_profile in raw_profiles.items():
            profile = self._normalise_loaded_profile(raw_profile, str(stored_key))
            if not profile:
                raise APIError("One of the backup user profiles is invalid.")
            if len(profile.get("flashcard_decks", [])) > 500:
                raise APIError("A backup user profile contains too many flashcard decks.")
            for deck in profile.get("flashcard_decks", []):
                if not isinstance(deck, dict) or not isinstance(deck.get("cards", []), list):
                    raise APIError("A flashcard deck in the backup is invalid.")
                if len(deck["cards"]) > 5_000:
                    raise APIError("A flashcard deck in the backup contains too many cards.")
            key = profile["display_name"].casefold()
            if key in memory["users"]:
                raise APIError("The backup contains duplicate user names.")
            memory["users"][key] = profile
        memory["schema_version"] = 11
        return memory

    def import_full_data(self, raw_username: Any, raw_data: Any) -> dict[str, Any]:
        # Previous releases exported question-bank-only JSON files. Accept those in
        # the new full-data dialog without discarding unrelated user profiles.
        legacy_bank_formats = {
            "airport-label-quest/question-banks",
            "airport-label-quest/main-question-bank",
            "airport-label-quest/locations-question-bank",
        }
        bank_document = None
        if isinstance(raw_data, list):
            bank_document = {
                "format": "airport-label-quest/main-question-bank",
                "version": 1,
                "questions": raw_data,
            }
        elif isinstance(raw_data, dict):
            if raw_data.get("format") in legacy_bank_formats:
                bank_document = raw_data
            elif "questions" in raw_data and "users" not in raw_data and "data" not in raw_data:
                bank_document = {
                    "format": "airport-label-quest/main-question-bank",
                    "version": 1,
                    "questions": raw_data.get("questions"),
                }
        if bank_document is not None:
            result = self.import_question_banks(raw_username, bank_document)
            return {
                "feedback": "Legacy question-bank data imported successfully. Existing user profiles were preserved.",
                "current_user_available": True,
                "state": result["state"],
                "user_count": len(self.memory["users"]),
                "legacy_bank_import": True,
            }

        with self.lock:
            current_key, _ = self._username_parts(raw_username)
            imported = self._normalise_imported_full_data(raw_data)
            self.memory = imported
            current_profile = self.memory["users"].get(current_key)
            self._save()
            return {
                "feedback": "All application data imported successfully.",
                "current_user_available": current_profile is not None,
                "state": self._memory_snapshot(current_key, current_profile) if current_profile else None,
                "user_count": len(self.memory["users"]),
                "legacy_bank_import": False,
            }

    # ------------------------------------------------------------------
    # User-specific trends and reset
    # ------------------------------------------------------------------
    def trends(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            sessions = []
            for session in profile.get("sessions", []):
                attempts = int(session.get("attempts", 0))
                incorrect = int(session.get("incorrect", 0))
                sessions.append(
                    {
                        "id": session.get("id"),
                        "started_at": session.get("started_at"),
                        "finished_at": session.get("finished_at"),
                        "duration_seconds": int(session.get("duration_seconds", 0)),
                        "question_total": int(session.get("question_total", len(self._all_questions()))),
                        "attempts": attempts,
                        "incorrect": incorrect,
                        "correct": max(0, attempts - incorrect),
                        "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else 0.0,
                        "events": deepcopy(session.get("events", [])),
                    }
                )

            question_stats = []
            for question in self._all_questions():
                stat = profile.get("question_stats", {}).get(question["id"], {})
                attempts = int(stat.get("attempts", 0))
                incorrect = int(stat.get("incorrect", 0))
                question_stats.append(
                    {
                        "id": question["id"],
                        "label": question["label"],
                        "category": question["category"],
                        "attempts": attempts,
                        "incorrect": incorrect,
                        "correct": int(stat.get("correct", 0)),
                        "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else None,
                    }
                )
            question_stats.sort(key=lambda item: (-item["incorrect"], -item["attempts"], item["label"]))

            total_attempts = sum(session["attempts"] for session in sessions)
            total_incorrect = sum(session["incorrect"] for session in sessions)
            total_duration = sum(session["duration_seconds"] for session in sessions)
            lifetime = {
                "sessions": len(sessions),
                "attempts": total_attempts,
                "incorrect": total_incorrect,
                "correct": max(0, total_attempts - total_incorrect),
                "accuracy": round((total_attempts - total_incorrect) / total_attempts * 100, 1)
                if total_attempts
                else 0.0,
                "average_duration_seconds": round(total_duration / len(sessions)) if sessions else 0,
                "total_duration_seconds": total_duration,
            }
            return {
                "user": {"name": profile["display_name"]},
                "lifetime": lifetime,
                "sessions": sessions,
                "question_stats": question_stats,
                "active": self._active_view(profile),
                "validation": self._validation_view(profile),
                "configuration": {
                    "override_count": len(self.memory.get("route_overrides", {})),
                    "question_override_count": len(self.memory.get("question_overrides", {})),
                    "custom_question_count": len(self._all_questions()) - len(self._main_source_questions()),
                    "validation_count": len(profile.get("validation_sessions", [])),
                },
            }

    def location_trends(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            sessions = []
            for session in profile.get("location_sessions", []):
                attempts = int(session.get("attempts", 0))
                incorrect = int(session.get("incorrect", 0))
                sessions.append(
                    {
                        "id": session.get("id"),
                        "started_at": session.get("started_at"),
                        "finished_at": session.get("finished_at"),
                        "duration_seconds": int(session.get("duration_seconds", 0)),
                        "question_total": int(session.get("question_total", len(self._locations_source_questions()))),
                        "attempts": attempts,
                        "incorrect": incorrect,
                        "correct": max(0, attempts - incorrect),
                        "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else 0.0,
                        "events": deepcopy(session.get("events", [])),
                    }
                )

            question_stats = []
            for question in self._locations_source_questions():
                stat = profile.get("location_question_stats", {}).get(question["id"], {})
                attempts = int(stat.get("attempts", 0))
                incorrect = int(stat.get("incorrect", 0))
                question_stats.append(
                    {
                        "id": question["id"],
                        "label": question["label"],
                        "category": question["category"],
                        "attempts": attempts,
                        "incorrect": incorrect,
                        "correct": int(stat.get("correct", 0)),
                        "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else None,
                    }
                )
            question_stats.sort(key=lambda item: (-item["incorrect"], -item["attempts"], item["label"]))

            total_attempts = sum(session["attempts"] for session in sessions)
            total_incorrect = sum(session["incorrect"] for session in sessions)
            total_duration = sum(session["duration_seconds"] for session in sessions)
            lifetime = {
                "sessions": len(sessions),
                "attempts": total_attempts,
                "incorrect": total_incorrect,
                "correct": max(0, total_attempts - total_incorrect),
                "accuracy": round((total_attempts - total_incorrect) / total_attempts * 100, 1)
                if total_attempts
                else 0.0,
                "average_duration_seconds": round(total_duration / len(sessions)) if sessions else 0,
                "total_duration_seconds": total_duration,
            }
            return {
                "user": {"name": profile["display_name"]},
                "lifetime": lifetime,
                "sessions": sessions,
                "question_stats": question_stats,
                "active": self._locations_view(profile),
                "locations_validation": self._locations_validation_view(profile),
                "configuration": {
                    "question_count": len(self._locations_source_questions()),
                    "validation_count": len(profile.get("locations_validation_sessions", [])),
                    "route_override_count": len(self.memory.get("location_route_overrides", {})),
                    "detail_override_count": len(self.memory.get("location_question_overrides", {})),
                },
            }

    # ------------------------------------------------------------------
    # YYC Ground Sort trends
    # ------------------------------------------------------------------
    def yyc_ground_trends(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            sessions = []
            for session in profile.get("yyc_ground_sessions", []):
                attempts = int(session.get("attempts", 0))
                incorrect = int(session.get("incorrect", 0))
                sessions.append({
                    "id": session.get("id"),
                    "started_at": session.get("started_at"),
                    "finished_at": session.get("finished_at"),
                    "duration_seconds": int(session.get("duration_seconds", 0)),
                    "question_total": int(session.get("question_total", len(self._yyc_ground_questions()))),
                    "attempts": attempts,
                    "incorrect": incorrect,
                    "correct": max(0, attempts - incorrect),
                    "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else 0.0,
                    "events": deepcopy(session.get("events", [])),
                })
            stats = []
            for question in self._yyc_ground_questions():
                stat = profile.get("yyc_ground_question_stats", {}).get(question["id"], {})
                attempts = int(stat.get("attempts", 0))
                incorrect = int(stat.get("incorrect", 0))
                stats.append({
                    "id": question["id"],
                    "label": question["label"],
                    "category": question["category"],
                    "attempts": attempts,
                    "incorrect": incorrect,
                    "correct": int(stat.get("correct", 0)),
                    "locate_incorrect": int(stat.get("locate_incorrect", 0)),
                    "use_incorrect": int(stat.get("use_incorrect", 0)),
                    "accuracy": round((attempts - incorrect) / attempts * 100, 1) if attempts else None,
                })
            stats.sort(key=lambda item: (-item["incorrect"], -item["attempts"], item["label"]))
            total_attempts = sum(session["attempts"] for session in sessions)
            total_incorrect = sum(session["incorrect"] for session in sessions)
            total_duration = sum(session["duration_seconds"] for session in sessions)
            lifetime = {
                "sessions": len(sessions),
                "attempts": total_attempts,
                "incorrect": total_incorrect,
                "correct": max(0, total_attempts - total_incorrect),
                "accuracy": round((total_attempts - total_incorrect) / total_attempts * 100, 1) if total_attempts else 0.0,
                "average_duration_seconds": round(total_duration / len(sessions)) if sessions else 0,
                "total_duration_seconds": total_duration,
            }
            return {
                "user": {"name": profile["display_name"]},
                "lifetime": lifetime,
                "sessions": sessions,
                "question_stats": stats,
                "active": self._yyc_ground_view(profile),
                "validation": self._yyc_ground_validation_view(profile),
                "configuration": {
                    "question_count": len(self._yyc_ground_questions()),
                    "validation_count": len(profile.get("yyc_ground_validation_sessions", [])),
                    "route_override_count": len(self.memory.get("yyc_ground_route_overrides", {})),
                    "detail_override_count": len(self.memory.get("yyc_ground_question_overrides", {})),
                },
            }

    # ------------------------------------------------------------------
    # Flashcard decks (per-user study library)
    # ------------------------------------------------------------------
    @staticmethod
    def _flashcard_text(value: Any, label: str) -> str:
        if not isinstance(value, str):
            raise APIError(f"{label} is required.")
        text = value.strip()
        if not text:
            raise APIError(f"{label} is required.")
        if len(text) > 2_000:
            raise APIError(f"{label} must be 2,000 characters or fewer.")
        return text

    @staticmethod
    def _normalise_flashcard_image(value: Any, label: str) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise APIError(f"{label} must be an image data URL.")
        if len(value) > 2_800_000:
            raise APIError(f"{label} is too large. Choose an image under roughly 2 MB.")
        match = FLASHCARD_IMAGE_PATTERN.match(value)
        if not match:
            raise APIError(f"{label} must be a PNG, JPEG, WEBP, or GIF image.")
        try:
            decoded = base64.b64decode(match.group(1), validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise APIError(f"{label} contains invalid image data.") from error
        if len(decoded) > 2_000_000:
            raise APIError(f"{label} is too large. Choose an image under 2 MB.")
        return value

    @staticmethod
    def _flashcard_deck_by_id(profile: dict[str, Any], deck_id: str) -> dict[str, Any]:
        for deck in profile.get("flashcard_decks", []):
            if deck.get("id") == deck_id:
                return deck
        raise APIError("This flashcard deck is no longer available.", HTTPStatus.NOT_FOUND)

    @staticmethod
    def _flashcard_by_id(deck: dict[str, Any], card_id: str) -> dict[str, Any]:
        for card in deck.get("cards", []):
            if card.get("id") == card_id:
                return card
        raise APIError("This flashcard is no longer available.", HTTPStatus.NOT_FOUND)

    @staticmethod
    def _public_flashcard(card: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": card["id"],
            "question": card["question"],
            "answer": card["answer"],
            "question_image": card.get("question_image"),
            "answer_image": card.get("answer_image"),
            "status": card.get("status", "new"),
            "review_count": int(card.get("review_count", 0)),
            "easy_count": int(card.get("easy_count", 0)),
            "mid_count": int(card.get("mid_count", 0)),
            "hard_count": int(card.get("hard_count", 0)),
            "last_rating": card.get("last_rating"),
            "last_reviewed_at": card.get("last_reviewed_at"),
            "created_at": card.get("created_at"),
            "updated_at": card.get("updated_at"),
        }

    def _flashcard_deck_stats(self, deck: dict[str, Any]) -> dict[str, Any]:
        cards = deck.get("cards", [])
        counts = {state: 0 for state in FLASHCARD_STATES}
        for card in cards:
            state = card.get("status", "new")
            counts[state if state in FLASHCARD_STATES else "new"] += 1
        reviews = sum(int(card.get("review_count", 0)) for card in cards)
        difficult = []
        for card in cards:
            review_count = int(card.get("review_count", 0))
            hard_count = int(card.get("hard_count", 0))
            mid_count = int(card.get("mid_count", 0))
            forgotten_score = hard_count * 2 + mid_count
            if forgotten_score or card.get("status") == "hard":
                difficult.append(
                    {
                        "id": card["id"],
                        "question": card["question"],
                        "answer": card["answer"],
                        "status": card.get("status", "new"),
                        "review_count": review_count,
                        "hard_count": hard_count,
                        "mid_count": mid_count,
                        "forgotten_score": forgotten_score,
                        "hard_rate": round(hard_count / review_count * 100, 1) if review_count else 0.0,
                    }
                )
        difficult.sort(key=lambda item: (-item["forgotten_score"], -item["hard_count"], item["question"].casefold()))
        return {
            "card_count": len(cards),
            "new_count": counts["new"],
            "easy_count": counts["easy"],
            "mid_count": counts["mid"],
            "hard_count": counts["hard"],
            "total_reviews": reviews,
            "study_sessions": int(deck.get("study_sessions", 0)),
            "common_mistakes": difficult[:10],
        }

    def _public_flashcard_deck(self, deck: dict[str, Any], include_cards: bool = False) -> dict[str, Any]:
        payload = {
            "id": deck["id"],
            "title": deck["title"],
            "created_at": deck.get("created_at"),
            "updated_at": deck.get("updated_at"),
            "source": deck.get("source"),
            "stats": self._flashcard_deck_stats(deck),
        }
        if include_cards:
            payload["cards"] = [self._public_flashcard(card) for card in deck.get("cards", [])]
        return payload

    def flashcard_decks(self, raw_username: Any) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            decks = [self._public_flashcard_deck(deck) for deck in profile.get("flashcard_decks", [])]
            decks.sort(key=lambda deck: (deck.get("updated_at") or "", deck["title"].casefold()), reverse=True)
            return {"decks": decks}

    def create_flashcard_deck(self, raw_username: Any, title_value: Any) -> dict[str, Any]:
        title = cleaned_text(title_value, "Deck title", 100)
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            existing_titles = {str(deck.get("title", "")).casefold() for deck in profile.get("flashcard_decks", [])}
            if title.casefold() in existing_titles:
                raise APIError("A deck with that title already exists.")
            now = utc_now()
            deck = {
                "id": f"deck_{uuid.uuid4().hex[:12]}",
                "title": title,
                "created_at": now,
                "updated_at": now,
                "study_sessions": 0,
                "cards": [],
            }
            profile.setdefault("flashcard_decks", []).append(deck)
            self._touch(profile)
            self._save()
            return {"deck": self._public_flashcard_deck(deck, include_cards=True), "state": self._memory_snapshot(key, profile)}

    @staticmethod
    def _decode_quizlet_pdf(value: Any) -> bytes:
        """Accept the browser-supplied PDF (base64 data URL) and return raw bytes."""
        if not isinstance(value, str) or not value:
            raise APIError("Attach the PDF saved from the Quizlet print page.")
        if len(value) > QUIZLET_PDF_MAX_BYTES * 4 // 3 + 64:
            raise APIError("The PDF is too large. Quizlet print PDFs should be under 15 MB.")
        match = QUIZLET_PDF_PATTERN.match(value)
        if not match:
            raise APIError("The uploaded file must be a PDF.")
        try:
            decoded = base64.b64decode(match.group(1), validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise APIError("The uploaded PDF could not be decoded.") from error
        if len(decoded) > QUIZLET_PDF_MAX_BYTES:
            raise APIError("The PDF is too large. Quizlet print PDFs should be under 15 MB.")
        if b"%PDF" not in decoded[:1024]:
            raise APIError("The uploaded file is not a PDF document.")
        return decoded

    def import_quizlet_deck(self, raw_username: Any, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a deck from a PDF printed from a Quizlet set.

        The browser cannot fetch Quizlet directly (cross-origin) and this server
        deliberately ships without a headless browser, so the user prints the
        Quizlet print page to PDF and uploads it here. The PDF is parsed in
        memory and discarded; only the resulting cards are stored. Every card
        starts in the ``new`` state.
        """
        title = cleaned_text(payload.get("title"), "Deck name", 100)
        try:
            source_url = normalise_quizlet_url(payload.get("url"))
        except QuizletImportError as error:
            raise APIError(str(error)) from error
        pdf_bytes = self._decode_quizlet_pdf(payload.get("pdf"))
        # Parse outside the lock: it is CPU-bound and does not touch shared state.
        try:
            parsed_cards = parse_quizlet_pdf(pdf_bytes)
        except QuizletImportError as error:
            raise APIError(str(error)) from error
        except Exception as error:  # pragma: no cover - defensive parser boundary
            print(f"Quizlet PDF parse failure: {error!r}")
            raise APIError("The PDF could not be read. Save the Quizlet print page again as a PDF and retry.") from error
        finally:
            del pdf_bytes
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            existing_titles = {str(deck.get("title", "")).casefold() for deck in profile.get("flashcard_decks", [])}
            if title.casefold() in existing_titles:
                raise APIError("A deck with that name already exists. Choose a different name.")
            if len(profile.get("flashcard_decks", [])) >= 500:
                raise APIError("This profile already has the maximum number of flashcard decks.")
            now = utc_now()
            cards = []
            for parsed in parsed_cards:
                cards.append(
                    {
                        "id": f"card_{uuid.uuid4().hex[:12]}",
                        "question": parsed.term,
                        "answer": parsed.definition,
                        "question_image": None,
                        "answer_image": None,
                        "status": "new",
                        "review_count": 0,
                        "easy_count": 0,
                        "mid_count": 0,
                        "hard_count": 0,
                        "last_rating": None,
                        "last_reviewed_at": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            deck = {
                "id": f"deck_{uuid.uuid4().hex[:12]}",
                "title": title,
                "created_at": now,
                "updated_at": now,
                "study_sessions": 0,
                "source": {"type": "quizlet", "url": source_url, "imported_at": now, "card_count": len(cards)},
                "cards": cards,
            }
            profile.setdefault("flashcard_decks", []).append(deck)
            self._touch(profile)
            self._save()
            return {
                "deck": self._public_flashcard_deck(deck, include_cards=True),
                "imported_count": len(cards),
                "state": self._memory_snapshot(key, profile),
            }

    def flashcard_deck(self, raw_username: Any, deck_id: str) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            return {"deck": self._public_flashcard_deck(deck, include_cards=True)}

    def add_flashcard(self, raw_username: Any, deck_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        question = self._flashcard_text(payload.get("question"), "Question")
        answer = self._flashcard_text(payload.get("answer"), "Answer")
        question_image = self._normalise_flashcard_image(payload.get("question_image"), "Question image")
        answer_image = self._normalise_flashcard_image(payload.get("answer_image"), "Answer image")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            now = utc_now()
            card = {
                "id": f"card_{uuid.uuid4().hex[:12]}",
                "question": question,
                "answer": answer,
                "question_image": question_image,
                "answer_image": answer_image,
                "status": "new",
                "review_count": 0,
                "easy_count": 0,
                "mid_count": 0,
                "hard_count": 0,
                "last_rating": None,
                "last_reviewed_at": None,
                "created_at": now,
                "updated_at": now,
            }
            deck.setdefault("cards", []).append(card)
            deck["updated_at"] = now
            self._touch(profile)
            self._save()
            return {"card": self._public_flashcard(card), "deck": self._public_flashcard_deck(deck, include_cards=True), "state": self._memory_snapshot(key, profile)}

    def edit_flashcard(self, raw_username: Any, deck_id: str, card_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        question = self._flashcard_text(payload.get("question"), "Question")
        answer = self._flashcard_text(payload.get("answer"), "Answer")
        question_image = self._normalise_flashcard_image(payload.get("question_image"), "Question image")
        answer_image = self._normalise_flashcard_image(payload.get("answer_image"), "Answer image")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            card = self._flashcard_by_id(deck, card_id)
            card.update(
                {
                    "question": question,
                    "answer": answer,
                    "question_image": question_image,
                    "answer_image": answer_image,
                    "updated_at": utc_now(),
                }
            )
            deck["updated_at"] = card["updated_at"]
            self._touch(profile)
            self._save()
            return {"card": self._public_flashcard(card), "deck": self._public_flashcard_deck(deck, include_cards=True), "state": self._memory_snapshot(key, profile)}

    def start_flashcard_review(self, raw_username: Any, deck_id: str, filter_value: Any) -> dict[str, Any]:
        selected_filter = str(filter_value or "all").lower()
        allowed_filters = {"all", *FLASHCARD_STATES}
        if selected_filter not in allowed_filters:
            raise APIError("Choose All, New, Easy, Mid, or Hard for the flashcard filter.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            cards = [
                self._public_flashcard(card)
                for card in deck.get("cards", [])
                if selected_filter == "all" or card.get("status", "new") == selected_filter
            ]
            random.SystemRandom().shuffle(cards)
            if cards:
                deck["study_sessions"] = int(deck.get("study_sessions", 0)) + 1
                deck["updated_at"] = utc_now()
                self._touch(profile)
                self._save()
            return {"cards": cards, "deck": self._public_flashcard_deck(deck), "filter": selected_filter, "state": self._memory_snapshot(key, profile)}

    def review_flashcard(self, raw_username: Any, deck_id: str, card_id: str, rating: Any) -> dict[str, Any]:
        rating = str(rating or "").lower()
        if rating not in {"easy", "mid", "hard"}:
            raise APIError("Rate the card as Easy, Mid, or Hard.")
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            card = self._flashcard_by_id(deck, card_id)
            card["status"] = rating
            card["review_count"] = int(card.get("review_count", 0)) + 1
            card[f"{rating}_count"] = int(card.get(f"{rating}_count", 0)) + 1
            card["last_rating"] = rating
            card["last_reviewed_at"] = utc_now()
            card["updated_at"] = card["last_reviewed_at"]
            deck["updated_at"] = card["updated_at"]
            self._touch(profile)
            self._save()
            return {"card": self._public_flashcard(card), "deck_stats": self._flashcard_deck_stats(deck), "state": self._memory_snapshot(key, profile)}

    def flashcard_deck_stats(self, raw_username: Any, deck_id: str) -> dict[str, Any]:
        with self.lock:
            _, profile = self._profile(raw_username, create=True)
            deck = self._flashcard_deck_by_id(profile, deck_id)
            return {"deck": self._public_flashcard_deck(deck), "stats": self._flashcard_deck_stats(deck)}

    def reset_user(self, raw_username: Any) -> dict[str, Any]:
        """Erase only one user's profile; never erase the shared validated bank."""
        with self.lock:
            key, profile = self._profile(raw_username, create=True)
            display_name = profile["display_name"]
            self.memory["users"][key] = self._empty_profile(display_name)
            profile = self.memory["users"][key]
            self._save()
            return self._memory_snapshot(key, profile)


STORE = GameStore(MEMORY_FILE)


class AirportLabelHandler(BaseHTTPRequestHandler):
    server_version = "AirportLabelQuest/2.0"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_error_json(self, message: str, status: int) -> None:
        self._send_json({"error": message}, status)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length", "0")
        try:
            size = int(content_length)
        except ValueError as error:
            raise APIError("Invalid Content-Length header.") from error
        # Full data backups can include multiple flashcard images. Keep a bounded
        # envelope while allowing a practical import/export archive size.
        if size < 0 or size > 50_000_000:
            raise APIError("Request body is too large. Use a smaller backup or split image-heavy decks.")
        try:
            raw = self.rfile.read(size) if size else b"{}"
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise APIError("Request body must be JSON.") from error
        if not isinstance(parsed, dict):
            raise APIError("Request body must be a JSON object.")
        return parsed

    def _request_user(self, payload: dict[str, Any] | None = None) -> str:
        username = self.headers.get("X-Airport-User", "").strip()
        if not username and payload:
            username = str(payload.get("username", "")).strip()
        if not username:
            raise APIError("Choose a username to continue.", HTTPStatus.UNAUTHORIZED)
        return username

    def do_OPTIONS(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/healthz":
                self._send_json({"status": "ok"})
                return
            if path == "/api/users":
                self._send_json(STORE.users())
                return
            if path == "/api/state":
                self._send_json(STORE.state(self._request_user()))
                return
            if path == "/api/trends":
                self._send_json(STORE.trends(self._request_user()))
                return
            if path == "/api/locations/trends":
                self._send_json(STORE.location_trends(self._request_user()))
                return
            if path == "/api/yyc-ground/trends":
                self._send_json(STORE.yyc_ground_trends(self._request_user()))
                return
            if path == "/api/gates/trends":
                self._send_json(STORE.gates_trends(self._request_user()))
                return
            if path == "/api/apron-ops/trends":
                self._send_json(STORE.apron_ops_trends(self._request_user()))
                return
            if path == "/api/question-banks/export":
                self._send_json(STORE.export_question_banks(self._request_user()))
                return
            if path == "/api/locations/question-bank/export":
                self._send_json(STORE.export_locations_question_bank(self._request_user()))
                return
            if path == "/api/data/export":
                self._send_json(STORE.export_full_data(self._request_user()))
                return
            if path == "/api/flashcards/decks":
                self._send_json(STORE.flashcard_decks(self._request_user()))
                return
            parts = path.split("/")
            if len(parts) == 5 and parts[:4] == ["", "api", "flashcards", "decks"]:
                self._send_json(STORE.flashcard_deck(self._request_user(), unquote(parts[4])))
                return
            if len(parts) == 6 and parts[:4] == ["", "api", "flashcards", "decks"] and parts[5] == "stats":
                self._send_json(STORE.flashcard_deck_stats(self._request_user(), unquote(parts[4])))
                return
            self._serve_static(path)
        except APIError as error:
            self._send_error_json(error.message, error.status)
        except BrokenPipeError:
            pass
        except Exception as error:  # pragma: no cover - defensive server boundary
            print(f"Unexpected GET error: {error!r}")
            self._send_error_json("The game server hit an unexpected error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json_body()
            if path == "/api/users/select":
                result = STORE.select_user(payload.get("username"))
            else:
                username = self._request_user(payload)
                parts = path.split("/")
                if path == "/api/data/import":
                    result = STORE.import_full_data(username, payload.get("data"))
                elif path == "/api/flashcards/decks":
                    result = STORE.create_flashcard_deck(username, payload.get("title"))
                elif path == "/api/flashcards/import/quizlet":
                    result = STORE.import_quizlet_deck(username, payload)
                elif len(parts) == 6 and parts[:4] == ["", "api", "flashcards", "decks"] and parts[5] == "cards":
                    result = STORE.add_flashcard(username, unquote(parts[4]), payload)
                elif len(parts) == 7 and parts[:4] == ["", "api", "flashcards", "decks"] and parts[5] == "cards":
                    card_id = unquote(parts[6])
                    if payload.get("action") == "review":
                        result = STORE.review_flashcard(username, unquote(parts[4]), card_id, payload.get("rating"))
                    else:
                        result = STORE.edit_flashcard(username, unquote(parts[4]), card_id, payload)
                elif len(parts) == 6 and parts[:4] == ["", "api", "flashcards", "decks"] and parts[5] == "start-review":
                    result = STORE.start_flashcard_review(username, unquote(parts[4]), payload.get("filter"))
                elif path == "/api/new":
                    result = STORE.start_new_game(username, bool(payload.get("replace_active", False)))
                elif path == "/api/resume":
                    result = STORE.resume(username)
                elif path == "/api/pause":
                    result = STORE.pause(username)
                elif path == "/api/answer":
                    result = STORE.answer(username, payload.get("x"), payload.get("y"))
                elif path == "/api/hint":
                    result = STORE.hint(username)
                elif path == "/api/locations/new":
                    result = STORE.start_locations_game(username, bool(payload.get("replace_active", False)))
                elif path == "/api/locations/resume":
                    result = STORE.resume_locations_game(username)
                elif path == "/api/locations/pause":
                    result = STORE.pause_locations_game(username)
                elif path == "/api/locations/answer":
                    result = STORE.answer_location(username, payload.get("x"), payload.get("y"))
                elif path == "/api/locations/hint":
                    result = STORE.location_hint(username)
                elif path == "/api/gates/new":
                    result = STORE.start_gates_game(username, bool(payload.get("replace_active", False)))
                elif path == "/api/gates/resume":
                    result = STORE.resume_gates_game(username)
                elif path == "/api/gates/pause":
                    result = STORE.pause_gates_game(username)
                elif path == "/api/gates/answer":
                    result = STORE.answer_gates(username, payload.get("x"), payload.get("y"))
                elif path == "/api/gates/hint":
                    result = STORE.gates_hint(username)
                elif path == "/api/apron-ops/new":
                    result = STORE.start_apron_ops_game(username, bool(payload.get("replace_active", False)))
                elif path == "/api/apron-ops/resume":
                    result = STORE.resume_apron_ops_game(username)
                elif path == "/api/apron-ops/pause":
                    result = STORE.pause_apron_ops_game(username)
                elif path == "/api/apron-ops/answer":
                    result = STORE.answer_apron_ops(
                        username,
                        spot=payload.get("spot"),
                        taxiway=payload.get("taxiway"),
                        ground=payload.get("ground"),
                    )
                elif path == "/api/yyc-ground/new":
                    result = STORE.start_yyc_ground_game(username, bool(payload.get("replace_active", False)))
                elif path == "/api/yyc-ground/resume":
                    result = STORE.resume_yyc_ground_game(username)
                elif path == "/api/yyc-ground/pause":
                    result = STORE.pause_yyc_ground_game(username)
                elif path == "/api/yyc-ground/answer-point":
                    result = STORE.answer_yyc_ground_location(username, payload.get("x"), payload.get("y"))
                elif path == "/api/yyc-ground/answer-use":
                    result = STORE.answer_yyc_ground_use(username, payload.get("use"))
                elif path == "/api/yyc-ground/hint":
                    result = STORE.yyc_ground_hint(username)
                elif path == "/api/yyc-ground/validation/start":
                    result = STORE.start_yyc_ground_validation(username, bool(payload.get("replace_active", False)))
                elif path == "/api/yyc-ground/validation/resume":
                    result = STORE.resume_yyc_ground_validation(username)
                elif path == "/api/yyc-ground/validation/pause":
                    result = STORE.pause_yyc_ground_validation(username)
                elif path == "/api/yyc-ground/validation/submit":
                    result = STORE.submit_yyc_ground_validation(username, payload.get("action"), payload.get("paths"))
                elif path == "/api/yyc-ground/validation/edit-details":
                    result = STORE.edit_yyc_ground_validation_question_details(
                        username,
                        payload.get("label"),
                        payload.get("clue"),
                        payload.get("use"),
                    )
                elif path == "/api/yyc-ground/validation/skip-to-add":
                    result = STORE.skip_yyc_ground_validation_to_add_questions(username)
                elif path == "/api/yyc-ground/validation/add-question":
                    result = STORE.add_yyc_ground_validation_question(
                        username,
                        payload.get("label"),
                        payload.get("category"),
                        payload.get("clue"),
                        payload.get("use"),
                        payload.get("paths"),
                    )
                elif path == "/api/yyc-ground/validation/finish":
                    result = STORE.finish_yyc_ground_validation(username)
                elif path == "/api/locations/validation/start":
                    result = STORE.start_locations_validation(username, bool(payload.get("replace_active", False)))
                elif path == "/api/locations/validation/resume":
                    result = STORE.resume_locations_validation(username)
                elif path == "/api/locations/validation/pause":
                    result = STORE.pause_locations_validation(username)
                elif path == "/api/locations/validation/submit":
                    result = STORE.submit_locations_validation(username, payload.get("action"), payload.get("paths"))
                elif path == "/api/locations/validation/edit-details":
                    result = STORE.edit_locations_validation_question_details(
                        username,
                        payload.get("label"),
                        payload.get("clue"),
                    )
                elif path == "/api/locations/validation/skip-to-add":
                    result = STORE.skip_locations_validation_to_add_questions(username)
                elif path == "/api/locations/validation/add-question":
                    result = STORE.add_locations_validation_question(
                        username,
                        payload.get("label"),
                        payload.get("category"),
                        payload.get("clue"),
                        payload.get("paths"),
                    )
                elif path == "/api/locations/validation/finish":
                    result = STORE.finish_locations_validation(username)
                elif path == "/api/locations/question-bank/import":
                    result = STORE.import_question_banks(username, payload.get("bank"))
                elif path == "/api/validation/start":
                    result = STORE.start_validation(username, bool(payload.get("replace_active", False)))
                elif path == "/api/validation/resume":
                    result = STORE.resume_validation(username)
                elif path == "/api/validation/pause":
                    result = STORE.pause_validation(username)
                elif path == "/api/validation/submit":
                    result = STORE.submit_validation(username, payload.get("action"), payload.get("paths"))
                elif path == "/api/validation/edit-details":
                    result = STORE.edit_validation_question_details(
                        username,
                        payload.get("label"),
                        payload.get("clue"),
                    )
                elif path == "/api/validation/skip-to-add":
                    result = STORE.skip_validation_to_add_questions(username)
                elif path == "/api/validation/add-question":
                    result = STORE.add_validation_question(
                        username,
                        payload.get("label"),
                        payload.get("category"),
                        payload.get("clue"),
                        payload.get("paths"),
                    )
                elif path == "/api/validation/finish":
                    result = STORE.finish_validation(username)
                elif path == "/api/question-banks/import":
                    result = STORE.import_question_banks(username, payload.get("bank"))
                elif path == "/api/reset":
                    result = STORE.reset_user(username)
                else:
                    raise APIError("Unknown API route.", HTTPStatus.NOT_FOUND)
            self._send_json(result)
        except APIError as error:
            self._send_error_json(error.message, error.status)
        except BrokenPipeError:
            pass
        except Exception as error:  # pragma: no cover - defensive server boundary
            print(f"Unexpected POST error: {error!r}")
            self._send_error_json("The game server hit an unexpected error.", HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_static(self, requested_path: str) -> None:
        if requested_path in ("", "/"):
            target = STATIC_DIR / "index.html"
        elif requested_path.startswith("/static/"):
            target = STATIC_DIR / unquote(requested_path.removeprefix("/static/"))
        elif requested_path.startswith("/assets/"):
            target = ASSETS_DIR / unquote(requested_path.removeprefix("/assets/"))
        elif requested_path.startswith("/uploads/"):
            target = UPLOADS_DIR / unquote(requested_path.removeprefix("/uploads/"))
        else:
            self._send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return

        try:
            target = target.resolve(strict=True)
        except FileNotFoundError:
            self._send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return
        static_root = STATIC_DIR.resolve()
        assets_root = ASSETS_DIR.resolve()
        uploads_root = UPLOADS_DIR.resolve()
        allowed_roots = (static_root, assets_root, uploads_root)
        if not any(target == r or r in target.parents for r in allowed_roots):
            self._send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._send_error_json("Not found.", HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Airport Label Quest local game server.")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="TCP port to listen on (default: %(default)s)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host interface to bind (default: %(default)s)",
    )
    args = parser.parse_args()
    if not (1 <= args.port <= 65535):
        parser.error("--port must be between 1 and 65535")

    server = ThreadingHTTPServer((args.host, args.port), AirportLabelHandler)
    print("\nAirport Label Quest is ready.")
    print(f"Open http://localhost:{args.port} in a browser.")
    print(f"Saved progress: {MEMORY_FILE}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Airport Label Quest.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
