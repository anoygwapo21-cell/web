# Updated app.py (only change is init_db now ensures a default admin user exists)
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import os

DATABASE = os.path.join(os.path.dirname(__file__), "events.db")
SECRET_KEY = os.environ.get("FLASK_SECRET", "change-me")
BOOT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
BOOT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

app = Flask(__name__)
app.config.from_mapping(SECRET_KEY=SECRET_KEY, DATABASE=DATABASE)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def has_column(table, column):
    db = get_db()
    cur = db.execute(f"PRAGMA table_info({table})").fetchall()
    for c in cur:
        if c["name"] == column:
            return True
    return False


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if not has_column("users", "role"):
        try:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        except Exception:
            pass
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            event_datetime TEXT,
            location TEXT,
            created_by INTEGER,
            visible_to_all INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    if not has_column("events", "visible_to_all"):
        try:
            db.execute("ALTER TABLE events ADD COLUMN visible_to_all INTEGER DEFAULT 0")
        except Exception:
            pass
    db.commit()

    # optional bootstrap admin from environment (keeps previous behavior)
    cur = db.execute("SELECT COUNT(1) as c FROM users").fetchone()
    if cur and cur["c"] == 0 and BOOT_ADMIN_USERNAME and BOOT_ADMIN_PASSWORD:
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (BOOT_ADMIN_USERNAME, generate_password_hash(BOOT_ADMIN_PASSWORD), "admin"),
        )
        db.commit()
        print(f"Bootstrapped admin user from env: {BOOT_ADMIN_USERNAME}")

    # Ensure a default admin user exists with credentials:
    # username: admin
    # password: admin123
    # NOTE: This creates a default admin if there is no user named 'admin' already.
    # This is convenient for development but insecure for production; change the password immediately.
    try:
        admin_exists = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not admin_exists:
            default_hash = generate_password_hash("admin123")
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", default_hash, "admin"),
            )
            db.commit()
            print("Inserted default admin user: 'admin' (password: admin123). Please change immediately.")
    except Exception:
        # If anything fails here, we don't want the app to crash on init_db.
        pass


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("You need to be logged in to view that page.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("role") != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("events") if "user_id" in session else url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("events"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if not username or not password:
            flash("Username and password required.", "danger")
            return redirect(url_for("register"))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), "user"),
            )
            db.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already taken.", "danger")
            return redirect(url_for("register"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"] if ("role" in user.keys() and user["role"]) else "user"
            flash(f"Welcome, {user['username']}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("events"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/events")
@login_required
def events():
    db = get_db()
    user_id = session.get("user_id")
    try:
        events_rows = db.execute(
            "SELECT id, title, description, event_datetime, location, created_by, visible_to_all FROM events WHERE visible_to_all = 1 OR created_by = ? ORDER BY datetime(event_datetime) ASC",
            (user_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        events_rows = []

    events = []
    for r in events_rows:
        ed = r["event_datetime"]
        if isinstance(ed, str):
            ed_dt = None
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    ed_dt = datetime.strptime(ed, fmt)
                    break
                except Exception:
                    continue
            if ed_dt is None:
                try:
                    ed_dt = datetime.fromisoformat(ed)
                except Exception:
                    ed_dt = None
        else:
            ed_dt = ed
        events.append(
            {
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "event_datetime": ed_dt,
                "location": r["location"],
                "created_by": r["created_by"],
                "visible_to_all": bool(r["visible_to_all"]),
            }
        )

    NOTIFY_HOURS = 24
    now = datetime.utcnow()
    notify_until = now + timedelta(hours=NOTIFY_HOURS)
    notifications = [e for e in events if e["event_datetime"] and now <= e["event_datetime"] <= notify_until]

    return render_template("events.html", events=events, notifications=notifications, notify_hours=NOTIFY_HOURS)


@app.route("/events/create", methods=["GET", "POST"])
@login_required
def create_event():
    """
    Any logged-in user can create an event.
    Admins can mark it visible_to_all (public). Regular users create private events by default.
    """
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_dt = request.form.get("event_datetime", "").strip()
        location = request.form.get("location", "").strip()

        # admins can set visible_to_all via checkbox; non-admins cannot
        visible_to_all = 0
        if session.get("role") == "admin":
            visible_to_all = 1 if request.form.get("visible_to_all") == "on" else 0

        if not title or not event_dt:
            flash("Title and event date/time are required.", "danger")
            return redirect(url_for("create_event"))

        try:
            if "T" in event_dt:
                dt = datetime.fromisoformat(event_dt)
            else:
                dt = datetime.strptime(event_dt, "%Y-%m-%d %H:%M:%S")
            event_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            flash("Invalid date/time format. Use the date/time picker.", "danger")
            return redirect(url_for("create_event"))

        db = get_db()
        db.execute(
            "INSERT INTO events (title, description, event_datetime, location, created_by, visible_to_all) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, event_iso, location, session.get("user_id"), visible_to_all),
        )
        db.commit()
        flash("Event created.", "success")
        return redirect(url_for("events"))

    return render_template("create_event.html")


@app.route("/admin/promote/<username>", methods=["POST"])
@admin_required
def promote_user(username):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    db.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
    db.commit()
    flash(f"{username} promoted to admin.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/events/delete/<int:event_id>", methods=["POST"])
@admin_required
def admin_delete_event(event_id):
    db = get_db()
    ev = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not ev:
        flash("Event not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    flash("Event deleted.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at ASC").fetchall()
    events = db.execute("SELECT id, title, event_datetime, location, created_by, visible_to_all FROM events ORDER BY datetime(event_datetime) ASC").fetchall()
    parsed_events = []
    for r in events:
        ed = r["event_datetime"]
        ed_dt = None
        if isinstance(ed, str):
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    ed_dt = datetime.strptime(ed, fmt)
                    break
                except Exception:
                    continue
            if ed_dt is None:
                try:
                    ed_dt = datetime.fromisoformat(ed)
                except Exception:
                    ed_dt = None
        parsed_events.append(
            {
                "id": r["id"],
                "title": r["title"],
                "event_datetime": ed_dt,
                "location": r["location"],
                "created_by": r["created_by"],
                "visible_to_all": bool(r["visible_to_all"]),
            }
        )

    return render_template("admin_dashboard.html", users=users, events=parsed_events)


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", username=session.get("username"), role=session.get("role"))


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.secret_key = app.config["SECRET_KEY"]
    app.run(debug=True)