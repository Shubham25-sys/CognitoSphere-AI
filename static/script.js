// ===== CONFIGURATION =====
marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

let totalTokens      = 0;
let isLoading        = false;
let currentSessionId = null;

// ===== SIDEBAR TOGGLE (mobile) =====
function toggleSidebar() {
  const sidebar  = document.getElementById("sidebar");
  const overlay  = document.getElementById("sidebarOverlay");
  const isOpen   = sidebar.classList.contains("open");
  sidebar.classList.toggle("open", !isOpen);
  overlay.classList.toggle("show", !isOpen);
  document.body.style.overflow = isOpen ? "" : "hidden";
}

function openSidebar() {
  document.getElementById("sidebar").classList.add("open");
  document.getElementById("sidebarOverlay").classList.add("show");
  document.body.style.overflow = "hidden";
}

function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebarOverlay").classList.remove("show");
  document.body.style.overflow = "";
}

// ===== DOM REFS =====
const chatMessages = document.getElementById("chatMessages");
const userInput    = document.getElementById("userInput");
const sendBtn      = document.getElementById("sendBtn");
const tokenCount   = document.getElementById("tokenCount");
const chatHistory  = document.getElementById("chatHistory");

// ===== ESCAPE HTML =====
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ===== AUTO-RESIZE TEXTAREA =====
userInput.addEventListener("input", () => {
  userInput.style.height = "auto";
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + "px";
});

// ===== KEYBOARD SHORTCUT: Enter to send, Shift+Enter for newline =====
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ===== WELCOME SCREEN =====
function showWelcome() {
  chatMessages.innerHTML = `
    <div class="welcome-screen" id="welcomeScreen">
      <div class="welcome-icon">🤖</div>
      <h2>How can I help you today?</h2>
      <p>Start a conversation by typing a message below.</p>
      <div class="quick-prompts">
        <button class="quick-prompt" onclick="sendQuickPrompt('Explain machine learning in simple terms')">Explain machine learning</button>
        <button class="quick-prompt" onclick="sendQuickPrompt('Write a Python function to sort a list')">Write Python code</button>
        <button class="quick-prompt" onclick="sendQuickPrompt('What are the best practices for REST APIs?')">REST API best practices</button>
        <button class="quick-prompt" onclick="sendQuickPrompt('Summarize the key concepts of OOP')">OOP key concepts</button>
      </div>
    </div>`;
}

function removeWelcome() {
  const welcome = document.getElementById("welcomeScreen");
  if (welcome) welcome.remove();
}

// ===== APPEND A MESSAGE BUBBLE =====
function appendMessage(role, content) {
  removeWelcome();

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "bot-avatar"}`;
  avatar.textContent = role === "user" ? "👤" : "🤖";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (role === "bot") {
    bubble.innerHTML = marked.parse(content);
    bubble.querySelectorAll("pre code").forEach((el) => hljs.highlightElement(el));
  } else {
    bubble.textContent = content;
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  scrollToBottom();
}

// ===== TYPING INDICATOR =====
function showTyping() {
  removeWelcome();
  const row = document.createElement("div");
  row.className = "message-row bot";
  row.id = "typingRow";

  const avatar = document.createElement("div");
  avatar.className = "avatar bot-avatar";
  avatar.textContent = "🤖";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = `
    <div class="typing-indicator">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;

  row.appendChild(avatar);
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  scrollToBottom();
}

function removeTyping() {
  const row = document.getElementById("typingRow");
  if (row) row.remove();
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ===== SESSION LIST =====
async function loadSessions() {
  const res = await fetch("/sessions");
  const sessions = await res.json();
  renderSessionList(sessions);
  return sessions;
}

function renderSessionList(sessions) {
  if (!sessions.length) {
    chatHistory.innerHTML = '<p class="no-history">No conversations yet</p>';
    return;
  }
  chatHistory.innerHTML = sessions.map(s => `
    <div class="history-item ${s.id === currentSessionId ? "active" : ""}"
         data-id="${s.id}" onclick="switchSession(${s.id})">
      <div class="history-item-body">
        <div class="history-title">${escapeHtml(s.title)}</div>
        <div class="history-date">${s.created_at}</div>
      </div>
      <button class="history-delete" onclick="deleteSession(event,${s.id})" title="Delete">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>`).join("");
}

// ===== SWITCH / LOAD SESSION =====
async function switchSession(id) {
  if (id === currentSessionId) return;
  currentSessionId = id;

  document.querySelectorAll(".history-item").forEach(el => {
    el.classList.toggle("active", parseInt(el.dataset.id) === id);
  });

  const res  = await fetch(`/sessions/${id}`);
  const data = await res.json();

  document.getElementById("chatTitle").textContent =
    data.title === "New Chat" ? "Chat with AI" : data.title;

  // Auto-close sidebar on mobile after selecting a chat
  if (window.innerWidth <= 768) closeSidebar();

  chatMessages.innerHTML = "";
  totalTokens = 0;
  tokenCount.textContent = "0";

  if (!data.messages.length) {
    showWelcome();
  } else {
    data.messages.forEach(m =>
      appendMessage(m.role === "user" ? "user" : "bot", m.content)
    );
  }
  userInput.focus();
}

// ===== CREATE NEW SESSION =====
async function createNewSession() {
  const res  = await fetch("/sessions", { method: "POST" });
  const data = await res.json();
  currentSessionId = data.id;

  await loadSessions();
  showWelcome();
  totalTokens = 0;
  tokenCount.textContent = "0";
  document.getElementById("chatTitle").textContent = "Chat with AI";
  userInput.focus();
}

// ===== DELETE SESSION =====
async function deleteSession(event, id) {
  event.stopPropagation();
  await fetch(`/sessions/${id}`, { method: "DELETE" });

  if (id === currentSessionId) {
    await createNewSession();
  } else {
    await loadSessions();
  }
}

// ===== SEND MESSAGE =====
async function sendMessage() {
  const message = userInput.value.trim();
  if (!message || isLoading || !currentSessionId) return;

  isLoading = true;
  sendBtn.disabled = true;
  userInput.value = "";
  userInput.style.height = "auto";

  appendMessage("user", message);
  showTyping();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: currentSessionId }),
    });

    const data = await res.json();
    removeTyping();

    if (!res.ok) {
      appendMessage("bot", `**Error:** ${data.error || "Something went wrong."}`);
      return;
    }

    appendMessage("bot", data.reply);

    if (data.usage) {
      totalTokens += data.usage.prompt_tokens + data.usage.completion_tokens;
      tokenCount.textContent = totalTokens.toLocaleString();
    }

    // Refresh sidebar when title is auto-set from first message
    if (data.title_updated) {
      await loadSessions();
      document.getElementById("chatTitle").textContent = data.title_updated;
    }
  } catch {
    removeTyping();
    appendMessage("bot", "**Network error.** Please check your connection and try again.");
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    userInput.focus();
  }
}

// ===== QUICK PROMPT =====
function sendQuickPrompt(prompt) {
  userInput.value = prompt;
  sendMessage();
}

// ===== NEW CHAT BUTTON =====
function resetChat() {
  createNewSession();
}

// ===== INIT =====
async function init() {
  const sessions = await loadSessions();
  if (sessions.length > 0) {
    await switchSession(sessions[0].id);
  } else {
    await createNewSession();
  }
  userInput.focus();
}

init();
