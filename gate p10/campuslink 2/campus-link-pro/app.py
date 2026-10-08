import sqlite3
import csv
import hmac
import io
import json
import os
import random
import re
import secrets
import zipfile
from datetime import date, datetime, time, timedelta
from xml.sax.saxutils import escape

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from config import Config
from database import get_db_connection, create_tables
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)




app = Flask(__name__)
app.config.from_object(Config)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
)

MAX_CERTIFICATE_SIZE = 10 * 1024 * 1024
MAX_RESUME_SIZE = 10 * 1024 * 1024
RESUME_TYPES = {
    ".pdf": (
        "application/pdf",
        lambda data: data.startswith(b"%PDF-"),
    ),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        lambda data: valid_docx_file(data),
    ),
}
CERTIFICATE_TYPES = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}


def valid_docx_file(data):
    """Confirm an uploaded Word document is a bounded, readable DOCX archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as document:
            members = {item.filename: item for item in document.infolist()}
            required_files = {"[Content_Types].xml", "word/document.xml"}
            if not required_files.issubset(members):
                return False
            if sum(item.file_size for item in members.values()) > 20 * 1024 * 1024:
                return False
            if any(members[name].file_size > MAX_RESUME_SIZE for name in required_files):
                return False
            return all(document.read(name) for name in required_files)
    except (OSError, RuntimeError, zipfile.BadZipFile, KeyError):
        return False


def parse_student_skills(value):
    """Return every non-empty skill from comma-, semicolon-, or line-separated text."""
    skills = []
    seen = set()
    for item in re.split(r"[,;\r\n]+", value or ""):
        skill = item.strip()
        key = skill.casefold()
        if skill and key not in seen:
            skills.append(skill)
            seen.add(key)
    return skills


SKILL_ALIASES = {
    "js": "javascript",
    "py": "python",
    "structured query language": "sql",
    "dsa": "data structures and algorithms",
    "data structures & algorithms": "data structures and algorithms",
    "c plus plus": "c++",
    "c sharp": "c#",
}

SKILL_DISPLAY_NAMES = {
    "python": "Python",
    "sql": "SQL",
    "java": "Java",
    "javascript": "JavaScript",
    "git": "Git",
    "data structures and algorithms": "Data Structures and Algorithms",
    "algorithms": "Algorithms",
    "communication": "Communication",
    "react": "React",
    "c++": "C++",
    "c#": "C#",
    "cloud": "Cloud",
    "html": "HTML",
    "css": "CSS",
    "flask": "Flask",
    "api": "API",
}


def canonical_skill_key(skill):
    """Normalize common skill aliases so equivalent labels match consistently."""
    key = re.sub(r"\s+", " ", skill.strip().casefold())
    return SKILL_ALIASES.get(key, key)


def recommend_skill_development(
    skill, student_skills=(), matched_skills=(), role=""
):
    """Build a practical next step from the candidate's listed strengths and target role."""
    next_steps = {
        "python": "Practice core syntax and data structures, then expose one feature through a small script or API.",
        "sql": "Model a few related tables, then demonstrate SELECT, JOIN, grouping, and filtering queries.",
        "java": "Use classes, collections, and error handling to implement one feature end to end.",
        "javascript": "Build an interactive page that uses DOM updates and asynchronous data loading.",
        "git": "Use a feature branch, focused commits, a merge, and a clear pull-request description.",
        "dsa": "Solve one array, tree, or graph problem at a time and explain its time and space complexity.",
        "data structures and algorithms": "Solve one array, tree, or graph problem at a time and explain its time and space complexity.",
        "algorithms": "Solve problems by pattern and compare the time and space complexity of each solution.",
        "communication": "Explain one project using the problem, your contribution, and the measurable result; then practice follow-up questions.",
        "react": "Build a component-based interface and demonstrate state, props, and one user interaction.",
        "c++": "Use STL containers and problem-solving patterns to implement and test a small feature.",
        "cloud": "Deploy a small application and document its services, configuration, and monitoring.",
    }
    known_skills = {
        canonical_skill_key(item): item
        for item in student_skills
    }
    strengths = []
    strength_keys = set()
    for item in [*matched_skills, *student_skills]:
        key = canonical_skill_key(item)
        if key != canonical_skill_key(skill) and key not in strength_keys:
            listed_skill = known_skills.get(key, item)
            strengths.append(
                SKILL_DISPLAY_NAMES.get(
                    key,
                    listed_skill.title() if listed_skill.isupper() else listed_skill,
                )
            )
            strength_keys.add(key)
        if len(strengths) == 2:
            break

    role_label = role.strip() or "target role"
    next_step = next_steps.get(
        canonical_skill_key(skill),
        f"Learn {skill} fundamentals, complete guided exercises, and demonstrate them in a small project.",
    )
    if strengths:
        strength_label = " and ".join(strengths)
        if canonical_skill_key(skill) == "communication":
            return (
                f"Use your {strength_label} project to prepare a concise story "
                f"for the {role_label} role: explain the problem, your contribution, "
                "and the result, then practice follow-up questions."
            )
        return (
            f"Build a small project for the {role_label} role that combines your "
            f"{strength_label} experience with {skill}. {next_step}"
        )
    return (
        f"Start with {skill} fundamentals for the {role_label} role. "
        f"{next_step}"
    )


def score_student_for_job(student, job):
    """Calculate an explainable, eligibility-aware score for a student and drive."""
    student_skill_list = parse_student_skills(student["skills"])
    student_skills = {
        canonical_skill_key(skill) for skill in student_skill_list
    }
    required_skills = []
    required_skill_keys = set()
    for skill in parse_student_skills(job["required_skills"]):
        key = canonical_skill_key(skill)
        if key not in required_skill_keys:
            required_skills.append(skill)
            required_skill_keys.add(key)
    matched_skills = [
        skill for skill in required_skills
        if canonical_skill_key(skill) in student_skills
    ]
    skill_gaps = [
        skill for skill in required_skills
        if canonical_skill_key(skill) not in student_skills
    ]
    skills_score = (
        round(len(matched_skills) / len(required_skills) * 100)
        if required_skills
        else 100
    )

    eligible_branches = parse_student_skills(job["eligible_branches"])
    all_branches = (
        not eligible_branches
        or any(
            branch.casefold() in {"all", "all branches", "any", "*"}
            for branch in eligible_branches
        )
    )
    branch_match = (
        all_branches
        or student["branch"].strip().casefold()
        in {branch.casefold() for branch in eligible_branches}
    )
    cgpa = float(student["cgpa"] or 0)
    minimum_cgpa = float(job["min_cgpa"] or 0)
    cgpa_score = round(min(100, max(0, cgpa / 10 * 100)))
    backlogs = int(student["backlogs"] or 0)
    maximum_backlogs = int(job["max_backlogs"] or 0)
    attendance = float(student["attendance"] or 0)
    minimum_attendance = float(job["min_attendance"] or 0)
    attendance_score = (
        round(min(100, max(0, attendance / minimum_attendance * 100)))
        if minimum_attendance > 0
        else 100
    )
    backlog_score = 100 if backlogs <= maximum_backlogs else 0
    branch_score = 100 if branch_match else 0

    score = round(
        skills_score * 0.40
        + cgpa_score * 0.30
        + branch_score * 0.20
        + backlog_score * 0.05
        + attendance_score * 0.05
    )

    eligibility_reasons = []
    requirement_gaps = []
    if not branch_match:
        eligibility_reasons.append("Branch is not eligible")
        branch_requirement = ", ".join(eligible_branches)
        requirement_gaps.append(
            f"Branch: {student['branch']} (drive accepts {branch_requirement})"
        )
    if cgpa < minimum_cgpa:
        eligibility_reasons.append(f"CGPA below {minimum_cgpa:g}")
        requirement_gaps.append(
            f"CGPA: {cgpa:g} / {minimum_cgpa:g} required "
            f"({minimum_cgpa - cgpa:.2f} below minimum)"
        )
    if backlogs > maximum_backlogs:
        eligibility_reasons.append(f"More than {maximum_backlogs} active backlogs")
        requirement_gaps.append(
            f"Backlogs: {backlogs} / maximum {maximum_backlogs}"
        )
    if attendance < minimum_attendance:
        eligibility_reasons.append(f"Attendance below {minimum_attendance:g}%")
        requirement_gaps.append(
            f"Attendance: {attendance:g}% / {minimum_attendance:g}% required "
            f"({minimum_attendance - attendance:.1f}% below minimum)"
        )

    return {
        "score": score,
        "skills_score": skills_score,
        "matched_skills": matched_skills,
        "skill_gaps": skill_gaps,
        "skill_recommendations": [
            {
                "skill": skill,
                "recommendation": recommend_skill_development(
                    skill,
                    student_skills=student_skill_list,
                    matched_skills=matched_skills,
                    role=job["role"],
                ),
            }
            for skill in skill_gaps
        ],
        "required_skill_count": len(required_skills),
        "eligible": not eligibility_reasons,
        "eligibility_reasons": eligibility_reasons,
        "requirement_gaps": requirement_gaps,
        "has_application": bool(student["application_id"]),
    }


def resume_readiness(resume):
    """Return Ready only when the essential resume sections contain real content."""
    return bool(
        resume
        and resume["professional_summary"].strip()
        and resume["education"].strip()
        and resume["skills"].strip()
    )


def pdf_safe_text(value):
    """Keep user-entered content safe for ReportLab's built-in PDF fonts."""
    return str(value or "").encode("latin-1", "replace").decode("latin-1")


def add_resume_section(story, title, content, heading_style, body_style, bullet=False):
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    if not lines:
        return
    story.append(Paragraph(escape(pdf_safe_text(title)).upper(), heading_style))
    story.append(HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#dbe3f0"), spaceAfter=7))
    for line in lines:
        story.append(
            Paragraph(
                f"&bull;&nbsp;&nbsp;{escape(pdf_safe_text(line))}" if bullet else escape(pdf_safe_text(line)),
                body_style,
            )
        )
    story.append(Spacer(1, 9))


def parse_job_date(value):
    """Parse stored drive dates in the supported form and display formats."""
    value = (value or "").strip()
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(value, date_format).date()
                except ValueError:
                    continue
    return None


def format_job_date(value):
    """Render a stored job date in a readable, unambiguous format."""
    parsed_date = parse_job_date(value)
    return parsed_date.strftime("%d %b %Y") if parsed_date else (value or "—")


app.jinja_env.filters["job_date"] = format_job_date


def normalize_job_status(status=None, drive_date=None, application_deadline=None):
    """Return a drive status from its deadline and scheduled drive date."""
    today = date.today()
    drive_value = (drive_date or "").strip()
    deadline_value = (application_deadline or "").strip()
    drive_day = parse_job_date(drive_value)
    deadline_day = parse_job_date(deadline_value)

    if (drive_value and drive_day is None) or (deadline_value and deadline_day is None):
        return "Date needs review"
    if (deadline_day and deadline_day < today) or (drive_day and drive_day < today):
        return "Closed"
    if drive_day and drive_day > today:
        return "Upcoming"
    if drive_day == today:
        return "Active"
    if deadline_day:
        return "Active"

    status_value = (status or "Active").strip()
    return status_value if status_value in {"Active", "Upcoming", "Closed"} else "Date needs review"


def is_job_open_for_applications(job):
    """Check whether a drive is current and its application deadline is open."""
    status = normalize_job_status(
        job["status"],
        job["drive_date"],
        job["application_deadline"]
    )
    if status not in {"Active", "Upcoming"}:
        return False

    deadline = parse_job_date(job["application_deadline"])
    if job["application_deadline"] and deadline is None:
        return False
    if deadline and deadline < date.today():
        return False

    return True


def sync_job_drive_statuses(connection):
    """Persist date-derived statuses so all job-drive views stay consistent."""
    jobs = connection.execute(
        """
        SELECT id, status, drive_date, application_deadline
        FROM jobs
        """
    ).fetchall()

    for job in jobs:
        status = normalize_job_status(
            job["status"],
            job["drive_date"],
            job["application_deadline"]
        )
        if status != job["status"]:
            connection.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job["id"])
            )

    connection.commit()



create_tables()

ROLE_LABELS = {
    "admin": "Administrator",
    "placement_officer": "Placement Officer",
    "student": "Student",
}

STUDENT_ENDPOINTS = {
    "student_home",
    "mock_tests",
    "start_mock_test",
    "view_mock_test",
    "edit_resume",
    "download_resume",
    "communication_inbox",
    "reply_to_communication",
    "mark_communication_read",
    "mark_all_communications_read",
    "upload_resume",
    "download_original_resume",
}


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.before_request
def load_authenticated_user():
    g.current_user = None
    if request.endpoint == "static":
        return None

    connection = get_db_connection()
    try:
        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        user_id = session.get("user_id")
        if user_id is not None:
            g.current_user = connection.execute(
                """
                SELECT id, name, email, role, student_id, is_active
                FROM users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if g.current_user is None or not g.current_user["is_active"]:
                session.clear()
                g.current_user = None
    finally:
        connection.close()

    if request.method == "POST":
        submitted_token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRFToken", "")
        )
        expected_token = session.get("_csrf_token", "")
        if not submitted_token or not hmac.compare_digest(
            submitted_token, expected_token
        ):
            abort(400, description="Your session token is invalid. Refresh and try again.")

    if request.endpoint == "login":
        if g.current_user:
            return redirect(
                url_for("student_home")
                if g.current_user["role"] == "student"
                else url_for("dashboard")
            )
        return None

    if request.endpoint == "setup":
        if user_count:
            return redirect(url_for("login"))
        return None

    if request.endpoint == "logout":
        return None

    if user_count == 0 and request.endpoint == "login":
        return None

    if g.current_user is None:
        return redirect(url_for("login"))

    role = g.current_user["role"]
    if role not in ROLE_LABELS:
        abort(403)

    if role == "student":
        if request.endpoint not in STUDENT_ENDPOINTS:
            abort(403)
        if g.current_user["student_id"] is None:
            abort(403, description="This student account is not linked to a student profile.")
        student_id = request.view_args.get("student_id") if request.view_args else None
        if student_id is not None and student_id != g.current_user["student_id"]:
            abort(403)
        attempt_id = request.view_args.get("attempt_id") if request.view_args else None
        if attempt_id is not None:
            connection = get_db_connection()
            try:
                owned_attempt = connection.execute(
                    """
                    SELECT 1 FROM mock_test_attempts
                    WHERE id = ? AND student_id = ?
                    """,
                    (attempt_id, g.current_user["student_id"]),
                ).fetchone()
            finally:
                connection.close()
            if owned_attempt is None:
                abort(404)
    elif request.endpoint == "admin_users" and role != "admin":
        abort(403)


@app.context_processor
def inject_auth_context():
    return {
        "current_user": getattr(g, "current_user", None),
        "role_labels": ROLE_LABELS,
        "csrf_token": csrf_token,
    }


@app.errorhandler(403)
def forbidden(error):
    return render_template("errors/403.html", error=error), 403

connection = get_db_connection()
try:
    sync_job_drive_statuses(connection)
finally:
    connection.close()


@app.context_processor
def inject_notifications():
    """Provide current placement-workflow notifications to every page."""
    today = date.today()
    week_ahead = (today + timedelta(days=7)).isoformat()
    connection = get_db_connection()
    try:
        application_summary = connection.execute(
            """
            SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS latest_id
            FROM applications
            WHERE status IN ('Applied', 'In Progress')
            """
        ).fetchone()
        interview_summary = connection.execute(
            """
            SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS latest_id
            FROM interviews
            WHERE interview_date >= ? AND interview_date <= ?
              AND status IN ('Scheduled', 'Pending')
            """,
            (today.isoformat(), week_ahead),
        ).fetchone()
        offer_summary = connection.execute(
            """
            SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS latest_id
            FROM offers
            WHERE lower(trim(status)) = 'pending'
            """
        ).fetchone()
        summaries = {
            "applications": application_summary,
            "interviews": interview_summary,
            "offers": offer_summary,
        }
        signatures = [
            f"{key}:{summary['total']}:{summary['latest_id']}"
            for key, summary in summaries.items()
            if summary["total"]
        ]
        read_signatures = {
            row["notification_signature"]
            for row in connection.execute(
                """
                SELECT notification_signature
                FROM admin_notification_receipts
                WHERE notification_signature IN (
                    """ + ",".join("?" for _ in signatures) + """)
                """,
                signatures,
            ).fetchall()
        } if signatures else set()
    finally:
        connection.close()

    notifications = []
    application_count = application_summary["total"]
    application_signature = f"applications:{application_summary['total']}:{application_summary['latest_id']}"
    if application_count and application_signature not in read_signatures:
        notifications.append({
            "key": "applications",
            "signature": application_signature,
            "title": "Applications need review",
            "message": f"{application_count} candidates are awaiting a placement-stage review.",
            "count": application_count,
            "url": url_for("applications"),
            "icon": "fa-file-lines",
            "tone": "blue",
        })
    interview_count = interview_summary["total"]
    interview_signature = f"interviews:{interview_summary['total']}:{interview_summary['latest_id']}"
    if interview_count and interview_signature not in read_signatures:
        notifications.append({
            "key": "interviews",
            "signature": interview_signature,
            "title": "Interviews coming up",
            "message": f"{interview_count} interview rounds are scheduled within the next 7 days.",
            "count": interview_count,
            "url": url_for("interviews"),
            "icon": "fa-calendar-check",
            "tone": "purple",
        })
    offer_count = offer_summary["total"]
    offer_signature = f"offers:{offer_summary['total']}:{offer_summary['latest_id']}"
    if offer_count and offer_signature not in read_signatures:
        notifications.append({
            "key": "offers",
            "signature": offer_signature,
            "title": "Offer decisions pending",
            "message": f"{offer_count} offer{'s' if offer_count != 1 else ''} need a decision.",
            "count": offer_count,
            "url": url_for("offers"),
            "icon": "fa-award",
            "tone": "amber",
        })

    return {
        "placement_notifications": notifications,
        "notification_count": sum(item["count"] for item in notifications),
    }


@app.route("/notifications/read", methods=["POST"])
def mark_notifications_read():
    payload = request.get_json(silent=True)
    signatures = payload.get("signatures") if isinstance(payload, dict) else None
    if (
        not isinstance(signatures, list)
        or len(signatures) > 3
        or any(
            not isinstance(signature, str)
            or not re.fullmatch(r"(applications|interviews|offers):\d+:\d+", signature)
            for signature in signatures
        )
    ):
        return jsonify({"error": "Invalid notification receipt request."}), 400

    connection = get_db_connection()
    try:
        connection.executemany(
            """
            INSERT OR IGNORE INTO admin_notification_receipts
                (notification_signature)
            VALUES (?)
            """,
            [(signature,) for signature in signatures],
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not save notification read state")
        return jsonify({"error": "Unable to update notifications."}), 500
    finally:
        connection.close()
    return jsonify({"marked_read": len(signatures)})


def communication_audience_filter():
    return """
        communications.audience_type = 'all'
        OR (
            communications.audience_type = 'branch'
            AND communications.target_branch = students.branch
        )
        OR (
            communications.audience_type = 'student'
            AND communications.target_student_id = students.id
        )
    """


@app.route("/communications", methods=["GET", "POST"])
def communications():
    connection = get_db_connection()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        category = request.form.get("category", "Announcement").strip()
        audience_type = request.form.get("audience_type", "all").strip()
        target_branch = request.form.get("target_branch", "").strip()
        target_student_id = request.form.get("target_student_id", type=int)
        allowed_categories = {
            "Announcement", "Opportunity", "Deadline", "Interview", "General"
        }

        error = None
        if not title or len(title) > 120:
            error = "Enter a message title between 1 and 120 characters."
        elif not body or len(body) > 4000:
            error = "Enter message content between 1 and 4,000 characters."
        elif category not in allowed_categories:
            error = "Choose a valid communication category."
        elif audience_type not in {"all", "branch", "student"}:
            error = "Choose a valid message audience."
        elif audience_type == "branch" and not target_branch:
            error = "Choose a branch for this message."
        elif audience_type == "student" and not target_student_id:
            error = "Choose a student for this message."

        if error is None and audience_type == "branch":
            branch_exists = connection.execute(
                "SELECT 1 FROM students WHERE branch = ? LIMIT 1",
                (target_branch,),
            ).fetchone()
            if branch_exists is None:
                error = "Choose a branch that has students."
        elif error is None and audience_type == "student":
            student_exists = connection.execute(
                "SELECT 1 FROM students WHERE id = ?",
                (target_student_id,),
            ).fetchone()
            if student_exists is None:
                error = "The selected student was not found."

        if error:
            connection.close()
            flash(error, "error")
            return redirect(url_for("communications"))

        try:
            connection.execute(
                """
                INSERT INTO communications
                    (title, body, category, audience_type, target_branch,
                     target_student_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    body,
                    category,
                    audience_type,
                    target_branch if audience_type == "branch" else None,
                    target_student_id if audience_type == "student" else None,
                ),
            )
            connection.commit()
            flash("Message sent to the selected student audience.", "success")
        except sqlite3.Error:
            connection.rollback()
            app.logger.exception("Could not send a communication")
            flash("Unable to send this message. Please try again.", "error")
        finally:
            connection.close()
        return redirect(url_for("communications"))

    try:
        branches = connection.execute(
            """
            SELECT DISTINCT branch FROM students
            WHERE trim(COALESCE(branch, '')) != ''
            ORDER BY branch COLLATE NOCASE
            """
        ).fetchall()
        students = connection.execute(
            """
            SELECT id, name, registration_no, branch
            FROM students
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        messages = connection.execute(
            """
            SELECT communications.*,
                CASE communications.audience_type
                    WHEN 'all' THEN 'All students'
                    WHEN 'branch' THEN 'Branch: ' || communications.target_branch
                    ELSE COALESCE(
                        (SELECT name FROM students
                         WHERE id = communications.target_student_id),
                        'Student unavailable'
                    )
                END AS audience_label,
                CASE communications.audience_type
                    WHEN 'all' THEN (SELECT COUNT(*) FROM students)
                    WHEN 'branch' THEN
                        (SELECT COUNT(*) FROM students
                         WHERE branch = communications.target_branch)
                    ELSE 1
                END AS recipient_count,
                (SELECT COUNT(*)
                 FROM communication_reads
                 WHERE communication_reads.communication_id = communications.id)
                    AS read_count
            FROM communications
            ORDER BY communications.created_at DESC, communications.id DESC
            """
        ).fetchall()
        unread_counts = connection.execute(
            f"""
            SELECT students.id, COUNT(communications.id) AS unread_count
            FROM students
            LEFT JOIN communications
                ON ({communication_audience_filter()})
            LEFT JOIN communication_reads
                ON communication_reads.communication_id = communications.id
               AND communication_reads.student_id = students.id
            WHERE communication_reads.read_at IS NULL
            GROUP BY students.id
            """
        ).fetchall()
        thread_rows = connection.execute(
            """
            SELECT communication_replies.communication_id,
                   communication_replies.student_id,
                   COUNT(*) AS reply_count,
                   MAX(communication_replies.id) AS latest_reply_id,
                   communications.title,
                   communications.body AS original_body,
                   communications.category,
                   students.name AS student_name,
                   students.registration_no
            FROM communication_replies
            JOIN communications
                ON communications.id = communication_replies.communication_id
            JOIN students ON students.id = communication_replies.student_id
            GROUP BY communication_replies.communication_id,
                     communication_replies.student_id
            ORDER BY latest_reply_id DESC
            """
        ).fetchall()
        reply_rows = connection.execute(
            """
            SELECT communication_id, student_id, sender_type, body, created_at
            FROM communication_replies
            ORDER BY id
            """
        ).fetchall()
    finally:
        connection.close()

    replies_by_thread = {}
    for reply in reply_rows:
        thread_key = (reply["communication_id"], reply["student_id"])
        replies_by_thread.setdefault(thread_key, []).append(dict(reply))
    conversation_threads = []
    for thread in thread_rows:
        thread_data = dict(thread)
        thread_data["replies"] = replies_by_thread.get(
            (thread["communication_id"], thread["student_id"]),
            [],
        )
        thread_data["awaiting_officer"] = (
            bool(thread_data["replies"])
            and thread_data["replies"][-1]["sender_type"] == "student"
        )
        conversation_threads.append(thread_data)

    return render_template(
        "communications/index.html",
        branches=branches,
        students=students,
        messages=messages,
        total_students=len(students),
        unread_by_student={row["id"]: row["unread_count"] for row in unread_counts},
        conversation_threads=conversation_threads,
        unanswered_count=sum(
            1 for thread in conversation_threads if thread["awaiting_officer"]
        ),
    )


@app.route("/communications/inbox/<int:student_id>", methods=["GET"])
def communication_inbox(student_id):
    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT id, name, registration_no, branch FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if student is None:
            abort(404)
        message_rows = connection.execute(
            f"""
            SELECT communications.*, communication_reads.read_at
            FROM communications
            JOIN students ON students.id = ?
            LEFT JOIN communication_reads
                ON communication_reads.communication_id = communications.id
               AND communication_reads.student_id = students.id
            WHERE ({communication_audience_filter()})
            ORDER BY communications.created_at DESC, communications.id DESC
            """,
            (student_id,),
        ).fetchall()
        reply_rows = connection.execute(
            """
            SELECT communication_id, sender_type, body, created_at
            FROM communication_replies
            WHERE student_id = ?
            ORDER BY id
            """,
            (student_id,),
        ).fetchall()
    finally:
        connection.close()
    replies_by_message = {}
    for reply in reply_rows:
        replies_by_message.setdefault(reply["communication_id"], []).append(
            dict(reply)
        )
    messages = []
    for message in message_rows:
        message_data = dict(message)
        message_data["replies"] = replies_by_message.get(message["id"], [])
        message_data["new_officer_reply"] = (
            message_data["read_at"] is None
            and bool(message_data["replies"])
            and message_data["replies"][-1]["sender_type"] == "officer"
        )
        messages.append(message_data)
    return render_template(
        "communications/inbox.html",
        student=student,
        messages=messages,
        unread_count=sum(1 for message in messages if message["read_at"] is None),
    )


@app.route(
    "/communications/<int:communication_id>/reply/student/<int:student_id>",
    methods=["POST"],
)
def reply_to_communication(communication_id, student_id):
    body = request.form.get("body", "").strip()
    if not body or len(body) > 4000:
        flash("Enter a reply between 1 and 4,000 characters.", "error")
        return redirect(url_for("communication_inbox", student_id=student_id))

    connection = get_db_connection()
    try:
        message = connection.execute(
            f"""
            SELECT communications.id
            FROM communications
            JOIN students ON students.id = ?
            WHERE communications.id = ?
              AND ({communication_audience_filter()})
            """,
            (student_id, communication_id),
        ).fetchone()
        if message is None:
            abort(404)
        connection.execute(
            """
            INSERT INTO communication_replies
                (communication_id, student_id, sender_type, body)
            VALUES (?, ?, 'student', ?)
            """,
            (communication_id, student_id, body),
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO communication_reads
                (communication_id, student_id)
            VALUES (?, ?)
            """,
            (communication_id, student_id),
        )
        connection.commit()
        flash("Your question was sent to the placement officer.", "success")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception(
            "Could not save student reply for communication %s",
            communication_id,
        )
        flash("Unable to send your reply. Please try again.", "error")
    finally:
        connection.close()
    return redirect(url_for("communication_inbox", student_id=student_id))


@app.route(
    "/communications/<int:communication_id>/reply/officer/<int:student_id>",
    methods=["POST"],
)
def reply_to_student(communication_id, student_id):
    body = request.form.get("body", "").strip()
    if not body or len(body) > 4000:
        flash("Enter a reply between 1 and 4,000 characters.", "error")
        return redirect(url_for("communications"))

    connection = get_db_connection()
    try:
        message = connection.execute(
            f"""
            SELECT communications.id
            FROM communications
            JOIN students ON students.id = ?
            WHERE communications.id = ?
              AND ({communication_audience_filter()})
            """,
            (student_id, communication_id),
        ).fetchone()
        if message is None:
            abort(404)
        connection.execute(
            """
            INSERT INTO communication_replies
                (communication_id, student_id, sender_type, body)
            VALUES (?, ?, 'officer', ?)
            """,
            (communication_id, student_id, body),
        )
        connection.execute(
            """
            DELETE FROM communication_reads
            WHERE communication_id = ? AND student_id = ?
            """,
            (communication_id, student_id),
        )
        connection.commit()
        flash("Your response was added to the student conversation.", "success")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception(
            "Could not save officer reply for communication %s",
            communication_id,
        )
        flash("Unable to send your response. Please try again.", "error")
    finally:
        connection.close()
    return redirect(url_for("communications"))


@app.route(
    "/communications/<int:communication_id>/read/<int:student_id>",
    methods=["POST"],
)
def mark_communication_read(communication_id, student_id):
    connection = get_db_connection()
    try:
        message = connection.execute(
            f"""
            SELECT communications.id
            FROM communications
            JOIN students ON students.id = ?
            WHERE communications.id = ?
              AND ({communication_audience_filter()})
            """,
            (student_id, communication_id),
        ).fetchone()
        if message is None:
            abort(404)
        connection.execute(
            """
            INSERT OR IGNORE INTO communication_reads (communication_id, student_id)
            VALUES (?, ?)
            """,
            (communication_id, student_id),
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception(
            "Could not mark communication %s read for student %s",
            communication_id,
            student_id,
        )
        flash("Unable to update message read status.", "error")
    finally:
        connection.close()
    return redirect(url_for("communication_inbox", student_id=student_id))


@app.route("/communications/inbox/<int:student_id>/read-all", methods=["POST"])
def mark_all_communications_read(student_id):
    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        if student is None:
            abort(404)
        messages = connection.execute(
            f"""
            SELECT communications.id
            FROM communications
            JOIN students ON students.id = ?
            WHERE ({communication_audience_filter()})
            """,
            (student_id,),
        ).fetchall()
        connection.executemany(
            """
            INSERT OR IGNORE INTO communication_reads (communication_id, student_id)
            VALUES (?, ?)
            """,
            [(message["id"], student_id) for message in messages],
        )
        connection.commit()
        flash("All messages marked as read.", "success")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not mark all messages read for student %s", student_id)
        flash("Unable to update message read status.", "error")
    finally:
        connection.close()
    return redirect(url_for("communication_inbox", student_id=student_id))



@app.route("/", methods=["GET", "POST"])
def login():
    connection = get_db_connection()
    try:
        accounts_exist = connection.execute(
            "SELECT 1 FROM users LIMIT 1"
        ).fetchone() is not None
        if request.method == "POST":
            if not accounts_exist:
                flash(
                    "No accounts are set up yet. Use the one-time setup page at /setup.",
                    "error",
                )
                return render_template("login.html")

            identity = request.form.get("identity", "").strip()
            password = request.form.get("password", "")
            user = connection.execute(
                """
                SELECT id, username, name, email, password, role, student_id, is_active
                FROM users
                WHERE username = ? COLLATE NOCASE
                   OR email = ? COLLATE NOCASE
                   OR name = ? COLLATE NOCASE
                """,
                (identity, identity, identity),
            ).fetchone()
            if (
                user is None
                or not user["is_active"]
                or not check_password_hash(user["password"], password)
            ):
                flash("The email or password is incorrect.", "error")
                return render_template("login.html")
            if user["role"] not in ROLE_LABELS:
                flash("This account has an invalid role. Contact an administrator.", "error")
                return render_template("login.html")
            if user["role"] == "student" and user["student_id"] is None:
                flash("This student account is not linked to a student profile.", "error")
                return render_template("login.html")
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}.", "success")
            return redirect(
                url_for("student_home")
                if user["role"] == "student"
                else url_for("dashboard")
            )
    finally:
        connection.close()

    return render_template("login.html")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    connection = get_db_connection()
    try:
        account_exists = connection.execute(
            "SELECT 1 FROM users LIMIT 1"
        ).fetchone() is not None
        if account_exists:
            flash("Administrator setup has already been completed.", "info")
            return redirect(url_for("login"))

        if request.method == "POST":
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                flash("Administrator setup has already been completed.", "info")
                return redirect(url_for("login"))

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
                flash(
                    "Choose a username with 3–32 letters, numbers, dots, dashes, or underscores.",
                    "error",
                )
            elif len(password) < 12:
                flash("Use a password with at least 12 characters.", "error")
            else:
                connection.execute(
                    """
                    INSERT INTO users (username, name, email, password, role)
                    VALUES (?, ?, NULL, ?, 'admin')
                    """,
                    (username, username, generate_password_hash(password)),
                )
                connection.commit()
                user = connection.execute(
                    """
                    SELECT id FROM users WHERE username = ?
                    """,
                    (username,),
                ).fetchone()
                session.clear()
                session["user_id"] = user["id"]
                flash("Administrator account created. Welcome to CAMPUSLINK.", "success")
                return redirect(url_for("dashboard"))
    except sqlite3.IntegrityError:
        connection.rollback()
        app.logger.exception("Could not create the initial administrator account")
        flash("That username is already in use. Choose a different one.", "error")
    finally:
        connection.close()
    return render_template("setup.html")


@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    connection = get_db_connection()
    try:
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().casefold()
            password = request.form.get("password", "")
            role = request.form.get("role", "").strip()
            student_id = request.form.get("student_id", type=int)
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
                flash("Choose a valid username using 3–32 letters, numbers, dots, dashes, or underscores.", "error")
            elif not name or len(name) > 100:
                flash("Enter a name between 1 and 100 characters.", "error")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid email address.", "error")
            elif len(password) < 12:
                flash("Use a temporary password with at least 12 characters.", "error")
            elif role not in {"admin", "placement_officer", "student"}:
                flash("Choose a valid account role.", "error")
            elif role == "student" and student_id is None:
                flash("Select the student profile for this account.", "error")
            elif role != "student" and student_id is not None:
                flash("Only student accounts can be linked to a student profile.", "error")
            else:
                if student_id is not None and connection.execute(
                    "SELECT 1 FROM students WHERE id = ?", (student_id,)
                ).fetchone() is None:
                    flash("The selected student profile was not found.", "error")
                else:
                    connection.execute(
                        """
                        INSERT INTO users
                            (username, name, email, password, role, student_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            name,
                            email,
                            generate_password_hash(password),
                            role,
                            student_id,
                        ),
                    )
                    connection.commit()
                    flash(f"{ROLE_LABELS[role]} account created successfully.", "success")
                    return redirect(url_for("admin_users"))

        users = connection.execute(
            """
            SELECT users.id, users.username, users.name, users.email,
                   users.role, users.is_active,
                   students.name AS student_name, students.registration_no
            FROM users
            LEFT JOIN students ON students.id = users.student_id
            ORDER BY users.created_at DESC, users.id DESC
            """
        ).fetchall()
        students = connection.execute(
            """
            SELECT students.id, students.name, students.registration_no, students.branch
            FROM students
            LEFT JOIN users ON users.student_id = students.id
            WHERE users.id IS NULL
            ORDER BY students.name COLLATE NOCASE
            """
        ).fetchall()
    except sqlite3.IntegrityError:
        connection.rollback()
        app.logger.exception("Could not create a user account")
        flash("That username, email, or student profile is already assigned to an account.", "error")
        users = connection.execute(
            """
            SELECT users.id, users.username, users.name, users.email, users.role, users.is_active,
                   students.name AS student_name, students.registration_no
            FROM users LEFT JOIN students ON students.id = users.student_id
            ORDER BY users.created_at DESC, users.id DESC
            """
        ).fetchall()
        students = connection.execute(
            """
            SELECT students.id, students.name, students.registration_no, students.branch
            FROM students LEFT JOIN users ON users.student_id = students.id
            WHERE users.id IS NULL ORDER BY students.name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()
    return render_template("admin/users.html", users=users, students=students)


@app.route("/student")
def student_home():
    student_id = g.current_user["student_id"]
    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()
        if student is None:
            abort(403)
        summary = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM applications WHERE student_id = ?) AS applications,
                (SELECT COUNT(*) FROM mock_test_attempts WHERE student_id = ?) AS tests,
                (SELECT COUNT(*) FROM mock_test_attempts
                 WHERE student_id = ? AND status = 'Completed') AS completed_tests,
                (SELECT CASE
                    WHEN student_resumes.status = 'Ready' THEN 'Ready'
                    WHEN student_resume_files.student_id IS NOT NULL THEN 'Uploaded'
                    ELSE COALESCE(student_resumes.status, 'Needs generation')
                 END
                 FROM students
                 LEFT JOIN student_resumes
                   ON student_resumes.student_id = students.id
                 LEFT JOIN student_resume_files
                   ON student_resume_files.student_id = students.id
                 WHERE students.id = ?) AS resume_status
            """,
            (student_id, student_id, student_id, student_id),
        ).fetchone()
        unread_count = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM communications
            JOIN students ON students.id = ?
            LEFT JOIN communication_reads
              ON communication_reads.communication_id = communications.id
             AND communication_reads.student_id = students.id
            WHERE ({communication_audience_filter()})
              AND communication_reads.read_at IS NULL
            """,
            (student_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    return render_template(
        "student/dashboard.html",
        student=student,
        summary=summary,
        unread_count=unread_count,
    )



@app.route("/dashboard")
def dashboard():

    connection = get_db_connection()

    total_students = connection.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_companies = connection.execute(
        "SELECT COUNT(*) FROM companies"
    ).fetchone()[0]

    total_jobs = connection.execute(
        "SELECT COUNT(*) FROM jobs"
    ).fetchone()[0]

    open_jobs = [
        job
        for job in connection.execute(
            """
            SELECT id, status, drive_date, application_deadline,
                   min_cgpa, max_backlogs, min_attendance, eligible_branches
            FROM jobs
            """
        ).fetchall()
        if is_job_open_for_applications(job)
    ]
    active_job_ids = {job["id"] for job in open_jobs}

    eligible_students = 0
    if active_job_ids:
        students = connection.execute(
            """
            SELECT branch, cgpa, backlogs, attendance, placement_status
            FROM students
            WHERE lower(trim(COALESCE(placement_status, ''))) != 'placed'
            """
        ).fetchall()

        for student in students:
            for job in open_jobs:
                branches = {
                    branch.strip().casefold()
                    for branch in (job["eligible_branches"] or "").split(",")
                    if branch.strip()
                }
                if (
                    student["cgpa"] >= (job["min_cgpa"] or 0)
                    and student["backlogs"] <= (job["max_backlogs"] or 0)
                    and student["attendance"] >= (job["min_attendance"] or 0)
                    and (
                        not branches
                        or (student["branch"] or "").strip().casefold() in branches
                    )
                ):
                    eligible_students += 1
                    break

    total_applications = connection.execute(
        "SELECT COUNT(*) FROM applications"
    ).fetchone()[0]

    total_offers = connection.execute(
        "SELECT COUNT(*) FROM offers"
    ).fetchone()[0]

    total_interviews = connection.execute(
        "SELECT COUNT(*) FROM interviews"
    ).fetchone()[0]

    placed_students = connection.execute(
        """
        SELECT COUNT(*)
        FROM students
        WHERE placement_status = 'Placed'
        """
    ).fetchone()[0]

    upcoming_interviews = connection.execute(
        """
        SELECT interviews.interview_date, interviews.interview_time,
               interviews.round, interviews.venue,
               students.name AS student_name, companies.name AS company_name,
               jobs.role
        FROM interviews
        JOIN applications ON interviews.application_id = applications.id
        JOIN students ON applications.student_id = students.id
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE interviews.interview_date >= ?
          AND interviews.status IN ('Scheduled', 'Pending')
        ORDER BY interviews.interview_date, interviews.interview_time
        LIMIT 5
        """,
        (date.today().isoformat(),)
    ).fetchall()

    connection.close()

    return render_template(
        "dashboard/index.html",
        total_students=total_students,
        eligible_students=eligible_students,
        total_companies=total_companies,
        total_jobs=total_jobs,
        active_jobs=len(open_jobs),
        total_applications=total_applications,
        total_offers=total_offers,
        total_interviews=total_interviews,
        placed_students=placed_students,
        placement_activity=total_applications + total_interviews + total_offers,
        upcoming_interviews=upcoming_interviews
    )



@app.route("/students")
def students():

    connection = get_db_connection()

    students = connection.execute(
        """
        SELECT *
        FROM students
        ORDER BY id DESC
        """
    ).fetchall()

    connection.close()

    branch_options = sorted(
        {student["branch"].strip() for student in students if student["branch"]},
        key=str.casefold
    )
    status_options = sorted(
        {
            student["placement_status"].strip()
            for student in students
            if student["placement_status"]
        },
        key=str.casefold
    )
    skill_options_by_key = {}
    for student in students:
        for skill in (
            (student["skills"] or "")
            .replace("\r", "")
            .replace("\n", ",")
            .replace(";", ",")
            .split(",")
        ):
            skill = skill.strip()
            if not skill:
                continue
            key = skill.casefold()
            current = skill_options_by_key.get(key)
            if current is None or (current == current.lower() and skill != skill.lower()):
                skill_options_by_key[key] = skill
    skill_options = sorted(skill_options_by_key.values(), key=str.casefold)

    return render_template(
        "students/index.html",
        students=students,
        branch_options=branch_options,
        status_options=status_options,
        skill_options=skill_options
    )



@app.route("/students/add", methods=["GET", "POST"])
def add_student():

    if request.method == "GET":
        return render_template("students/add.html")

    name = request.form.get("name", "").strip()

    registration_no = request.form.get(
        "registration_no",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    branch = request.form.get(
        "branch",
        ""
    ).strip()

    cgpa = request.form.get(
        "cgpa",
        "0"
    )

    backlogs = request.form.get(
        "backlogs",
        "0"
    )

    attendance = request.form.get(
        "attendance",
        "0"
    )

    skills = request.form.get(
        "skills",
        ""
    ).strip()

    placement_status = request.form.get(
        "placement_status",
        "Unplaced"
    )



    if not name or not registration_no or not branch:

        flash(
            "Please fill all required fields.",
            "error"
        )

        return redirect(
            url_for("add_student")
        )



    try:

        cgpa = float(cgpa)
        backlogs = int(backlogs)
        attendance = float(attendance)

    except ValueError:

        flash(
            "Please enter valid academic values.",
            "error"
        )

        return redirect(
            url_for("add_student")
        )



    if cgpa < 0 or cgpa > 10:

        flash(
            "CGPA must be between 0 and 10.",
            "error"
        )

        return redirect(
            url_for("add_student")
        )



    if attendance < 0 or attendance > 100:

        flash(
            "Attendance must be between 0 and 100.",
            "error"
        )

        return redirect(
            url_for("add_student")
        )



    if backlogs < 0:

        flash(
            "Backlogs cannot be negative.",
            "error"
        )

        return redirect(
            url_for("add_student")
        )



    connection = get_db_connection()

    try:

        connection.execute(
            """
            INSERT INTO students (
                name,
                registration_no,
                email,
                phone,
                branch,
                cgpa,
                backlogs,
                attendance,
                skills,
                placement_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                registration_no,
                email,
                phone,
                branch,
                cgpa,
                backlogs,
                attendance,
                skills,
                placement_status
            )
        )

        connection.commit()

        flash(
            "Student added successfully.",
            "success"
        )

    except Exception as error:

        connection.rollback()

        if "UNIQUE constraint failed" in str(error):

            flash(
                "Registration number already exists.",
                "error"
            )

        else:

            flash(
                "Unable to add student.",
                "error"
            )

    finally:

        connection.close()


    return redirect(
        url_for("students")
    )



@app.route(
    "/students/edit/<int:student_id>",
    methods=["GET", "POST"]
)
def edit_student(student_id):

    connection = get_db_connection()



    student = connection.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()



    if student is None:

        connection.close()

        flash(
            "Student not found.",
            "error"
        )

        return redirect(
            url_for("students")
        )



    if request.method == "GET":

        connection.close()

        return render_template(
            "students/edit.html",
            student=student,
            return_to_profile=request.args.get("return_to_profile") == "1"
        )



    name = request.form.get(
        "name",
        ""
    ).strip()

    registration_no = request.form.get(
        "registration_no",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    branch = request.form.get(
        "branch",
        ""
    ).strip()

    cgpa = request.form.get(
        "cgpa",
        "0"
    )

    backlogs = request.form.get(
        "backlogs",
        "0"
    )

    attendance = request.form.get(
        "attendance",
        "0"
    )

    skills = request.form.get(
        "skills",
        ""
    ).strip()

    placement_status = request.form.get(
        "placement_status",
        "Unplaced"
    )
    return_to_profile = request.form.get("return_to_profile") == "1"



    if not name or not registration_no or not branch:

        connection.close()

        flash(
            "Please fill all required fields.",
            "error"
        )

        return redirect(
            url_for(
                "edit_student",
                student_id=student_id
            )
        )



    try:

        cgpa = float(cgpa)
        backlogs = int(backlogs)
        attendance = float(attendance)

    except ValueError:

        connection.close()

        flash(
            "Please enter valid academic values.",
            "error"
        )

        return redirect(
            url_for(
                "edit_student",
                student_id=student_id
            )
        )



    if cgpa < 0 or cgpa > 10:

        connection.close()

        flash(
            "CGPA must be between 0 and 10.",
            "error"
        )

        return redirect(
            url_for(
                "edit_student",
                student_id=student_id
            )
        )



    if attendance < 0 or attendance > 100:

        connection.close()

        flash(
            "Attendance must be between 0 and 100.",
            "error"
        )

        return redirect(
            url_for(
                "edit_student",
                student_id=student_id
            )
        )



    if backlogs < 0:

        connection.close()

        flash(
            "Backlogs cannot be negative.",
            "error"
        )

        return redirect(
            url_for(
                "edit_student",
                student_id=student_id
            )
        )



    try:

        connection.execute(
            """
            UPDATE students
            SET
                name = ?,
                registration_no = ?,
                email = ?,
                phone = ?,
                branch = ?,
                cgpa = ?,
                backlogs = ?,
                attendance = ?,
                skills = ?,
                placement_status = ?
            WHERE id = ?
            """,
            (
                name,
                registration_no,
                email,
                phone,
                branch,
                cgpa,
                backlogs,
                attendance,
                skills,
                placement_status,
                student_id
            )
        )

        connection.commit()

        flash(
            "Student updated successfully.",
            "success"
        )

    except Exception as error:

        connection.rollback()

        if "UNIQUE constraint failed" in str(error):

            flash(
                "Registration number already exists.",
                "error"
            )

        else:

            flash(
                "Unable to update student.",
                "error"
            )

    finally:

        connection.close()


    if return_to_profile:
        return redirect(url_for("view_student", student_id=student_id))
    return redirect(url_for("students"))



@app.route(
    "/students/delete/<int:student_id>",
    methods=["POST"]
)
def delete_student(student_id):

    connection = get_db_connection()



    student = connection.execute(
        """
        SELECT id, name
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()



    if student is None:

        connection.close()

        flash(
            "Student not found.",
            "error"
        )

        return redirect(
            url_for("students")
        )



    try:

        connection.execute(
            """
            DELETE FROM students
            WHERE id = ?
            """,
            (student_id,)
        )

        connection.commit()

        flash(
            f"Student '{student['name']}' deleted successfully.",
            "success"
        )

    except Exception:

        connection.rollback()

        flash(
            "Unable to delete student.",
            "error"
        )

    finally:

        connection.close()


    return redirect(
        url_for("students")
    )



@app.route("/students/view/<int:student_id>")
def view_student(student_id):

    connection = get_db_connection()

    student = connection.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    applications = connection.execute(
        """
        SELECT applications.*, companies.name AS company_name, jobs.role
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE applications.student_id = ?
        ORDER BY applications.id DESC
        """,
        (student_id,)
    ).fetchall()

    offers = connection.execute(
        """
        SELECT offers.*, companies.name AS company_name, jobs.role
        FROM offers
        JOIN companies ON offers.company_id = companies.id
        JOIN jobs ON offers.job_id = jobs.id
        WHERE offers.student_id = ?
        ORDER BY offers.id DESC
        """,
        (student_id,)
    ).fetchall()

    interviews = connection.execute(
        """
        SELECT interviews.*, companies.name AS company_name, jobs.role
        FROM interviews
        JOIN applications ON interviews.application_id = applications.id
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE applications.student_id = ?
        ORDER BY interviews.interview_date DESC, interviews.interview_time DESC
        """,
        (student_id,)
    ).fetchall()

    selected_offer_applications = connection.execute(
        """
        SELECT applications.id, jobs.id AS job_id,
               companies.name AS company_name, jobs.role, jobs.package
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE applications.student_id = ?
          AND applications.status = 'Selected'
          AND NOT EXISTS (
              SELECT 1 FROM offers
              WHERE offers.student_id = applications.student_id
                AND offers.job_id = applications.job_id
          )
        ORDER BY applications.id DESC
        """,
        (student_id,)
    ).fetchall()

    certificates = connection.execute(
        """
        SELECT id, certificate_name, original_filename, mime_type,
               file_size, uploaded_at
        FROM student_certificates
        WHERE student_id = ?
        ORDER BY uploaded_at DESC, id DESC
        """,
        (student_id,)
    ).fetchall()

    resume = connection.execute(
        """
        SELECT CASE
                   WHEN student_resumes.status = 'Ready' THEN 'Ready'
                   WHEN student_resume_files.student_id IS NOT NULL THEN 'Uploaded'
                   ELSE COALESCE(student_resumes.status, 'Needs generation')
               END AS status
        FROM students
        LEFT JOIN student_resumes ON student_resumes.student_id = students.id
        LEFT JOIN student_resume_files ON student_resume_files.student_id = students.id
        WHERE students.id = ?
        """,
        (student_id,)
    ).fetchone()

    unread_communications = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM communications
        JOIN students ON students.id = ?
        LEFT JOIN communication_reads
            ON communication_reads.communication_id = communications.id
           AND communication_reads.student_id = students.id
        WHERE ({communication_audience_filter()})
          AND communication_reads.read_at IS NULL
        """,
        (student_id,),
    ).fetchone()[0]

    connection.close()


    if student is None:

        flash(
            "Student not found.",
            "error"
        )

        return redirect(
            url_for("students")
        )


    return render_template(
        "students/view.html",
        student=student,
        student_skills=parse_student_skills(student["skills"]),
        applications=applications,
        offers=offers,
        interviews=interviews,
        selected_offer_applications=selected_offer_applications,
        certificates=certificates,
        resume_status=resume["status"] if resume else "Needs generation",
        has_uploaded_resume=bool(resume and resume["status"] == "Uploaded"),
        max_certificate_size=MAX_CERTIFICATE_SIZE,
        unread_communications=unread_communications,
    )


@app.route("/students/view/<int:student_id>/certificates", methods=["POST"])
def upload_student_certificate(student_id):
    certificate_name = request.form.get("certificate_name", "").strip()
    upload = request.files.get("certificate_file")

    if not certificate_name:
        flash("Enter a name for this certificate.", "error")
        return redirect(url_for("view_student", student_id=student_id))
    if upload is None or not upload.filename:
        flash("Choose the original certificate file to upload.", "error")
        return redirect(url_for("view_student", student_id=student_id))

    safe_filename = secure_filename(upload.filename.replace("\\", "/").split("/")[-1])
    extension = "." + safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    file_type = CERTIFICATE_TYPES.get(extension)
    if file_type is None:
        flash("Use an original PDF, PNG, or JPEG certificate file.", "error")
        return redirect(url_for("view_student", student_id=student_id))

    file_data = upload.stream.read(MAX_CERTIFICATE_SIZE + 1)
    if not file_data:
        flash("The selected certificate file is empty.", "error")
        return redirect(url_for("view_student", student_id=student_id))
    if len(file_data) > MAX_CERTIFICATE_SIZE:
        flash("Certificate files must be 10 MB or smaller.", "error")
        return redirect(url_for("view_student", student_id=student_id))
    mime_type, signature_check = file_type
    if not signature_check(file_data):
        flash("The file contents do not match its PDF, PNG, or JPEG extension.", "error")
        return redirect(url_for("view_student", student_id=student_id))

    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()
        if student is None:
            flash("Student not found.", "error")
            return redirect(url_for("students"))

        connection.execute(
            """
            INSERT INTO student_certificates
                (student_id, certificate_name, original_filename,
                 mime_type, file_data, file_size)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                student_id,
                certificate_name,
                safe_filename,
                mime_type,
                sqlite3.Binary(file_data),
                len(file_data),
            )
        )
        connection.commit()
        flash("Original certificate uploaded successfully.", "success")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not save certificate for student %s", student_id)
        flash("Unable to save this certificate. Please try again.", "error")
    finally:
        connection.close()

    return redirect(url_for("view_student", student_id=student_id))


@app.route("/students/view/<int:student_id>/certificates/<int:certificate_id>/file")
def open_student_certificate(student_id, certificate_id):
    connection = get_db_connection()
    try:
        certificate = connection.execute(
            """
            SELECT original_filename, mime_type, file_data
            FROM student_certificates
            WHERE id = ? AND student_id = ?
            """,
            (certificate_id, student_id)
        ).fetchone()
    finally:
        connection.close()

    if certificate is None:
        abort(404)

    response = send_file(
        io.BytesIO(certificate["file_data"]),
        mimetype=certificate["mime_type"],
        as_attachment=request.args.get("download") == "1",
        download_name=certificate["original_filename"],
        max_age=0
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response



MOCK_TEST_QUESTION_COUNT = 10


@app.route("/mock-tests", methods=["GET"])
def mock_tests():
    connection = get_db_connection()
    is_student = g.current_user["role"] == "student"
    student_id = g.current_user["student_id"] if is_student else None
    students = connection.execute(
        """
        SELECT id, name, registration_no, branch FROM students
        WHERE (? IS NULL OR id = ?)
        ORDER BY name COLLATE NOCASE
        """,
        (student_id, student_id),
    ).fetchall()
    categories = connection.execute(
        "SELECT category, COUNT(*) AS question_count FROM mock_test_questions GROUP BY category ORDER BY category"
    ).fetchall()
    attempts = connection.execute(
        """
        SELECT mock_test_attempts.id, mock_test_attempts.category,
               mock_test_attempts.score, mock_test_attempts.total_questions,
               mock_test_attempts.status, mock_test_attempts.started_at,
               mock_test_attempts.completed_at,
               students.id AS student_id, students.name AS student_name,
               students.registration_no, students.branch
        FROM mock_test_attempts
        JOIN students ON mock_test_attempts.student_id = students.id
        WHERE (? IS NULL OR mock_test_attempts.student_id = ?)
        ORDER BY mock_test_attempts.id DESC
        LIMIT 50
        """,
        (student_id, student_id),
    ).fetchall()
    summary = connection.execute(
        """
        SELECT COUNT(*) AS total_attempts,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed_attempts,
               AVG(CASE WHEN status = 'Completed' AND total_questions > 0
                        THEN (score * 100.0 / total_questions) END) AS average_score
        FROM mock_test_attempts
        WHERE (? IS NULL OR student_id = ?)
        """,
        (student_id, student_id),
    ).fetchone()
    connection.close()
    return render_template(
        "mock_tests/index.html",
        students=students,
        categories=categories,
        attempts=attempts,
        summary=summary,
        selected_student_id=request.args.get("student_id", type=int),
        selected_category=request.args.get("category", ""),
    )


@app.route("/mock-tests/start", methods=["POST"])
def start_mock_test():
    student_id = (
        g.current_user["student_id"]
        if g.current_user["role"] == "student"
        else request.form.get("student_id", type=int)
    )
    category = request.form.get("category", "").strip()
    connection = get_db_connection()
    try:
        student = connection.execute(
            "SELECT id FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        question_rows = connection.execute(
            """
            SELECT id FROM mock_test_questions
            WHERE category = ?
            ORDER BY id
            """,
            (category,),
        ).fetchall()
        valid_category = connection.execute(
            "SELECT 1 FROM mock_test_questions WHERE category = ? LIMIT 1",
            (category,),
        ).fetchone()
        if student is None or valid_category is None:
            flash("Choose a valid student and mock test category.", "error")
            return redirect(url_for("mock_tests"))
        if len(question_rows) < MOCK_TEST_QUESTION_COUNT:
            app.logger.error(
                "Mock test category %s has only %s questions",
                category,
                len(question_rows),
            )
            flash("This test does not have enough questions yet.", "error")
            return redirect(url_for("mock_tests"))

        all_question_ids = [row["id"] for row in question_rows]
        rng = random.SystemRandom()
        selected_ids = rng.sample(all_question_ids, MOCK_TEST_QUESTION_COUNT)
        previous_attempt = connection.execute(
            """
            SELECT question_ids FROM mock_test_attempts
            WHERE student_id = ? AND category = ?
            ORDER BY id DESC LIMIT 1
            """,
            (student_id, category),
        ).fetchone()
        if previous_attempt:
            previous_ids = set(json.loads(previous_attempt["question_ids"]))
            if set(selected_ids) == previous_ids:
                replacements = [qid for qid in all_question_ids if qid not in selected_ids]
                selected_ids[-1] = rng.choice(replacements)
                rng.shuffle(selected_ids)

        cursor = connection.execute(
            """
            INSERT INTO mock_test_attempts
                (student_id, category, question_ids, total_questions)
            VALUES (?, ?, ?, ?)
            """,
            (
                student_id,
                category,
                json.dumps(selected_ids),
                len(selected_ids),
            ),
        )
        attempt_id = cursor.lastrowid
        connection.commit()
    except (sqlite3.Error, ValueError):
        connection.rollback()
        app.logger.exception("Could not start mock test for student %s", student_id)
        flash("Unable to start this mock test. Please try again.", "error")
        return redirect(url_for("mock_tests"))
    finally:
        connection.close()
    return redirect(url_for("view_mock_test", attempt_id=attempt_id))


@app.route("/mock-tests/<int:attempt_id>", methods=["GET", "POST"])
def view_mock_test(attempt_id):
    connection = get_db_connection()
    attempt = connection.execute(
        """
        SELECT mock_test_attempts.*, students.name AS student_name,
               students.registration_no, students.branch
        FROM mock_test_attempts
        JOIN students ON mock_test_attempts.student_id = students.id
        WHERE mock_test_attempts.id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if attempt is None:
        connection.close()
        abort(404)

    question_ids = json.loads(attempt["question_ids"])
    if not isinstance(question_ids, list) or not question_ids:
        connection.close()
        app.logger.error("Mock test attempt %s has invalid question data", attempt_id)
        abort(500)
    placeholders = ",".join("?" for _ in question_ids)
    question_rows = connection.execute(
        f"""
        SELECT id, question, options_json, correct_option, explanation
        FROM mock_test_questions
        WHERE id IN ({placeholders})
        """,
        question_ids,
    ).fetchall()
    question_by_id = {row["id"]: row for row in question_rows}
    if len(question_by_id) != len(question_ids):
        connection.close()
        app.logger.error("Mock test attempt %s references missing questions", attempt_id)
        abort(500)
    questions = [
        {
            "options": json.loads(question_by_id[question_id]["options_json"]),
        }
        for question_id in question_ids
    ]

    if request.method == "POST":
        if attempt["status"] != "In Progress":
            connection.close()
            flash("This test has already been submitted.", "info")
            return redirect(url_for("view_mock_test", attempt_id=attempt_id))
        allowed_answers = {"A", "B", "C", "D"}
        answers = {
            str(question["id"]): request.form.get(f"question_{question['id']}", "")
            for question in questions
        }
        if any(answer and answer not in allowed_answers for answer in answers.values()):
            connection.close()
            flash("One or more answers were invalid. Please check and submit again.", "error")
            return redirect(url_for("view_mock_test", attempt_id=attempt_id))

        score = sum(
            answers[str(question["id"])] == question["correct_option"]
            for question in questions
        )
        try:
            cursor = connection.execute(
                """
                UPDATE mock_test_attempts
                SET answers_json = ?, score = ?, status = 'Completed',
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'In Progress'
                """,
                (json.dumps(answers), score, attempt_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                flash("This test has already been submitted.", "info")
            else:
                connection.commit()
                flash("Mock test submitted. Review your results below.", "success")
        except sqlite3.Error:
            connection.rollback()
            app.logger.exception("Could not submit mock test attempt %s", attempt_id)
            flash("Unable to submit this mock test.", "error")
        finally:
            connection.close()
        return redirect(url_for("view_mock_test", attempt_id=attempt_id))

    answers = json.loads(attempt["answers_json"] or "{}")
    results = []
    if attempt["status"] == "Completed":
        for question in questions:
            selected = answers.get(str(question["id"]), "")
            question["selected_option"] = selected
            question["is_correct"] = selected == question["correct_option"]
            results.append(question)
    connection.close()
    return render_template(
        "mock_tests/attempt.html",
        attempt=attempt,
        questions=questions if attempt["status"] == "In Progress" else results,
        submitted=attempt["status"] == "Completed",
        percentage=round((attempt["score"] or 0) * 100 / attempt["total_questions"])
        if attempt["total_questions"] else 0,
    )



@app.route("/resumes")
def resumes():
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT students.id AS student_id, students.name,
               students.registration_no, students.branch, students.email,
               CASE
                   WHEN student_resumes.status = 'Ready' THEN 'Ready'
                   WHEN student_resume_files.student_id IS NOT NULL THEN 'Uploaded'
                   ELSE COALESCE(student_resumes.status, 'Needs generation')
               END AS status,
               COALESCE(student_resume_files.uploaded_at, student_resumes.updated_at) AS updated_at,
               student_resume_files.original_filename AS uploaded_filename
        FROM students
        LEFT JOIN student_resumes ON student_resumes.student_id = students.id
        LEFT JOIN student_resume_files ON student_resume_files.student_id = students.id
        ORDER BY students.name COLLATE NOCASE
        """
    ).fetchall()
    branches = connection.execute(
        "SELECT DISTINCT branch FROM students WHERE trim(COALESCE(branch, '')) != '' ORDER BY branch COLLATE NOCASE"
    ).fetchall()
    connection.close()

    resume_rows = [
        {
            **dict(row),
            "status": row["status"] or "Needs generation",
        }
        for row in rows
    ]
    return render_template(
        "resumes/index.html",
        students=resume_rows,
        branches=[row["branch"] for row in branches],
        ready_count=sum(row["status"] == "Ready" for row in resume_rows),
        uploaded_count=sum(bool(row["uploaded_filename"]) for row in resume_rows),
        needs_generation_count=sum(
            row["status"] not in {"Ready", "Uploaded"} for row in resume_rows
        ),
    )


@app.route("/resumes/<int:student_id>", methods=["GET", "POST"])
def edit_resume(student_id):
    connection = get_db_connection()
    student = connection.execute(
        "SELECT * FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()
    if student is None:
        connection.close()
        abort(404)

    stored_resume = connection.execute(
        "SELECT * FROM student_resumes WHERE student_id = ?",
        (student_id,),
    ).fetchone()
    uploaded_resume = connection.execute(
        """
        SELECT original_filename, mime_type, file_size, uploaded_at
        FROM student_resume_files
        WHERE student_id = ?
        """,
        (student_id,),
    ).fetchone()

    if request.method == "POST":
        field_limits = {
            "professional_summary": 2500,
            "education": 4000,
            "skills": 2000,
            "projects": 7000,
            "experience": 7000,
            "certifications": 4000,
            "linkedin_url": 500,
            "portfolio_url": 500,
        }
        resume_data = {
            field: request.form.get(field, "").strip()
            for field in field_limits
        }
        oversized_fields = [
            field.replace("_", " ").title()
            for field, limit in field_limits.items()
            if len(resume_data[field]) > limit
        ]
        if oversized_fields:
            connection.close()
            flash(
                "Please shorten these sections: " + ", ".join(oversized_fields) + ".",
                "error",
            )
            return redirect(url_for("edit_resume", student_id=student_id))

        status = "Ready" if (
            resume_data["professional_summary"]
            and resume_data["education"]
            and resume_data["skills"]
        ) else "Needs generation"

        try:
            connection.execute(
                """
                INSERT INTO student_resumes (
                    student_id, professional_summary, education, skills,
                    projects, experience, certifications, linkedin_url,
                    portfolio_url, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(student_id) DO UPDATE SET
                    professional_summary = excluded.professional_summary,
                    education = excluded.education,
                    skills = excluded.skills,
                    projects = excluded.projects,
                    experience = excluded.experience,
                    certifications = excluded.certifications,
                    linkedin_url = excluded.linkedin_url,
                    portfolio_url = excluded.portfolio_url,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    student_id,
                    resume_data["professional_summary"],
                    resume_data["education"],
                    resume_data["skills"],
                    resume_data["projects"],
                    resume_data["experience"],
                    resume_data["certifications"],
                    resume_data["linkedin_url"],
                    resume_data["portfolio_url"],
                    status,
                ),
            )
            connection.commit()
            flash(
                "Resume saved and ready to download."
                if status == "Ready"
                else "Resume draft saved. Add a summary, education, and skills to generate it.",
                "success" if status == "Ready" else "info",
            )
        except sqlite3.Error:
            connection.rollback()
            app.logger.exception("Could not save resume for student %s", student_id)
            flash("Unable to save this resume. Please try again.", "error")
        finally:
            connection.close()
        return redirect(url_for("edit_resume", student_id=student_id))

    connection.close()
    resume = dict(stored_resume) if stored_resume else {
        "professional_summary": "",
        "education": "",
        "skills": student["skills"] or "",
        "projects": "",
        "experience": "",
        "certifications": "",
        "linkedin_url": "",
        "portfolio_url": "",
        "status": "Needs generation",
        "updated_at": None,
    }
    is_resume_ready = resume_readiness(resume)
    resume["status"] = (
        "Ready" if is_resume_ready
        else "Uploaded" if uploaded_resume
        else "Needs generation"
    )
    return render_template(
        "resumes/builder.html",
        student=student,
        resume=resume,
        resume_ready=is_resume_ready,
        uploaded_resume=uploaded_resume,
        max_resume_size=MAX_RESUME_SIZE,
    )


@app.route("/resumes/<int:student_id>/upload", methods=["POST"])
def upload_resume(student_id):
    upload = request.files.get("resume_file")
    if upload is None or not upload.filename:
        flash("Choose a PDF or DOCX resume file to upload.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    filename = secure_filename(upload.filename.replace("\\", "/").split("/")[-1])
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_type = RESUME_TYPES.get(extension)
    if not filename or file_type is None:
        flash("Upload your resume as a PDF or DOCX file.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    try:
        file_data = upload.stream.read(MAX_RESUME_SIZE + 1)
    except OSError:
        app.logger.exception("Could not read resume upload for student %s", student_id)
        flash("Unable to read the selected resume file. Please try again.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    if not file_data:
        flash("The selected resume file is empty.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))
    if len(file_data) > MAX_RESUME_SIZE:
        flash("Resume files must be 10 MB or smaller.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    mime_type, signature_check = file_type
    if not signature_check(file_data):
        flash("The file contents do not match a valid PDF or DOCX resume.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    connection = get_db_connection()
    try:
        if connection.execute(
            "SELECT 1 FROM students WHERE id = ?", (student_id,)
        ).fetchone() is None:
            abort(404)
        connection.execute(
            """
            INSERT INTO student_resume_files
                (student_id, original_filename, mime_type, file_data, file_size)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(student_id) DO UPDATE SET
                original_filename = excluded.original_filename,
                mime_type = excluded.mime_type,
                file_data = excluded.file_data,
                file_size = excluded.file_size,
                uploaded_at = CURRENT_TIMESTAMP
            """,
            (
                student_id,
                filename,
                mime_type,
                sqlite3.Binary(file_data),
                len(file_data),
            ),
        )
        connection.commit()
        flash("Resume uploaded successfully.", "success")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not save resume upload for student %s", student_id)
        flash("Unable to save this resume. Please try again.", "error")
    finally:
        connection.close()
    return redirect(url_for("edit_resume", student_id=student_id))


@app.route("/resumes/<int:student_id>/original")
def download_original_resume(student_id):
    connection = get_db_connection()
    try:
        uploaded_resume = connection.execute(
            """
            SELECT original_filename, mime_type, file_data
            FROM student_resume_files
            WHERE student_id = ?
            """,
            (student_id,),
        ).fetchone()
    finally:
        connection.close()

    if uploaded_resume is None:
        flash("No uploaded resume is available to download.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    return send_file(
        io.BytesIO(uploaded_resume["file_data"]),
        mimetype=uploaded_resume["mime_type"],
        as_attachment=True,
        download_name=uploaded_resume["original_filename"],
        max_age=0,
    )


@app.route("/resumes/<int:student_id>/download")
def download_resume(student_id):
    connection = get_db_connection()
    student = connection.execute(
        "SELECT * FROM students WHERE id = ?",
        (student_id,),
    ).fetchone()
    resume = connection.execute(
        "SELECT * FROM student_resumes WHERE student_id = ?",
        (student_id,),
    ).fetchone()
    connection.close()

    if student is None:
        abort(404)
    if not resume or not resume_readiness(resume):
        flash("Complete the summary, education, and skills before generating the resume.", "error")
        return redirect(url_for("edit_resume", student_id=student_id))

    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.68 * inch,
        leftMargin=0.68 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        title=f"{student['name']} - Resume",
        author="CAMPUSLINK Resume Builder",
    )
    styles = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "ResumeName",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=27,
        textColor=colors.white,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    header_detail_style = ParagraphStyle(
        "ResumeHeaderDetails",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#e0e7ff"),
    )
    section_style = ParagraphStyle(
        "ResumeSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#243b63"),
        spaceBefore=7,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#293548"),
        spaceAfter=4,
    )
    contact_parts = [
        student["email"],
        student["phone"],
        student["branch"],
        f"CGPA {student['cgpa']:.2f}/10",
    ]
    if resume["linkedin_url"]:
        contact_parts.append(resume["linkedin_url"])
    if resume["portfolio_url"]:
        contact_parts.append(resume["portfolio_url"])
    header = Table(
        [[
            Paragraph(escape(pdf_safe_text(student["name"])), name_style),
            Paragraph("CAREER RESUME", ParagraphStyle(
                "ResumeLabel",
                parent=header_detail_style,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER,
            )),
        ], [
            Paragraph(
                escape(pdf_safe_text("  |  ".join(part for part in contact_parts if part))),
                header_detail_style,
            ),
            "",
        ]],
        colWidths=[5.65 * inch, 1.25 * inch],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#172b4d")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("SPAN", (0, 1), (1, 1)),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, 0), 15),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
    ]))
    story = [header, Spacer(1, 15)]
    add_resume_section(story, "Professional summary", resume["professional_summary"], section_style, body_style)
    add_resume_section(story, "Education", resume["education"], section_style, body_style, bullet=True)
    add_resume_section(story, "Technical skills", resume["skills"], section_style, body_style)
    add_resume_section(story, "Projects", resume["projects"], section_style, body_style, bullet=True)
    add_resume_section(story, "Experience", resume["experience"], section_style, body_style, bullet=True)
    add_resume_section(story, "Certifications", resume["certifications"], section_style, body_style, bullet=True)

    def draw_footer(canvas, _document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbe3f0"))
        canvas.line(0.68 * inch, 0.48 * inch, 7.82 * inch, 0.48 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7b8798"))
        canvas.drawString(0.68 * inch, 0.31 * inch, "CAMPUSLINK  |  Student Resume")
        canvas.drawRightString(7.82 * inch, 0.31 * inch, f"{_document.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    pdf_buffer.seek(0)
    filename = secure_filename(student["name"]) or f"student-{student_id}"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{filename}-resume.pdf",
        max_age=0,
    )



@app.route("/companies/add", methods=["GET", "POST"])
def add_company():

    if request.method == "GET":

        return render_template(
            "companies/add.html"
        )



    name = request.form.get(
        "name",
        ""
    ).strip()

    industry = request.form.get(
        "industry",
        ""
    ).strip()

    location = request.form.get(
        "location",
        ""
    ).strip()

    website = request.form.get(
        "website",
        ""
    ).strip()



    if not name:

        flash(
            "Company name is required.",
            "error"
        )

        return redirect(
            url_for("add_company")
        )



    connection = get_db_connection()

    try:

        connection.execute(
            """
            INSERT INTO companies (
                name,
                industry,
                location,
                website
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                industry,
                location,
                website
            )
        )

        connection.commit()

        flash(
            "Company added successfully.",
            "success"
        )

    except Exception:

        connection.rollback()

        flash(
            "Unable to add company.",
            "error"
        )

    finally:

        connection.close()


    return redirect(
        url_for("companies")
    )


@app.route("/companies/view/<int:company_id>")
def view_company(company_id):

    connection = get_db_connection()
    sync_job_drive_statuses(connection)

    company = connection.execute(
        """
        SELECT *
        FROM companies
        WHERE id = ?
        """,
        (company_id,)
    ).fetchone()

    drives = []
    if company is not None:
        drive_rows = connection.execute(
            """
            SELECT id, role, package, status, required_skills,
                   eligible_branches, drive_date, application_deadline
            FROM jobs
            WHERE company_id = ?
            ORDER BY
                CASE status
                    WHEN 'Active' THEN 0
                    WHEN 'Upcoming' THEN 1
                    ELSE 2
                END,
                role
            """,
            (company_id,)
        ).fetchall()
        drives = [
            {
                **dict(drive),
                "skill_list": parse_student_skills(drive["required_skills"]),
            }
            for drive in drive_rows
        ]

    connection.close()

    if company is None:
        flash("Company not found.", "error")
        return redirect(url_for("companies"))

    return render_template(
        "companies/view.html",
        company=company,
        drives=drives,
        is_recruiting_partner=any(
            drive["status"] in {"Active", "Upcoming"} for drive in drives
        ),
    )

@app.route(
    "/companies/edit/<int:company_id>",
    methods=["GET", "POST"]
)
def edit_company(company_id):

    connection = get_db_connection()

    company = connection.execute(
        """
        SELECT *
        FROM companies
        WHERE id = ?
        """,
        (company_id,)
    ).fetchone()

    if company is None:
        connection.close()
        flash("Company not found.", "error")
        return redirect(url_for("companies"))

    if request.method == "GET":
        connection.close()

        return render_template(
            "companies/edit.html",
            company=company
        )

    name = request.form.get("name", "").strip()
    industry = request.form.get("industry", "").strip()
    location = request.form.get("location", "").strip()
    website = request.form.get("website", "").strip()

    if not name:
        connection.close()
        flash("Company name is required.", "error")
        return redirect(
            url_for(
                "edit_company",
                company_id=company_id
            )
        )

    try:

        connection.execute(
            """
            UPDATE companies
            SET
                name = ?,
                industry = ?,
                location = ?,
                website = ?
            WHERE id = ?
            """,
            (
                name,
                industry,
                location,
                website,
                company_id
            )
        )

        connection.commit()

        flash(
            "Company updated successfully.",
            "success"
        )

    except Exception:

        connection.rollback()

        flash(
            "Unable to update company.",
            "error"
        )

    finally:
        connection.close()

    return redirect(url_for("companies"))



@app.route("/companies/delete/<int:company_id>", methods=["POST"])
def delete_company(company_id):

    connection = get_db_connection()

    company = connection.execute(
        """
        SELECT id, name
        FROM companies
        WHERE id = ?
        """,
        (company_id,)
    ).fetchone()

    if company is None:

        connection.close()

        flash(
            "Company not found.",
            "error"
        )

        return redirect(
            url_for("companies")
        )

    try:

        connection.execute(
            """
            DELETE FROM companies
            WHERE id = ?
            """,
            (company_id,)
        )

        connection.commit()

        flash(
            f"Company '{company['name']}' deleted successfully.",
            "success"
        )

    except Exception:

        connection.rollback()

        flash(
            "Unable to delete company.",
            "error"
        )

    finally:

        connection.close()

    return redirect(
        url_for("companies")
    )


@app.route("/jobs")
def jobs():

    connection = get_db_connection()
    sync_job_drive_statuses(connection)

    jobs = connection.execute(
        """
        SELECT
            jobs.*,
            companies.name AS company_name
        FROM jobs
        JOIN companies
            ON jobs.company_id = companies.id
        ORDER BY jobs.id DESC
        """
    ).fetchall()

    jobs = [
        {
            **dict(job),
            "status": normalize_job_status(
                job["status"],
                job["drive_date"],
                job["application_deadline"]
            ),
        }
        for job in jobs
    ]
    drive_counts = {
        status: sum(1 for job in jobs if job["status"] == status)
        for status in ("Active", "Upcoming", "Closed")
    }
    hiring_company_ids = {
        job["company_id"]
        for job in jobs
        if is_job_open_for_applications(job)
    }

    connection.close()

    return render_template(
        "jobs/index.html",
        jobs=jobs,
        drive_counts=drive_counts,
        hiring_company_count=len(hiring_company_ids),
    )


@app.route("/jobs/add", methods=["GET", "POST"])
def add_job():

    connection = get_db_connection()

    companies = connection.execute(
        """
        SELECT id, name
        FROM companies
        ORDER BY name ASC
        """
    ).fetchall()

    connection.close()

    if request.method == "GET":

        return render_template(
            "jobs/add.html",
            companies=companies
        )

    company_id = request.form.get("company_id")
    role = request.form.get("role", "").strip()
    package = request.form.get("package", "0").strip()
    min_cgpa = request.form.get("min_cgpa", "0").strip()
    max_backlogs = request.form.get("max_backlogs", "0").strip()
    min_attendance = request.form.get("min_attendance", "0").strip()
    eligible_branches = request.form.get(
        "eligible_branches", ""
    ).strip()
    required_skills = request.form.get(
        "required_skills", ""
    ).strip()
    application_deadline = (
        request.form.get("application_deadline")
        or request.form.get("deadline", "")
    ).strip()
    drive_date = (
        request.form.get("drive_date")
        or request.form.get("date", "")
    ).strip()
    status = request.form.get(
        "status",
        "Active"
    )

    status = normalize_job_status(
        status,
        drive_date,
        application_deadline
    )


    if not company_id or not role:

        flash(
            "Company and job role are required.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )


    try:

        package = float(package)
        min_cgpa = float(min_cgpa)
        max_backlogs = int(max_backlogs)
        min_attendance = float(min_attendance)

    except ValueError:

        flash(
            "Please enter valid numeric values.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )

    try:

        if application_deadline:
            application_deadline = date.fromisoformat(
                application_deadline
            ).isoformat()

        if drive_date:
            drive_date = date.fromisoformat(drive_date).isoformat()

    except ValueError:

        flash(
            "Please enter valid date values in YYYY-MM-DD format.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )

    if application_deadline and drive_date and drive_date < application_deadline:

        flash(
            "Drive date must be on or after the application deadline.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )


    if min_cgpa < 0 or min_cgpa > 10:

        flash(
            "Minimum CGPA must be between 0 and 10.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )


    if min_attendance < 0 or min_attendance > 100:

        flash(
            "Minimum attendance must be between 0 and 100.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )


    if max_backlogs < 0:

        flash(
            "Maximum backlogs cannot be negative.",
            "error"
        )

        return redirect(
            url_for("add_job")
        )


    connection = get_db_connection()

    try:

        connection.execute(
            """
            INSERT INTO jobs (
                company_id,
                role,
                package,
                min_cgpa,
                max_backlogs,
                min_attendance,
                eligible_branches,
                required_skills,
                application_deadline,
                drive_date,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                role,
                package,
                min_cgpa,
                max_backlogs,
                min_attendance,
                eligible_branches,
                required_skills,
                application_deadline,
                drive_date,
                status
            )
        )

        connection.commit()

        flash(
            "Job drive added successfully.",
            "success"
        )

    except Exception:

        connection.rollback()

        flash(
            "Unable to add job drive.",
            "error"
        )

    finally:

        connection.close()


    return redirect(
        url_for("jobs")
    )

@app.route("/matching")
def matching():
    connection = get_db_connection()
    sync_job_drive_statuses(connection)

    all_jobs = connection.execute(
        """
        SELECT
            jobs.*,
            companies.name AS company_name
        FROM jobs
        JOIN companies
            ON jobs.company_id = companies.id
        ORDER BY jobs.id DESC
        """
    ).fetchall()
    jobs = [
        dict(job)
        for job in all_jobs
        if is_job_open_for_applications(job)
    ]
    selected_job_id = request.args.get("job_id", type=int)
    if selected_job_id is None and jobs:
        default_job = next(
            (job for job in jobs if job["status"] == "Active"),
            jobs[0],
        )
        selected_job_id = default_job["id"]
    selected_job = next(
        (job for job in jobs if job["id"] == selected_job_id),
        None,
    )
    candidates = []
    if selected_job:
        students = connection.execute(
            """
            SELECT students.id, students.name, students.registration_no,
                   students.branch, students.cgpa, students.backlogs,
                   students.attendance, students.skills,
                   applications.id AS application_id
            FROM students
            LEFT JOIN applications
                ON applications.student_id = students.id
               AND applications.job_id = ?
            ORDER BY students.name COLLATE NOCASE
            """,
            (selected_job["id"],),
        ).fetchall()
        candidates = [
            {
                **dict(student),
                **score_student_for_job(student, selected_job),
            }
            for student in students
        ]
        candidates.sort(
            key=lambda candidate: (
                not candidate["eligible"],
                -candidate["score"],
                -candidate["skills_score"],
                candidate["name"].casefold(),
            )
        )

    eligible_candidates = [
        candidate for candidate in candidates if candidate["eligible"]
    ]
    strong_matches = [
        candidate for candidate in eligible_candidates if candidate["score"] >= 80
    ]
    average_score = round(
        sum(candidate["score"] for candidate in eligible_candidates)
        / len(eligible_candidates)
    ) if eligible_candidates else 0

    connection.close()

    return render_template(
        "matching/index.html",
        jobs=jobs,
        selected_job=selected_job,
        candidates=candidates,
        candidates_analyzed=len(candidates),
        eligible_count=len(eligible_candidates),
        strong_match_count=len(strong_matches),
        average_score=average_score,
    )



@app.route("/profile")
def profile():
    return render_template("profile.html")



@app.route("/settings")
def settings():
    return render_template("settings/index.html")


@app.route("/reports")
def reports():
    connection = get_db_connection()

    report_stats = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM students) AS students,
            (SELECT COUNT(*) FROM companies) AS companies,
            (SELECT COUNT(*) FROM applications) AS applications,
            (SELECT COUNT(*) FROM interviews) AS interviews,
            (SELECT COUNT(*) FROM offers) AS offers,
            (SELECT COUNT(*) FROM students WHERE placement_status = 'Placed') AS placed
        """
    ).fetchone()

    connection.close()

    placement_rate = (
        round((report_stats["placed"] / report_stats["students"]) * 100, 1)
        if report_stats["students"] else 0
    )

    return render_template(
        "reports/index.html",
        report_stats=report_stats,
        placement_rate=placement_rate,
    )


@app.route("/requirements")
def project_requirements():
    return render_template("requirements/index.html")


@app.route("/reports/<report_type>.<file_format>")
def generate_report(report_type, file_format):
    report_queries = {
        "students": (
            "Student Report",
            """
            SELECT name, registration_no, email, phone, branch, cgpa,
                   backlogs, attendance, skills, placement_status
            FROM students ORDER BY name
            """,
        ),
        "companies": (
            "Company Report",
            """
            SELECT companies.name, companies.industry, companies.location,
                   COUNT(DISTINCT jobs.id) AS job_drives,
                   COUNT(DISTINCT offers.id) AS offers
            FROM companies
            LEFT JOIN jobs ON jobs.company_id = companies.id
            LEFT JOIN offers ON offers.company_id = companies.id
            GROUP BY companies.id ORDER BY companies.name
            """,
        ),
        "placement": (
            "Placement Report",
            """
            SELECT branch, placement_status, COUNT(*) AS students
            FROM students GROUP BY branch, placement_status
            ORDER BY branch, placement_status
            """,
        ),
        "offers": (
            "Offer Report",
            """
            SELECT students.name AS student, companies.name AS company,
                   jobs.role, offers.package, offers.offer_date,
                   offers.joining_date, offers.status
            FROM offers
            JOIN students ON offers.student_id = students.id
            JOIN companies ON offers.company_id = companies.id
            JOIN jobs ON offers.job_id = jobs.id
            ORDER BY offers.offer_date DESC
            """,
        ),
        "applications": (
            "Application Report",
            """
            SELECT students.name AS student, companies.name AS company,
                   jobs.role, applications.match_score,
                   applications.status, applications.applied_at
            FROM applications
            JOIN students ON applications.student_id = students.id
            JOIN jobs ON applications.job_id = jobs.id
            JOIN companies ON jobs.company_id = companies.id
            ORDER BY applications.applied_at DESC
            """,
        ),
        "interviews": (
            "Interview Report",
            """
            SELECT students.name AS student, companies.name AS company,
                   jobs.role, interviews.round, interviews.interview_date,
                   interviews.interview_time, interviews.venue, interviews.status
            FROM interviews
            JOIN applications ON interviews.application_id = applications.id
            JOIN students ON applications.student_id = students.id
            JOIN jobs ON applications.job_id = jobs.id
            JOIN companies ON jobs.company_id = companies.id
            ORDER BY interviews.interview_date DESC, interviews.interview_time DESC
            """,
        ),
    }

    if report_type not in report_queries or file_format not in {"csv", "xls", "pdf"}:
        return "Report type not found.", 404

    report_name, query = report_queries[report_type]
    connection = get_db_connection()
    rows = connection.execute(query).fetchall()
    connection.close()

    headers = list(rows[0].keys()) if rows else ["No records found"]
    values = [tuple(row) for row in rows]
    filename = f"campuslink-{report_type}-report"

    if file_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([report_name])
        writer.writerow(headers)
        writer.writerows(values)
        return app.response_class(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )

    if file_format == "xls":
        table_rows = "".join(
            "<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>"
            for row in values
        )
        html = (
            "<html><head><meta charset='utf-8'></head><body>"
            f"<h1>{report_name}</h1><table border='1'><tr>"
            + "".join(f"<th>{header}</th>" for header in headers)
            + f"</tr>{table_rows}</table></body></html>"
        )
        return app.response_class(
            html,
            mimetype="application/vnd.ms-excel",
            headers={"Content-Disposition": f"attachment; filename={filename}.xls"},
        )

    lines = [report_name] + [", ".join(str(value or "") for value in row) for row in values]
    lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:115] for line in lines[:48]]
    stream_lines = ["BT", "/F1 9 Tf", "40 760 Td"]
    for index, line in enumerate(lines):
        if index:
            stream_lines.append("0 -14 Td")
        stream_lines.append(f"({line}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return app.response_class(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"},
    )



@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been securely signed out.", "success")
    return redirect("/")


@app.route("/analytics")
def analytics():

    connection = get_db_connection()
    academic_year = request.args.get("year", "2026-27")
    available_years = {"2026-27", "2025-26", "2024-25"}
    if academic_year not in available_years:
        academic_year = "2026-27"
    start_year = int(academic_year[:4])
    year_start = f"{start_year}-07-01"
    year_end = f"{start_year + 1}-07-01"

    total_students = connection.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    cohort_students = connection.execute(
        """
        SELECT COUNT(*) FROM students
        WHERE created_at >= ? AND created_at < ?
        """,
        (year_start, year_end)
    ).fetchone()[0]

    placed_students = connection.execute(
        """
        SELECT COUNT(*)
        FROM students
        WHERE placement_status = 'Placed'
          AND created_at >= ? AND created_at < ?
        """,
        (year_start, year_end)
    ).fetchone()[0]

    total_companies = connection.execute(
        """
        SELECT COUNT(DISTINCT jobs.company_id)
        FROM jobs
        WHERE jobs.created_at >= ? AND jobs.created_at < ?
        """,
        (year_start, year_end)
    ).fetchone()[0]

    total_offers = connection.execute(
        """
        SELECT COUNT(*) FROM offers
        WHERE offer_date >= ? AND offer_date < ?
        """,
        (year_start, year_end)
    ).fetchone()[0]

    placement_status = connection.execute(
        """
        SELECT placement_status, COUNT(*) AS total
        FROM students
        WHERE created_at >= ? AND created_at < ?
        GROUP BY placement_status
        """,
        (year_start, year_end)
    ).fetchall()

    branch_placement = connection.execute(
        """
        SELECT branch,
               COUNT(*) AS total,
               SUM(CASE WHEN placement_status = 'Placed' THEN 1 ELSE 0 END) AS placed
        FROM students
        WHERE created_at >= ? AND created_at < ?
        GROUP BY branch
        ORDER BY placed DESC, branch ASC
        """,
        (year_start, year_end)
    ).fetchall()

    package_ranges = connection.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN package < 5 THEN 1 ELSE 0 END), 0) AS below_five,
            COALESCE(SUM(CASE WHEN package >= 5 AND package < 8 THEN 1 ELSE 0 END), 0) AS five_eight,
            COALESCE(SUM(CASE WHEN package >= 8 AND package < 12 THEN 1 ELSE 0 END), 0) AS eight_twelve,
            COALESCE(SUM(CASE WHEN package >= 12 THEN 1 ELSE 0 END), 0) AS above_twelve
        FROM offers
        WHERE package IS NOT NULL AND offer_date >= ? AND offer_date < ?
        """,
        (year_start, year_end)
    ).fetchone()

    recruitment_overview = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM applications
             WHERE applied_at >= ? AND applied_at < ?) AS applications,
            (SELECT COUNT(*) FROM interviews
             WHERE interview_date >= ? AND interview_date < ?) AS interviews,
            (SELECT COUNT(*) FROM offers
             WHERE offer_date >= ? AND offer_date < ?) AS offers,
            (SELECT COUNT(*) FROM companies
             WHERE id IN (SELECT DISTINCT company_id FROM jobs
                          WHERE created_at >= ? AND created_at < ?)) AS recruiting_companies
        """,
        (year_start, year_end, year_start, year_end, year_start, year_end,
         year_start, year_end)
    ).fetchone()

    top_companies = connection.execute(
        """
        SELECT companies.name AS company_name,
               COUNT(offers.id) AS offer_count,
               COALESCE(MAX(offers.package), 0) AS highest_package
        FROM offers
        JOIN companies ON offers.company_id = companies.id
        WHERE offers.offer_date >= ? AND offers.offer_date < ?
        GROUP BY companies.id, companies.name
        ORDER BY offer_count DESC, highest_package DESC, company_name ASC
        LIMIT 5
        """,
        (year_start, year_end)
    ).fetchall()

    connection.close()

    placement_rate = (
        round((placed_students / cohort_students) * 100, 1)
        if cohort_students > 0 else 0
    )

    return render_template(
        "analytics/index.html",
        total_students=total_students,
        placed_students=placed_students,
        total_companies=total_companies,
        total_offers=total_offers,
        placement_rate=placement_rate,
        academic_year=academic_year,
        placement_status=placement_status,
        cohort_students=cohort_students,
        branch_placement=branch_placement,
        package_ranges=package_ranges,
        recruitment_overview=recruitment_overview,
        top_companies=top_companies
    )

@app.route("/interviews", methods=["GET", "POST"])
def interviews():

    connection = get_db_connection()

    if request.method == "POST":
        application_id = request.form.get("application_id")
        return_to_student = request.form.get("return_to_student", type=int)
        interview_date = request.form.get("interview_date", "").strip()
        interview_time = request.form.get("interview_time", "").strip()
        round_name = request.form.get("round", "Technical").strip()
        venue = request.form.get("venue", "").strip()

        if not application_id or not interview_date or not interview_time or not venue:
            connection.close()
            flash("Application, date, time, and venue are required.", "error")
            if return_to_student:
                return redirect(url_for("view_student", student_id=return_to_student))
            return redirect(url_for("interviews"))

        try:
            application = connection.execute(
                "SELECT student_id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            if application is None:
                flash("Select a valid application before scheduling an interview.", "error")
            elif return_to_student and application["student_id"] != return_to_student:
                flash("The selected application does not belong to this student.", "error")
            else:
                date.fromisoformat(interview_date)
                time.fromisoformat(interview_time)
                connection.execute(
                    """
                    INSERT INTO interviews
                        (application_id, round, interview_date, interview_time, venue, status)
                    VALUES (?, ?, ?, ?, ?, 'Scheduled')
                    """,
                    (application_id, round_name, interview_date, interview_time, venue),
                )
                connection.commit()
                flash("Interview scheduled successfully.", "success")
        except ValueError:
            connection.rollback()
            flash("Enter a valid interview date and time.", "error")
        except sqlite3.Error:
            connection.rollback()
            app.logger.exception("Could not schedule an interview")
            flash("Unable to schedule this interview.", "error")
        finally:
            connection.close()
        if return_to_student:
            return redirect(url_for("view_student", student_id=return_to_student))
        return redirect(url_for("interviews"))

    interviews = connection.execute(
        """
        SELECT
            interviews.*,
            applications.id AS application_id,
            students.name AS student_name,
            students.registration_no,
            students.branch AS student_branch,
            students.cgpa AS student_cgpa,
            companies.name AS company_name,
            jobs.role,
            jobs.package

        FROM interviews

        JOIN applications
            ON interviews.application_id = applications.id

        JOIN students
            ON applications.student_id = students.id

        JOIN jobs
            ON applications.job_id = jobs.id

        JOIN companies
            ON jobs.company_id = companies.id

        ORDER BY interviews.interview_date ASC, interviews.interview_time ASC
        """
    ).fetchall()

    applications = connection.execute(
        """
        SELECT applications.id, students.id AS student_id, students.name AS student_name,
               students.registration_no, students.branch AS student_branch,
               students.cgpa AS student_cgpa, companies.name AS company_name,
               jobs.role, jobs.package
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE applications.status NOT IN ('Rejected')
        ORDER BY students.name ASC
        """
    ).fetchall()

    status_counts = connection.execute(
        "SELECT status, COUNT(*) AS total FROM interviews GROUP BY status"
    ).fetchall()
    connection.close()

    return render_template(
        "interviews/index.html",
        interviews=interviews,
        applications=applications,
        status_counts={row["status"]: row["total"] for row in status_counts},
        selected_student_id=request.args.get("student_id", type=int),
    )


@app.route("/interviews/ai-practice/<int:interview_id>")
def ai_interview_practice(interview_id):
    connection = get_db_connection()
    interview = connection.execute(
        """
        SELECT interviews.id, interviews.round, interviews.interview_date,
               interviews.interview_time, interviews.venue, interviews.status,
               students.id AS student_id, students.name AS student_name,
               students.registration_no, students.branch, students.email,
               companies.name AS company_name, jobs.role
        FROM interviews
        JOIN applications ON interviews.application_id = applications.id
        JOIN students ON applications.student_id = students.id
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE interviews.id = ?
        """,
        (interview_id,),
    ).fetchone()
    connection.close()
    if interview is None:
        abort(404)
    return render_template(
        "interviews/ai_practice.html",
        interview=interview,
        interview_context={
            "student": interview["student_name"],
            "company": interview["company_name"],
            "role": interview["role"],
            "round": interview["round"],
        },
    )


@app.route("/interviews/update/<int:interview_id>", methods=["POST"])
def update_interview(interview_id):
    status = request.form.get("status")
    allowed_statuses = {"Scheduled", "Completed", "Pending", "Cancelled"}
    if status not in allowed_statuses:
        flash("Invalid interview status.", "error")
        return redirect(url_for("interviews"))

    connection = get_db_connection()
    connection.execute(
        "UPDATE interviews SET status = ? WHERE id = ?",
        (status, interview_id),
    )
    connection.commit()
    connection.close()
    flash("Interview status updated.", "success")
    return redirect(url_for("interviews"))

@app.route("/applications")
def applications():

    connection = get_db_connection()

    applications = connection.execute(
        """
        SELECT
            applications.*,
            students.name AS student_name,
            students.registration_no,
            students.branch AS student_branch,
            students.cgpa AS student_cgpa,
            jobs.role,
            jobs.id AS job_id,
            jobs.package,
            companies.name AS company_name,
            companies.id AS company_id

        FROM applications

        JOIN students
            ON applications.student_id = students.id

        JOIN jobs
            ON applications.job_id = jobs.id

        JOIN companies
            ON jobs.company_id = companies.id

        ORDER BY applications.id DESC
        """
    ).fetchall()

    students = connection.execute(
        "SELECT id, name, registration_no FROM students ORDER BY name ASC"
    ).fetchall()
    jobs = connection.execute(
        """
        SELECT jobs.id, jobs.role, companies.name AS company_name
        FROM jobs JOIN companies ON jobs.company_id = companies.id
        ORDER BY companies.name ASC, jobs.role ASC
        """
    ).fetchall()
    status_counts = connection.execute(
        "SELECT status, COUNT(*) AS total FROM applications GROUP BY status"
    ).fetchall()
    connection.close()

    return render_template(
        "applications/index.html",
        applications=applications,
        students=students,
        jobs=jobs,
        status_counts={row["status"]: row["total"] for row in status_counts},
        selected_student_id=request.args.get("student_id", type=int),
    )


@app.route("/applications/add", methods=["POST"])
def add_application():
    student_id = request.form.get("student_id")
    job_id = request.form.get("job_id")
    status = request.form.get("status", "Applied")
    return_to_student = request.form.get("return_to_student", type=int)

    if not student_id or not job_id:
        flash("Select a student and job drive to add an application.", "error")
        if return_to_student:
            return redirect(url_for("view_student", student_id=return_to_student))
        return redirect(url_for("applications"))

    allowed_statuses = {
        "Applied", "In Progress", "Selected", "Rejected"
    }
    if status not in allowed_statuses:
        flash("Select a valid application status.", "error")
        if return_to_student:
            return redirect(url_for("view_student", student_id=return_to_student))
        return redirect(url_for("applications"))

    try:
        match_score = float(request.form.get("match_score", 0))
        if not 0 <= match_score <= 100:
            raise ValueError
        connection = get_db_connection()
        if return_to_student and int(student_id) != return_to_student:
            flash("The selected application does not belong to this student.", "error")
            connection.close()
            return redirect(url_for("view_student", student_id=return_to_student))
        connection.execute(
            """
            INSERT INTO applications (student_id, job_id, match_score, status)
            VALUES (?, ?, ?, ?)
            """,
            (student_id, job_id, match_score, status)
        )
        connection.commit()
        connection.close()
        flash("Application added successfully.", "success")
    except sqlite3.IntegrityError:
        flash("This student already has an application for that job drive.", "error")
    except (TypeError, ValueError):
        flash("Enter a valid match score between 0 and 100.", "error")

    if return_to_student:
        return redirect(url_for("view_student", student_id=return_to_student))
    return redirect(url_for("applications"))


@app.route("/applications/update/<int:application_id>", methods=["POST"])
def update_application(application_id):
    status = request.form.get("status")
    allowed_statuses = {
        "Applied",
        "In Progress",
        "Selected",
        "Rejected"
    }
    if status not in allowed_statuses:
        flash("Invalid application status.", "error")
        return redirect(url_for("applications"))

    connection = get_db_connection()
    connection.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (status, application_id)
    )
    connection.commit()
    connection.close()
    flash("Application status updated.", "success")
    return redirect(url_for("applications"))


@app.route("/offers/add", methods=["POST"])
def add_offer():
    application_id = request.form.get("application_id")
    return_to_student = request.form.get("return_to_student", type=int)

    if not application_id:
        flash("Select a selected application to create an offer.", "error")
        if return_to_student:
            return redirect(url_for("view_student", student_id=return_to_student))
        return redirect(url_for("offers"))

    connection = get_db_connection()
    try:
        application = connection.execute(
            """
            SELECT applications.student_id, applications.status,
                   jobs.id AS job_id, jobs.company_id, jobs.package
            FROM applications
            JOIN jobs ON applications.job_id = jobs.id
            WHERE applications.id = ?
            """,
            (application_id,),
        ).fetchone()
        if application is None or application["status"] != "Selected":
            flash("An offer can only be created from a selected application.", "error")
        elif return_to_student and application["student_id"] != return_to_student:
            flash("The selected application does not belong to this student.", "error")
        else:
            existing_offer = connection.execute(
                "SELECT 1 FROM offers WHERE student_id = ? AND job_id = ?",
                (application["student_id"], application["job_id"]),
            ).fetchone()
            if existing_offer:
                flash("An offer already exists for this student and job drive.", "error")
            else:
                package = float(request.form.get("package", application["package"] or 0))
                if package < 0:
                    raise ValueError
                offer_date = request.form.get("offer_date", "").strip() or date.today().isoformat()
                joining_date = request.form.get("joining_date", "").strip() or None
                date.fromisoformat(offer_date)
                if joining_date:
                    date.fromisoformat(joining_date)
                connection.execute(
                    """
                    INSERT INTO offers
                        (student_id, company_id, job_id, package, offer_date, joining_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'Pending')
                    """,
                    (
                        application["student_id"],
                        application["company_id"],
                        application["job_id"],
                        package,
                        offer_date,
                        joining_date,
                    ),
                )
                connection.commit()
                flash("Offer created with pending status.", "success")
    except ValueError:
        connection.rollback()
        flash("Enter a valid non-negative package and offer dates.", "error")
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not create an offer")
        flash("Unable to create this offer.", "error")
    finally:
        connection.close()

    if return_to_student:
        return redirect(url_for("view_student", student_id=return_to_student))
    return redirect(url_for("offers"))


@app.route("/companies")
def companies():

    connection = get_db_connection()
    sync_job_drive_statuses(connection)

    companies = connection.execute(
        """
        SELECT companies.*,
               SUM(
                   CASE WHEN jobs.status IN ('Active', 'Upcoming')
                        THEN 1 ELSE 0 END
               ) AS recruiting_drive_count
        FROM companies
        LEFT JOIN jobs ON jobs.company_id = companies.id
        GROUP BY companies.id
        ORDER BY companies.id DESC
        """
    ).fetchall()

    total_companies = connection.execute(
        "SELECT COUNT(*) FROM companies"
    ).fetchone()[0]
    recruiting_partners = [
        company for company in companies if company["recruiting_drive_count"] > 0
    ]

    connection.close()

    return render_template(
        "companies/index.html",
        companies=companies,
        total_companies=total_companies,
        total_recruiting_partners=len(recruiting_partners),
        recruiting_partners=recruiting_partners,
    )

@app.route("/offers")
def offers():

    connection = get_db_connection()

    offers = connection.execute(
        """
        SELECT
            offers.*,
            students.name AS student_name,
            students.registration_no,
            students.branch AS student_branch,
            students.cgpa AS student_cgpa,
            companies.name AS company_name,
            jobs.role

        FROM offers

        JOIN students
            ON offers.student_id = students.id

        JOIN companies
            ON offers.company_id = companies.id

        JOIN jobs
            ON offers.job_id = jobs.id

        ORDER BY offers.id DESC
        """
    ).fetchall()

    status_counts = connection.execute(
        """
        SELECT lower(trim(status)) AS status_key, COUNT(*) AS total
        FROM offers
        GROUP BY lower(trim(status))
        """
    ).fetchall()
    selected_applications = connection.execute(
        """
        SELECT applications.id, students.id AS student_id,
               students.name AS student_name, students.registration_no,
               companies.name AS company_name, jobs.role, jobs.package
        FROM applications
        JOIN students ON applications.student_id = students.id
        JOIN jobs ON applications.job_id = jobs.id
        JOIN companies ON jobs.company_id = companies.id
        WHERE applications.status = 'Selected'
        ORDER BY students.name, companies.name, jobs.role
        """
    ).fetchall()
    package_summary = connection.execute(
        """
        SELECT
            COALESCE(MAX(package), 0) AS highest,
            COALESCE(AVG(package), 0) AS average,
            COALESCE(MIN(package), 0) AS lowest,
            COUNT(DISTINCT company_id) AS companies,
            COUNT(*) AS total_offers
        FROM offers
        """
    ).fetchone()

    connection.close()
    normalized_status_counts = {
        "Accepted": 0,
        "Pending": 0,
        "Declined": 0,
    }
    status_labels = {
        "accepted": "Accepted",
        "pending": "Pending",
        "declined": "Declined",
    }
    for row in status_counts:
        label = status_labels.get(row["status_key"])
        if label:
            normalized_status_counts[label] = row["total"]

    return render_template(
        "offers/index.html",
        offers=offers,
        selected_applications=selected_applications,
        selected_student_id=request.args.get("student_id", type=int),
        status_counts=normalized_status_counts,
        package_summary=package_summary,
        acceptance_rate=round(
            normalized_status_counts["Accepted"]
            / max(
                normalized_status_counts["Accepted"]
                + normalized_status_counts["Declined"],
                1,
            )
        ),
        decided_offer_count=(
            normalized_status_counts["Accepted"]
            + normalized_status_counts["Declined"]
        ),
    )


@app.route("/offers/update/<int:offer_id>", methods=["POST"])
def update_offer(offer_id):
    status = request.form.get("status")
    allowed_statuses = {"Accepted", "Pending", "Declined"}
    if status not in allowed_statuses:
        flash("Invalid offer status.", "error")
        return redirect(url_for("offers"))

    connection = get_db_connection()
    updated = False
    try:
        offer = connection.execute(
            "SELECT student_id FROM offers WHERE id = ?",
            (offer_id,),
        ).fetchone()
        if offer is None:
            flash("Offer record was not found.", "error")
        else:
            connection.execute(
                "UPDATE offers SET status = ? WHERE id = ?",
                (status, offer_id),
            )
            accepted_offer = connection.execute(
                """
                SELECT 1 FROM offers
                WHERE student_id = ? AND lower(trim(status)) = 'accepted'
                LIMIT 1
                """,
                (offer["student_id"],),
            ).fetchone()
            connection.execute(
                "UPDATE students SET placement_status = ? WHERE id = ?",
                ("Placed" if accepted_offer else "Unplaced", offer["student_id"]),
            )
            connection.commit()
            updated = True
    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Could not update offer %s", offer_id)
        flash("Unable to update the offer decision.", "error")
    finally:
        connection.close()

    if updated:
        flash("Offer decision updated.", "success")
    return redirect(url_for("offers"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
