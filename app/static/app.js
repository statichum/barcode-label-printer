const themeStorageKey = "prv-label-station-theme";

const state = {
  mode: "po",
  resultMode: null,
  items: [],
  reference: null,
  sortMode: "natural",
  printEnabled: false,
  busy: false,
  barcodeAdminToken: "",
  assignmentItems: [],
  assignmentVisibleLimit: 250,
  assignmentSelected: new Set(),
  assignmentPreview: null,
  assignmentStoredAt: null,
  assignmentLargeBatchUnlocked: false,
  lastAssignedItems: [],
  barcodeEntryItems: [],
  barcodeEntryVisibleLimit: 250,
  barcodeEntryStoredAt: null,
  barcodeEntryStockStoredAt: null,
  barcodeEntryStockFresh: false,
  barcodeEntrySelected: null,
  barcodeEntryPending: new Map(),
  barcodeEntrySending: false,
  stockLabelRefreshRequested: false,
  barcodeCheckRequestId: 0,
};

const elements = {
  tabs: [...document.querySelectorAll(".mode-tab")],
  panels: [...document.querySelectorAll(".panel")],
  poForm: document.querySelector("#po-form"),
  manualForm: document.querySelector("#manual-form"),
  poNumber: document.querySelector("#po-number"),
  itemCode: document.querySelector("#item-code"),
  manualQuantity: document.querySelector("#manual-quantity"),
  workspace: document.querySelector(".workspace"),
  message: document.querySelector("#message"),
  results: document.querySelector("#results"),
  resultKicker: document.querySelector("#result-kicker"),
  resultTitle: document.querySelector("#result-title"),
  resultMeta: document.querySelector("#result-meta"),
  itemList: document.querySelector("#item-list"),
  template: document.querySelector("#item-template"),
  selectAll: document.querySelector("#select-all"),
  selectNone: document.querySelector("#select-none"),
  labelCount: document.querySelector("#label-count"),
  itemCount: document.querySelector("#item-count"),
  printButton: document.querySelector("#print-button"),
  printButtonLabel: document.querySelector("#print-button-label"),
  printerStatus: document.querySelector("#printer-status"),
  toast: document.querySelector("#toast"),
  sortControl: document.querySelector("#sort-control"),
  barcodeEntrySearch: document.querySelector("#barcode-entry-search"),
  barcodeEntryMissingOnly: document.querySelector("#barcode-entry-missing-only"),
  barcodeEntryMeta: document.querySelector("#barcode-entry-meta"),
  barcodeEntryItemList: document.querySelector("#barcode-entry-item-list"),
  barcodeEntryLoading: document.querySelector("#barcode-entry-loading"),
  barcodeEntryLoadingTitle: document.querySelector("#barcode-entry-loading-title"),
  refreshBarcodeEntryItems: document.querySelector("#refresh-barcode-entry-items"),
  refreshBarcodeEntryStock: document.querySelector("#refresh-barcode-entry-stock"),
  clearBarcodeEntryBatch: document.querySelector("#clear-barcode-entry-batch"),
  barcodeEntryQueue: document.querySelector("#barcode-entry-queue"),
  barcodeEntryCount: document.querySelector("#barcode-entry-count"),
  sendEnteredBarcodes: document.querySelector("#send-entered-barcodes"),
  barcodeEntryDialog: document.querySelector("#barcode-entry-dialog"),
  barcodeEntryForm: document.querySelector("#barcode-entry-form"),
  barcodeEntryItemCode: document.querySelector("#barcode-entry-item-code"),
  barcodeEntryDescription: document.querySelector("#barcode-entry-description"),
  barcodeEntryValue: document.querySelector("#barcode-entry-value"),
  barcodeEntryError: document.querySelector("#barcode-entry-error"),
  assignLocked: document.querySelector("#assign-locked"),
  assignWorkspace: document.querySelector("#assign-workspace"),
  assignSearch: document.querySelector("#assign-search"),
  assignMissingOnly: document.querySelector("#assign-missing-only"),
  assignMeta: document.querySelector("#assign-meta"),
  assignItemList: document.querySelector("#assign-item-list"),
  assignLoading: document.querySelector("#assign-loading"),
  assignLoadingTitle: document.querySelector("#assign-loading-title"),
  refreshAssignItems: document.querySelector("#refresh-assign-items"),
  selectFilteredAssignItems: document.querySelector("#select-filtered-assign-items"),
  assignCount: document.querySelector("#assign-count"),
  reviewAssignments: document.querySelector("#review-assignments"),
  assignmentLimitCopy: document.querySelector("#assignment-limit-copy"),
  unlockLargeAssignments: document.querySelector("#unlock-large-assignments"),
  largeAssignmentsUnlocked: document.querySelector("#large-assignments-unlocked"),
  largeBatchPinDialog: document.querySelector("#large-batch-pin-dialog"),
  largeBatchPinError: document.querySelector("#large-batch-pin-error"),
  assignPinDialog: document.querySelector("#assign-pin-dialog"),
  assignmentPreviewDialog: document.querySelector("#assignment-preview-dialog"),
  assignmentPreviewList: document.querySelector("#assignment-preview-list"),
  assignmentWriteWarning: document.querySelector("#assignment-write-warning"),
  commitAssignments: document.querySelector("#commit-assignments"),
  assignmentCompleteDialog: document.querySelector("#assignment-complete-dialog"),
  assignmentCompleteSummary: document.querySelector("#assignment-complete-summary"),
  prepareStockLabels: document.querySelector("#prepare-stock-labels"),
  refreshAndPrepareStockLabels: document.querySelector("#refresh-and-prepare-stock-labels"),
  stockLabelProgress: document.querySelector("#stock-label-progress"),
  stockLabelProgressTitle: document.querySelector("#stock-label-progress-title"),
  stockLabelProgressDetail: document.querySelector("#stock-label-progress-detail"),
  stockLabelError: document.querySelector("#stock-label-error"),
  stockLabelReauth: document.querySelector("#stock-label-reauth"),
  stockLabelReauthCopy: document.querySelector("#stock-label-reauth-copy"),
  stockLabelReauthError: document.querySelector("#stock-label-reauth-error"),
  printResultDialog: document.querySelector("#print-result-dialog"),
  printResultKicker: document.querySelector("#print-result-kicker"),
  printResultTitle: document.querySelector("#print-result-title"),
  printResultMessage: document.querySelector("#print-result-message"),
  themeToggle: document.querySelector("#theme-toggle"),
  themeColor: document.querySelector("meta[name='theme-color']"),
  barcodeCheckIdle: document.querySelector("#barcode-check-idle"),
  barcodeCheckLoading: document.querySelector("#barcode-check-loading"),
  barcodeCheckLoadingCode: document.querySelector("#barcode-check-loading-code"),
  barcodeCheckMatch: document.querySelector("#barcode-check-match"),
  barcodeCheckScanned: document.querySelector("#barcode-check-scanned"),
  barcodeCheckItemCode: document.querySelector("#barcode-check-item-code"),
  barcodeCheckDescription: document.querySelector("#barcode-check-description"),
  barcodeCheckSupplierCode: document.querySelector("#barcode-check-supplier-code"),
  barcodeCheckMissing: document.querySelector("#barcode-check-missing"),
  barcodeCheckMissingTitle: document.querySelector("#barcode-check-missing-title"),
  barcodeCheckMissingMessage: document.querySelector("#barcode-check-missing-message"),
  barcodeCheckMissingCode: document.querySelector("#barcode-check-missing-code"),
};

function storedTheme() {
  try {
    const theme = localStorage.getItem(themeStorageKey);
    return theme === "light" || theme === "dark" ? theme : null;
  } catch {
    return null;
  }
}

function applyTheme(theme, persist = true) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  const label = dark ? "Switch to light mode" : "Switch to dark mode";
  elements.themeToggle.setAttribute("aria-label", label);
  elements.themeToggle.setAttribute("title", label);
  elements.themeToggle.setAttribute("aria-pressed", String(dark));
  elements.themeColor.setAttribute("content", dark ? "#101815" : "#17483e");
  if (persist) {
    try {
      localStorage.setItem(themeStorageKey, dark ? "dark" : "light");
    } catch {
      // Theme persistence is optional when browser storage is unavailable.
    }
  }
}

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
applyTheme(storedTheme() || (systemTheme.matches ? "dark" : "light"), false);
elements.themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
systemTheme.addEventListener?.("change", (event) => {
  if (!storedTheme()) applyTheme(event.matches ? "dark" : "light", false);
});

const naturalCollator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });
const defaultMaxAssignmentItems = 350;
const catalogueRenderBatchSize = 250;
const stockCacheSeconds = 12 * 60 * 60;
const assignedItemRecoveryKey = "prv-label-station:last-assigned-items";

function rememberAssignedItems(items) {
  try {
    sessionStorage.setItem(
      assignedItemRecoveryKey,
      JSON.stringify(items.map((item) => ({ item_code: item.item_code })))
    );
  } catch {
    // In-memory recovery still works when browser storage is unavailable.
  }
}

function forgetAssignedItems() {
  try {
    sessionStorage.removeItem(assignedItemRecoveryKey);
  } catch {
    // Nothing else is required when browser storage is unavailable.
  }
}

function restoreAssignedItems() {
  try {
    const items = JSON.parse(sessionStorage.getItem(assignedItemRecoveryKey) || "[]");
    if (!Array.isArray(items) || items.length > 20_000) return [];
    return items.filter((item) => item && typeof item.item_code === "string" && item.item_code);
  } catch {
    return [];
  }
}

async function api(path, options = {}) {
  const { barcodeAdmin = false, ...requestOptions } = options;
  const response = await fetch(path, {
    ...requestOptions,
    headers: {
      "Content-Type": "application/json",
      ...(barcodeAdmin && state.barcodeAdminToken
        ? { Authorization: `Bearer ${state.barcodeAdminToken}` }
        : {}),
      ...(requestOptions.headers || {}),
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join("; ")
      : data.detail;
    const error = new Error(detail || "The request could not be completed");
    error.status = response.status;
    if (barcodeAdmin && response.status === 401) {
      state.barcodeAdminToken = "";
      state.assignmentLargeBatchUnlocked = false;
    }
    throw error;
  }
  return data;
}

function setBusy(busy) {
  state.busy = busy;
  elements.workspace.classList.toggle("loading", busy);
  document.querySelectorAll("form button").forEach((button) => {
    button.disabled = busy;
  });
  updateSummary();
}

function showMessage(text, type = "error") {
  elements.message.textContent = text;
  elements.message.className = `message ${type === "info" ? "info" : ""}`;
  elements.message.hidden = false;
}

function clearMessage() {
  elements.message.hidden = true;
  elements.message.textContent = "";
}

let toastTimer;
function showToast(text) {
  clearTimeout(toastTimer);
  elements.toast.textContent = text;
  elements.toast.hidden = false;
  toastTimer = setTimeout(() => {
    elements.toast.hidden = true;
  }, 5000);
}

function showPrintResult({ success, title, message }) {
  elements.printResultKicker.textContent = success ? "PRINT COMPLETE" : "PRINT ERROR";
  elements.printResultTitle.textContent = title;
  elements.printResultMessage.textContent = message;
  if (!elements.printResultDialog.open) elements.printResultDialog.showModal();
}

function switchMode(mode) {
  state.mode = mode;
  elements.tabs.forEach((tab) => {
    const active = tab.dataset.mode === mode;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  elements.panels.forEach((panel) => {
    const active = panel.id === `${mode}-panel`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  clearMessage();
  if (mode === "assign") {
    elements.results.hidden = true;
    showAssignmentAccess();
  } else if (mode === "entry") {
    elements.results.hidden = true;
    showBarcodeEntry();
  } else if (mode === "check") {
    elements.results.hidden = true;
  } else {
    if (state.items.length) elements.results.hidden = false;
    (mode === "po" ? elements.poNumber : elements.itemCode).focus();
  }
}

function showBarcodeCheckState(activeState) {
  elements.barcodeCheckIdle.hidden = activeState !== "idle";
  elements.barcodeCheckLoading.hidden = activeState !== "loading";
  elements.barcodeCheckMatch.hidden = activeState !== "match";
  elements.barcodeCheckMissing.hidden = activeState !== "missing";
}

async function checkBarcode(rawBarcode) {
  const barcode = String(rawBarcode || "").trim();
  if (!barcode) return;
  const requestId = ++state.barcodeCheckRequestId;
  clearMessage();
  elements.barcodeCheckLoadingCode.textContent = barcode;
  showBarcodeCheckState("loading");
  try {
    const response = await api("/api/barcodes/check", {
      method: "POST",
      body: JSON.stringify({ barcode }),
    });
    if (requestId !== state.barcodeCheckRequestId) return;
    if (!response.found) {
      elements.barcodeCheckMissingTitle.textContent = "No item found.";
      elements.barcodeCheckMissingMessage.textContent = "No MYOB Barcode row is linked to this scan.";
      elements.barcodeCheckMissingCode.textContent = barcode;
      showBarcodeCheckState("missing");
      return;
    }
    elements.barcodeCheckScanned.textContent = response.barcode;
    elements.barcodeCheckItemCode.textContent = response.item_code;
    elements.barcodeCheckDescription.textContent = response.description;
    elements.barcodeCheckSupplierCode.textContent = response.supplier_codes.length
      ? response.supplier_codes.join(" · ")
      : "Not recorded in MYOB";
    showBarcodeCheckState("match");
  } catch (error) {
    if (requestId !== state.barcodeCheckRequestId) return;
    elements.barcodeCheckMissingTitle.textContent = "Barcode check failed.";
    elements.barcodeCheckMissingMessage.textContent = error.message;
    elements.barcodeCheckMissingCode.textContent = barcode;
    showBarcodeCheckState("missing");
  }
}

let barcodeScanBuffer = "";
let barcodeScanLastKeyAt = 0;
document.addEventListener("keydown", (event) => {
  if (state.mode !== "check" || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
  if (document.querySelector("dialog[open]")) return;
  const buttonAction = event.target instanceof HTMLButtonElement
    && !barcodeScanBuffer
    && (event.key === "Enter" || event.key === " ");
  if (buttonAction) return;
  const now = performance.now();
  if (event.key === "Enter" || event.key === "Tab") {
    const barcode = barcodeScanBuffer;
    barcodeScanBuffer = "";
    barcodeScanLastKeyAt = 0;
    if (!barcode) return;
    event.preventDefault();
    checkBarcode(barcode);
    return;
  }
  if (event.key.length !== 1) return;
  if (now - barcodeScanLastKeyAt > 180) barcodeScanBuffer = "";
  barcodeScanBuffer += event.key;
  barcodeScanLastKeyAt = now;
  event.preventDefault();
});

function quantityValue(value) {
  return Math.max(1, Math.min(999, Number.parseInt(value, 10) || 1));
}

function renderResults({ title, kicker, meta }) {
  elements.resultTitle.textContent = title;
  elements.resultKicker.textContent = kicker;
  elements.resultMeta.textContent = meta;
  elements.itemList.replaceChildren();

  elements.sortControl.hidden = state.resultMode !== "po";
  elements.sortControl.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.sort === state.sortMode);
  });

  state.items.forEach((item, index) => {
    const row = elements.template.content.firstElementChild.cloneNode(true);
    const checkbox = row.querySelector(".item-check");
    const quantity = row.querySelector(".item-quantity");
    const warning = row.querySelector(".item-warning");
    const barcodeCell = row.querySelector(".barcode-cell");

    row.dataset.index = String(index);
    checkbox.checked = Boolean(item.selected && item.printable);
    checkbox.disabled = !item.printable;
    checkbox.nextElementSibling.nextElementSibling.textContent = `Select ${item.item_code}`;
    row.querySelector(".item-description").textContent = item.description;
    row.querySelector(".item-code").textContent = item.item_code;
    row.querySelector(".barcode-value").textContent = item.barcode || "No barcode";
    quantity.value = quantityValue(item.quantity);
    quantity.disabled = !item.printable;

    if (!item.printable) {
      barcodeCell.classList.add("missing");
    }
    if (item.warning || !item.printable) {
      warning.textContent = item.warning || "This item cannot be printed";
      warning.hidden = false;
    }

    checkbox.addEventListener("change", () => {
      state.items[index].selected = checkbox.checked;
      updateSummary();
    });
    quantity.addEventListener("change", () => {
      quantity.value = quantityValue(quantity.value);
      state.items[index].quantity = quantityValue(quantity.value);
      updateSummary();
    });
    row.querySelector(".qty-minus").addEventListener("click", () => {
      quantity.value = quantityValue(Number(quantity.value) - 1);
      quantity.dispatchEvent(new Event("change"));
    });
    row.querySelector(".qty-plus").addEventListener("click", () => {
      quantity.value = quantityValue(Number(quantity.value) + 1);
      quantity.dispatchEvent(new Event("change"));
    });

    elements.itemList.append(row);
  });

  elements.results.hidden = false;
  updateSummary();
}

function applyResultSort() {
  state.items.sort((left, right) => {
    if (state.sortMode === "po") {
      return Number(left.po_position ?? 0) - Number(right.po_position ?? 0);
    }
    return naturalCollator.compare(left.item_code, right.item_code)
      || Number(left.po_position ?? 0) - Number(right.po_position ?? 0);
  });
}

function rerenderCurrentResults() {
  applyResultSort();
  renderResults({
    kicker: elements.resultKicker.textContent,
    title: elements.resultTitle.textContent,
    meta: elements.resultMeta.textContent,
  });
}

function updateSummary() {
  const selected = state.items.filter((item) => item.selected && item.printable);
  const labels = selected.reduce((total, item) => total + quantityValue(item.quantity), 0);
  elements.labelCount.textContent = String(labels);
  elements.itemCount.textContent = `${selected.length} item${selected.length === 1 ? "" : "s"} selected`;
  elements.printButton.disabled = state.busy || labels === 0;
  elements.printButtonLabel.textContent = state.printEnabled ? "Print labels" : "Create test job";
}

async function checkPrinter() {
  const dot = elements.printerStatus.querySelector(".status-dot");
  const title = elements.printerStatus.querySelector("b");
  const detail = elements.printerStatus.querySelector("small");
  try {
    const status = await api("/api/printer/status");
    state.printEnabled = Boolean(status.print_enabled);
    dot.className = `status-dot ${status.online ? "online" : "offline"}`;
    title.textContent = status.online
      ? status.print_enabled ? "Printer ready" : "Printer found · test mode"
      : "Printer offline";
    detail.textContent = status.online
      ? `${status.model || status.name} · ${status.ip}:${status.port}`
      : status.message || status.name;
  } catch (error) {
    dot.className = "status-dot offline";
    title.textContent = "Printer check failed";
    detail.textContent = error.message;
  }
  updateSummary();
}

elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchMode(tab.dataset.mode));
});

elements.poForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  setBusy(true);
  const poNumber = elements.poNumber.value.trim();
  try {
    const order = await api("/api/purchase-orders/lookup", {
      method: "POST",
      body: JSON.stringify({ po_number: poNumber }),
    });
    state.items = order.lines;
    state.resultMode = "po";
    state.sortMode = "natural";
    applyResultSort();
    state.reference = order.po_number || poNumber;
    if (!state.items.length) {
      elements.results.hidden = true;
      showMessage(`Purchase order ${poNumber} has no inventory lines.`);
      return;
    }
    const missingCount = state.items.filter((item) => !item.printable).length;
    renderResults({
      kicker: "PURCHASE ORDER",
      title: `PO ${state.reference}`,
      meta: `${state.items.length} line${state.items.length === 1 ? "" : "s"} found${missingCount ? ` · ${missingCount} missing a barcode` : ""}`,
    });
    if (missingCount) {
      showMessage(`${missingCount} item${missingCount === 1 ? " is" : "s are"} unavailable for printing because no barcode was found.`);
    }
    elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    elements.results.hidden = true;
    showMessage(error.message);
  } finally {
    setBusy(false);
  }
});

elements.manualForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  setBusy(true);
  const code = elements.itemCode.value.trim();
  const requestedQuantity = quantityValue(elements.manualQuantity.value);
  try {
    const response = await api("/api/items/lookup", {
      method: "POST",
      body: JSON.stringify({ item_codes: [code] }),
    });
    const item = response.items[0];
    if (state.resultMode !== "manual") {
      state.items = [];
      state.resultMode = "manual";
      state.sortMode = "natural";
    }
    const existingIndex = state.items.length
      ? state.items.findIndex((entry) => entry.item_code === item.item_code)
      : -1;
    if (existingIndex >= 0) {
      state.items[existingIndex].quantity = quantityValue(
        state.items[existingIndex].quantity + requestedQuantity
      );
      state.items[existingIndex].selected = state.items[existingIndex].printable;
    } else {
      item.quantity = requestedQuantity;
      state.items.push(item);
    }
    applyResultSort();
    state.reference = null;
    renderResults({
      kicker: "MANUAL LABELS",
      title: "Label list",
      meta: `${state.items.length} item${state.items.length === 1 ? "" : "s"} added manually`,
    });
    if (!item.printable) showMessage(item.warning);
    elements.itemCode.value = "";
    elements.manualQuantity.value = "1";
    elements.itemCode.focus();
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(false);
  }
});

elements.selectAll.addEventListener("click", () => {
  state.items.forEach((item) => { item.selected = item.printable; });
  renderResults({
    kicker: elements.resultKicker.textContent,
    title: elements.resultTitle.textContent,
    meta: elements.resultMeta.textContent,
  });
});

elements.selectNone.addEventListener("click", () => {
  state.items.forEach((item) => { item.selected = false; });
  renderResults({
    kicker: elements.resultKicker.textContent,
    title: elements.resultTitle.textContent,
    meta: elements.resultMeta.textContent,
  });
});

elements.sortControl.querySelectorAll("button").forEach((button) => {
  button.addEventListener("click", () => {
    state.sortMode = button.dataset.sort;
    rerenderCurrentResults();
  });
});

elements.printButton.addEventListener("click", async () => {
  clearMessage();
  const selected = state.items
    .filter((item) => item.selected && item.printable)
    .map((item) => ({ item_code: item.item_code, quantity: quantityValue(item.quantity) }));
  if (!selected.length) return;

  state.busy = true;
  elements.printButton.disabled = true;
  elements.printButtonLabel.textContent = state.printEnabled ? "Sending…" : "Saving…";
  try {
    const result = await api("/api/print", {
      method: "POST",
      body: JSON.stringify({
        items: selected,
        source: elements.resultKicker.textContent === "PURCHASE ORDER" ? "purchase-order" : "manual",
        reference: state.reference,
      }),
    });
    const submitted = result.status === "submitted";
    showPrintResult({
      success: true,
      title: submitted
        ? "Barcodes sent to printer successfully."
        : "Test print job saved successfully.",
      message: submitted
        ? `${result.label_count} label${result.label_count === 1 ? " was" : "s were"} accepted by the printer connection.`
        : `${result.label_count} label${result.label_count === 1 ? " was" : "s were"} saved as test job ${result.job_id}. Nothing was printed.`,
    });
    state.items.forEach((item) => { item.selected = false; });
    rerenderCurrentResults();
  } catch (error) {
    showPrintResult({
      success: false,
      title: "Print error",
      message: error.message,
    });
  } finally {
    state.busy = false;
    updateSummary();
  }
});

function matchesSearchTerms(item, query) {
  const terms = query.split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const searchable = [item.item_code, item.description, item.barcode || ""]
    .join(" ")
    .toLocaleLowerCase();
  return terms.every((term) => searchable.includes(term));
}

function hasUsableBarcode(item) {
  const barcode = String(item.barcode || "").trim().toLocaleLowerCase();
  return Boolean(barcode && barcode !== "x");
}

function barcodeEntryMatches(item, query) {
  if (elements.barcodeEntryMissingOnly.checked && hasUsableBarcode(item)) return false;
  return matchesSearchTerms(item, query);
}

function filteredBarcodeEntryItems() {
  const query = elements.barcodeEntrySearch.value.trim().toLocaleLowerCase();
  return state.barcodeEntryItems
    .filter((item) => barcodeEntryMatches(item, query))
    .sort((left, right) => naturalCollator.compare(left.item_code, right.item_code));
}

function updateBarcodeEntrySummary() {
  const count = state.barcodeEntryPending.size;
  elements.barcodeEntryCount.textContent = `${count} barcode${count === 1 ? "" : "s"} ready`;
  elements.sendEnteredBarcodes.disabled = state.busy || count === 0;
  elements.sendEnteredBarcodes.textContent = state.barcodeEntrySending
    ? "Sending to MYOB…"
    : count
    ? `Send ${count} to MYOB`
    : "Send to MYOB";
  elements.clearBarcodeEntryBatch.disabled = state.busy || count === 0;
}

function renderBarcodeEntryQueue() {
  elements.barcodeEntryQueue.replaceChildren();
  const entries = [...state.barcodeEntryPending.values()]
    .sort((left, right) => naturalCollator.compare(left.item_code, right.item_code));
  elements.barcodeEntryQueue.hidden = entries.length === 0;
  for (const entry of entries) {
    const row = document.createElement("div");
    row.className = "barcode-entry-queue-row";
    row.innerHTML = "<div><b></b><small></small></div><code></code><button type=\"button\" class=\"text-button\">Remove</button>";
    row.querySelector("b").textContent = entry.item_code;
    row.querySelector("small").textContent = entry.description;
    row.querySelector("code").textContent = entry.barcode;
    row.querySelector("button").addEventListener("click", () => {
      state.barcodeEntryPending.delete(entry.item_code);
      renderBarcodeEntryItems();
    });
    elements.barcodeEntryQueue.append(row);
  }
}

function selectBarcodeEntryItem(item) {
  if (!item.barcode_entry_allowed) return;
  state.barcodeEntrySelected = item;
  const pending = state.barcodeEntryPending.get(item.item_code);
  elements.barcodeEntryItemCode.textContent = item.item_code;
  elements.barcodeEntryDescription.textContent = item.description;
  elements.barcodeEntryValue.value = pending ? pending.barcode : "";
  elements.barcodeEntryError.hidden = true;
  elements.barcodeEntryError.textContent = "";
  if (!elements.barcodeEntryDialog.open) elements.barcodeEntryDialog.showModal();
  setTimeout(() => {
    elements.barcodeEntryValue.focus();
    elements.barcodeEntryValue.select();
  }, 0);
}

function barcodeEntryStockCacheIsFresh() {
  return Boolean(
    state.barcodeEntryStockFresh
    && state.barcodeEntryStockStoredAt
    && Date.now() / 1000 - state.barcodeEntryStockStoredAt < stockCacheSeconds
  );
}

function appendLoadMoreControl(container, total, visibleCount, loadMore) {
  const remaining = total - visibleCount;
  if (remaining <= 0) return;
  const nextCount = Math.min(catalogueRenderBatchSize, remaining);
  const control = document.createElement("div");
  control.className = "catalogue-load-more";
  const button = document.createElement("button");
  button.className = "secondary-button";
  button.type = "button";
  button.textContent = `Load ${nextCount.toLocaleString("en-NZ")} more`;
  const status = document.createElement("small");
  status.textContent = `${remaining.toLocaleString("en-NZ")} item${remaining === 1 ? "" : "s"} remaining`;
  button.addEventListener("click", loadMore);
  control.append(button, status);
  container.append(control);
}

function loadMoreBarcodeEntryItems() {
  const total = filteredBarcodeEntryItems().length;
  if (state.barcodeEntryVisibleLimit >= total) return;
  const scrollTop = elements.barcodeEntryItemList.scrollTop;
  state.barcodeEntryVisibleLimit += catalogueRenderBatchSize;
  renderBarcodeEntryItems();
  elements.barcodeEntryItemList.scrollTop = scrollTop;
}

function renderBarcodeEntryItems() {
  const matches = filteredBarcodeEntryItems();
  const visible = matches.slice(0, state.barcodeEntryVisibleLimit);
  const stockCacheFresh = barcodeEntryStockCacheIsFresh();
  elements.barcodeEntryItemList.replaceChildren();

  for (const item of visible) {
    const pending = state.barcodeEntryPending.has(item.item_code);
    const selectable = item.barcode_entry_allowed;
    const row = document.createElement("article");
    row.className = `assign-item-row barcode-entry-row ${selectable ? "" : "existing"}`;
    row.innerHTML = `
      <div class="entry-action"><span class="secondary-button"></span></div>
      <div><b></b><code></code></div>
      <div class="assign-current-barcode"><code></code><small></small></div>
      <div class="entry-stock"><b></b></div>`;
    const action = row.querySelector(".entry-action .secondary-button");
    action.textContent = pending
      ? "Edit"
      : selectable
      ? hasUsableBarcode(item) ? "Update" : "Enter"
      : "Unavailable";
    row.querySelector("b").textContent = item.description;
    row.querySelectorAll("code")[0].textContent = item.item_code;
    const barcode = row.querySelector(".assign-current-barcode code");
    barcode.textContent = pending
      ? state.barcodeEntryPending.get(item.item_code).barcode
      : item.barcode || "No barcode";
    barcode.classList.toggle("missing-barcode", !item.barcode && !pending);
    const warning = row.querySelector("small");
    warning.textContent = pending ? "Ready to send" : item.warning || "";
    warning.hidden = !warning.textContent;
    const stock = row.querySelector(".entry-stock b");
    stock.textContent = stockCacheFresh && Number.isInteger(item.stock_on_hand)
      ? item.stock_on_hand.toLocaleString("en-NZ")
      : "—";
    stock.title = stockCacheFresh && Number.isInteger(item.stock_on_hand)
      ? "MAIN warehouse stock on hand"
      : state.barcodeEntryStockStoredAt
      ? "The stock-on-hand cache has expired; refresh it to view stock"
      : "Stock on hand has not been refreshed for this item";
    if (selectable) {
      row.classList.add("selectable");
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.setAttribute("aria-label", `Enter a barcode for ${item.item_code}`);
      row.addEventListener("click", () => selectBarcodeEntryItem(item));
      row.addEventListener("keydown", (event) => {
        if (event.target !== row) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectBarcodeEntryItem(item);
        }
      });
    }
    elements.barcodeEntryItemList.append(row);
  }

  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "assign-empty";
    empty.textContent = "No active stock items match this search.";
    elements.barcodeEntryItemList.append(empty);
  }
  appendLoadMoreControl(
    elements.barcodeEntryItemList,
    matches.length,
    visible.length,
    loadMoreBarcodeEntryItems
  );
  const limitCopy = matches.length > visible.length ? ` · showing ${visible.length}` : "";
  const storedCopy = state.barcodeEntryStoredAt
    ? ` · refreshed ${new Date(state.barcodeEntryStoredAt * 1000).toLocaleString("en-NZ", { dateStyle: "medium", timeStyle: "short" })}`
    : "";
  const stockCopy = stockCacheFresh && state.barcodeEntryStockStoredAt
    ? ` · stock ${new Date(state.barcodeEntryStockStoredAt * 1000).toLocaleString("en-NZ", { dateStyle: "medium", timeStyle: "short" })}`
    : state.barcodeEntryStockStoredAt
    ? " · stock cache expired — refresh required"
    : " · stock not refreshed";
  elements.barcodeEntryMeta.textContent = `${matches.length} matching of ${state.barcodeEntryItems.length} active items${limitCopy}${storedCopy}${stockCopy}`;
  renderBarcodeEntryQueue();
  updateBarcodeEntrySummary();
}

async function loadBarcodeEntryItems(refresh = false) {
  state.busy = true;
  elements.barcodeEntryLoading.hidden = false;
  elements.barcodeEntryLoadingTitle.textContent = refresh
    ? "Refreshing stock items from MYOB…"
    : "Loading the stock-item catalogue…";
  elements.refreshBarcodeEntryItems.disabled = true;
  elements.refreshBarcodeEntryItems.textContent = refresh ? "Refreshing…" : "Loading…";
  updateBarcodeEntrySummary();
  try {
    const hadItems = state.barcodeEntryItems.length > 0;
    const response = await api(`/api/barcode-entry/items${refresh ? "?refresh=true" : ""}`);
    state.barcodeEntryItems = response.items;
    state.barcodeEntryStoredAt = response.stored_at;
    state.barcodeEntryStockStoredAt = response.stock_stored_at;
    state.barcodeEntryStockFresh = response.stock_cache_fresh;
    if (refresh || !hadItems) state.barcodeEntryVisibleLimit = catalogueRenderBatchSize;
    renderBarcodeEntryItems();
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.busy = false;
    elements.barcodeEntryLoading.hidden = true;
    elements.refreshBarcodeEntryItems.disabled = false;
    elements.refreshBarcodeEntryItems.textContent = "↻ Refresh from MYOB";
    updateBarcodeEntrySummary();
  }
}

async function refreshBarcodeEntryStock() {
  if (state.busy) return;
  state.busy = true;
  elements.barcodeEntryLoading.hidden = false;
  elements.barcodeEntryLoadingTitle.textContent = "Refreshing MAIN stock on hand from MYOB…";
  elements.refreshBarcodeEntryItems.disabled = true;
  elements.refreshBarcodeEntryStock.disabled = true;
  elements.refreshBarcodeEntryStock.textContent = "Refreshing stock…";
  updateBarcodeEntrySummary();
  try {
    const response = await api("/api/barcode-entry/stock-on-hand/refresh", {
      method: "POST",
    });
    state.barcodeEntryItems.forEach((item) => {
      const itemCode = item.item_code.toLocaleUpperCase();
      item.stock_on_hand = Object.hasOwn(response.quantities, itemCode)
        ? response.quantities[itemCode]
        : null;
    });
    state.barcodeEntryStockStoredAt = response.stored_at;
    state.barcodeEntryStockFresh = true;
    renderBarcodeEntryItems();
    showToast("MAIN stock on hand refreshed from MYOB.");
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.busy = false;
    elements.barcodeEntryLoading.hidden = true;
    elements.refreshBarcodeEntryItems.disabled = false;
    elements.refreshBarcodeEntryStock.disabled = false;
    elements.refreshBarcodeEntryStock.textContent = "↻ Refresh stock on hand";
    updateBarcodeEntrySummary();
  }
}

function showBarcodeEntry() {
  loadBarcodeEntryItems(false);
}

elements.barcodeEntrySearch.addEventListener("input", () => {
  state.barcodeEntryVisibleLimit = catalogueRenderBatchSize;
  elements.barcodeEntryItemList.scrollTop = 0;
  renderBarcodeEntryItems();
});
elements.barcodeEntryMissingOnly.addEventListener("change", () => {
  state.barcodeEntryVisibleLimit = catalogueRenderBatchSize;
  elements.barcodeEntryItemList.scrollTop = 0;
  renderBarcodeEntryItems();
});
elements.barcodeEntryItemList.addEventListener("scroll", () => {
  const list = elements.barcodeEntryItemList;
  if (list.scrollTop + list.clientHeight >= list.scrollHeight - 140) {
    loadMoreBarcodeEntryItems();
  }
});
elements.refreshBarcodeEntryItems.addEventListener("click", () => loadBarcodeEntryItems(true));
elements.refreshBarcodeEntryStock.addEventListener("click", refreshBarcodeEntryStock);
elements.clearBarcodeEntryBatch.addEventListener("click", () => {
  state.barcodeEntryPending.clear();
  renderBarcodeEntryItems();
});
document.querySelector("#barcode-entry-close").addEventListener("click", () => {
  elements.barcodeEntryDialog.close();
});
elements.barcodeEntryValue.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  elements.barcodeEntryForm.requestSubmit();
});
elements.barcodeEntryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const item = state.barcodeEntrySelected;
  if (!item) return;
  const barcode = elements.barcodeEntryValue.value.trim();
  const duplicate = [...state.barcodeEntryPending.values()].find(
    (entry) => entry.item_code !== item.item_code
      && entry.barcode.toLocaleLowerCase() === barcode.toLocaleLowerCase()
  );
  if (duplicate) {
    elements.barcodeEntryError.textContent = `That barcode is already queued for ${duplicate.item_code}.`;
    elements.barcodeEntryError.hidden = false;
    elements.barcodeEntryValue.select();
    return;
  }
  state.barcodeEntryPending.set(item.item_code, {
    item_code: item.item_code,
    description: item.description,
    barcode,
  });
  elements.barcodeEntryDialog.close();
  state.barcodeEntrySelected = null;
  renderBarcodeEntryItems();
});
elements.sendEnteredBarcodes.addEventListener("click", async () => {
  if (!state.barcodeEntryPending.size || state.busy) return;
  clearMessage();
  state.busy = true;
  state.barcodeEntrySending = true;
  updateBarcodeEntrySummary();
  try {
    const result = await api("/api/barcode-entry/commit", {
      method: "POST",
      body: JSON.stringify({
        entries: [...state.barcodeEntryPending.values()].map((entry) => ({
          item_code: entry.item_code,
          barcode: entry.barcode,
        })),
      }),
    });
    const enteredByCode = new Map(
      result.entered.map((entry) => [entry.item_code, entry.barcode])
    );
    state.barcodeEntryItems.forEach((item) => {
      if (!enteredByCode.has(item.item_code)) return;
      item.barcode = enteredByCode.get(item.item_code);
      item.barcode_entry_allowed = true;
      item.warning = `Current barcode ${item.barcode} will be replaced`;
    });
    state.barcodeEntryPending.clear();
    renderBarcodeEntryItems();
    showToast(`${result.count} product barcode${result.count === 1 ? "" : "s"} saved to MYOB.`);
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.busy = false;
    state.barcodeEntrySending = false;
    renderBarcodeEntryItems();
  }
});

function showAssignmentAccess() {
  const unlocked = Boolean(state.barcodeAdminToken);
  elements.assignLocked.hidden = unlocked;
  elements.assignWorkspace.hidden = !unlocked;
  if (!unlocked) {
    if (!elements.assignPinDialog.open) elements.assignPinDialog.showModal();
    return;
  }
  if (!state.assignmentItems.length) loadAssignmentItems(false);
  else renderAssignmentItems();
}

function assignmentMatches(item, query) {
  if (elements.assignMissingOnly.checked && hasUsableBarcode(item)) return false;
  return matchesSearchTerms(item, query);
}

function updateAssignmentSummary() {
  const count = state.assignmentSelected.size;
  elements.assignCount.textContent = `${count} item${count === 1 ? "" : "s"} selected`;
  elements.reviewAssignments.disabled = state.busy || count === 0;
  elements.assignmentLimitCopy.hidden = state.assignmentLargeBatchUnlocked;
  elements.unlockLargeAssignments.hidden = state.assignmentLargeBatchUnlocked;
  elements.largeAssignmentsUnlocked.hidden = !state.assignmentLargeBatchUnlocked;
}

function filteredAssignmentItems() {
  const query = elements.assignSearch.value.trim().toLocaleLowerCase();
  return state.assignmentItems
    .filter((item) => assignmentMatches(item, query))
    .sort((left, right) => naturalCollator.compare(left.item_code, right.item_code));
}

function loadMoreAssignmentItems() {
  const total = filteredAssignmentItems().length;
  if (state.assignmentVisibleLimit >= total) return;
  const scrollTop = elements.assignItemList.scrollTop;
  state.assignmentVisibleLimit += catalogueRenderBatchSize;
  renderAssignmentItems();
  elements.assignItemList.scrollTop = scrollTop;
}

function renderAssignmentItems() {
  const matches = filteredAssignmentItems();
  const visible = matches.slice(0, state.assignmentVisibleLimit);
  elements.assignItemList.replaceChildren();

  for (const item of visible) {
    const row = document.createElement("article");
    row.className = `assign-item-row ${item.assignable ? "" : "existing"}`;
    row.innerHTML = `
      <div class="assign-check"><label class="check-control"><input type="checkbox" /><span aria-hidden="true">✓</span><span class="sr-only"></span></label></div>
      <div><b></b><code></code></div>
      <div class="assign-current-barcode"><code></code></div>`;
    const checkbox = row.querySelector("input");
    checkbox.checked = state.assignmentSelected.has(item.item_code);
    checkbox.disabled = !item.assignable;
    row.querySelector(".sr-only").textContent = `Assign a barcode to ${item.item_code}`;
    row.querySelector("b").textContent = item.description;
    row.querySelectorAll("code")[0].textContent = item.item_code;
    const barcode = row.querySelector(".assign-current-barcode code");
    barcode.textContent = item.barcode || "No barcode";
    barcode.classList.toggle("missing-barcode", !item.barcode || item.barcode.toLocaleLowerCase() === "x");
    if (item.warning) barcode.title = item.warning;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        if (
          !state.assignmentLargeBatchUnlocked
          && state.assignmentSelected.size >= defaultMaxAssignmentItems
        ) {
          checkbox.checked = false;
          showMessage(
            `A barcode assignment batch is limited to ${defaultMaxAssignmentItems} items unless a larger batch is unlocked.`,
            "info"
          );
          return;
        }
        state.assignmentSelected.add(item.item_code);
      } else state.assignmentSelected.delete(item.item_code);
      updateAssignmentSummary();
    });
    elements.assignItemList.append(row);
  }

  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "assign-empty";
    empty.textContent = "No active stock items match this search.";
    elements.assignItemList.append(empty);
  }
  appendLoadMoreControl(
    elements.assignItemList,
    matches.length,
    visible.length,
    loadMoreAssignmentItems
  );
  const limitCopy = matches.length > visible.length ? ` · showing ${visible.length}` : "";
  const storedCopy = state.assignmentStoredAt
    ? ` · stored ${new Date(state.assignmentStoredAt * 1000).toLocaleString("en-NZ", { dateStyle: "medium", timeStyle: "short" })}`
    : "";
  elements.assignMeta.textContent = `${matches.length} matching of ${state.assignmentItems.length} active items${limitCopy}${storedCopy}`;
  updateAssignmentSummary();
}

async function loadAssignmentItems(refresh = false) {
  state.busy = true;
  elements.assignLoading.hidden = false;
  elements.assignLoadingTitle.textContent = refresh
    ? "Refreshing stock items from MYOB…"
    : "Loading the stock-item catalogue…";
  elements.assignWorkspace.setAttribute("aria-busy", "true");
  elements.refreshAssignItems.disabled = true;
  elements.refreshAssignItems.textContent = refresh ? "Refreshing…" : "Loading…";
  elements.assignMeta.textContent = refresh ? "Refreshing active stock items from MYOB…" : "Loading active stock items…";
  elements.reviewAssignments.disabled = true;
  try {
    const response = await api(`/api/barcode-admin/items${refresh ? "?refresh=true" : ""}`, { barcodeAdmin: true });
    state.assignmentItems = response.items;
    state.assignmentStoredAt = response.stored_at;
    state.assignmentVisibleLimit = catalogueRenderBatchSize;
    elements.assignItemList.scrollTop = 0;
    state.assignmentSelected = new Set(
      [...state.assignmentSelected].filter((code) => response.items.some((item) => item.item_code === code && item.assignable))
    );
    renderAssignmentItems();
  } catch (error) {
    if (error.status === 401) showAssignmentAccess();
    showMessage(error.message);
  } finally {
    state.busy = false;
    elements.assignLoading.hidden = true;
    elements.assignWorkspace.removeAttribute("aria-busy");
    elements.refreshAssignItems.disabled = false;
    elements.refreshAssignItems.textContent = "↻ Refresh from MYOB";
    updateAssignmentSummary();
  }
}

function renderAssignmentPreview(preview) {
  elements.assignmentPreviewList.replaceChildren();
  const visibleAssignments = preview.assignments.slice(0, 500);
  for (const assignment of visibleAssignments) {
    const row = document.createElement("div");
    row.className = "assignment-preview-row";
    row.innerHTML = "<div><b></b><small></small></div><code></code>";
    row.querySelector("b").textContent = assignment.item_code;
    const action = assignment.action === "replace"
      ? `Replace ${assignment.previous_barcode || "existing Barcode row"}`
      : "Create new Barcode row";
    row.querySelector("small").textContent = `${assignment.description} · ${action}`;
    row.querySelector("code").textContent = assignment.barcode;
    elements.assignmentPreviewList.append(row);
  }
  if (preview.assignments.length > visibleAssignments.length) {
    const remainder = document.createElement("p");
    remainder.className = "assignment-preview-remainder";
    remainder.textContent = `${preview.assignments.length - visibleAssignments.length} additional assignments are selected and will also be written.`;
    elements.assignmentPreviewList.append(remainder);
  }
  elements.assignmentWriteWarning.hidden = preview.writes_enabled;
  elements.commitAssignments.disabled = !preview.writes_enabled;
  elements.commitAssignments.textContent = `Assign ${preview.assignments.length} barcode${preview.assignments.length === 1 ? "" : "s"} in MYOB`;
  if (!elements.assignmentPreviewDialog.open) elements.assignmentPreviewDialog.showModal();
}

document.querySelector("#unlock-assign").addEventListener("click", () => {
  if (!elements.assignPinDialog.open) elements.assignPinDialog.showModal();
});

document.querySelector("#assign-pin-close").addEventListener("click", () => elements.assignPinDialog.close());
document.querySelector("#assign-pin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  const pinInput = document.querySelector("#assign-pin");
  try {
    const response = await api("/api/barcode-admin/login", {
      method: "POST",
      body: JSON.stringify({ pin: pinInput.value }),
    });
    state.barcodeAdminToken = response.token;
    state.assignmentLargeBatchUnlocked = false;
    pinInput.value = "";
    elements.assignPinDialog.close();
    showAssignmentAccess();
  } catch (error) {
    showMessage(error.message);
    pinInput.select();
  }
});

elements.assignSearch.addEventListener("input", () => {
  state.assignmentVisibleLimit = catalogueRenderBatchSize;
  elements.assignItemList.scrollTop = 0;
  renderAssignmentItems();
});
elements.assignMissingOnly.addEventListener("change", () => {
  state.assignmentVisibleLimit = catalogueRenderBatchSize;
  elements.assignItemList.scrollTop = 0;
  renderAssignmentItems();
});
elements.assignItemList.addEventListener("scroll", () => {
  const list = elements.assignItemList;
  if (list.scrollTop + list.clientHeight >= list.scrollHeight - 140) {
    loadMoreAssignmentItems();
  }
});
elements.refreshAssignItems.addEventListener("click", () => loadAssignmentItems(true));
elements.unlockLargeAssignments.addEventListener("click", () => {
  elements.largeBatchPinError.hidden = true;
  if (!elements.largeBatchPinDialog.open) elements.largeBatchPinDialog.showModal();
  document.querySelector("#large-batch-pin").focus();
});
document.querySelector("#large-batch-pin-close").addEventListener("click", () => {
  elements.largeBatchPinDialog.close();
});
document.querySelector("#large-batch-pin-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const pinInput = document.querySelector("#large-batch-pin");
  elements.largeBatchPinError.hidden = true;
  try {
    await api("/api/barcode-admin/unlock-large-batches", {
      method: "POST",
      barcodeAdmin: true,
      body: JSON.stringify({ pin: pinInput.value }),
    });
    state.assignmentLargeBatchUnlocked = true;
    pinInput.value = "";
    elements.largeBatchPinDialog.close();
    updateAssignmentSummary();
    showMessage("Larger barcode batches are unlocked for this administration session.", "info");
  } catch (error) {
    elements.largeBatchPinError.textContent = error.message;
    elements.largeBatchPinError.hidden = false;
    pinInput.select();
  }
});
elements.selectFilteredAssignItems.addEventListener("click", () => {
  clearMessage();
  const filtered = filteredAssignmentItems().filter((item) => item.assignable);
  let skipped = 0;
  for (const item of filtered) {
    if (state.assignmentSelected.has(item.item_code)) continue;
    if (
      !state.assignmentLargeBatchUnlocked
      && state.assignmentSelected.size >= defaultMaxAssignmentItems
    ) {
      skipped += 1;
      continue;
    }
    state.assignmentSelected.add(item.item_code);
  }
  if (skipped) {
    showMessage(
      `${defaultMaxAssignmentItems} items selected—the normal safe batch limit. Re-enter the PIN to unlock the remaining ${skipped}.`,
      "info"
    );
  }
  renderAssignmentItems();
});
document.querySelector("#clear-assign-selection").addEventListener("click", () => {
  state.assignmentSelected.clear();
  renderAssignmentItems();
});

elements.reviewAssignments.addEventListener("click", async () => {
  if (!state.assignmentSelected.size || state.busy) return;
  state.busy = true;
  updateAssignmentSummary();
  elements.reviewAssignments.textContent = "Reserving barcode numbers…";
  showMessage(
    "Reserving permanent, unique barcode numbers. The first reservation after this upgrade scans all MYOB items and can take a few minutes.",
    "info"
  );
  try {
    const preview = await api("/api/barcode-admin/assignments/preview", {
      method: "POST",
      barcodeAdmin: true,
      body: JSON.stringify({ item_codes: [...state.assignmentSelected] }),
    });
    state.assignmentPreview = preview;
    clearMessage();
    renderAssignmentPreview(preview);
  } catch (error) {
    if (error.status === 401) showAssignmentAccess();
    showMessage(error.message);
  } finally {
    state.busy = false;
    elements.reviewAssignments.textContent = "Review assignments";
    updateAssignmentSummary();
  }
});

document.querySelector("#assignment-preview-close").addEventListener("click", () => elements.assignmentPreviewDialog.close());
elements.commitAssignments.addEventListener("click", async () => {
  if (!state.assignmentPreview || state.busy) return;
  state.busy = true;
  elements.commitAssignments.disabled = true;
  elements.commitAssignments.textContent = "Writing to MYOB…";
  try {
    const result = await api("/api/barcode-admin/assignments/commit", {
      method: "POST",
      barcodeAdmin: true,
      body: JSON.stringify({ preview_token: state.assignmentPreview.preview_token }),
    });
    const assignedByCode = new Map(result.assigned.map((item) => [item.item_code, item.barcode]));
    state.assignmentItems.forEach((item) => {
      if (!assignedByCode.has(item.item_code)) return;
      item.barcode = assignedByCode.get(item.item_code);
      item.assignable = true;
      state.assignmentSelected.delete(item.item_code);
    });
    elements.assignmentPreviewDialog.close();
    state.assignmentPreview = null;
    renderAssignmentItems();
    showToast(`${result.count} barcode${result.count === 1 ? "" : "s"} assigned in MYOB.`);
    state.lastAssignedItems = result.assigned;
    state.stockLabelRefreshRequested = false;
    rememberAssignedItems(result.assigned);
    elements.assignmentCompleteSummary.textContent = `${result.count} barcode${result.count === 1 ? " was" : "s were"} assigned successfully.`;
    elements.stockLabelError.hidden = true;
    elements.stockLabelReauth.hidden = true;
    if (!elements.assignmentCompleteDialog.open) elements.assignmentCompleteDialog.showModal();
  } catch (error) {
    elements.assignmentPreviewDialog.close();
    state.assignmentPreview = null;
    if (error.status === 401) {
      showAssignmentAccess();
    }
    showMessage(`${error.message} Review the assignments again before retrying.`);
  } finally {
    state.busy = false;
    if (state.assignmentPreview) renderAssignmentPreview(state.assignmentPreview);
    updateAssignmentSummary();
  }
});

function closeAssignmentCompleteDialog() {
  if (elements.assignmentCompleteDialog.open) elements.assignmentCompleteDialog.close();
}

document.querySelector("#assignment-complete-close").addEventListener("click", closeAssignmentCompleteDialog);
document.querySelector("#assignment-complete-done").addEventListener("click", () => {
  forgetAssignedItems();
  state.lastAssignedItems = [];
  closeAssignmentCompleteDialog();
});

function showStockLabelReauthentication(message = "Your barcode administration session has expired.") {
  elements.stockLabelError.textContent = message;
  elements.stockLabelError.hidden = false;
  elements.stockLabelReauthCopy.textContent = `The ${state.lastAssignedItems.length}-item assigned list is still safely held and will be used after login.`;
  elements.stockLabelReauthError.hidden = true;
  elements.stockLabelReauth.hidden = false;
  elements.prepareStockLabels.disabled = true;
  elements.refreshAndPrepareStockLabels.disabled = true;
  document.querySelector("#stock-label-pin").focus();
}

async function prepareAssignedStockLabels(refreshStock = false) {
  if (!state.lastAssignedItems.length || state.busy) return;
  state.stockLabelRefreshRequested = refreshStock;
  if (!state.barcodeAdminToken) {
    showStockLabelReauthentication("Barcode administration PIN required");
    return;
  }
  state.busy = true;
  clearMessage();
  elements.stockLabelError.hidden = true;
  elements.stockLabelReauth.hidden = true;
  elements.stockLabelProgress.hidden = false;
  elements.prepareStockLabels.disabled = true;
  elements.refreshAndPrepareStockLabels.disabled = true;
  elements.prepareStockLabels.textContent = refreshStock ? "Waiting for refresh…" : "Checking cache…";
  elements.stockLabelProgressTitle.textContent = refreshStock
    ? "Refreshing MAIN stock on hand from MYOB…"
    : "Checking stored MAIN stock…";
  elements.stockLabelProgressDetail.textContent = refreshStock
    ? "MYOB returns the full warehouse dataset, so this can take a minute or two."
    : "A valid stored snapshot is used immediately.";
  try {
    const response = await api(`/api/barcode-admin/stock-labels${refreshStock ? "?refresh_stock=true" : ""}`, {
      method: "POST",
      barcodeAdmin: true,
      body: JSON.stringify({ item_codes: state.lastAssignedItems.map((item) => item.item_code) }),
    });
    forgetAssignedItems();
    closeAssignmentCompleteDialog();
    if (!response.items.length) {
      elements.results.hidden = true;
      showMessage("None of the newly assigned items has stored QtyOnHand in MAIN.", "info");
      return;
    }
    state.items = response.items;
    state.resultMode = "stock";
    state.sortMode = "natural";
    state.reference = "MAIN stock after barcode assignment";
    applyResultSort();
    const zeroCopy = response.zero_stock.length
      ? ` · ${response.zero_stock.length} with no stock on hand`
      : "";
    renderResults({
      kicker: "MAIN STOCK ON HAND",
      title: "New barcode labels",
      meta: `${response.items.length} item${response.items.length === 1 ? "" : "s"} ready${zeroCopy}`,
    });
    elements.results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    if (error.status === 401) showStockLabelReauthentication(error.message);
    else {
      elements.stockLabelError.textContent = error.message;
      elements.stockLabelError.hidden = false;
    }
  } finally {
    state.busy = false;
    elements.stockLabelProgress.hidden = true;
    elements.prepareStockLabels.disabled = !elements.stockLabelReauth.hidden;
    elements.refreshAndPrepareStockLabels.disabled = !elements.stockLabelReauth.hidden;
    elements.prepareStockLabels.textContent = "Use stored stock";
    elements.refreshAndPrepareStockLabels.textContent = "Refresh stock first";
    updateAssignmentSummary();
    updateSummary();
  }
}

elements.prepareStockLabels.addEventListener("click", () => prepareAssignedStockLabels(false));
elements.refreshAndPrepareStockLabels.addEventListener("click", () => prepareAssignedStockLabels(true));
document.querySelector("#stock-label-reauth").addEventListener("submit", async (event) => {
  event.preventDefault();
  const pinInput = document.querySelector("#stock-label-pin");
  const submitButton = event.currentTarget.querySelector("button[type='submit']");
  elements.stockLabelReauthError.hidden = true;
  submitButton.disabled = true;
  submitButton.textContent = "Logging in…";
  try {
    const response = await api("/api/barcode-admin/login", {
      method: "POST",
      body: JSON.stringify({ pin: pinInput.value }),
    });
    state.barcodeAdminToken = response.token;
    state.assignmentLargeBatchUnlocked = false;
    pinInput.value = "";
    elements.stockLabelReauth.hidden = true;
    elements.stockLabelError.hidden = true;
    elements.prepareStockLabels.disabled = false;
    elements.refreshAndPrepareStockLabels.disabled = false;
    await prepareAssignedStockLabels(state.stockLabelRefreshRequested);
  } catch (error) {
    elements.stockLabelReauthError.textContent = error.message;
    elements.stockLabelReauthError.hidden = false;
    pinInput.select();
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Log in and prepare labels";
  }
});

function closePrintResultDialog() {
  if (elements.printResultDialog.open) elements.printResultDialog.close();
}

document.querySelector("#print-result-close").addEventListener("click", closePrintResultDialog);
document.querySelector("#print-result-done").addEventListener("click", closePrintResultDialog);

const recoveredAssignedItems = restoreAssignedItems();
if (recoveredAssignedItems.length) {
  state.lastAssignedItems = recoveredAssignedItems;
  elements.assignmentCompleteSummary.textContent = `${recoveredAssignedItems.length} assigned barcode${recoveredAssignedItems.length === 1 ? " was" : "s were"} recovered from this browser session.`;
  elements.stockLabelError.hidden = true;
  if (!elements.assignmentCompleteDialog.open) elements.assignmentCompleteDialog.showModal();
}

checkPrinter();
