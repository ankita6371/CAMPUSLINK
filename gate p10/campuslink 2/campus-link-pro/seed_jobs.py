from database import get_db_connection



job_drives = [

    {
        "company": "TCS",
        "role": "Graduate Engineer Trainee",
        "package": 7.0,
        "min_cgpa": 6.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "Python,Java,SQL,Communication",
        "deadline": "2026-10-05",
        "drive_date": "2026-10-12",
        "status": "Active"
    },

    {
        "company": "Infosys",
        "role": "Systems Engineer",
        "package": 6.5,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE",
        "skills": "Java,Python,SQL,Problem Solving",
        "deadline": "2026-10-08",
        "drive_date": "2026-10-15",
        "status": "Active"
    },

    {
        "company": "Wipro",
        "role": "Project Engineer",
        "package": 5.5,
        "min_cgpa": 6.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "Java,Python,SQL,Web Development",
        "deadline": "2026-10-10",
        "drive_date": "2026-10-18",
        "status": "Active"
    },

    {
        "company": "Accenture",
        "role": "Associate Software Engineer",
        "package": 7.2,
        "min_cgpa": 6.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Python,Java,Cloud,SQL",
        "deadline": "2026-10-12",
        "drive_date": "2026-10-20",
        "status": "Active"
    },

    {
        "company": "Cognizant",
        "role": "Programmer Analyst Trainee",
        "package": 6.75,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "Java,SQL,Python,Testing",
        "deadline": "2026-10-15",
        "drive_date": "2026-10-22",
        "status": "Active"
    },

    {
        "company": "Capgemini",
        "role": "Software Engineer",
        "package": 6.0,
        "min_cgpa": 6.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Java,SQL,HTML,CSS",
        "deadline": "2026-10-18",
        "drive_date": "2026-10-25",
        "status": "Active"
    },

    {
        "company": "HCLTech",
        "role": "Graduate Engineer",
        "package": 5.75,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE,EEE,ME",
        "skills": "C,Java,Python,SQL",
        "deadline": "2026-10-20",
        "drive_date": "2026-10-28",
        "status": "Active"
    },

    {
        "company": "Tech Mahindra",
        "role": "Associate Software Engineer",
        "package": 5.0,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "Java,Python,Networking,SQL",
        "deadline": "2026-10-22",
        "drive_date": "2026-10-30",
        "status": "Active"
    },

    {
        "company": "IBM",
        "role": "Associate Developer",
        "package": 8.0,
        "min_cgpa": 7.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Python,Java,Cloud,SQL,AI",
        "deadline": "2026-10-25",
        "drive_date": "2026-11-02",
        "status": "Active"
    },

    {
        "company": "Deloitte",
        "role": "Analyst",
        "package": 7.5,
        "min_cgpa": 6.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "SQL,Excel,Python,Communication",
        "deadline": "2026-10-28",
        "drive_date": "2026-11-05",
        "status": "Active"
    },

    {
        "company": "Zoho",
        "role": "Software Developer",
        "package": 8.5,
        "min_cgpa": 7.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Java,Python,C++,DSA,SQL",
        "deadline": "2026-11-01",
        "drive_date": "2026-11-10",
        "status": "Active"
    },

    {
        "company": "Freshworks",
        "role": "Software Engineer",
        "package": 8.0,
        "min_cgpa": 6.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "JavaScript,Python,SQL,React",
        "deadline": "2026-11-05",
        "drive_date": "2026-11-15",
        "status": "Active"
    },

    {
        "company": "Oracle",
        "role": "Cloud Associate",
        "package": 9.0,
        "min_cgpa": 7.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Java,Python,Cloud,SQL",
        "deadline": "2026-11-08",
        "drive_date": "2026-11-18",
        "status": "Active"
    },

    {
        "company": "Microsoft",
        "role": "Software Engineer Intern",
        "package": 12.0,
        "min_cgpa": 8.0,
        "max_backlogs": 0,
        "min_attendance": 80,
        "branches": "CSE,IT",
        "skills": "C++,Python,DSA,Algorithms",
        "deadline": "2026-11-12",
        "drive_date": "2026-11-22",
        "status": "Active"
    },

    {
        "company": "Amazon",
        "role": "Software Development Engineer",
        "package": 14.0,
        "min_cgpa": 7.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Java,Python,C++,DSA,Algorithms",
        "deadline": "2026-11-15",
        "drive_date": "2026-11-25",
        "status": "Active"
    },

    {
        "company": "Razorpay",
        "role": "Backend Developer",
        "package": 10.0,
        "min_cgpa": 7.0,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT",
        "skills": "Python,Java,APIs,SQL,Git",
        "deadline": "2026-11-18",
        "drive_date": "2026-11-28",
        "status": "Active"
    },

    {
        "company": "Flipkart",
        "role": "Software Development Engineer",
        "package": 11.0,
        "min_cgpa": 7.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Java,Python,DSA,SQL",
        "deadline": "2026-11-20",
        "drive_date": "2026-12-02",
        "status": "Active"
    },

    {
        "company": "EY",
        "role": "Technology Analyst",
        "package": 6.8,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE,EEE",
        "skills": "SQL,Python,Excel,Communication",
        "deadline": "2026-11-22",
        "drive_date": "2026-12-05",
        "status": "Active"
    },

    {
        "company": "PwC",
        "role": "Associate Consultant",
        "package": 7.0,
        "min_cgpa": 6.5,
        "max_backlogs": 0,
        "min_attendance": 75,
        "branches": "CSE,IT,ECE",
        "skills": "Python,SQL,Analytics,Communication",
        "deadline": "2026-11-25",
        "drive_date": "2026-12-08",
        "status": "Active"
    },

    {
        "company": "Reliance Industries",
        "role": "Graduate Engineer Trainee",
        "package": 6.5,
        "min_cgpa": 6.0,
        "max_backlogs": 1,
        "min_attendance": 70,
        "branches": "CSE,IT,ECE,EEE,ME",
        "skills": "Python,SQL,Communication,Problem Solving",
        "deadline": "2026-11-28",
        "drive_date": "2026-12-12",
        "status": "Active"
    }
]



connection = get_db_connection()

added = 0
skipped = 0

for job in job_drives:

    company = connection.execute(
        """
        SELECT id
        FROM companies
        WHERE name = ?
        """,
        (job["company"],)
    ).fetchone()

    if company is None:
        print(
            f"Company not found: {job['company']}"
        )
        skipped += 1
        continue

    existing = connection.execute(
        """
        SELECT id
        FROM jobs
        WHERE company_id = ?
        AND role = ?
        """,
        (
            company["id"],
            job["role"]
        )
    ).fetchone()

    if existing:
        skipped += 1
        continue

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
            company["id"],
            job["role"],
            job["package"],
            job["min_cgpa"],
            job["max_backlogs"],
            job["min_attendance"],
            job["branches"],
            job["skills"],
            job["deadline"],
            job["drive_date"],
            job["status"]
        )
    )

    added += 1


connection.commit()
connection.close()


print()
print("==========================================")
print("CAMPUSLINK JOB DRIVE SEEDING")
print("==========================================")
print(f"Job drives added : {added}")
print(f"Already existed  : {skipped}")
print("==========================================")