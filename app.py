from flask import Flask, request, redirect, url_for, session, jsonify, flash, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time
from functools import wraps
from pathlib import Path
import qrcode, smtplib, random, string, sqlite3, os
from email.mime.text import MIMEText

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-to-something-secure"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///brand_new_attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

SENDER_EMAIL = "your-email@gmail.com"
SENDER_PASSWORD = "your-app-password-here"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

db = SQLAlchemy(app)
BASE_DIR = Path(__file__).resolve().parent
QR_FOLDER = BASE_DIR / "qr_codes"
QR_FOLDER.mkdir(exist_ok=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="faculty")
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.String(50), nullable=False)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    active = db.Column(db.Boolean, default=True)
    attendances = db.relationship("Attendance", backref="student", lazy=True, cascade="all, delete-orphan")

class AttendanceSchedule(db.Model):
    __tablename__ = "attendance_schedules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.String(50), nullable=False)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    days = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    late_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    active = db.Column(db.Boolean, default=True)

class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    late_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default="OPEN")
    schedule_id = db.Column(db.Integer, nullable=True, index=True)
    course = db.Column(db.String(100), nullable=True)
    year_level = db.Column(db.String(50), nullable=True)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    attendances = db.relationship("Attendance", backref="attendance_session", lazy=True, cascade="all, delete-orphan")

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_session.id"), nullable=False)
    scan_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    __table_args__ = (db.UniqueConstraint("student_id", "session_id", name="unique_student_session"),)

class AssessmentConfig(db.Model):
    __tablename__ = "assessment_configs"
    id = db.Column(db.Integer, primary_key=True)
    course = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.String(50), nullable=False)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    assessment_type = db.Column(db.String(50), nullable=False)
    assessment_name = db.Column(db.String(150), nullable=False)
    total_score = db.Column(db.Float, nullable=False)
    weight = db.Column(db.Float, nullable=False, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Assessment(db.Model):
    __tablename__ = "assessments"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    assessment_type = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Float, nullable=False)
    total_score = db.Column(db.Float, nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    assessment_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    assessment_name = db.Column(db.String(150), nullable=True)
    weight = db.Column(db.Float, nullable=True, default=0)
    config_id = db.Column(db.Integer, nullable=True)
    course = db.Column(db.String(100), nullable=True)
    year_level = db.Column(db.String(50), nullable=True)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    student = db.relationship("Student", backref=db.backref("assessments", lazy=True, cascade="all, delete-orphan"))

ASSESSMENT_TYPES = ["Quiz", "Activity", "Exam", "Performance", "Oral Recitation"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def send_reset_email(to_email, reset_code):
    subject = "Password Reset Code"
    body = f"""Hello,

Your verification code is: {reset_code}

Enter this code to create a new password.
If you did not request this, ignore this email."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print("Email Error:", e)
        return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def parse_time(value):
    return datetime.strptime(value, "%H:%M").time()

def selected_days(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip() in DAY_NAMES]

def schedule_matches_today(s):
    return DAY_NAMES[date.today().weekday()] in selected_days(s.days)

def class_students(course, year_level, major="", section=""):
    q = Student.query.filter_by(active=True, course=course, year_level=year_level)
    if major:
        q = q.filter(Student.major == major)
    if section:
        q = q.filter(Student.section == section)
    return q.order_by(Student.full_name).all()

def create_today_sessions():
    today = date.today()
    today_name = DAY_NAMES[today.weekday()]
    schedules = AttendanceSchedule.query.filter_by(active=True).all()
    created = 0
    for s in schedules:
        if today_name not in selected_days(s.days):
            continue
        existing = AttendanceSession.query.filter_by(schedule_id=s.id, session_date=today).first()
        if existing:
            continue
        db.session.add(AttendanceSession(
            name=s.name, session_date=today, start_time=s.start_time,
            late_time=s.late_time, end_time=s.end_time, status="OPEN",
            schedule_id=s.id, course=s.course, year_level=s.year_level,
            major=s.major, section=s.section
        ))
        created += 1
    if created:
        db.session.commit()
    return created

def close_expired_sessions():
    now = datetime.now()
    sessions = AttendanceSession.query.filter(
        AttendanceSession.session_date == date.today(),
        AttendanceSession.status == "OPEN"
    ).all()
    changed = False
    for sess in sessions:
        if now.time() > sess.end_time:
            roster = class_students(sess.course or "", sess.year_level or "", sess.major or "", sess.section or "")
            scanned = {a.student_id for a in sess.attendances}
            for st in roster:
                if st.id not in scanned:
                    db.session.add(Attendance(
                        student_id=st.id, session_id=sess.id,
                        scan_time=now, status="ABSENT"
                    ))
            sess.status = "CLOSED"
            changed = True
    if changed:
        db.session.commit()

def get_active_session():
    create_today_sessions()
    close_expired_sessions()
    now = datetime.now().time()
    return AttendanceSession.query.filter(
        AttendanceSession.session_date == date.today(),
        AttendanceSession.status == "OPEN",
        AttendanceSession.start_time <= now,
        AttendanceSession.end_time >= now
    ).order_by(AttendanceSession.id.desc()).first()

def determine_status(attendance_session):
    return "PRESENT" if datetime.now().time() < attendance_session.late_time else "LATE"

def qr_path(student_id):
    return QR_FOLDER / f"{str(student_id).strip()}.png"

def generate_student_qr(student_id):
    path = qr_path(student_id)
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(str(student_id))
    qr.make(fit=True)
    qr.make_image().save(path)
    return path

def delete_student_qr(student_id):
    path = qr_path(student_id)
    if path.exists():
        path.unlink()

def db_columns(table):
    con = sqlite3.connect(get_db_path())
    try:
        return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    finally:
        con.close()

def get_db_path():
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        p = uri.replace("sqlite:///", "", 1)
        return str((Path(app.instance_path) / p).resolve())
    return str((BASE_DIR / "brand_new_attendance.db").resolve())

def migrate_existing_database():
    db.create_all()
    con = sqlite3.connect(get_db_path())
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        migrations = {
            "student": [
                ("major", "VARCHAR(100)"),
            ],
            "attendance_session": [
                ("schedule_id", "INTEGER"),
                ("course", "VARCHAR(100)"),
                ("year_level", "VARCHAR(50)"),
                ("major", "VARCHAR(100)"),
                ("section", "VARCHAR(50)")
            ],
            "assessments": [
                ("assessment_name", "VARCHAR(150)"),
                ("weight", "FLOAT DEFAULT 0"),
                ("config_id", "INTEGER"),
                ("course", "VARCHAR(100)"),
                ("year_level", "VARCHAR(50)"),
                ("major", "VARCHAR(100)"),
                ("section", "VARCHAR(50)")
            ]
        }
        for table, cols in migrations.items():
            if table not in tables:
                continue
            existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
            for col, typ in cols:
                if col not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        con.commit()
    finally:
        con.close()
    db.session.expire_all()

BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;min-height:100vh;background:#eef4ff;color:#172033}
.topbar{background:#0f172a;color:white;padding:15px 25px;display:flex;justify-content:space-between;align-items:center}.brand{font-size:20px;font-weight:bold}nav{display:flex;gap:6px;flex-wrap:wrap}nav a{color:white;text-decoration:none;padding:9px 11px;border-radius:7px}nav a:hover{background:#334155}.menu{display:none;background:transparent;border:0;color:white;font-size:25px}
.container{width:94%;max-width:1250px;margin:30px auto}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;gap:15px;flex-wrap:wrap}.card,.stat{background:white;padding:22px;border-radius:15px;margin-bottom:20px;box-shadow:0 3px 15px rgba(0,0,0,.08)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-bottom:20px}.stat span{color:#64748b}.stat strong{display:block;font-size:30px;margin-top:8px}.present{color:#15803d}.late{color:#b45309}.absent{color:#b91c1c}
.btn{border:none;padding:10px 15px;border-radius:8px;cursor:pointer;text-decoration:none;display:inline-block;font-weight:bold}.primary{background:#2563eb;color:white}.secondary{background:#e2e8f0;color:#1e293b}.danger{background:#dc2626;color:white}.warning-btn{background:#d97706;color:white}.small{padding:6px 10px;font-size:12px}.full{width:100%}
input,select{width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:10px;font-size:15px}label{display:block;font-weight:bold;margin:10px 0 5px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #e2e8f0}th{background:#f8fafc}.table-container{overflow-x:auto}.badge{padding:5px 9px;border-radius:20px;font-size:12px;font-weight:bold}.badge.present{background:#dcfce7;color:#166534}.badge.late{background:#fef3c7;color:#92400e}.badge.absent{background:#fee2e2;color:#991b1b}.badge.active{background:#dcfce7;color:#166534}.badge.inactive{background:#fee2e2;color:#991b1b}
.alert{padding:13px;border-radius:8px;margin-bottom:20px}.alert.success{background:#dcfce7;color:#166534}.alert.danger{background:#fee2e2;color:#991b1b}.alert.warning{background:#fef3c7;color:#92400e}.alert.info{background:#dbeafe;color:#1e40af}.session-banner{background:#dbeafe;color:#1e40af;padding:15px;border-radius:10px;margin-bottom:20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}.form-card{max-width:850px}.form-actions{margin-top:20px;display:flex;justify-content:flex-end;gap:10px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:15px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.check-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:15px}.check-grid label{font-weight:normal;background:#f8fafc;padding:9px;border-radius:8px;margin:0}.check-grid input{width:auto;margin:0 6px 0 0}.scanner{max-width:700px;margin:auto}#reader{width:100%;min-height:280px}.scanner-status{text-align:center;padding:15px;margin-top:15px;border-radius:8px;background:#f1f5f9;font-weight:bold}.login-page{min-height:100vh;display:flex;align-items:center;justify-content:center}.login-card{background:white;width:90%;max-width:420px;padding:30px;border-radius:18px;box-shadow:0 8px 30px rgba(0,0,0,.15)}.login-card h1{text-align:center}.muted{color:#64748b}.empty{text-align:center;padding:30px;color:#64748b}.qr-card{text-align:center;max-width:520px;margin:auto}.qr-card img{width:300px;max-width:80%;height:auto;border:10px solid white;border-radius:10px}.student-profile{display:grid;grid-template-columns:1fr 1fr;gap:20px}.result{background:white;padding:20px;border-radius:15px;margin-top:20px;text-align:center}.hidden{display:none}.score-input{min-width:110px}.class-filter{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.help{background:#f8fafc;border-left:4px solid #2563eb;padding:12px;margin:12px 0;border-radius:6px}
@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}.grid2,.grid3,.class-filter{grid-template-columns:1fr 1fr}.check-grid{grid-template-columns:repeat(2,1fr)}nav{display:none;position:absolute;top:60px;left:0;right:0;background:#0f172a;flex-direction:column;padding:15px;z-index:10}nav.show{display:flex}.menu{display:block}}
@media(max-width:550px){.container{width:92%}.stats,.grid2,.grid3,.class-filter{grid-template-columns:1fr}.check-grid{grid-template-columns:1fr}.student-profile{grid-template-columns:1fr}}
</style>
</head>
<body>
{% if session.user_id %}
<header class="topbar"><div class="brand">Attendance Checker</div><button class="menu" onclick="toggleMenu()">☰</button>
<nav id="nav">
<a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('scanner') }}">Scanner</a><a href="{{ url_for('students') }}">Students</a><a href="{{ url_for('attendance') }}">Attendance</a><a href="{{ url_for('schedules') }}">Schedules</a><a href="{{ url_for('sessions') }}">Sessions</a><a href="{{ url_for('assessments') }}">Assessments</a><a href="{{ url_for('logout') }}">Logout</a>
</nav></header>
{% endif %}
<div class="container">{% with messages=get_flashed_messages(with_categories=true) %}{% for category,message in messages %}<div class="alert {{ category }}">{{ message }}</div>{% endfor %}{% endwith %}{{ content|safe }}</div>
<script>function toggleMenu(){const n=document.getElementById('nav');if(n)n.classList.toggle('show');}</script>
</body></html>
"""

def render_page(content, title="Attendance Checker", **context):
    return render_template_string(BASE_HTML, content=render_template_string(content, **context), title=title)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        user=User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear(); session["user_id"]=user.id; session["username"]=user.username; session["role"]=user.role
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.","danger")
    content="""<div class="login-page"><div class="login-card"><h1>Attendance Checker</h1><p class="muted">Login to your account</p><form method="POST"><label>Username</label><input name="username" required><label>Password</label><input type="password" name="password" id="pwd" required><p><input type="checkbox" style="width:auto" onclick="document.getElementById('pwd').type=this.checked?'text':'password'"> Show Password</p><button class="btn primary full">Log In</button></form><div style="text-align:center;margin-top:15px">No account? <a href="{{ url_for('register') }}">Register</a><br><br><a href="{{ url_for('forgot_password') }}">Forgot Password?</a></div></div></div>"""
    return render_page(content,"Login")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username=request.form.get("username","").strip(); email=request.form.get("email","").strip().lower()
        password=request.form.get("password","").strip(); confirm=request.form.get("confirm_password","").strip()
        if not all([username,email,password,confirm]): flash("Fill all fields.","danger"); return redirect(url_for("register"))
        if password!=confirm: flash("Passwords do not match.","danger"); return redirect(url_for("register"))
        if User.query.filter_by(username=username).first(): flash("Username taken.","danger"); return redirect(url_for("register"))
        if User.query.filter_by(email=email).first(): flash("Email already registered.","danger"); return redirect(url_for("register"))
        u=User(username=username,email=email); u.set_password(password); db.session.add(u); db.session.commit()
        flash("Account created! Please log in.","success"); return redirect(url_for("login"))
    content="""<div class="login-page"><div class="login-card"><h1>Register Account</h1><form method="POST"><label>Username</label><input name="username" required><label>Email</label><input type="email" name="email" required><label>Password</label><input type="password" name="password" required><label>Confirm Password</label><input type="password" name="confirm_password" required><button class="btn primary full">Create Account</button></form><div style="text-align:center;margin-top:15px"><a href="{{ url_for('login') }}">Back to Login</a></div></div></div>"""
    return render_page(content,"Register")

@app.route("/forgot-password",methods=["GET","POST"])
def forgot_password():
    if request.method=="POST":
        step=request.form.get("step","1")
        if step=="1":
            email=request.form.get("email","").strip().lower(); user=User.query.filter_by(email=email).first()
            if not user: flash("No account found with that email.","danger"); return redirect(url_for("forgot_password"))
            code=''.join(random.choices(string.digits,k=6)); session["reset_email"]=email; session["reset_code"]=code
            if send_reset_email(email,code):
                flash("Verification code sent to your email.","success")
                return render_page("""<div class="login-page"><div class="login-card"><h1>Enter Code</h1><form method="POST"><input type="hidden" name="step" value="2"><label>6-Digit Code</label><input name="reset_code" maxlength="6" required><button class="btn primary full">Verify</button></form></div></div>""","Verify Code")
            flash("Failed to send email.","danger")
        elif step=="2":
            if request.form.get("reset_code","").strip()==session.get("reset_code"):
                return render_page("""<div class="login-page"><div class="login-card"><h1>Reset Password</h1><form method="POST"><input type="hidden" name="step" value="3"><label>New Password</label><input type="password" name="new_password" required><label>Confirm Password</label><input type="password" name="confirm_password" required><button class="btn primary full">Reset Password</button></form></div></div>""","Reset Password")
            flash("Wrong code.","danger")
        elif step=="3":
            new=request.form.get("new_password","").strip(); confirm=request.form.get("confirm_password","").strip(); email=session.get("reset_email")
            if new!=confirm: flash("Passwords do not match.","danger"); return redirect(url_for("forgot_password"))
            user=User.query.filter_by(email=email).first()
            if user: user.set_password(new); db.session.commit()
            session.clear(); flash("Password reset! Please log in.","success"); return redirect(url_for("login"))
    return render_page("""<div class="login-page"><div class="login-card"><h1>Forgot Password</h1><form method="POST"><input type="hidden" name="step" value="1"><label>Your Email</label><input type="email" name="email" required><button class="btn primary full">Send Code</button></form></div></div>""","Forgot Password")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    active=get_active_session(); total=Student.query.filter_by(active=True).count()
    if active:
        present=Attendance.query.filter_by(session_id=active.id,status="PRESENT").count()
        late=Attendance.query.filter_by(session_id=active.id,status="LATE").count()
        roster_count=len(class_students(active.course or "",active.year_level or "",active.major or "",active.section or ""))
        absent=max(roster_count-present-late,0)
    else:
        present=late=0; absent=0
    recent=Attendance.query.join(Student).order_by(Attendance.scan_time.desc()).limit(10).all()
    banner=f"""<div class="session-banner"><strong>Active Class: {active.name}</strong><span>{active.course} • {active.year_level} • {active.major or 'No Major'}<br>{active.start_time.strftime('%I:%M %p')} - {active.end_time.strftime('%I:%M %p')}</span></div>""" if active else '<div class="alert warning">No class is currently active. Scheduled classes are created automatically on their scheduled days.</div>'
    rows="".join(f"<tr><td>{a.student.student_id}</td><td>{a.student.full_name}</td><td>{a.attendance_session.name}</td><td>{a.scan_time.strftime('%I:%M %p')}</td><td><span class='badge {a.status.lower()}'>{a.status}</span></td></tr>" for a in recent) or "<tr><td colspan='5' class='empty'>No scans yet.</td></tr>"
    content=f"""<div class="page-header"><div><h1>Dashboard</h1><p class="muted">Welcome, {session.get('username')}</p></div><a href="{url_for('scanner')}" class="btn primary">Open Scanner</a></div>{banner}<div class="stats"><div class="stat"><span>Total Active Students</span><strong>{total}</strong></div><div class="stat"><span>Present</span><strong class="present">{present}</strong></div><div class="stat"><span>Late</span><strong class="late">{late}</strong></div><div class="stat"><span>Absent</span><strong class="absent">{absent}</strong></div></div><div class="card"><h2>Recent Scans</h2><div class="table-container"><table><tr><th>ID</th><th>Name</th><th>Class</th><th>Time</th><th>Status</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Dashboard")

@app.route("/students")
@login_required
def students():
    search=request.args.get("search","").strip(); q=Student.query
    if search: q=q.filter((Student.student_id.ilike(f"%{search}%"))|(Student.full_name.ilike(f"%{search}%")))
    items=q.order_by(Student.full_name).all()
    rows="".join(f"""<tr><td>{s.student_id}</td><td>{s.full_name}</td><td>{s.course}</td><td>{s.year_level}</td><td>{s.major or ""}</td><td>{s.section or ""}</td><td><span class="badge {'active' if s.active else 'inactive'}">{'ACTIVE' if s.active else 'INACTIVE'}</span></td><td><a href="{url_for('student_profile',id=s.id)}" class="btn small primary">QR</a> <a href="{url_for('edit_student',id=s.id)}" class="btn small secondary">Edit</a></td></tr>""" for s in items) or "<tr><td colspan='8' class='empty'>No students found.</td></tr>"
    content=f"""<div class="page-header"><h1>Students</h1><a href="{url_for('add_student')}" class="btn primary">+ Add Student</a></div><div class="card"><form method="GET"><input name="search" value="{search}" placeholder="Search Student ID or Name"><button class="btn secondary">Search</button></form></div><div class="card"><div class="table-container"><table><tr><th>ID</th><th>Name</th><th>Course</th><th>Year</th><th>Major</th><th>Section</th><th>Status</th><th>Action</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Students")

@app.route("/students/add",methods=["GET","POST"])
@login_required
def add_student():
    if request.method=="POST":
        sid=request.form.get("student_id","").strip(); name=request.form.get("full_name","").strip(); course=request.form.get("course","").strip(); year=request.form.get("year_level","").strip(); major=request.form.get("major","").strip(); section=request.form.get("section","").strip()
        if not all([sid,name,course,year]): flash("Student ID, name, course, and year level are required.","danger"); return redirect(url_for("add_student"))
        if Student.query.filter_by(student_id=sid).first(): flash("Student ID exists.","danger"); return redirect(url_for("add_student"))
        s=Student(student_id=sid,full_name=name,course=course,year_level=year,major=major or None,section=section or None,active=request.form.get('active','1')=='1'); db.session.add(s); db.session.commit(); generate_student_qr(sid)
        flash("Student added and QR generated.","success"); return redirect(url_for("student_profile",id=s.id))
    content="""<div class="page-header"><h1>Add Student</h1></div><div class="card form-card"><form method="POST"><div class="grid2"><div><label>Student ID</label><input name="student_id" required></div><div><label>Full Name</label><input name="full_name" required></div><div><label>Course / Program</label><input name="course" placeholder="BSIT" required></div><div><label>Year Level</label><input name="year_level" placeholder="2nd Year" required></div><div><label>Major</label><input name="major" placeholder="Computer Technology"></div><div><label>Section</label><input name="section" placeholder="A"></div></div><label>Status</label><select name="active"><option value="1">Active</option><option value="0">Inactive</option></select><div class="form-actions"><a href="{{ url_for('students') }}" class="btn secondary">Cancel</a><button class="btn primary">Add Student</button></div></form></div>"""
    return render_page(content,"Add Student")

@app.route("/students/profile/<int:id>")
@login_required
def student_profile(id):
    s=Student.query.get_or_404(id)
    if not qr_path(s.student_id).exists(): generate_student_qr(s.student_id)
    content=f"""<div class="page-header"><h1>{s.full_name}</h1><a href="{url_for('students')}" class="btn secondary">Back</a></div><div class="student-profile"><div class="card"><p><strong>ID:</strong> {s.student_id}</p><p><strong>Course:</strong> {s.course}</p><p><strong>Year:</strong> {s.year_level}</p><p><strong>Major:</strong> {s.major or 'Not set'}</p><p><strong>Section:</strong> {s.section or 'Not set'}</p><p><strong>Status:</strong> {'ACTIVE' if s.active else 'INACTIVE'}</p></div><div class="card qr-card"><h3>QR Code</h3><img src="{url_for('student_qr',student_id=s.student_id)}"><p class="muted">ID: {s.student_id}</p><a class="btn primary" href="{url_for('student_qr',student_id=s.student_id)}" download>Download</a></div></div>"""
    return render_page(content,"Profile")

@app.route("/qr_codes/<path:student_id>.png")
@login_required
def student_qr(student_id):
    return send_from_directory(QR_FOLDER,f"{student_id}.png")

@app.route("/students/edit/<int:id>",methods=["GET","POST"])
@login_required
def edit_student(id):
    s=Student.query.get_or_404(id)
    if request.method=="POST":
        old=s.student_id; new=request.form.get("student_id","").strip()
        if not new: flash("Student ID is required.","danger"); return redirect(url_for("edit_student",id=id))
        duplicate=Student.query.filter(Student.student_id==new,Student.id!=s.id).first()
        if duplicate: flash("Student ID already exists.","danger"); return redirect(url_for("edit_student",id=id))
        s.student_id=new; s.full_name=request.form.get("full_name","").strip(); s.course=request.form.get("course","").strip(); s.year_level=request.form.get("year_level","").strip(); s.major=request.form.get("major","").strip() or None; s.section=request.form.get("section","").strip() or None; s.active=request.form.get("active")=="1"
        db.session.commit()
        if old!=new: delete_student_qr(old)
        generate_student_qr(new); flash("Student updated.","success"); return redirect(url_for("students"))
    content=f"""<div class="page-header"><h1>Edit Student</h1></div><div class="card form-card"><form method="POST"><label>Student ID</label><input name="student_id" value="{s.student_id}" required><label>Full Name</label><input name="full_name" value="{s.full_name}" required><div class="grid2"><div><label>Course</label><input name="course" value="{s.course}" required></div><div><label>Year Level</label><input name="year_level" value="{s.year_level}" required></div><div><label>Major</label><input name="major" value="{s.major or ''}"></div><div><label>Section</label><input name="section" value="{s.section or ''}"></div></div><label>Status</label><select name="active"><option value="1" {'selected' if s.active else ''}>Active</option><option value="0" {'selected' if not s.active else ''}>Inactive</option></select><div class="form-actions"><a href="{url_for('students')}" class="btn secondary">Cancel</a><button class="btn primary">Save</button></div></form></div>"""
    return render_page(content,"Edit Student")

@app.route("/schedules")
@login_required
def schedules():
    items=AttendanceSchedule.query.order_by(AttendanceSchedule.active.desc(),AttendanceSchedule.name).all()
    create_today_sessions()
    rows=""
    for s in items:
        buttons=f"""<a class="btn small secondary" href="{url_for('edit_schedule',id=s.id)}">Edit</a> <form method="POST" action="{url_for('toggle_schedule',id=s.id)}" style="display:inline"><button class="btn small {'danger' if s.active else 'primary'}">{'Deactivate' if s.active else 'Activate'}</button></form> <form method="POST" action="{url_for('delete_schedule',id=s.id)}" style="display:inline" onsubmit="return confirm('Delete this schedule? Existing attendance sessions will be preserved.')"><button class="btn small danger">Delete</button></form>"""
        rows+=f"<tr><td>{s.name}</td><td>{s.course}</td><td>{s.year_level}</td><td>{s.major or ''}</td><td>{s.section or ''}</td><td>{s.days}</td><td>{s.start_time.strftime('%I:%M %p')}</td><td>{s.late_time.strftime('%I:%M %p')}</td><td>{s.end_time.strftime('%I:%M %p')}</td><td><span class='badge {'active' if s.active else 'inactive'}'>{'ACTIVE' if s.active else 'INACTIVE'}</span></td><td>{buttons}</td></tr>"
    content=f"""<div class="page-header"><div><h1>Class Schedules</h1><p class="muted">Create a class once. Attendance sessions are automatically generated on the selected days.</p></div><a href="{url_for('add_schedule')}" class="btn primary">+ Add Schedule</a></div><div class="card"><div class="table-container"><table><tr><th>Name</th><th>Course</th><th>Year</th><th>Major</th><th>Section</th><th>Days</th><th>Start</th><th>Late</th><th>End</th><th>Status</th><th>Action</th></tr>{rows or "<tr><td colspan='11' class='empty'>No schedules yet.</td></tr>"}</table></div></div>"""
    return render_page(content,"Schedules")

def schedule_form_content(s=None):
    editing=s is not None
    vals={"name":s.name if s else "","course":s.course if s else "","year":s.year_level if s else "","major":s.major if s else "","section":s.section if s else "","start":s.start_time.strftime("%H:%M") if s else "08:00","late":s.late_time.strftime("%H:%M") if s else "08:15","end":s.end_time.strftime("%H:%M") if s else "10:00"}
    chosen=selected_days(s.days) if s else []
    checks="".join(f"<label><input type='checkbox' name='days' value='{d}' {'checked' if d in chosen else ''}>{d}</label>" for d in DAY_NAMES)
    action=url_for("edit_schedule",id=s.id) if editing else url_for("add_schedule")
    return f"""<div class="page-header"><h1>{'Edit' if editing else 'Add'} Class Schedule</h1></div><div class="card form-card"><div class="help">Set the recurring class here once. The system will automatically create/use the attendance session on every selected weekday.</div><form method="POST"><label>Schedule Name</label><input name="name" value="{vals['name']}" placeholder="Computer Programming" required><div class="grid2"><div><label>Course / Program</label><input name="course" value="{vals['course']}" placeholder="BSIT" required></div><div><label>Year Level</label><input name="year_level" value="{vals['year']}" placeholder="2nd Year" required></div><div><label>Major</label><input name="major" value="{vals['major']}" placeholder="Computer Technology"></div><div><label>Section (Optional)</label><input name="section" value="{vals['section']}" placeholder="A"></div></div><label>Days</label><div class="check-grid">{checks}</div><div class="grid3"><div><label>Start Time</label><input type="time" name="start_time" value="{vals['start']}" required></div><div><label>Late After</label><input type="time" name="late_time" value="{vals['late']}" required></div><div><label>End Time</label><input type="time" name="end_time" value="{vals['end']}" required></div></div><div class="form-actions"><a href="{url_for('schedules')}" class="btn secondary">Cancel</a><button class="btn primary">Save Schedule</button></div></form></div>"""

@app.route("/schedules/add",methods=["GET","POST"])
@login_required
def add_schedule():
    if request.method=="POST":
        days=request.form.getlist("days")
        if not days: flash("Select at least one day.","danger"); return redirect(url_for("add_schedule"))
        try: st=parse_time(request.form.get("start_time")); lt=parse_time(request.form.get("late_time")); et=parse_time(request.form.get("end_time"))
        except: flash("Invalid time.","danger"); return redirect(url_for("add_schedule"))
        if not(st<=lt<=et): flash("Start ≤ Late ≤ End.","danger"); return redirect(url_for("add_schedule"))
        s=AttendanceSchedule(name=request.form.get("name","").strip(),course=request.form.get("course","").strip(),year_level=request.form.get("year_level","").strip(),major=request.form.get("major","").strip() or None,section=request.form.get("section","").strip() or None,days=",".join(days),start_time=st,late_time=lt,end_time=et,active=True)
        if not s.name or not s.course or not s.year_level: flash("Schedule name, course, and year level are required.","danger"); return redirect(url_for("add_schedule"))
        db.session.add(s); db.session.commit(); create_today_sessions(); flash("Recurring schedule created.","success"); return redirect(url_for("schedules"))
    return render_page(schedule_form_content(),"Add Schedule")

@app.route("/schedules/edit/<int:id>",methods=["GET","POST"])
@login_required
def edit_schedule(id):
    s=AttendanceSchedule.query.get_or_404(id)
    if request.method=="POST":
        days=request.form.getlist("days")
        try: st=parse_time(request.form.get("start_time")); lt=parse_time(request.form.get("late_time")); et=parse_time(request.form.get("end_time"))
        except: flash("Invalid time.","danger"); return redirect(url_for("edit_schedule",id=id))
        if not days: flash("Select at least one day.","danger"); return redirect(url_for("edit_schedule",id=id))
        if not(st<=lt<=et): flash("Start ≤ Late ≤ End.","danger"); return redirect(url_for("edit_schedule",id=id))
        s.name=request.form.get("name","").strip(); s.course=request.form.get("course","").strip(); s.year_level=request.form.get("year_level","").strip(); s.major=request.form.get("major","").strip() or None; s.section=request.form.get("section","").strip() or None; s.days=",".join(days); s.start_time=st; s.late_time=lt; s.end_time=et
        db.session.commit(); flash("Schedule updated. Existing attendance sessions are preserved.","success"); return redirect(url_for("schedules"))
    return render_page(schedule_form_content(s),"Edit Schedule")

@app.route("/schedules/toggle/<int:id>",methods=["POST"])
@login_required
def toggle_schedule(id):
    s=AttendanceSchedule.query.get_or_404(id); s.active=not s.active; db.session.commit(); flash(f"Schedule {'activated' if s.active else 'deactivated'}.","success"); return redirect(url_for("schedules"))

@app.route("/schedules/delete/<int:id>",methods=["POST"])
@login_required
def delete_schedule(id):
    s=AttendanceSchedule.query.get_or_404(id)
    db.session.delete(s); db.session.commit(); flash("Schedule deleted. Existing attendance records were preserved.","success"); return redirect(url_for("schedules"))

@app.route("/sessions")
@login_required
def sessions():
    create_today_sessions(); close_expired_sessions()
    items=AttendanceSession.query.order_by(AttendanceSession.session_date.desc(),AttendanceSession.id.desc()).limit(100).all()
    rows="".join(f"""<tr><td>{x.session_date}</td><td>{x.name}</td><td>{x.course or ''}</td><td>{x.year_level or ''}</td><td>{x.start_time.strftime('%I:%M %p')}</td><td>{x.end_time.strftime('%I:%M %p')}</td><td><span class="badge {'active' if x.status=='OPEN' else 'inactive'}">{x.status}</span></td><td>{('<form method="POST" action="'+url_for('close_session',id=x.id)+'"><button class="btn small danger">Close</button></form>') if x.status=='OPEN' else 'Completed'}</td></tr>""" for x in items) or "<tr><td colspan='8' class='empty'>No sessions.</td></tr>"
    content=f"""<div class="page-header"><div><h1>Attendance Sessions</h1><p class="muted">Recurring schedules create these automatically.</p></div></div><div class="card"><div class="table-container"><table><tr><th>Date</th><th>Class</th><th>Course</th><th>Year</th><th>Start</th><th>End</th><th>Status</th><th>Action</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Sessions")

@app.route("/sessions/create", methods=["POST"])
@login_required
def create_session():
    flash("Manual session creation has been replaced by recurring Class Schedules. Create the class once under Schedules.", "info")
    return redirect(url_for("schedules"))

@app.route("/sessions/close/<int:id>",methods=["POST"])
@login_required
def close_session(id):
    sess=AttendanceSession.query.get_or_404(id)
    roster=class_students(sess.course or "",sess.year_level or "",sess.major or "",sess.section or "")
    scanned={a.student_id for a in sess.attendances}; now=datetime.now()
    for st in roster:
        if st.id not in scanned: db.session.add(Attendance(student_id=st.id,session_id=sess.id,scan_time=now,status="ABSENT"))
    sess.status="CLOSED"; db.session.commit(); flash("Session closed. Unscanned class members marked ABSENT.","success"); return redirect(url_for("sessions"))

@app.route("/scan",methods=["POST"])
@login_required
def scan():
    create_today_sessions(); close_expired_sessions()
    data=request.get_json() or {}; sid=str(data.get("student_id","")).strip()
    if not sid: return jsonify({"success":False,"message":"No ID provided"})
    active=get_active_session()
    if not active: return jsonify({"success":False,"message":"No active scheduled class right now."})
    student=Student.query.filter_by(student_id=sid,active=True).first()
    if not student: return jsonify({"success":False,"message":"Student not found"})
    roster=class_students(active.course or "",active.year_level or "",active.major or "",active.section or "")
    if student.id not in {s.id for s in roster}: return jsonify({"success":False,"message":"Student is not enrolled in the currently active class.","student":{"name":student.full_name,"student_id":student.student_id}})
    existing=Attendance.query.filter_by(student_id=student.id,session_id=active.id).first()
    if existing: return jsonify({"success":False,"message":"Already scanned","student":{"name":student.full_name,"student_id":student.student_id}})
    status=determine_status(active)
    db.session.add(Attendance(student_id=student.id,session_id=active.id,scan_time=datetime.now(),status=status)); db.session.commit()
    now=datetime.now()
    return jsonify({"success":True,"status":status,"date":date.today().strftime("%B %d, %Y"),"time":now.strftime("%I:%M:%S %p"),"student":{"name":student.full_name,"student_id":student.student_id,"course":student.course,"year":student.year_level,"major":student.major or "","section":student.section or ""}})

@app.route("/scanner")
@login_required
def scanner():
    active=get_active_session()
    banner=f"<div class='session-banner'><strong>Active Class: {active.name}</strong><span>{active.course} • {active.year_level} • {active.major or 'No Major'}<br>{active.start_time.strftime('%I:%M %p')} - {active.end_time.strftime('%I:%M %p')}</span></div>" if active else "<div class='alert warning'>No scheduled class is active right now.</div>"
    content=f"""<div class="scanner"><div class="page-header"><h1>QR Scanner</h1></div>{banner}<div class="card"><div id="reader"></div><div id="scannerStatus" class="scanner-status">Ready to scan QR Code...</div><div id="result" class="result hidden"><h2 id="resultTitle"></h2><h3 id="studentName"></h3><p id="studentId"></p><p id="studentCourse"></p><p id="studentClass"></p><div id="status" class="big-status"></div><p id="scanDate"></p><p id="scanTime"></p></div></div></div><script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script><script>
let processing=false;
function statusMsg(m){{document.getElementById('scannerStatus').textContent=m;}}
async function processScan(sid){{sid=String(sid||'').trim();if(!sid||processing)return;processing=true;statusMsg('Checking...');try{{const res=await fetch('{url_for('scan')}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{student_id:sid}})}});const d=await res.json();showResult(d);}}catch(e){{statusMsg('Server error.');}}setTimeout(()=>{{processing=false;statusMsg('Ready for next scan.');}},1500);}}
function showResult(d){{const r=document.getElementById('result');r.classList.remove('hidden');document.getElementById('resultTitle').textContent=d.success?'ATTENDANCE RECORDED':(d.message||'Scan failed');document.getElementById('status').textContent=d.success?d.status:'FAILED';document.getElementById('status').className='big-status '+(d.success?d.status.toLowerCase():'absent');if(d.student){{document.getElementById('studentName').textContent=d.student.name;document.getElementById('studentId').textContent='ID: '+d.student.student_id;document.getElementById('studentCourse').textContent='Course: '+d.student.course;document.getElementById('studentClass').textContent=d.student.year+' • '+(d.student.major||'')+' • '+(d.student.section||'');}}if(d.date)document.getElementById('scanDate').textContent='Date: '+d.date;if(d.time)document.getElementById('scanTime').textContent='Time: '+d.time;}}
const html5QrCode=new Html5Qrcode('reader');html5QrCode.start({{facingMode:'environment'}},{{fps:10,qrbox:{{width:250,height:250}}}},txt=>{{if(!processing)processScan(txt);}},()=>{{}}).catch(e=>statusMsg('Camera error: '+e.message));
</script>"""
    return render_page(content,"QR Scanner")

@app.route("/attendance")
@login_required
def attendance():
    records=Attendance.query.join(Student).join(AttendanceSession).order_by(Attendance.scan_time.desc()).all()
    rows="".join(f"<tr><td>{r.student.student_id}</td><td>{r.student.full_name}</td><td>{r.attendance_session.name}</td><td>{r.attendance_session.session_date}</td><td>{r.scan_time.strftime('%I:%M %p')}</td><td><span class='badge {r.status.lower()}'>{r.status}</span></td></tr>" for r in records) or "<tr><td colspan='6' class='empty'>No attendance records.</td></tr>"
    content=f"""<div class="page-header"><h1>Attendance Records</h1></div><div class="card"><div class="table-container"><table><tr><th>Student ID</th><th>Name</th><th>Class</th><th>Date</th><th>Time</th><th>Status</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Attendance")

def get_class_options():
    pairs=db.session.query(Student.course,Student.year_level,Student.major,Student.section).filter(Student.active==True).distinct().order_by(Student.course,Student.year_level,Student.major,Student.section).all()
    return pairs

@app.route("/assessments")
@login_required
def assessments():
    records=Assessment.query.join(Student).order_by(Assessment.assessment_date.desc(),Assessment.id.desc()).all()
    rows="".join(f"<tr><td>{a.assessment_date}</td><td>{a.student.student_id}</td><td>{a.student.full_name}</td><td>{a.course or a.student.course}</td><td>{a.assessment_name or a.assessment_type}</td><td>{a.score:.1f}/{a.total_score:.1f}</td><td>{a.percentage:.1f}%</td><td>{(a.weight or 0):.1f}%</td></tr>" for a in records) or "<tr><td colspan='8' class='empty'>No assessments yet.</td></tr>"
    content=f"""<div class="page-header"><div><h1>Assessments / Grades</h1><p class="muted">Select a class and assessment. The student roster comes automatically from the Student database.</p></div><a href="{url_for('add_assessment')}" class="btn primary">+ Class Assessment</a></div><div class="card"><div class="table-container"><table><tr><th>Date</th><th>ID</th><th>Student</th><th>Class</th><th>Assessment</th><th>Score</th><th>Percentage</th><th>Weight</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Assessments")

@app.route("/assessments/configs")
@login_required
def assessment_configs():
    items=AssessmentConfig.query.order_by(AssessmentConfig.course,AssessmentConfig.year_level,AssessmentConfig.assessment_name).all()
    rows="".join(f"<tr><td>{c.course}</td><td>{c.year_level}</td><td>{c.major or ''}</td><td>{c.section or ''}</td><td>{c.assessment_type}</td><td>{c.assessment_name}</td><td>{c.total_score:g}</td><td>{c.weight:g}%</td></tr>" for c in items) or "<tr><td colspan='8' class='empty'>No saved assessment configurations.</td></tr>"
    content=f"""<div class="page-header"><h1>Saved Assessment Configurations</h1><a href="{url_for('add_assessment')}" class="btn primary">+ New Assessment</a></div><div class="card"><div class="table-container"><table><tr><th>Course</th><th>Year</th><th>Major</th><th>Section</th><th>Type</th><th>Name</th><th>Total</th><th>Weight</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Assessment Configurations")

@app.route("/assessments/add",methods=["GET","POST"])
@login_required
def add_assessment():
    if request.method=="POST":
        course=request.form.get("course","").strip(); year=request.form.get("year_level","").strip(); major=request.form.get("major","").strip(); section=request.form.get("section","").strip()
        a_type=request.form.get("assessment_type","").strip(); name=request.form.get("assessment_name","").strip(); total_raw=request.form.get("total_score","").strip(); weight_raw=request.form.get("weight","0").strip(); a_date=request.form.get("assessment_date","").strip()
        try: total=float(total_raw); weight=float(weight_raw or 0); adate=datetime.strptime(a_date,"%Y-%m-%d").date()
        except: flash("Enter valid assessment details.","danger"); return redirect(url_for("add_assessment"))
        if total<=0 or weight<0 or weight>100: flash("Total score must be greater than 0 and weight must be between 0 and 100.","danger"); return redirect(url_for("add_assessment"))
        roster=class_students(course,year,major,section)
        if not roster: flash("No active students match that class.","danger"); return redirect(url_for("add_assessment"))
        config=AssessmentConfig.query.filter_by(course=course,year_level=year,major=major or None,section=section or None,assessment_type=a_type,assessment_name=name).first()
        if config:
            config.total_score=total; config.weight=weight; config.active=True
        else:
            config=AssessmentConfig(course=course,year_level=year,major=major or None,section=section or None,assessment_type=a_type,assessment_name=name,total_score=total,weight=weight,active=True); db.session.add(config); db.session.flush()
        saved=0
        for st in roster:
            raw=request.form.get(f"score_{st.id}","").strip()
            if raw=="":
                continue
            try: score=float(raw)
            except: continue
            if score<0 or score>total:
                flash(f"Invalid score for {st.full_name}. Score must be between 0 and {total:g}.","danger"); db.session.rollback(); return redirect(url_for("add_assessment"))
            existing=Assessment.query.filter_by(student_id=st.id,assessment_date=adate,assessment_type=a_type,assessment_name=name).first()
            if existing:
                existing.score=score; existing.total_score=total; existing.percentage=round((score/total)*100,2); existing.weight=weight; existing.config_id=config.id; existing.course=course; existing.year_level=year; existing.major=major or None; existing.section=section or None
            else:
                db.session.add(Assessment(student_id=st.id,assessment_type=a_type,assessment_name=name,score=score,total_score=total,percentage=round((score/total)*100,2),assessment_date=adate,weight=weight,config_id=config.id,course=course,year_level=year,major=major or None,section=section or None))
            saved+=1
        db.session.commit(); flash(f"Assessment saved for {saved} student(s). Configuration saved for reuse.","success"); return redirect(url_for("assessments"))
    classes=get_class_options()
    class_opts="<option value=''>Select class</option>"+"".join(f"<option data-course='{c}' data-year='{y}' data-major='{m or ''}' data-section='{s or ''}' value='{c}|{y}|{m or ''}|{s or ''}'>{c} • {y} • {m or 'No Major'} • {s or 'No Section'}</option>" for c,y,m,s in classes)
    types="".join(f"<option>{x}</option>" for x in ASSESSMENT_TYPES)
    content=f"""<div class="page-header"><h1>Class-Based Assessment</h1><a href="{url_for('assessment_configs')}" class="btn secondary">Saved Configurations</a></div><div class="card"><div class="help">Choose the class. Active students are loaded automatically. When an assessment with the same class, type, and name already exists, its saved total score and weight are reused.</div><label>Class / Cohort</label><select id="classSelect" onchange="loadClass()" required>{class_opts}</select><form method="POST" id="gradeForm"><input type="hidden" name="course" id="course"><input type="hidden" name="year_level" id="year_level"><input type="hidden" name="major" id="major"><input type="hidden" name="section" id="section"><div class="grid2"><div><label>Assessment Type</label><select name="assessment_type" id="assessmentType" onchange="loadConfig()" required>{types}</select></div><div><label>Assessment Name</label><input name="assessment_name" id="assessmentName" placeholder="Quiz 1" onblur="loadConfig()" required></div><div><label>Total Score</label><input type="number" step="0.01" name="total_score" id="totalScore" required></div><div><label>Percentage / Weight</label><input type="number" step="0.01" min="0" max="100" name="weight" id="weight" value="0" required></div><div><label>Assessment Date</label><input type="date" name="assessment_date" value="{date.today()}" required></div></div><div id="roster" class="card"><p class="muted">Select a class to load students.</p></div><div class="form-actions"><a href="{url_for('assessments')}" class="btn secondary">Cancel</a><button class="btn primary">Save All Scores</button></div></form></div>
<script>
function loadClass(){{
 const o=document.getElementById('classSelect').selectedOptions[0]; if(!o||!o.value)return;
 const p=o.value.split('|'); document.getElementById('course').value=p[0];document.getElementById('year_level').value=p[1];document.getElementById('major').value=p[2];document.getElementById('section').value=p[3];
 loadRoster(); loadConfig();
}}
async function loadRoster(){{
 const q=new URLSearchParams({{course:document.getElementById('course').value,year_level:document.getElementById('year_level').value,major:document.getElementById('major').value,section:document.getElementById('section').value}});
 const r=await fetch('{url_for('api_class_students')}?'+q.toString()); const d=await r.json();
 let h='<div class="table-container"><table><tr><th>Student ID</th><th>Student Name</th><th>Score</th><th>Total Score</th><th>Percentage</th></tr>';
 if(!d.students.length)h+='<tr><td colspan="5" class="empty">No active students found for this class.</td></tr>';
 d.students.forEach(s=>h+=`<tr><td>${{s.student_id}}</td><td>${{s.full_name}}</td><td><input class="score-input" type="number" min="0" step="0.01" max="${{document.getElementById('totalScore').value||0}}" name="score_${{s.id}}" oninput="calc(this)"></td><td class="total-cell">${{document.getElementById('totalScore').value||'0'}}</td><td class="pct-cell">0.00%</td></tr>`);
 h+='</table></div>';document.getElementById('roster').innerHTML=h;
}}
function calc(el){{const row=el.closest('tr');const total=parseFloat(document.getElementById('totalScore').value)||0;row.querySelector('.total-cell').textContent=total;row.querySelector('.pct-cell').textContent=total?((parseFloat(el.value)||0)/total*100).toFixed(2)+'%':'0.00%';}}
async function loadConfig(){{
 const c=document.getElementById('course').value,y=document.getElementById('year_level').value,m=document.getElementById('major').value,s=document.getElementById('section').value,t=document.getElementById('assessmentType').value,n=document.getElementById('assessmentName').value;
 if(!c||!y||!n)return; const q=new URLSearchParams({{course:c,year_level:y,major:m,section:s,assessment_type:t,assessment_name:n}});
 const r=await fetch('{url_for('api_assessment_config')}?'+q.toString());const d=await r.json();
 if(d.found){{document.getElementById('totalScore').value=d.total_score;document.getElementById('weight').value=d.weight;loadRoster();}}
}}
document.getElementById('totalScore').addEventListener('input',()=>{{document.querySelectorAll('.score-input').forEach(calc);}});
</script>"""
    return render_page(content,"Class-Based Assessment")

@app.route("/api/class-students")
@login_required
def api_class_students():
    course=request.args.get("course","").strip(); year=request.args.get("year_level","").strip(); major=request.args.get("major","").strip(); section=request.args.get("section","").strip()
    items=class_students(course,year,major,section)
    return jsonify({"students":[{"id":s.id,"student_id":s.student_id,"full_name":s.full_name} for s in items]})

@app.route("/api/assessment-config")
@login_required
def api_assessment_config():
    c=request.args.get("course","").strip(); y=request.args.get("year_level","").strip(); m=request.args.get("major","").strip(); s=request.args.get("section","").strip(); t=request.args.get("assessment_type","").strip(); n=request.args.get("assessment_name","").strip()
    cfg=AssessmentConfig.query.filter_by(course=c,year_level=y,major=m or None,section=s or None,assessment_type=t,assessment_name=n,active=True).first()
    if not cfg:return jsonify({"found":False})
    return jsonify({"found":True,"total_score":cfg.total_score,"weight":cfg.weight})

with app.app_context():
    migrate_existing_database()

if __name__=="__main__":
    app.run(debug=True)
