from datetime import date, datetime, time, timedelta

from database import get_db_connection


APPLICATION_STATUSES = [
    "Applied", "Applied", "Applied", "Applied",
    "In Progress", "In Progress", "In Progress", "In Progress",
    "In Progress", "In Progress", "In Progress", "In Progress",
    "In Progress", "In Progress", "In Progress",
    "Selected", "Selected", "Selected",
    "Rejected", "Rejected",
    "Applied", "In Progress", "In Progress", "Selected",
]

INTERVIEW_STATUSES = [
    "Completed", "Completed", "Pending", "Scheduled",
    "Scheduled", "Completed", "Pending", "Scheduled",
    "Cancelled", "Completed", "Scheduled",
]


def seed_placement_activity():
    connection = get_db_connection()
    added_applications = 0
    added_interviews = 0
    added_offers = 0

    try:
        students = connection.execute(
            """
            SELECT id, branch, cgpa, backlogs, attendance
            FROM students
            WHERE lower(trim(COALESCE(placement_status, ''))) != 'placed'
            ORDER BY id
            """
        ).fetchall()
        jobs = connection.execute(
            """
            SELECT jobs.id, jobs.min_cgpa, jobs.max_backlogs,
                   jobs.min_attendance, jobs.eligible_branches
            FROM jobs
            ORDER BY jobs.id
            """
        ).fetchall()

        pairs = []
        used_students = set()
        for job in jobs:
            branches = {
                branch.strip().casefold()
                for branch in (job["eligible_branches"] or "").split(",")
                if branch.strip()
            }
            matches = [
                student for student in students
                if student["id"] not in used_students
                and student["cgpa"] >= (job["min_cgpa"] or 0)
                and student["backlogs"] <= (job["max_backlogs"] or 0)
                and student["attendance"] >= (job["min_attendance"] or 0)
                and (
                    not branches
                    or (student["branch"] or "").strip().casefold() in branches
                )
            ]

            for student in matches[:2]:
                pairs.append((student["id"], job["id"]))
                used_students.add(student["id"])
                if len(pairs) >= len(APPLICATION_STATUSES):
                    break
            if len(pairs) >= len(APPLICATION_STATUSES):
                break

        application_records = []
        for index, (student_id, job_id) in enumerate(pairs):
            existing = connection.execute(
                """
                SELECT id, status FROM applications
                WHERE student_id = ? AND job_id = ?
                """,
                (student_id, job_id),
            ).fetchone()
            if existing:
                application_records.append(
                    (existing["id"], job_id, existing["status"])
                )
                continue

            applied_at = datetime.combine(
                date.today() - timedelta(days=index + 2),
                time(10 + index % 8, (index * 7) % 60),
            ).isoformat(sep=" ", timespec="seconds")
            cursor = connection.execute(
                """
                INSERT INTO applications
                    (student_id, job_id, match_score, status, applied_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    job_id,
                    72 + (index * 7) % 27,
                    APPLICATION_STATUSES[index],
                    applied_at,
                ),
            )
            application_records.append(
                (cursor.lastrowid, job_id, APPLICATION_STATUSES[index])
            )
            added_applications += 1

        interview_candidates = [
            record for record in application_records
            if record[2] in {"In Progress", "Selected"}
        ][:len(INTERVIEW_STATUSES)]

        for index, (application_id, _job_id, _application_status) in enumerate(
            interview_candidates
        ):
            existing_interview = connection.execute(
                "SELECT 1 FROM interviews WHERE application_id = ?",
                (application_id,),
            ).fetchone()
            if existing_interview:
                continue

            status = INTERVIEW_STATUSES[index]
            day_offset = {
                "Completed": -(index % 6 + 1),
                "Pending": 0,
                "Scheduled": index % 5 + 1,
                "Cancelled": 3,
            }[status]
            interview_day = date.today() + timedelta(days=day_offset)
            interview_time = time(9 + index % 7, (index * 10) % 60)
            connection.execute(
                """
                INSERT INTO interviews
                    (application_id, round, interview_date, interview_time, venue, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    ("Technical", "HR", "Managerial")[index % 3],
                    interview_day.isoformat(),
                    interview_time.strftime("%H:%M"),
                    ("Campus placement cell", "Seminar Hall A", "Online · Video call")[index % 3],
                    status,
                ),
            )
            added_interviews += 1

        selected_applications = [
            record for record in application_records if record[2] == "Selected"
        ]
        offer_statuses = ["Accepted", "Pending", "Accepted", "Declined"]
        for index, (application_id, job_id, _status) in enumerate(
            selected_applications[:len(offer_statuses)]
        ):
            application = connection.execute(
                "SELECT student_id FROM applications WHERE id = ?",
                (application_id,),
            ).fetchone()
            existing_offer = connection.execute(
                "SELECT 1 FROM offers WHERE student_id = ? AND job_id = ?",
                (application["student_id"], job_id),
            ).fetchone()
            if existing_offer:
                continue

            job = connection.execute(
                "SELECT company_id, package FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO offers
                    (student_id, company_id, job_id, package, offer_date, joining_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application["student_id"],
                    job["company_id"],
                    job_id,
                    job["package"],
                    (date.today() - timedelta(days=index + 1)).isoformat(),
                    (date.today() + timedelta(days=90 + index * 7)).isoformat(),
                    offer_statuses[index],
                ),
            )
            added_offers += 1

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(
        "Placement activity added: "
        f"{added_applications} applications, "
        f"{added_interviews} interviews, {added_offers} offers."
    )


if __name__ == "__main__":
    seed_placement_activity()
