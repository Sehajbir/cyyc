/* Airport Label Quest client. Game rules and persistence are enforced by app.py. */
(() => {
  "use strict";

  const GAME_MODES = {
    main: {
      key: "main",
      canvas: { width: 803, height: 922 },
      image: "/assets/airport_blank.png",
      referenceImage: "/assets/airport_labelled.png",
      referenceTitle: "Labelled airport chart",
      referenceCopy: "Use the supplied labelled chart to orient yourself. Close it, then place the requested label on the blank chart.",
      eyebrow: "LIVE CHART",
      title: "Locate the route",
      mapCaption: "Click any part of the named route. Use the labelled-chart reference or a temporary hint when needed.",
      instruction: "Click the route on the chart",
      answerPath: "/api/answer",
      hintPath: "/api/hint",
    },
    locations: {
      key: "locations",
      canvas: { width: 566, height: 739 },
      image: "/assets/locations_blank.png",
      referenceImage: "/assets/locations_labelled.png",
      referenceTitle: "Labelled airport locations chart",
      referenceCopy: "Study the supplied labelled locations chart. Then find the matching marker or facility on the blank locations chart.",
      eyebrow: "AIRFIELD ORIENTATION",
      title: "Learn airport locations",
      mapCaption: "Click the coloured marker or facility named in the prompt. Use the labelled locations chart or a temporary hint when needed.",
      instruction: "Click the location on the chart",
      answerPath: "/api/locations/answer",
      hintPath: "/api/locations/hint",
    },
    yyc: {
      key: "yyc",
      canvas: { width: 657, height: 727 },
      image: "/assets/ground_sort_blank_new.png",
      referenceImage: "/assets/yyc_ground_filled.png",
      referenceTitle: "YYC Ground Sort answer key",
      referenceCopy: "Study the filled YYC sector diagram, then locate the named point on the blank diagram and classify who may use it.",
      eyebrow: "YYC GROUND SORT",
      title: "YYC Ground Sort Program",
      mapCaption: "First click the matching blank point label. Points with an aircraft-use classification then ask a Jets / Props follow-up; corner fixes such as ADVOX are location-only.",
      instruction: "Click the named YYC point",
      answerPath: "/api/yyc-ground/answer-point",
      hintPath: "/api/yyc-ground/hint",
    },
    gates: {
      key: "gates",
      canvas: { width: 1377, height: 857 },
      image: "/assets/gates_blank.png",
      referenceImage: "/assets/gates_labelled.png",
      referenceTitle: "Labelled gates chart",
      referenceCopy: "Study the labelled gates chart, then find the named gate among the empty blue bubbles.",
      eyebrow: "GATE IDENTIFICATION",
      title: "Identify the Gates",
      mapCaption: "Click the empty blue bubble for the named gate. Correct clicks briefly show the gate name, then return to empty placeholders.",
      instruction: "Click the gate bubble",
      answerPath: "/api/gates/answer",
      hintPath: "/api/gates/hint",
    },
  };
  const VALIDATION_MODES = {
    main: {
      key: "main",
      canvas: GAME_MODES.main.canvas,
      image: "/assets/airport_blank.png",
      eyebrow: "CONFIGURATION VALIDATION",
      title: "Review the saved route",
      previewLabel: "CURRENT SAVED ROUTE",
      reviewNoun: "route",
      bankNoun: "question bank",
      startPath: "/api/validation/start",
      resumePath: "/api/validation/resume",
      pausePath: "/api/validation/pause",
      submitPath: "/api/validation/submit",
      detailsPath: "/api/validation/edit-details",
      skipPath: "/api/validation/skip-to-add",
      addPath: "/api/validation/add-question",
      finishPath: "/api/validation/finish",
      stateKey: "validation",
      referenceMode: "main",
    },
    locations: {
      key: "locations",
      canvas: GAME_MODES.locations.canvas,
      image: "/assets/locations_blank.png",
      eyebrow: "LOCATIONS VALIDATION",
      title: "Review the saved marker",
      previewLabel: "CURRENT SAVED MARKER",
      reviewNoun: "location marker",
      bankNoun: "locations bank",
      startPath: "/api/locations/validation/start",
      resumePath: "/api/locations/validation/resume",
      pausePath: "/api/locations/validation/pause",
      submitPath: "/api/locations/validation/submit",
      detailsPath: "/api/locations/validation/edit-details",
      skipPath: "/api/locations/validation/skip-to-add",
      addPath: "/api/locations/validation/add-question",
      finishPath: "/api/locations/validation/finish",
      stateKey: "locations_validation",
      referenceMode: "locations",
    },
    yyc: {
      key: "yyc",
      canvas: GAME_MODES.yyc.canvas,
      image: "/assets/ground_sort_blank_new.png",
      eyebrow: "YYC GROUND SORT VALIDATION",
      title: "Review the saved point",
      previewLabel: "CURRENT SAVED GROUND POINT",
      reviewNoun: "ground point",
      bankNoun: "YYC Ground Sort bank",
      startPath: "/api/yyc-ground/validation/start",
      resumePath: "/api/yyc-ground/validation/resume",
      pausePath: "/api/yyc-ground/validation/pause",
      submitPath: "/api/yyc-ground/validation/submit",
      detailsPath: "/api/yyc-ground/validation/edit-details",
      skipPath: "/api/yyc-ground/validation/skip-to-add",
      addPath: "/api/yyc-ground/validation/add-question",
      finishPath: "/api/yyc-ground/validation/finish",
      stateKey: "yyc_ground_validation",
      referenceMode: "yyc",
    },
  };
  const $ = (id) => document.getElementById(id);

  const screens = [
    $("welcomeScreen"),
    $("menuScreen"),
    $("apronOpsScreen"),
    $("flashcardsScreen"),
    $("flashcardDeckScreen"),
    $("flashcardStudyScreen"),
    $("flashcardStatsScreen"),
    $("gameScreen"),
    $("validationScreen"),
    $("validationAddScreen"),
    $("validationCompleteScreen"),
    $("endScreen"),
    $("trendsScreen"),
  ];

  const airportMap = $("airportMap");
  const mapOverlay = $("mapOverlay");
  const placementLayer = $("placementLayer");
  const hintLayer = $("hintLayer");
  const flashLayer = $("flashLayer");
  const validationPreviewRoute = $("validationPreviewRoute");
  const routeEditorMap = $("routeEditorMap");
  const routeEditorOverlay = $("routeEditorOverlay");
  const routeEditorCurrentLayer = $("routeEditorCurrentLayer");
  const routeEditorDraftLayer = $("routeEditorDraftLayer");
  const routeEditorModal = $("routeEditorModal");
  const questionDetailsModal = $("questionDetailsModal");
  const flashcardModal = $("flashcardModal");
  const quizletImportModal = $("quizletImportModal");
  const dataUpdateModal = $("dataUpdateModal");
  const toast = $("toast");

  // The browser remembers the selected display name; the server keeps separate
  // progress/trends per user while the question bank remains shared.
  let currentUser = "";
  let state = null;
  let activePlayMode = "main";
  let activeTrendsMode = "main";
  let activeValidationMode = "main";
  let currentCanvas = { ...GAME_MODES.main.canvas };
  let lastSummary = null;
  let lastValidationSummary = null;
  let answerLocked = false;
  let validationReviewLocked = false;
  let timerInterval = null;
  let timerBaseSeconds = 0;
  let timerStartedAt = 0;
  let timerTarget = null;
  let hintTimer = null;
  let toastTimer = null;

  // Full-screen route editor state. Drafts are sent only when the player saves.
  let editorMode = null; // "edit" or "add"
  let editorQuestion = null;
  let editorDraftPaths = [];
  let editorActiveStroke = null;
  let editorPointerId = null;
  let editorShowCurrent = true;
  let editorLocked = false;

  // Flashcard deck state lives in the current user profile on the server.
  let currentDeckId = null;
  let currentDeck = null;
  let flashcardEditingId = null;
  let flashcardDraftImages = { question: null, answer: null };
  let studyQueue = [];
  let studyIndex = 0;
  let studyRevealed = false;
  let studyFlipped = false;

  async function request(path, method = "GET", payload = undefined) {
    const options = { method, headers: {} };
    if (currentUser) options.headers["X-Airport-User"] = currentUser;
    if (payload !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (error) {
      throw new Error("Unable to reach the local game server. Is app.py still running?");
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error("The game server returned an unreadable response.");
    }
    if (!response.ok) throw new Error(data.error || "The request could not be completed.");
    return data;
  }

  function escapeHTML(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatDuration(rawSeconds) {
    const seconds = Math.max(0, Math.round(Number(rawSeconds) || 0));
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    const hours = Math.floor(minutes / 60);
    if (hours) return `${hours}:${String(minutes % 60).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }

  function formatCompactDuration(rawSeconds) {
    const seconds = Math.max(0, Math.round(Number(rawSeconds) || 0));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    if (minutes < 60) return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(date);
  }

  function showToast(message, type = "normal") {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.className = `toast visible${type === "error" ? " error" : ""}`;
    toastTimer = window.setTimeout(() => {
      toast.className = "toast";
    }, 3500);
  }

  function showScreen(screen) {
    screens.forEach((element) => element.classList.toggle("hidden", element !== screen));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeReference() {
    $("referenceModal").classList.add("hidden");
    const tabs = $("referenceTabs");
    if (tabs) tabs.classList.add("hidden");
  }

  function closeQuestionDetails() {
    questionDetailsModal.classList.add("hidden");
  }

  function configureGameMode(mode) {
    const config = GAME_MODES[mode] || GAME_MODES.main;
    activePlayMode = config.key;
    currentCanvas = { ...config.canvas };
    airportMap.src = config.image;
    airportMap.width = config.canvas.width;
    airportMap.height = config.canvas.height;
    $("mapFrame").style.aspectRatio = `${config.canvas.width} / ${config.canvas.height}`;
    if (config.key === "gates") {
      $("mapFrame").style.maxWidth = "980px";
    } else if (config.key === "main") {
      $("mapFrame").style.maxWidth = "690px";
    } else {
      $("mapFrame").style.maxWidth = "610px";
    }
    document.querySelector(".game-layout")?.classList.toggle("gates-mode", config.key === "gates");
    mapOverlay.setAttribute("viewBox", `0 0 ${config.canvas.width} ${config.canvas.height}`);
    $("gameEyebrow").textContent = config.eyebrow;
    $("gameTitle").textContent = config.title;
    $("mapCaption").textContent = config.mapCaption;
    $("mapInstruction").textContent = config.instruction;
    $("referenceTitle").textContent = config.referenceTitle;
    $("referenceCopy").textContent = config.referenceCopy;
    $("referenceImage").src = config.referenceImage;
    $("referenceImage").alt = config.referenceTitle;
    return config;
  }

  function openReference(mode = activePlayMode) {
    configureGameMode(mode);
    $("referenceModal").classList.remove("hidden");
  }

  function configureValidationMode(mode) {
    const config = VALIDATION_MODES[mode] || VALIDATION_MODES.main;
    activeValidationMode = config.key;
    const previewMap = $("validationPreviewMap");
    const previewOverlay = $("validationPreviewOverlay");
    previewMap.src = config.image;
    previewMap.width = config.canvas.width;
    previewMap.height = config.canvas.height;
    previewOverlay.setAttribute("viewBox", `0 0 ${config.canvas.width} ${config.canvas.height}`);
    $("validationPreviewFrame").style.aspectRatio = `${config.canvas.width} / ${config.canvas.height}`;
    $("validationPreviewFrame").style.maxWidth = config.key === "main" ? "690px" : "610px";
    $("validationEyebrow").textContent = config.eyebrow;
    $("validationTitle").textContent = config.title;
    $("validationPreviewLabel").textContent = config.previewLabel;
    return config;
  }

  function setUserChrome() {
    const signedIn = Boolean(currentUser);
    document.querySelectorAll(".user-only").forEach((element) => element.classList.toggle("hidden", !signedIn));
    if (signedIn) $("playerName").textContent = currentUser;
  }

  function showWelcomeError(message = "") {
    const host = $("welcomeError");
    host.textContent = message;
    host.classList.toggle("hidden", !message);
  }

  function formatLastActive(value) {
    if (!value) return "Saved player";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Saved player";
    return `Last active ${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date)}`;
  }

  function renderKnownUsers(users) {
    const host = $("knownUsers");
    host.replaceChildren();
    if (!users || !users.length) {
      const empty = document.createElement("div");
      empty.className = "known-users-empty";
      empty.textContent = "No saved players yet. Create the first profile above.";
      host.append(empty);
      return;
    }
    users.forEach((user) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "known-user-button";
      const copy = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = user.name;
      const detail = document.createElement("span");
      detail.textContent = `${formatLastActive(user.last_active_at)} · ${user.session_count || 0} completed ${user.session_count === 1 ? "chart" : "charts"}`;
      copy.append(name, detail);
      const arrow = document.createElement("span");
      arrow.className = "known-user-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      button.append(copy, arrow);
      button.addEventListener("click", () => selectUser(user.name));
      host.append(button);
    });
  }

  async function loadWelcome() {
    showWelcomeError("");
    try {
      const result = await request("/api/users");
      renderKnownUsers(result.users || []);
    } catch (error) {
      showWelcomeError(error.message);
    }
  }

  async function showWelcome() {
    closeRouteEditor(true);
    closeFlashcardEditor();
    closeQuizletImport();
    closeDataUpdate();
    closeQuestionDetails();
    closeReference();
    clearHint();
    stopTimer();
    currentUser = "";
    state = null;
    setUserChrome();
    const remembered = window.localStorage.getItem("airportLabelQuest.currentUser") || "";
    $("welcomeUsername").value = remembered;
    showScreen($("welcomeScreen"));
    await loadWelcome();
    $("welcomeUsername").focus();
  }

  async function selectUser(rawName = $("welcomeUsername").value) {
    const username = String(rawName || "").trim();
    if (!username) {
      showWelcomeError("Enter a username to continue.");
      $("welcomeUsername").focus();
      return;
    }
    showWelcomeError("");
    $("welcomeContinueBtn").disabled = true;
    try {
      const selected = await request("/api/users/select", "POST", { username });
      currentUser = selected.user.name;
      window.localStorage.setItem("airportLabelQuest.currentUser", currentUser);
      state = selected;
      setUserChrome();
      renderMenu();
      showScreen($("menuScreen"));
    } catch (error) {
      showWelcomeError(error.message);
    } finally {
      $("welcomeContinueBtn").disabled = false;
    }
  }

  async function switchUser() {
    try {
      await pauseOpenSessions();
    } catch (error) {
      showToast(error.message, "error");
    }
    await showWelcome();
  }

  function setSavedStatus() {
    const active = state && state.active;
    const locations = state && state.locations;
    const yycGround = state && state.yyc_ground;
    const gates = state && state.gates;
    const apronOps = state && state.apron_ops;
    const validation = state && state.validation;
    const locationsValidation = state && state.locations_validation;
    const yycGroundValidation = state && state.yyc_ground_validation;
    const status = $("savedStatus");
    if (yycGroundValidation && yycGroundValidation.is_running) {
      status.innerHTML = '<span class="status-dot"></span> YYC validation saving';
    } else if (locationsValidation && locationsValidation.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Locations validation saving';
    } else if (validation && validation.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Validation saving';
    } else if (apronOps && apronOps.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Apron Ops progress saving';
    } else if (gates && gates.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Gates progress saving';
    } else if (yycGround && yycGround.is_running) {
      status.innerHTML = '<span class="status-dot"></span> YYC Ground Sort saving';
    } else if (locations && locations.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Locations progress saving';
    } else if (active && active.is_running) {
      status.innerHTML = '<span class="status-dot"></span> Progress saving';
    } else if (yycGroundValidation) {
      status.innerHTML = '<span class="status-dot"></span> YYC validation draft saved';
    } else if (locationsValidation) {
      status.innerHTML = '<span class="status-dot"></span> Locations validation draft saved';
    } else if (apronOps) {
      status.innerHTML = '<span class="status-dot"></span> Apron Ops progress saved';
    } else if (gates) {
      status.innerHTML = '<span class="status-dot"></span> Gates progress saved';
    } else if (yycGround) {
      status.innerHTML = '<span class="status-dot"></span> YYC Ground Sort saved';
    } else if (validation) {
      status.innerHTML = '<span class="status-dot"></span> Validation draft saved';
    } else if (locations) {
      status.innerHTML = '<span class="status-dot"></span> Locations progress saved';
    } else if (active) {
      status.innerHTML = '<span class="status-dot"></span> Progress saved';
    } else {
      status.innerHTML = '<span class="status-dot"></span> Saved locally';
    }
  }

  function renderMenu() {
    if (!state) return;
    const active = state.active;
    const validation = state.validation;
    const history = state.history || {};
    const total = state.question_total || 0;
    $("questionCount").textContent = `${total} locations`;

    const start = $("startBtn");
    const note = $("resumeNote");
    if (active) {
      start.innerHTML = 'Resume saved chart <span aria-hidden="true">→</span>';
      note.replaceChildren();
      note.append(document.createTextNode(
        `${active.completed_count} of ${active.question_total} locations placed · ${formatCompactDuration(active.elapsed_seconds)} recorded. `
      ));
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "text-button";
      discard.textContent = "Discard it and start fresh";
      discard.addEventListener("click", replaceActiveGame);
      note.append(discard);
    } else {
      start.innerHTML = 'Start a new chart <span aria-hidden="true">→</span>';
      note.textContent = history.session_count
        ? "A fresh chart is randomized every time."
        : "No setup needed — your chart progress will save automatically.";
    }

    const locations = state.locations;
    const locationsButton = $("locationsBtn");
    const locationsNote = $("locationsNote");
    const locationsTotal = state.locations_question_total || 0;
    if (locations) {
      locationsButton.innerHTML = 'Resume locations lab <span aria-hidden="true">→</span>';
      locationsNote.replaceChildren();
      locationsNote.append(document.createTextNode(
        `${locations.completed_count} of ${locations.question_total} markers learned · ${formatCompactDuration(locations.elapsed_seconds)} recorded. `
      ));
      const discardLocations = document.createElement("button");
      discardLocations.type = "button";
      discardLocations.className = "text-button";
      discardLocations.textContent = "Discard and restart";
      discardLocations.addEventListener("click", replaceLocationsGame);
      locationsNote.append(discardLocations);
    } else {
      locationsButton.innerHTML = 'Start locations lab <span aria-hidden="true">→</span>';
      locationsNote.textContent = history.location_session_count
        ? `${locationsTotal} navigation and facility locations are ready for another run.`
        : `${locationsTotal} locations are ready to learn from the supplied chart.`;
    }

    const locationsValidation = state.locations_validation;
    const locationsValidationButton = $("locationsValidationBtn");
    if (locationsValidation) {
      locationsValidationButton.textContent = locationsValidation.phase === "add_questions"
        ? "Finish locations validation"
        : `Resume validation (${locationsValidation.reviewed_count}/${locationsValidation.question_total})`;
    } else {
      locationsValidationButton.textContent = "Validate locations";
    }

    const yycGround = state.yyc_ground;
    const yycButton = $("yycGroundBtn");
    const yycNote = $("yycGroundNote");
    const yycTotal = state.yyc_ground_question_total || 0;
    if (yycGround) {
      yycButton.innerHTML = 'Resume ground sort <span aria-hidden="true">→</span>';
      yycNote.replaceChildren();
      yycNote.append(document.createTextNode(`${yycGround.completed_count} of ${yycGround.question_total} points completed · ${formatCompactDuration(yycGround.elapsed_seconds)} recorded. `));
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "text-button";
      discard.textContent = "Discard and restart";
      discard.addEventListener("click", replaceYycGroundGame);
      yycNote.append(discard);
    } else {
      yycButton.innerHTML = 'Start ground sort <span aria-hidden="true">→</span>';
      yycNote.textContent = history.yyc_ground_session_count
        ? `${yycTotal} YYC points are ready for another ground-sort run.`
        : `${yycTotal} YYC points are ready to learn with aircraft-use follow-ups.`;
    }
    const yycValidation = state.yyc_ground_validation;
    const yycValidationButton = $("yycGroundValidationBtn");
    yycValidationButton.textContent = yycValidation
      ? (yycValidation.phase === "add_questions" ? "Finish YYC validation" : `Resume validation (${yycValidation.reviewed_count}/${yycValidation.question_total})`)
      : "Validate ground points";

    const gates = state.gates;
    const gatesBtn = $("gatesBtn");
    const gatesNote = $("gatesNote");
    const gatesTotal = state.gates_question_total || 0;
    if (gates) {
      gatesBtn.innerHTML = 'Resume gates lab <span aria-hidden="true">→</span>';
      gatesNote.replaceChildren();
      gatesNote.append(document.createTextNode(`${gates.completed_count} of ${gates.question_total} gates identified · ${formatCompactDuration(gates.elapsed_seconds)} recorded. `));
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "text-button";
      discard.textContent = "Discard and restart";
      discard.addEventListener("click", replaceGatesGame);
      gatesNote.append(discard);
    } else {
      gatesBtn.innerHTML = 'Start gates lab <span aria-hidden="true">→</span>';
      gatesNote.textContent = history.gates_session_count ? `${gatesTotal} gates are ready for another identification run.` : `${gatesTotal} gates are ready to learn from the blank diagram.`;
    }

    const apronOps = state.apron_ops;
    const apronOpsBtn = $("apronOpsBtn");
    const apronOpsNote = $("apronOpsNote");
    const apronTotal = state.apron_ops_question_total || 15;
    if (apronOps) {
      apronOpsBtn.innerHTML = 'Resume Apron Ops <span aria-hidden="true">→</span>';
      apronOpsNote.replaceChildren();
      apronOpsNote.append(document.createTextNode(`${apronOps.completed_count} of ${apronOps.question_total} clearances issued · ${formatCompactDuration(apronOps.elapsed_seconds)} recorded. `));
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "text-button";
      discard.textContent = "Discard and restart";
      discard.addEventListener("click", replaceApronOpsGame);
      apronOpsNote.append(discard);
    } else {
      apronOpsBtn.innerHTML = 'Start Apron Ops <span aria-hidden="true">→</span>';
      apronOpsNote.textContent = history.apron_ops_session_count
        ? `${apronTotal} clearances are ready for another Apron Ops run.`
        : "15 clearances ready. Pushback spots, exit/entry taxiways, and ground frequencies according to CYYC runway rules.";
    }

    const deckCount = history.flashcard_deck_count || 0;
    $("flashcardsBtn").innerHTML = deckCount ? `Open ${deckCount} flashcard ${deckCount === 1 ? "deck" : "decks"} <span aria-hidden="true">→</span>` : 'Open flashcard decks <span aria-hidden="true">→</span>';
    $("flashcardsNote").textContent = deckCount
      ? `${deckCount} personal ${deckCount === 1 ? "deck" : "decks"} · recall ratings and difficult-card stats update as you study.`
      : "Create a deck, add New cards, then rate what you recall as Easy, Mid, or Hard.";

    const validationButton = $("validationBtn");
    const validationNote = $("validationNote");
    if (validation) {
      validationButton.innerHTML = validation.phase === "add_questions"
        ? 'Finish validation setup <span aria-hidden="true">→</span>'
        : 'Resume validation run <span aria-hidden="true">→</span>';
      validationNote.replaceChildren();
      if (validation.phase === "add_questions") {
        validationNote.append(document.createTextNode(
          `Route review ${validation.skipped_count ? `skipped after ${validation.reviewed_count} checks` : "complete"} · ${validation.changed_count} route ${validation.changed_count === 1 ? "change" : "changes"}, ${validation.detail_changed_count || 0} detail ${validation.detail_changed_count === 1 ? "edit" : "edits"}, and ${validation.added_count} new ${validation.added_count === 1 ? "question" : "questions"} staged. `
        ));
      } else {
        validationNote.append(document.createTextNode(
          `${validation.reviewed_count} of ${validation.question_total} reviewed · ${validation.changed_count} route ${validation.changed_count === 1 ? "draft" : "drafts"} · ${validation.detail_changed_count || 0} detail ${validation.detail_changed_count === 1 ? "edit" : "edits"}. `
        ));
      }
      const restart = document.createElement("button");
      restart.type = "button";
      restart.className = "text-button";
      restart.textContent = "Discard draft and restart";
      restart.addEventListener("click", replaceActiveValidation);
      validationNote.append(restart);
    } else {
      validationButton.innerHTML = 'Start validation run <span aria-hidden="true">→</span>';
      const validations = history.validation_count || 0;
      const overrides = history.configured_override_count || 0;
      const custom = history.custom_question_count || 0;
      if (validations) {
        validationNote.textContent = `${validations} completed ${validations === 1 ? "review" : "reviews"} saved · ${overrides} validated route ${overrides === 1 ? "override" : "overrides"}${custom ? ` · ${custom} custom ${custom === 1 ? "question" : "questions"}` : ""}.`;
      } else {
        validationNote.textContent = "Review every saved route, then optionally add new practice questions.";
      }
    }

    const sessions = history.session_count || 0;
    const last = history.last_completed;
    const overrides = history.configured_override_count || 0;
    const custom = history.custom_question_count || 0;
    const bankNote = `${overrides ? ` · ${overrides} validated route ${overrides === 1 ? "override" : "overrides"}` : ""}${custom ? ` · ${custom} custom ${custom === 1 ? "question" : "questions"}` : ""}`;
    if (!sessions) {
      $("memoryHeadline").textContent = "No completed sessions yet";
      $("memoryDetail").textContent = bankNote
        ? `${total} practice locations are ready${bankNote}.`
        : "Your first chart becomes the baseline.";
    } else {
      $("memoryHeadline").textContent = `${sessions} completed ${sessions === 1 ? "session" : "sessions"} saved`;
      const accuracy = last && Number.isFinite(last.accuracy) ? `${last.accuracy}% accuracy` : "history ready";
      $("memoryDetail").textContent = last
        ? `Latest: ${formatCompactDuration(last.duration_seconds)} · ${last.incorrect} misses · ${accuracy}${bankNote}`
        : `Open session trends to review your progress.${bankNote}`;
    }
    setSavedStatus();
  }

  function stopTimer() {
    if (timerInterval) window.clearInterval(timerInterval);
    timerInterval = null;
    timerTarget = null;
  }

  function renderTimer() {
    if (!timerTarget) return;
    const liveSeconds = timerBaseSeconds + (Date.now() - timerStartedAt) / 1000;
    timerTarget.textContent = formatDuration(liveSeconds);
  }

  function startTimer(session, target) {
    stopTimer();
    timerBaseSeconds = Number(session.elapsed_seconds) || 0;
    timerStartedAt = Date.now();
    timerTarget = target;
    renderTimer();
    if (session.is_running) timerInterval = window.setInterval(renderTimer, 250);
  }

  function setAnswerStatus(kind, message) {
    const status = $("answerStatus");
    const icons = { neutral: "◎", correct: "✓", incorrect: "!" };
    status.className = `answer-status ${kind}`;
    status.replaceChildren();
    const icon = document.createElement("span");
    icon.className = "answer-status-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = icons[kind] || "◎";
    const text = document.createElement("span");
    text.textContent = message;
    status.append(icon, text);
  }

  function setValidationStatus(kind, message) {
    const status = $("validationStatus");
    const icons = { neutral: "?", correct: "✓", incorrect: "!" };
    status.className = `answer-status ${kind}`;
    status.replaceChildren();
    const icon = document.createElement("span");
    icon.className = "answer-status-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = icons[kind] || "?";
    const text = document.createElement("span");
    text.textContent = message;
    status.append(icon, text);
  }

  function routeClass(category) {
    const normalized = String(category || "").toLowerCase();
    if (normalized === "runway" || normalized.includes("navigation") || normalized.includes("weather")) return "runway";
    return "taxiway";
  }

  function renderPlacements(placements) {
    placementLayer.innerHTML = (placements || []).map((placement) => {
      const label = escapeHTML(placement.label);
      const x = Number(placement.x).toFixed(1);
      const y = Number(placement.y).toFixed(1);
      const width = Math.max(52, Math.min(148, String(placement.label).length * 7.1 + 19));
      const placeLeft = Number(placement.x) > currentCanvas.width * 0.79;
      const labelX = placeLeft ? -width - 14 : 14;
      const labelY = Number(placement.y) > currentCanvas.height * 0.96 ? -25 : -20;
      const className = routeClass(placement.category);
      return `
        <g class="route-label ${className}" transform="translate(${x} ${y})">
          <circle class="route-label-dot" r="6"></circle>
          <rect class="route-label-box" x="${labelX}" y="${labelY}" width="${width}" height="18"></rect>
          <text x="${labelX + 7}" y="${labelY + 12.3}">${label}</text>
        </g>`;
    }).join("");
  }

  function clearHint() {
    hintLayer.innerHTML = "";
    if (hintTimer) window.clearTimeout(hintTimer);
    hintTimer = null;
  }

  function showHint(hint) {
    clearHint();
    const routeWidth = Math.max(18, Number(hint.tolerance || 15) * 1.85);
    const paths = (hint.paths || []).map((path) => {
      const points = path.map((point) => `${point[0]},${point[1]}`).join(" ");
      const endpoints = [path[0], path[path.length - 1]]
        .map((point) => `<circle class="hint-dot" cx="${point[0]}" cy="${point[1]}" r="6"></circle>`)
        .join("");
      return `<polyline class="hint-route" points="${points}" stroke-width="${routeWidth}"></polyline>
              <polyline class="hint-route" points="${points}" stroke="#fff6d4" stroke-width="2.5"></polyline>${endpoints}`;
    }).join("");
    hintLayer.innerHTML = paths;
    setAnswerStatus("neutral", `Hint displayed for ${hint.label}. It will fade shortly.`);
    hintTimer = window.setTimeout(() => {
      hintLayer.innerHTML = "";
      setAnswerStatus("neutral", "Choose a spot on the chart.");
      hintTimer = null;
    }, 4000);
  }

  function flashAnswer(x, y, correct) {
    flashLayer.innerHTML = `<circle class="flash-ring ${correct ? "correct" : "incorrect"}" cx="${x}" cy="${y}" r="7"></circle>`;
    window.setTimeout(() => {
      flashLayer.innerHTML = "";
    }, 900);
  }

  function setMapLocked(locked) {
    answerLocked = locked;
    mapOverlay.style.pointerEvents = locked ? "none" : "auto";
    const config = GAME_MODES[activePlayMode];
    $("mapInstruction").textContent = locked ? "Checking location…" : config.instruction;
  }

  function activeGameFor(mode = activePlayMode, fromState = state) {
    if (!fromState) return null;
    if (mode === "locations") return fromState.locations;
    if (mode === "yyc") return fromState.yyc_ground;
    if (mode === "gates") return fromState.gates;
    return fromState.active;
  }

  function renderGame(active, mode = "main") {
    if (!active || !active.current) {
      showToast("No saved question could be found.", "error");
      return;
    }
    const config = configureGameMode(mode);
    const isYyc = mode === "yyc";
    const isGates = mode === "gates";
    const awaitingUse = isYyc && active.phase === "use";
    closeReference();
    clearHint();
    showScreen($("gameScreen"));
    $("categoryPill").textContent = active.current.category;
    $("questionLabel").textContent = awaitingUse ? `Who can use ${active.current.label}?` : active.current.label;
    $("questionClue").textContent = awaitingUse
      ? "Choose the correct aircraft-use classification for this YYC ground point."
      : (active.current.clue || "Find the named marker on the chart.");
    $("progressText").textContent = `${active.completed_count} of ${active.question_total} correctly labelled`;
    $("remainingText").textContent = `${active.remaining_count} ${active.remaining_count === 1 ? "item" : "items"} in queue`;
    $("progressFill").style.width = `${(active.completed_count / active.question_total) * 100}%`;
    $("attemptsValue").textContent = active.attempts;
    $("missesValue").textContent = active.incorrect;
    $("accuracyValue").textContent = active.attempts
      ? `${Math.round(((active.attempts - active.incorrect) / active.attempts) * 100)}%`
      : "—";
    const noun = mode === "locations" ? "location" : (isYyc ? "ground point" : (isGates ? "gate" : "route"));
    mapOverlay.setAttribute("aria-label", awaitingUse ? `YYC Ground Sort. Answer who can use ${active.current.label}.` : `Airport diagram. Locate ${active.current.label}; click the ${noun}.`);
    $("mapInstruction").textContent = awaitingUse ? "Answer the follow-up question" : `Click ${active.current.label}`;
    $("groundFollowup").classList.toggle("hidden", !awaitingUse);
    if (awaitingUse) $("groundFollowupPoint").textContent = active.current.label;
    if (isGates) {
      // Gates canvas stays blank; do not show persistent placements
      placementLayer.innerHTML = "";
    } else {
      renderPlacements(active.placements);
    }
    setAnswerStatus("neutral", awaitingUse
      ? "Point identified — choose who can use it."
      : (mode === "locations" ? "Choose the matching marker or facility on the chart." : (isYyc ? "First identify the named YYC ground point." : (isGates ? "Click where the named gate is on the blank diagram." : "Choose a spot on the chart."))));
    if (awaitingUse) {
      answerLocked = false;
      mapOverlay.style.pointerEvents = "none";
    } else {
      setMapLocked(false);
    }
    document.querySelectorAll("[data-ground-use]").forEach((button) => { button.disabled = !awaitingUse; });
    startTimer(active, $("timerValue"));
    setSavedStatus();
    return config;
  }

  // All map input is calculated from the actual rendered PNG, not an overlay or
  // container. This keeps normal-chart and locations-chart clicks aligned.
  function pointFromMapEvent(event, imageElement, canvas = currentCanvas) {
    const rect = imageElement.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((event.clientY - rect.top) / rect.height) * canvas.height;
    return [
      Math.max(0, Math.min(canvas.width, Number(x.toFixed(2)))),
      Math.max(0, Math.min(canvas.height, Number(y.toFixed(2)))),
    ];
  }

  async function handleMapClick(event) {
    const active = activeGameFor();
    if (answerLocked || !active || (activePlayMode === "yyc" && active.phase === "use")) return;
    const [x, y] = pointFromMapEvent(event, airportMap);
    setMapLocked(true);
    clearHint();
    try {
      const config = GAME_MODES[activePlayMode];
      const result = await request(config.answerPath, "POST", { x, y });
      flashAnswer(result.clicked.x, result.clicked.y, result.correct);
      setAnswerStatus(result.correct ? "correct" : "incorrect", result.feedback);
      state = result.state;
      const nextActive = activeGameFor(activePlayMode, state);
      if (result.correct && nextActive && !(activePlayMode === "yyc" && nextActive.phase === "use")) {
        if (activePlayMode === "gates") {
          // For gates, briefly show correct marker then remove leaving blank
          renderPlacements([ { label: result.question.label, category: "Gate", x: result.clicked.x, y: result.clicked.y } ]);
          window.setTimeout(() => { placementLayer.innerHTML = ""; }, 900);
        } else {
          renderPlacements(nextActive.placements);
        }
      }
      setSavedStatus();
      if (result.follow_up) {
        window.setTimeout(() => renderGame(nextActive, activePlayMode), 650);
      } else if (result.finished) {
        lastSummary = result.summary;
        stopTimer();
        window.setTimeout(() => renderCompletion(result.summary, activePlayMode), 930);
      } else {
        window.setTimeout(() => renderGame(nextActive, activePlayMode), result.correct ? (activePlayMode === "gates" ? 1100 : 780) : 1120);
      }
    } catch (error) {
      setMapLocked(false);
      setAnswerStatus("incorrect", error.message);
      showToast(error.message, "error");
    }
  }

  async function answerGroundUse(use) {
    const active = activeGameFor("yyc");
    if (answerLocked || !active || active.phase !== "use") return;
    answerLocked = true;
    document.querySelectorAll("[data-ground-use]").forEach((button) => { button.disabled = true; });
    try {
      const result = await request("/api/yyc-ground/answer-use", "POST", { use });
      setAnswerStatus(result.correct ? "correct" : "incorrect", result.feedback);
      state = result.state;
      const nextActive = activeGameFor("yyc", state);
      if (result.finished) {
        lastSummary = result.summary;
        stopTimer();
        window.setTimeout(() => renderCompletion(result.summary, "yyc"), 930);
      } else {
        window.setTimeout(() => renderGame(nextActive, "yyc"), result.correct ? 780 : 1120);
      }
    } catch (error) {
      answerLocked = false;
      document.querySelectorAll("[data-ground-use]").forEach((button) => { button.disabled = false; });
      setAnswerStatus("incorrect", error.message);
      showToast(error.message, "error");
    }
  }

  async function showRouteHint() {
    const active = activeGameFor();
    if (answerLocked || !active || (activePlayMode === "yyc" && active.phase === "use")) return;
    try {
      const hint = await request(GAME_MODES[activePlayMode].hintPath, "POST", {});
      showHint(hint);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  // ---------------------------------------------------------------------------
  // Validation review and calibrated full-screen route editor
  // ---------------------------------------------------------------------------
  function routeStrokeMarkup(paths, outerClass, centreClass, dotClass, outerWidth, centreWidth) {
    return (paths || []).filter((path) => path && path.length).map((path) => {
      const points = path.map((point) => `${Number(point[0]).toFixed(1)},${Number(point[1]).toFixed(1)}`).join(" ");
      const [startX, startY] = path[0];
      const [endX, endY] = path[path.length - 1];
      const dots = path.length > 1
        ? `<circle class="${dotClass}" cx="${startX}" cy="${startY}" r="4"></circle><circle class="${dotClass}" cx="${endX}" cy="${endY}" r="4"></circle>`
        : `<circle class="${dotClass}" cx="${startX}" cy="${startY}" r="4"></circle>`;
      return `<polyline class="${outerClass}" points="${points}" stroke-width="${outerWidth}"></polyline><polyline class="${centreClass}" points="${points}" stroke-width="${centreWidth}"></polyline>${dots}`;
    }).join("");
  }

  function configuredRouteMarkup(current, outerClass = "editor-current-route", centreClass = "editor-current-centre", dotClass = "editor-current-dot") {
    if (!current || !current.configured_answer) return "";
    const answer = current.configured_answer;
    const width = Math.max(14, Math.min(50, Number(answer.tolerance || 18) * 1.75));
    return routeStrokeMarkup(answer.paths, outerClass, centreClass, dotClass, width, 2.5);
  }

  function renderValidationPreview(current) {
    validationPreviewRoute.innerHTML = configuredRouteMarkup(
      current,
      "validation-current-route",
      "validation-current-centre",
      "validation-current-dot"
    );
  }

  function setValidationReviewLocked(locked) {
    validationReviewLocked = locked;
    $("validationKeepBtn").disabled = locked;
    $("validationEditBtn").disabled = locked;
    $("validationSkipToAddBtn").disabled = locked;
    $("validationDetailsBtn").disabled = locked;
    $("validationReferenceBtn").disabled = locked;
  }

  function validationStateFor(mode = activeValidationMode) {
    return state && state[VALIDATION_MODES[mode].stateKey];
  }

  function renderValidationReview(validation, mode = activeValidationMode) {
    const config = configureValidationMode(mode);
    if (!validation || validation.phase !== "review" || !validation.current) {
      return renderValidationAdd(validation, mode);
    }
    closeQuestionDetails();
    closeReference();
    clearHint();
    stopTimer();
    setValidationReviewLocked(false);
    showScreen($("validationScreen"));

    const current = validation.current;
    const reviewNumber = validation.reviewed_count + 1;
    const plural = config.key === "main" ? "routes" : (config.key === "yyc" ? "points" : "locations");
    $("validationCategoryPill").textContent = current.category;
    $("validationQuestionLabel").textContent = current.label;
    $("validationQuestionClue").textContent = current.clue || "Find the matching marker on the chart.";
    $("validationSourceValue").textContent = current.configured_answer.source_label;
    $("validationYycUseField").classList.toggle("hidden", config.key !== "yyc");
    if (config.key === "yyc") $("validationYycUse").value = current.configured_answer.use || "";
    $("validationProgressText").textContent = `Review ${reviewNumber} of ${validation.question_total}`;
    $("validationRemainingText").textContent = `${validation.remaining_count} ${validation.remaining_count === 1 ? config.reviewNoun : plural} to review`;
    $("validationProgressFill").style.width = `${(validation.reviewed_count / validation.question_total) * 100}%`;
    renderValidationPreview(current);
    setValidationStatus("neutral", `Does this ${config.reviewNoun} need editing?`);
    $("validationKeepBtn").textContent = config.key === "locations" ? "Yes — keep marker" : (config.key === "yyc" ? "Yes — keep point" : "Yes — keep route");
    $("validationEditBtn").innerHTML = config.key === "main" ? 'No — edit full screen <span aria-hidden="true">→</span>' : (config.key === "locations" ? 'No — edit marker <span aria-hidden="true">→</span>' : 'No — edit point <span aria-hidden="true">→</span>');
    $("validationSkipToAddBtn").textContent = config.key === "locations" ? "Skip remaining locations → Add questions" : (config.key === "yyc" ? "Skip remaining points → Add questions" : "Skip remaining routes → Add questions");
    startTimer(validation, $("validationTimerValue"));
    setSavedStatus();
  }

  function renderValidationAdd(validation, mode = activeValidationMode) {
    if (!validation) {
      showToast("No validation session could be found.", "error");
      return;
    }
    const config = configureValidationMode(mode);
    closeReference();
    clearHint();
    const skipped = Number(validation.skipped_count) || 0;
    const locationMode = config.key === "locations";
    const yycMode = config.key === "yyc";
    const reviewWord = yycMode ? "point" : (locationMode ? "location" : "route");
    const heading = yycMode ? "YYC GROUND SORT" : (locationMode ? "LOCATIONS" : "ROUTE");
    const bankTitle = yycMode ? "YYC Ground Sort bank" : (locationMode ? "Locations bank" : "Question bank");
    if (skipped) {
      $("validationAddEyebrow").textContent = `${heading} REVIEW SKIPPED`;
      $("validationAddTitle").innerHTML = `${bankTitle}<br /><em>ready.</em>`;
      $("validationAddIntro").textContent = `${skipped} unreviewed ${skipped === 1 ? reviewWord : `${reviewWord}s`} keep the existing saved answer${skipped === 1 ? "" : "s"}. You can now add new questions or finish validation.`;
    } else {
      $("validationAddEyebrow").textContent = `${heading} REVIEW COMPLETE`;
      $("validationAddTitle").innerHTML = `${bankTitle}<br /><em>reviewed.</em>`;
      $("validationAddIntro").textContent = yycMode
        ? "You can now add another YYC ground point and its Jets / Props classification to the shared Ground Sort bank."
        : (locationMode
          ? "You can now add a navigation aid, facility, weather marker, or other airport location to the shared locations bank."
          : "You can now add new runway or taxiway prompts to the practice bank, or finish validation and apply your staged route changes.");
    }
    $("addQuestionTitle").textContent = yycMode ? "Add another YYC ground point" : (locationMode ? "Add another airport location" : "Add another question");
    $("addQuestionCopy").textContent = yycMode
      ? "Open the full-screen YYC editor, name the point, select Jets, Props, or Jets or Props, and draw its label location."
      : (locationMode
        ? "Open the full-screen locations editor, name the location, choose a category, and draw its marker or area. Added locations are saved when validation is finished."
        : "Open the full-screen route editor, name the question, choose a category, and draw its answer route. Added questions are saved to future practice sessions when validation is finished.");
    $("addQuestionBtn").innerHTML = yycMode ? 'Add a ground point <span aria-hidden="true">→</span>' : (locationMode ? 'Add a location <span aria-hidden="true">→</span>' : 'Add a question <span aria-hidden="true">→</span>');
    $("finishValidationBtn").innerHTML = yycMode ? 'Finish &amp; apply YYC validation <span aria-hidden="true">→</span>' : (locationMode ? 'Finish &amp; apply locations validation <span aria-hidden="true">→</span>' : 'Finish &amp; apply validation <span aria-hidden="true">→</span>');
    showScreen($("validationAddScreen"));
    $("validationAddSummaryGrid").innerHTML = [
      summaryCard(`${yycMode ? "POINTS" : (locationMode ? "LOCATIONS" : "ROUTES")} REVIEWED`, String(validation.reviewed_count), skipped ? `${skipped} left unchanged` : `${validation.question_total} configured prompts checked`),
      summaryCard(yycMode ? "POINTS REDRAWN" : (locationMode ? "MARKERS REDRAWN" : "ROUTES REDRAWN"), String(validation.changed_count), validation.changed_count ? `${yycMode ? "Point" : (locationMode ? "Marker" : "Route")} edits staged · ${validation.detail_changed_count || 0} detail ${validation.detail_changed_count === 1 ? "edit" : "edits"}` : `${validation.detail_changed_count || 0} question detail ${validation.detail_changed_count === 1 ? "edit" : "edits"} staged`),
      summaryCard("QUESTIONS STAGED", String(validation.added_count), validation.added_count ? `New ${yycMode ? "ground points" : (locationMode ? "locations" : "practice prompts")} ready` : "Add optional questions"),
      summaryCard("REVIEW TIME", formatDuration(validation.elapsed_seconds), "Active validation time"),
    ].join("");
    startTimer(validation, $("validationTimerValue"));
    setSavedStatus();
  }

  function renderValidationPhase(validation, mode = activeValidationMode) {
    if (validation && validation.phase === "add_questions") renderValidationAdd(validation, mode);
    else renderValidationReview(validation, mode);
  }

  async function keepValidationRoute() {
    const config = VALIDATION_MODES[activeValidationMode];
    const validation = validationStateFor();
    if (validationReviewLocked || !validation || validation.phase !== "review") return;
    setValidationReviewLocked(true);
    setValidationStatus("neutral", `Keeping saved ${config.reviewNoun}…`);
    try {
      const result = await request(config.submitPath, "POST", { action: "keep" });
      state = result.state;
      const nextValidation = validationStateFor();
      if (result.review_complete) {
        renderValidationAdd(nextValidation, activeValidationMode);
      } else {
        setValidationStatus("correct", result.feedback);
        window.setTimeout(() => renderValidationReview(nextValidation, activeValidationMode), 360);
      }
    } catch (error) {
      setValidationReviewLocked(false);
      setValidationStatus("incorrect", error.message);
      showToast(error.message, "error");
    }
  }

  async function skipToAddQuestions() {
    const config = VALIDATION_MODES[activeValidationMode];
    const validation = validationStateFor();
    if (validationReviewLocked || !validation || validation.phase !== "review") return;
    const remaining = validation.remaining_count;
    const noun = config.key === "locations" ? "location" : "route";
    const confirmSkip = window.confirm(
      `Skip ${remaining} remaining ${remaining === 1 ? noun : `${noun}s`}? Their current answers will be kept unchanged, and you can move directly to adding questions.`
    );
    if (!confirmSkip) return;
    setValidationReviewLocked(true);
    setValidationStatus("neutral", `Skipping remaining ${config.key === "locations" ? "locations" : "routes"}…`);
    try {
      const result = await request(config.skipPath, "POST", {});
      state = result.state;
      showToast(result.feedback);
      renderValidationAdd(validationStateFor(), activeValidationMode);
    } catch (error) {
      setValidationReviewLocked(false);
      setValidationStatus("incorrect", error.message);
      showToast(error.message, "error");
    }
  }

  function editorHasDrawing() {
    return editorDraftPaths.some((path) => path.length >= 2);
  }

  function setRouteEditorStatus(message, type = "neutral") {
    const host = $("routeEditorStatus");
    host.textContent = message;
    host.dataset.type = type;
  }

  function renderRouteEditorLayers() {
    if (editorMode === "edit" && editorShowCurrent) {
      routeEditorCurrentLayer.innerHTML = configuredRouteMarkup(editorQuestion);
    } else {
      routeEditorCurrentLayer.innerHTML = "";
    }
    routeEditorDraftLayer.innerHTML = routeStrokeMarkup(
      editorDraftPaths,
      "editor-draft-route",
      "editor-draft-centre",
      "editor-draft-dot",
      13,
      2.7
    );
  }

  function updateRouteEditorUI() {
    const hasDrawing = editorHasDrawing();
    const addName = $("customQuestionLabel").value.trim();
    const metadataReady = editorMode !== "add" || addName.length > 0;
    $("routeEditorSaveBtn").disabled = editorLocked || !hasDrawing || !metadataReady;
    $("routeEditorClearBtn").disabled = editorLocked || !hasDrawing;
    $("routeEditorCancelBtn").disabled = editorLocked;
    $("routeEditorCloseBtn").disabled = editorLocked;
    $("routeEditorToggleCurrentBtn").disabled = editorLocked || editorMode !== "edit";
    $("routeEditorReferenceBtn").disabled = editorLocked;
    routeEditorOverlay.style.pointerEvents = editorLocked ? "none" : "auto";
    const locationMode = activeValidationMode === "locations";
    $("routeEditorSaveBtn").textContent = editorMode === "add"
      ? (locationMode ? "Save location & continue →" : "Save question & continue →")
      : (locationMode ? "Save marker & continue →" : "Save route & continue →");
  }

  function openRouteEditor(mode) {
    const config = VALIDATION_MODES[activeValidationMode];
    const validation = validationStateFor();
    if (!validation) return;
    editorMode = mode;
    editorQuestion = mode === "edit" ? validation.current : null;
    editorDraftPaths = [];
    editorActiveStroke = null;
    editorPointerId = null;
    editorShowCurrent = true;
    editorLocked = false;

    const isAdd = mode === "add";
    routeEditorMap.src = config.image;
    routeEditorMap.width = config.canvas.width;
    routeEditorMap.height = config.canvas.height;
    routeEditorOverlay.setAttribute("viewBox", `0 0 ${config.canvas.width} ${config.canvas.height}`);
    $("routeEditorMapStage").style.aspectRatio = `${config.canvas.width} / ${config.canvas.height}`;
    $("routeEditorMetadata").classList.toggle("hidden", !isAdd);
    $("routeEditorYycUseField").classList.toggle("hidden", !(isAdd && config.key === "yyc"));
    if (config.key === "yyc") $("customYycUse").value = "Jets";
    $("routeEditorEyebrow").textContent = isAdd
      ? (config.key === "locations" ? "NEW AIRPORT LOCATION" : "NEW PRACTICE QUESTION")
      : (config.key === "locations" ? "EDIT CONFIGURED MARKER" : "EDIT CONFIGURED ROUTE");
    $("routeEditorTitle").textContent = isAdd
      ? (config.key === "locations" ? "Name and draw a new location" : "Name and draw a new route")
      : `Edit ${editorQuestion.label}`;
    $("routeEditorSubtitle").textContent = isAdd
      ? `Add a label, choose its category, then draw the exact ${config.key === "locations" ? "marker or area" : "answer route"} on the calibrated map.`
      : `The PNG and drawing layer share the exact same ${config.canvas.width} × ${config.canvas.height} coordinate space.`;
    $("routeEditorToggleCurrentBtn").textContent = "Hide current route";
    $("routeEditorToggleCurrentBtn").classList.toggle("hidden", isAdd);
    if (isAdd) {
      const categorySelect = $("customQuestionCategory");
      [...categorySelect.options].forEach((option) => {
        option.disabled = config.key === "main" && !["Taxiway", "Runway"].includes(option.value);
      });
      $("customQuestionLabel").value = "";
      categorySelect.value = config.key === "locations" ? "Facility" : (config.key === "yyc" ? "YYC ground point" : "Taxiway");
      $("customQuestionClue").value = "";
      setRouteEditorStatus(`Name the ${config.key === "locations" ? "location" : "question"}, then draw one or more answer strokes.`);
    } else {
      setRouteEditorStatus(`Blue is the saved ${config.reviewNoun}. Draw amber strokes to replace it.`);
    }
    renderRouteEditorLayers();
    updateRouteEditorUI();
    routeEditorModal.classList.remove("hidden");
    window.setTimeout(() => {
      if (isAdd) $("customQuestionLabel").focus();
      else routeEditorOverlay.focus();
    }, 40);
  }

  function closeRouteEditor(force = false) {
    if (editorLocked && !force) return;
    if (!force && editorHasDrawing()) {
      const close = window.confirm("Discard the unsaved route drawing?");
      if (!close) return;
    }
    editorMode = null;
    editorQuestion = null;
    editorDraftPaths = [];
    editorActiveStroke = null;
    editorPointerId = null;
    editorLocked = false;
    routeEditorCurrentLayer.innerHTML = "";
    routeEditorDraftLayer.innerHTML = "";
    routeEditorModal.classList.add("hidden");
  }

  function toggleRouteEditorCurrent() {
    if (editorLocked || editorMode !== "edit") return;
    editorShowCurrent = !editorShowCurrent;
    $("routeEditorToggleCurrentBtn").textContent = editorShowCurrent ? "Hide current route" : "Show current route";
    renderRouteEditorLayers();
  }

  function editorPointDistance(a, b) {
    return Math.hypot(a[0] - b[0], a[1] - b[1]);
  }

  function handleEditorPointerDown(event) {
    if (editorLocked || !editorMode || (event.button !== undefined && event.button !== 0)) return;
    event.preventDefault();
    editorPointerId = event.pointerId;
    editorActiveStroke = [pointFromMapEvent(event, routeEditorMap, VALIDATION_MODES[activeValidationMode].canvas)];
    routeEditorOverlay.setPointerCapture?.(event.pointerId);
    setRouteEditorStatus("Drawing… release to finish this route stroke.");
  }

  function handleEditorPointerMove(event) {
    if (editorPointerId !== event.pointerId || !editorActiveStroke) return;
    event.preventDefault();
    const point = pointFromMapEvent(event, routeEditorMap, VALIDATION_MODES[activeValidationMode].canvas);
    const previous = editorActiveStroke[editorActiveStroke.length - 1];
    if (editorPointDistance(point, previous) >= 3.5) {
      editorActiveStroke.push(point);
      // Show the in-progress stroke without changing saved draft data.
      routeEditorDraftLayer.innerHTML = routeStrokeMarkup(
        [...editorDraftPaths, editorActiveStroke],
        "editor-draft-route",
        "editor-draft-centre",
        "editor-draft-dot",
        13,
        2.7
      );
    }
  }

  function finishEditorStroke(event) {
    if (editorPointerId !== event.pointerId || !editorActiveStroke) return;
    event.preventDefault();
    const stroke = editorActiveStroke;
    const finalPoint = pointFromMapEvent(event, routeEditorMap, VALIDATION_MODES[activeValidationMode].canvas);
    if (editorPointDistance(finalPoint, stroke[stroke.length - 1]) >= 2) stroke.push(finalPoint);
    try { routeEditorOverlay.releasePointerCapture?.(event.pointerId); } catch (error) { /* no-op */ }
    editorPointerId = null;
    editorActiveStroke = null;
    const routeLength = stroke.slice(1).reduce((total, point, index) => total + editorPointDistance(point, stroke[index]), 0);
    if (stroke.length >= 2 && routeLength >= 5) {
      editorDraftPaths.push(stroke.map((point) => [Number(point[0].toFixed(1)), Number(point[1].toFixed(1))]));
      setRouteEditorStatus("Stroke added. Draw another section or save this route.");
    } else {
      setRouteEditorStatus("That stroke was too short. Drag over a visible route section.", "error");
    }
    renderRouteEditorLayers();
    updateRouteEditorUI();
  }

  function cancelEditorStroke(event) {
    if (editorPointerId !== event.pointerId) return;
    editorPointerId = null;
    editorActiveStroke = null;
    renderRouteEditorLayers();
    updateRouteEditorUI();
  }

  function clearRouteEditorDrawing() {
    if (editorLocked || !editorHasDrawing()) return;
    editorDraftPaths = [];
    editorActiveStroke = null;
    renderRouteEditorLayers();
    setRouteEditorStatus("Drawing cleared. Draw the answer route again.");
    updateRouteEditorUI();
  }

  async function saveRouteEditor() {
    if (editorLocked || !editorMode || !editorHasDrawing()) return;
    const savedMode = editorMode;
    const config = VALIDATION_MODES[activeValidationMode];
    editorLocked = true;
    updateRouteEditorUI();
    setRouteEditorStatus(savedMode === "add" ? `Saving new ${config.key === "locations" ? "location" : "practice question"}…` : `Saving corrected ${config.reviewNoun}…`);
    try {
      let result;
      if (savedMode === "edit") {
        result = await request(config.submitPath, "POST", { action: "replace", paths: editorDraftPaths });
      } else {
        const addPayload = {
          label: $("customQuestionLabel").value,
          category: $("customQuestionCategory").value,
          clue: $("customQuestionClue").value,
          paths: editorDraftPaths,
        };
        if (config.key === "yyc") addPayload.use = $("customYycUse").value;
        result = await request(config.addPath, "POST", addPayload);
      }
      state = result.state;
      const reviewComplete = result.review_complete;
      closeRouteEditor(true);
      const validation = validationStateFor();
      if (savedMode === "edit" && reviewComplete) {
        renderValidationAdd(validation, activeValidationMode);
      } else if (savedMode === "edit") {
        renderValidationReview(validation, activeValidationMode);
      } else {
        showToast(result.feedback);
        renderValidationAdd(validation, activeValidationMode);
      }
    } catch (error) {
      editorLocked = false;
      updateRouteEditorUI();
      setRouteEditorStatus(error.message, "error");
      showToast(error.message, "error");
    }
  }

  function openQuestionDetails() {
    const validation = validationStateFor();
    if (validationReviewLocked || !validation || !validation.current) return;
    const current = validation.current;
    $("validationDetailLabel").value = current.label || "";
    $("validationDetailClue").value = current.clue || "";
    const yycDetails = activeValidationMode === "yyc";
    $("validationYycUseField").classList.toggle("hidden", !yycDetails);
    if (yycDetails) $("validationYycUse").value = (current.configured_answer && current.configured_answer.use) || "";
    questionDetailsModal.classList.remove("hidden");
    window.setTimeout(() => $("validationDetailLabel").focus(), 30);
  }

  async function saveQuestionDetails() {
    const validation = validationStateFor();
    if (validationReviewLocked || !validation || !validation.current) return;
    const button = $("saveQuestionDetailsBtn");
    button.disabled = true;
    try {
      const detailPayload = {
        label: $("validationDetailLabel").value,
        clue: $("validationDetailClue").value,
      };
      if (activeValidationMode === "yyc") detailPayload.use = $("validationYycUse").value;
      const result = await request(VALIDATION_MODES[activeValidationMode].detailsPath, "POST", detailPayload);
      state = result.state;
      closeQuestionDetails();
      showToast(result.feedback);
      renderValidationReview(validationStateFor(), activeValidationMode);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  function openEditRouteEditor() {
    const validation = validationStateFor();
    if (validationReviewLocked || !validation || !validation.current) return;
    openRouteEditor("edit");
  }

  function openAddQuestionEditor() {
    const validation = validationStateFor();
    if (!validation || validation.phase !== "add_questions") return;
    openRouteEditor("add");
  }

  async function finishValidation() {
    const validation = validationStateFor();
    if (!validation || validation.phase !== "add_questions") return;
    const config = VALIDATION_MODES[activeValidationMode];
    const button = $("finishValidationBtn");
    button.disabled = true;
    try {
      const result = await request(config.finishPath, "POST", {});
      state = result.state;
      lastValidationSummary = result.summary;
      stopTimer();
      renderValidationCompletion(result.summary, activeValidationMode);
    } catch (error) {
      button.disabled = false;
      showToast(error.message, "error");
    }
  }

  function summaryCard(label, value, detail) {
    return `<article class="summary-card"><span class="summary-label">${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong><p>${escapeHTML(detail)}</p></article>`;
  }

  function renderValidationCompletion(summary, mode = activeValidationMode) {
    if (!summary) return goHome();
    const config = configureValidationMode(mode);
    closeReference();
    clearHint();
    stopTimer();
    lastValidationSummary = summary;
    const locationMode = config.key === "locations";
    const yycMode = config.key === "yyc";
    const additions = summary.added_count || 0;
    const detailEdits = summary.detail_changed_count || 0;
    const skipped = summary.skipped_count || 0;
    const noun = yycMode ? "point" : (locationMode ? "marker" : "route");
    const plural = yycMode ? "points" : (locationMode ? "locations" : "routes");
    const bankName = yycMode ? "YYC Ground Sort bank" : (locationMode ? "shared locations bank" : "practice bank");
    const changeSentence = `${summary.changed_count} ${noun} ${summary.changed_count === 1 ? "change was" : "changes were"} applied${detailEdits ? `, ${detailEdits} question detail ${detailEdits === 1 ? "edit was" : "edits were"} saved` : ""}${additions ? `, and ${additions} new ${additions === 1 ? "question was" : "questions were"} added` : ""} to the ${bankName}.`;
    const skippedSentence = skipped ? ` ${skipped} unreviewed ${skipped === 1 ? noun : plural} keep the existing saved answer${skipped === 1 ? "" : "s"}.` : "";
    $("validationCompleteTitle").innerHTML = yycMode ? "The YYC ground bank<br /><em>is validated.</em>" : (locationMode ? "The locations bank<br /><em>is validated.</em>" : "The answer bank<br /><em>is validated.</em>");
    $("validationCommitTitle").textContent = yycMode ? "Ground Sort now uses your validated points and classifications." : (locationMode ? "Locations mode now uses your validated markers." : "Practice mode now uses your validated routes.");
    $("validationCommitCopy").textContent = yycMode
      ? "Any changed YYC point, aircraft-use answer, or custom ground point was stored only after this validation run finished."
      : (locationMode
        ? "Any changed location answer was stored only after this full validation run finished. Future location hints and correct-answer checks use the new marker geometry."
        : "Any changed answer was stored in local memory only after this full validation run finished. Future hints and correct-answer checks use the new route geometry.");
    $("validationCompleteIntro").textContent = `Completed on ${formatDate(summary.finished_at)}. ${changeSentence}${skippedSentence}`;
    $("validationSummaryGrid").innerHTML = [
      summaryCard(yycMode ? "POINTS REVIEWED" : (locationMode ? "LOCATIONS REVIEWED" : "ROUTES REVIEWED"), String(summary.reviewed_count), skipped ? `${skipped} left unchanged` : `${summary.question_total} prompts checked`),
      summaryCard(yycMode ? "POINTS REDRAWN" : (locationMode ? "MARKERS REDRAWN" : "ROUTES REDRAWN"), String(summary.changed_count), summary.changed_count ? `New ${noun} geometry committed · ${detailEdits} detail ${detailEdits === 1 ? "edit" : "edits"}` : `${detailEdits} question detail ${detailEdits === 1 ? "edit" : "edits"} committed`),
      summaryCard("QUESTIONS ADDED", String(additions), additions ? `Added to future ${yycMode ? "Ground Sort runs" : (locationMode ? "locations labs" : "practice runs")}` : "No new questions added"),
      summaryCard(yycMode ? "GROUND SORT BANK" : (locationMode ? "LOCATIONS BANK" : "PRACTICE BANK"), String(summary.practice_question_count), "Locations now available"),
    ].join("");
    showScreen($("validationCompleteScreen"));
  }

  async function beginValidation(mode = "main") {
    const config = VALIDATION_MODES[mode];
    try {
      state = await request(config.startPath, "POST", {});
      renderValidationPhase(validationStateFor(mode), mode);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceActiveValidation() {
    const config = VALIDATION_MODES[activeValidationMode];
    const noun = config.key === "locations" ? "locations validation draft" : "validation draft";
    if (!window.confirm(`Discard the saved ${noun} and start the full review again? No draft answers or questions will be applied.`)) return;
    try {
      state = await request(config.startPath, "POST", { replace_active: true });
      renderValidationPhase(validationStateFor(), activeValidationMode);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResumeValidation(mode = "main") {
    const config = VALIDATION_MODES[mode];
    activeValidationMode = mode;
    const validation = validationStateFor(mode);
    if (validation) {
      try {
        state = await request(config.resumePath, "POST", {});
        renderValidationPhase(validationStateFor(mode), mode);
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginValidation(mode);
    }
  }

  // ---------------------------------------------------------------------------
  // Practice-game navigation
  // ---------------------------------------------------------------------------
  async function beginNewGame() {
    try {
      state = await request("/api/new", "POST", {});
      renderGame(state.active, "main");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceActiveGame() {
    if (!window.confirm("Discard the saved in-progress chart? Completed-session history will remain.")) return;
    try {
      state = await request("/api/new", "POST", { replace_active: true });
      renderGame(state.active, "main");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResume() {
    if (state && state.active) {
      try {
        state = await request("/api/resume", "POST", {});
        renderGame(state.active, "main");
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginNewGame();
    }
  }

  async function beginLocationsGame() {
    try {
      state = await request("/api/locations/new", "POST", {});
      renderGame(state.locations, "locations");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceLocationsGame() {
    if (!window.confirm("Discard the saved in-progress locations lab? Completed locations-session history will remain.")) return;
    try {
      state = await request("/api/locations/new", "POST", { replace_active: true });
      renderGame(state.locations, "locations");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResumeLocations() {
    if (state && state.locations) {
      try {
        state = await request("/api/locations/resume", "POST", {});
        renderGame(state.locations, "locations");
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginLocationsGame();
    }
  }

  async function beginGatesGame() {
    try {
      state = await request("/api/gates/new", "POST", {});
      renderGame(state.gates, "gates");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceGatesGame() {
    if (!window.confirm("Discard the saved gates identification run? Completed gates trends will remain.")) return;
    try {
      state = await request("/api/gates/new", "POST", { replace_active: true });
      renderGame(state.gates, "gates");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResumeGates() {
    if (state && state.gates) {
      try {
        state = await request("/api/gates/resume", "POST", {});
        renderGame(state.gates, "gates");
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginGatesGame();
    }
  }

  // ---------------------------------------------------------------------------
  // Apron Ops Mode
  // ---------------------------------------------------------------------------
  let selectedSpot = null;
  let selectedExitTaxiway = null;
  let selectedEntryTaxiway = null;
  let selectedGround = null;
  let apronAdvanceTimer = null;

  async function beginApronOpsGame() {
    try {
      state = await request("/api/apron-ops/new", "POST", {});
      renderApronOpsGame(state.apron_ops);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceApronOpsGame() {
    if (!window.confirm("Discard the saved Apron Ops session? Completed apron trends will remain.")) return;
    try {
      state = await request("/api/apron-ops/new", "POST", { replace_active: true });
      renderApronOpsGame(state.apron_ops);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResumeApronOps() {
    if (state && state.apron_ops) {
      try {
        state = await request("/api/apron-ops/resume", "POST", {});
        renderApronOpsGame(state.apron_ops);
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginApronOpsGame();
    }
  }

  function renderApronOpsGame(active) {
    if (!active || !active.current) {
      showToast("No active Apron Ops clearance could be found.", "error");
      return;
    }
    clearTimeout(apronAdvanceTimer);
    closeReference();
    activePlayMode = "apron";
    showScreen($("apronOpsScreen"));

    const current = active.current;
    const isDeparture = current.request_type === "departure";

    $("apronProgressText").textContent = `${active.completed_count} of ${active.question_total} clearances issued`;
    $("apronRemainingText").textContent = `${active.remaining_count} ${active.remaining_count === 1 ? "item" : "items"} in queue`;
    $("apronProgressFill").style.width = `${(active.completed_count / active.question_total) * 100}%`;
    $("apronAttemptsValue").textContent = active.attempts;
    $("apronMissesValue").textContent = active.incorrect;
    $("apronAccuracyValue").textContent = active.attempts
      ? `${Math.round(((active.attempts - active.incorrect) / active.attempts) * 100)}%`
      : "—";

    const typePill = $("apronTypePill");
    typePill.textContent = isDeparture ? "DEPARTURE" : "ARRIVAL";
    typePill.className = `flight-type-pill ${isDeparture ? "departure" : "arrival"}`;
    $("apronCallsign").textContent = current.callsign;
    $("apronAircraft").textContent = current.aircraft;
    $("apronGate").textContent = current.gate_label;
    $("apronConcourse").textContent = current.concourse;
    $("apronRunway").textContent = current.runway;
    $("apronOperation").textContent = isDeparture ? "Pushback (Exit Apron)" : "Apron Entry (Park at Gate)";
    $("apronTransmission").textContent = `"${current.transmission}"`;

    $("apronFeedbackCard").classList.add("hidden");
    $("apronFeedbackCard").className = "apron-feedback-card hidden";

    $("departureControls").classList.toggle("hidden", !isDeparture);
    $("arrivalControls").classList.toggle("hidden", isDeparture);

    selectedSpot = null;
    selectedExitTaxiway = null;
    selectedEntryTaxiway = null;
    selectedGround = null;

    const opts = current.options || {};
    const spotsList = opts.spots || ["4", "5", "6", "7", "10", "11", "14", "15", "16", "17", "23", "24"];
    const taxiwaysList = opts.taxiways || ["BA", "BC", "E", "EA", "G", "HB", "HD", "JR", "JS", "JT", "K"];
    const groundList = opts.ground_freqs || ["West Ground (121.9)", "East Ground (125.35)"];

    const spotContainer = $("spotPills");
    spotContainer.replaceChildren();
    spotsList.forEach((sp) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "selector-pill";
      btn.textContent = `Spot ${sp}`;
      btn.dataset.value = sp;
      btn.addEventListener("click", () => {
        selectedSpot = sp;
        spotContainer.querySelectorAll(".selector-pill").forEach((el) => el.classList.toggle("selected", el.dataset.value === sp));
        updateApronClearancePreview(current);
      });
      spotContainer.appendChild(btn);
    });

    const exitContainer = $("exitTaxiwayPills");
    exitContainer.replaceChildren();
    taxiwaysList.forEach((tw) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "selector-pill";
      btn.textContent = tw;
      btn.dataset.value = tw;
      btn.addEventListener("click", () => {
        selectedExitTaxiway = tw;
        exitContainer.querySelectorAll(".selector-pill").forEach((el) => el.classList.toggle("selected", el.dataset.value === tw));
        updateApronClearancePreview(current);
      });
      exitContainer.appendChild(btn);
    });

    const groundContainer = $("groundFreqPills");
    groundContainer.replaceChildren();
    groundList.forEach((gf) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "selector-pill";
      btn.textContent = gf;
      btn.dataset.value = gf;
      btn.addEventListener("click", () => {
        selectedGround = gf;
        groundContainer.querySelectorAll(".selector-pill").forEach((el) => el.classList.toggle("selected", el.dataset.value === gf));
        updateApronClearancePreview(current);
      });
      groundContainer.appendChild(btn);
    });

    const entryContainer = $("entryTaxiwayPills");
    entryContainer.replaceChildren();
    taxiwaysList.forEach((tw) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "selector-pill";
      btn.textContent = tw;
      btn.dataset.value = tw;
      btn.addEventListener("click", () => {
        selectedEntryTaxiway = tw;
        entryContainer.querySelectorAll(".selector-pill").forEach((el) => el.classList.toggle("selected", el.dataset.value === tw));
        updateApronClearancePreview(current);
      });
      entryContainer.appendChild(btn);
    });

    renderApronGateHighlight(current.coords);
    updateApronClearancePreview(current);
    startTimer(active, $("apronTimerValue"));
    setSavedStatus();
  }

  function renderApronGateHighlight(coords) {
    const layer = $("apronHighlightLayer");
    layer.replaceChildren();
    if (!coords || !Array.isArray(coords) || coords.length < 2) return;
    const [x, y] = coords;

    const beacon = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    beacon.setAttribute("cx", x);
    beacon.setAttribute("cy", y);
    beacon.setAttribute("r", "20");
    beacon.setAttribute("class", "apron-gate-beacon");

    const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    pulse.setAttribute("cx", x);
    pulse.setAttribute("cy", y);
    pulse.setAttribute("r", "32");
    pulse.setAttribute("class", "apron-gate-pulse");

    layer.appendChild(pulse);
    layer.appendChild(beacon);
  }

  function updateApronClearancePreview(current) {
    const isDeparture = current.request_type === "departure";
    const submitBtn = $("apronSubmitBtn");
    const previewEl = $("clearancePreviewText");

    if (isDeparture) {
      const ready = !!(selectedSpot && selectedExitTaxiway && selectedGround);
      submitBtn.disabled = !ready;
      if (ready) {
        previewEl.innerHTML = `<em>"${escapeHTML(current.callsign)}, push back to Spot ${escapeHTML(selectedSpot)}, exit Apron via Taxiway ${escapeHTML(selectedExitTaxiway)}, contact ${escapeHTML(selectedGround)}."</em>`;
      } else {
        const missing = [];
        if (!selectedSpot) missing.push("pushback spot");
        if (!selectedExitTaxiway) missing.push("exit taxiway");
        if (!selectedGround) missing.push("ground frequency");
        previewEl.textContent = `Select ${missing.join(", ")} above to formulate instruction.`;
      }
    } else {
      const ready = !!selectedEntryTaxiway;
      submitBtn.disabled = !ready;
      if (ready) {
        previewEl.innerHTML = `<em>"${escapeHTML(current.callsign)}, enter Apron via Taxiway ${escapeHTML(selectedEntryTaxiway)} to ${escapeHTML(current.gate_label)}."</em>`;
      } else {
        previewEl.textContent = "Select entry taxiway above to formulate instruction.";
      }
    }
  }

  async function submitApronClearance() {
    const active = state && state.apron_ops;
    if (!active || !active.current) return;
    const current = active.current;
    const isDeparture = current.request_type === "departure";

    const payload = isDeparture
      ? { spot: selectedSpot, taxiway: selectedExitTaxiway, ground: selectedGround }
      : { taxiway: selectedEntryTaxiway };

    $("apronSubmitBtn").disabled = true;

    try {
      const result = await request("/api/apron-ops/answer", "POST", payload);
      state = result.state;

      const fbCard = $("apronFeedbackCard");
      fbCard.className = `apron-feedback-card ${result.correct ? "correct" : "incorrect"}`;
      fbCard.classList.remove("hidden");
      $("apronFeedbackStatus").querySelector("strong").textContent = result.correct ? "Clearance Accepted" : "Clearance Rejected";
      $("apronFeedbackIcon").textContent = result.correct ? "✓" : "✗";
      $("apronFeedbackDetail").textContent = result.feedback;

      const breakdownEl = $("apronFeedbackBreakdown");
      if (!result.correct && result.breakdown) {
        const b = result.breakdown;
        breakdownEl.replaceChildren();
        if (isDeparture) {
          const list = document.createElement("ul");
          list.style.margin = "0";
          list.style.paddingLeft = "18px";
          const spotLi = document.createElement("li");
          spotLi.textContent = `Spot: ${b.selected_spot} (${b.spot_correct ? "Correct" : `Incorrect — expected ${b.correct_spots.join(" or ")}`})`;
          spotLi.style.color = b.spot_correct ? "#059669" : "#e11d48";
          const twLi = document.createElement("li");
          twLi.textContent = `Exit Taxiway: ${b.selected_taxiway} (${b.taxiway_correct ? "Correct" : `Incorrect — expected ${b.correct_taxiways.join(" or ")}`})`;
          twLi.style.color = b.taxiway_correct ? "#059669" : "#e11d48";
          const gLi = document.createElement("li");
          gLi.textContent = `Ground Frequency: ${b.selected_ground} (${b.ground_correct ? "Correct" : `Incorrect — expected ${b.correct_ground}`})`;
          gLi.style.color = b.ground_correct ? "#059669" : "#e11d48";
          list.appendChild(spotLi);
          list.appendChild(twLi);
          list.appendChild(gLi);
          breakdownEl.appendChild(list);
        } else {
          breakdownEl.textContent = `Chose Taxiway ${b.selected_taxiway}. Correct taxiway: ${b.correct_taxiways.join(" or ")}.`;
        }
        breakdownEl.classList.remove("hidden");
      } else {
        breakdownEl.classList.add("hidden");
      }

      setSavedStatus();

      const nextActive = state && state.apron_ops;
      if (result.finished) {
        lastSummary = result.summary;
        stopTimer();
        window.setTimeout(() => renderCompletion(result.summary, "apron"), 1200);
      } else {
        $("apronNextBtn").onclick = () => renderApronOpsGame(nextActive);
        if (result.correct) {
          apronAdvanceTimer = window.setTimeout(() => {
            renderApronOpsGame(nextActive);
          }, 1400);
        }
      }
    } catch (error) {
      showToast(error.message, "error");
      $("apronSubmitBtn").disabled = false;
    }
  }

  function openApronStudyGuide(initialTab = "gates") {
    const tabs = $("referenceTabs");
    tabs.classList.remove("hidden");

    function setTab(tab) {
      $("refTabGates").classList.toggle("active", tab === "gates");
      $("refTabRules17").classList.toggle("active", tab === "rules17");
      $("refTabRules35").classList.toggle("active", tab === "rules35");

      if (tab === "gates") {
        $("referenceTitle").textContent = "CYYC Gate Locations (Gates.png)";
        $("referenceCopy").textContent = "Gates: 1-6, 11-24 (Concourse A), 31-40 (Concourse B), 50-59 (Concourse C), 70-76, 78-79 (Concourse D), 80-92, 94-97 (Concourse E).";
        $("referenceImage").src = "/assets/Gates.png";
        $("referenceImage").alt = "CYYC Gates Diagram";
      } else if (tab === "rules17") {
        $("referenceTitle").textContent = "Runway 17L & 17R Rules (Rules_17)";
        $("referenceCopy").textContent = "Pushback spots, exit/entry taxiways, and ground frequencies for Runways 17L and 17R.";
        $("referenceImage").src = "/assets/Rules_17.png";
        $("referenceImage").alt = "Rules for Runway 17L and 17R";
      } else if (tab === "rules35") {
        $("referenceTitle").textContent = "Runway 35L & 35R Rules (Rules_35)";
        $("referenceCopy").textContent = "Pushback spots, exit/entry taxiways, and ground frequencies for Runways 35L and 35R.";
        $("referenceImage").src = "/assets/Rules_35.png";
        $("referenceImage").alt = "Rules for Runway 35L and 35R";
      }
    }

    $("refTabGates").onclick = () => setTab("gates");
    $("refTabRules17").onclick = () => setTab("rules17");
    $("refTabRules35").onclick = () => setTab("rules35");

    setTab(initialTab);
    $("referenceModal").classList.remove("hidden");
  }


  async function beginYycGroundGame() {
    try {
      state = await request("/api/yyc-ground/new", "POST", {});
      renderGame(state.yyc_ground, "yyc");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function replaceYycGroundGame() {
    if (!window.confirm("Discard the saved YYC Ground Sort run? Completed ground-sort trends will remain.")) return;
    try {
      state = await request("/api/yyc-ground/new", "POST", { replace_active: true });
      renderGame(state.yyc_ground, "yyc");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function startOrResumeYycGround() {
    if (state && state.yyc_ground) {
      try {
        state = await request("/api/yyc-ground/resume", "POST", {});
        renderGame(state.yyc_ground, "yyc");
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      await beginYycGroundGame();
    }
  }

  async function pauseOpenSessions() {
    if (!state) return;
    if (state.active && state.active.is_running) state = await request("/api/pause", "POST", {});
    if (state.locations && state.locations.is_running) state = await request("/api/locations/pause", "POST", {});
    if (state.yyc_ground && state.yyc_ground.is_running) state = await request("/api/yyc-ground/pause", "POST", {});
    if (state.gates && state.gates.is_running) state = await request("/api/gates/pause", "POST", {});
    if (state.apron_ops && state.apron_ops.is_running) state = await request("/api/apron-ops/pause", "POST", {});
    if (state.validation && state.validation.is_running) state = await request("/api/validation/pause", "POST", {});
    if (state.locations_validation && state.locations_validation.is_running) state = await request("/api/locations/validation/pause", "POST", {});
    if (state.yyc_ground_validation && state.yyc_ground_validation.is_running) state = await request("/api/yyc-ground/validation/pause", "POST", {});
  }

  async function goHome() {
    if (!currentUser) {
      await showWelcome();
      return;
    }
    closeRouteEditor(true);
    closeFlashcardEditor();
    closeDataUpdate();
    closeQuestionDetails();
    closeReference();
    clearHint();
    stopTimer();
    try {
      await pauseOpenSessions();
      state = await request("/api/state");
    } catch (error) {
      showToast(error.message, "error");
    }
    renderMenu();
    showScreen($("menuScreen"));
  }

  function renderCompletion(summary, mode = "main") {
    if (!summary) return goHome();
    closeReference();
    clearHint();
    stopTimer();
    activePlayMode = mode;
    lastSummary = summary;
    const isLocations = mode === "locations";
    const isYyc = mode === "yyc";
    const isGates = mode === "gates";
    const isApron = mode === "apron";
    const wrongQuestionIds = new Set((summary.events || []).filter((event) => !event.correct).map((event) => event.question_id));
    const firstPass = Math.max(0, summary.question_total - wrongQuestionIds.size);
    $("endTitle").innerHTML = isApron ? "Every apron clearance<br /><em>issued.</em>" : (isYyc ? "Every ground point<br /><em>sorted.</em>" : (isGates ? "Every gate<br /><em>identified.</em>" : (isLocations ? "Every marker<br /><em>accounted for.</em>" : "Every route<br /><em>accounted for.</em>")));
    $("endIntro").textContent = `Completed on ${formatDate(summary.finished_at)}. This ${isApron ? "Apron Ops" : (isYyc ? "YYC Ground Sort" : (isGates ? "gates-lab" : (isLocations ? "locations-lab" : "chart")))} result is now part of your saved trend history.`;
    $("summaryGrid").innerHTML = [
      summaryCard("TOTAL TIME", formatDuration(summary.duration_seconds), isApron ? "Active Apron Ops time" : (isYyc ? "Active Ground Sort time" : (isGates ? "Active gates-lab time" : (isLocations ? "Active locations-lab time" : "Active chart time")))),
      summaryCard(isApron ? "INCORRECT CLEARANCES" : (isYyc ? "INCORRECT RESPONSES" : "INCORRECT CLICKS"), String(summary.incorrect), summary.incorrect === 1 ? "One retry was needed" : "Retries returned to queue"),
      summaryCard("ATTEMPTS", String(summary.attempts), `${summary.question_total} ${isApron ? "clearances" : (isYyc ? "points sorted" : (isGates ? "gates" : (isLocations ? "markers" : "labels")))} solved`),
      summaryCard(isApron ? "FIRST-PASS CLEARANCES" : (isYyc ? "FIRST-PASS POINTS" : (isGates ? "FIRST-PASS GATES" : (isLocations ? "FIRST-PASS MARKERS" : "FIRST-PASS LABELS"))), String(firstPass), `${summary.accuracy}% answer accuracy`),
    ].join("");
    $("sessionChartTitle").textContent = isLocations ? "Incorrect-marker trend" : "Incorrect-answer trend";
    renderSessionTrend($("sessionChart"), summary);
    showScreen($("endScreen"));
  }

  // ---------------------------------------------------------------------------
  // Charts and saved-session trends
  // ---------------------------------------------------------------------------
  function svgEmpty(message, detail = "") {
    return `<div class="empty-state"><div><strong>${escapeHTML(message)}</strong>${detail ? `<p>${escapeHTML(detail)}</p>` : ""}</div></div>`;
  }

  function numericTicks(maxValue, desired = 4) {
    if (maxValue <= 1) return [0, 1];
    const ticks = [];
    for (let index = 0; index <= desired; index += 1) ticks.push((maxValue / desired) * index);
    return ticks;
  }

  function renderSessionTrend(host, summary) {
    const events = summary.events || [];
    if (!events.length) {
      host.innerHTML = svgEmpty("No answer events recorded", "Finish another chart to see the trend line.");
      return;
    }
    const width = 760;
    const height = 245;
    const margin = { left: 43, right: 18, top: 22, bottom: 38 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const misses = [];
    let cumulative = 0;
    events.forEach((event, index) => {
      if (!event.correct) cumulative += 1;
      misses.push({ index, cumulative, incorrect: !event.correct });
    });
    const maximum = Math.max(1, cumulative);
    const y = (value) => margin.top + innerHeight - (value / maximum) * innerHeight;
    const x = (index) => margin.left + ((index + 1) / events.length) * innerWidth;
    const points = misses.map((item) => `${x(item.index).toFixed(1)},${y(item.cumulative).toFixed(1)}`);
    const linePoints = [`${margin.left},${y(0)}`, ...points].join(" ");
    const areaPath = `M ${margin.left} ${margin.top + innerHeight} L ${points.join(" L ")} L ${x(events.length - 1)} ${margin.top + innerHeight} Z`;
    const grid = numericTicks(maximum).map((tick) => {
      const py = y(tick);
      const label = Number.isInteger(tick) ? tick : tick.toFixed(1);
      return `<line class="grid-line" x1="${margin.left}" y1="${py}" x2="${width - margin.right}" y2="${py}"></line><text class="axis-text" x="${margin.left - 8}" y="${py + 3.5}" text-anchor="end">${label}</text>`;
    }).join("");
    const missDots = misses.filter((item) => item.incorrect).map((item) => `<circle class="miss-dot" cx="${x(item.index)}" cy="${y(item.cumulative)}" r="5"><title>Miss at attempt ${item.index + 1}</title></circle>`).join("");
    const finalDots = misses.filter((item) => !item.incorrect).map((item) => `<circle class="data-dot" cx="${x(item.index)}" cy="${y(item.cumulative)}" r="3.4"></circle>`).join("");
    const endLabel = events.length === 1 ? "" : `Attempt ${events.length}`;
    host.innerHTML = `
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Cumulative incorrect answers by response attempt">
        <text class="axis-label" x="${margin.left}" y="12">CUMULATIVE MISSES</text>
        ${grid}
        <path class="area-fill" d="${areaPath}"></path>
        <polyline class="trend-line" points="${linePoints}"></polyline>
        ${finalDots}
        ${missDots}
        <text class="axis-text" x="${margin.left}" y="${height - 12}">Attempt 1</text>
        <text class="axis-text" x="${width - margin.right}" y="${height - 12}" text-anchor="end">${endLabel}</text>
        <circle class="miss-dot" cx="${width - 146}" cy="13" r="4"></circle><text class="legend-label" x="${width - 137}" y="16">incorrect click</text>
        <line class="trend-line" x1="${width - 256}" y1="13" x2="${width - 235}" y2="13"></line><text class="legend-label" x="${width - 228}" y="16">cumulative trend</text>
      </svg>`;
  }

  function renderLifetime(lifetime) {
    const items = [
      ["COMPLETED CHARTS", lifetime.sessions, "All saved sessions"],
      ["ANSWER ACCURACY", `${lifetime.accuracy}%`, `${lifetime.correct} correct clicks`],
      ["TOTAL MISSES", lifetime.incorrect, "Across completed charts"],
      ["AVG. CHART TIME", formatCompactDuration(lifetime.average_duration_seconds), "Per completed chart"],
      ["TOTAL PRACTICE", formatCompactDuration(lifetime.total_duration_seconds), "Active chart time"],
    ];
    $("lifetimeGrid").innerHTML = items.map(([label, value, detail]) => `<article class="lifetime-card"><span>${escapeHTML(label)}</span><strong>${escapeHTML(value)}</strong><p>${escapeHTML(detail)}</p></article>`).join("");
  }

  function niceMaximum(value) {
    if (value <= 1) return 1;
    const magnitude = 10 ** Math.floor(Math.log10(value));
    return Math.ceil(value / magnitude) * magnitude;
  }

  function renderAllSessionsChart(host, sessions) {
    if (!sessions.length) {
      host.innerHTML = svgEmpty("No completed sessions yet", "Finish a chart to begin your all-session trend line.");
      return;
    }
    const width = 760;
    const height = 245;
    const margin = { left: 43, right: 43, top: 30, bottom: 36 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const minuteValues = sessions.map((session) => session.duration_seconds / 60);
    const timeMax = niceMaximum(Math.max(...minuteValues, 1));
    const missMax = Math.max(1, ...sessions.map((session) => session.incorrect));
    const yTime = (value) => margin.top + innerHeight - (value / timeMax) * innerHeight;
    const yMiss = (value) => margin.top + innerHeight - (value / missMax) * innerHeight;
    const step = innerWidth / sessions.length;
    const barWidth = Math.max(2, Math.min(32, step * 0.48));
    const grid = numericTicks(timeMax).map((tick) => {
      const py = yTime(tick);
      return `<line class="grid-line" x1="${margin.left}" y1="${py}" x2="${width - margin.right}" y2="${py}"></line><text class="axis-text" x="${margin.left - 8}" y="${py + 3.5}" text-anchor="end">${tick < 10 ? tick.toFixed(tick % 1 ? 1 : 0) : Math.round(tick)}</text>`;
    }).join("");
    const bars = sessions.map((session, index) => {
      const center = margin.left + step * index + step / 2;
      const barY = yTime(minuteValues[index]);
      const heightValue = margin.top + innerHeight - barY;
      return `<rect class="time-bar" x="${center - barWidth / 2}" y="${barY}" width="${barWidth}" height="${heightValue}" rx="2"><title>Session ${index + 1}: ${formatCompactDuration(session.duration_seconds)}</title></rect>`;
    }).join("");
    const points = sessions.map((session, index) => {
      const px = margin.left + step * index + step / 2;
      return `${px.toFixed(1)},${yMiss(session.incorrect).toFixed(1)}`;
    });
    const dots = sessions.map((session, index) => {
      const px = margin.left + step * index + step / 2;
      return `<circle class="miss-dot" cx="${px}" cy="${yMiss(session.incorrect)}" r="4"><title>Session ${index + 1}: ${session.incorrect} misses</title></circle>`;
    }).join("");
    const labels = sessions.length <= 12
      ? sessions.map((_, index) => `<text class="axis-text" x="${margin.left + step * index + step / 2}" y="${height - 11}" text-anchor="middle">${index + 1}</text>`).join("")
      : `<text class="axis-text" x="${margin.left}" y="${height - 11}">Session 1</text><text class="axis-text" x="${width - margin.right}" y="${height - 11}" text-anchor="end">Session ${sessions.length}</text>`;
    host.innerHTML = `
      <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Time and incorrect answers across completed sessions">
        <text class="axis-label" x="${margin.left}" y="13">TIME (MINUTES)</text>
        <text class="axis-label" x="${width - margin.right}" y="13" text-anchor="end">MISSES · 0–${missMax}</text>
        ${grid}
        ${bars}
        <polyline class="trend-line" points="${points.join(" ")}"></polyline>
        ${dots}
        ${labels}
        <rect class="time-bar" x="${width - 217}" y="8" width="13" height="8" rx="2"></rect><text class="legend-label" x="${width - 199}" y="16">time</text>
        <circle class="miss-dot" cx="${width - 137}" cy="12" r="4"></circle><text class="legend-label" x="${width - 128}" y="16">misses</text>
      </svg>`;
  }

  function renderDifficulty(stats) {
    const attempted = stats.filter((stat) => stat.attempts > 0);
    if (!attempted.length) {
      const isLocations = activeTrendsMode === "locations";
      const isYyc = activeTrendsMode === "yyc";
      const isApron = activeTrendsMode === "apron";
      $("difficultyTable").innerHTML = svgEmpty(
        isApron ? "No Apron Ops attempts yet" : (isLocations ? "No location attempts yet" : (isYyc ? "No Ground Sort attempts yet" : "No route attempts yet")),
        isApron ? "Your missed gates and clearances will be ranked here." : (isLocations ? "Your missed airport markers will be ranked here." : (isYyc ? "Missed YYC points and aircraft-use follow-ups will be ranked here." : "Your missed locations will be ranked here."))
      );
      return;
    }
    const top = attempted.slice(0, 7);
    const maximum = Math.max(1, ...top.map((stat) => stat.incorrect));
    $("difficultyTable").innerHTML = `<div class="difficulty-list">${top.map((stat) => {
      const rate = stat.accuracy === null ? "—" : `${stat.accuracy}% accuracy`;
      const width = (stat.incorrect / maximum) * 100;
      return `<div class="difficulty-row"><div><div class="difficulty-name">${escapeHTML(stat.label)}</div><div class="difficulty-meta">${escapeHTML(stat.category)} · ${stat.attempts} attempts · ${rate}</div><div class="difficulty-bar"><span style="width:${width}%"></span></div></div><div class="difficulty-count">${stat.incorrect} ${stat.incorrect === 1 ? "miss" : "misses"}</div></div>`;
    }).join("")}</div>`;
  }

  function renderHistory(sessions, mode = "main") {
    const host = $("historyTableBody");
    const isApron = mode === "apron";
    const noun = isApron ? "Apron Ops sessions" : (mode === "locations" ? "locations labs" : (mode === "yyc" ? "Ground Sort runs" : (mode === "gates" ? "gates labs" : "charts")));
    const rowName = isApron ? "Session" : (mode === "locations" ? "Lab" : (mode === "yyc" ? "Run" : (mode === "gates" ? "Lab" : "Chart")));
    if (!sessions.length) {
      host.innerHTML = `<tr><td colspan="6" class="empty-table">No completed ${noun} saved yet.</td></tr>`;
      return;
    }
    host.innerHTML = [...sessions].reverse().map((session, reverseIndex) => {
      const number = sessions.length - reverseIndex;
      return `<tr><td>${rowName} ${number}</td><td>${escapeHTML(formatDate(session.finished_at))}</td><td>${escapeHTML(formatDuration(session.duration_seconds))}</td><td>${session.attempts}</td><td>${session.incorrect}</td><td>${session.accuracy}%</td></tr>`;
    }).join("");
  }

  async function showTrends(mode = "main") {
    activeTrendsMode = mode;
    closeRouteEditor(true);
    closeFlashcardEditor();
    closeDataUpdate();
    closeQuestionDetails();
    closeReference();
    clearHint();
    stopTimer();
    try {
      await pauseOpenSessions();
      const trendsPath = mode === "locations" ? "/api/locations/trends" : (mode === "yyc" ? "/api/yyc-ground/trends" : (mode === "gates" ? "/api/gates/trends" : (mode === "apron" ? "/api/apron-ops/trends" : "/api/trends")));
      const trends = await request(trendsPath);
      const owner = (trends.user && trends.user.name) || currentUser;
      $("trendsTitle").textContent = mode === "locations" ? `${owner}'s location trends` : (mode === "yyc" ? `${owner}'s YYC Ground Sort trends` : (mode === "gates" ? `${owner}'s gates trends` : (mode === "apron" ? `${owner}'s Apron Ops trends` : `${owner}'s session trends`)));
      $("allSessionChartTitle").textContent = mode === "locations" ? "Time and misses by locations lab" : (mode === "yyc" ? "Time and misses by Ground Sort run" : (mode === "gates" ? "Time and misses by gates lab" : (mode === "apron" ? "Time and misses by Apron Ops session" : "Time and misses by session")));
      $("difficultyTitle").textContent = mode === "locations" ? "Most missed airport locations" : (mode === "yyc" ? "Most missed YYC ground points" : (mode === "gates" ? "Most missed gates" : (mode === "apron" ? "Most missed gates & clearances" : "Most missed locations")));
      $("historyTitle").textContent = mode === "locations" ? "Completed locations-lab history" : (mode === "yyc" ? "Completed Ground Sort history" : (mode === "gates" ? "Completed gates history" : (mode === "apron" ? "Completed Apron Ops history" : "Completed chart history")));
      renderLifetime(trends.lifetime);
      renderAllSessionsChart($("allSessionsChart"), trends.sessions);
      renderDifficulty(trends.question_stats);
      renderHistory(trends.sessions, mode);
      setSavedStatus();
      showScreen($("trendsScreen"));
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function resetMemory() {
    if (!window.confirm(`Reset ${currentUser}'s saved progress, validation drafts, and session trends? Shared validated routes and custom questions will remain available to every user.`)) return;
    try {
      state = await request("/api/reset", "POST", {});
      lastSummary = null;
      lastValidationSummary = null;
      stopTimer();
      renderMenu();
      showScreen($("menuScreen"));
      showToast(`${currentUser}'s profile has been reset. Shared question-bank changes were kept.`);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function openDataUpdate() {
    $("dataUpdateStatus").textContent = "";
    dataUpdateModal.classList.remove("hidden");
  }

  function closeDataUpdate() {
    dataUpdateModal.classList.add("hidden");
    $("importFullDataInput").value = "";
  }

  async function exportFullData() {
    try {
      const backup = await request("/api/data/export");
      const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `airport-label-quest-full-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      $("dataUpdateStatus").textContent = "Full data backup exported successfully.";
    } catch (error) {
      $("dataUpdateStatus").textContent = error.message;
      showToast(error.message, "error");
    }
  }

  async function importFullData(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const confirmImport = window.confirm(
        "Import this full backup? This replaces every user profile, airport question bank, locations bank, YYC Ground Sort point/classification, validation edit, flashcard deck, card, image, and card tag currently stored in the app."
      );
      if (!confirmImport) return;
      $("dataUpdateStatus").textContent = "Importing complete application data…";
      const result = await request("/api/data/import", "POST", { data: parsed });
      closeDataUpdate();
      if (result.current_user_available && result.state) {
        state = result.state;
        renderMenu();
        showScreen($("menuScreen"));
        showToast(result.legacy_bank_import
          ? "Imported a legacy question-bank backup. Existing user profiles were preserved."
          : `Imported all data for ${result.user_count} ${result.user_count === 1 ? "user" : "users"}.`);
      } else {
        currentUser = "";
        state = null;
        window.localStorage.removeItem("airportLabelQuest.currentUser");
        setUserChrome();
        showToast("All data imported. Choose a user from the restored profiles.");
        await showWelcome();
      }
    } catch (error) {
      $("dataUpdateStatus").textContent = `Import failed: ${error.message}`;
      showToast(`Import failed: ${error.message}`, "error");
    }
  }

  // ---------------------------------------------------------------------------
  // Flashcard decks
  // ---------------------------------------------------------------------------
  function flashcardStatePill(state) {
    const value = ["new", "easy", "mid", "hard"].includes(state) ? state : "new";
    return `<span class="card-state-pill ${value}">${value}</span>`;
  }

  function renderDeckLibrary(decks) {
    const host = $("deckLibrary");
    if (!decks.length) {
      host.innerHTML = `<div class="deck-library-empty"><div><strong>No flashcard decks yet</strong><br />Create a deck above, add cards with questions, answers, and optional images, or import a set from Quizlet.</div></div>`;
      return;
    }
    host.innerHTML = decks.map((deck) => {
      const stats = deck.stats || {};
      return `<article class="deck-tile">
        <div><p class="eyebrow flashcards-eyebrow">${stats.card_count || 0} CARDS${deck.source && deck.source.type === "quizlet" ? ' <span class="deck-source-pill" title="Imported from Quizlet">Quizlet</span>' : ""}</p><h2>${escapeHTML(deck.title)}</h2></div>
        <div class="deck-state-row">${flashcardStatePill("new")} <span class="deck-tile-meta">${stats.new_count || 0}</span> ${flashcardStatePill("easy")} <span class="deck-tile-meta">${stats.easy_count || 0}</span> ${flashcardStatePill("mid")} <span class="deck-tile-meta">${stats.mid_count || 0}</span> ${flashcardStatePill("hard")} <span class="deck-tile-meta">${stats.hard_count || 0}</span></div>
        <div class="deck-tile-footer"><span>${stats.total_reviews || 0} recall ratings</span><button class="button button-flashcards" data-open-deck="${escapeHTML(deck.id)}" type="button">Open deck</button></div>
      </article>`;
    }).join("");
    host.querySelectorAll("[data-open-deck]").forEach((button) => {
      button.addEventListener("click", () => openFlashcardDeck(button.dataset.openDeck));
    });
  }

  async function showFlashcards() {
    closeRouteEditor(true);
    closeQuestionDetails();
    closeReference();
    clearHint();
    stopTimer();
    try {
      await pauseOpenSessions();
      const result = await request("/api/flashcards/decks");
      renderDeckLibrary(result.decks || []);
      $("newDeckTitle").value = "";
      showScreen($("flashcardsScreen"));
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function createFlashcardDeck() {
    const input = $("newDeckTitle");
    const title = input.value.trim();
    if (!title) {
      input.focus();
      showToast("Give the flashcard deck a title first.", "error");
      return;
    }
    const button = $("createDeckBtn");
    button.disabled = true;
    try {
      const result = await request("/api/flashcards/decks", "POST", { title });
      state = result.state;
      input.value = "";
      showToast(`Created ${result.deck.title}.`);
      await openFlashcardDeck(result.deck.id);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  const QUIZLET_URL_PATTERN = /^(?:https?:\/\/)?(?:[a-z0-9-]+\.)*quizlet\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?(?:(?:[a-z0-9-]+\/)?(\d{5,}))(?:\/[^?#]*)?(?:[?#].*)?$/i;

  function quizletPrintUrl(value) {
    const match = QUIZLET_URL_PATTERN.exec(String(value || "").trim());
    return match ? `https://quizlet.com/${match[1]}/print` : "";
  }

  function setQuizletImportStatus(message, isError = false) {
    const node = $("quizletImportStatus");
    node.textContent = message || "";
    node.classList.toggle("error", Boolean(isError));
  }

  function syncQuizletOpenLink() {
    const link = $("quizletOpenLink");
    const url = quizletPrintUrl($("quizletUrlInput").value);
    link.href = url || "https://quizlet.com";
    link.textContent = url ? "Open the print page ↗" : "Open Quizlet ↗";
  }

  function syncQuizletPdfHint() {
    const input = $("quizletPdfInput");
    const file = input.files && input.files[0];
    $("quizletPdfHint").textContent = file
      ? `${file.name} (${(file.size / 1024 / 1024).toFixed(file.size > 1024 * 1024 ? 1 : 2)} MB) ready to import.`
      : "No file chosen. The PDF is read once to build cards and is not stored.";
  }

  function openQuizletImport() {
    $("quizletUrlInput").value = "";
    $("quizletDeckNameInput").value = $("newDeckTitle").value.trim();
    $("quizletPdfInput").value = "";
    syncQuizletPdfHint();
    syncQuizletOpenLink();
    setQuizletImportStatus("");
    $("runQuizletImportBtn").disabled = false;
    quizletImportModal.classList.remove("hidden");
    window.setTimeout(() => $("quizletUrlInput").focus(), 30);
  }

  function closeQuizletImport() {
    if (!quizletImportModal || quizletImportModal.classList.contains("hidden")) return;
    if ($("runQuizletImportBtn").disabled) return; // import in progress
    quizletImportModal.classList.add("hidden");
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("The PDF could not be read from disk."));
      reader.readAsDataURL(file);
    });
  }

  async function runQuizletImport() {
    const urlInput = $("quizletUrlInput");
    const nameInput = $("quizletDeckNameInput");
    const pdfInput = $("quizletPdfInput");
    const rawUrl = urlInput.value.trim();
    const title = nameInput.value.trim();
    const file = pdfInput.files && pdfInput.files[0];
    if (!rawUrl || !quizletPrintUrl(rawUrl)) {
      setQuizletImportStatus("Enter the Quizlet print URL, for example https://quizlet.com/123456789/print.", true);
      urlInput.focus();
      return;
    }
    if (!title) {
      setQuizletImportStatus("Give the imported deck a name.", true);
      nameInput.focus();
      return;
    }
    if (!file) {
      setQuizletImportStatus("Attach the PDF you saved from the Quizlet print page.", true);
      pdfInput.focus();
      return;
    }
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
      setQuizletImportStatus("The attached file must be a PDF.", true);
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setQuizletImportStatus("That PDF is over 15 MB. Print with the Table layout to keep it small.", true);
      return;
    }
    const button = $("runQuizletImportBtn");
    button.disabled = true;
    setQuizletImportStatus("Reading the PDF and building cards…");
    try {
      let pdf = await readFileAsDataUrl(file);
      if (!/^data:application\/pdf;base64,/i.test(pdf)) {
        pdf = `data:application/pdf;base64,${pdf.split(",")[1] || ""}`;
      }
      const result = await request("/api/flashcards/import/quizlet", "POST", { title, url: quizletPrintUrl(rawUrl), pdf });
      state = result.state;
      button.disabled = false;
      closeQuizletImport();
      $("newDeckTitle").value = "";
      showToast(`Imported ${result.imported_count} card${result.imported_count === 1 ? "" : "s"} into ${result.deck.title}. All cards are tagged New.`);
      await openFlashcardDeck(result.deck.id);
    } catch (error) {
      setQuizletImportStatus(error.message, true);
    } finally {
      button.disabled = false;
    }
  }

  function renderDeckSummary(deck) {
    const stats = deck.stats || {};
    $("deckSummaryGrid").innerHTML = [
      ["TOTAL CARDS", stats.card_count || 0],
      ["NEW", stats.new_count || 0],
      ["EASY", stats.easy_count || 0],
      ["MID", stats.mid_count || 0],
      ["HARD", stats.hard_count || 0],
    ].map(([label, value]) => `<article class="deck-summary-card"><span>${label}</span><strong>${value}</strong></article>`).join("");
  }

  function renderDeckCards(cards) {
    const host = $("deckCardList");
    $("deckCardsCount").textContent = `${cards.length} ${cards.length === 1 ? "card" : "cards"}`;
    if (!cards.length) {
      host.innerHTML = `<div class="empty-state"><div><strong>No cards in this deck</strong><p>Add a card, then choose a filter and start reviewing.</p></div></div>`;
      return;
    }
    host.innerHTML = cards.map((card) => `<article class="deck-card-row">
      <div class="deck-card-copy"><span>QUESTION ${card.question_image ? '<i class="deck-card-image-dot"></i>' : ""}</span><p>${escapeHTML(card.question)}</p></div>
      <div class="deck-card-copy"><span>ANSWER ${card.answer_image ? '<i class="deck-card-image-dot"></i>' : ""}</span><p>${escapeHTML(card.answer)}</p></div>
      <div><div>${flashcardStatePill(card.status)}</div><button class="button button-secondary" data-edit-card="${escapeHTML(card.id)}" type="button">Edit</button></div>
    </article>`).join("");
    host.querySelectorAll("[data-edit-card]").forEach((button) => {
      button.addEventListener("click", () => openFlashcardEditor(button.dataset.editCard));
    });
  }

  async function openFlashcardDeck(deckId) {
    if (!deckId) return showFlashcards();
    try {
      const result = await request(`/api/flashcards/decks/${encodeURIComponent(deckId)}`);
      currentDeck = result.deck;
      currentDeckId = currentDeck.id;
      const stats = currentDeck.stats || {};
      $("flashcardDeckTitle").textContent = currentDeck.title;
      $("flashcardDeckMeta").textContent = `${stats.card_count || 0} cards · ${stats.total_reviews || 0} recall ratings · ${stats.study_sessions || 0} review sessions`;
      renderDeckSummary(currentDeck);
      renderDeckCards(currentDeck.cards || []);
      showScreen($("flashcardDeckScreen"));
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function setFlashcardPreview(side) {
    const image = flashcardDraftImages[side];
    const preview = $(side === "question" ? "flashcardQuestionImagePreview" : "flashcardAnswerImagePreview");
    const remove = $(side === "question" ? "removeQuestionImageBtn" : "removeAnswerImageBtn");
    preview.classList.toggle("hidden", !image);
    remove.classList.toggle("hidden", !image);
    if (image) preview.src = image;
    else preview.removeAttribute("src");
  }

  async function imageFileToDataUrl(file) {
    if (!file) return null;
    if (!file.type.startsWith("image/")) throw new Error("Choose an image file.");
    if (file.size > 1_800_000) throw new Error("Choose an image smaller than roughly 1.8 MB.");
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("The image could not be read."));
      reader.onload = () => resolve(reader.result);
      reader.readAsDataURL(file);
    });
  }

  function openFlashcardEditor(cardId = null) {
    if (!currentDeck) return;
    flashcardEditingId = cardId;
    const card = cardId ? (currentDeck.cards || []).find((item) => item.id === cardId) : null;
    $("flashcardModalEyebrow").textContent = card ? "EDIT FLASHCARD" : "NEW FLASHCARD";
    $("flashcardModalTitle").textContent = card ? "Edit card" : "Add card";
    $("flashcardQuestionInput").value = card ? card.question : "";
    $("flashcardAnswerInput").value = card ? card.answer : "";
    $("flashcardQuestionImageInput").value = "";
    $("flashcardAnswerImageInput").value = "";
    flashcardDraftImages = { question: card ? card.question_image : null, answer: card ? card.answer_image : null };
    setFlashcardPreview("question");
    setFlashcardPreview("answer");
    $("flashcardEditorStatus").textContent = "";
    flashcardModal.classList.remove("hidden");
    window.setTimeout(() => $("flashcardQuestionInput").focus(), 30);
  }

  function closeFlashcardEditor() {
    flashcardModal.classList.add("hidden");
    flashcardEditingId = null;
    flashcardDraftImages = { question: null, answer: null };
  }

  async function handleFlashcardImageChange(side, event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    try {
      flashcardDraftImages[side] = await imageFileToDataUrl(file);
      setFlashcardPreview(side);
      $("flashcardEditorStatus").textContent = "";
    } catch (error) {
      event.target.value = "";
      $("flashcardEditorStatus").textContent = error.message;
    }
  }

  async function saveFlashcardEditor() {
    if (!currentDeckId) return;
    const wasEditing = Boolean(flashcardEditingId);
    const button = $("saveFlashcardBtn");
    button.disabled = true;
    try {
      const payload = {
        question: $("flashcardQuestionInput").value,
        answer: $("flashcardAnswerInput").value,
        question_image: flashcardDraftImages.question,
        answer_image: flashcardDraftImages.answer,
      };
      const endpoint = flashcardEditingId
        ? `/api/flashcards/decks/${encodeURIComponent(currentDeckId)}/cards/${encodeURIComponent(flashcardEditingId)}`
        : `/api/flashcards/decks/${encodeURIComponent(currentDeckId)}/cards`;
      const result = await request(endpoint, "POST", payload);
      state = result.state;
      currentDeck = result.deck;
      closeFlashcardEditor();
      $("flashcardDeckTitle").textContent = currentDeck.title;
      renderDeckSummary(currentDeck);
      renderDeckCards(currentDeck.cards || []);
      showToast(wasEditing ? "Card updated." : "New card added with New status.");
    } catch (error) {
      $("flashcardEditorStatus").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function startDeckStudy(flipped = false) {
    if (!currentDeckId) return;
    try {
      const filter = $("deckStudyFilter").value;
      const result = await request(`/api/flashcards/decks/${encodeURIComponent(currentDeckId)}/start-review`, "POST", { filter });
      state = result.state;
      if (!result.cards.length) {
        showToast(`No ${filter === "all" ? "cards" : filter} cards match this filter.`, "error");
        return;
      }
      studyQueue = result.cards;
      studyIndex = 0;
      studyRevealed = false;
      studyFlipped = Boolean(flipped);
      $("flashcardStudyTitle").textContent = result.deck.title;
      $("flippedBadge").classList.toggle("hidden", !studyFlipped);
      $("flashcardStudyEyebrow").classList.toggle("flipped-mode", studyFlipped);
      $("studyCard").classList.toggle("flipped-mode", studyFlipped);
      // Adjust eyebrow text to make flipped mode obvious for testing and a11y
      $("flashcardStudyEyebrow").textContent = studyFlipped ? "FLASHCARD REVIEW · FLIPPED" : "FLASHCARD REVIEW";
      renderStudyCard();
      showScreen($("flashcardStudyScreen"));
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function startFlippedDeckStudy() {
    return startDeckStudy(true);
  }

  function setStudyImage(id, image, alt) {
    const node = $(id);
    node.classList.toggle("hidden", !image);
    if (image) {
      node.src = image;
      node.alt = alt;
    } else {
      node.removeAttribute("src");
    }
  }

  function renderStudyCard() {
    const card = studyQueue[studyIndex];
    const qLabel = $("studyQuestionLabel");
    const aLabel = $("studyAnswerLabel");
    if (!card) {
      $("studyQuestionText").textContent = "Review complete";
      $("studyAnswerPanel").classList.add("hidden");
      setStudyImage("studyQuestionImage", null, "");
      setStudyImage("studyAnswerImage", null, "");
      $("studyTip").textContent = `You rated ${studyQueue.length} ${studyQueue.length === 1 ? "card" : "cards"}. Return to the deck to review another filter.`;
      $("studyRevealActions").classList.remove("hidden");
      $("revealAnswerBtn").textContent = "Back to deck";
      $("editStudyCardBtn").classList.add("hidden");
      $("studyRatingActions").classList.add("hidden");
      $("flashcardStudyProgress").textContent = `${studyQueue.length} / ${studyQueue.length}`;
      if (qLabel) qLabel.textContent = studyFlipped ? "ANSWER" : "QUESTION";
      if (aLabel) aLabel.textContent = studyFlipped ? "QUESTION" : "ANSWER";
      return;
    }
    $("flashcardStudyProgress").textContent = `${studyIndex + 1} / ${studyQueue.length}`;
    const promptText = studyFlipped ? card.answer : card.question;
    const promptImage = studyFlipped ? card.answer_image : card.question_image;
    const promptAlt = studyFlipped ? "Answer visual" : "Question visual";
    const revealText = studyFlipped ? card.question : card.answer;
    const revealImage = studyFlipped ? card.question_image : card.answer_image;
    const revealAlt = studyFlipped ? "Question visual" : "Answer visual";
    if (qLabel) qLabel.textContent = studyFlipped ? "ANSWER" : "QUESTION";
    if (aLabel) aLabel.textContent = studyFlipped ? "QUESTION" : "ANSWER";
    $("studyQuestionText").textContent = promptText;
    $("studyAnswerText").textContent = revealText;
    setStudyImage("studyQuestionImage", promptImage, promptAlt);
    setStudyImage("studyAnswerImage", revealImage, revealAlt);
    $("studyAnswerPanel").classList.toggle("hidden", !studyRevealed);
    $("studyTip").textContent = studyRevealed ? "How well did you recall this card?" : (studyFlipped ? "Think of the question, then reveal the front of the card." : "Think of the answer, then reveal the back of the card.");
    $("studyRevealActions").classList.toggle("hidden", studyRevealed);
    $("studyRatingActions").classList.toggle("hidden", !studyRevealed);
    $("revealAnswerBtn").textContent = studyFlipped ? "Reveal question" : "Reveal answer";
    $("editStudyCardBtn").classList.remove("hidden");
  }

  function revealStudyAnswer() {
    if (!studyQueue[studyIndex]) {
      openFlashcardDeck(currentDeckId);
      return;
    }
    studyRevealed = true;
    renderStudyCard();
  }

  async function rateStudyCard(rating) {
    const card = studyQueue[studyIndex];
    if (!card || !studyRevealed) return;
    try {
      const endpoint = `/api/flashcards/decks/${encodeURIComponent(currentDeckId)}/cards/${encodeURIComponent(card.id)}`;
      const result = await request(endpoint, "POST", { action: "review", rating });
      state = result.state;
      studyQueue[studyIndex] = result.card;
      studyIndex += 1;
      studyRevealed = false;
      renderStudyCard();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function editCurrentStudyCard() {
    const card = studyQueue[studyIndex];
    if (!card) return;
    await openFlashcardDeck(currentDeckId);
    openFlashcardEditor(card.id);
  }

  async function showDeckStats() {
    if (!currentDeckId) return;
    try {
      const result = await request(`/api/flashcards/decks/${encodeURIComponent(currentDeckId)}/stats`);
      const stats = result.stats;
      $("flashcardStatsTitle").textContent = result.deck.title;
      $("flashcardStatsIntro").textContent = `${stats.card_count} cards · ${stats.total_reviews} recall ratings · ${stats.study_sessions} review sessions`;
      $("flashcardStatsGrid").innerHTML = [
        ["TOTAL", stats.card_count], ["NEW", stats.new_count], ["EASY", stats.easy_count], ["MID", stats.mid_count], ["HARD", stats.hard_count],
      ].map(([label, value]) => `<article class="deck-summary-card"><span>${label}</span><strong>${value}</strong></article>`).join("");
      const host = $("commonMistakesList");
      if (!stats.common_mistakes.length) {
        host.innerHTML = `<div class="empty-state"><div><strong>No recurring mistakes yet</strong><p>Cards rated Mid or Hard will appear here.</p></div></div>`;
      } else {
        host.innerHTML = `<div class="common-mistakes-list">${stats.common_mistakes.map((card) => `<div class="common-mistake-row"><div><strong>${escapeHTML(card.question)}</strong><span>${card.hard_count} hard · ${card.mid_count} mid · ${card.hard_rate}% hard rate</span></div><div class="common-mistake-score">${card.forgotten_score} score</div></div>`).join("")}</div>`;
      }
      showScreen($("flashcardStatsScreen"));
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function bindEvents() {
    $("welcomeContinueBtn").addEventListener("click", () => selectUser());
    $("welcomeUsername").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        selectUser();
      }
    });
    $("switchUserBtn").addEventListener("click", switchUser);
    $("dataUpdateBtn").addEventListener("click", openDataUpdate);
    $("closeDataUpdateBtn").addEventListener("click", closeDataUpdate);
    $("exportFullDataBtn").addEventListener("click", exportFullData);
    $("importFullDataInput").addEventListener("change", importFullData);
    dataUpdateModal.addEventListener("click", (event) => { if (event.target.dataset.closeDataUpdate) closeDataUpdate(); });
    $("flashcardsBtn").addEventListener("click", showFlashcards);
    $("flashcardsHomeBtn").addEventListener("click", goHome);
    $("createDeckBtn").addEventListener("click", createFlashcardDeck);
    $("newDeckTitle").addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); createFlashcardDeck(); }
    });
    $("importQuizletBtn").addEventListener("click", openQuizletImport);
    $("closeQuizletImportBtn").addEventListener("click", closeQuizletImport);
    $("cancelQuizletImportBtn").addEventListener("click", closeQuizletImport);
    $("runQuizletImportBtn").addEventListener("click", runQuizletImport);
    $("quizletUrlInput").addEventListener("input", syncQuizletOpenLink);
    $("quizletPdfInput").addEventListener("change", syncQuizletPdfHint);
    [$("quizletUrlInput"), $("quizletDeckNameInput")].forEach((input) => input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); runQuizletImport(); }
    }));
    quizletImportModal.addEventListener("click", (event) => { if (event.target.dataset.closeQuizletImport) closeQuizletImport(); });
    $("deckBackBtn").addEventListener("click", showFlashcards);
    $("deckStatsBtn").addEventListener("click", showDeckStats);
    $("addCardBtn").addEventListener("click", () => openFlashcardEditor());
    $("startDeckStudyBtn").addEventListener("click", () => startDeckStudy(false));
    $("startFlippedDeckStudyBtn").addEventListener("click", startFlippedDeckStudy);
    $("exitStudyBtn").addEventListener("click", () => openFlashcardDeck(currentDeckId));
    $("revealAnswerBtn").addEventListener("click", revealStudyAnswer);
    $("studyCard").addEventListener("click", revealStudyAnswer);
    $("studyCard").addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); revealStudyAnswer(); }
    });
    $("editStudyCardBtn").addEventListener("click", editCurrentStudyCard);
    $("editStudyCardAfterRevealBtn").addEventListener("click", editCurrentStudyCard);
    document.querySelectorAll("[data-rating]").forEach((button) => button.addEventListener("click", () => rateStudyCard(button.dataset.rating)));
    $("statsBackToDeckBtn").addEventListener("click", () => openFlashcardDeck(currentDeckId));
    $("closeFlashcardModalBtn").addEventListener("click", closeFlashcardEditor);
    $("cancelFlashcardModalBtn").addEventListener("click", closeFlashcardEditor);
    $("saveFlashcardBtn").addEventListener("click", saveFlashcardEditor);
    $("flashcardQuestionImageInput").addEventListener("change", (event) => handleFlashcardImageChange("question", event));
    $("flashcardAnswerImageInput").addEventListener("change", (event) => handleFlashcardImageChange("answer", event));
    $("removeQuestionImageBtn").addEventListener("click", () => { flashcardDraftImages.question = null; $("flashcardQuestionImageInput").value = ""; setFlashcardPreview("question"); });
    $("removeAnswerImageBtn").addEventListener("click", () => { flashcardDraftImages.answer = null; $("flashcardAnswerImageInput").value = ""; setFlashcardPreview("answer"); });
    flashcardModal.addEventListener("click", (event) => { if (event.target.dataset.closeFlashcard) closeFlashcardEditor(); });
    $("startBtn").addEventListener("click", startOrResume);
    $("locationsBtn").addEventListener("click", startOrResumeLocations);
    $("locationsValidationBtn").addEventListener("click", () => startOrResumeValidation("locations"));
    $("locationsTrendsBtn").addEventListener("click", () => showTrends("locations"));
    $("gatesBtn").addEventListener("click", startOrResumeGates);
    $("gatesTrendsBtn").addEventListener("click", () => showTrends("gates"));
    $("apronOpsBtn").addEventListener("click", startOrResumeApronOps);
    $("apronOpsTrendsBtn").addEventListener("click", () => showTrends("apron"));
    $("apronPauseBtn").addEventListener("click", goHome);
    $("apronSubmitBtn").addEventListener("click", submitApronClearance);
    $("apronStudyGuideBtn").addEventListener("click", () => openApronStudyGuide("gates"));
    $("apronViewRules17Btn").addEventListener("click", () => openApronStudyGuide("rules17"));
    $("apronViewRules35Btn").addEventListener("click", () => openApronStudyGuide("rules35"));
    $("yycGroundBtn").addEventListener("click", startOrResumeYycGround);
    $("yycGroundValidationBtn").addEventListener("click", () => startOrResumeValidation("yyc"));
    $("yycGroundTrendsBtn").addEventListener("click", () => showTrends("yyc"));
    $("validationBtn").addEventListener("click", () => startOrResumeValidation("main"));
    $("menuTrendsBtn").addEventListener("click", () => showTrends("main"));
    $("topTrendsBtn").addEventListener("click", () => showTrends("main"));
    $("homeBrand").addEventListener("click", goHome);
    $("resetDataBtn").addEventListener("click", resetMemory);
    $("pauseBtn").addEventListener("click", goHome);
    $("validationPauseBtn").addEventListener("click", goHome);
    $("validationAddHomeBtn").addEventListener("click", goHome);
    $("hintBtn").addEventListener("click", showRouteHint);
    $("referenceBtn").addEventListener("click", () => openReference(activePlayMode));
    $("validationReferenceBtn").addEventListener("click", () => openReference(VALIDATION_MODES[activeValidationMode].referenceMode));
    $("validationKeepBtn").addEventListener("click", keepValidationRoute);
    $("validationEditBtn").addEventListener("click", openEditRouteEditor);
    $("validationDetailsBtn").addEventListener("click", openQuestionDetails);
    $("validationSkipToAddBtn").addEventListener("click", skipToAddQuestions);
    $("closeQuestionDetailsBtn").addEventListener("click", closeQuestionDetails);
    $("cancelQuestionDetailsBtn").addEventListener("click", closeQuestionDetails);
    $("saveQuestionDetailsBtn").addEventListener("click", saveQuestionDetails);
    questionDetailsModal.addEventListener("click", (event) => {
      if (event.target.dataset.closeDetails) closeQuestionDetails();
    });
    $("addQuestionBtn").addEventListener("click", openAddQuestionEditor);
    $("finishValidationBtn").addEventListener("click", finishValidation);
    $("closeReferenceBtn").addEventListener("click", closeReference);
    $("referenceModal").addEventListener("click", (event) => {
      if (event.target.dataset.closeModal) closeReference();
    });

    $("routeEditorCloseBtn").addEventListener("click", () => closeRouteEditor());
    $("routeEditorCancelBtn").addEventListener("click", () => closeRouteEditor());
    $("routeEditorClearBtn").addEventListener("click", clearRouteEditorDrawing);
    $("routeEditorToggleCurrentBtn").addEventListener("click", toggleRouteEditorCurrent);
    $("routeEditorReferenceBtn").addEventListener("click", () => openReference(VALIDATION_MODES[activeValidationMode].referenceMode));
    $("routeEditorSaveBtn").addEventListener("click", saveRouteEditor);
    $("customQuestionLabel").addEventListener("input", updateRouteEditorUI);

    $("playAgainBtn").addEventListener("click", () => activePlayMode === "locations" ? beginLocationsGame() : (activePlayMode === "gates" ? beginGatesGame() : (activePlayMode === "yyc" ? beginYycGroundGame() : (activePlayMode === "apron" ? beginApronOpsGame() : beginNewGame()))));
    $("endTrendsBtn").addEventListener("click", () => showTrends(activePlayMode));
    $("endHomeBtn").addEventListener("click", goHome);
    $("validatedPracticeBtn").addEventListener("click", () => activeValidationMode === "locations" ? startOrResumeLocations() : (activeValidationMode === "yyc" ? startOrResumeYycGround() : startOrResume()));
    $("validationCompleteHomeBtn").addEventListener("click", goHome);
    $("trendsHomeBtn").addEventListener("click", goHome);

    mapOverlay.addEventListener("click", handleMapClick);
    document.querySelectorAll("[data-ground-use]").forEach((button) => {
      button.addEventListener("click", () => answerGroundUse(button.dataset.groundUse));
    });
    mapOverlay.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showToast("Use a mouse, touchpad, or touch screen to select a chart location.");
      }
    });

    routeEditorOverlay.addEventListener("pointerdown", handleEditorPointerDown);
    routeEditorOverlay.addEventListener("pointermove", handleEditorPointerMove);
    routeEditorOverlay.addEventListener("pointerup", finishEditorStroke);
    routeEditorOverlay.addEventListener("pointercancel", cancelEditorStroke);
    routeEditorOverlay.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showToast("Drag on the full-screen chart with a mouse, touchpad, or touch screen to draw a route.");
      }
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!dataUpdateModal.classList.contains("hidden")) closeDataUpdate();
        else if (!quizletImportModal.classList.contains("hidden")) closeQuizletImport();
        else if (!flashcardModal.classList.contains("hidden")) closeFlashcardEditor();
        else if (!questionDetailsModal.classList.contains("hidden")) closeQuestionDetails();
        else if (!routeEditorModal.classList.contains("hidden")) closeRouteEditor();
        else closeReference();
      }
    });
    window.addEventListener("pagehide", () => {
      if (!currentUser) return;
      const headers = { type: "application/json" };
      // sendBeacon cannot set the player header, so pause routes also receive the
      // username in their JSON body during page shutdown.
      if (state && state.active) navigator.sendBeacon("/api/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.locations) navigator.sendBeacon("/api/locations/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.gates) navigator.sendBeacon("/api/gates/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.apron_ops) navigator.sendBeacon("/api/apron-ops/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.yyc_ground) navigator.sendBeacon("/api/yyc-ground/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.validation) navigator.sendBeacon("/api/validation/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.locations_validation) navigator.sendBeacon("/api/locations/validation/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
      if (state && state.yyc_ground_validation) navigator.sendBeacon("/api/yyc-ground/validation/pause", new Blob([JSON.stringify({ username: currentUser })], headers));
    });
  }

  async function initialise() {
    bindEvents();
    setUserChrome();
    await showWelcome();
  }

  initialise();
})();
