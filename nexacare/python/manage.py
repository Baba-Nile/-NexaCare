#!/usr/bin/env python3
"""Operations for the secure platform.  Usage: python python/manage.py <command>
  gen-keys           print fresh secrets for .env
  migrate            apply database migrations
  create-admin       create the first system administrator (prompts for a password; no default accounts exist)
  verify-audit       check the audit-log hash chain
  purge              delete expired sessions, old login attempts and stale pending/rejected portal registrations
  backup             write an encrypted backup (SQLite) or print the pg_dump command (PostgreSQL)
  restore-check      decrypt a backup to a temp file and run integrity checks (does not touch the live database)
  seed-demo          development only: fictional users and records for trying the system (refused in production)"""
import getpass, os, secrets, sqlite3, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cryptography.fernet import Fernet
from flask import Flask

def make_app():
    from portal import create_portal
    app = Flask(__name__, static_folder=None); create_portal(app); return app

def cutoff(days): return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

def main(argv):
    if not argv or argv[0] not in {"gen-keys", "migrate", "create-admin", "verify-audit", "purge", "backup", "restore-check", "seed-demo"}: print(__doc__); return 2
    cmd = argv[0]
    if cmd == "gen-keys":
        print("PORTAL_SECRET_KEY=" + secrets.token_urlsafe(48)); print("PORTAL_DATA_KEY=" + Fernet.generate_key().decode()); print("PORTAL_BACKUP_KEY=" + Fernet.generate_key().decode()); print("PORTAL_HASH_SALT=" + secrets.token_urlsafe(24)); return 0
    app = make_app()
    from portal import db as dbm, security as sec
    from portal.audit import audit, verify_chain
    D = app.config["PORTAL_DB"]
    if cmd == "migrate": print("Applied:", D.migrate() or "nothing new"); return 0
    if cmd == "restore-check":
        key = os.environ.get("PORTAL_BACKUP_KEY");  path = Path(argv[1]) if len(argv) > 1 else None
        if not key or not path or not path.exists(): print("Usage: restore-check <backup file>  (needs PORTAL_BACKUP_KEY)"); return 2
        tmp = Path(tempfile.mkdtemp()) / "restored.db"; tmp.write_bytes(Fernet(key.encode()).decrypt(path.read_bytes()))
        c = sqlite3.connect(tmp); ok = c.execute("PRAGMA integrity_check").fetchone()[0]; n = c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        print(f"integrity: {ok}; migrations recorded: {n}"); return 0 if ok == "ok" else 1
    with app.app_context():
        if cmd == "create-admin":
            D.migrate(); email = input("Administrator email: ").strip().lower(); name = input("Full name: ").strip()
            pw = getpass.getpass("Password (12+ characters): "); 
            if pw != getpass.getpass("Again: "): print("Passwords differ."); return 1
            problems = sec.password_problems(pw, email, name)
            if problems: print("\n".join(problems)); return 1
            if dbm.one("SELECT id FROM users WHERE email=?", (email,)): print("That email already exists."); return 1
            uid = dbm.insert("INSERT INTO users (email, full_name, role, password_hash, must_change_password, active, created_at) VALUES (?,?,?,?,0,1,?)", (email, name, "system_admin", sec.hash_password(pw), dbm.now()))
            audit("user.created", target=("user", uid), detail={"role": "system_admin", "via": "cli"}, actor=None); print("Created."); return 0
        if cmd == "verify-audit": ok, bad, n = verify_chain(); print(f"{n} events; chain {'intact' if ok else 'BROKEN at event ' + str(bad)}"); return 0 if ok else 1
        if cmd == "purge":
            r = [dbm.run("DELETE FROM sessions WHERE expires_at<?", (dbm.now(),)).rowcount, dbm.run("DELETE FROM login_attempts WHERE ts<?", (cutoff(90),)).rowcount,
                 dbm.run("DELETE FROM portal_accounts WHERE status IN ('pending','rejected') AND created_at<? AND id NOT IN (SELECT account_id FROM patient_access)", (cutoff(30),)).rowcount]
            audit("retention.purge", detail={"sessions": r[0], "login_attempts": r[1], "stale_registrations": r[2]}, actor=None)
            print(f"Deleted sessions={r[0]}, login attempts={r[1]}, stale registrations={r[2]}. Clinical, billing and audit records are NOT purged: the owner must set retention periods first."); return 0
        if cmd == "backup":
            key = os.environ.get("PORTAL_BACKUP_KEY")
            if D.is_pg: print("PostgreSQL: run  pg_dump --format=custom --file=nexacare-$(date +%F).dump \"$DATABASE_URL\"  then encrypt and copy it off-site. Test restores regularly."); return 0
            if not key: print("Set PORTAL_BACKUP_KEY first (python python/manage.py gen-keys)."); return 2
            out = Path("backups"); out.mkdir(exist_ok=True); os.chmod(out, 0o700); tmp = Path(tempfile.mkdtemp()) / "b.db"
            src = sqlite3.connect(D.path); dst = sqlite3.connect(tmp); src.backup(dst); dst.close(); src.close()
            f = out / f"portal-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db.enc"; f.write_bytes(Fernet(key.encode()).encrypt(tmp.read_bytes())); os.chmod(f, 0o600); tmp.unlink()
            audit("backup.created", detail={"file": f.name}, actor=None); print("Wrote", f); return 0
        if cmd == "seed-demo":
            if app.config["PORTAL"]["production"]: print("Refused: seed-demo is for development only."); return 1
            D.migrate(); out = []
            for email, name, role in [("admin@example.test", "Demo Admin", "system_admin"), ("manager@example.test", "Demo Hospital Admin", "hospital_admin"), ("reception@example.test", "Demo Receptionist", "receptionist"), ("coordinator@example.test", "Demo Coordinator", "homecare_coordinator"),
                                      ("nurse@example.test", "Demo Nurse", "nurse"), ("doctor@example.test", "Demo Doctor", "doctor"), ("carer@example.test", "Demo Caregiver", "caregiver"), ("billing@example.test", "Demo Billing", "billing_clerk")]:
                if dbm.one("SELECT id FROM users WHERE email=?", (email,)): continue
                pw = secrets.token_urlsafe(12) + "9a"; dbm.insert("INSERT INTO users (email, full_name, role, password_hash, must_change_password, active, created_at) VALUES (?,?,?,?,0,1,?)", (email, name, role, sec.hash_password(pw), dbm.now())); out.append((email, pw))
            if not dbm.one("SELECT id FROM patients"): dbm.insert("INSERT INTO patients (full_name, date_of_birth, area, created_at) VALUES (?,?,?,?)", ("Fictional Patient One", "1950-01-01", "Demo Estate", dbm.now()))
            print("FICTIONAL demo accounts (printed once):"); [print(" ", e, p) for e, p in out]; return 0
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
