# CognitoSphere AI — Project Documentation

**Version:** 1.0.0
**Developer:** Shubham Rajendra Wani
**Role:** Developer
**Year:** 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Project Workflow](#4-project-workflow)
5. [Features](#5-features)
6. [Database Design](#6-database-design)
7. [API Routes](#7-api-routes)
8. [Security](#8-security)
9. [Environment Variables](#9-environment-variables)
10. [Deployment — Render.com](#10-deployment--rendercom)
11. [Deployment — PythonAnywhere](#11-deployment--pythonanywhere)

---

## 1. Project Overview

**CognitoSphere AI** is a full-stack AI chatbot web application powered by OpenAI's GPT-4o-mini model. Users can register, log in, chat with an AI assistant, manage conversation history, reset their password via OTP email, and manage their profile.

The application is live at:
> `https://<your-app>.onrender.com`

---

## 2. Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, Flask 3.1 |
| Database ORM | Flask-SQLAlchemy |
| Database | PostgreSQL (Neon.tech) / SQLite (local) |
| Authentication | Flask-Login, Werkzeug (PBKDF2-SHA256) |
| Forms & CSRF | Flask-WTF |
| Rate Limiting | Flask-Limiter |
| Email (OTP & Query) | Flask-Mail, Gmail SMTP |
| AI Model | OpenAI GPT-4o-mini |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Charts | Chart.js v4.4.0 |
| Markdown Rendering | marked.js, highlight.js |
| Deployment | Render.com / PythonAnywhere |
| Environment Config | python-dotenv |
| Production Server | Gunicorn |

---

## 3. Project Structure

```
ai_chatbot_web/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (never commit)
├── .gitignore              # Git ignore rules
├── DOCUMENTATION.md        # This file
│
├── templates/
│   ├── index.html          # Main chat interface
│   ├── login.html          # Login page
│   ├── register.html       # Registration page
│   ├── profile.html        # User profile page
│   ├── forgot_password.html# Forgot password page
│   ├── verify_otp.html     # OTP verification page
│   └── reset_password.html # Reset password page
│
└── static/
    ├── style.css           # Chat interface styles
    ├── auth.css            # Auth pages styles
    ├── profile.css         # Profile page styles
    └── script.js           # Frontend JavaScript
```

---

## 4. Project Workflow

### 4.1 User Registration & Login Flow

```
User visits site
      │
      ▼
  [Login Page]
      │
      ├── No account? ──► [Register Page]
      │                        │
      │                   Fill username,
      │                   email, password
      │                        │
      │                   Server validates
      │                   & saves to DB
      │                        │
      │                   Redirect to Login
      │
      ├── Has account? ──► Enter email + password
      │                        │
      │                   Server checks
      │                   password hash
      │                        │
      │                   ┌────┴────┐
      │                 Valid    Invalid
      │                   │         │
      │              Session     Show error
      │              created     message
      │                   │
      └───────────────────►
                          │
                    [Chat Interface]
```

---

### 4.2 Forgot Password / OTP Flow

```
[Login Page]
      │
      ▼
"Forgot Password?" link
      │
      ▼
[Forgot Password Page]
  Enter registered email
      │
      ▼
Server checks if email exists in DB
      │
      ├── Not found ──► Show error toast
      │
      └── Found ──► Generate 6-digit OTP
                         │
                    Hash OTP (PBKDF2)
                    Store in memory
                    with 10-min expiry
                         │
                    Send OTP to
                    user's email (Gmail SMTP)
                         │
                         ▼
                  [Verify OTP Page]
                  User enters 6 digits
                         │
                  Server compares
                  hash of entered OTP
                         │
                    ┌────┴────┐
                  Valid    Invalid/Expired
                    │         │
             Mark session   Show error,
             as verified    allow retry
                    │
                    ▼
            [Reset Password Page]
            Enter new password
                    │
            Hash & save to DB
                    │
                    ▼
            Redirect to Login
```

---

### 4.3 AI Chat Flow

```
[Chat Interface]
      │
      ▼
User types message
in chat input box
      │
      ▼
JavaScript sends POST /chat
with { message, session_id }
      │
      ▼
Flask receives request
      │
      ├── No session? ──► Auto-create new session
      │
      ▼
Save user message to DB
(ChatMessage: role="user")
      │
      ▼
Build message history
from DB (last N messages)
      │
      ▼
Send to OpenAI API
(GPT-4o-mini)
      │
      ▼
Receive AI response
      │
      ▼
Save AI message to DB
(ChatMessage: role="assistant")
      │
      ▼
Return JSON response
to frontend
      │
      ▼
JavaScript renders
markdown + code highlighting
in chat bubble
```

---

### 4.4 Chat Session Management Flow

```
[Sidebar]
      │
      ├── [+ New Chat] button
      │         │
      │    POST /sessions
      │    Creates new session in DB
      │    Loads empty chat window
      │
      ├── Click existing session
      │         │
      │    GET /sessions/<id>
      │    Fetches all messages from DB
      │    Renders full conversation
      │
      └── Delete session (trash icon)
                │
           DELETE /sessions/<id>
           Removes session + all messages
           (cascade delete)
           Loads next available session
```

---

### 4.5 Profile Page Flow

```
[Sidebar] ──► Click username/avatar
                      │
                      ▼
              [Profile Page]
                      │
         ┌────────────┼────────────┐
         │            │            │
         ▼            ▼            ▼
  [Update        [Send         [Delete
  Username]      Query]        Account]
      │              │              │
  Validate       Validate       Show modal
  username       subject +      "Type DELETE
  (live)         message        to confirm"
      │              │              │
  POST           POST           POST
  /profile       /profile/      /profile/
  (update DB)    query          delete
      │              │              │
  Show success   Save to DB     Delete user +
  toast          Send email     all sessions
                 to admin       from DB
                                     │
                               Redirect to
                               Login page
```

---

### 4.6 Full Application Architecture

```
┌─────────────────────────────────────────────────┐
│                   Browser (Client)               │
│  HTML + CSS + JavaScript (script.js)             │
│  Chart.js │ marked.js │ highlight.js             │
└───────────────────┬─────────────────────────────┘
                    │  HTTP Requests (fetch API)
                    ▼
┌─────────────────────────────────────────────────┐
│               Flask Web Server (app.py)          │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │Flask-    │  │Flask-WTF │  │Flask-Limiter │  │
│  │Login     │  │(CSRF)    │  │(Rate Limit)  │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                  │
│  ┌──────────┐  ┌──────────┐                     │
│  │Flask-    │  │Flask-    │                     │
│  │Mail      │  │SQLAlchemy│                     │
│  └────┬─────┘  └────┬─────┘                     │
└───────┼─────────────┼───────────────────────────┘
        │             │
        ▼             ▼
┌─────────────┐ ┌─────────────────────────────────┐
│ Gmail SMTP  │ │        PostgreSQL / SQLite        │
│ (OTP +      │ │  (Neon.tech cloud / local file)  │
│  Queries)   │ │                                  │
└─────────────┘ │  Users │ ChatSessions │          │
                │  ChatMessages │ UserQueries       │
                └─────────────────────────────────┘
                              ▲
                              │ API calls
                              ▼
                ┌─────────────────────────────────┐
                │         OpenAI API               │
                │      (GPT-4o-mini model)         │
                └─────────────────────────────────┘
```

---

## 5. Features

### 5.1 Authentication
- **Register** — username, email, password with confirm password validation
- **Login** — email + password with session management (24-hour expiry)
- **Logout** — clears session securely
- **Forgot Password** — 6-digit OTP sent to registered email, valid 10 minutes
- **Reset Password** — new password with strength meter and confirm validation

### 5.2 AI Chat
- Powered by **OpenAI GPT-4o-mini**
- Real-time streaming-style response rendering
- Markdown + code highlighting in responses (marked.js + highlight.js)
- Chat input placeholder: "Type your message..."
- Max message length: 4000 characters

### 5.3 Chat Session Management
- **Multiple sessions** — create, switch, and delete chat sessions
- **Persistent history** — all messages stored in PostgreSQL/SQLite
- **Auto-title** — session title set from first user message (max 40 chars)
- **Sidebar** — lists all sessions with delete option
- **Mobile sidebar** — slide-in drawer with overlay and hamburger button

### 5.4 Profile Page
- **View profile** — avatar (initials), username, email
- **Update username** — live validation, instant save
- **Send query** — subject + message form, email notification sent to admin
- **Usage statistics** — 4 stat pills (sessions, messages, AI responses, total)
- **Usage charts** — bar chart (last 7 days activity) + doughnut chart (message breakdown)
- **Delete account** — danger zone with confirmation modal (type "DELETE" to confirm)

### 5.5 Responsive Design
- **Desktop** (>1024px) — full sidebar 260px wide
- **Tablet** (≤1024px) — sidebar 220px wide
- **Mobile** (≤768px) — slide-in drawer sidebar, hamburger menu
- **Small mobile** (≤400px) — full-width sidebar drawer
- Auth pages responsive at 768px, 480px, 360px breakpoints

### 5.6 Email Notifications
- **OTP Email** — sent to user's registered email on forgot password request
- **Query Email** — sent to admin email when user submits a query
  - Sender display: user's username
  - Reply-To: user's email address

### 5.7 Copyright
- Displayed in sidebar bottom and profile page footer
- © 2026 CognitoSphere AI — Created by **Shubham Rajendra Wani** · Developer

---

## 6. Database Design

### User
| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| username | String(80) | Unique username |
| email | String(120) | Unique email address |
| password_hash | String(256) | PBKDF2-SHA256 hashed password |

**Relationships:** has many `ChatSession`, `UserQuery` (cascade delete)

---

### ChatSession
| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| user_id | Integer (FK) | References User.id |
| title | String(100) | Session title (from first message) |
| created_at | DateTime | UTC timestamp of creation |

**Relationships:** has many `ChatMessage` (cascade delete)

---

### ChatMessage
| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| session_id | Integer (FK) | References ChatSession.id |
| role | String(20) | `"user"` or `"assistant"` |
| content | Text | Message content |
| created_at | DateTime | UTC timestamp |

---

### UserQuery
| Column | Type | Description |
|--------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| user_id | Integer (FK) | References User.id |
| subject | String(100) | Query subject |
| message | Text | Query message body |
| created_at | DateTime | UTC timestamp |

---

## 7. API Routes

| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/` | No | Redirect to login or chat |
| GET | `/login` | No | Login page |
| POST | `/login` | No | Process login |
| GET | `/register` | No | Register page |
| POST | `/register` | No | Process registration |
| GET | `/logout` | Yes | Logout user |
| GET | `/chat` | Yes | Main chat interface |
| POST | `/chat` | Yes | Send message, get AI response |
| GET | `/sessions` | Yes | Get all user sessions |
| POST | `/sessions` | Yes | Create new session |
| GET | `/sessions/<id>` | Yes | Get messages for session |
| DELETE | `/sessions/<id>` | Yes | Delete session |
| GET | `/profile` | Yes | Profile page |
| GET | `/profile/stats` | Yes | Usage statistics (JSON) |
| POST | `/profile/query` | Yes | Submit user query |
| POST | `/profile/delete` | Yes | Delete account |
| GET | `/forgot-password` | No | Forgot password page |
| POST | `/forgot-password` | No | Send OTP email |
| GET | `/verify-otp` | No | OTP entry page |
| POST | `/verify-otp` | No | Verify OTP |
| GET | `/reset-password` | No | Reset password page |
| POST | `/reset-password` | No | Save new password |

---

## 8. Security

| Feature | Implementation |
|---------|---------------|
| Password hashing | PBKDF2-SHA256 via Werkzeug |
| OTP hashing | PBKDF2-SHA256, stored in memory, 10-min expiry |
| CSRF protection | Flask-WTF on all forms |
| Rate limiting | `/login` 10/min, `/register` 5/min, `/forgot-password` 10/hr |
| Session security | HTTPOnly, SameSite=Lax, 24-hour lifetime |
| Content Security Policy | Custom header blocking inline scripts/styles |
| Input validation | Server-side length/regex checks on all inputs |
| SQL injection | Prevented by SQLAlchemy ORM (parameterized queries) |
| XSS | Jinja2 auto-escaping on all template variables |
| Secrets | All keys in `.env`, never committed to git |

---

## 9. Environment Variables

Create a `.env` file in the project root. **Never commit this file to git.**

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret key (long random string) |
| `OPENAI_API_KEY` | OpenAI API key from platform.openai.com |
| `MAIL_USERNAME` | Gmail address used to send emails |
| `MAIL_PASSWORD` | Gmail App Password (not account password) |
| `DATABASE_URL` | PostgreSQL or SQLite connection string |

> **Gmail App Password:** Google Account → Security → 2-Step Verification → App Passwords → Generate
> All environment variables must be configured in the hosting platform's environment settings (e.g. Render Environment tab). Never store credentials in code or commit them to git.

---

## 10. Deployment — Render.com

### Prerequisites
- GitHub account with project pushed
- Render.com free account
- Neon.tech PostgreSQL database (free tier)

### Steps

**1. Push code to GitHub**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<username>/CognitoSphere-AI.git
git push -u origin main
```

**2. Create Web Service on Render**
- New → Web Service → Connect GitHub repo
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python -m gunicorn app:app`
- **Python Version:** 3.10+

**3. Add Environment Variables**
In Render → Environment tab, add all variables listed in Section 9

**4. Initialize Database**
In Render → Shell tab:
```bash
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('OK')"
```

**5. Keep Awake (UptimeRobot)**
- uptimerobot.com → Add HTTP monitor
- URL: your Render URL
- Interval: 5 minutes (prevents 15-min sleep)

### Render Free Tier Limits
| Resource | Limit |
|----------|-------|
| Hours | 750/month (24/7 for 1 service) |
| Bandwidth | 100 GB/month |
| Sleep | After 15 min inactivity (bypassed with UptimeRobot) |
| Expiry | Never |

---

## 11. Deployment — PythonAnywhere

> **Note:** Free tier blocks external TCP connections — use SQLite instead of PostgreSQL.

### Steps

**1. Upload project zip via Files tab**

**2. Extract files**
```bash
cd /home/<username>/CognitoSphereAI
unzip -o ai_chatbot_web.zip
```

**3. Create virtualenv**
```bash
python3 -m venv /home/<username>/.virtualenvs/cognito
source /home/<username>/.virtualenvs/cognito/bin/activate
pip install flask flask-sqlalchemy flask-login flask-wtf flask-limiter flask-mail openai python-dotenv pymysql gunicorn
```

**4. Create .env**
```bash
nano /home/<username>/CognitoSphereAI/.env
```
Add all environment variables listed in Section 9. Save with `Ctrl+X` → `Y` → `Enter`.

**5. Configure WSGI file**
```python
import sys, os
from dotenv import load_dotenv

project_home = '/home/<username>/CognitoSphereAI'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

load_dotenv(os.path.join(project_home, '.env'))
from app import app as application
```

**6. Set virtualenv path in Web tab**
```
/home/<username>/.virtualenvs/cognito
```

**7. Initialize DB and Reload**
```bash
source /home/<username>/.virtualenvs/cognito/bin/activate
cd /home/<username>/CognitoSphereAI
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('OK')"
```
Then click **Reload** in Web tab.

---

## Dependencies (requirements.txt)

```
flask==3.1.3
gunicorn==21.2.0
psycopg2-binary==2.9.10
PyMySQL==1.1.1
flask-sqlalchemy==3.1.1
flask-login==0.6.3
flask-wtf==1.2.2
flask-limiter==4.1.1
flask-mail==0.10.0
werkzeug==3.1.7
openai==2.30.0
python-dotenv==1.2.2
```

---

*© 2026 CognitoSphere AI — Created by **Shubham Rajendra Wani** · Developer*
