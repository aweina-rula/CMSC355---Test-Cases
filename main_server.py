from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from threading import Timer, Lock
from datetime import datetime
from pathlib import Path
import json
import os
import time
import uuid
import webbrowser

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DATA_FILE = BASE_DIR / "reports.json"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # Hard server-side limit: 10 MiB

DATA_LOCK = Lock()
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VALID_HAZARDS = {
    "Pothole",
    "Flooding",
    "Debris",
    "Broken Traffic Light",
    "Damaged Sidewalk",
    "Downed Tree",
    "Other",
}


def ensure_data_file():
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")


def load_reports():
    ensure_data_file()
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        app.logger.exception("Could not read reports.json")
        return []


def save_reports(reports):
    temp_file = DATA_FILE.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(reports, file, indent=2, ensure_ascii=False)
    temp_file.replace(DATA_FILE)


def is_allowed_image(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def image_signature_is_valid(data):
    """Check common image file signatures without requiring an extra package."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


HTML_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#102a43">
  <title>RVA SafeRoute | Hazard Reporting</title>
  <style>
    :root {
      color-scheme: light;
      --navy: #102a43;
      --navy-2: #243b53;
      --teal: #0f766e;
      --teal-dark: #115e59;
      --ink: #172b4d;
      --muted: #627d98;
      --line: #d9e2ec;
      --surface: #ffffff;
      --page: #f3f7fa;
      --danger: #b42318;
      --danger-bg: #fff1f0;
      --success: #067647;
      --success-bg: #ecfdf3;
      --warning: #92400e;
      --warning-bg: #fffaeb;
      --shadow: 0 12px 32px rgba(16, 42, 67, .08);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--page); color: var(--ink); line-height: 1.5; }
    button, input, select, textarea { font: inherit; }
    button { cursor: pointer; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
      outline: 3px solid #7dd3fc; outline-offset: 2px;
    }
    .topbar { background: linear-gradient(120deg, var(--navy), #155e75); color: white; }
    .topbar-inner { width: min(1160px, calc(100% - 36px)); margin: auto; padding: 22px 0; display: flex; align-items: center; justify-content: space-between; gap: 18px; }
    .brand { display: flex; gap: 13px; align-items: center; }
    .brand-mark { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; background: rgba(255,255,255,.13); font-size: 25px; }
    .brand h1 { margin: 0; font-size: clamp(1.2rem, 3vw, 1.65rem); letter-spacing: -.03em; }
    .brand p { margin: 3px 0 0; color: #d9f2f2; font-size: .88rem; }
    .prototype-pill { border: 1px solid rgba(255,255,255,.35); border-radius: 999px; padding: 7px 12px; font-size: .78rem; white-space: nowrap; }
    main { width: min(1160px, calc(100% - 36px)); margin: 28px auto 48px; }
    .intro { margin-bottom: 22px; }
    .eyebrow { color: var(--teal); font-size: .76rem; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; }
    .intro h2 { margin: 5px 0 7px; font-size: clamp(1.65rem, 4vw, 2.2rem); letter-spacing: -.045em; }
    .intro p { color: var(--muted); max-width: 720px; margin: 0; }
    .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }
    .stat { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 17px 19px; box-shadow: var(--shadow); }
    .stat-label { color: var(--muted); font-size: .82rem; font-weight: 650; }
    .stat-value { display: block; margin-top: 3px; font-size: 1.8rem; line-height: 1.2; font-weight: 800; letter-spacing: -.04em; }
    .layout { display: grid; grid-template-columns: minmax(0, .92fr) minmax(0, 1.08fr); gap: 20px; align-items: start; }
    .panel { background: var(--surface); border: 1px solid var(--line); border-radius: 18px; box-shadow: var(--shadow); overflow: hidden; }
    .panel-head { padding: 20px 22px 16px; border-bottom: 1px solid var(--line); }
    .panel-head h3 { margin: 0; font-size: 1.13rem; }
    .panel-head p { margin: 5px 0 0; color: var(--muted); font-size: .88rem; }
    .panel-body { padding: 22px; }
    .field { margin-bottom: 17px; }
    label, .field-label { display: block; font-weight: 750; font-size: .88rem; margin-bottom: 7px; }
    .optional { color: var(--muted); font-weight: 500; }
    input, select { width: 100%; min-height: 45px; padding: 10px 12px; border: 1px solid #bcccdc; border-radius: 10px; background: white; color: var(--ink); }
    input[readonly] { background: #f0f4f8; color: var(--muted); }
    input[type=file] { padding: 9px; background: #f8fafc; }
    .hint { color: var(--muted); display: block; margin-top: 6px; font-size: .78rem; }
    .file-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border-radius: 10px; background: #f0fdfa; color: var(--teal-dark); font-size: .83rem; }
    .file-meta.invalid { background: var(--danger-bg); color: var(--danger); }
    .btn { border: 0; border-radius: 10px; min-height: 43px; padding: 10px 15px; font-weight: 750; transition: transform .15s, background .15s; }
    .btn:hover { transform: translateY(-1px); }
    .btn-primary { color: white; background: var(--teal); }
    .btn-primary:hover { background: var(--teal-dark); }
    .btn-secondary { color: var(--navy); background: #eaf0f6; }
    .btn-secondary:hover { background: #d9e2ec; }
    .btn-submit { width: 100%; min-height: 49px; font-size: .97rem; margin-top: 3px; }
    .feedback { display: none; padding: 13px 15px; border-radius: 11px; margin-top: 16px; font-size: .9rem; }
    .feedback.success { display: block; background: var(--success-bg); border: 1px solid #abefc6; color: var(--success); }
    .feedback.error { display: block; background: var(--danger-bg); border: 1px solid #fecdca; color: var(--danger); }
    .feedback.info { display: block; background: #eff8ff; border: 1px solid #b2ddff; color: #175cd3; }
    .test-area { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 17px; }
    .test-area h4 { margin: 0 0 5px; font-size: .95rem; }
    .test-area p { margin: 0 0 12px; color: var(--muted); font-size: .81rem; }
    .test-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .test-btn { text-align: left; padding: 10px 11px; border: 1px solid var(--line); background: #fff; border-radius: 10px; color: var(--ink); font-size: .79rem; font-weight: 750; }
    .test-btn:hover { border-color: var(--teal); background: #f0fdfa; }
    .test-result { display: none; margin-top: 12px; padding: 12px; border-radius: 10px; font-size: .84rem; }
    .feed-tools { display: flex; gap: 9px; margin-bottom: 14px; }
    .feed-tools input { flex: 1; min-width: 0; }
    .feed-tools select { width: 155px; }
    .feed-summary { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin: 0 0 13px; color: var(--muted); font-size: .82rem; }
    .report-list { display: grid; gap: 12px; }
    .report-card { display: grid; grid-template-columns: 94px minmax(0, 1fr); gap: 14px; border: 1px solid var(--line); border-radius: 14px; padding: 12px; min-width: 0; }
    .report-image { width: 94px; height: 94px; object-fit: cover; border-radius: 10px; background: #eaf0f6; cursor: zoom-in; }
    .report-placeholder { width: 94px; height: 94px; border-radius: 10px; display: grid; place-items: center; text-align: center; color: var(--muted); background: #f0f4f8; font-size: .72rem; padding: 7px; }
    .report-topline { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
    .report-title { font-weight: 800; overflow-wrap: anywhere; }
    .badge { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 8px; font-size: .71rem; font-weight: 800; background: #eaf0f6; color: var(--navy-2); }
    .severity-high { background: #fee4e2; color: #b42318; }
    .severity-medium { background: #fef0c7; color: #93370d; }
    .severity-low { background: #dcfae6; color: #067647; }
    .report-meta { color: var(--muted); font-size: .79rem; margin-top: 6px; overflow-wrap: anywhere; }
    .report-desc { margin-top: 7px; font-size: .85rem; overflow-wrap: anywhere; }
    .empty { padding: 32px 16px; text-align: center; border: 1px dashed #bcccdc; border-radius: 13px; color: var(--muted); }
    .empty strong { display: block; color: var(--ink); margin-bottom: 4px; }
    .footer-note { margin: 18px 2px 0; color: var(--muted); font-size: .78rem; }
    .modal { display: none; position: fixed; inset: 0; z-index: 10; padding: 24px; background: rgba(10, 25, 41, .88); align-items: center; justify-content: center; }
    .modal.open { display: flex; }
    .modal img { max-width: min(100%, 1100px); max-height: 85vh; object-fit: contain; border-radius: 12px; }
    .modal-close { position: absolute; top: 18px; right: 20px; width: 42px; height: 42px; border: 0; border-radius: 50%; background: white; color: var(--navy); font-size: 1.6rem; }
    @media (max-width: 850px) { .layout { grid-template-columns: 1fr; } }
    @media (max-width: 560px) {
      .topbar-inner, main { width: min(100% - 24px, 1160px); }
      .topbar-inner { align-items: flex-start; }
      .prototype-pill { display: none; }
      main { margin-top: 20px; }
      .stats { gap: 8px; }
      .stat { padding: 13px 12px; }
      .stat-value { font-size: 1.5rem; }
      .panel-body { padding: 16px; }
      .panel-head { padding: 17px 16px 14px; }
      .feed-tools { flex-direction: column; }
      .feed-tools select { width: 100%; }
      .report-card { grid-template-columns: 76px minmax(0, 1fr); gap: 10px; padding: 9px; }
      .report-image, .report-placeholder { width: 76px; height: 76px; }
      .test-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">🛟</div>
        <div>
          <h1>RVA SafeRoute</h1>
          <p>Community hazard reporting</p>
        </div>
      </div>
      <div class="prototype-pill">SPRINT 1 · CLASS PROJECT PROTOTYPE</div>
    </div>
  </header>

  <main>
    <section class="intro">
      <div class="eyebrow">Safer streets start with us</div>
      <h2>Report a hazard. Help your community.</h2>
      <p>Submit a road or sidewalk hazard so the community can see it. This class prototype stores reports locally; it is not connected to an official Department of Transportation system.</p>
    </section>

    <section class="stats" aria-label="Report statistics">
      <div class="stat"><span class="stat-label">Total reports</span><strong class="stat-value" id="totalCount">—</strong></div>
      <div class="stat"><span class="stat-label">High severity (4–5)</span><strong class="stat-value" id="highCount">—</strong></div>
      <div class="stat"><span class="stat-label">Reports with photos</span><strong class="stat-value" id="photoCount">—</strong></div>
    </section>

    <div class="layout">
      <section class="panel">
        <div class="panel-head">
          <h3>Submit a hazard report</h3>
          <p>Fields marked required must be completed before submission.</p>
        </div>
        <div class="panel-body">
          <form id="hazardForm" novalidate>
            <div class="field">
              <label for="hazardType">Hazard type <span aria-hidden="true">*</span></label>
              <select id="hazardType" name="hazardType" required>
                <option value="Pothole">Pothole</option>
                <option value="Flooding">Flooding</option>
                <option value="Debris">Debris</option>
                <option value="Broken Traffic Light">Broken traffic light</option>
                <option value="Damaged Sidewalk">Damaged sidewalk</option>
                <option value="Downed Tree">Downed tree</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div class="field">
              <label for="severityRating">Severity rating <span aria-hidden="true">*</span></label>
              <select id="severityRating" name="severity" required>
                <option value="">Select severity (1–5)</option>
                <option value="1">1 — Low</option>
                <option value="2">2 — Minor</option>
                <option value="3">3 — Moderate</option>
                <option value="4">4 — High</option>
                <option value="5">5 — Critical</option>
              </select>
              <small class="hint">Choose based on the hazard's potential impact on public safety.</small>
            </div>
            <div class="field">
              <label for="imageInput">Hazard photo <span aria-hidden="true">*</span></label>
              <input type="file" id="imageInput" name="image" accept=".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp" required>
              <small class="hint">PNG, JPG, GIF, or WEBP. Maximum file size: 10 MB.</small>
              <div class="file-meta" id="fileMeta" style="margin-top:9px">
                <span id="fileName">No photo selected</span><strong id="fileSize">—</strong>
              </div>
            </div>
            <div class="field">
              <label for="geolocation">Location <span class="optional">(prototype default)</span></label>
              <input type="text" id="geolocation" name="geolocation" value="37.5407° N, 77.4360° W" maxlength="120" required>
              <small class="hint">This is a preset Richmond location. Automatic GPS is not implemented in this prototype.</small>
            </div>
            <button class="btn btn-primary btn-submit" type="submit" id="submitButton">Submit hazard report <span aria-hidden="true">→</span></button>
          </form>

          <div id="feedbackBox" class="feedback" role="status" aria-live="polite"></div>

          <section class="test-area" aria-labelledby="testTitle">
            <h4 id="testTitle">Test case presets</h4>
            <p>Run the four validation scenarios for your software engineering demonstration. These presets do not create fake reports.</p>
            <div class="test-grid">
              <button class="test-btn" type="button" onclick="runTestCase(1)">TC-01 · Valid submission</button>
              <button class="test-btn" type="button" onclick="runTestCase(2)">TC-02 · Missing fields</button>
              <button class="test-btn" type="button" onclick="runTestCase(3)">TC-03 · Invalid severity (6)</button>
              <button class="test-btn" type="button" onclick="runTestCase(4)">TC-04 · File exceeds 10 MB</button>
            </div>
            <div id="testResult" class="test-result" role="status" aria-live="polite"></div>
          </section>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h3>Community hazard feed</h3>
          <p>Browse submitted reports saved by this prototype.</p>
        </div>
        <div class="panel-body">
          <div class="feed-tools">
            <input type="search" id="searchInput" placeholder="Search hazard or location…" aria-label="Search reports">
            <select id="severityFilter" aria-label="Filter by severity">
              <option value="all">All severities</option>
              <option value="high">High / critical (4–5)</option>
              <option value="medium">Moderate (3)</option>
              <option value="low">Low / minor (1–2)</option>
            </select>
          </div>
          <div class="feed-summary"><span id="feedCount">Loading reports…</span><button type="button" class="btn btn-secondary" id="refreshButton">Refresh</button></div>
          <div id="newsfeed" class="report-list"><div class="empty">Loading reports…</div></div>
          <p class="footer-note">Demo data is stored in <code>reports.json</code> in the app directory. Keep this prototype on a trusted local machine; it has no user accounts or moderation workflow.</p>
        </div>
      </section>
    </div>
  </main>

  <div class="modal" id="imageModal" role="dialog" aria-modal="true" aria-label="Expanded hazard photo" onclick="closeModal()">
    <button class="modal-close" type="button" aria-label="Close image" onclick="closeModal()">×</button>
    <img id="modalImage" alt="Expanded hazard photo" onclick="event.stopPropagation()">
  </div>

<script>
  const form = document.getElementById('hazardForm');
  const feedback = document.getElementById('feedbackBox');
  const imageInput = document.getElementById('imageInput');
  const fileMeta = document.getElementById('fileMeta');
  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  let reportsCache = [];

  function showFeedback(message, kind) {
    feedback.className = 'feedback ' + kind;
    feedback.textContent = message;
  }

  function clearFeedback() {
    feedback.className = 'feedback';
    feedback.textContent = '';
  }

  function updateFileMeta() {
    const file = imageInput.files && imageInput.files[0];
    const name = document.getElementById('fileName');
    const size = document.getElementById('fileSize');
    if (!file) {
      name.textContent = 'No photo selected';
      size.textContent = '—';
      fileMeta.classList.remove('invalid');
      return;
    }
    name.textContent = file.name;
    size.textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
    fileMeta.classList.toggle('invalid', file.size > MAX_FILE_SIZE);
  }

  imageInput.addEventListener('change', updateFileMeta);
  document.getElementById('refreshButton').addEventListener('click', fetchReports);
  document.getElementById('searchInput').addEventListener('input', renderReports);
  document.getElementById('severityFilter').addEventListener('change', renderReports);

  function runTestCase(number) {
    const result = document.getElementById('testResult');
    result.style.display = 'block';
    result.style.background = '#eff8ff';
    result.style.color = '#175cd3';
    result.style.border = '1px solid #b2ddff';

    if (number === 1) {
      document.getElementById('hazardType').value = 'Pothole';
      document.getElementById('severityRating').value = '3';
      result.textContent = 'TC-01 · READY: Valid hazard type and severity are set. Select a real image, then submit to test a complete server-validated report.';
    } else if (number === 2) {
      document.getElementById('severityRating').value = '';
      imageInput.value = '';
      updateFileMeta();
      result.style.background = '#fff1f0';
      result.style.color = '#b42318';
      result.style.border = '1px solid #fecdca';
      result.textContent = 'TC-02 · EXPECTED REJECTION: Severity and image are missing. Submitting now should be blocked by browser validation; the server also checks required fields.';
    } else if (number === 3) {
      document.getElementById('severityRating').value = '6';
      result.style.background = '#fff1f0';
      result.style.color = '#b42318';
      result.style.border = '1px solid #fecdca';
      result.textContent = 'TC-03 · EXPECTED REJECTION: Severity 6 is outside the permitted 1–5 range. The server independently validates the submitted value.';
    } else if (number === 4) {
      result.style.background = '#fffaeb';
      result.style.color = '#92400e';
      result.style.border = '1px solid #fedf89';
      result.textContent = 'TC-04 · SIZE-LIMIT SCENARIO: Choose a real image larger than 10 MB to verify rejection. For safety, this preset does not create or upload a large test file. Flask also enforces a 10 MB request limit.';
    }
  }

  form.addEventListener('submit', async function(event) {
    event.preventDefault();
    clearFeedback();

    const file = imageInput.files && imageInput.files[0];
    const severity = Number(document.getElementById('severityRating').value);
    if (!document.getElementById('severityRating').value) {
      showFeedback('Please select a severity rating from 1 to 5.', 'error');
      return;
    }
    if (!Number.isInteger(severity) || severity < 1 || severity > 5) {
      showFeedback('Severity must be a whole number between 1 and 5.', 'error');
      return;
    }
    if (!file) {
      showFeedback('Please select a hazard photo before submitting.', 'error');
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      showFeedback('The selected photo exceeds the 10 MB upload limit.', 'error');
      return;
    }
    if (!document.getElementById('geolocation').value.trim()) {
      showFeedback('Please provide a location.', 'error');
      return;
    }

    const button = document.getElementById('submitButton');
    button.disabled = true;
    button.textContent = 'Submitting…';
    const formData = new FormData();
    formData.append('hazardType', document.getElementById('hazardType').value);
    formData.append('severity', String(severity));
    formData.append('geolocation', document.getElementById('geolocation').value.trim());
    formData.append('image', file);

    try {
      const response = await fetch('/api/reports', { method: 'POST', body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'The server could not save this report.');
      showFeedback('Report submitted successfully and added to the local community feed. No external DOT system was contacted.', 'success');
      form.reset();
      updateFileMeta();
      await fetchReports();
    } catch (error) {
      showFeedback(error.message || 'An error occurred while submitting the report.', 'error');
    } finally {
      button.disabled = false;
      button.innerHTML = 'Submit hazard report <span aria-hidden="true">→</span>';
    }
  });

  function severityClass(value) {
    if (value >= 4) return 'severity-high';
    if (value === 3) return 'severity-medium';
    return 'severity-low';
  }

  function makeText(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text == null ? '' : String(text);
    return element;
  }

  function createReportElement(report) {
    const card = document.createElement('article');
    card.className = 'report-card';

    if (report.imageUrl) {
      const image = document.createElement('img');
      image.className = 'report-image';
      image.src = report.imageUrl;
      image.alt = 'Photo for ' + report.hazardType + ' report';
      image.loading = 'lazy';
      image.addEventListener('click', () => openModal(report.imageUrl));
      card.appendChild(image);
    } else {
      card.appendChild(makeText('div', 'report-placeholder', 'No photo available'));
    }

    const details = document.createElement('div');
    const top = document.createElement('div');
    top.className = 'report-topline';
    top.appendChild(makeText('span', 'report-title', report.hazardType || 'Unknown hazard'));
    const severity = Number(report.severity);
    top.appendChild(makeText('span', 'badge ' + severityClass(severity), 'Severity ' + severity + '/5'));
    details.appendChild(top);
    details.appendChild(makeText('div', 'report-meta', (report.timestamp || 'Time unavailable') + ' · ' + (report.fileSize || '—') + ' MB'));
    details.appendChild(makeText('div', 'report-meta', 'Location: ' + (report.geolocation || 'Not provided')));
    if (report.description) details.appendChild(makeText('div', 'report-desc', report.description));
    card.appendChild(details);
    return card;
  }

  function renderReports() {
    const list = document.getElementById('newsfeed');
    const search = document.getElementById('searchInput').value.trim().toLowerCase();
    const filter = document.getElementById('severityFilter').value;
    const filtered = reportsCache.filter(report => {
      const severity = Number(report.severity);
      const matchesSearch = [report.hazardType, report.geolocation, report.timestamp]
        .some(value => String(value || '').toLowerCase().includes(search));
      const matchesSeverity = filter === 'all' ||
        (filter === 'high' && severity >= 4) ||
        (filter === 'medium' && severity === 3) ||
        (filter === 'low' && severity <= 2);
      return matchesSearch && matchesSeverity;
    });

    list.replaceChildren();
    document.getElementById('feedCount').textContent =
      filtered.length + ' shown · ' + reportsCache.length + ' total';

    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.appendChild(makeText('strong', '', reportsCache.length ? 'No matching reports' : 'No hazards reported yet'));
      empty.appendChild(makeText('span', '', reportsCache.length ? 'Try changing your search or severity filter.' : 'Be the first to submit a community hazard report.'));
      list.appendChild(empty);
      return;
    }
    filtered.forEach(report => list.appendChild(createReportElement(report)));
  }

  async function fetchReports() {
    const list = document.getElementById('newsfeed');
    try {
      const response = await fetch('/api/reports', { cache: 'no-store' });
      if (!response.ok) throw new Error('Unable to load reports.');
      const reports = await response.json();
      reportsCache = Array.isArray(reports) ? reports : [];
      document.getElementById('totalCount').textContent = reportsCache.length;
      document.getElementById('highCount').textContent = reportsCache.filter(r => Number(r.severity) >= 4).length;
      document.getElementById('photoCount').textContent = reportsCache.filter(r => Boolean(r.imageUrl)).length;
      renderReports();
    } catch (error) {
      list.replaceChildren();
      list.appendChild(makeText('div', 'empty', 'Could not load reports. Check that the Flask server is running, then refresh.'));
      document.getElementById('feedCount').textContent = 'Feed unavailable';
      console.error(error);
    }
  }

  function openModal(imageSrc) {
    const modal = document.getElementById('imageModal');
    document.getElementById('modalImage').src = imageSrc;
    modal.classList.add('open');
  }

  function closeModal() {
    document.getElementById('imageModal').classList.remove('open');
    document.getElementById('modalImage').src = '';
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeModal();
  });

  updateFileMeta();
  fetchReports();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # Only serve a basename from the configured upload directory.
    safe_name = os.path.basename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name, max_age=3600)


@app.route("/api/reports", methods=["GET"])
def get_reports():
    with DATA_LOCK:
        reports = load_reports()
    return jsonify(reports)


@app.route("/api/reports", methods=["POST"])
def add_report():
    hazard_type = (request.form.get("hazardType") or "").strip()
    severity_raw = (request.form.get("severity") or "").strip()
    geolocation = (request.form.get("geolocation") or "").strip()
    uploaded = request.files.get("image")

    if hazard_type not in VALID_HAZARDS:
        return jsonify(error="Please choose a valid hazard type."), 400

    try:
        severity = int(severity_raw)
    except (TypeError, ValueError):
        return jsonify(error="Severity must be a whole number from 1 to 5."), 400
    if not 1 <= severity <= 5:
        return jsonify(error="Severity must be a whole number from 1 to 5."), 400

    if not geolocation or len(geolocation) > 120:
        return jsonify(error="A location of 1–120 characters is required."), 400

    if uploaded is None or not uploaded.filename:
        return jsonify(error="A hazard photo is required."), 400

    original_name = secure_filename(uploaded.filename)
    if not original_name or not is_allowed_image(original_name):
        return jsonify(error="Unsupported image format. Use PNG, JPG, GIF, or WEBP."), 400

    # Read at most one byte over the cap as a second check; Flask also enforces MAX_CONTENT_LENGTH.
    image_data = uploaded.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(image_data) > MAX_UPLOAD_BYTES:
        return jsonify(error="The image exceeds the 10 MB maximum upload size."), 413

    detected_extension = image_signature_is_valid(image_data)
    if not detected_extension:
        return jsonify(error="The uploaded file does not appear to be a supported image."), 400

    # Avoid saving a misleading extension when the signature differs from the filename.
    extension = detected_extension
    safe_filename = f"{uuid.uuid4().hex}{extension}"
    output_path = UPLOAD_FOLDER / safe_filename
    try:
        output_path.write_bytes(image_data)
    except OSError:
        app.logger.exception("Failed to save uploaded image")
        return jsonify(error="The server could not save the uploaded image."), 500

    timestamp = datetime.now().astimezone().strftime("%b %d, %Y · %I:%M %p")
    new_report = {
        "id": uuid.uuid4().hex,
        "hazardType": hazard_type,
        "severity": severity,
        "fileSize": round(len(image_data) / (1024 * 1024), 2),
        "geolocation": geolocation,
        "timestamp": timestamp,
        "imageUrl": f"/uploads/{safe_filename}",
    }

    try:
        with DATA_LOCK:
            reports = load_reports()
            reports.insert(0, new_report)
            save_reports(reports)
    except OSError:
        # Avoid leaving an orphaned image if report persistence fails.
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        app.logger.exception("Failed to save report data")
        return jsonify(error="The server could not save this report."), 500

    return jsonify(new_report), 201


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify(error="The upload request exceeds the 10 MB limit."), 413


@app.errorhandler(400)
def bad_request(_error):
    return jsonify(error="The request was invalid. Check the submitted fields and image."), 400


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")



if __name__ == "__main__":
    ensure_data_file()
    Timer(1.0, open_browser).start()

    # Local development only
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
