const SESSION_KEY = "barcode_generator_history";

const fallbackConfig = {
  symbology: "code128",
  default_preset_id: "standard-scan",
  web_max_length: 40,
  web_recommended_length: 20,
  web_warning_message: "Longer barcodes may be harder to use from screenshots",
  presets: [
    {
      id: "standard-scan",
      label: "Standard Scan",
      foreground: "#000000",
      background: "#FFFFFF",
      text_foreground: "#000000",
      web_bar_width_px: 3,
      web_height_px: 140,
      web_margin_px: 28,
      web_font_size_px: 18,
      web_text_margin_px: 12
    },
    {
      id: "compact-label",
      label: "Compact Label",
      foreground: "#000000",
      background: "#FFFFFF",
      text_foreground: "#000000",
      web_bar_width_px: 2.6,
      web_height_px: 124,
      web_margin_px: 24,
      web_font_size_px: 17,
      web_text_margin_px: 10
    },
    {
      id: "large-screen-print",
      label: "Large Screen/Print",
      foreground: "#000000",
      background: "#FFFFFF",
      text_foreground: "#000000",
      web_bar_width_px: 3.8,
      web_height_px: 156,
      web_margin_px: 32,
      web_font_size_px: 19,
      web_text_margin_px: 12
    }
  ]
};

const elements = {
  input: document.querySelector("#barcodeValue"),
  preset: document.querySelector("#presetSelect"),
  button: document.querySelector("#createButton"),
  feedback: document.querySelector("#feedback"),
  display: document.querySelector("#barcodeDisplay"),
  svg: document.querySelector("#barcodeSvg"),
  empty: document.querySelector("#emptyState"),
  barcodeCaption: document.querySelector("#barcodeCaption"),
  presetCaption: document.querySelector("#presetCaption"),
  historyList: document.querySelector("#historyList"),
  sessionCount: document.querySelector("#sessionCount")
};

let config = fallbackConfig;
let presetMap = new Map();
let historyItems = [];

function bootFreshHistory() {
  sessionStorage.removeItem(SESSION_KEY);
  historyItems = [];
}

function saveHistory() {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(historyItems));
}

function loadHistory() {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) {
    historyItems = [];
    return;
  }

  try {
    const parsed = JSON.parse(raw);
    historyItems = Array.isArray(parsed) ? parsed : [];
  } catch {
    historyItems = [];
  }
}

function setFeedback(message, tone = "neutral") {
  elements.feedback.textContent = message;
  elements.feedback.dataset.tone = tone;
}

function normalizeValue(value) {
  return value.trim();
}

function validateInput(value) {
  if (!value) {
    return { ok: false, message: "Enter barcode text.", tone: "error" };
  }

  if (!/^[ -~]+$/.test(value)) {
    return {
      ok: false,
      message: "Use printable ASCII characters only.",
      tone: "error"
    };
  }

  if (value.length > config.web_max_length) {
    return {
      ok: false,
      message: `Use ${config.web_max_length} characters or fewer.`,
      tone: "error"
    };
  }

  if (value.length > config.web_recommended_length) {
    return {
      ok: true,
      message: config.web_warning_message,
      tone: "warning"
    };
  }

  return {
    ok: true,
    message: "Ready to render.",
    tone: "neutral"
  };
}

function renderHistory() {
  if (!historyItems.length) {
    elements.historyList.innerHTML =
      '<p class="history-empty">No barcodes created yet.</p>';
    elements.sessionCount.textContent = "0 this session";
    return;
  }

  elements.historyList.innerHTML = "";
  historyItems.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-button";
    button.innerHTML = `<strong>${item.value}</strong><span>${presetMap.get(item.presetId)?.label ?? "Preset"}</span>`;
    button.addEventListener("click", () => {
      elements.input.value = item.value;
      elements.preset.value = item.presetId;
      createBarcode();
    });

    const wrapper = document.createElement("div");
    wrapper.className = "history-item";
    wrapper.appendChild(button);
    elements.historyList.appendChild(wrapper);
  });

  elements.sessionCount.textContent = `${historyItems.length} this session`;
}

function pushHistory(value, presetId) {
  const item = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    value,
    presetId,
    createdAt: new Date().toISOString()
  };

  historyItems = [
    item,
    ...historyItems.filter(
      (entry) => entry.value !== value || entry.presetId !== presetId
    )
  ].slice(0, 6);
  saveHistory();
  renderHistory();
}

function buildBarcodeOptions(preset) {
  return {
    format: "CODE128",
    width: preset.web_bar_width_px,
    height: preset.web_height_px,
    margin: preset.web_margin_px,
    lineColor: preset.foreground,
    background: preset.background,
    displayValue: false
  };
}

function showBarcodeState(isEmpty) {
  elements.display.classList.toggle("is-empty", isEmpty);
  elements.empty.hidden = !isEmpty;
  elements.svg.hidden = isEmpty;
}

function createBarcode() {
  const value = normalizeValue(elements.input.value);
  const presetId = elements.preset.value || config.default_preset_id;
  const preset = presetMap.get(presetId);
  const validation = validateInput(value);

  setFeedback(validation.message, validation.tone);
  if (!validation.ok || !preset) {
    showBarcodeState(true);
    elements.barcodeCaption.textContent = "Your barcode value will appear here.";
    elements.presetCaption.textContent = preset?.label ?? "Standard Scan";
    return;
  }

  try {
    JsBarcode(elements.svg, value, buildBarcodeOptions(preset));
  } catch {
    setFeedback("The barcode could not be generated.", "error");
    showBarcodeState(true);
    return;
  }

  showBarcodeState(false);
  elements.barcodeCaption.textContent = value;
  elements.presetCaption.textContent = preset.label;
  pushHistory(value, presetId);
}

function populatePresets() {
  elements.preset.innerHTML = "";
  config.presets.forEach((preset) => {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.label;
    elements.preset.appendChild(option);
  });
  elements.preset.value = config.default_preset_id;
}

async function loadConfig() {
  try {
    const response = await fetch("./barcode_presets.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Preset fetch failed");
    }
    config = await response.json();
  } catch {
    config = fallbackConfig;
  }

  presetMap = new Map(config.presets.map((preset) => [preset.id, preset]));
}

async function init() {
  bootFreshHistory();
  await loadConfig();
  loadHistory();
  populatePresets();
  renderHistory();
  showBarcodeState(true);

  elements.button.addEventListener("click", createBarcode);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      createBarcode();
    }
  });
  elements.input.addEventListener("input", () => {
    const validation = validateInput(normalizeValue(elements.input.value));
    setFeedback(validation.message, validation.tone);
  });
  elements.preset.addEventListener("change", () => {
    const preset = presetMap.get(elements.preset.value);
    elements.presetCaption.textContent = preset?.label ?? "Standard Scan";
  });
}

init();
