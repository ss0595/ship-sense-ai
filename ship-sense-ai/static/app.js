const form = document.querySelector("#risk-form");
const loginScreen = document.querySelector("#login-screen");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const loginError = document.querySelector("#login-error");
const authTitle = document.querySelector("#auth-title");
const authModeButton = document.querySelector("#auth-mode-button");
const displayNameField = document.querySelector("#display-name-field");
const otpField = document.querySelector("#otp-field");
const otpInput = document.querySelector("#login-otp");
const otpDemoBox = document.querySelector("#otp-demo-box");
const loginNote = document.querySelector("#login-note");
const googleLoginButton = document.querySelector("#google-login-button");
const appShell = document.querySelector("#app-shell");
const portSelect = document.querySelector("#destination_port");
const originSelect = document.querySelector("#origin");
const analyzeButton = document.querySelector("#analyze-button");
const queueButton = document.querySelector("#queue-button");
const jobStatus = document.querySelector("#job-status");
const apiStatus = document.querySelector("#api-status");
const userBadge = document.querySelector("#user-badge");
const liveBadge = document.querySelector("#live-badge");
const logoutButton = document.querySelector("#logout-button");
let authMode = "login";
let mfaChallengeId = "";

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
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return response.json();
}

function showLogin(message = "") {
  appShell.hidden = true;
  loginScreen.hidden = false;
  loginError.hidden = !message;
  loginError.textContent = message;
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
  otpField.hidden = !isMfa;
  googleLoginButton.hidden = isMfa;
  otpDemoBox.hidden = true;
  otpDemoBox.textContent = "";
  if (!isMfa) {
    otpInput.value = "";
  }
  loginNote.textContent = isMfa
    ? "Enter the six digit OTP. In local demo mode, the OTP is displayed below for judge verification."
    : "Demo users are listed in the README. Dashboard API calls use secure access and refresh cookies after login.";
  loginError.hidden = true;
  loginError.textContent = "";
}

function showApp(user) {
  loginScreen.hidden = true;
  appShell.hidden = false;
  userBadge.textContent = `${user.display_name} - ${user.role}`;
}

function formPayload() {
  const data = new FormData(form);
  const origin = String(data.get("origin") || "").trim();
  const destination = String(data.get("destination_port") || "").trim();
  const arrivalDays = String(data.get("arrival_days") || "").trim();
  return {
    query: String(data.get("query") || "").trim(),
    destination_port: destination,
    arrival_days: arrivalDays ? Number(arrivalDays) : null,
    origin,
    carrier: String(data.get("carrier") || "").trim(),
    cargo_type: String(data.get("cargo_type") || "").trim(),
    priority: String(data.get("priority") || "").trim(),
    route: origin && destination ? `${origin}-${destination}` : "",
  };
}

function validationMessage(payload) {
  if (payload.query) {
    return "";
  }
  const missing = [];
  if (!payload.destination_port) missing.push("destination port");
  if (!payload.origin) missing.push("origin port");
  if (payload.arrival_days === null || Number.isNaN(payload.arrival_days)) missing.push("arrival days");
  if (!payload.carrier) missing.push("carrier");
  if (!payload.cargo_type) missing.push("cargo type");
  if (!payload.priority) missing.push("priority");
  if (!missing.length) {
    return "";
  }
  return `Fill ${missing.join(", ")} or enter a complete natural-language shipment query.`;
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
      <strong>${alternate.port}</strong>
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
      <td>${shipment.route}</td>
      <td>${shipment.cargo_type}</td>
      <td>${shipment.carrier}</td>
      <td><span class="status-pill ${statusClass}">${status}</span></td>
      <td>${shipment.delay_hours}h</td>
    `;
    table.appendChild(row);
  });
}

function renderSignals(result) {
  const weather = result.signals.weather;
  const port = result.signals.port;
  const news = result.signals.news?.[0]?.headline || "No major news alert";
  document.querySelector("#signal-title").textContent =
    `${result.shipment.destination_port}: ${weather.condition}`;
  document.querySelector("#signal-summary").textContent =
    `Port congestion is ${port.congestion_index}/100 with ${port.berth_wait_hours}h berth wait. Latest alert: ${news}.`;
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
  document.querySelector("#yellow-status").textContent = `${status.yellow.status}: ${status.yellow.items.join(", ")}.`;
  document.querySelector("#blue-status").textContent =
    `${status.blue.status}: ${status.blue.items.join(", ")}. Workers active: ${status.queue.workers}.`;
}

function renderResult(result) {
  setGauge(result.score, result.level);
  document.querySelector("#risk-title").textContent = `${result.level} risk for ${result.shipment.destination_port}`;
  document.querySelector("#risk-explanation").textContent = result.explanation;
  document.querySelector("#risk-probability").textContent = `${Math.round(result.probability * 100)}%`;
  document.querySelector("#risk-confidence").textContent = `${result.confidence}%`;
  document.querySelector("#risk-route").textContent = result.shipment.route;

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
    jobStatus.textContent = "Complete the shipment input before queueing.";
    return;
  }
  renderWarnings([]);
  queueButton.disabled = true;
  queueButton.textContent = "Queueing job...";
  jobStatus.hidden = false;
  jobStatus.textContent = "Creating async prediction job with an idempotency key.";
  const idempotencyKey = `${payload.route}-${payload.destination_port}-${payload.arrival_days}-${payload.cargo_type}`;
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
  jobStatus.textContent = "Job is still running. Check the Platform section or /api/observability.";
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
    const portData = await api("/api/ports");
    portSelect.innerHTML = "";
    const defaultPortOption = document.createElement("option");
    defaultPortOption.value = "";
    defaultPortOption.textContent = "Select destination port";
    defaultPortOption.disabled = true;
    defaultPortOption.selected = true;
    portSelect.appendChild(defaultPortOption);
    portData.ports.forEach((port) => {
      const option = document.createElement("option");
      option.value = port;
      option.textContent = port;
      portSelect.appendChild(option);
    });
    const originData = await api("/api/origins");
    originSelect.innerHTML = "";
    const defaultOriginOption = document.createElement("option");
    defaultOriginOption.value = "";
    defaultOriginOption.textContent = "Select origin port";
    defaultOriginOption.disabled = true;
    defaultOriginOption.selected = true;
    originSelect.appendChild(defaultOriginOption);
    originData.origins.forEach((origin) => {
      const option = document.createElement("option");
      option.value = origin;
      option.textContent = origin;
      originSelect.appendChild(option);
    });
  } catch (error) {
    apiStatus.textContent = "Offline";
    console.error(error);
  }
}

async function init() {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  setAuthMode("login");
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
  }
  try {
    const result = await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.mfa_required) {
      mfaChallengeId = result.challenge_id;
      setAuthMode("mfa");
      if (result.demo_otp) {
        otpDemoBox.hidden = false;
        otpDemoBox.textContent = `Demo OTP: ${result.demo_otp}`;
        otpInput.value = "";
      } else {
        otpDemoBox.hidden = false;
        otpDemoBox.textContent = "OTP created. Check your configured OTP delivery.";
      }
      showLogin("OTP challenge created.");
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
    showLogin(fallback);
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
  googleLoginButton.textContent = "Connecting...";
  try {
    const result = await api("/api/google-login", { method: "POST", body: "{}" });
    showApp(result.user);
    await initDashboard();
  } catch (error) {
    showLogin("Google SSO demo is not available.");
  } finally {
    googleLoginButton.disabled = false;
    googleLoginButton.textContent = "Continue with Google demo";
  }
});

logoutButton.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }).catch(() => {});
  setAuthMode("login");
  showLogin("You have been logged out.");
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze();
});

queueButton.addEventListener("click", queueAnalysis);

setAuthMode("login");
init();
