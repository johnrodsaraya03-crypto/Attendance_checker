from flask import Flask, request, redirect, url_for, session, jsonify, flash, render_template_string, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time
from functools import wraps
from pathlib import Path
from sqlalchemy import and_, or_, exists
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
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="faculty")

    schedules = db.relationship(
        "FacultySchedule",
        back_populates="faculty",
        cascade="all, delete-orphan",
        foreign_keys="FacultySchedule.faculty_id",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Student(db.Model):
    __tablename__ = "student"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    course = db.Column(db.String(100), nullable=False)
    year_level = db.Column(db.String(50), nullable=False)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)
    active = db.Column(db.Boolean, default=True)

    attendances = db.relationship(
        "Attendance", backref="student", lazy=True, cascade="all, delete-orphan"
    )


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

    faculty_assignments = db.relationship(
        "FacultySchedule",
        back_populates="schedule",
        cascade="all, delete-orphan",
        lazy=True,
    )
    sessions = db.relationship(
        "AttendanceSession",
        back_populates="schedule",
        lazy=True,
    )


class FacultySchedule(db.Model):
    __tablename__ = "faculty_schedules"
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    schedule_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_schedules.id"),
        nullable=False,
        index=True,
    )
    assigned_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    faculty = db.relationship(
        "User",
        back_populates="schedules",
        foreign_keys=[faculty_id],
    )
    schedule = db.relationship(
        "AttendanceSchedule",
        back_populates="faculty_assignments",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "faculty_id", "schedule_id", name="unique_faculty_schedule"
        ),
    )


class AttendanceSession(db.Model):
    __tablename__ = "attendance_session"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    late_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default="OPEN")
    schedule_id = db.Column(
        db.Integer,
        db.ForeignKey("attendance_schedules.id"),
        nullable=True,
        index=True,
    )
    course = db.Column(db.String(100), nullable=True)
    year_level = db.Column(db.String(50), nullable=True)
    major = db.Column(db.String(100), nullable=True)
    section = db.Column(db.String(50), nullable=True)

    schedule = db.relationship("AttendanceSchedule", back_populates="sessions")
    attendances = db.relationship(
        "Attendance", backref="attendance_session", lazy=True,
        cascade="all, delete-orphan"
    )


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    session_id = db.Column(
        db.Integer, db.ForeignKey("attendance_session.id"), nullable=False
    )
    scan_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "session_id", name="unique_student_session"
        ),
    )


class AssessmentConfig(db.Model):
    __tablename__ = "assessment_configs"
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    schedule_id = db.Column(
        db.Integer, db.ForeignKey("attendance_schedules.id"), nullable=True, index=True
    )
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
    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False, index=True
    )
    faculty_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    schedule_id = db.Column(
        db.Integer, db.ForeignKey("attendance_schedules.id"), nullable=True, index=True
    )
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
 
def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if not current_user():
            session.clear()
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated(*args, **kwargs):
            user = current_user()
            if not user or user.role not in roles:
                if request.is_json or request.path.startswith("/api/") or request.path == "/scan":
                    return jsonify({"success": False, "message": "Forbidden"}), 403
                flash("You are not authorized to perform that action.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def is_admin(user=None):
    user = user or current_user()
    return bool(user and user.role == "admin")


def assigned_schedule_ids(user=None):
    user = user or current_user()
    if not user or user.role != "faculty":
        return []
    return db.session.query(FacultySchedule.schedule_id).filter(
        FacultySchedule.faculty_id == user.id
    )


def schedule_access_query(user=None):
    user = user or current_user()
    if not user:
        return AttendanceSchedule.query.filter(db.literal(False))
    if user.role == "admin":
        return AttendanceSchedule.query
    return AttendanceSchedule.query.join(
        FacultySchedule, FacultySchedule.schedule_id == AttendanceSchedule.id
    ).filter(FacultySchedule.faculty_id == user.id)


def get_schedule_or_forbidden(schedule_id, user=None):
    schedule = db.session.get(AttendanceSchedule, schedule_id)
    if not schedule:
        return None, (jsonify({"success": False, "message": "Schedule not found"}), 404)
    user = user or current_user()
    if user.role != "admin":
        allowed = db.session.query(FacultySchedule.id).filter_by(
            faculty_id=user.id, schedule_id=schedule.id
        ).first()
        if not allowed:
            return None, (jsonify({"success": False, "message": "Forbidden"}), 403)
    return schedule, None


def faculty_can_access_schedule(schedule_id, user=None):
    user = user or current_user()
    if not user:
        return False
    if user.role == "admin":
        return True
    return db.session.query(FacultySchedule.id).filter_by(
        faculty_id=user.id, schedule_id=schedule_id
    ).first() is not None


def faculty_can_access_class(course, year_level, major="", section="", user=None):
    user = user or current_user()
    if not user:
        return False
    if user.role == "admin":
        return True
    q = db.session.query(FacultySchedule.id).join(
        AttendanceSchedule,
        AttendanceSchedule.id == FacultySchedule.schedule_id
    ).filter(
        FacultySchedule.faculty_id == user.id,
        AttendanceSchedule.course == course,
        AttendanceSchedule.year_level == year_level,
    )
    if major:
        q = q.filter(AttendanceSchedule.major == major)
    else:
        q = q.filter(or_(AttendanceSchedule.major.is_(None), AttendanceSchedule.major == ""))
    if section:
        q = q.filter(AttendanceSchedule.section == section)
    else:
        q = q.filter(or_(AttendanceSchedule.section.is_(None), AttendanceSchedule.section == ""))
    return q.first() is not None


def faculty_can_access_student(student, user=None):
    if not student:
        return False
    return faculty_can_access_class(
        student.course, student.year_level, student.major or "", student.section or "", user
    )


def faculty_can_access_session(sess, user=None):
    user = user or current_user()
    if not sess or not user:
        return False
    if user.role == "admin":
        return True
    if sess.schedule_id and faculty_can_access_schedule(sess.schedule_id, user):
        return True
    return faculty_can_access_class(
        sess.course or "", sess.year_level or "", sess.major or "", sess.section or "", user
    )


def faculty_can_access_assessment(a, user=None):
    user = user or current_user()
    if not a or not user:
        return False
    if user.role == "admin":
        return True
    if a.schedule_id and faculty_can_access_schedule(a.schedule_id, user):
        return True
    return faculty_can_access_class(
        a.course or "", a.year_level or "", a.major or "", a.section or "", user
    )


def accessible_students_query(user=None, active_only=False):
    user = user or current_user()
    q = Student.query
    if active_only:
        q = q.filter(Student.active == True)
    if not user or user.role == "admin":
        return q

    assignment_exists = exists().where(
        and_(
            FacultySchedule.faculty_id == user.id,
            FacultySchedule.schedule_id == AttendanceSchedule.id,
            AttendanceSchedule.course == Student.course,
            AttendanceSchedule.year_level == Student.year_level,
            or_(
                AttendanceSchedule.major == Student.major,
                and_(
                    AttendanceSchedule.major.is_(None),
                    or_(Student.major.is_(None), Student.major == "")
                ),
                and_(
                    Student.major.is_(None),
                    AttendanceSchedule.major == ""
                ),
            ),
            or_(
                AttendanceSchedule.section == Student.section,
                and_(
                    AttendanceSchedule.section.is_(None),
                    or_(Student.section.is_(None), Student.section == "")
                ),
                and_(
                    Student.section.is_(None),
                    AttendanceSchedule.section == ""
                ),
            ),
        )
    )
    return q.filter(assignment_exists)


def class_students(course, year_level, major="", section="", user=None):
    q = Student.query.filter_by(active=True, course=course, year_level=year_level)
    if major:
        q = q.filter(Student.major == major)
    else:
        q = q.filter(or_(Student.major.is_(None), Student.major == ""))
    if section:
        q = q.filter(Student.section == section)
    else:
        q = q.filter(or_(Student.section.is_(None), Student.section == ""))
    if user and user.role != "admin":
        q = q.filter(
            exists().where(
                and_(
                    FacultySchedule.faculty_id == user.id,
                    FacultySchedule.schedule_id == AttendanceSchedule.id,
                    AttendanceSchedule.course == Student.course,
                    AttendanceSchedule.year_level == Student.year_level,
                    or_(
                        AttendanceSchedule.major == Student.major,
                        and_(
                            AttendanceSchedule.major.is_(None),
                            or_(Student.major.is_(None), Student.major == "")
                        )
                    ),
                    or_(
                        AttendanceSchedule.section == Student.section,
                        and_(
                            AttendanceSchedule.section.is_(None),
                            or_(Student.section.is_(None), Student.section == "")
                        )
                    ),
                )
            )
        )
    return q.order_by(Student.full_name).all()


def create_today_sessions():
    today = date.today()
    today_name = DAY_NAMES[today.weekday()]
    schedules = AttendanceSchedule.query.filter_by(active=True).all()
    created = 0
    for s in schedules:
        if today_name not in selected_days(s.days):
            continue
        existing = AttendanceSession.query.filter_by(
            schedule_id=s.id, session_date=today
        ).first()
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
            roster = class_students(
                sess.course or "", sess.year_level or "",
                sess.major or "", sess.section or "", user=None
            )
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


def get_active_session(user=None):
    user = user or current_user()
    create_today_sessions()
    close_expired_sessions()
    now = datetime.now().time()
    q = AttendanceSession.query.filter(
        AttendanceSession.session_date == date.today(),
        AttendanceSession.status == "OPEN",
        AttendanceSession.start_time <= now,
        AttendanceSession.end_time >= now
    )
    if user and user.role != "admin":
        q = q.join(
            FacultySchedule, FacultySchedule.schedule_id == AttendanceSession.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    return q.order_by(AttendanceSession.id.desc()).first()


def determine_status(attendance_session):
    return "PRESENT" if datetime.now().time() < attendance_session.late_time else "LATE"


def qr_path(student_id):
    return QR_FOLDER / f"{str(student_id).strip()}.png"


def generate_student_qr(student_id):
    path = qr_path(student_id)
    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10, border=4
    )
    qr.add_data(str(student_id))
    qr.make(fit=True)
    qr.make_image().save(path)
    return path


def delete_student_qr(student_id):
    path = qr_path(student_id)
    if path.exists():
        path.unlink()


def get_db_path():
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        p = uri.replace("sqlite:///", "", 1)
        return str((Path(app.instance_path) / p).resolve())
    return str((BASE_DIR / "brand_new_attendance.db").resolve())


def migrate_existing_database():
    """Non-destructive SQLite migration for existing attendance data.

    Existing schedules are intentionally NOT assigned to faculty automatically.
    They remain visible to admins until an admin assigns them. This prevents
    accidental cross-faculty disclosure during migration.
    """
    db.create_all()
    con = sqlite3.connect(get_db_path())
    con.execute("PRAGMA foreign_keys=ON")
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        # Existing installations may have older table names/columns.
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
                ("section", "VARCHAR(50)"),
                ("faculty_id", "INTEGER"),
                ("schedule_id", "INTEGER"),
            ],
            "assessment_configs": [
                ("faculty_id", "INTEGER"),
                ("schedule_id", "INTEGER"),
            ],
        }

        for table, cols in migrations.items():
            if table not in tables:
                continue
            existing = {
                r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for col, typ in cols:
                if col not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

        # Create the assignment table explicitly for older SQLite databases.
        con.execute("""
            CREATE TABLE IF NOT EXISTS faculty_schedules (
                id INTEGER PRIMARY KEY,
                faculty_id INTEGER NOT NULL,
                schedule_id INTEGER NOT NULL,
                assigned_at DATETIME NOT NULL,
                CONSTRAINT unique_faculty_schedule UNIQUE (faculty_id, schedule_id),
                FOREIGN KEY (faculty_id) REFERENCES user(id) ON DELETE CASCADE,
                FOREIGN KEY (schedule_id) REFERENCES attendance_schedules(id) ON DELETE CASCADE
            )
        """)

        # Link legacy sessions to a schedule only when there is exactly one
        # matching schedule. We do not guess when multiple schedules match.
        if "attendance_session" in tables and "attendance_schedules" in tables:
            con.execute("""
                UPDATE attendance_session
                SET schedule_id = (
                    SELECT MIN(s.id)
                    FROM attendance_schedules s
                    WHERE s.course = attendance_session.course
                      AND s.year_level = attendance_session.year_level
                      AND COALESCE(s.major, '') = COALESCE(attendance_session.major, '')
                      AND COALESCE(s.section, '') = COALESCE(attendance_session.section, '')
                )
                WHERE schedule_id IS NULL
                  AND (
                    SELECT COUNT(*)
                    FROM attendance_schedules s
                    WHERE s.course = attendance_session.course
                      AND s.year_level = attendance_session.year_level
                      AND COALESCE(s.major, '') = COALESCE(attendance_session.major, '')
                      AND COALESCE(s.section, '') = COALESCE(attendance_session.section, '')
                  ) = 1
            """)

        if "assessments" in tables and "attendance_schedules" in tables:
            con.execute("""
                UPDATE assessments
                SET schedule_id = (
                    SELECT MIN(s.id)
                    FROM attendance_schedules s
                    WHERE s.course = assessments.course
                      AND s.year_level = assessments.year_level
                      AND COALESCE(s.major, '') = COALESCE(assessments.major, '')
                      AND COALESCE(s.section, '') = COALESCE(assessments.section, '')
                )
                WHERE schedule_id IS NULL
                  AND (
                    SELECT COUNT(*)
                    FROM attendance_schedules s
                    WHERE s.course = assessments.course
                      AND s.year_level = assessments.year_level
                      AND COALESCE(s.major, '') = COALESCE(assessments.major, '')
                      AND COALESCE(s.section, '') = COALESCE(assessments.section, '')
                  ) = 1
            """)

        if "assessment_configs" in tables and "attendance_schedules" in tables:
            con.execute("""
                UPDATE assessment_configs
                SET schedule_id = (
                    SELECT MIN(s.id)
                    FROM attendance_schedules s
                    WHERE s.course = assessment_configs.course
                      AND s.year_level = assessment_configs.year_level
                      AND COALESCE(s.major, '') = COALESCE(assessment_configs.major, '')
                      AND COALESCE(s.section, '') = COALESCE(assessment_configs.section, '')
                )
                WHERE schedule_id IS NULL
                  AND (
                    SELECT COUNT(*)
                    FROM attendance_schedules s
                    WHERE s.course = assessment_configs.course
                      AND s.year_level = assessment_configs.year_level
                      AND COALESCE(s.major, '') = COALESCE(assessment_configs.major, '')
                      AND COALESCE(s.section, '') = COALESCE(assessment_configs.section, '')
                  ) = 1
            """)

        # Legacy records with no uniquely identifiable schedule remain
        # admin-only until an administrator creates/assigns the correct class.
        con.commit()
    finally:
        con.close()
    db.session.expire_all()


def seed_admin_from_environment():
    """Optionally bootstrap/promote an admin without exposing an open setup route."""
    username = os.environ.get("ATTENDANCE_ADMIN_USERNAME", "").strip()
    password = os.environ.get("ATTENDANCE_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    user = User.query.filter_by(username=username).first()
    if user:
        user.role = "admin"
        db.session.commit()
        return
    email = os.environ.get("ATTENDANCE_ADMIN_EMAIL", f"{username}@localhost").strip().lower()
    if User.query.filter_by(email=email).first():
        return
    user = User(username=username, email=email, role="admin")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


def get_class_options(user=None):
    user = user or current_user()
    if user and user.role == "admin":
        return db.session.query(
            AttendanceSchedule.course, AttendanceSchedule.year_level,
            AttendanceSchedule.major, AttendanceSchedule.section
        ).distinct().order_by(
            AttendanceSchedule.course, AttendanceSchedule.year_level,
            AttendanceSchedule.major, AttendanceSchedule.section
        ).all()
    return db.session.query(
        AttendanceSchedule.course, AttendanceSchedule.year_level,
        AttendanceSchedule.major, AttendanceSchedule.section
    ).join(
        FacultySchedule, FacultySchedule.schedule_id == AttendanceSchedule.id
    ).filter(
        FacultySchedule.faculty_id == user.id,
        AttendanceSchedule.active == True
    ).distinct().order_by(
        AttendanceSchedule.course, AttendanceSchedule.year_level,
        AttendanceSchedule.major, AttendanceSchedule.section
    ).all()


BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{--ink:#172033;--muted:#718096;--blue:#4568f5;--violet:#7657e8;--line:#e7eaf3;--surface:#fff;--bg:#f5f7fc;--mint:#16a085}
*{box-sizing:border-box}
body{margin:0;font-family:'DM Sans',Arial,sans-serif;min-height:100vh;background:radial-gradient(ellipse at 8% 0%,#e8edff 0,transparent 36%),radial-gradient(ellipse at 100% 12%,#e9e3ff 0,transparent 30%),var(--bg);color:var(--ink);font-size:14px}
h1,h2,h3,.brand{font-family:'Space Grotesk',sans-serif;letter-spacing:-.5px}
h1{font-size:clamp(25px,3vw,34px);margin:0 0 8px;font-weight:700}h2{font-size:21px;margin:0 0 16px}h3{font-size:17px}
.topbar{background:linear-gradient(110deg,#172554,#292b69 58%,#5145b5);color:white;padding:15px clamp(16px,3vw,38px);display:flex;justify-content:space-between;align-items:center;gap:18px;box-shadow:0 8px 28px #202b6530;position:sticky;top:0;z-index:20}
.brand{font-size:20px;font-weight:700;white-space:nowrap;display:flex;align-items:center;gap:10px}.brand:before{content:'✓';display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#8de9df,#b8a8ff);color:#20245a;font-size:20px}
nav{display:flex;gap:4px;flex-wrap:wrap;align-items:center}nav a{color:#e9eaff;text-decoration:none;padding:10px 12px;border-radius:10px;font-weight:600;font-size:13px;transition:.2s}nav a:hover{background:#ffffff20;color:white;transform:translateY(-1px)}
.menu{display:none;background:#ffffff18;border:0;color:white;font-size:25px;border-radius:9px;padding:4px 10px}
.container{width:min(94%,1380px);margin:34px auto 60px}
.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:15px;flex-wrap:wrap}.page-header .muted{margin:5px 0 0}
.card,.stat{background:rgba(255,255,255,.94);padding:24px;border:1px solid #e9ecf5;border-radius:19px;margin-bottom:20px;box-shadow:0 8px 28px #28345c0a;transition:box-shadow .2s}.card:hover{box-shadow:0 12px 32px #28345c12}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:22px}
.stat{position:relative;overflow:hidden;padding:23px 24px}.stat:after{content:'';position:absolute;width:90px;height:90px;border-radius:50%;right:-25px;top:-30px;background:linear-gradient(135deg,#e5eaff,#f0eaff);opacity:.9}.stat span{color:var(--muted);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.7px}.stat strong{display:block;font-family:'Space Grotesk',sans-serif;font-size:34px;margin-top:10px;position:relative;z-index:1}
.present{color:#119879}.late{color:#d78a16}.absent{color:#e24c68}
.btn{border:none;padding:11px 16px;border-radius:10px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;gap:6px;font-weight:700;font-family:inherit;font-size:13px;transition:transform .18s,box-shadow .18s,filter .18s}.btn:hover{transform:translateY(-2px);box-shadow:0 7px 16px #29376b20;filter:brightness(1.03)}.primary{background:linear-gradient(120deg,var(--blue),var(--violet));color:white}.secondary{background:#eef1fa;color:#35405e}.danger{background:#ffe8ed;color:#c42e4b}.warning-btn{background:#fff0d8;color:#a86406}.small{padding:7px 10px;font-size:12px}.full{width:100%}
input,select{width:100%;padding:12px 13px;border:1px solid #dfe4ef;border-radius:10px;margin-bottom:10px;font-size:14px;font-family:inherit;background:#fbfcff;color:var(--ink);outline:none;transition:border .2s,box-shadow .2s}input:focus,select:focus{border-color:#8292ff;box-shadow:0 0 0 4px #6577ff19;background:white}label{display:block;font-weight:700;margin:12px 0 6px;color:#39435c;font-size:13px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}th,td{text-align:left;padding:14px 13px;border-bottom:1px solid var(--line);vertical-align:middle}th{background:#f6f7fc;color:#6b7590;font-size:11px;text-transform:uppercase;letter-spacing:.65px;font-weight:700}th:first-child{border-radius:9px 0 0 9px}th:last-child{border-radius:0 9px 9px 0}tbody tr:hover,table tr:hover td{background:#fafbff}.table-container{overflow-x:auto;border-radius:10px}
.badge{padding:6px 10px;border-radius:30px;font-size:10px;font-weight:800;letter-spacing:.45px;display:inline-block}.badge.present{background:#dff8ef;color:#087b5e}.badge.late{background:#fff1d8;color:#a96300}.badge.absent{background:#ffe5eb;color:#bd2947}.badge.active{background:#dff8ef;color:#087b5e}.badge.inactive{background:#ffe5eb;color:#bd2947}
.alert{padding:14px 17px;border-radius:12px;margin-bottom:18px;font-weight:600;border:1px solid transparent}.alert.success{background:#e5f8f0;color:#087b5e;border-color:#c9f0e1}.alert.danger{background:#fff0f2;color:#bd2947;border-color:#ffd9e0}.alert.warning{background:#fff6e5;color:#986000;border-color:#ffebbf}.alert.info{background:#edf1ff;color:#344fc0;border-color:#dce3ff}
.session-banner{background:linear-gradient(115deg,#e8edff,#f0eaff);color:#303d8e;padding:19px 22px;border:1px solid #dce2ff;border-radius:15px;margin-bottom:22px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}.session-banner strong{font-family:'Space Grotesk',sans-serif;font-size:17px}
.form-card{max-width:920px}.form-actions{margin-top:22px;display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:15px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.check-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:15px}.check-grid label{font-weight:600;background:#f7f8fd;border:1px solid #e9ecf5;padding:11px;border-radius:10px;margin:0}.check-grid input{width:auto;margin:0 7px 0 0;accent-color:var(--blue)}
.scanner{max-width:760px;margin:auto}#reader{width:100%;min-height:280px;border:2px dashed #d9def0;border-radius:14px;overflow:hidden;padding:8px;background:#fafbff}#reader video{border-radius:10px}.scanner-status{text-align:center;padding:15px;margin-top:15px;border-radius:11px;background:#f0f3fc;color:#4b587b;font-weight:700}.login-page{min-height:75vh;display:flex;align-items:center;justify-content:center;padding:24px}.login-card{background:white;width:100%;max-width:440px;padding:36px;border:1px solid #e8ebf5;border-radius:24px;box-shadow:0 22px 65px #29376b18}.login-card h1{text-align:center;font-size:29px}.login-card>p{text-align:center}.login-card .primary{margin-top:8px}.muted{color:var(--muted)}.empty{text-align:center;padding:32px;color:#8a93a9}.qr-card{text-align:center;max-width:520px;margin:auto}.qr-card img{width:300px;max-width:80%;height:auto;border:12px solid white;border-radius:16px;box-shadow:0 8px 30px #202b651c}.student-profile{display:grid;grid-template-columns:1fr 1fr;gap:20px}.result{background:linear-gradient(145deg,#fff,#f8f9ff);padding:22px;border:1px solid #e5e9f6;border-radius:15px;margin-top:20px;text-align:center}.big-status{font-family:'Space Grotesk',sans-serif;font-size:23px;font-weight:700;margin:12px}.hidden{display:none}.score-input{min-width:110px}.class-filter{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.help{background:#f1f4ff;border-left:4px solid #6879f5;padding:14px 16px;margin:12px 0 18px;border-radius:8px;color:#485581}
@media(max-width:1050px){nav a{padding:9px 8px;font-size:12px}.brand{font-size:18px}.topbar{padding:13px 18px}}
@media(max-width:850px){.stats{grid-template-columns:repeat(2,1fr)}.grid2,.grid3,.class-filter{grid-template-columns:1fr 1fr}.check-grid{grid-template-columns:repeat(2,1fr)}nav{display:none;position:absolute;top:62px;left:12px;right:12px;background:#20265b;flex-direction:column;align-items:stretch;padding:12px;border-radius:14px;box-shadow:0 12px 28px #11193640}nav.show{display:flex}.menu{display:block}}
@media(max-width:550px){.container{width:92%;margin:22px auto 40px}.stats,.grid2,.grid3,.class-filter{grid-template-columns:1fr}.check-grid{grid-template-columns:1fr}.student-profile{grid-template-columns:1fr}.card{padding:17px;border-radius:15px}.login-card{padding:25px 20px}.page-header{align-items:flex-start}.stat strong{font-size:30px}.session-banner{padding:16px}.topbar{padding:12px 14px}}
</style>
</head>
<body>
{% if session.user_id %}
<header class="topbar"><div class="brand">Attendance Checker</div><button class="menu" onclick="toggleMenu()">☰</button>
<nav id="nav">
<a href="{{ url_for('dashboard') }}">Dashboard</a><a href="{{ url_for('scanner') }}">Scanner</a><a href="{{ url_for('students') }}">Students</a><a href="{{ url_for('attendance') }}">Attendance</a><a href="{{ url_for('schedules') }}">Schedules</a><a href="{{ url_for('sessions') }}">Sessions</a><a href="{{ url_for('assessments') }}">Assessments</a>
{% if session.get('role') == 'admin' %}<a href="{{ url_for('admin_users') }}">Faculty Access</a>{% endif %}
<a href="{{ url_for('logout') }}">Logout</a>
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
    user = current_user()
    course = request.args.get("course", "").strip()
    year_level = request.args.get("year_level", "").strip()

    student_base = accessible_students_query(user, active_only=True)
    courses = [
        x[0] for x in student_base.with_entities(Student.course).distinct()
        .order_by(Student.course).all() if x[0]
    ]
    years = [
        x[0] for x in student_base.with_entities(Student.year_level).distinct()
        .order_by(Student.year_level).all() if x[0]
    ]

    q = accessible_students_query(user, active_only=True)
    if course:
        q = q.filter(Student.course == course)
    if year_level:
        q = q.filter(Student.year_level == year_level)
    total = q.count()

    active = get_active_session(user)
    present = late = absent = 0
    if active:
        session_matches = (
            (not course or active.course == course)
            and (not year_level or active.year_level == year_level)
        )
        if session_matches:
            roster = class_students(
                active.course or "", active.year_level or "",
                active.major or "", active.section or "", user
            )
            roster_ids = [s.id for s in roster]
            if roster_ids:
                present = Attendance.query.filter(
                    Attendance.session_id == active.id,
                    Attendance.status == "PRESENT",
                    Attendance.student_id.in_(roster_ids)
                ).count()
                late = Attendance.query.filter(
                    Attendance.session_id == active.id,
                    Attendance.status == "LATE",
                    Attendance.student_id.in_(roster_ids)
                ).count()
            absent = max(len(roster_ids) - present - late, 0)

    recent_q = Attendance.query.join(Student).join(AttendanceSession)
    if user.role != "admin":
        recent_q = recent_q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == AttendanceSession.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    if course:
        recent_q = recent_q.filter(Student.course == course)
    if year_level:
        recent_q = recent_q.filter(Student.year_level == year_level)
    recent = recent_q.order_by(Attendance.scan_time.desc()).limit(10).all()

    options_course = '<option value="">All Courses</option>' + "".join(
        f'<option value="{c}" {"selected" if c == course else ""}>{c}</option>'
        for c in courses
    )
    options_year = '<option value="">All Year Levels</option>' + "".join(
        f'<option value="{y}" {"selected" if y == year_level else ""}>{y}</option>'
        for y in years
    )

    banner = (
        f"""<div class="session-banner"><strong>Active Class: {active.name}</strong>
        <span>{active.course} • {active.year_level} • {active.major or 'No Major'}<br>
        {active.start_time.strftime('%I:%M %p')} - {active.end_time.strftime('%I:%M %p')}</span></div>"""
        if active else
        '<div class="alert warning">No class is currently active. Scheduled classes are created automatically on their scheduled days.</div>'
    )
    rows = "".join(
        f"<tr><td>{a.student.student_id}</td><td>{a.student.full_name}</td>"
        f"<td>{a.attendance_session.name}</td>"
        f"<td>{a.scan_time.strftime('%I:%M %p')}</td>"
        f"<td><span class='badge {a.status.lower()}'>{a.status}</span></td></tr>"
        for a in recent
    ) or "<tr><td colspan='5' class='empty'>No scans yet.</td></tr>"

    content = f"""<div class="page-header"><div><h1>Dashboard</h1><p class="muted">Welcome,
    {session.get('username')} ({user.role.title()})</p></div><a href="{url_for('scanner')}"
    class="btn primary">Open Scanner</a></div>{banner}
    <div class="card"><form method="GET" class="class-filter"><div><label>Course</label>
    <select name="course">{options_course}</select></div><div><label>Year Level</label>
    <select name="year_level">{options_year}</select></div><div style="align-self:end">
    <button class="btn primary">Apply Filters</button> <a class="btn secondary"
    href="{url_for('dashboard')}">Reset</a></div></form></div>
    <div class="stats"><div class="stat"><span>Total Active Students</span><strong>{total}</strong></div>
    <div class="stat"><span>Present</span><strong class="present">{present}</strong></div>
    <div class="stat"><span>Late</span><strong class="late">{late}</strong></div>
    <div class="stat"><span>Absent</span><strong class="absent">{absent}</strong></div></div>
    <div class="card"><h2>Recent Scans</h2><div class="table-container"><table>
    <tr><th>ID</th><th>Name</th><th>Class</th><th>Time</th><th>Status</th></tr>{rows}</table></div></div>"""
    return render_page(content, "Dashboard")

@app.route("/students")
@login_required
def students():
    user = current_user()
    search = request.args.get("search", "").strip()
    course = request.args.get("course", "").strip()
    year_level = request.args.get("year_level", "").strip()

    base = accessible_students_query(user)
    courses = [x[0] for x in base.with_entities(Student.course).distinct().order_by(Student.course).all() if x[0]]
    years = [x[0] for x in base.with_entities(Student.year_level).distinct().order_by(Student.year_level).all() if x[0]]

    q = accessible_students_query(user)
    if search:
        q = q.filter(
            or_(Student.student_id.ilike(f"%{search}%"), Student.full_name.ilike(f"%{search}%"))
        )
    if course:
        q = q.filter(Student.course == course)
    if year_level:
        q = q.filter(Student.year_level == year_level)
    items = q.order_by(Student.full_name).all()

    options_course = '<option value="">All Courses</option>' + ''.join(
        f'<option value="{c}" {"selected" if c == course else ""}>{c}</option>' for c in courses
    )
    options_year = '<option value="">All Year Levels</option>' + ''.join(
        f'<option value="{y}" {"selected" if y == year_level else ""}>{y}</option>' for y in years
    )
    rows = "".join(
        f"""<tr><td>{s.student_id}</td><td>{s.full_name}</td><td>{s.course}</td>
        <td>{s.year_level}</td><td>{s.major or ""}</td><td>{s.section or ""}</td>
        <td><span class="badge {'active' if s.active else 'inactive'}">
        {'ACTIVE' if s.active else 'INACTIVE'}</span></td><td>
        <a href="{url_for('student_profile',id=s.id)}" class="btn small primary">QR</a>
        <a href="{url_for('edit_student',id=s.id)}" class="btn small secondary">Edit</a>
        </td></tr>"""
        for s in items
    ) or "<tr><td colspan='8' class='empty'>No students found.</td></tr>"

    content = f"""<div class="page-header"><h1>Students</h1><a href="{url_for('add_student')}"
    class="btn primary">+ Add Student</a></div><div class="card"><form method="GET">
    <input name="search" value="{search}" placeholder="Search Student ID or Name">
    <div class="class-filter"><div><label>Course</label><select name="course">{options_course}</select></div>
    <div><label>Year Level</label><select name="year_level">{options_year}</select></div></div>
    <button class="btn primary">Apply Filters / Search</button> <a class="btn secondary"
    href="{url_for('students')}">Reset</a></form></div><div class="card"><div class="table-container">
    <table><tr><th>ID</th><th>Name</th><th>Course</th><th>Year</th><th>Major</th><th>Section</th>
    <th>Status</th><th>Action</th></tr>{rows}</table></div></div>"""
    return render_page(content, "Students")


@app.route("/students/add",methods=["GET","POST"])
@login_required
def add_student():
    user = current_user()
    if request.method == "POST":
        sid = request.form.get("student_id","").strip()
        name = request.form.get("full_name","").strip()
        course = request.form.get("course","").strip()
        year = request.form.get("year_level","").strip()
        major = request.form.get("major","").strip()
        section = request.form.get("section","").strip()

        if not all([sid,name,course,year]):
            flash("Student ID, name, course, and year level are required.","danger")
            return redirect(url_for("add_student"))
        if Student.query.filter_by(student_id=sid).first():
            flash("Student ID exists.","danger")
            return redirect(url_for("add_student"))
        if user.role != "admin" and not faculty_can_access_class(course, year, major, section, user):
            flash("You can only add students to a class assigned to you.","danger")
            return redirect(url_for("students"))

        s = Student(
            student_id=sid, full_name=name, course=course, year_level=year,
            major=major or None, section=section or None,
            active=request.form.get('active','1') == '1'
        )
        db.session.add(s)
        db.session.commit()
        generate_student_qr(sid)
        flash("Student added and QR generated.","success")
        return redirect(url_for("student_profile",id=s.id))

    content="""<div class="page-header"><h1>Add Student</h1></div><div class="card form-card">
    <form method="POST"><div class="grid2"><div><label>Student ID</label><input name="student_id" required>
    </div><div><label>Full Name</label><input name="full_name" required></div><div><label>Course / Program</label>
    <input name="course" placeholder="BSIT" required></div><div><label>Year Level</label><input name="year_level"
    placeholder="2nd Year" required></div><div><label>Major</label><input name="major"
    placeholder="Computer Technology"></div><div><label>Section</label><input name="section"
    placeholder="A"></div></div><label>Status</label><select name="active"><option value="1">Active</option>
    <option value="0">Inactive</option></select><div class="form-actions"><a href="{{ url_for('students') }}"
    class="btn secondary">Cancel</a><button class="btn primary">Add Student</button></div></form></div>"""
    return render_page(content,"Add Student")


@app.route("/students/profile/<int:id>")
@login_required
def student_profile(id):
    user = current_user()
    s = db.session.get(Student, id)
    if not s:
        return "Student not found", 404
    if not faculty_can_access_student(s, user):
        return "Forbidden", 403
    if not qr_path(s.student_id).exists():
        generate_student_qr(s.student_id)
    content=f"""<div class="page-header"><h1>{s.full_name}</h1><a href="{url_for('students')}"
    class="btn secondary">Back</a></div><div class="student-profile"><div class="card">
    <p><strong>ID:</strong> {s.student_id}</p><p><strong>Course:</strong> {s.course}</p>
    <p><strong>Year:</strong> {s.year_level}</p><p><strong>Major:</strong> {s.major or 'Not set'}</p>
    <p><strong>Section:</strong> {s.section or 'Not set'}</p><p><strong>Status:</strong>
    {'ACTIVE' if s.active else 'INACTIVE'}</p></div><div class="card qr-card"><h3>QR Code</h3>
    <img src="{url_for('student_qr',student_id=s.student_id)}"><p class="muted">ID: {s.student_id}</p>
    <a class="btn primary" href="{url_for('student_qr',student_id=s.student_id)}" download>Download</a>
    </div></div>"""
    return render_page(content,"Profile")


@app.route("/qr_codes/<path:student_id>.png")
@login_required
def student_qr(student_id):
    user = current_user()
    s = Student.query.filter_by(student_id=student_id).first()
    if not s or not faculty_can_access_student(s, user):
        return "Forbidden", 403
    path = qr_path(student_id)
    if not path.exists():
        generate_student_qr(student_id)
    return send_from_directory(QR_FOLDER,f"{student_id}.png")


@app.route("/students/edit/<int:id>",methods=["GET","POST"])
@login_required
def edit_student(id):
    user = current_user()
    s = db.session.get(Student, id)
    if not s:
        return "Student not found", 404
    if not faculty_can_access_student(s, user):
        return "Forbidden", 403

    if request.method=="POST":
        old=s.student_id
        new=request.form.get("student_id","").strip()
        course=request.form.get("course","").strip()
        year=request.form.get("year_level","").strip()
        major=request.form.get("major","").strip()
        section=request.form.get("section","").strip()

        if not new:
            flash("Student ID is required.","danger")
            return redirect(url_for("edit_student",id=id))
        duplicate=Student.query.filter(Student.student_id==new,Student.id!=s.id).first()
        if duplicate:
            flash("Student ID already exists.","danger")
            return redirect(url_for("edit_student",id=id))
        if not all([course, year]):
            flash("Course and year level are required.","danger")
            return redirect(url_for("edit_student",id=id))
        if user.role != "admin" and not faculty_can_access_class(course, year, major, section, user):
            flash("You cannot move a student into a class that is not assigned to you.","danger")
            return redirect(url_for("edit_student",id=id))

        s.student_id=new
        s.full_name=request.form.get("full_name","").strip()
        s.course=course
        s.year_level=year
        s.major=major or None
        s.section=section or None
        s.active=request.form.get("active")=="1"
        db.session.commit()
        if old!=new:
            delete_student_qr(old)
        generate_student_qr(new)
        flash("Student updated.","success")
        return redirect(url_for("students"))

    content=f"""<div class="page-header"><h1>Edit Student</h1></div><div class="card form-card">
    <form method="POST"><label>Student ID</label><input name="student_id" value="{s.student_id}" required>
    <label>Full Name</label><input name="full_name" value="{s.full_name}" required><div class="grid2">
    <div><label>Course</label><input name="course" value="{s.course}" required></div><div><label>Year Level</label>
    <input name="year_level" value="{s.year_level}" required></div><div><label>Major</label><input name="major"
    value="{s.major or ''}"></div><div><label>Section</label><input name="section" value="{s.section or ''}">
    </div></div><label>Status</label><select name="active"><option value="1" {'selected' if s.active else ''}>
    Active</option><option value="0" {'selected' if not s.active else ''}>Inactive</option></select>
    <div class="form-actions"><a href="{url_for('students')}" class="btn secondary">Cancel</a>
    <button class="btn primary">Save</button></div></form></div>"""
    return render_page(content,"Edit Student")

@app.route("/schedules")
@login_required
def schedules():
    user = current_user()
    create_today_sessions()
    items = schedule_access_query(user).order_by(
        AttendanceSchedule.active.desc(), AttendanceSchedule.name
    ).all()
    faculty = User.query.filter_by(role="faculty").order_by(User.username).all()

    rows = ""
    for s in items:
        assigned = [a.faculty.username for a in s.faculty_assignments]
        if user.role == "admin":
            assignment_form = f"""
            <form method="POST" action="{url_for('assign_schedule', id=s.id)}"
                  style="display:flex;gap:6px;flex-wrap:wrap;margin-top:7px">
              <select name="faculty_id" style="margin:0;min-width:150px">
                <option value="">Assign faculty...</option>
                {''.join(
                    f'<option value="{f.id}">{f.username}</option>'
                    for f in faculty
                )}
              </select>
              <button class="btn small primary">Assign</button>
            </form>
            <div style="margin-top:6px">
              {''.join(
                  f'<form method="POST" action="{url_for("unassign_schedule", id=s.id)}" style="display:inline;margin-right:5px">'
                  f'<input type="hidden" name="faculty_id" value="{a.faculty_id}">'
                  f'<button class="btn small danger" type="submit">Remove {a.faculty.username}</button></form>'
                  for a in s.faculty_assignments
              )}
            </div>
            """
        else:
            assignment_form = ""
        assigned_text = ", ".join(assigned) if assigned else "Admin only / unassigned"
        buttons = f"""<a class="btn small secondary" href="{url_for('edit_schedule',id=s.id)}">Edit</a>
        <form method="POST" action="{url_for('toggle_schedule',id=s.id)}" style="display:inline">
        <button class="btn small {'danger' if s.active else 'primary'}">
        {'Deactivate' if s.active else 'Activate'}</button></form>
        <form method="POST" action="{url_for('delete_schedule',id=s.id)}" style="display:inline"
        onsubmit="return confirm('Delete this schedule? Existing attendance sessions will be preserved.')">
        <button class="btn small danger">Delete</button></form>{assignment_form}"""
        rows += f"""<tr><td>{s.name}</td><td>{s.course}</td><td>{s.year_level}</td>
        <td>{s.major or ''}</td><td>{s.section or ''}</td><td>{s.days}</td>
        <td>{s.start_time.strftime('%I:%M %p')}</td><td>{s.late_time.strftime('%I:%M %p')}</td>
        <td>{s.end_time.strftime('%I:%M %p')}</td><td><span class='badge
        {'active' if s.active else 'inactive'}'>{'ACTIVE' if s.active else 'INACTIVE'}</span></td>
        <td><strong>{assigned_text}</strong><br>{buttons}</td></tr>"""

    extra_head = "<th>Assigned Faculty / Actions</th>"
    content=f"""<div class="page-header"><div><h1>Class Schedules</h1><p class="muted">
    Create a class once. Attendance sessions are automatically generated on selected days.
    {'Admins can assign each schedule to one or more faculty accounts.' if user.role == 'admin' else 'Only classes assigned to your account are shown.'}
    </p></div><a href="{url_for('add_schedule')}" class="btn primary">+ Add Schedule</a></div>
    <div class="card"><div class="table-container"><table><tr><th>Name</th><th>Course</th><th>Year</th>
    <th>Major</th><th>Section</th><th>Days</th><th>Start</th><th>Late</th><th>End</th><th>Status</th>
    {extra_head}</tr>{rows or "<tr><td colspan='11' class='empty'>No schedules yet.</td></tr>"}</table></div></div>"""
    return render_page(content,"Schedules")


def schedule_form_content(s=None):
    editing=s is not None
    vals={"name":s.name if s else "","course":s.course if s else "","year":s.year_level if s else "",
          "major":s.major if s else "","section":s.section if s else "",
          "start":s.start_time.strftime("%H:%M") if s else "08:00",
          "late":s.late_time.strftime("%H:%M") if s else "08:15",
          "end":s.end_time.strftime("%H:%M") if s else "10:00"}
    chosen=selected_days(s.days) if s else []
    checks="".join(
        f"<label><input type='checkbox' name='days' value='{d}' {'checked' if d in chosen else ''}>{d}</label>"
        for d in DAY_NAMES
    )
    action=url_for("edit_schedule",id=s.id) if editing else url_for("add_schedule")
    return f"""<div class="page-header"><h1>{'Edit' if editing else 'Add'} Class Schedule</h1></div>
    <div class="card form-card"><div class="help">Set the recurring class here once. The system will
    automatically create/use the attendance session on every selected weekday.</div><form method="POST">
    <label>Schedule Name</label><input name="name" value="{vals['name']}" placeholder="Computer Programming" required>
    <div class="grid2"><div><label>Course / Program</label><input name="course" value="{vals['course']}"
    placeholder="BSIT" required></div><div><label>Year Level</label><input name="year_level" value="{vals['year']}"
    placeholder="2nd Year" required></div><div><label>Major</label><input name="major" value="{vals['major']}"
    placeholder="Computer Technology"></div><div><label>Section (Optional)</label><input name="section"
    value="{vals['section']}" placeholder="A"></div></div><label>Days</label><div class="check-grid">{checks}</div>
    <div class="grid3"><div><label>Start Time</label><input type="time" name="start_time" value="{vals['start']}" required>
    </div><div><label>Late After</label><input type="time" name="late_time" value="{vals['late']}" required></div>
    <div><label>End Time</label><input type="time" name="end_time" value="{vals['end']}" required></div></div>
    <div class="form-actions"><a href="{url_for('schedules')}" class="btn secondary">Cancel</a>
    <button class="btn primary">Save Schedule</button></div></form></div>"""


@app.route("/schedules/add",methods=["GET","POST"])
@login_required
def add_schedule():
    user = current_user()
    if request.method=="POST":
        days=request.form.getlist("days")
        if not days:
            flash("Select at least one day.","danger")
            return redirect(url_for("add_schedule"))
        try:
            st=parse_time(request.form.get("start_time"))
            lt=parse_time(request.form.get("late_time"))
            et=parse_time(request.form.get("end_time"))
        except:
            flash("Invalid time.","danger")
            return redirect(url_for("add_schedule"))
        if not(st<=lt<=et):
            flash("Start Late End.","danger")
            return redirect(url_for("add_schedule"))

        name=request.form.get("name","").strip()
        course=request.form.get("course","").strip()
        year=request.form.get("year_level","").strip()
        major=request.form.get("major","").strip() or None
        section=request.form.get("section","").strip() or None
        if not name or not course or not year:
            flash("Schedule name, course, and year level are required.","danger")
            return redirect(url_for("add_schedule"))

        s=AttendanceSchedule(
            name=name,course=course,year_level=year,major=major,section=section,
            days=",".join(days),start_time=st,late_time=lt,end_time=et,active=True
        )
        db.session.add(s)
        db.session.flush()

        # A faculty member who creates a schedule automatically owns that class.
        # Admin-created schedules remain unassigned until explicitly assigned.
        if user.role == "faculty":
            db.session.add(FacultySchedule(faculty_id=user.id, schedule_id=s.id))

        db.session.commit()
        create_today_sessions()
        flash("Recurring schedule created and access assignment saved.","success")
        return redirect(url_for("schedules"))
    return render_page(schedule_form_content(),"Add Schedule")


@app.route("/schedules/edit/<int:id>",methods=["GET","POST"])
@login_required
def edit_schedule(id):
    user = current_user()
    s, err = get_schedule_or_forbidden(id, user)
    if err:
        if request.method == "GET":
            return "Forbidden", 403
        return err

    if request.method=="POST":
        days=request.form.getlist("days")
        try:
            st=parse_time(request.form.get("start_time"))
            lt=parse_time(request.form.get("late_time"))
            et=parse_time(request.form.get("end_time"))
        except:
            flash("Invalid time.","danger")
            return redirect(url_for("edit_schedule",id=id))
        if not days:
            flash("Select at least one day.","danger")
            return redirect(url_for("edit_schedule",id=id))
        if not(st<=lt<=et):
            flash("Start Late End.","danger")
            return redirect(url_for("edit_schedule",id=id))

        new_course=request.form.get("course","").strip()
        new_year=request.form.get("year_level","").strip()
        new_major=request.form.get("major","").strip() or None
        new_section=request.form.get("section","").strip() or None
        if not new_course or not new_year or not request.form.get("name","").strip():
            flash("Schedule name, course, and year level are required.","danger")
            return redirect(url_for("edit_schedule",id=id))

        # Faculty cannot edit a schedule into a cohort they do not own.
        if user.role != "admin":
            own = faculty_can_access_class(new_course,new_year,new_major or "",new_section or "",user)
            if not own:
                flash("You cannot move this schedule to an unassigned class.","danger")
                return redirect(url_for("edit_schedule",id=id))

        s.name=request.form.get("name","").strip()
        s.course=new_course
        s.year_level=new_year
        s.major=new_major
        s.section=new_section
        s.days=",".join(days)
        s.start_time=st
        s.late_time=lt
        s.end_time=et
        db.session.commit()
        flash("Schedule updated. Existing attendance sessions are preserved.","success")
        return redirect(url_for("schedules"))
    return render_page(schedule_form_content(s),"Edit Schedule")


@app.route("/schedules/toggle/<int:id>",methods=["POST"])
@login_required
def toggle_schedule(id):
    user=current_user()
    s, err=get_schedule_or_forbidden(id,user)
    if err:
        return err
    s.active=not s.active
    db.session.commit()
    flash(f"Schedule {'activated' if s.active else 'deactivated'}.","success")
    return redirect(url_for("schedules"))


@app.route("/schedules/delete/<int:id>",methods=["POST"])
@login_required
def delete_schedule(id):
    user=current_user()
    s, err=get_schedule_or_forbidden(id,user)
    if err:
        return err
    db.session.delete(s)
    db.session.commit()
    flash("Schedule deleted. Existing attendance records were preserved.","success")
    return redirect(url_for("schedules"))


@app.route("/admin/users")
@roles_required("admin")
def admin_users():
    users=User.query.order_by(User.role.desc(),User.username).all()
    schedules=AttendanceSchedule.query.order_by(AttendanceSchedule.name).all()
    rows=""
    for u in users:
        role_form=f"""<form method="POST" action="{url_for('set_user_role',id=u.id)}"
        style="display:flex;gap:6px"><select name="role" style="margin:0">
        <option value="faculty" {'selected' if u.role=='faculty' else ''}>Faculty</option>
        <option value="admin" {'selected' if u.role=='admin' else ''}>Admin</option>
        </select><button class="btn small secondary">Save Role</button></form>"""
        assigned=", ".join(a.schedule.name for a in u.schedules) or "None"
        rows += f"""<tr><td>{u.username}</td><td>{u.email}</td><td>{u.role}</td>
        <td>{assigned}</td><td>{role_form}</td></tr>"""
    content=f"""<div class="page-header"><div><h1>Faculty & Access Management</h1>
    <p class="muted">Admins can change account roles and assign classes under Schedules.</p></div>
    <a class="btn secondary" href="{url_for('schedules')}">Manage Schedules</a></div>
    <div class="card"><div class="table-container"><table><tr><th>Username</th><th>Email</th>
    <th>Role</th><th>Assigned Classes</th><th>Change Role</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Faculty & Access")


@app.route("/admin/users/<int:id>/role", methods=["POST"])
@roles_required("admin")
def set_user_role(id):
    user=db.session.get(User,id)
    if not user:
        return "User not found",404
    role=request.form.get("role","").strip()
    if role not in {"admin","faculty"}:
        flash("Invalid role.","danger")
        return redirect(url_for("admin_users"))
    if user.id == current_user().id and role != "admin":
        if User.query.filter_by(role="admin").count() <= 1:
            flash("The last admin account cannot be demoted.","danger")
            return redirect(url_for("admin_users"))
    user.role=role
    db.session.commit()
    flash("User role updated.","success")
    return redirect(url_for("admin_users"))


@app.route("/admin/schedules/<int:id>/assign", methods=["POST"])
@roles_required("admin")
def assign_schedule(id):
    schedule=db.session.get(AttendanceSchedule,id)
    faculty_id=request.form.get("faculty_id","").strip()
    faculty=db.session.get(User,int(faculty_id)) if faculty_id.isdigit() else None
    if not schedule or not faculty or faculty.role != "faculty":
        flash("Select a valid faculty account and schedule.","danger")
        return redirect(url_for("schedules"))
    existing=FacultySchedule.query.filter_by(
        faculty_id=faculty.id, schedule_id=schedule.id
    ).first()
    if not existing:
        db.session.add(FacultySchedule(faculty_id=faculty.id,schedule_id=schedule.id))
        db.session.commit()
    flash(f"{faculty.username} assigned to {schedule.name}.","success")
    return redirect(url_for("schedules"))


@app.route("/admin/schedules/<int:id>/unassign", methods=["POST"])
@roles_required("admin")
def unassign_schedule(id):
    schedule=db.session.get(AttendanceSchedule,id)
    faculty_id=request.form.get("faculty_id","").strip()
    faculty=db.session.get(User,int(faculty_id)) if faculty_id.isdigit() else None
    if not schedule or not faculty:
        flash("Invalid schedule or faculty.","danger")
        return redirect(url_for("schedules"))
    assignment=FacultySchedule.query.filter_by(
        faculty_id=faculty.id, schedule_id=schedule.id
    ).first()
    if assignment:
        db.session.delete(assignment)
        db.session.commit()
    flash(f"{faculty.username} removed from {schedule.name}.","success")
    return redirect(url_for("schedules"))

@app.route("/sessions")
@login_required
def sessions():
    user=current_user()
    create_today_sessions()
    close_expired_sessions()
    q=AttendanceSession.query
    if user.role != "admin":
        q=q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == AttendanceSession.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    items=q.order_by(
        AttendanceSession.session_date.desc(),AttendanceSession.id.desc()
    ).limit(100).all()
    rows="".join(
        f"""<tr><td>{x.session_date}</td><td>{x.name}</td><td>{x.course or ''}</td>
        <td>{x.year_level or ''}</td><td>{x.start_time.strftime('%I:%M %p')}</td>
        <td>{x.end_time.strftime('%I:%M %p')}</td><td><span class="badge
        {'active' if x.status=='OPEN' else 'inactive'}">{x.status}</span></td><td>
        {('<form method="POST" action="'+url_for('close_session',id=x.id)+'"><button class="btn small danger">Close</button></form>')
        if x.status=='OPEN' else 'Completed'}</td></tr>"""
        for x in items
    ) or "<tr><td colspan='8' class='empty'>No sessions.</td></tr>"
    content=f"""<div class="page-header"><div><h1>Attendance Sessions</h1><p class="muted">
    Recurring schedules create these automatically. {'All faculty sessions are shown to admins.' if user.role=='admin'
    else 'Only sessions for classes assigned to you are shown.'}</p></div></div>
    <div class="card"><div class="table-container"><table><tr><th>Date</th><th>Class</th><th>Course</th>
    <th>Year</th><th>Start</th><th>End</th><th>Status</th><th>Action</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Sessions")


@app.route("/sessions/create", methods=["POST"])
@login_required
def create_session():
    flash("Manual session creation has been replaced by recurring Class Schedules. Create the class once under Schedules.", "info")
    return redirect(url_for("schedules"))


@app.route("/sessions/close/<int:id>",methods=["POST"])
@login_required
def close_session(id):
    user=current_user()
    sess=db.session.get(AttendanceSession,id)
    if not sess:
        return "Session not found",404
    if not faculty_can_access_session(sess,user):
        return "Forbidden",403
    roster=class_students(
        sess.course or "",sess.year_level or "",
        sess.major or "",sess.section or "",user
    )
    scanned={a.student_id for a in sess.attendances}
    now=datetime.now()
    for st in roster:
        if st.id not in scanned:
            db.session.add(Attendance(
                student_id=st.id,session_id=sess.id,scan_time=now,status="ABSENT"
            ))
    sess.status="CLOSED"
    db.session.commit()
    flash("Session closed. Unscanned class members marked ABSENT.","success")
    return redirect(url_for("sessions"))

@app.route("/scan",methods=["POST"])
@login_required
def scan():
    user=current_user()
    create_today_sessions()
    close_expired_sessions()
    data=request.get_json(silent=True) or {}
    sid=str(data.get("student_id","")).strip()
    if not sid:
        return jsonify({"success":False,"message":"No ID provided"}),400

    active=get_active_session(user)
    if not active:
        return jsonify({"success":False,"message":"No active scheduled class assigned to this account right now."}),403
    if not faculty_can_access_session(active,user):
        return jsonify({"success":False,"message":"Forbidden"}),403

    student=Student.query.filter_by(student_id=sid,active=True).first()
    if not student:
        return jsonify({"success":False,"message":"Student not found"}),404

    roster=class_students(
        active.course or "",active.year_level or "",
        active.major or "",active.section or "",user
    )
    if student.id not in {s.id for s in roster}:
        return jsonify({
            "success":False,
            "message":"Student is not enrolled in the currently active class.",
            "student":{"name":student.full_name,"student_id":student.student_id}
        }),403

    existing=Attendance.query.filter_by(
        student_id=student.id,session_id=active.id
    ).first()
    if existing:
        return jsonify({
            "success":False,"message":"Already scanned",
            "student":{"name":student.full_name,"student_id":student.student_id}
        })

    status=determine_status(active)
    db.session.add(Attendance(
        student_id=student.id,session_id=active.id,
        scan_time=datetime.now(),status=status
    ))
    db.session.commit()
    now=datetime.now()
    return jsonify({
        "success":True,"status":status,
        "date":date.today().strftime("%B %d, %Y"),
        "time":now.strftime("%I:%M:%S %p"),
        "student":{
            "name":student.full_name,"student_id":student.student_id,
            "course":student.course,"year":student.year_level,
            "major":student.major or "","section":student.section or ""
        }
    })


@app.route("/scanner")
@login_required
def scanner():
    active=get_active_session(current_user())
    banner=f"""<div class='session-banner'><strong>Active Class: {active.name}</strong>
    <span>{active.course} • {active.year_level} • {active.major or 'No Major'}<br>
    {active.start_time.strftime('%I:%M %p')} - {active.end_time.strftime('%I:%M %p')}</span></div>""" if active else """
    <div class="alert warning">No scheduled class assigned to your account is active right now.</div>"""
    content=f"""<div class="scanner"><div class="page-header"><h1>QR Scanner</h1></div>{banner}
    <div class="card"><div id="reader"></div><div id="scannerStatus" class="scanner-status">
    Ready to scan QR Code...</div><div id="result" class="result hidden"><h2 id="resultTitle"></h2>
    <h3 id="studentName"></h3><p id="studentId"></p><p id="studentCourse"></p><p id="studentClass"></p>
    <div id="status" class="big-status"></div><p id="scanDate"></p><p id="scanTime"></p></div></div></div>
    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script><script>
    let processing=false;
    function statusMsg(m){{document.getElementById('scannerStatus').textContent=m;}}
    async function processScan(sid){{sid=String(sid||'').trim();if(!sid||processing)return;processing=true;
    statusMsg('Checking...');try{{const res=await fetch('{url_for('scan')}',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{student_id:sid}})}});const d=await res.json();
    showResult(d);}}catch(e){{statusMsg('Server error.');}}setTimeout(()=>{{processing=false;
    statusMsg('Ready for next scan.');}},1500);}}
    function showResult(d){{const r=document.getElementById('result');r.classList.remove('hidden');
    document.getElementById('resultTitle').textContent=d.success?'ATTENDANCE RECORDED':(d.message||'Scan failed');
    document.getElementById('status').textContent=d.success?d.status:'FAILED';
    document.getElementById('status').className='big-status '+(d.success?d.status.toLowerCase():'absent');
    if(d.student){{document.getElementById('studentName').textContent=d.student.name;
    document.getElementById('studentId').textContent='ID: '+d.student.student_id;
    document.getElementById('studentCourse').textContent='Course: '+d.student.course;
    document.getElementById('studentClass').textContent=d.student.year+' • '+(d.student.major||'')+' • '+(d.student.section||'');}}
    if(d.date)document.getElementById('scanDate').textContent='Date: '+d.date;
    if(d.time)document.getElementById('scanTime').textContent='Time: '+d.time;}}
    const html5QrCode=new Html5Qrcode('reader');html5QrCode.start(
    {{facingMode:'environment'}},{{fps:10,qrbox:{{width:250,height:250}}}},
    txt=>{{if(!processing)processScan(txt);}},()=>{{}}).catch(e=>statusMsg('Camera error: '+e.message));
    </script>"""
    return render_page(content,"QR Scanner")

@app.route("/attendance")
@login_required
def attendance():
    user=current_user()
    course=request.args.get("course","").strip()
    year_level=request.args.get("year_level","").strip()
    attendance_date=request.args.get("date","").strip()

    student_scope=accessible_students_query(user)
    courses=[x[0] for x in student_scope.with_entities(Student.course).distinct().order_by(Student.course).all() if x[0]]
    years=[x[0] for x in student_scope.with_entities(Student.year_level).distinct().order_by(Student.year_level).all() if x[0]]

    q=Attendance.query.join(Student).join(AttendanceSession)
    if user.role != "admin":
        q=q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == AttendanceSession.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    if course:
        q=q.filter(Student.course==course)
    if year_level:
        q=q.filter(Student.year_level==year_level)
    if attendance_date:
        q=q.filter(AttendanceSession.session_date==attendance_date)

    records=q.order_by(Attendance.scan_time.desc()).all()
    options_course='<option value="">All Courses</option>'+''.join(
        f'<option value="{c}" {"selected" if c==course else ""}>{c}</option>' for c in courses
    )
    options_year='<option value="">All Year Levels</option>'+''.join(
        f'<option value="{y}" {"selected" if y==year_level else ""}>{y}</option>' for y in years
    )
    rows="".join(
        f"<tr><td>{r.student.student_id}</td><td>{r.student.full_name}</td><td>{r.student.course}</td>"
        f"<td>{r.student.major or ''}</td><td>{r.student.year_level}</td>"
        f"<td>{r.attendance_session.session_date}</td>"
        f"<td>{r.scan_time.strftime('%I:%M %p') if r.status != 'ABSENT' else '—'}</td>"
        f"<td><span class='badge {r.status.lower()}'>{r.status}</span></td></tr>"
        for r in records
    ) or "<tr><td colspan='8' class='empty'>No attendance records.</td></tr>"

    content=f"""<div class="page-header"><h1>Attendance Records</h1></div><div class="card"><form method="GET">
    <div class="class-filter"><div><label>Course</label><select name="course">{options_course}</select></div>
    <div><label>Year Level</label><select name="year_level">{options_year}</select></div><div><label>Date</label>
    <input type="date" name="date" value="{attendance_date}"></div></div><button class="btn primary">
    Apply Filters</button> <a class="btn secondary" href="{url_for('attendance')}">Reset</a></form></div>
    <div class="card"><div class="table-container"><table><tr><th>Student ID</th><th>Name</th><th>Course</th>
    <th>Major</th><th>Year Level</th><th>Date</th><th>Time In</th><th>Status</th></tr>{rows}</table></div></div>"""
    return render_page(content, "Attendance")


@app.route("/assessments")
@login_required
def assessments():
    user=current_user()
    q=Assessment.query.join(Student)
    if user.role != "admin":
        q=q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == Assessment.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    records=q.order_by(
        Assessment.assessment_date.desc(),Assessment.id.desc()
    ).all()
    rows="".join(
        f"<tr><td>{a.assessment_date}</td><td>{a.student.student_id}</td><td>{a.student.full_name}</td>"
        f"<td>{a.course or a.student.course}</td><td>{a.assessment_name or a.assessment_type}</td>"
        f"<td>{a.score:.1f}/{a.total_score:.1f}</td><td>{a.percentage:.1f}%</td>"
        f"<td>{(a.weight or 0):.1f}%</td></tr>"
        for a in records
    ) or "<tr><td colspan='8' class='empty'>No assessments yet.</td></tr>"
    content=f"""<div class="page-header"><div><h1>Assessments / Grades</h1><p class="muted">
    Select a class and assessment. The student roster comes automatically from the Student database.
    Only records belonging to your assigned classes are accessible.</p></div><a href="{url_for('add_assessment')}"
    class="btn primary">+ Class Assessment</a></div><div class="card"><div class="table-container">
    <table><tr><th>Date</th><th>ID</th><th>Student</th><th>Class</th><th>Assessment</th><th>Score</th>
    <th>Percentage</th><th>Weight</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Assessments")


@app.route("/assessments/configs")
@login_required
def assessment_configs():
    user=current_user()
    q=AssessmentConfig.query
    if user.role != "admin":
        q=q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == AssessmentConfig.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    items=q.order_by(
        AssessmentConfig.course,AssessmentConfig.year_level,AssessmentConfig.assessment_name
    ).all()
    rows="".join(
        f"<tr><td>{c.course}</td><td>{c.year_level}</td><td>{c.major or ''}</td>"
        f"<td>{c.section or ''}</td><td>{c.assessment_type}</td><td>{c.assessment_name}</td>"
        f"<td>{c.total_score:g}</td><td>{c.weight:g}%</td></tr>"
        for c in items
    ) or "<tr><td colspan='8' class='empty'>No saved assessment configurations.</td></tr>"
    content=f"""<div class="page-header"><h1>Saved Assessment Configurations</h1><a href="{url_for('add_assessment')}"
    class="btn primary">+ New Assessment</a></div><div class="card"><div class="table-container">
    <table><tr><th>Course</th><th>Year</th><th>Major</th><th>Section</th><th>Type</th><th>Name</th>
    <th>Total</th><th>Weight</th></tr>{rows}</table></div></div>"""
    return render_page(content,"Assessment Configurations")


@app.route("/assessments/add",methods=["GET","POST"])
@login_required
def add_assessment():
    user=current_user()
    if request.method=="POST":
        course=request.form.get("course","").strip()
        year=request.form.get("year_level","").strip()
        major=request.form.get("major","").strip()
        section=request.form.get("section","").strip()
        a_type=request.form.get("assessment_type","").strip()
        name=request.form.get("assessment_name","").strip()
        total_raw=request.form.get("total_score","").strip()
        weight_raw=request.form.get("weight","0").strip()
        a_date=request.form.get("assessment_date","").strip()

        try:
            total=float(total_raw)
            weight=float(weight_raw or 0)
            adate=datetime.strptime(a_date,"%Y-%m-%d").date()
        except:
            flash("Enter valid assessment details.","danger")
            return redirect(url_for("add_assessment"))
        if total<=0 or weight<0 or weight>100:
            flash("Total score must be greater than 0 and weight must be between 0 and 100.","danger")
            return redirect(url_for("add_assessment"))

        # Resolve the exact assigned schedule. The client-supplied course/year
        # fields are NOT trusted for authorization.
        schedule_q=AttendanceSchedule.query.filter_by(
            course=course,year_level=year,major=major or None,section=section or None,
            active=True
        )
        if user.role == "admin":
            schedule=schedule_q.order_by(AttendanceSchedule.id).first()
        else:
            schedule=schedule_q.join(
                FacultySchedule,
                FacultySchedule.schedule_id == AttendanceSchedule.id
            ).filter(FacultySchedule.faculty_id == user.id).first()

        if not schedule:
            flash("You are not assigned to that class.","danger")
            return redirect(url_for("add_assessment"))

        roster=class_students(course,year,major,section,user)
        if not roster:
            flash("No active students match that assigned class.","danger")
            return redirect(url_for("add_assessment"))

        config=AssessmentConfig.query.filter_by(
            course=course,year_level=year,major=major or None,section=section or None,
            assessment_type=a_type,assessment_name=name,schedule_id=schedule.id
        ).first()
        if config:
            config.total_score=total
            config.weight=weight
            config.active=True
            config.faculty_id=user.id if user.role != "admin" else config.faculty_id
        else:
            config=AssessmentConfig(
                faculty_id=user.id if user.role != "admin" else None,
                schedule_id=schedule.id,course=course,year_level=year,
                major=major or None,section=section or None,
                assessment_type=a_type,assessment_name=name,
                total_score=total,weight=weight,active=True
            )
            db.session.add(config)
            db.session.flush()

        saved=0
        for st in roster:
            raw=request.form.get(f"score_{st.id}","").strip()
            if raw=="":
                continue
            try:
                score=float(raw)
            except:
                continue
            if score<0 or score>total:
                flash(f"Invalid score for {st.full_name}. Score must be between 0 and {total:g}.","danger")
                db.session.rollback()
                return redirect(url_for("add_assessment"))

            existing=Assessment.query.filter_by(
                student_id=st.id,assessment_date=adate,
                assessment_type=a_type,assessment_name=name,
                schedule_id=schedule.id
            ).first()
            if existing:
                if not faculty_can_access_assessment(existing,user):
                    db.session.rollback()
                    return "Forbidden",403
                existing.score=score
                existing.total_score=total
                existing.percentage=round((score/total)*100,2)
                existing.weight=weight
                existing.config_id=config.id
                existing.faculty_id=user.id if user.role != "admin" else existing.faculty_id
                existing.course=course
                existing.year_level=year
                existing.major=major or None
                existing.section=section or None
            else:
                db.session.add(Assessment(
                    student_id=st.id,
                    faculty_id=user.id if user.role != "admin" else None,
                    schedule_id=schedule.id,
                    assessment_type=a_type,assessment_name=name,
                    score=score,total_score=total,
                    percentage=round((score/total)*100,2),
                    assessment_date=adate,weight=weight,
                    config_id=config.id,course=course,year_level=year,
                    major=major or None,section=section or None
                ))
            saved+=1
        db.session.commit()
        flash(f"Assessment saved for {saved} student(s). Configuration saved for reuse.","success")
        return redirect(url_for("assessments"))

    classes=get_class_options(user)
    class_opts="<option value=''>Select class</option>"+"".join(
        f"<option data-course='{c}' data-year='{y}' data-major='{m or ''}' data-section='{s or ''}' "
        f"value='{c}|{y}|{m or ''}|{s or ''}'>{c} • {y} • {m or 'No Major'} • {s or 'No Section'}</option>"
        for c,y,m,s in classes
    )
    types="".join(f"<option>{x}</option>" for x in ASSESSMENT_TYPES)
    content=f"""<div class="page-header"><h1>Class-Based Assessment</h1><a href="{url_for('assessment_configs')}"
    class="btn secondary">Saved Configurations</a></div><div class="card"><div class="help">Choose an assigned
    class. Active students are loaded automatically. Authorization is checked again when scores are saved.</div>
    <label>Class / Cohort</label><select id="classSelect" onchange="loadClass()" required>{class_opts}</select>
    <form method="POST" id="gradeForm"><input type="hidden" name="course" id="course"><input type="hidden"
    name="year_level" id="year_level"><input type="hidden" name="major" id="major"><input type="hidden"
    name="section" id="section"><div class="grid2"><div><label>Assessment Type</label><select
    name="assessment_type" id="assessmentType" onchange="loadConfig()" required>{types}</select></div>
    <div><label>Assessment Name</label><input name="assessment_name" id="assessmentName" placeholder="Quiz 1"
    onblur="loadConfig()" required></div><div><label>Total Score</label><input type="number" step="0.01"
    name="total_score" id="totalScore" required></div><div><label>Percentage / Weight</label><input type="number"
    step="0.01" min="0" max="100" name="weight" id="weight" value="0" required></div><div><label>Assessment Date</label>
    <input type="date" name="assessment_date" value="{date.today()}" required></div></div><div id="roster"
    class="card"><p class="muted">Select a class to load students.</p></div><div class="form-actions">
    <a href="{url_for('assessments')}" class="btn secondary">Cancel</a><button class="btn primary">Save All Scores</button>
    </div></form></div>
    <script>
    function loadClass(){{
      const o=document.getElementById('classSelect').selectedOptions[0]; if(!o||!o.value)return;
      const p=o.value.split('|');document.getElementById('course').value=p[0];
      document.getElementById('year_level').value=p[1];document.getElementById('major').value=p[2];
      document.getElementById('section').value=p[3];loadRoster();loadConfig();
    }}
    async function loadRoster(){{
      const q=new URLSearchParams({{course:document.getElementById('course').value,
      year_level:document.getElementById('year_level').value,major:document.getElementById('major').value,
      section:document.getElementById('section').value}});
      const r=await fetch('{url_for('api_class_students')}?'+q.toString());
      if(!r.ok)return;const d=await r.json();
      let h='<div class="table-container"><table><tr><th>Student ID</th><th>Student Name</th><th>Score</th><th>Total Score</th><th>Percentage</th></tr>';
      if(!d.students.length)h+='<tr><td colspan="5" class="empty">No active students found for this class.</td></tr>';
      d.students.forEach(s=>h+=`<tr><td>${{s.student_id}}</td><td>${{s.full_name}}</td><td><input
      class="score-input" type="number" min="0" step="0.01" max="${{document.getElementById('totalScore').value||0}}"
      name="score_${{s.id}}" oninput="calc(this)"></td><td class="total-cell">${{document.getElementById('totalScore').value||'0'}}</td>
      <td class="pct-cell">0.00%</td></tr>`);
      h+='</table></div>';document.getElementById('roster').innerHTML=h;
    }}
    function calc(el){{const row=el.closest('tr');const total=parseFloat(document.getElementById('totalScore').value)||0;
      row.querySelector('.total-cell').textContent=total;row.querySelector('.pct-cell').textContent=total?
      ((parseFloat(el.value)||0)/total*100).toFixed(2)+'%':'0.00%';}}
    async function loadConfig(){{
      const c=document.getElementById('course').value,y=document.getElementById('year_level').value,
      m=document.getElementById('major').value,s=document.getElementById('section').value,
      t=document.getElementById('assessmentType').value,n=document.getElementById('assessmentName').value;
      if(!c||!y||!n)return;const q=new URLSearchParams({{course:c,year_level:y,major:m,section:s,
      assessment_type:t,assessment_name:n}});const r=await fetch('{url_for('api_assessment_config')}?'+q.toString());
      if(!r.ok)return;const d=await r.json();if(d.found){{document.getElementById('totalScore').value=d.total_score;
      document.getElementById('weight').value=d.weight;loadRoster();}}
    }}
    document.getElementById('totalScore').addEventListener('input',()=>{{
      document.querySelectorAll('.score-input').forEach(calc);
    }});
    </script>"""
    return render_page(content,"Class-Based Assessment")


@app.route("/api/class-students")
@login_required
def api_class_students():
    user=current_user()
    course=request.args.get("course","").strip()
    year=request.args.get("year_level","").strip()
    major=request.args.get("major","").strip()
    section=request.args.get("section","").strip()

    if user.role != "admin" and not faculty_can_access_class(course,year,major,section,user):
        return jsonify({"success":False,"message":"Forbidden"}),403

    items=class_students(course,year,major,section,user)
    return jsonify({
        "students":[{"id":s.id,"student_id":s.student_id,"full_name":s.full_name} for s in items]
    })


@app.route("/api/assessment-config")
@login_required
def api_assessment_config():
    user=current_user()
    c=request.args.get("course","").strip()
    y=request.args.get("year_level","").strip()
    m=request.args.get("major","").strip()
    s=request.args.get("section","").strip()
    t=request.args.get("assessment_type","").strip()
    n=request.args.get("assessment_name","").strip()

    if user.role != "admin" and not faculty_can_access_class(c,y,m,s,user):
        return jsonify({"success":False,"message":"Forbidden"}),403

    q=AssessmentConfig.query.filter_by(
        course=c,year_level=y,major=m or None,section=s or None,
        assessment_type=t,assessment_name=n,active=True
    )
    if user.role != "admin":
        q=q.join(
            FacultySchedule,
            FacultySchedule.schedule_id == AssessmentConfig.schedule_id
        ).filter(FacultySchedule.faculty_id == user.id)
    cfg=q.order_by(AssessmentConfig.id.desc()).first()
    if not cfg:
        return jsonify({"found":False})
    return jsonify({"found":True,"total_score":cfg.total_score,"weight":cfg.weight})

with app.app_context():
    migrate_existing_database()
 
if __name__=="__main__":
    app.run(debug=True)
