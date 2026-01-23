<div align="center">
  <h1>Dotolista</h1>
  <p><b>Simple Telegram todo-list for personal productivity.</b><br/>
  Telegram-bot UI + local SQLite database. AI-analysis planned later.</p>
</div>
<hr/>
<h2>Features</h2>
<ul>
  <li>Telegram-first UX (button-first where possible)</li>
  <li>Add / list / complete / edit / delete tasks</li>
  <li>Local SQLite persistence</li>
  <li>Deterministic prioritization (optional <code>!</code> suffix priority)</li>
</ul>
<h2>Requirements</h2>
<ul>
  <li>Python 3.10+</li>
  <li>Telegram Bot Token (BotFather)</li>
  <li>Windows / Linux / macOS</li>
</ul>
<hr/>
<h2>Install &amp; Run</h2>

<ol>
  <li><b>Clone + venv</b><br/>
    <code>git clone https://github.com/LarryDahl/TODOv2/</code><br/>
    <code>cd YOUR_REPO_FOLDER</code><br/>
    <code>python -m venv .venv</code>
  </li>
  <li style="margin-top:10px;"><b>Activate venv</b><br/>
    Windows (PowerShell): <code>.\.venv\Scripts\Activate.ps1</code><br/>
    Linux/macOS: <code>source .venv/bin/activate</code>
  </li>
  <li style="margin-top:10px;"><b>Install deps</b><br/>
    <code>pip install -r requirements.txt</code>
  </li>
  <li style="margin-top:10px;"><b>Create .env</b><br/>
    <code>TELEGRAM_BOT_TOKEN=your_token_here</code><br/>
    Optional: <code>TZ=Europe/Helsinki</code>, <code>DATABASE_PATH=./app.db</code>
  </li>
  <li style="margin-top:10px;"><b>Run</b><br/>
    <code>python -m app.main</code><br/>
    or <code>python -m app.ui.telegram.main</code>
  </li>
</ol>
<h2>Notes</h2>
<ul>
  <li>Do not commit <code>.env</code> (add to <code>.gitignore</code>).</li>
  <li>If PowerShell blocks activation: run as admin<br/>
    <code>Set-ExecutionPolicy RemoteSigned</code>
  </li>
</ul>

<div align="center">
  <sub>Simple first, powerful later.</sub>
</div>
