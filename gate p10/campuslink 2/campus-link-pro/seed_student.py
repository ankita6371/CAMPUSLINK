import sqlite3
import random
import os

DATABASE = os.path.join(
    os.path.dirname(__file__),
    "instance",
    "campuslink.db"
)

first_names = [
    "Ananya", "Priya", "Rahul", "Aarav", "Sneha",
    "Riya", "Aditya", "Neha", "Rohan", "Pooja",
    "Ayush", "Kavya", "Arjun", "Simran", "Vikash",
    "Sakshi", "Abhishek", "Ishita", "Karan", "Swati",
    "Aman", "Nisha", "Raj", "Shreya", "Sourav",
    "Ankit", "Muskan", "Rakesh", "Divya", "Sumit"
]

last_names = [
    "Sharma", "Mishra", "Kumar", "Patel", "Das",
    "Behera", "Sahu", "Singh", "Mohanty", "Nayak",
    "Jena", "Pradhan", "Rout", "Panda", "Mehta",
    "Gupta", "Verma", "Seth", "Naik", "Samal"
]

branches = ["CSE", "IT", "ECE", "EEE", "ME", "CE"]

skills_by_branch = {
    "CSE": ["Python, Java, SQL", "Python, Flask, HTML, CSS", "Java, SQL, Git"],
    "IT": ["Python, SQL, HTML, CSS", "Java, JavaScript, SQL", "Python, Git, JavaScript"],
    "ECE": ["Python, Embedded Systems, C", "C, IoT, MATLAB", "Python, IoT, C"],
    "EEE": ["C, MATLAB, Embedded Systems", "Python, MATLAB, PLC", "C, PLC, IoT"],
    "ME": ["AutoCAD, SolidWorks, Python", "AutoCAD, CAD, MATLAB", "SolidWorks, CAD, C"],
    "CE": ["AutoCAD, Civil 3D", "AutoCAD, STAAD Pro", "Civil 3D, AutoCAD, Excel"]
}

statuses = ["Unplaced", "Unplaced", "Unplaced", "In Process"]

connection = sqlite3.connect(DATABASE)

existing_count = connection.execute(
    "SELECT COUNT(*) FROM students"
).fetchone()[0]

target = 500

if existing_count >= target:
    print(f"Database already contains {existing_count} students.")
    connection.close()
    exit()

students_to_add = target - existing_count

print(f"Existing students: {existing_count}")
print(f"Adding {students_to_add} sample students...")

for i in range(students_to_add):

    first = random.choice(first_names)
    last = random.choice(last_names)
    name = f"{first} {last}"

    registration_no = f"GATE2026{existing_count + i + 1:04d}"

    email = f"student{existing_count + i + 1}@campuslink.edu"

    phone = "9" + "".join(
        random.choice("0123456789") for _ in range(9)
    )

    branch = random.choice(branches)

    cgpa = round(random.uniform(6.2, 9.6), 2)

    backlogs = random.choices(
        [0, 1, 2],
        weights=[80, 15, 5]
    )[0]

    attendance = round(
        random.uniform(70, 98), 1
    )

    skills = random.choice(
        skills_by_branch[branch]
    )

    placement_status = random.choice(statuses)

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

final_count = connection.execute(
    "SELECT COUNT(*) FROM students"
).fetchone()[0]

connection.close()

print()
print("===================================")
print("CAMPUSLINK SAMPLE DATA CREATED")
print("===================================")
print(f"Total students: {final_count}")
print("Database:", DATABASE)
print("===================================")