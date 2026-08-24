const state = {
  mode: "po",
  resultMode: null,
  items: [],
  reference: null,
  printEnabled: false,
  busy: false,
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
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
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
    throw new Error(detail || "The request could not be completed");
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
  (mode === "po" ? elements.poNumber : elements.itemCode).focus();
}

function quantityValue(value) {
  return Math.max(1, Math.min(999, Number.parseInt(value, 10) || 1));
}

function renderResults({ title, kicker, meta }) {
  elements.resultTitle.textContent = title;
  elements.resultKicker.textContent = kicker;
  elements.resultMeta.textContent = meta;
  elements.itemList.replaceChildren();

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
    showToast(
      result.status === "submitted"
        ? `${result.label_count} labels sent to the printer.`
        : `${result.label_count} labels saved as test job ${result.job_id}. Nothing was printed.`
    );
  } catch (error) {
    showMessage(error.message);
  } finally {
    state.busy = false;
    updateSummary();
  }
});

checkPrinter();
