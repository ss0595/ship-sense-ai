const form = document.querySelector("#risk-form");
const loginScreen = document.querySelector("#login-screen");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginError = document.querySelector("#login-error");
const authTitle = document.querySelector("#auth-title");
const authModeButton = document.querySelector("#auth-mode-button");
const displayNameField = document.querySelector("#display-name-field");
const emailField = document.querySelector("#email-field");
const otpField = document.querySelector("#otp-field");
const otpInput = document.querySelector("#login-otp");
const otpDemoBox = document.querySelector("#otp-demo-box");
const loginNote = document.querySelector("#login-note");
const googleLoginButton = document.querySelector("#google-login-button");
const appShell = document.querySelector("#app-shell");
const modeSelect = document.querySelector("#transport_mode");
const vehicleSelect = document.querySelector("#vehicle_type");
const hubSelect = document.querySelector("#destination_hub");
const originSelect = document.querySelector("#origin");
const carrierSelect = document.querySelector("#carrier");
const analyzeButton = document.querySelector("#analyze-button");
const queueButton = document.querySelector("#queue-button");
const jobStatus = document.querySelector("#job-status");
const apiStatus = document.querySelector("#api-status");
const userBadge = document.querySelector("#user-badge");
const liveBadge = document.querySelector("#live-badge");
const logoutButton = document.querySelector("#logout-button");
const adminConsole = document.querySelector("#admin-console");
const adminSummary = document.querySelector("#admin-summary");
const rbacList = document.querySelector("#rbac-list");
const userDirectory = document.querySelector("#user-directory");
const auditEvents = document.querySelector("#audit-events");
const traceEvents = document.querySelector("#trace-events");
const stackStatus = document.querySelector("#stack-status");
const logLines = document.querySelector("#log-lines");
const refreshAdminButton = document.querySelector("#refresh-admin-button");
const adminAccountForm = document.querySelector("#admin-account-form");
const adminAccountMessage = document.querySelector("#admin-account-message");
let authMode = "login";
let mfaChallengeId = "";
let networkConfig = { modes: [] };
let currentUser = null;
let googleLoginPath = "/auth/google/start";
let currentPolicy = null;

const levelColors = {
  Low: "#0f9d74",
  Moderate: "#189aa8",
  Elevated: "#d6a21f",
  High: "#df4d5f",
  Critical: "#a51f34",
};

async function api(path, options = {}, retry = true) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401 && retry && !["/api/login", "/api/verify-mfa", "/api/refresh"].includes(path)) {
    const refresh = await fetch("/api/refresh", {
      method: "POST",
      body: "{}",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
    });
    if (refresh.ok) {
      return api(path, options, false);
    }
  }
  if (!response.ok) {
    const message = await response.text();
    let parsedMessage = message;
    try {
      const payload = JSON.parse(message);
      parsedMessage = payload.error || payload.message || message;
    } catch (error) {
      parsedMessage = message;
    }
    throw new Error(parsedMessage || `Request failed: ${response.status}`);
  }
  return response.json();
}

function prettyMode(mode) {
  return String(mode || "").replace(/^\w/, (char) => char.toUpperCase());
}

function capitalize(text) {
  const value = String(text || "");
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

function setSelectOptions(select, placeholder, options, labelFrom = (item) => item, valueFrom = (item) => item) {
  select.innerHTML = "";
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = placeholder;
  defaultOption.disabled = true;
  defaultOption.selected = true;
  select.appendChild(defaultOption);
  options.forEach((item) => {
    const option = document.createElement("option");
    option.value = valueFrom(item);
    option.textContent = labelFrom(item);
    select.appendChild(option);
  });
}

function disableDependentSelects() {
  setSelectOptions(vehicleSelect, "Select vehicle type", []);
  setSelectOptions(hubSelect, "Select destination hub", []);
  setSelectOptions(originSelect, "Select origin hub", []);
  setSelectOptions(carrierSelect, "Select carrier or operator", []);
  [vehicleSelect, hubSelect, originSelect, carrierSelect].forEach((select) => {
    select.disabled = true;
  });
}

function selectedModeConfig() {
  return networkConfig.modes.find((mode) => mode.id === modeSelect.value) || null;
}

function populateModeOptions() {
  setSelectOptions(modeSelect, "Select transport mode", networkConfig.modes, (mode) => mode.label, (mode) => mode.id);
}

function populateDependentOptions() {
  const config = selectedModeConfig();
  if (!config) {
    disableDependentSelects();
    return;
  }
  setSelectOptions(vehicleSelect, "Select vehicle type", config.vehicle_types);
  setSelectOptions(hubSelect, "Select destination hub", config.destinations);
  setSelectOptions(originSelect, "Select origin hub", config.origins);
  setSelectOptions(carrierSelect, "Select carrier or operator", config.carriers);
  [vehicleSelect, hubSelect, originSelect, carrierSelect].forEach((select) => {
    select.disabled = false;
  });
}

function showLogin(message = "") {
  currentUser = null;
  appShell.hidden = true;
  loginScreen.hidden = false;
  loginError.hidden = !message;
  loginError.textContent = message;
  adminConsole.hidden = true;
}

function setAuthMode(mode) {
  authMode = mode;
  const isSignup = authMode === "signup";
  const isMfa = authMode === "mfa";
  authTitle.textContent = isMfa
    ? "Verify your OTP"
    : isSignup
    ? "Create a ShipSense account"
    : "Sign in to the control tower";
  loginButton.textContent = isMfa ? "Verify OTP" : isSignup ? "Sign up" : "Login";
  authModeButton.textContent = isMfa || isSignup ? "Back to login" : "Create a new account";
  displayNameField.hidden = !isSignup;
  emailField.hidden = !isSignup;
  otpField.hidden = !isMfa;
  googleLoginButton.hidden = isMfa;
  otpDemoBox.hidden = true;
  otpDemoBox.textContent = "";
  if (!isMfa) {
    otpInput.value = "";
  }
  loginNote.textContent = isMfa
    ? "Enter the six digit OTP sent to your registered email address."
    : "Sign in with your user ID and password, or continue with Google. New accounts require an email address so ShipSense can send the OTP through SMTP email.";
  loginError.hidden = true;
  loginError.textContent = "";
}

function showApp(user) {
  currentUser = user;
  loginScreen.hidden = true;
  appShell.hidden = false;
  const providerSuffix = user.provider === "google" ? " · Google" : "";
  userBadge.textContent = `${user.display_name} · ${capitalize(user.role)}${providerSuffix}`;
  adminConsole.hidden = user.role !== "admin";
}

function formPayload() {
  const data = new FormData(form);
  const origin = String(data.get("origin") || "").trim();
  const destinationHub = String(data.get("destination_hub") || "").trim();
  const arrivalDays = String(data.get("arrival_days") || "").trim();
  return {
    query: String(data.get("query") || "").trim(),
    transport_mode: String(data.get("transport_mode") || "").trim(),
    vehicle_type: String(data.get("vehicle_type") || "").trim(),
    destination_hub: destinationHub,
    arrival_days: arrivalDays ? Number(arrivalDays) : null,
    origin,
    carrier: String(data.get("carrier") || "").trim(),
    cargo_type: String(data.get("cargo_type") || "").trim(),
    priority: String(data.get("priority") || "").trim(),
    route: origin && destinationHub ? `${origin}-${destinationHub}` : "",
  };
}

function validationMessage(payload) {
  if (payload.query) {
    return "";
  }
  const missing = [];
  if (!payload.transport_mode) missing.push("transport mode");
  if (!payload.vehicle_type) missing.push("vehicle type");
  if (!payload.destination_hub) missing.push("destination hub");
  if (!payload.origin) missing.push("origin hub");
  if (payload.arrival_days === null || Number.isNaN(payload.arrival_days)) missing.push("arrival days");
  if (!payload.carrier) missing.push("carrier or operator");
  if (!payload.cargo_type) missing.push("cargo type");
  if (!payload.priority) missing.push("priority");
  if (!missing.length) {
    return "";
  }
  return `Fill ${missing.join(", ")} or enter a complete natural-language transport query.`;
}

function setGauge(score, level) {
  const gauge = document.querySelector("#risk-gauge");
  const color = levelColors[level] || levelColors.Moderate;
  gauge.style.background = `conic-gradient(${color} ${score * 3.6}deg, #e5eee9 0deg)`;
  document.querySelector("#risk-score").textContent = score;
}

function renderSources(sources) {
  const row = document.querySelector("#source-row");
  row.innerHTML = "";
  sources.forEach((source) => {
    const chip = document.createElement("span");
    chip.textContent = source;
    row.appendChild(chip);
  });
}

function renderFactors(factors) {
  const list = document.querySelector("#factor-list");
  list.innerHTML = "";
  factors.forEach((factor) => {
    const row = document.createElement("div");
    row.className = "factor-row";
    row.innerHTML = `
      <div>
        <strong>${factor.name}</strong>
        <p>${factor.evidence}</p>
      </div>
      <span class="factor-score">+${factor.contribution}</span>
    `;
    list.appendChild(row);
  });
}

function renderRecommendations(recommendations) {
  const list = document.querySelector("#recommendation-list");
  list.innerHTML = "";
  recommendations.forEach((recommendation) => {
    const item = document.createElement("li");
    item.textContent = recommendation;
    list.appendChild(item);
  });
}

function renderAlternates(alternatives) {
  const list = document.querySelector("#alternate-list");
  list.innerHTML = "";
  if (!alternatives.length) {
    list.innerHTML = `<div class="alternate-row"><strong>No alternate route needed</strong><p>Keep monitoring the primary route.</p></div>`;
    return;
  }
  alternatives.forEach((alternate) => {
    const row = document.createElement("div");
    row.className = "alternate-row";
    row.innerHTML = `
      <strong>${alternate.hub || alternate.port}</strong>
      <p>${alternate.reason}</p>
      <p>${alternate.tradeoff}</p>
    `;
    list.appendChild(row);
  });
}

function renderShipments(shipments) {
  const table = document.querySelector("#shipment-table");
  table.innerHTML = "";
  shipments.forEach((shipment) => {
    const row = document.createElement("tr");
    const status = shipment.delayed ? "Delayed" : "On time";
    const statusClass = shipment.delayed ? "delayed" : "on-time";
    row.innerHTML = `
      <td>${shipment.shipment_id}</td>
      <td>${prettyMode(shipment.transport_mode)}</td>
      <td>${shipment.route}</td>
      <td>${shipment.vehicle_type}</td>
      <td>${shipment.carrier}</td>
      <td><span class="status-pill ${statusClass}">${status}</span></td>
      <td>${shipment.delay_hours}h</td>
    `;
    table.appendChild(row);
  });
}

function renderSignals(result) {
  const weather = result.signals.weather || {};
  const hub = result.signals.hub || {};
  const news = result.signals.news?.[0]?.headline || "No major news alert";
  const metricLabel = hub.metric_label || "hub pressure";
  const waitLabel = hub.wait_label || "handling";
  document.querySelector("#signal-title").textContent =
    `${result.shipment.destination_hub}: ${weather.condition || "Signal refresh ready"}`;
  document.querySelector("#signal-summary").textContent =
    `${capitalize(metricLabel)} is ${hub.capacity_index || 0}/100 with ${hub.wait_hours || 0}h ${waitLabel} wait. Latest alert: ${news}.`;
  document.querySelector("#signal-updated").textContent =
    `Signals updated ${result.signals.last_updated}`;
  if (result.ai_agent?.used) {
    liveBadge.textContent = "OpenAI agent used";
  } else if (result.ai_agent?.error) {
    liveBadge.textContent = "OpenAI fallback";
  } else if (result.live_sources?.destination?.live_enriched) {
    liveBadge.textContent = "Live API signals";
  } else {
    liveBadge.textContent = "Demo signals";
  }
}

function renderWarnings(warnings = []) {
  const warningBox = document.querySelector("#validation-warning");
  if (!warnings.length) {
    warningBox.hidden = true;
    warningBox.textContent = "";
    return;
  }
  warningBox.hidden = false;
  warningBox.textContent = warnings.join(" ");
}

function renderPlatformStatus(status) {
  document.querySelector("#green-status").textContent = `${status.green.status}: ${status.green.items.join(", ")}.`;
  document.querySelector("#yellow-status").textContent =
    `${status.yellow.status}: ${status.yellow.items.join(", ")}. ${
      currentUser?.role === "admin"
        ? "Admin role can review audit logs, user access, and observability."
        : "Standard users can analyze movements and queue jobs without admin controls."
    }`;
  document.querySelector("#blue-status").textContent =
    `${status.blue.status}: ${status.blue.items.join(", ")}. Workers active: ${status.queue.workers}.`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) {
    return "Unknown time";
  }
  return new Date(timestamp * 1000).toLocaleString();
}

function renderAdminRows(container, items, emptyMessage, renderItem) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = `<div class="admin-row"><strong>${emptyMessage}</strong></div>`;
    return;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "admin-row";
    row.innerHTML = renderItem(item);
    container.appendChild(row);
  });
}

function renderLogLines(lines = []) {
  logLines.innerHTML = "";
  if (!lines.length) {
    logLines.textContent = "No application logs yet.";
    return;
  }
  logLines.textContent = lines.join("\n");
}

function setAdminAccountMessage(message, tone = "") {
  if (!adminAccountMessage) {
    return;
  }
  adminAccountMessage.textContent = message;
  adminAccountMessage.className = `admin-message${tone ? ` ${tone}` : ""}`;
}

function renderAdminOverview(overview, policy) {
  adminConsole.hidden = currentUser?.role !== "admin";
  if (currentUser?.role !== "admin") {
    return;
  }
  currentPolicy = policy;
  const queueSummary = Object.entries(overview.queue?.statuses || {})
    .map(([status, count]) => `${status}: ${count}`)
    .join(", ") || "No queued jobs yet";
  adminSummary.textContent =
    `Admins: ${overview.summary.admins}, standard users: ${overview.summary.standard_users}, workers: ${overview.queue.workers}. Queue backend: ${overview.queue.backend}. Queue status: ${queueSummary}.`;

  const roleRows = Object.entries(policy.roles || {}).map(([role, privileges]) => ({
    role,
    privileges,
  }));
  renderAdminRows(
    rbacList,
    roleRows,
    "No RBAC policy loaded.",
    (entry) => `
      <strong>${entry.role}</strong>
      <p>${entry.privileges.join(", ")}</p>
    `
  );

  renderAdminRows(
    userDirectory,
    overview.users || [],
    "No registered users yet.",
    (entry) => `
      <div class="admin-row-shell">
        <div class="admin-row-copy">
          <strong>${entry.display_name || "Unnamed account"} - ${entry.role}</strong>
          <span>${entry.email_hint}</span>
          <small>OTP: ${entry.otp_delivery}. Provider: ${entry.auth_provider || "local"}. Joined ${formatTimestamp(entry.created_at)}</small>
        </div>
        <div class="admin-row-actions">
          ${entry.account_id === currentUser?.account_id ? '<small>Current session</small>' : ""}
          <button
            type="button"
            class="secondary-button danger-button compact-button"
            data-remove-account="${entry.account_id || ""}"
            ${entry.account_id === currentUser?.account_id ? "disabled" : ""}
          >
            Remove
          </button>
        </div>
      </div>
    `
  );

  renderAdminRows(
    auditEvents,
    overview.audit_events || [],
    "No audit events yet.",
    (entry) => `
      <strong>${entry.event}</strong>
      <span>Role: ${entry.role}</span>
      <small>${formatTimestamp(entry.created_at)}</small>
    `
  );

  renderAdminRows(
    traceEvents,
    overview.traces || [],
    "No traces captured yet.",
    (entry) => `
      <strong>${entry.trace_id || "trace"} · ${entry.method} ${entry.path}</strong>
      <span>Status ${entry.status} · ${entry.duration_ms} ms · ${entry.role}</span>
      <small>${formatTimestamp(entry.timestamp)}</small>
    `
  );

  renderAdminRows(
    stackStatus,
    overview.stack || [],
    "No stack details available.",
    (entry) => `
      <strong>${entry.service} · ${entry.status}</strong>
      <p>${entry.detail}</p>
    `
  );

  renderLogLines(overview.logs || []);
}

function renderResult(result) {
  setGauge(result.score, result.level);
  document.querySelector("#risk-title").textContent = `${result.level} risk for ${result.shipment.destination_hub}`;
  document.querySelector("#risk-explanation").textContent = result.explanation;
  document.querySelector("#risk-probability").textContent = `${Math.round(result.probability * 100)}%`;
  document.querySelector("#risk-confidence").textContent = `${result.confidence}%`;
  document.querySelector("#risk-route").textContent = `${prettyMode(result.shipment.transport_mode)} - ${result.shipment.route}`;

  renderSources(result.data_sources);
  renderFactors(result.factors);
  renderRecommendations(result.recommendations);
  renderAlternates(result.alternatives);
  renderShipments(result.recent_shipments || []);
  renderSignals(result);
  renderWarnings(result.validation?.warnings || []);
}

async function analyze() {
  const payload = formPayload();
  const warning = validationMessage(payload);
  if (warning) {
    renderWarnings([warning]);
    apiStatus.textContent = "Waiting for input";
    return;
  }
  renderWarnings([]);
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyzing risk...";
  try {
    const result = await api("/api/predict-risk", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderResult(result);
    apiStatus.textContent = "Online";
  } catch (error) {
    if (String(error.message).includes("Login required") || String(error.message).includes("authenticated")) {
      showLogin("Please login again to continue.");
      return;
    }
    apiStatus.textContent = "API error";
    document.querySelector("#risk-explanation").textContent =
      "Could not reach the risk engine. Run python3 app.py and refresh the page.";
    console.error(error);
  } finally {
    analyzeButton.disabled = false;
    analyzeButton.textContent = "Analyze shipment";
  }
}

async function queueAnalysis() {
  const payload = formPayload();
  const warning = validationMessage(payload);
  if (warning) {
    renderWarnings([warning]);
    jobStatus.hidden = false;
    jobStatus.textContent = "Complete the transport input before queueing.";
    return;
  }
  renderWarnings([]);
  queueButton.disabled = true;
  queueButton.textContent = "Queueing job...";
  jobStatus.hidden = false;
  jobStatus.textContent = "Creating async prediction job with an idempotency key.";
  const idempotencyKey =
    `${payload.transport_mode}-${payload.route}-${payload.destination_hub}-${payload.arrival_days}-${payload.cargo_type}`;
  try {
    const result = await api("/api/prediction-jobs", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
    jobStatus.textContent = `Job ${result.job.id} is ${result.job.status}. Two workers will pick it up atomically.`;
    await pollJob(result.job.id);
  } catch (error) {
    jobStatus.textContent = "Could not create async job.";
    console.error(error);
  } finally {
    queueButton.disabled = false;
    queueButton.textContent = "Queue async analysis";
  }
}

async function pollJob(jobId) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const result = await api(`/api/prediction-jobs/${jobId}`);
    jobStatus.textContent = `Job ${result.job.id} is ${result.job.status}. Attempts: ${result.job.attempts}.`;
    if (result.job.status === "completed") {
      renderResult(result.job.result);
      jobStatus.textContent = `Async job completed by ${result.job.locked_by || "worker pool"} with idempotency protection.`;
      return;
    }
    if (result.job.status === "failed") {
      jobStatus.textContent = `Async job failed: ${result.job.error}`;
      return;
    }
  }
  jobStatus.textContent =
    currentUser?.role === "admin"
      ? "Job is still running. Check the Platform section or the admin console for queue status."
      : "Job is still running. Give it a moment and check the Platform section again.";
}

async function initDashboard() {
  try {
    const health = await api("/api/health");
    apiStatus.textContent = health.status === "ok" ? "Online" : "Checking";
    const liveSources = await api("/api/live-sources");
    if (liveSources.openai?.configured) {
      liveBadge.textContent = "OpenAI agent ready";
    } else if (liveSources.openweather.configured || liveSources.newsapi.configured) {
      liveBadge.textContent = "API keys ready";
    } else {
      liveBadge.textContent = "Demo signals";
    }
    const platformStatus = await api("/api/platform-status");
    renderPlatformStatus(platformStatus);
    const policy = await api("/api/rbac-policy");
    currentPolicy = policy;
    networkConfig = await api("/api/network");
    populateModeOptions();
    disableDependentSelects();
    const shipments = await api("/api/shipments");
    renderShipments(shipments.shipments || []);
    if (currentUser?.role === "admin") {
      await refreshAdminTelemetry();
    } else {
      adminConsole.hidden = true;
    }
  } catch (error) {
    apiStatus.textContent = "Offline";
    console.error(error);
  }
}

async function refreshAdminTelemetry() {
  if (currentUser?.role !== "admin") {
    return;
  }
  const policy = currentPolicy || await api("/api/rbac-policy");
  const overview = await api("/api/admin/overview");
  renderAdminOverview(overview, policy);
}

async function loadAuthProviders() {
  try {
    const providers = await api("/api/auth-providers", {}, false);
    const google = providers.google || {};
    googleLoginPath = google.login_path || "/auth/google/start";
    googleLoginButton.textContent = google.label || "Continue with Google";
    googleLoginButton.disabled = !google.configured;
  } catch (error) {
    googleLoginPath = "/auth/google/start";
    googleLoginButton.disabled = false;
    googleLoginButton.textContent = "Continue with Google";
    console.error(error);
  }
}

async function init() {
  const url = new URL(window.location.href);
  const oauthStatus = url.searchParams.get("oauth");
  const oauthMessage = url.searchParams.get("message");
  await loadAuthProviders();
  setAuthMode("login");
  if (oauthStatus) {
    window.history.replaceState({}, "", url.pathname);
    if (oauthStatus === "google-success") {
      try {
        const session = await api("/api/me", {}, false);
        if (session.authenticated) {
          showApp(session.user);
          await initDashboard();
          return;
        }
      } catch (error) {
        console.error(error);
      }
      showLogin("Google sign-in completed, but the session could not be restored. Please try again.");
      return;
    }
    showLogin(oauthMessage || "Google sign-in was not completed.");
    return;
  }
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  showLogin();
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginButton.disabled = true;
  loginButton.textContent = authMode === "mfa" ? "Verifying..." : authMode === "signup" ? "Creating account..." : "Signing in...";
  const data = new FormData(loginForm);
  const path = authMode === "mfa" ? "/api/verify-mfa" : authMode === "signup" ? "/api/signup" : "/api/login";
  const payload = authMode === "mfa"
    ? {
        challenge_id: mfaChallengeId,
        otp: data.get("otp"),
      }
    : {
        username: data.get("username"),
        password: data.get("password"),
      };
  if (authMode === "signup") {
    payload.display_name = data.get("display_name");
    payload.email = data.get("email");
  }
  try {
    const result = await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.mfa_required) {
      mfaChallengeId = result.challenge_id;
      setAuthMode("mfa");
      otpDemoBox.hidden = false;
      otpDemoBox.textContent = result.delivery_target_hint
        ? `OTP sent via ${result.delivery} to ${result.delivery_target_hint}.`
        : "OTP sent. Check your configured delivery channel.";
      showLogin();
      return;
    }
    showApp(result.user);
    await initDashboard();
  } catch (error) {
    const fallback =
      authMode === "mfa"
        ? "Invalid or expired OTP."
        : authMode === "signup"
        ? "Could not create account."
        : "Invalid username or password.";
    showLogin(error.message || fallback);
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = authMode === "mfa" ? "Verify OTP" : authMode === "signup" ? "Sign up" : "Login";
  }
});

authModeButton.addEventListener("click", () => {
  setAuthMode(authMode === "signup" || authMode === "mfa" ? "login" : "signup");
});

googleLoginButton.addEventListener("click", async () => {
  googleLoginButton.disabled = true;
  googleLoginButton.textContent = "Redirecting to Google...";
  window.location.href = googleLoginPath;
});

logoutButton.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  setAuthMode("login");
  showLogin("You have been logged out.");
});

modeSelect.addEventListener("change", () => {
  populateDependentOptions();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze();
});

queueButton.addEventListener("click", queueAnalysis);

if (refreshAdminButton) {
  refreshAdminButton.addEventListener("click", async () => {
    refreshAdminButton.disabled = true;
    refreshAdminButton.textContent = "Refreshing...";
    try {
      await refreshAdminTelemetry();
    } catch (error) {
      console.error(error);
    } finally {
      refreshAdminButton.disabled = false;
      refreshAdminButton.textContent = "Refresh admin telemetry";
    }
  });
}

if (adminAccountForm) {
  adminAccountForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = adminAccountForm.querySelector('button[type="submit"]');
    const data = new FormData(adminAccountForm);
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Adding...";
    }
    setAdminAccountMessage("Creating account...", "");
    try {
      await api("/api/admin/accounts", {
        method: "POST",
        body: JSON.stringify({
          display_name: data.get("display_name"),
          email: data.get("email"),
          username: data.get("username"),
          password: data.get("password"),
          role: data.get("role"),
        }),
      });
      adminAccountForm.reset();
      setAdminAccountMessage("Account created successfully.", "success");
      await refreshAdminTelemetry();
    } catch (error) {
      setAdminAccountMessage(error.message || "Could not create account.", "error");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Add account";
      }
    }
  });
}

if (userDirectory) {
  userDirectory.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-remove-account]");
    if (!button) {
      return;
    }
    const accountId = button.getAttribute("data-remove-account");
    if (!accountId) {
      return;
    }
    if (!window.confirm("Remove this registered account?")) {
      return;
    }
    button.disabled = true;
    button.textContent = "Removing...";
    setAdminAccountMessage("Removing account...", "");
    try {
      await api(`/api/admin/accounts/${accountId}`, {
        method: "DELETE",
      });
      setAdminAccountMessage("Account removed successfully.", "success");
      await refreshAdminTelemetry();
    } catch (error) {
      setAdminAccountMessage(error.message || "Could not remove account.", "error");
      button.disabled = false;
      button.textContent = "Remove";
    }
  });
}

setAuthMode("login");
init();
