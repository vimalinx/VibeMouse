const state = {
  config: null,
  status: null,
};

const defaultProfileSelect = document.querySelector("#default-profile");
const translationToastEnabledInput = document.querySelector("#translation-toast-enabled");
const readbackTtsEnabledInput = document.querySelector("#readback-tts-enabled");
const readbackTtsVoiceInput = document.querySelector("#readback-tts-voice");
const translationProviderSelect = document.querySelector("#translation-provider");
const translationDeeplAuthKeyInput = document.querySelector("#translation-deepl-auth-key");
const translationDeeplApiUrlInput = document.querySelector("#translation-deepl-api-url");
const translationLibreTranslateUrlInput = document.querySelector("#translation-libretranslate-url");
const translationLibreTranslateApiKeyInput = document.querySelector("#translation-libretranslate-api-key");
const translationMyMemoryEmailInput = document.querySelector("#translation-mymemory-email");
const translationMyMemoryKeyInput = document.querySelector("#translation-mymemory-key");
const dictionaryBody = document.querySelector("#dictionary-body");
const backendStatus = document.querySelector("#backend-status");
const notice = document.querySelector("#notice");
const saveButton = document.querySelector("#save-config");
const refreshStatusButton = document.querySelector("#refresh-status");
const dictionaryForm = document.querySelector("#dictionary-form");

async function readJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(body.error || response.statusText);
  }
  return response.json();
}

function setNotice(message, type = "info") {
  notice.textContent = message;
  notice.dataset.type = type;
}

function renderProfiles() {
  defaultProfileSelect.value = state.config.profiles.default;
}

function renderTranslationSettings() {
  translationToastEnabledInput.checked = false;
  readbackTtsEnabledInput.checked = Boolean(state.config.output.readback_tts_enabled);
  readbackTtsVoiceInput.value = state.config.output.readback_tts_voice || "";
  translationProviderSelect.value = state.config.translation.provider;
  translationDeeplAuthKeyInput.value = state.config.translation.deepl_auth_key || "";
  translationDeeplApiUrlInput.value = state.config.translation.deepl_api_url || "";
  translationLibreTranslateUrlInput.value = state.config.translation.libretranslate_url || "";
  translationLibreTranslateApiKeyInput.value = state.config.translation.libretranslate_api_key || "";
  translationMyMemoryEmailInput.value = state.config.translation.mymemory_email || "";
  translationMyMemoryKeyInput.value = state.config.translation.mymemory_key || "";
}

function renderDictionary() {
  dictionaryBody.innerHTML = "";
  for (const [index, entry] of state.config.dictionary.entries()) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(entry.term)}</td>
      <td>${escapeHtml(entry.phrases.join(", "))}</td>
      <td>${entry.weight}</td>
      <td>${escapeHtml(entry.scope)}</td>
      <td>${entry.enabled ? "Yes" : "No"}</td>
      <td><button class="button button-danger" data-remove-index="${index}" type="button">Remove</button></td>
    `;
    dictionaryBody.appendChild(row);
  }
}

function renderStatus() {
  backendStatus.innerHTML = "";
  for (const [target, details] of Object.entries(state.status.backends)) {
    const card = document.createElement("article");
    card.className = "status-card";
    card.innerHTML = `
      <p class="status-target">${escapeHtml(target)}</p>
      <h3>${escapeHtml(details.backend_id)}</h3>
      <p class="status-pill ${details.available ? "status-ok" : "status-fail"}">
        ${details.available ? "Available" : "Unavailable"}
      </p>
      <p class="status-reason">${escapeHtml(details.reason || "Ready")}</p>
    `;
    backendStatus.appendChild(card);
  }
}

function syncProfileState() {
  state.config.profiles.default = defaultProfileSelect.value;
}

function syncTranslationState() {
  state.config.output.translation_toast_enabled = false;
  state.config.output.readback_tts_enabled = readbackTtsEnabledInput.checked;
  state.config.output.readback_tts_voice = readbackTtsVoiceInput.value.trim() || "en-US-EmmaMultilingualNeural";
  state.config.translation.provider = translationProviderSelect.value;
  state.config.translation.deepl_auth_key = emptyToNull(translationDeeplAuthKeyInput.value);
  state.config.translation.deepl_api_url = emptyToNull(translationDeeplApiUrlInput.value);
  state.config.translation.libretranslate_url = emptyToNull(translationLibreTranslateUrlInput.value);
  state.config.translation.libretranslate_api_key = emptyToNull(translationLibreTranslateApiKeyInput.value);
  state.config.translation.mymemory_email = emptyToNull(translationMyMemoryEmailInput.value);
  state.config.translation.mymemory_key = emptyToNull(translationMyMemoryKeyInput.value);
}

async function loadConfig() {
  state.config = await readJson("/api/config");
  renderProfiles();
  renderTranslationSettings();
  renderDictionary();
}

async function loadStatus() {
  state.status = await readJson("/api/status");
  renderStatus();
}

async function saveConfig() {
  syncProfileState();
  syncTranslationState();
  state.config = await readJson("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.config),
  });
  renderProfiles();
  renderTranslationSettings();
  renderDictionary();
  const reload = await readJson("/api/reload", { method: "POST" });
  try {
    await loadStatus();
  } catch (error) {
    setNotice(`Settings saved, but status refresh failed: ${error.message}`, "error");
    return;
  }
  if (reload.reloaded) {
    setNotice("Settings saved and daemon reload requested.", "success");
  } else {
    setNotice(`Settings saved. Daemon reload not sent: ${reload.reason}.`, "info");
  }
}

function addDictionaryEntry(event) {
  event.preventDefault();
  const form = new FormData(dictionaryForm);
  const phrases = String(form.get("phrases") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  if (!phrases.length) {
    setNotice("Add at least one phrase.", "error");
    return;
  }

  state.config.dictionary.push({
    term: String(form.get("term") || "").trim(),
    phrases,
    weight: Number(form.get("weight") || 8),
    scope: String(form.get("scope") || "both"),
    enabled: Boolean(form.get("enabled")),
  });
  dictionaryForm.reset();
  document.querySelector("#entry-weight").value = "8";
  document.querySelector("#entry-enabled").checked = true;
  renderDictionary();
  setNotice("Entry added locally. Save Settings to persist.", "info");
}

function removeDictionaryEntry(event) {
  const button = event.target.closest("[data-remove-index]");
  if (!button) {
    return;
  }
  const index = Number(button.dataset.removeIndex);
  state.config.dictionary.splice(index, 1);
  renderDictionary();
  setNotice("Entry removed locally. Save Settings to persist.", "info");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function emptyToNull(value) {
  const normalized = String(value || "").trim();
  return normalized ? normalized : null;
}

saveButton.addEventListener("click", async () => {
  try {
    await saveConfig();
  } catch (error) {
    setNotice(error.message, "error");
  }
});

refreshStatusButton.addEventListener("click", async () => {
  try {
    await loadStatus();
    setNotice("Backend status refreshed.", "success");
  } catch (error) {
    setNotice(error.message, "error");
  }
});

dictionaryForm.addEventListener("submit", addDictionaryEntry);
dictionaryBody.addEventListener("click", removeDictionaryEntry);

Promise.all([loadConfig(), loadStatus()])
  .then(() => setNotice("Settings loaded.", "success"))
  .catch((error) => setNotice(error.message, "error"));
