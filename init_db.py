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