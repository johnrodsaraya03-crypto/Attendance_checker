from flask import Flask, request, redirect, url_for, session, jsonify, Response, flash, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from functools import wraps
from pathlib import Path
import csv
import io
import os
import qrcode

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///attendance.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

BASE_DIR = Path(__file__).resolve().parent
QR_FOLDER = BASE_DIR / "qr_codes"
QR_FOLDER.mkdir(exist_ok=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
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
    major = db.Column(db.String(50), nullable=False)
    active = db.Column(db.Boolean, default=True)
    attendances = db.relationship(
        "Attendance",
        backref="student",
        lazy=True,
        cascade="all, delete-orphan"
    )

class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    late_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default="OPEN")
    attendances = db.relationship(
        "Attendance",
        backref="attendance_session",
        lazy=True,
        cascade="all, delete-orphan"
    )

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_session.id"), nullable=False)
    scan_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("student_id", "session_id", name="unique_student_session"),
    )

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def get_active_session():
    return AttendanceSession.query.filter(
        AttendanceSession.session_date == date.today(),
        AttendanceSession.status == "OPEN"
    ).order_by(AttendanceSession.id.desc()).first()

def determine_status(attendance_session):
    if datetime.now().time() < attendance_session.late_time:
        return "PRESENT"
    return "LATE"

def qr_path(student_id):
    safe_id = str(student_id).strip()
    return QR_FOLDER / f"{safe_id}.png"

def generate_student_qr(student_id):
    path = qr_path(student_id)
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4
    )
    qr.add_data(str(student_id))
    qr.make(fit=True)
    image = qr.make_image()
    image.save(path)
    return path

def delete_student_qr(student_id):
    path = qr_path(student_id)
    if path.exists():
        path.unlink()

BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:#f1f5f9;color:#1e293b}
.topbar{background:#0f172a;color:white;padding:15px 25px;display:flex;justify-content:space-between;align-items:center;position:relative}
.brand{font-size:20px;font-weight:bold}
nav{display:flex;gap:8px}
nav a{color:white;text-decoration:none;padding:9px 12px;border-radius:7px}
nav a:hover{background:#334155}
.menu{display:none;background:transparent;border:0;color:white;font-size:25px}
.container{width:94%;max-width:1200px;margin:30px auto}
.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px;gap:15px}
.card{background:white;padding:22px;border-radius:15px;margin-bottom:20px;box-shadow:0 3px 15px rgba(0,0,0,.06)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-bottom:20px}
.stat{background:white;padding:20px;border-radius:14px;box-shadow:0 3px 15px rgba(0,0,0,.06)}
.stat span{color:#64748b}.stat strong{display:block;font-size:30px;margin-top:8px}
.present{color:#15803d}.late{color:#b45309}.absent{color:#b91c1c}
.btn{border:none;padding:10px 15px;border-radius:8px;cursor:pointer;text-decoration:none;display:inline-block;font-weight:bold}
.primary{background:#2563eb;color:white}.secondary{background:#e2e8f0;color:#1e293b}.danger{background:#dc2626;color:white}
.small{padding:6px 10px;font-size:12px}.full{width:100%}
input,select{width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:8px;margin-bottom:10px;font-size:15px}
label{display:block;font-weight:bold;margin:10px 0 5px}
.filters{display:flex;gap:10px;flex-wrap:wrap}.filters input,.filters select{flex:1;min-width:150px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #e2e8f0}
th{background:#f8fafc}
.table-container{overflow-x:auto}
.badge{padding:5px 9px;border-radius:20px;font-size:12px;font-weight:bold}
.badge.present{background:#dcfce7;color:#166534}.badge.late{background:#fef3c7;color:#92400e}.badge.absent{background:#fee2e2;color:#991b1b}
.alert{padding:13px;border-radius:8px;margin-bottom:20px}.alert.success{background:#dcfce7;color:#166534}.alert.danger{background:#fee2e2;color:#991b1b}.alert.warning{background:#fef3c7;color:#92400e}
.session-banner{background:#dbeafe;color:#1e40af;padding:15px;border-radius:10px;margin-bottom:20px;display:flex;justify-content:space-between}
.form-card{max-width:650px}.form-actions{margin-top:20px;display:flex;justify-content:flex-end;gap:10px}
.scanner{max-width:700px;margin:auto}#reader{width:100%;min-height:280px}.scanner-status{text-align:center;padding:15px;margin-top:15px;border-radius:8px;background:#f1f5f9;font-weight:bold}
.result{margin-top:20px;padding:25px;background:white;border-radius:15px;text-align:center;box-shadow:0 3px 15px rgba(0,0,0,.06)}.result.hidden{display:none}
.big-status{display:inline-block;padding:10px 20px;border-radius:25px;font-size:20px;font-weight:bold}
.login-page{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f172a}
.login-card{background:white;width:90%;max-width:400px;padding:30px;border-radius:18px}.login-card h1{text-align:center}
.muted{color:#64748b}.empty{text-align:center;padding:30px;color:#64748b}
.qr-card{text-align:center;max-width:520px;margin:auto}.qr-card img{width:300px;max-width:80%;height:auto;border:10px solid white;border-radius:10px}
.qr-actions{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin-top:18px}
.student-profile{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:800px){.stats{grid-template-columns:repeat(2,1fr)}nav{display:none;position:absolute;top:60px;left:0;right:0;background:#0f172a;flex-direction:column;padding:15px;z-index:10}nav.show{display:flex}.menu{display:block}.session-banner{flex-direction:column;gap:5px}.student-profile{grid-template-columns:1fr}}
@media(max-width:500px){.container{width:92%;margin-top:20px}.page-header{flex-direction:column;align-items:flex-start}.stats{gap:8px}.stat{padding:15px}.stat strong{font-size:25px}.qr-card img{width:250px}}
</style>
</head>
<body>
{% if session.get("user_id") %}
<header class="topbar">
<div class="brand">Attendance Checker</div>
<button class="menu" onclick="toggleMenu()">☰</button>
<nav id="nav">
<a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('scanner') }}">Scanner</a>
<a href="{{ url_for('students') }}">Students</a>
<a href="{{ url_for('attendance') }}">Attendance</a>
<a href="{{ url_for('sessions') }}">Sessions</a>
<a href="{{ url_for('logout') }}">Logout</a>
</nav>
</header>
{% endif %}
<div class="container">
{% with messages = get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}
<div class="alert {{ category }}">{{ message }}</div>
{% endfor %}
{% endwith %}
{{ content|safe }}
</div>
<script>
function toggleMenu(){
    const nav=document.getElementById("nav");
    if(nav) nav.classList.toggle("show");
}
</script>
</body>
</html>
"""

def render_page(content, title="Attendance Checker", **context):
    return render_template_string(
        BASE_HTML,
        content=render_template_string(content, **context),
        title=title
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")

    content = """
    <div class="login-page">
    <div class="login-card">
    <h1>📋 Attendance Checker</h1>
    <p class="muted">Faculty / Admin Login</p>
    <form method="POST">
    <label>Username</label>
    <input type="text" name="username" required>
    <label>Password</label>
    <input type="password" name="password" required>
    <button class="btn primary full">Login</button>
    </form>
    </div>
    </div>
    """
    return render_page(content, "Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    active = get_active_session()
    total_students = Student.query.filter_by(active=True).count()

    if active:
        present = Attendance.query.filter_by(session_id=active.id, status="PRESENT").count()
        late = Attendance.query.filter_by(session_id=active.id, status="LATE").count()
    else:
        today_records = Attendance.query.join(AttendanceSession).filter(
            AttendanceSession.session_date == date.today()
        )
        present = today_records.filter(Attendance.status == "PRESENT").count()
        late = today_records.filter(Attendance.status == "LATE").count()

    absent = max(total_students - present - late, 0)
    recent = Attendance.query.join(Student).order_by(
        Attendance.scan_time.desc()
    ).limit(10).all()

    content = """
    <div class="page-header">
    <div>
    <h1>Dashboard</h1>
    <p class="muted">Welcome, {{ session.get("username") }}</p>
    </div>
    <a href="{{ url_for('scanner') }}" class="btn primary">Open Scanner</a>
    </div>

    {% if active %}
    <div class="session-banner">
    <strong>Active: {{ active.name }}</strong>
    <span>{{ active.start_time.strftime("%I:%M %p") }} - {{ active.end_time.strftime("%I:%M %p") }}</span>
    </div>
    {% else %}
    <div class="alert warning">No open attendance session today.</div>
    {% endif %}

    <div class="stats">
    <div class="stat"><span>Total Students</span><strong>{{ total_students }}</strong></div>
    <div class="stat"><span>Present</span><strong class="present">{{ present }}</strong></div>
    <div class="stat"><span>Late</span><strong class="late">{{ late }}</strong></div>
    <div class="stat"><span>Absent</span><strong class="absent">{{ absent }}</strong></div>
    </div>

    <div class="card">
    <div class="page-header">
    <h2>Recent Scans</h2>
    <a href="{{ url_for('attendance') }}" class="btn secondary">View All</a>
    </div>
    <div class="table-container">
    <table>
    <tr><th>ID</th><th>Name</th><th>Course</th><th>Time</th><th>Status</th></tr>
    {% for record in recent %}
    <tr>
    <td>{{ record.student.student_id }}</td>
    <td>{{ record.student.full_name }}</td>
    <td>{{ record.student.course }}</td>
    <td>{{ record.scan_time.strftime("%I:%M:%S %p") }}</td>
    <td><span class="badge {{ record.status|lower }}">{{ record.status }}</span></td>
    </tr>
    {% else %}
    <tr><td colspan="5" class="empty">No scans yet.</td></tr>
    {% endfor %}
    </table>
    </div>
    </div>
    """
    return render_page(
        content, "Dashboard", active=active, total_students=total_students,
        present=present, late=late, absent=absent, recent=recent
    )

@app.route("/students")
@login_required
def students():
    search = request.args.get("search", "").strip()
    query = Student.query
    if search:
        query = query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.full_name.ilike(f"%{search}%")
            )
        )

    student_list = query.order_by(Student.full_name).all()
    content = """
    <div class="page-header">
    <div>
    <h1>Students</h1>
    <p class="muted">Registered students</p>
    </div>
    <a href="{{ url_for('add_student') }}" class="btn primary">+ Add Student</a>
    </div>

    <div class="card">
    <form method="GET">
    <input type="text" name="search" value="{{ search }}" placeholder="Search Student ID or Name">
    <button class="btn secondary">Search</button>
    </form>
    </div>

    <div class="card">
    <div class="table-container">
    <table>
    <tr><th>Student ID</th><th>Name</th><th>Course</th><th>Year</th><th>major</th><th>Status</th><th>Action</th></tr>
    {% for student in student_list %}
    <tr>
    <td>{{ student.student_id }}</td>
    <td>{{ student.full_name }}</td>
    <td>{{ student.course }}</td>
    <td>{{ student.year_level }}</td>
    <td>{{ student.major }}</td>
    <td>
    {% if student.active %}
    <span class="badge present">ACTIVE</span>
    {% else %}
    <span class="badge absent">INACTIVE</span>
    {% endif %}
    </td>
    <td>
    <a href="{{ url_for('student_profile', id=student.id) }}" class="btn small primary">QR/Profile</a>
    <a href="{{ url_for('edit_student', id=student.id) }}" class="btn small secondary">Edit</a>
    {% if student.active %}
    <form method="POST" action="{{ url_for('delete_student', id=student.id) }}" style="display:inline">
    <button class="btn small danger" onclick="return confirm('Deactivate this student?')">Disable</button>
    </form>
    {% endif %}
    </td>
    </tr>
    {% else %}
    <tr><td colspan="7" class="empty">No students found.</td></tr>
    {% endfor %}
    </table>
    </div>
    </div>
    """
    return render_page(content, "Students", student_list=student_list, search=search)

@app.route("/students/add", methods=["GET", "POST"])
@login_required
def add_student():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        course = request.form.get("course", "").strip()
        year_level = request.form.get("year_level", "").strip()
        major = request.form.get("major", "").strip()

        if not all([student_id, full_name, course, year_level, major]):
            flash("Complete all fields.", "danger")
            return redirect(url_for("add_student"))

        if Student.query.filter_by(student_id=student_id).first():
            flash("Student ID already exists.", "danger")
            return redirect(url_for("add_student"))

        student = Student(
            student_id=student_id,
            full_name=full_name,
            course=course,
            year_level=year_level,
            major=major
        )
        db.session.add(student)
        db.session.commit()

        try:
            generate_student_qr(student.student_id)
        except Exception as e:
            db.session.delete(student)
            db.session.commit()
            flash(f"QR code generation failed: {e}", "danger")
            return redirect(url_for("add_student"))

        flash("Student registered successfully and QR code generated.", "success")
        return redirect(url_for("student_profile", id=student.id))

    content = """
    <div class="page-header"><h1>Add Student</h1></div>
    <div class="card form-card">
    <form method="POST">
    <label>Student ID</label>
    <input name="student_id" placeholder="Example: 2026-001" required>
    <p class="muted">The QR code will contain this exact Student ID.</p>

    <label>Full Name</label>
    <input name="full_name" required>

    <label>Course / Program</label>
    <input name="course" placeholder="BSIT" required>

    <label>Year Level</label>
    <input name="year_level" placeholder="2nd Year" required>

    <label>major</label>
    <input name="major" placeholder="A" required>

    <div class="form-actions">
    <a href="{{ url_for('students') }}" class="btn secondary">Cancel</a>
    <button class="btn primary">Register & Generate QR</button>
    </div>
    </form>
    </div>
    """
    return render_page(content, "Add Student")

@app.route("/students/profile/<int:id>")
@login_required
def student_profile(id):
    student = Student.query.get_or_404(id)
    if not qr_path(student.student_id).exists():
        generate_student_qr(student.student_id)

    content = """
    <div class="page-header">
    <div>
    <h1>Student Profile</h1>
    <p class="muted">QR attendance ID</p>
    </div>
    <a href="{{ url_for('students') }}" class="btn secondary">Back to Students</a>
    </div>

    <div class="student-profile">
    <div class="card">
    <h2>{{ student.full_name }}</h2>
    <p><strong>Student ID:</strong> {{ student.student_id }}</p>
    <p><strong>Course:</strong> {{ student.course }}</p>
    <p><strong>Year Level:</strong> {{ student.year_level }}</p>
    <p><strong>major:</strong> {{ student.major }}</p>
    <p><strong>Status:</strong>
    {% if student.active %}<span class="badge present">ACTIVE</span>
    {% else %}<span class="badge absent">INACTIVE</span>{% endif %}
    </p>
    </div>

    <div class="card qr-card">
    <h2>Student QR Code</h2>
    <img src="{{ url_for('student_qr', student_id=student.student_id) }}" alt="QR Code for {{ student.student_id }}">
    <p class="muted">This QR code contains: <strong>{{ student.student_id }}</strong></p>
    <div class="qr-actions">
    <a class="btn primary" href="{{ url_for('student_qr', student_id=student.student_id) }}" download="{{ student.student_id }}.png">Download QR Code</a>
    <button class="btn secondary" onclick="printQR()">Print QR Code</button>
    </div>
    </div>
    </div>

    <script>
    function printQR(){
        const img=document.querySelector(".qr-card img");
        const name={{ student.full_name|tojson }};
        const id={{ student.student_id|tojson }};
        const win=window.open("","_blank","width=500,height=650");
        win.document.write(`
        <html><head><title>QR Code - ${id}</title>
        <style>
        body{font-family:Arial;text-align:center;padding:30px}
        img{width:300px;max-width:90%}
        </style></head>
        <body>
        <h2>${name}</h2><p>Student ID: ${id}</p>
        <img src="${img.src}">
        <script>window.onload=function(){window.print();}<\/script>
        </body></html>`);
        win.document.close();
    }
    </script>
    """
    return render_page(content, "Student Profile", student=student)

@app.route("/qr_codes/<path:student_id>.png")
@login_required
def student_qr(student_id):
    path = qr_path(student_id)
    if not path.exists():
        generate_student_qr(student_id)
    return send_from_directory(QR_FOLDER, f"{student_id}.png")

@app.route("/students/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_student(id):
    student = Student.query.get_or_404(id)

    if request.method == "POST":
        old_student_id = student.student_id
        new_student_id = request.form.get("student_id", "").strip()
        new_name = request.form.get("full_name", "").strip()
        new_course = request.form.get("course", "").strip()
        new_year = request.form.get("year_level", "").strip()
        new_major = request.form.get("major", "").strip()

        if not all([new_student_id, new_name, new_course, new_year, new_major]):
            flash("Complete all fields.", "danger")
            return redirect(url_for("edit_student", id=id))

        duplicate = Student.query.filter(
            Student.student_id == new_student_id,
            Student.id != student.id
        ).first()
        if duplicate:
            flash("Student ID already exists.", "danger")
            return redirect(url_for("edit_student", id=id))

        student.student_id = new_student_id
        student.full_name = new_name
        student.course = new_course
        student.year_level = new_year
        student.major = new_major
        db.session.commit()

        if old_student_id != new_student_id:
            delete_student_qr(old_student_id)
        generate_student_qr(new_student_id)

        flash("Student updated and QR code synchronized.", "success")
        return redirect(url_for("student_profile", id=student.id))

    content = """
    <div class="page-header"><h1>Edit Student</h1></div>
    <div class="card form-card">
    <form method="POST">
    <label>Student ID</label>
    <input name="student_id" value="{{ student.student_id }}" required>
    <label>Full Name</label>
    <input name="full_name" value="{{ student.full_name }}" required>
    <label>Course</label>
    <input name="course" value="{{ student.course }}" required>
    <label>Year Level</label>
    <input name="year_level" value="{{ student.year_level }}" required>
    <label>major</label>
    <input name="major" value="{{ student.major }}" required>
    <div class="form-actions">
    <a href="{{ url_for('students') }}" class="btn secondary">Cancel</a>
    <button class="btn primary">Save Changes</button>
    </div>
    </form>
    </div>
    """
    return render_page(content, "Edit Student", student=student)

@app.route("/students/delete/<int:id>", methods=["POST"])
@login_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    student.active = False
    db.session.commit()
    flash("Student deactivated.", "success")
    return redirect(url_for("students"))

@app.route("/sessions")
@login_required
def sessions():
    sessions_list = AttendanceSession.query.order_by(
        AttendanceSession.session_date.desc(),
        AttendanceSession.id.desc()
    ).all()

    content = """
    <div class="page-header">
    <div>
    <h1>Attendance Sessions</h1>
    <p class="muted">Create the attendance period before scanning.</p>
    </div>
    </div>

    <div class="card">
    <h2>Create Session</h2>
    <form method="POST" action="{{ url_for('create_session') }}">
    <label>Session Name</label>
    <input name="name" placeholder="Morning Class" required>
    <label>Start Time</label>
    <input type="time" name="start_time" required>
    <label>Late After</label>
    <input type="time" name="late_time" required>
    <label>End Time</label>
    <input type="time" name="end_time" required>
    <button class="btn primary">Create Session</button>
    </form>
    </div>

    <div class="card">
    <h2>Session History</h2>
    <div class="table-container">
    <table>
    <tr><th>Date</th><th>Name</th><th>Start</th><th>Late After</th><th>End</th><th>Status</th><th>Action</th></tr>
    {% for item in sessions_list %}
    <tr>
    <td>{{ item.session_date }}</td>
    <td>{{ item.name }}</td>
    <td>{{ item.start_time.strftime("%I:%M %p") }}</td>
    <td>{{ item.late_time.strftime("%I:%M %p") }}</td>
    <td>{{ item.end_time.strftime("%I:%M %p") }}</td>
    <td><span class="badge {% if item.status == 'OPEN' %}present{% else %}absent{% endif %}">{{ item.status }}</span></td>
    <td>
    {% if item.status == "OPEN" %}
    <form method="POST" action="{{ url_for('close_session', id=item.id) }}">
    <button class="btn small danger" onclick="return confirm('Close session and mark unscanned students absent?')">Close</button>
    </form>
    {% else %}
    Completed
    {% endif %}
    </td>
    </tr>
    {% else %}
    <tr><td colspan="7" class="empty">No sessions.</td></tr>
    {% endfor %}
    </table>
    </div>
    </div>
    """
    return render_page(content, "Sessions", sessions_list=sessions_list)

@app.route("/sessions/create", methods=["POST"])
@login_required
def create_session():
    name = request.form.get("name", "").strip()
    start = request.form.get("start_time", "")
    late = request.form.get("late_time", "")
    end = request.form.get("end_time", "")

    try:
        start_time = datetime.strptime(start, "%H:%M").time()
        late_time = datetime.strptime(late, "%H:%M").time()
        end_time = datetime.strptime(end, "%H:%M").time()
    except ValueError:
        flash("Invalid time.", "danger")
        return redirect(url_for("sessions"))

    if not (start_time <= late_time <= end_time):
        flash("Time must be Start <= Late <= End.", "danger")
        return redirect(url_for("sessions"))

    existing = AttendanceSession.query.filter_by(
        session_date=date.today(),
        status="OPEN"
    ).first()
    if existing:
        flash("There is already an open session today.", "danger")
        return redirect(url_for("sessions"))

    new_session = AttendanceSession(
        name=name,
        session_date=date.today(),
        start_time=start_time,
        late_time=late_time,
        end_time=end_time,
        status="OPEN"
    )
    db.session.add(new_session)
    db.session.commit()
    flash("Attendance session created.", "success")
    return redirect(url_for("sessions"))

@app.route("/sessions/close/<int:id>", methods=["POST"])
@login_required
def close_session(id):
    attendance_session = AttendanceSession.query.get_or_404(id)
    students = Student.query.filter_by(active=True).all()
    existing_ids = {x.student_id for x in attendance_session.attendances}
    now = datetime.now()

    for student in students:
        if student.id not in existing_ids:
            db.session.add(
                Attendance(
                    student_id=student.id,
                    session_id=attendance_session.id,
                    scan_time=now,
                    status="ABSENT"
                )
            )

    attendance_session.status = "CLOSED"
    db.session.commit()
    flash("Session closed. Unscanned students were marked ABSENT.", "success")
    return redirect(url_for("sessions"))

@app.route("/scanner")
@login_required
def scanner():
    active = get_active_session()
    content = """
    <div class="scanner">
    <div class="page-header">
    <div>
    <h1>ID Scanner</h1>
    {% if active %}
    <p class="muted">Active Session: {{ active.name }}</p>
    {% else %}
    <p class="muted">No active session</p>
    {% endif %}
    </div>
    </div>

    {% if not active %}
    <div class="alert warning">Create an attendance session first.</div>
    {% endif %}

    <div class="card">
    <div id="reader"></div>
    <div id="scannerStatus" class="scanner-status">Ready to scan</div>

    <div style="margin-top:20px;text-align:center">
    <p class="muted">QR scanning is the primary attendance method. If camera access fails, use the manual fallback below.</p>
    <input id="manualId" placeholder="Enter Student ID" autocomplete="off">
    <button class="btn primary" onclick="manualScan()">Record Attendance</button>
    </div>
    </div>

    <div id="result" class="result hidden">
    <h2 id="resultTitle">Attendance Recorded</h2>
    <h3 id="studentName"></h3>
    <p id="studentId"></p>
    <p id="studentCourse"></p>
    <p id="studentmajor"></p>
    <div id="status" class="big-status"></div>
    <p id="scanDate"></p>
    <p id="scanTime"></p>
    </div>
    </div>

    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
    <script>
    let lastScan="";
    let lastScanTime=0;
    let processing=false;

    function statusMessage(message){
        document.getElementById("scannerStatus").textContent=message;
    }

    async function processScan(studentId){
        studentId=String(studentId || "").trim();

        if(!studentId){
            statusMessage("No Student ID detected.");
            return;
        }

        if(processing) return;
        processing=true;
        statusMessage("Checking Student ID...");

        try{
            const response=await fetch("{{ url_for('scan') }}",{
                method:"POST",
                headers:{"Content-Type":"application/json"},
                body:JSON.stringify({student_id:studentId})
            });

            const data=await response.json();
            showResult(data);
        }catch(error){
            statusMessage("Server connection error.");
        }finally{
            processing=false;
        }
    }

    function showResult(data){
        const result=document.getElementById("result");
        result.classList.remove("hidden");

        const title=document.getElementById("resultTitle");
        const name=document.getElementById("studentName");
        const id=document.getElementById("studentId");
        const course=document.getElementById("studentCourse");
        const major=document.getElementById("studentmajor");
        const status=document.getElementById("status");
        const scanDate=document.getElementById("scanDate");
        const time=document.getElementById("scanTime");

        name.textContent="";
        id.textContent="";
        course.textContent="";
        major.textContent="";
        status.textContent="";
        scanDate.textContent="";
        time.textContent="";

        if(data.student){
            name.textContent=data.student.name;
            id.textContent="Student ID: "+data.student.student_id;
            course.textContent="Course: "+data.student.course;
            major.textContent="Year/major: "+data.student.year+" - "+data.student.major;
        }

        if(data.success){
            title.textContent="ATTENDANCE RECORDED";
            status.textContent=data.status;
            status.className="big-status "+data.status.toLowerCase();
            scanDate.textContent="Date: "+data.date;
            time.textContent="Time: "+data.time;
            statusMessage("Ready for next student.");
        }else if(data.type==="duplicate"){
            title.textContent="ALREADY RECORDED";
            status.textContent=data.status;
            status.className="big-status "+String(data.status || "").toLowerCase();
            scanDate.textContent="Date: "+data.date;
            time.textContent="Original Scan: "+data.time;
            statusMessage("This student was already recorded today.");
        }else if(data.type==="invalid"){
            title.textContent="STUDENT NOT FOUND";
            status.textContent="";
            statusMessage("This QR code is not registered in the system.");
        }else{
            title.textContent=data.message || "Scan Failed";
            statusMessage(data.message || "Scan failed.");
        }

        setTimeout(function(){
            result.classList.add("hidden");
        },5000);
    }

    function scanSuccess(decodedText){
        const now=Date.now();
        if(decodedText===lastScan && now-lastScanTime<3000) return;
        lastScan=decodedText;
        lastScanTime=now;
        processScan(decodedText);
    }

    function scanFailure(error){}

    {% if active %}
    const scanner=new Html5Qrcode("reader");

    scanner.start(
        {facingMode:"environment"},
        {fps:10,qrbox:{width:250,height:250}},
        scanSuccess,
        scanFailure
    ).then(function(){
        statusMessage("Camera ready. Scan the student's QR code.");
    }).catch(function(error){
        statusMessage("Camera could not be started. Allow camera permission or use the manual Student ID fallback.");
    });
    {% else %}
    statusMessage("Create an attendance session first.");
    {% endif %}

    function manualScan(){
        const input=document.getElementById("manualId");
        processScan(input.value);
        input.value="";
        input.focus();
    }

    document.getElementById("manualId").addEventListener("keydown",function(event){
        if(event.key==="Enter") manualScan();
    });
    </script>
    """
    return render_page(content, "Scanner", active=active)

@app.route("/api/scan", methods=["POST"])
@login_required
def scan():
    data = request.get_json(silent=True) or {}
    scanned_id = str(data.get("student_id", "")).strip()

    if not scanned_id:
        return jsonify({
            "success": False,
            "message": "No ID was scanned."
        }), 400

    student = Student.query.filter_by(
        student_id=scanned_id,
        active=True
    ).first()

    if not student:
        return jsonify({
            "success": False,
            "type": "invalid",
            "message": "This QR code is not registered in the system."
        }), 404

    active = get_active_session()
    if not active:
        return jsonify({
            "success": False,
            "type": "no_session",
            "message": "No open attendance session."
        }), 400

    current_time = datetime.now().time()

    if current_time < active.start_time:
        return jsonify({
            "success": False,
            "type": "not_started",
            "message": "Attendance session has not started yet."
        }), 400

    if current_time > active.end_time:
        return jsonify({
            "success": False,
            "type": "closed",
            "message": "Attendance period has ended."
        }), 400

    today_start = datetime.combine(active.session_date, datetime.min.time())
    today_end = datetime.combine(active.session_date, datetime.max.time())

    existing_today = Attendance.query.join(AttendanceSession).filter(
        Attendance.student_id == student.id,
        AttendanceSession.session_date == active.session_date,
        Attendance.scan_time >= today_start,
        Attendance.scan_time <= today_end
      .order_by(Attendance.scan_time.asc()).first()
    )

    if existing_today:
        return jsonify({
            "success": False,
            "type": "duplicate",
            "message": "Attendance already recorded today.",
            "student": {
                "student_id": student.student_id,
                "name": student.full_name,
                "course": student.course,
                "year": student.year_level,
                "major": student.major
            },
            "status": existing_today.status,
            "date": existing_today.scan_time.strftime("%B %d, %Y"),
            "time": existing_today.scan_time.strftime("%I:%M:%S %p")
        })

    scan_time = datetime.now()
    status = determine_status(active)

    attendance = Attendance(
        student_id=student.id,
        session_id=active.id,
        scan_time=scan_time,
        status=status
    )

    db.session.add(attendance)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing_today = Attendance.query.join(AttendanceSession).filter(
            Attendance.student_id == student.id,
            AttendanceSession.session_date == active.session_date
        ).order_by(Attendance.scan_time.asc()).first()

        if existing_today:
            return jsonify({
                "success": False,
                "type": "duplicate",
                "message": "Attendance already recorded today.",
                "student": {
                    "student_id": student.student_id,
                    "name": student.full_name,
                    "course": student.course,
                    "year": student.year_level,
                    "major": student.major
                },
                "status": existing_today.status,
                "date": existing_today.scan_time.strftime("%B %d, %Y"),
                "time": existing_today.scan_time.strftime("%I:%M:%S %p")
            })

        return jsonify({
            "success": False,
            "message": "Unable to save attendance."
        }), 500

    return jsonify({
        "success": True,
        "message": "Attendance Recorded Successfully.",
        "student": {
            "student_id": student.student_id,
            "name": student.full_name,
            "course": student.course,
            "year": student.year_level,
            "major": student.major
        },
        "status": status,
        "date": scan_time.strftime("%B %d, %Y"),
        "time": scan_time.strftime("%I:%M:%S %p")
    })

@app.route("/attendance")
@login_required
def attendance():
    selected_date = request.args.get("date", date.today().isoformat())
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    try:
        selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        selected_date_obj = date.today()
        selected_date = selected_date_obj.isoformat()

    query = Attendance.query.join(Student).join(AttendanceSession).filter(
        AttendanceSession.session_date == selected_date_obj
    )

    if search:
        query = query.filter(
            db.or_(
                Student.student_id.ilike(f"%{search}%"),
                Student.full_name.ilike(f"%{search}%")
            )
        )

    if status_filter:
        query = query.filter(Attendance.status == status_filter)

    records = query.order_by(Attendance.scan_time.desc()).all()

    content = """
    <div class="page-header">
    <div>
    <h1>Attendance Records</h1>
    <p class="muted">Search and filter attendance.</p>
    </div>
    <a href="{{ url_for('export_attendance', date=selected_date) }}" class="btn primary">Export CSV</a>
    </div>

    <div class="card">
    <form method="GET" class="filters">
    <input type="date" name="date" value="{{ selected_date }}">
    <input name="search" value="{{ search }}" placeholder="Student ID or Name">
    <select name="status">
    <option value="">All Status</option>
    <option value="PRESENT" {% if status_filter=="PRESENT" %}selected{% endif %}>Present</option>
    <option value="LATE" {% if status_filter=="LATE" %}selected{% endif %}>Late</option>
    <option value="ABSENT" {% if status_filter=="ABSENT" %}selected{% endif %}>Absent</option>
    </select>
    <button class="btn secondary">Filter</button>
    </form>
    </div>

    <div class="card">
    <div class="table-container">
    <table>
    <tr><th>ID</th><th>Name</th><th>Course</th><th>Year</th><th>major</th><th>Session</th><th>Time</th><th>Status</th></tr>
    {% for record in records %}
    <tr>
    <td>{{ record.student.student_id }}</td>
    <td>{{ record.student.full_name }}</td>
    <td>{{ record.student.course }}</td>
    <td>{{ record.student.year_level }}</td>
    <td>{{ record.student.major }}</td>
    <td>{{ record.attendance_session.name }}</td>
    <td>{{ record.scan_time.strftime("%I:%M:%S %p") }}</td>
    <td><span class="badge {{ record.status|lower }}">{{ record.status }}</span></td>
    </tr>
    {% else %}
    <tr><td colspan="8" class="empty">No records found.</td></tr>
    {% endfor %}
    </table>
    </div>
    </div>
    """
    return render_page(
        content, "Attendance Records", records=records,
        selected_date=selected_date, search=search,
        status_filter=status_filter
    )

@app.route("/attendance/export")
@login_required
def export_attendance():
    selected_date = request.args.get("date", date.today().isoformat())

    try:
        selected_date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        selected_date_obj = date.today()
        selected_date = selected_date_obj.isoformat()

    records = Attendance.query.join(Student).join(AttendanceSession).filter(
        AttendanceSession.session_date == selected_date_obj
    ).order_by(Attendance.scan_time).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student ID", "Full Name", "Course", "Year Level", "Major",
        "Major", "Date", "Time", "Status"
    ])

    for record in records:
        writer.writerow([
            record.student.student_id,
            record.student.full_name,
            record.student.course,
            record.student.year_level,
            record.student.major,
            record.attendance_session.name,
            record.attendance_session.session_date,
            record.scan_time.strftime("%Y-%m-%d %I:%M:%S %p"),
            record.status
        ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = (
        "attachment; "
        f"filename=attendance_{selected_date}.csv"
    )
    return response

def initialize_database():
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

        for student in Student.query.all():
            if not qr_path(student.student_id).exists():
                try:
                    generate_student_qr(student.student_id)
                except Exception as e:
                    print(f"Could not generate QR for {student.student_id}: {e}")

        print("")
        print("==============================")
        print("DEFAULT LOGIN")
        print("Username: admin")
        print("Password: admin123")
        print("==============================")
        print("")

if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=True)
