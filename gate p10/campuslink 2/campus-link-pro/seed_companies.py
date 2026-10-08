from database import get_db_connection


companies = [
    ("TCS", "IT Services", "Bengaluru, India", "https://www.tcs.com"),
    ("Infosys", "IT Services", "Bengaluru, India", "https://www.infosys.com"),
    ("Wipro", "IT Services", "Bengaluru, India", "https://www.wipro.com"),
    ("Accenture", "Consulting & IT", "Bengaluru, India", "https://www.accenture.com"),
    ("Cognizant", "IT Services", "Chennai, India", "https://www.cognizant.com"),
    ("Capgemini", "IT Services", "Bengaluru, India", "https://www.capgemini.com"),
    ("HCLTech", "IT Services", "Noida, India", "https://www.hcltech.com"),
    ("Tech Mahindra", "IT Services", "Pune, India", "https://www.techmahindra.com"),
    ("IBM", "Technology", "Bengaluru, India", "https://www.ibm.com"),
    ("Microsoft", "Technology", "Hyderabad, India", "https://www.microsoft.com"),
    ("Amazon", "E-Commerce & Technology", "Bengaluru, India", "https://www.amazon.jobs"),
    ("Deloitte", "Consulting", "Hyderabad, India", "https://www.deloitte.com"),
    ("EY", "Consulting & Professional Services", "Bengaluru, India", "https://www.ey.com"),
    ("PwC", "Consulting & Professional Services", "Bengaluru, India", "https://www.pwc.com"),
    ("Zoho", "Software", "Chennai, India", "https://www.zoho.com"),
    ("Freshworks", "Software", "Chennai, India", "https://www.freshworks.com"),
    ("Razorpay", "FinTech", "Bengaluru, India", "https://razorpay.com"),
    ("Flipkart", "E-Commerce", "Bengaluru, India", "https://www.flipkartcareers.com"),
    ("Reliance Industries", "Conglomerate", "Mumbai, India", "https://www.ril.com"),
    ("Oracle", "Technology", "Bengaluru, India", "https://www.oracle.com")
]


connection = get_db_connection()


for company in companies:

    connection.execute(
        """
        INSERT OR IGNORE INTO companies (
            name,
            industry,
            location,
            website
        )
        VALUES (?, ?, ?, ?)
        """,
        company
    )


connection.commit()
connection.close()


print("20 built-in companies added successfully.")