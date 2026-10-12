from datetime import date, datetime
import csv
import io

from flask import (
    Flask, render_template_string, request,
    redirect, url_for, flash, make_response
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps


# =========================================================
# 1. FLASK APPLICATION CONFIGURATION
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = "replace-this-with-a-long-random-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///placement.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# =========================================================
# 2. DATABASE ASSOCIATION TABLE
# =========================================================

drive_departments = db.Table(
    "drive_departments",
    db.Column("drive_id", db.Integer, db.ForeignKey("drive.id"), primary_key=True),
    db.Column(
        "department_id",
        db.Integer,
        db.ForeignKey("department.id"),
        primary_key=True
    )
)


# =========================================================
# 3. DATABASE MODELS
# =========================================================

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    roll_number = db.Column(db.String(30), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)

    department_id = db.Column(
        db.Integer, db.ForeignKey("department.id"), nullable=False
    )

    program = db.Column(db.String(100), default="B.Tech")
    year = db.Column(db.Integer, default=2)
    section = db.Column(db.String(10), default="A")
    batch = db.Column(db.String(30), default="2025-2029")
    email = db.Column(db.String(150), unique=True, nullable=False)

    registration_status = db.Column(
        db.String(30), default="Registered"
    )

    cgpa = db.Column(db.Float, default=0.0)
    backlogs = db.Column(db.Integer, default=0)

    department = db.relationship("Department", backref="students")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Email address is used as the login username.
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False)

    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"),
        unique=True, nullable=True
    )

    student = db.relationship("Student", backref="user_account")


class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    website = db.Column(db.String(250))


class Drive(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id"), nullable=False
    )

    role = db.Column(db.String(150), nullable=False)
    package_lpa = db.Column(db.Float, default=0.0)
    location = db.Column(db.String(150))

    min_cgpa = db.Column(db.Float, default=0.0)
    max_backlogs = db.Column(db.Integer, default=0)

    deadline = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default="Open")

    company = db.relationship("Company", backref="drives")

    eligible_departments = db.relationship(
        "Department",
        secondary=drive_departments,
        backref="placement_drives"
    )


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )

    drive_id = db.Column(
        db.Integer, db.ForeignKey("drive.id"), nullable=False
    )

    stage = db.Column(db.String(50), default="Applied")
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", backref="applications")
    drive = db.relationship("Drive", backref="applications")

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "drive_id",
            name="unique_student_drive_application"
        ),
    )


class ClearanceCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    mandatory = db.Column(db.Boolean, default=True)


class StudentClearance(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer, db.ForeignKey("student.id"), nullable=False
    )

    category_id = db.Column(
        db.Integer, db.ForeignKey("clearance_category.id"), nullable=False
    )

    status = db.Column(db.String(30), default="Pending")
    remarks = db.Column(db.String(250), default="")

    student = db.relationship("Student", backref="clearances")
    category = db.relationship("ClearanceCategory", backref="student_clearances")

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "category_id",
            name="unique_student_clearance_category"
        ),
    )


# =========================================================
# 4. LOGIN MANAGEMENT AND ACCESS CONTROL
# =========================================================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            return "Access denied: administrators only.", 403
        return view_function(*args, **kwargs)

    return wrapper


def student_required(view_function):
    @wraps(view_function)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "student":
            return "Access denied: students only.", 403
        return view_function(*args, **kwargs)

    return wrapper


# =========================================================
# 5. DEMO DATA
# =========================================================

def seed_demo_data():
    # Do not duplicate demo records if departments already exist.
    if Department.query.first():
        return

    departments = [
        Department(name="Information Technology", code="IT"),
        Department(name="Computer Science", code="CSE"),
        Department(name="Electronics and Communication", code="ECE"),
    ]

    db.session.add_all(departments)
    db.session.flush()

    for i in range(1, 31):
        department = departments[(i - 1) % len(departments)]

        student = Student(
            roll_number=f"DEMO{i:03d}",
            full_name=f"Demo Student {i}",
            department_id=department.id,
            program="B.Tech",
            year=2,
            section="A",
            batch="2025-2029",
            email=f"demo{i:03d}@example.com",
            registration_status="Registered",
            cgpa=round(6.0 + (i % 40) / 10, 2),
            backlogs=0 if i % 4 else 1,
        )

        db.session.add(student)

    companies = [
        Company(name="Tech Solutions", website="https://example.com"),
        Company(name="Global Systems", website="https://example.com"),
        Company(name="Digital Innovations", website="https://example.com"),
        Company(name="Cloud Services", website="https://example.com"),
        Company(name="Software Works", website="https://example.com"),
    ]

    db.session.add_all(companies)
    db.session.flush()

    for i, company in enumerate(companies):
        drive = Drive(
            company_id=company.id,
            role=["Software Engineer", "Web Developer", "Data Analyst",
                  "Cloud Engineer", "Python Developer"][i],
            package_lpa=4.0 + i,
            location="India",
            min_cgpa=6.0,
            max_backlogs=0,
            deadline=date(2027, 12, 31),
            status="Open",
        )

        drive.eligible_departments = departments
        db.session.add(drive)

    clearance_categories = [
        ClearanceCategory(name="Library", mandatory=True),
        ClearanceCategory(name="Laboratory", mandatory=True),
        ClearanceCategory(name="Department", mandatory=True),
        ClearanceCategory(name="Accounts", mandatory=True),
    ]

    db.session.add_all(clearance_categories)
    db.session.flush()

    students = Student.query.all()
    drives = Drive.query.all()

    for student in students:
        for category in clearance_categories:
            db.session.add(
                StudentClearance(
                    student_id=student.id,
                    category_id=category.id,
                    status="Pending",
                    remarks=""
                )
            )

    for student in students[:20]:
        drive = drives[(student.id - 1) % len(drives)]

        db.session.add(
            Application(
                student_id=student.id,
                drive_id=drive.id,
                stage="Applied"
            )
        )

    db.session.commit()


def seed_login_accounts():
    # Create the demo administrator only if it does not already exist.
    admin_email = "admin@university.local"

    admin = User.query.filter_by(username=admin_email).first()

    if admin is None:
        db.session.add(
            User(
                username=admin_email,
                password_hash=generate_password_hash("AdminDemo@123"),
                role="admin"
            )
        )

    # Create a student login linked to the first demo student.
    student = Student.query.filter_by(email="demo001@example.com").first()

    if student:
        student_user = User.query.filter_by(
            username=student.email
        ).first()

        if student_user is None:
            db.session.add(
                User(
                    username=student.email,
                    password_hash=generate_password_hash("StudentDemo@123"),
                    role="student",
                    student_id=student.id
                )
            )

    db.session.commit()


# =========================================================
# 6. SHARED PAGE LAYOUT
# =========================================================

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }} - Placement Portal</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f3f5f9;
            margin: 0;
            color: #222;
        }
        header {
            background: #172554;
            color: white;
            padding: 18px 5%;
        }
        nav a {
            color: white;
            margin-right: 15px;
            text-decoration: none;
        }
        main {
            max-width: 1100px;
            margin: 25px auto;
            padding: 20px;
            background: white;
            border-radius: 10px;
        }
        input, select, button {
            padding: 9px;
            margin: 5px 0;
            max-width: 100%;
        }
        button {
            background: #1d4ed8;
            color: white;
            border: 0;
            border-radius: 4px;
            cursor: pointer;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin-top: 15px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 9px;
            text-align: left;
        }
        th { background: #e8eefc; }
        .message {
            background: #fff4cc;
            padding: 10px;
            margin-bottom: 10px;
        }
        .cards {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        .card {
            padding: 18px;
            background: #e8eefc;
            border-radius: 8px;
            min-width: 140px;
        }
        .form-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }
        .form-grid > * { flex: 1 1 160px; }
        a { color: #1d4ed8; }
        @media(max-width: 600px) {
            main { margin: 10px; padding: 12px; overflow-x: auto; }
            table { font-size: 12px; }
        }
    </style>
</head>
<body>
<header>
    <h2>University Placement & No-Dues Portal</h2>
    <nav>
        <a href="{{ url_for('home') }}">Home</a>
        {% if current_user.is_authenticated %}
            {% if current_user.role == 'admin' %}
                <a href="{{ url_for('admin_dashboard') }}">Admin Dashboard</a>
                <a href="{{ url_for('students_page') }}">Students</a>
                <a href="{{ url_for('companies_page') }}">Companies</a>
                <a href="{{ url_for('drives_page') }}">Placement Drives</a>
                <a href="{{ url_for('applications_page') }}">Applications</a>
                <a href="{{ url_for('clearances_page') }}">No-Dues</a>
            {% else %}
                <a href="{{ url_for('student_dashboard') }}">My Dashboard</a>
            {% endif %}
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </nav>
</header>
<main>
    {% with messages = get_flashed_messages() %}
        {% for message in messages %}
            <div class="message">{{ message }}</div>
        {% endfor %}
    {% endwith %}
    PAGE_CONTENT
</main>
</body>
</html>
"""


def page(title, content, **context):
    template = BASE_HTML.replace("PAGE_CONTENT", content)
    return render_template_string(template, title=title, **context)


# =========================================================
# 7. HOME PAGE
# =========================================================

@app.route("/")
def home():
    content = """
    <h1>University Portal</h1>
    <p>Manage student placements, company drives, applications, and departmental No-Dues.</p>

    <div class="cards">
        <div class="card"><h3>Students</h3><h2>{{ student_count }}</h2></div>
        <div class="card"><h3>Companies</h3><h2>{{ company_count }}</h2></div>
        <div class="card"><h3>Placement Drives</h3><h2>{{ drive_count }}</h2></div>
        <div class="card"><h3>Applications</h3><h2>{{ application_count }}</h2></div>
    </div>

    {% if not current_user.is_authenticated %}
        <p><a href="{{ url_for('login') }}">Login to continue</a></p>
    {% endif %}
    """

    return page(
        "Home",
        content,
        student_count=Student.query.count(),
        company_count=Company.query.count(),
        drive_count=Drive.query.count(),
        application_count=Application.query.count()
    )


# =========================================================
# 8. LOGIN AND LOGOUT
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)

            if user.role == "admin":
                return redirect(url_for("admin_dashboard"))

            return redirect(url_for("student_dashboard"))

        flash("Invalid email or password.")

    content = """
    <h1>Login</h1>
    <form method="POST">
        <label>Email address</label><br>
        <input type="email" name="email" required><br>

        <label>Password</label><br>
        <input type="password" name="password" required><br>

        <button type="submit">Login</button>
    </form>

    <hr>
    <h3>Demo accounts</h3>
    <p>Admin: admin@university.local</p>
    <p>Student: demo001@example.com</p>
    <p>Use the demo passwords configured in seed_login_accounts().</p>
    """

    return page("Login", content)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("login"))


# =========================================================
# 9. ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    content = """
    <h1>Administrator Dashboard</h1>
    <p>Welcome, {{ current_user.username }}</p>

    <div class="cards">
        <div class="card"><h3>Students</h3><h2>{{ students }}</h2></div>
        <div class="card"><h3>Companies</h3><h2>{{ companies }}</h2></div>
        <div class="card"><h3>Drives</h3><h2>{{ drives }}</h2></div>
        <div class="card"><h3>Applications</h3><h2>{{ applications }}</h2></div>
        <div class="card"><h3>Selected</h3><h2>{{ selected }}</h2></div>
        <div class="card"><h3>Pending No-Dues</h3><h2>{{ pending }}</h2></div>
    </div>

    <p><a href="{{ url_for('export_students') }}">Export students as CSV</a></p>
    """

    pending = StudentClearance.query.filter(
        StudentClearance.status != "Cleared"
    ).count()

    selected = Application.query.filter_by(stage="Selected").count()

    return page(
        "Admin Dashboard",
        content,
        students=Student.query.count(),
        companies=Company.query.count(),
        drives=Drive.query.count(),
        applications=Application.query.count(),
        selected=selected,
        pending=pending
    )


# =========================================================
# 10. STUDENT DASHBOARD
# =========================================================

@app.route("/student-dashboard")
@student_required
def student_dashboard():
    student = db.session.get(Student, current_user.student_id)

    if student is None:
        return "Your account is not linked to a student record.", 400

    applications = Application.query.filter_by(
        student_id=student.id
    ).all()

    clearances = StudentClearance.query.filter_by(
        student_id=student.id
    ).all()

    content = """
    <h1>Student Dashboard</h1>
    <p>Welcome, {{ student.full_name }}!</p>

    <h3>Student Details</h3>
    <p>Roll number: {{ student.roll_number }}</p>
    <p>Email: {{ student.email }}</p>
    <p>Department: {{ student.department.name }}</p>
    <p>CGPA: {{ student.cgpa }}</p>
    <p>Backlogs: {{ student.backlogs }}</p>

    <h3>Available Placement Drives</h3>
    <table>
        <tr><th>Company</th><th>Role</th><th>Package (LPA)</th>
        <th>Eligibility</th><th>Action</th></tr>
        {% for drive in drives %}
        <tr>
            <td>{{ drive.company.name }}</td>
            <td>{{ drive.role }}</td>
            <td>{{ drive.package_lpa }}</td>
            <td>
                {% if student.cgpa >= drive.min_cgpa
                    and student.backlogs <= drive.max_backlogs
                    and student.department in drive.eligible_departments
                    and drive.status == 'Open'
                    and (not drive.deadline or drive.deadline >= today) %}
                    Eligible
                {% else %}
                    Not eligible / Closed
                {% endif %}
            </td>
            <td>
                {% if student.cgpa >= drive.min_cgpa
                    and student.backlogs <= drive.max_backlogs
                    and student.department in drive.eligible_departments
                    and drive.status == 'Open'
                    and (not drive.deadline or drive.deadline >= today)
                    and drive.id not in applied_drive_ids %}
                    <form method="POST"
                          action="{{ url_for('apply_drive', drive_id=drive.id) }}">
                        <button type="submit">Apply</button>
                    </form>
                {% elif drive.id in applied_drive_ids %}
                    Already applied
                {% else %}
                    Not available
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>

    <h3>My Applications</h3>
    <table>
        <tr><th>Company</th><th>Role</th><th>Stage</th></tr>
        {% for application in applications %}
        <tr>
            <td>{{ application.drive.company.name }}</td>
            <td>{{ application.drive.role }}</td>
            <td>{{ application.stage }}</td>
        </tr>
        {% else %}
        <tr><td colspan="3">No applications yet.</td></tr>
        {% endfor %}
    </table>

    <h3>My No-Dues Status</h3>
    <table>
        <tr><th>Department</th><th>Status</th><th>Remarks</th></tr>
        {% for clearance in clearances %}
        <tr>
            <td>{{ clearance.category.name }}</td>
            <td>{{ clearance.status }}</td>
            <td>{{ clearance.remarks or '-' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="3">No clearance records found.</td></tr>
        {% endfor %}
    </table>
    <p>Overall No-Dues: <strong>{{ overall_status }}</strong></p>
    """

    overall_status = (
        "Cleared"
        if all(c.status == "Cleared" for c in clearances)
        and len(clearances) > 0
        else "Pending"
    )

    return page(
        "Student Dashboard",
        content,
        student=student,
        drives=Drive.query.order_by(Drive.id.desc()).all(),
        applications=applications,
        clearances=clearances,
        applied_drive_ids={a.drive_id for a in applications},
        today=date.today(),
        overall_status=overall_status
    )


# =========================================================
# 11. STUDENT MANAGEMENT
# =========================================================

@app.route("/students", methods=["GET", "POST"])
@admin_required
def students_page():
    message = None

    if request.method == "POST":
        try:
            roll_number = request.form.get("roll_number", "").strip()
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()

            department_id = int(request.form.get("department_id", "0"))
            cgpa = float(request.form.get("cgpa", "0"))
            backlogs = int(request.form.get("backlogs", "0"))
            year = int(request.form.get("year", "2"))

            if not roll_number or not full_name or not email:
                raise ValueError("Roll number, name, and email are required.")

            if not 0 <= cgpa <= 10:
                raise ValueError("CGPA must be between 0 and 10.")

            if backlogs < 0:
                raise ValueError("Backlogs cannot be negative.")

            department = db.session.get(Department, department_id)

            if department is None:
                raise ValueError("Please select a valid department.")

            duplicate = Student.query.filter(
                db.or_(
                    Student.roll_number == roll_number,
                    Student.email == email
                )
            ).first()

            if duplicate:
                raise ValueError("Roll number or email already exists.")

            student = Student(
                roll_number=roll_number,
                full_name=full_name,
                email=email,
                department_id=department_id,
                cgpa=cgpa,
                backlogs=backlogs,
                year=year,
                program="B.Tech",
                section="A",
                batch="2025-2029",
                registration_status="Registered"
            )

            db.session.add(student)
            db.session.commit()

            flash("Student added successfully.")
            return redirect(url_for("students_page"))

        except ValueError as error:
            db.session.rollback()
            message = str(error)

    search = request.args.get("q", "").strip()

    query = Student.query

    if search:
        query = query.filter(
            db.or_(
                Student.full_name.ilike(f"%{search}%"),
                Student.roll_number.ilike(f"%{search}%"),
                Student.email.ilike(f"%{search}%")
            )
        )

    students = query.order_by(Student.roll_number).all()

    content = """
    <h1>Student Management</h1>

    {% if message %}<div class="message">{{ message }}</div>{% endif %}

    <h3>Add Student</h3>
    <form method="POST" class="form-grid">
        <input name="roll_number" placeholder="Roll number" required>
        <input name="full_name" placeholder="Full name" required>
        <input type="email" name="email" placeholder="Email" required>

        <select name="department_id" required>
            <option value="">Select department</option>
            {% for department in departments %}
            <option value="{{ department.id }}">{{ department.name }}</option>
            {% endfor %}
        </select>

        <input type="number" name="cgpa" placeholder="CGPA"
               min="0" max="10" step="0.01" required>

        <input type="number" name="backlogs" placeholder="Backlogs"
               min="0" value="0" required>

        <input type="number" name="year" placeholder="Year"
               min="1" max="6" value="2" required>

        <button type="submit">Add Student</button>
    </form>

    <hr>
    <h3>Search Students</h3>
    <form method="GET">
        <input name="q" value="{{ search }}" placeholder="Name, roll number or email">
        <button type="submit">Search</button>
        <a href="{{ url_for('students_page') }}">Clear</a>
    </form>

    <table>
        <tr><th>Roll No.</th><th>Name</th><th>Email</th><th>Department</th>
        <th>CGPA</th><th>Backlogs</th><th>Edit</th></tr>
        {% for student in students %}
        <tr>
            <td>{{ student.roll_number }}</td>
            <td>{{ student.full_name }}</td>
            <td>{{ student.email }}</td>
            <td>{{ student.department.name }}</td>
            <td>{{ student.cgpa }}</td>
            <td>{{ student.backlogs }}</td>
            <td><a href="{{ url_for('edit_student', student_id=student.id) }}">Edit</a></td>
        </tr>
        {% else %}
        <tr><td colspan="7">No students found.</td></tr>
        {% endfor %}
    </table>

    <p><a href="{{ url_for('export_students') }}">Export student data to CSV</a></p>
    """

    return page(
        "Students",
        content,
        students=students,
        departments=Department.query.order_by(Department.name).all(),
        search=search,
        message=message
    )


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
@admin_required
def edit_student(student_id):
    student = db.session.get(Student, student_id)

    if student is None:
        return "Student not found.", 404

    if request.method == "POST":
        try:
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            department_id = int(request.form.get("department_id", "0"))
            cgpa = float(request.form.get("cgpa", "0"))
            backlogs = int(request.form.get("backlogs", "0"))

            if not full_name or not email:
                raise ValueError("Name and email are required.")

            if not 0 <= cgpa <= 10:
                raise ValueError("CGPA must be between 0 and 10.")

            if backlogs < 0:
                raise ValueError("Backlogs cannot be negative.")

            department = db.session.get(Department, department_id)

            if department is None:
                raise ValueError("Select a valid department.")

            duplicate = Student.query.filter(
                Student.id != student.id,
                db.or_(
                    Student.email == email,
                    Student.roll_number == student.roll_number
                )
            ).first()

            if duplicate and duplicate.email == email:
                raise ValueError("That email address is already in use.")

            student.full_name = full_name
            student.email = email
            student.department_id = department_id
            student.cgpa = cgpa
            student.backlogs = backlogs

            db.session.commit()
            flash("Student updated successfully.")
            return redirect(url_for("students_page"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Edit Student</h1>
    <form method="POST">
        <p>Roll number: <strong>{{ student.roll_number }}</strong></p>

        <label>Full name</label><br>
        <input name="full_name" value="{{ student.full_name }}" required><br>

        <label>Email</label><br>
        <input type="email" name="email" value="{{ student.email }}" required><br>

        <label>Department</label><br>
        <select name="department_id" required>
            {% for department in departments %}
            <option value="{{ department.id }}"
                {% if department.id == student.department_id %}selected{% endif %}>
                {{ department.name }}
            </option>
            {% endfor %}
        </select><br>

        <label>CGPA</label><br>
        <input type="number" name="cgpa" min="0" max="10" step="0.01"
               value="{{ student.cgpa }}" required><br>

        <label>Backlogs</label><br>
        <input type="number" name="backlogs" min="0"
               value="{{ student.backlogs }}" required><br>

        <button type="submit">Save Changes</button>
        <a href="{{ url_for('students_page') }}">Cancel</a>
    </form>
    """

    return page(
        "Edit Student",
        content,
        student=student,
        departments=Department.query.order_by(Department.name).all()
    )


# =========================================================
# 12. COMPANY MANAGEMENT
# =========================================================

@app.route("/companies", methods=["GET", "POST"])
@admin_required
def companies_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        website = request.form.get("website", "").strip()

        if not name:
            flash("Company name is required.")
        elif Company.query.filter_by(name=name).first():
            flash("That company already exists.")
        else:
            db.session.add(Company(name=name, website=website))
            db.session.commit()
            flash("Company added successfully.")
            return redirect(url_for("companies_page"))

    content = """
    <h1>Company Management</h1>

    <form method="POST" class="form-grid">
        <input name="name" placeholder="Company name" required>
        <input name="website" placeholder="Website URL">
        <button type="submit">Add Company</button>
    </form>

    <table>
        <tr><th>ID</th><th>Company</th><th>Website</th></tr>
        {% for company in companies %}
        <tr>
            <td>{{ company.id }}</td>
            <td>{{ company.name }}</td>
            <td>{{ company.website or '-' }}</td>
        </tr>
        {% else %}
        <tr><td colspan="3">No companies available.</td></tr>
        {% endfor %}
    </table>
    """

    return page(
        "Companies",
        content,
        companies=Company.query.order_by(Company.name).all()
    )


# =========================================================
# 13. PLACEMENT DRIVE MANAGEMENT
# =========================================================

@app.route("/drives", methods=["GET", "POST"])
@admin_required
def drives_page():
    if request.method == "POST":
        try:
            company_id = int(request.form.get("company_id", "0"))
            role = request.form.get("role", "").strip()
            package_lpa = float(request.form.get("package_lpa", "0"))
            min_cgpa = float(request.form.get("min_cgpa", "0"))
            max_backlogs = int(request.form.get("max_backlogs", "0"))
            location = request.form.get("location", "").strip()
            deadline_text = request.form.get("deadline", "").strip()
            department_ids = request.form.getlist("department_ids")

            company = db.session.get(Company, company_id)

            if company is None:
                raise ValueError("Select a valid company.")

            if not role:
                raise ValueError("Job role is required.")

            if package_lpa < 0 or not 0 <= min_cgpa <= 10 or max_backlogs < 0:
                raise ValueError("Enter valid package, CGPA, and backlog values.")

            deadline = date.fromisoformat(deadline_text) if deadline_text else None

            departments = []
            for department_id in department_ids:
                department = db.session.get(Department, int(department_id))
                if department:
                    departments.append(department)

            if not departments:
                raise ValueError("Select at least one eligible department.")

            drive = Drive(
                company_id=company_id,
                role=role,
                package_lpa=package_lpa,
                min_cgpa=min_cgpa,
                max_backlogs=max_backlogs,
                location=location,
                deadline=deadline,
                status="Open"
            )

            drive.eligible_departments = departments
            db.session.add(drive)
            db.session.commit()

            flash("Placement drive created.")
            return redirect(url_for("drives_page"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Placement Drives</h1>

    <h3>Create a Drive</h3>
    <form method="POST">
        <label>Company</label><br>
        <select name="company_id" required>
            <option value="">Select company</option>
            {% for company in companies %}
            <option value="{{ company.id }}">{{ company.name }}</option>
            {% endfor %}
        </select><br>

        <input name="role" placeholder="Job role" required><br>
        <input type="number" name="package_lpa" min="0" step="0.1"
               placeholder="Package in LPA" required><br>
        <input name="location" placeholder="Location"><br>

        <label>Minimum CGPA</label><br>
        <input type="number" name="min_cgpa" min="0" max="10"
               step="0.01" value="6" required><br>

        <label>Maximum backlogs</label><br>
        <input type="number" name="max_backlogs" min="0" value="0" required><br>

        <label>Application deadline</label><br>
        <input type="date" name="deadline"><br>

        <label>Eligible departments</label><br>
        {% for department in departments %}
            <label>
                <input type="checkbox" name="department_ids"
                       value="{{ department.id }}">
                {{ department.name }}
            </label><br>
        {% endfor %}

        <button type="submit">Create Drive</button>
    </form>

    <h3>Existing Drives</h3>
    <table>
        <tr><th>Company</th><th>Role</th><th>Package (LPA)</th>
        <th>Minimum CGPA</th><th>Maximum Backlogs</th><th>Deadline</th><th>Status</th></tr>
        {% for drive in drives %}
        <tr>
            <td>{{ drive.company.name }}</td>
            <td>{{ drive.role }}</td>
            <td>{{ drive.package_lpa }}</td>
            <td>{{ drive.min_cgpa }}</td>
            <td>{{ drive.max_backlogs }}</td>
            <td>{{ drive.deadline or '-' }}</td>
            <td>{{ drive.status }}</td>
        </tr>
        {% endfor %}
    </table>
    """

    return page(
        "Placement Drives",
        content,
        companies=Company.query.order_by(Company.name).all(),
        departments=Department.query.order_by(Department.name).all(),
        drives=Drive.query.order_by(Drive.id.desc()).all()
    )


# =========================================================
# 14. STUDENT APPLICATIONS AND ELIGIBILITY
# =========================================================

def is_student_eligible(student, drive):
    return (
        student.cgpa >= drive.min_cgpa
        and student.backlogs <= drive.max_backlogs
        and student.department in drive.eligible_departments
        and drive.status == "Open"
        and (drive.deadline is None or drive.deadline >= date.today())
    )


@app.route("/apply/<int:drive_id>", methods=["POST"])
@student_required
def apply_drive(drive_id):
    student = db.session.get(Student, current_user.student_id)
    drive = db.session.get(Drive, drive_id)

    if student is None or drive is None:
        flash("Student or placement drive not found.")
        return redirect(url_for("student_dashboard"))

    if not is_student_eligible(student, drive):
        flash("You are not eligible for this placement drive.")
        return redirect(url_for("student_dashboard"))

    existing = Application.query.filter_by(
        student_id=student.id,
        drive_id=drive.id
    ).first()

    if existing:
        flash("You have already applied for this drive.")
    else:
        db.session.add(
            Application(
                student_id=student.id,
                drive_id=drive.id,
                stage="Applied"
            )
        )
        db.session.commit()
        flash("Application submitted successfully.")

    return redirect(url_for("student_dashboard"))


@app.route("/applications", methods=["GET", "POST"])
@admin_required
def applications_page():
    if request.method == "POST":
        try:
            application_id = int(request.form.get("application_id", "0"))
            stage = request.form.get("stage", "")

            valid_stages = [
                "Applied",
                "Shortlisted",
                "Online Test",
                "Interview",
                "Selected",
                "Rejected"
            ]

            application = db.session.get(Application, application_id)

            if application is None:
                raise ValueError("Application not found.")

            if stage not in valid_stages:
                raise ValueError("Select a valid selection stage.")

            application.stage = stage
            db.session.commit()

            flash("Application stage updated.")
            return redirect(url_for("applications_page"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Placement Applications</h1>
    <table>
        <tr><th>Student</th><th>Roll Number</th><th>Company</th>
        <th>Role</th><th>Current Stage</th><th>Update Stage</th></tr>
        {% for application in applications %}
        <tr>
            <td>{{ application.student.full_name }}</td>
            <td>{{ application.student.roll_number }}</td>
            <td>{{ application.drive.company.name }}</td>
            <td>{{ application.drive.role }}</td>
            <td>{{ application.stage }}</td>
            <td>
                <form method="POST">
                    <input type="hidden" name="application_id"
                           value="{{ application.id }}">
                    <select name="stage">
                        {% for stage in stages %}
                        <option value="{{ stage }}"
                            {% if stage == application.stage %}selected{% endif %}>
                            {{ stage }}
                        </option>
                        {% endfor %}
                    </select>
                    <button type="submit">Update</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="6">No applications available.</td></tr>
        {% endfor %}
    </table>
    """

    return page(
        "Applications",
        content,
        applications=Application.query.order_by(Application.applied_at.desc()).all(),
        stages=[
            "Applied", "Shortlisted", "Online Test",
            "Interview", "Selected", "Rejected"
        ]
    )


# =========================================================
# 15. DEPARTMENT NO-DUES MANAGEMENT
# =========================================================

@app.route("/clearances", methods=["GET", "POST"])
@admin_required
def clearances_page():
    if request.method == "POST":
        try:
            clearance_id = int(request.form.get("clearance_id", "0"))
            status = request.form.get("status", "")
            remarks = request.form.get("remarks", "").strip()

            valid_statuses = ["Pending", "Cleared", "Rejected"]

            clearance = db.session.get(StudentClearance, clearance_id)

            if clearance is None:
                raise ValueError("Clearance record not found.")

            if status not in valid_statuses:
                raise ValueError("Select a valid clearance status.")

            clearance.status = status
            clearance.remarks = remarks

            db.session.commit()
            flash("Clearance status updated.")
            return redirect(url_for("clearances_page"))

        except ValueError as error:
            db.session.rollback()
            flash(str(error))

    content = """
    <h1>Department No-Dues Management</h1>
    <p>Mark each student's clearance as Pending, Cleared, or Rejected.</p>

    <table>
        <tr><th>Roll Number</th><th>Student</th><th>Category</th>
        <th>Status</th><th>Remarks</th><th>Update</th></tr>

        {% for clearance in clearances %}
        <tr>
            <td>{{ clearance.student.roll_number }}</td>
            <td>{{ clearance.student.full_name }}</td>
            <td>{{ clearance.category.name }}</td>
            <td>{{ clearance.status }}</td>
            <td>{{ clearance.remarks or '-' }}</td>
            <td>
                <form method="POST">
                    <input type="hidden" name="clearance_id"
                           value="{{ clearance.id }}">

                    <select name="status">
                        {% for status in statuses %}
                        <option value="{{ status }}"
                            {% if status == clearance.status %}selected{% endif %}>
                            {{ status }}
                        </option>
                        {% endfor %}
                    </select><br>

                    <input name="remarks" value="{{ clearance.remarks or '' }}"
                           placeholder="Remarks">
                    <button type="submit">Save</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="6">No clearance records available.</td></tr>
        {% endfor %}
    </table>
    """

    return page(
        "No-Dues",
        content,
        clearances=StudentClearance.query.join(Student).order_by(
            Student.roll_number
        ).all(),
        statuses=["Pending", "Cleared", "Rejected"]
    )


# =========================================================
# 16. CSV EXPORT
# =========================================================

@app.route("/export/students.csv")
@admin_required
def export_students():
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Roll Number", "Full Name", "Email",
        "Department", "Program", "Year",
        "Section", "Batch", "CGPA", "Backlogs",
        "Registration Status"
    ])

    for student in Student.query.order_by(Student.roll_number).all():
        writer.writerow([
            student.roll_number,
            student.full_name,
            student.email,
            student.department.name,
            student.program,
            student.year,
            student.section,
            student.batch,
            student.cgpa,
            student.backlogs,
            student.registration_status
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        "attachment; filename=students.csv"
    )

    return response


# =========================================================
# 17. DATABASE CHECK ROUTE
# =========================================================

@app.route("/db-check")
@admin_required
def db_check():
    content = """
    <h1>Database Check</h1>
    <ul>
        <li>Departments: {{ departments }}</li>
        <li>Students: {{ students }}</li>
        <li>Users: {{ users }}</li>
        <li>Companies: {{ companies }}</li>
        <li>Drives: {{ drives }}</li>
        <li>Applications: {{ applications }}</li>
        <li>Clearance Categories: {{ categories }}</li>
        <li>Student Clearances: {{ clearances }}</li>
    </ul>
    """

    return page(
        "Database Check",
        content,
        departments=Department.query.count(),
        students=Student.query.count(),
        users=User.query.count(),
        companies=Company.query.count(),
        drives=Drive.query.count(),
        applications=Application.query.count(),
        categories=ClearanceCategory.query.count(),
        clearances=StudentClearance.query.count()
    )


# =========================================================
# 18. APPLICATION STARTUP
# =========================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_demo_data()
        seed_login_accounts()

    app.run(debug=True)