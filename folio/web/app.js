"use strict";

/* Folio — front end. Files are streamed to the local Folio server as soon as they're added,
   so by the time you press Merge only the merge itself is left to do. */

const $ = (sel, root = document) => root.querySelector(sel);
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const PARALLEL_UPLOADS = 4;

const state = { items: [], seq: 0, merging: false, uploading: 0 };

const el = {
  list: $("#list"), empty: $("#empty"), listHead: $("#listHead"), hint: $("#hint"),
  sortBtn: $("#sortBtn"), sortMenu: $("#sortMenu"), clearBtn: $("#clearBtn"),
  statFiles: $("#statFiles"), statPages: $("#statPages"), statSize: $("#statSize"),
  outName: $("#outName"), bookmarks: $("#bookmarks"),
  mergeBtn: $("#mergeBtn"), mergeLabel: $("#mergeLabel"), mergeNote: $("#mergeNote"),
  progress: $("#progress"), progressFill: $("#progressFill"), progressLabel: $("#progressLabel"), progressValue: $("#progressValue"),
  result: $("#result"), resultName: $("#resultName"), resultMeta: $("#resultMeta"),
  downloadBtn: $("#downloadBtn"), previewBtn: $("#previewBtn"),
  filePicker: $("#filePicker"), folderPicker: $("#folderPicker"), dropOverlay: $("#dropOverlay"),
  toasts: $("#toasts"), closed: $("#closed"),
};

/* ---------- formatting ---------- */
const fmtInt = n => n.toLocaleString();
function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`;
}
const fmtSecs = s => s < 60 ? `${s.toFixed(s < 10 ? 1 : 0)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
const plural = (n, word) => `${fmtInt(n)} ${word}${n === 1 ? "" : "s"}`;

/* Mirrors parse_ranges() in folio/core.py; returns the number of pages selected, or null for "all". */
function countRange(spec, total) {
  spec = spec.trim();
  if (!spec) return null;
  let count = 0;
  for (let part of spec.split(",")) {
    part = part.trim();
    const m = /^(\d+)(?:\s*-\s*(\d*))?$/.exec(part);
    if (!m) throw new Error(`"${part}" isn't a page or range (try 1-5, 8, 10-)`);
    const a = +m[1], b = m[2] === undefined ? a : m[2] === "" ? total : +m[2];
    for (const n of [a, b]) if (n < 1 || n > total) throw new Error(`Page ${n} doesn't exist; this file has ${plural(total, "page")}`);
    count += Math.abs(b - a) + 1;
  }
  return count;
}

/* ---------- rows ---------- */
const ICON_GRIP = '<svg viewBox="0 0 24 24"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>';
const ICON_PDF = '<svg viewBox="0 0 26 32"><path d="M4 1.5h12l8 8V28a2.5 2.5 0 0 1-2.5 2.5h-17A2.5 2.5 0 0 1 2 28V4a2.5 2.5 0 0 1 2-2.5Z"/><path d="M16 1.5V7a2.5 2.5 0 0 0 2.5 2.5H24"/><text x="13" y="24" text-anchor="middle">PDF</text></svg>';
const ICON_TOP = '<svg viewBox="0 0 24 24"><path d="M5 4h14M12 20V9M7 13l5-5 5 5"/></svg>';
const ICON_X = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>';

function createRow(it) {
  const li = document.createElement("li");
  li.className = "row new";
  li.addEventListener("animationend", () => li.classList.remove("new"), { once: true });
  li.tabIndex = 0;
  li.dataset.key = it.key;
  li.innerHTML = `
    <button class="handle" type="button" tabindex="-1" aria-label="Drag to reorder">${ICON_GRIP}</button>
    <span class="idx"></span>
    <span class="file-icon" aria-hidden="true">${ICON_PDF}</span>
    <div class="file-main"><div class="file-name"></div><div class="file-meta"></div><div class="row-bar"><span></span></div></div>
    <input class="range" placeholder="All pages" spellcheck="false" autocomplete="off" aria-label="Pages to include">
    <div class="row-actions">
      <button class="icon-btn" type="button" data-act="top" title="Move to top" aria-label="Move to top">${ICON_TOP}</button>
      <button class="icon-btn remove" type="button" data-act="remove" title="Remove" aria-label="Remove">${ICON_X}</button>
    </div>`;
  const name = $(".file-name", li);
  name.textContent = it.name;
  name.title = it.path;
  li.setAttribute("aria-label", it.name);
  it.el = li;
  return li;
}

function updateRow(it) {
  const li = it.el;
  li.classList.toggle("error", it.status === "error");
  const meta = $(".file-meta", li), bar = $(".row-bar", li), range = $(".range", li);
  const size = fmtBytes(it.size);
  range.disabled = it.status !== "ready";
  bar.hidden = it.status !== "uploading" && it.status !== "queued";
  if (it.status === "queued") meta.textContent = `Waiting… · ${size}`;
  else if (it.status === "uploading") {
    const pct = it.size ? Math.round((it.loaded / it.size) * 100) : 100;
    meta.textContent = pct >= 100 ? `Checking… · ${size}` : `Preparing ${pct}% · ${size}`;
    $("span", bar).style.width = `${pct}%`;
  } else if (it.status === "error") meta.textContent = it.error;
  else if (it.rangeError) meta.textContent = it.rangeError;
  else if (it.rangeCount != null) meta.textContent = `${fmtInt(it.rangeCount)} of ${plural(it.pages, "page")} · ${size}`;
  else meta.textContent = `${plural(it.pages, "page")} · ${size}`;
  range.classList.toggle("invalid", !!it.rangeError);
  li.classList.toggle("range-error", !!it.rangeError);
}

function renderList() {
  // move only the rows that are out of place, so focus and scroll position survive
  state.items.forEach((it, i) => {
    const current = el.list.children[i];
    if (current !== it.el) el.list.insertBefore(it.el, current || null);
    $(".idx", it.el).textContent = i + 1;
  });
  while (el.list.children.length > state.items.length) el.list.lastElementChild.remove();
  const has = state.items.length > 0;
  el.empty.hidden = has;
  el.listHead.hidden = el.hint.hidden = !has;
  el.sortBtn.disabled = el.clearBtn.disabled = !has;
  updateSummary();
}

/* Coalesce frequent updates (upload progress) into one paint per frame. */
const dirty = new Set();
let frame = 0;
function scheduleUpdate(it) {
  dirty.add(it);
  frame ||= requestAnimationFrame(() => {
    frame = 0;
    dirty.forEach(updateRow);
    dirty.clear();
    updateSummary();
  });
}

/* ---------- summary / merge button ---------- */
function updateSummary() {
  const items = state.items;
  let pages = 0, bytes = 0, loaded = 0, pending = 0, errors = 0, firstBadRange = -1;
  items.forEach((it, i) => {
    bytes += it.size;
    if (it.status === "ready") {
      loaded += it.size;
      if (it.rangeError) { if (firstBadRange < 0) firstBadRange = i; }
      else pages += it.rangeCount ?? it.pages;
    } else if (it.status === "error") { errors++; loaded += it.size; }
    else { pending++; loaded += it.loaded || 0; }
  });
  el.statFiles.textContent = fmtInt(items.length);
  el.statPages.textContent = fmtInt(pages);
  el.statSize.textContent = items.length ? fmtBytes(bytes) : "0 MB";

  let note = "", warn = false;
  if (!items.length) note = "Add PDFs to get started";
  else if (pending) note = `Preparing ${plural(pending, "file")}…`;
  else if (errors) { note = `Remove ${plural(errors, "file")} that can't be used`; warn = true; }
  else if (firstBadRange >= 0) { note = `Fix the page range on file ${firstBadRange + 1}`; warn = true; }
  else note = `${plural(pages, "page")} from ${plural(items.length, "file")}`;
  if (state.merging) { note = "Merging — this can take a moment for large books"; warn = false; }
  el.mergeNote.textContent = note;
  el.mergeNote.classList.toggle("warn", warn);
  el.mergeLabel.textContent = state.merging ? "Merging…" : items.length ? `Merge ${plural(items.length, "PDF")}` : "Merge PDFs";
  el.mergeBtn.disabled = state.merging || !items.length || pending > 0 || errors > 0 || firstBadRange >= 0;

  if (!state.merging) {
    el.progress.hidden = pending === 0;
    if (pending) {
      const pct = bytes ? Math.floor((loaded / bytes) * 100) : 0;
      $(".bar", el.progress).classList.remove("indeterminate");
      el.progressFill.style.width = `${pct}%`;
      el.progressLabel.textContent = `Preparing ${fmtInt(items.length - pending)} of ${plural(items.length, "file")}`;
      el.progressValue.textContent = `${pct}%`;
    }
  }
}

/* ---------- adding files ---------- */
function addFiles(entries) {
  const pdfs = entries.filter(e => /\.pdf$/i.test(e.file.name));
  const skipped = entries.length - pdfs.length;
  if (!pdfs.length) {
    if (skipped) toast(`No PDFs found among ${plural(skipped, "file")}`, "error");
    return;
  }
  // a multi-file pick or drop arrives in no reliable order, so each batch is sorted by path (2 before 10)
  pdfs.sort((a, b) => collator.compare(a.path, b.path));
  for (const { file, path } of pdfs) {
    const it = {
      key: ++state.seq, file, path, name: file.name, size: file.size, modified: file.lastModified,
      status: "queued", loaded: 0, id: null, pages: 0, range: "", rangeCount: null, rangeError: null,
    };
    createRow(it);
    updateRow(it);
    state.items.push(it);
  }
  renderList();
  pump();
  toast(`Added ${plural(pdfs.length, "PDF")}` + (skipped ? ` · skipped ${plural(skipped, "non-PDF file")}` : ""));
}

function pump() {
  while (state.uploading < PARALLEL_UPLOADS) {
    const it = state.items.find(i => i.status === "queued");
    if (!it) return;
    upload(it);
  }
}

function upload(it) {
  state.uploading++;
  it.status = "uploading";
  const xhr = new XMLHttpRequest();
  it.xhr = xhr;
  xhr.open("POST", "/api/upload?name=" + encodeURIComponent(it.name));
  xhr.upload.onprogress = e => { it.loaded = e.loaded; scheduleUpdate(it); };
  xhr.onload = () => {
    let res = {};
    try { res = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status === 200) {
      Object.assign(it, { id: res.id, pages: res.pages, status: "ready" });
      validateRange(it);
    } else {
      Object.assign(it, { status: "error", error: res.error || "Couldn't read this file" });
    }
  };
  xhr.onerror = () => Object.assign(it, { status: "error", error: "Couldn't reach Folio — is it still running?" });
  xhr.onloadend = () => {
    state.uploading--;
    it.xhr = null;
    if (it.removed && it.id) discard([it.id]);
    if (!it.removed) scheduleUpdate(it);
    pump();
    updateSummary();
  };
  xhr.send(it.file);
  scheduleUpdate(it);
}

function discard(ids) {
  if (ids.length) fetch("/api/discard", { method: "POST", body: JSON.stringify(ids) }).catch(() => {});
}

function validateRange(it) {
  try {
    it.rangeCount = countRange(it.range, it.pages);
    it.rangeError = null;
  } catch (e) {
    it.rangeCount = null;
    it.rangeError = e.message;
  }
}

/* Drag-and-drop of files *and folders* from the desktop. */
async function entriesFromDrop(dt) {
  const roots = [...dt.items].map(i => i.webkitGetAsEntry?.()).filter(Boolean);  // must be read synchronously
  if (!roots.length) return [...dt.files].map(file => ({ file, path: file.name }));
  const out = [];
  async function walk(entry, prefix) {
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej));
      out.push({ file, path: prefix + file.name });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      for (;;) {
        const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const child of batch) await walk(child, `${prefix}${entry.name}/`);
      }
    }
  }
  for (const root of roots) await walk(root, "");
  return out;
}

let dragDepth = 0;
const isFileDrag = e => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
window.addEventListener("dragenter", e => {
  if (!isFileDrag(e)) return;
  e.preventDefault();
  if (dragDepth++ === 0) el.dropOverlay.hidden = false;
});
window.addEventListener("dragover", e => { if (isFileDrag(e)) e.preventDefault(); });
window.addEventListener("dragleave", e => {
  if (!isFileDrag(e)) return;
  if (--dragDepth <= 0) { dragDepth = 0; el.dropOverlay.hidden = true; }
});
window.addEventListener("drop", async e => {
  if (!isFileDrag(e)) return;
  e.preventDefault();
  dragDepth = 0;
  el.dropOverlay.hidden = true;
  addFiles(await entriesFromDrop(e.dataTransfer));
});

const pickFiles = () => el.filePicker.click();
const pickFolder = () => el.folderPicker.click();
$("#addFilesBtn").onclick = $("#browseBtn").onclick = pickFiles;
$("#addFolderBtn").onclick = $("#browseFolderBtn").onclick = pickFolder;
el.filePicker.onchange = e => { addFiles([...e.target.files].map(file => ({ file, path: file.name }))); e.target.value = ""; };
el.folderPicker.onchange = e => {
  addFiles([...e.target.files].map(file => ({ file, path: file.webkitRelativePath || file.name })));
  e.target.value = "";
};

/* ---------- editing the list ---------- */
function removeItems(items) {
  const gone = new Set(items);
  for (const it of items) {
    it.removed = true;
    it.xhr?.abort();
  }
  discard(items.filter(i => i.id && !i.xhr).map(i => i.id));
  state.items = state.items.filter(i => !gone.has(i));
  renderList();
  pump();
}

function moveItem(it, to) {
  const from = state.items.indexOf(it);
  to = Math.max(0, Math.min(state.items.length - 1, to));
  if (from === to) return;
  state.items.splice(from, 1);
  state.items.splice(to, 0, it);
  renderList();
}

el.list.addEventListener("click", e => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const it = itemOf(btn);
  if (btn.dataset.act === "remove") removeItems([it]);
  if (btn.dataset.act === "top") { moveItem(it, 0); it.el.focus(); it.el.scrollIntoView({ block: "nearest" }); }
});

el.list.addEventListener("input", e => {
  if (!e.target.classList.contains("range")) return;
  const it = itemOf(e.target);
  it.range = e.target.value;
  validateRange(it);
  updateRow(it);
  updateSummary();
});

el.list.addEventListener("keydown", e => {
  const row = e.target.closest(".row");
  if (!row || e.target !== row) return;  // typing in the range box is left alone
  const it = itemOf(row), i = state.items.indexOf(it);
  const focus = j => state.items[Math.max(0, Math.min(state.items.length - 1, j))]?.el.focus();
  if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
    moveItem(it, i + (e.key === "ArrowUp" ? -1 : 1));
    it.el.focus();
  } else if (e.altKey && (e.key === "Home" || e.key === "End")) {
    moveItem(it, e.key === "Home" ? 0 : state.items.length - 1);
    it.el.focus();
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") focus(i + (e.key === "ArrowUp" ? -1 : 1));
  else if (e.key === "Home" || e.key === "End") focus(e.key === "Home" ? 0 : state.items.length - 1);
  else if (e.key === "Delete" || e.key === "Backspace") { removeItems([it]); focus(i); }
  else return;
  e.preventDefault();
});

const itemOf = node => {
  const key = +node.closest(".row").dataset.key;
  return state.items.find(i => i.key === key);
};

/* Pointer-based reordering: smooth, works with mouse, pen and touch, and auto-scrolls long lists. */
let drag = null;
el.list.addEventListener("pointerdown", e => {
  const handle = e.target.closest(".handle");
  if (!handle || e.button !== 0) return;
  e.preventDefault();
  const row = handle.closest(".row"), rect = row.getBoundingClientRect();
  const ph = document.createElement("li");
  ph.className = "placeholder";
  ph.style.height = `${rect.height}px`;
  row.after(ph);
  Object.assign(row.style, { width: `${rect.width}px`, left: `${rect.left}px`, top: `${rect.top}px` });
  row.classList.add("dragging");
  document.body.classList.add("reordering");
  handle.setPointerCapture(e.pointerId);
  drag = { row, ph, handle, offset: e.clientY - rect.top, y: e.clientY, raf: requestAnimationFrame(autoScroll) };
});

function placePlaceholder() {
  const { row, ph, y, offset } = drag;
  row.style.top = `${y - offset}px`;
  let before = null;
  for (const r of el.list.children) {
    if (r === row || r === ph) continue;
    const b = r.getBoundingClientRect();
    if (y < b.top + b.height / 2) { before = r; break; }
  }
  if (before) { if (ph.nextSibling !== before) el.list.insertBefore(ph, before); }
  else if (el.list.lastElementChild !== ph) el.list.appendChild(ph);
}

function autoScroll() {
  if (!drag) return;
  const edge = 90, y = drag.y, h = window.innerHeight;
  const speed = y < edge ? -(edge - y) / 4 : y > h - edge ? (y - (h - edge)) / 4 : 0;
  if (speed) { window.scrollBy(0, speed); placePlaceholder(); }
  drag.raf = requestAnimationFrame(autoScroll);
}

el.list.addEventListener("pointermove", e => {
  if (!drag) return;
  drag.y = e.clientY;
  placePlaceholder();
});

function endDrag() {
  if (!drag) return;
  const { row, ph, raf } = drag;
  cancelAnimationFrame(raf);
  ph.replaceWith(row);
  row.classList.remove("dragging");
  row.removeAttribute("style");
  document.body.classList.remove("reordering");
  drag = null;
  const order = [...el.list.children].map(r => +r.dataset.key);
  const byKey = new Map(state.items.map(i => [i.key, i]));
  state.items = order.map(k => byKey.get(k));
  renderList();
  row.focus({ preventScroll: true });
}
el.list.addEventListener("pointerup", endDrag);
el.list.addEventListener("pointercancel", endDrag);

/* ---------- sort / clear ---------- */
const sorters = {
  "name": (a, b) => collator.compare(a.path, b.path),
  "name-desc": (a, b) => collator.compare(b.path, a.path),
  "modified": (a, b) => a.modified - b.modified || collator.compare(a.path, b.path),
  "modified-desc": (a, b) => b.modified - a.modified || collator.compare(a.path, b.path),
  "size-desc": (a, b) => b.size - a.size,
};
function toggleMenu(open = el.sortMenu.hidden) {
  el.sortMenu.hidden = !open;
  el.sortBtn.setAttribute("aria-expanded", open);
  if (open) $("button", el.sortMenu).focus();
}
el.sortBtn.onclick = e => { e.stopPropagation(); toggleMenu(); };
el.sortMenu.onclick = e => {
  const kind = e.target.closest("[data-sort]")?.dataset.sort;
  if (!kind) return;
  if (kind === "reverse") state.items.reverse();
  else state.items.sort(sorters[kind]);
  toggleMenu(false);
  renderList();
};
document.addEventListener("click", e => { if (!e.target.closest(".menu")) toggleMenu(false); });
el.sortMenu.addEventListener("keydown", e => {
  const btns = [...el.sortMenu.querySelectorAll("button")], i = btns.indexOf(document.activeElement);
  if (e.key === "Escape") { toggleMenu(false); el.sortBtn.focus(); }
  else if (e.key === "ArrowDown") btns[(i + 1) % btns.length].focus();
  else if (e.key === "ArrowUp") btns[(i - 1 + btns.length) % btns.length].focus();
  else return;
  e.preventDefault();
});

el.clearBtn.onclick = () => {
  const cleared = state.items;
  const inflight = cleared.filter(i => i.status === "queued" || i.status === "uploading");
  // keep finished files on the server for a few seconds so Undo can bring them back instantly
  removeItems(inflight);
  const kept = cleared.filter(i => !inflight.includes(i));
  state.items = [];
  renderList();
  let undone = false;
  toast(`Cleared ${plural(cleared.length, "file")}`, "info", {
    action: kept.length ? "Undo" : null,
    onAction: () => { undone = true; state.items = [...kept, ...state.items]; renderList(); },
    onClose: () => { if (!undone) discard(kept.filter(i => i.id).map(i => i.id)); },
  });
};

/* ---------- merge ---------- */
let mergeTimer = 0;
el.mergeBtn.onclick = async () => {
  if (el.mergeBtn.disabled) return;
  state.merging = true;
  el.result.hidden = true;
  const pages = el.statPages.textContent, started = performance.now();
  el.progress.hidden = false;
  $(".bar", el.progress).classList.add("indeterminate");
  el.progressLabel.textContent = `Merging ${pages} pages`;
  const tick = () => { el.progressValue.textContent = fmtSecs((performance.now() - started) / 1000); };
  tick();
  mergeTimer = setInterval(tick, 200);
  updateSummary();
  try {
    const res = await fetch("/api/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: el.outName.value,
        bookmarks: el.bookmarks.checked,
        items: state.items.map(i => ({ id: i.id, range: i.range })),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "The merge failed");
    showResult(data);
    toast(`Merged ${plural(state.items.length, "file")} into ${data.name}`, "success");
  } catch (e) {
    toast(e.message === "Failed to fetch" ? "Couldn't reach Folio — is it still running?" : e.message, "error");
  } finally {
    clearInterval(mergeTimer);
    state.merging = false;
    el.progress.hidden = true;
    $(".bar", el.progress).classList.remove("indeterminate");
    updateSummary();
  }
};

function showResult(r) {
  el.resultName.textContent = r.name;
  el.resultMeta.innerHTML = "";
  for (const [k, v] of [["Pages", fmtInt(r.pages)], ["Files", fmtInt(state.items.length)], ["Size", fmtBytes(r.size)], ["Time", fmtSecs(r.seconds)]]) {
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = k;
    dd.textContent = v;
    el.resultMeta.append(dt, dd);
  }
  el.downloadBtn.href = `/api/file/${r.id}?download=1`;
  el.downloadBtn.setAttribute("download", r.name);
  el.previewBtn.href = `/api/file/${r.id}`;
  el.result.hidden = false;
  el.result.style.animation = "none";
  void el.result.offsetWidth;  // restart the entrance animation
  el.result.style.animation = "";
}

/* ---------- toasts ---------- */
function toast(message, kind = "info", { action = null, onAction = null, onClose = null } = {}) {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.setAttribute("role", kind === "error" ? "alert" : "status");
  t.innerHTML = '<span class="dot"></span><p></p>';
  $("p", t).textContent = message;
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    onClose?.();
    t.classList.add("out");
    setTimeout(() => t.remove(), 200);
  };
  if (action) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = action;
    b.onclick = () => { onAction?.(); close(); };
    t.appendChild(b);
  }
  el.toasts.appendChild(t);
  while (el.toasts.children.length > 3) el.toasts.firstElementChild.remove();
  setTimeout(close, kind === "error" ? 7000 : action ? 6000 : 3200);
}

/* ---------- theme, shortcuts, lifecycle ---------- */
$("#themeBtn").onclick = () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("folio-theme", next); } catch {}
};

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") { e.preventDefault(); pickFiles(); }
});

const showClosed = () => { el.closed.hidden = false; };
$("#quitBtn").onclick = async () => {
  if (state.items.length && !confirm("Quit Folio? Your file list will be cleared.")) return;
  await fetch("/api/quit", { method: "POST" }).catch(() => {});
  showClosed();
};

// heartbeat: the server closes itself once this window is gone
let misses = 0;
async function ping() {
  try {
    const r = await fetch("/api/ping", { method: "POST" });
    misses = r.ok ? 0 : misses + 1;
  } catch { misses++; }
  if (misses >= 2 && !state.merging) showClosed();
}
ping();
setInterval(ping, 20000);
window.addEventListener("pagehide", () => navigator.sendBeacon("/api/bye"));
window.addEventListener("beforeunload", e => {
  if (state.merging || state.uploading) { e.preventDefault(); e.returnValue = ""; }
});

renderList();
