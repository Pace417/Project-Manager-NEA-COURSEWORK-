from flask import Flask, render_template, request, session, redirect, url_for
import hashlib, sqlite3, datetime,json
app = Flask(__name__)
app.secret_key = "random"




con = sqlite3.connect("database.db")
cur = con.cursor()
cur.execute("""
            CREATE TABLE IF NOT EXISTS userInfo(
            username VARCHAR(35) NOT NULL PRIMARY KEY,
            password VARCHAR(64) NOT NULL,
            joinedDate DATETIME default CURRENT_TIMESTAMP,
            accStatus BOOLEAN
            )
""")

def status_color(status):
    return {
        "backlog":     "#444444",
        "in_progress": "#d68910",
        "review":      "#2471a3",
        "done":        "#4CAF50",
    }.get(status, "#444444")

def priority_color(priority):
    return {
        "low":      "#555555",
        "medium":   "#2471a3",
        "high":     "#d68910",
        "critical": "#c0392b",
    }.get(priority, "#555555")

app.jinja_env.globals['status_color']   = status_color
app.jinja_env.globals['priority_color'] = priority_color

def get_db():
    con = sqlite3.connect("Database.db")
    con.row_factory = sqlite3.Row
    return con
 
def init_db():
    con = get_db()
    cur = con.cursor()
 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS User (
            Username VARCHAR(20) NOT NULL PRIMARY KEY,
            Password VARCHAR(256) NOT NULL
        )
    """)
 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Teams (
            TeamID        INTEGER PRIMARY KEY AUTOINCREMENT,
            TeamName      VARCHAR(50) NOT NULL,
            OwnerUsername VARCHAR(20) NOT NULL,
            FOREIGN KEY (OwnerUsername) REFERENCES User(Username)
        )
    """)
 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS TeamMembers (
            TeamID   INTEGER NOT NULL,
            Username VARCHAR(20) NOT NULL,
            Role     VARCHAR(10) NOT NULL DEFAULT 'member',
            PRIMARY KEY (TeamID, Username),
            FOREIGN KEY (TeamID)   REFERENCES Teams(TeamID),
            FOREIGN KEY (Username) REFERENCES User(Username)
        )
    """)
 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS Tasks (
            TaskID      INTEGER PRIMARY KEY AUTOINCREMENT,
            Title       VARCHAR(100) NOT NULL,
            Description TEXT,
            DueDate     DATE,
            Priority    VARCHAR(10) NOT NULL DEFAULT 'medium',
            Status      VARCHAR(20) NOT NULL DEFAULT 'backlog',
            TeamID      INTEGER NOT NULL,
            AssignedTo  VARCHAR(20),
            CreatedBy   VARCHAR(20) NOT NULL,
            CreatedAt   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (TeamID)     REFERENCES Teams(TeamID),
            FOREIGN KEY (AssignedTo) REFERENCES User(Username),
            FOREIGN KEY (CreatedBy)  REFERENCES User(Username)
        )
    """)
 
    con.commit()
    con.close()
 
init_db()

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", error = None)
    else:
        try:
            password = request.form['Password']
            confirmPassword = request.form['confirmPassword']

            if password != confirmPassword:
                return render_template("signup.html", error="Passwords do not match!")
        
            encoded = password.encode()
            hash = hashlib.sha256(encoded).hexdigest()

            con = sqlite3.connect("Database.db")
            cur = con.cursor()
            cur.execute("INSERT INTO User (Username, Password) VALUES (?,?)",
                            (request.form['Username'],hash))
            con.commit()
            con.close()
            return render_template("success.html")
        except sqlite3.IntegrityError:
            con.close()
            return render_template("signup.html", error = "username already exists!")
            

@app.route("/", methods=["GET", "POST"])


def login():
    if request.method == "GET":
        return render_template("login.html")
    else:
        encoded = request.form['Password'].encode()
        hash = hashlib.sha256(encoded).hexdigest()
        con = sqlite3.connect('Database.db')
        cur = con.cursor()
        cur.execute("SELECT * FROM User WHERE Username=? AND Password=?",
                        (request.form['Username'],hash))
        if len(cur.fetchall()) == 0:
            return render_template('login.html', error="Invalid username or password.")
        else:
            session['Username'] = request.form['Username']
            return render_template("home.html")
        
@app.route("/home")
def home():
    if "Username" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", page="home")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/projects")
def projects():
    if "Username" not in session:
        return redirect(url_for("login"))
    return render_template("projects.html", page="projects")

# deadlines functionality

@app.route("/deadlines")
def deadlines():
    if "Username" not in session:
        return redirect(url_for("login"))
 
    import json
    from datetime import date
 
    today = date.today().isoformat()
 
    con = get_db()
    cur = con.cursor()
 
    # All teams the user belongs to
    cur.execute("""
        SELECT t.TeamID FROM Teams t
        JOIN TeamMembers tm ON t.TeamID = tm.TeamID
        WHERE tm.Username = ?
    """, (session["Username"],))
    team_ids = [row["TeamID"] for row in cur.fetchall()]
 
    if not team_ids:
        con.close()
        return render_template("deadlines.html", page="deadlines",
                               my_tasks=[], team_tasks=[],
                               tasks_json="[]", today=today)
 
    placeholders = ",".join("?" * len(team_ids))
 
    # Tasks assigned to the current user
    cur.execute(f"""
        SELECT tk.*, t.TeamName FROM Tasks tk
        JOIN Teams t ON tk.TeamID = t.TeamID
        WHERE tk.TeamID IN ({placeholders}) AND tk.AssignedTo = ?
        ORDER BY tk.DueDate ASC NULLS LAST
    """, team_ids + [session["Username"]])
    my_tasks = cur.fetchall()
 
    # All tasks across the user's teams
    cur.execute(f"""
        SELECT tk.*, t.TeamName FROM Tasks tk
        JOIN Teams t ON tk.TeamID = t.TeamID
        WHERE tk.TeamID IN ({placeholders})
        ORDER BY tk.DueDate ASC NULLS LAST
    """, team_ids)
    all_tasks = cur.fetchall()
    con.close()
 
    # Team tasks = tasks NOT assigned to the current user
    team_tasks = [t for t in all_tasks
                  if t["AssignedTo"] != session["Username"]]
 
    # Serialize for JS calendar — only tasks with a due date
    tasks_json = json.dumps([{
        "id":       t["TaskID"],
        "title":    t["Title"],
        "due":      t["DueDate"],
        "status":   t["Status"],
        "priority": t["Priority"],
        "assigned": t["AssignedTo"],
        "team":     t["TeamName"],
    } for t in all_tasks if t["DueDate"]])
 
    return render_template("deadlines.html", page="deadlines",
                           my_tasks=my_tasks,
                           team_tasks=team_tasks,
                           tasks_json=tasks_json,
                           today=today)

# task functionality

@app.route("/tasks")
def tasks():
    if "Username" not in session:
        return redirect(url_for("login"))
 
    status_filter = request.args.get("status", "all")
 
    con = get_db()
    cur = con.cursor()
 
    # Get all teams the user belongs to
    cur.execute("""
        SELECT t.TeamID, t.TeamName FROM Teams t
        JOIN TeamMembers tm ON t.TeamID = tm.TeamID
        WHERE tm.Username = ?
    """, (session["Username"],))
    user_teams = cur.fetchall()
 
    team_ids = [t["TeamID"] for t in user_teams]
 
    if not team_ids:
        con.close()
        return render_template("tasks.html", page="tasks",
                               tasks=[], user_teams=[],
                               status_filter=status_filter)
 
    placeholders = ",".join("?" * len(team_ids))
    if status_filter != "all":
        cur.execute(f"""
            SELECT tk.*, t.TeamName FROM Tasks tk
            JOIN Teams t ON tk.TeamID = t.TeamID
            WHERE tk.TeamID IN ({placeholders}) AND tk.Status = ?
            ORDER BY tk.DueDate ASC
        """, team_ids + [status_filter])
    else:
        cur.execute(f"""
            SELECT tk.*, t.TeamName FROM Tasks tk
            JOIN Teams t ON tk.TeamID = t.TeamID
            WHERE tk.TeamID IN ({placeholders})
            ORDER BY tk.DueDate ASC
        """, team_ids)
 
    all_tasks = cur.fetchall()
    con.close()
 
    return render_template("tasks.html", page="tasks",
                           tasks=all_tasks,
                           user_teams=user_teams,
                           status_filter=status_filter)
 
 
@app.route("/tasks/create", methods=["POST"])
def create_task():
    if "Username" not in session:
        return redirect(url_for("login"))
 
    title       = request.form.get("Title", "").strip()
    description = request.form.get("Description", "").strip()
    due_date    = request.form.get("DueDate", "").strip() or None
    priority    = request.form.get("Priority", "medium")
    status      = request.form.get("Status", "backlog")
    team_id     = request.form.get("TeamID")
    assigned_to = request.form.get("AssignedTo", "").strip() or None
 
    if not title or not team_id:
        return redirect(url_for("tasks"))
 
    con = get_db()
    cur = con.cursor()
 
    # Verify user is a member of the team
    cur.execute("SELECT * FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                (team_id, session["Username"]))
    if cur.fetchone() is None:
        con.close()
        return redirect(url_for("tasks"))
 
    # If assigning to someone, verify they're in the team
    if assigned_to:
        cur.execute("SELECT * FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                    (team_id, assigned_to))
        if cur.fetchone() is None:
            assigned_to = None
 
    cur.execute("""
        INSERT INTO Tasks (Title, Description, DueDate, Priority, Status, TeamID, AssignedTo, CreatedBy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, due_date, priority, status, team_id, assigned_to, session["Username"]))
 
    con.commit()
    con.close()
    return redirect(url_for("tasks"))
 
 
@app.route("/tasks/<int:task_id>")
def task_detail(task_id):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    cur.execute("""
        SELECT tk.*, t.TeamName FROM Tasks tk
        JOIN Teams t ON tk.TeamID = t.TeamID
        WHERE tk.TaskID = ?
    """, (task_id,))
    task = cur.fetchone()
 
    if task is None:
        con.close()
        return redirect(url_for("tasks"))
 
    # Verify user is a member of the task's team
    cur.execute("SELECT * FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                (task["TeamID"], session["Username"]))
    if cur.fetchone() is None:
        con.close()
        return redirect(url_for("tasks"))
 
    # Get team members for reassignment dropdown
    cur.execute("SELECT Username FROM TeamMembers WHERE TeamID = ?", (task["TeamID"],))
    team_members = cur.fetchall()
 
    con.close()
    return render_template("task_detail.html", page="tasks",
                           task=task, team_members=team_members)
 
 
@app.route("/tasks/<int:task_id>/update", methods=["POST"])
def update_task(task_id):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    cur.execute("SELECT * FROM Tasks WHERE TaskID = ?", (task_id,))
    task = cur.fetchone()
 
    if task is None:
        con.close()
        return redirect(url_for("tasks"))
 
    cur.execute("SELECT * FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                (task["TeamID"], session["Username"]))
    if cur.fetchone() is None:
        con.close()
        return redirect(url_for("tasks"))
 
    title       = request.form.get("Title", task["Title"]).strip()
    description = request.form.get("Description", task["Description"] or "").strip()
    due_date    = request.form.get("DueDate", task["DueDate"] or "").strip() or None
    priority    = request.form.get("Priority", task["Priority"])
    status      = request.form.get("Status", task["Status"])
    assigned_to = request.form.get("AssignedTo", "").strip() or None
 
    cur.execute("""
        UPDATE Tasks SET Title=?, Description=?, DueDate=?, Priority=?, Status=?, AssignedTo=?
        WHERE TaskID=?
    """, (title, description, due_date, priority, status, assigned_to, task_id))
 
    con.commit()
    con.close()
    return redirect(url_for("task_detail", task_id=task_id))
 
 
@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    cur.execute("SELECT * FROM Tasks WHERE TaskID = ?", (task_id,))
    task = cur.fetchone()
 
    if task:
        cur.execute("SELECT * FROM Teams WHERE TeamID = ? AND OwnerUsername = ?",
                    (task["TeamID"], session["Username"]))
        is_owner = cur.fetchone() is not None
        is_creator = task["CreatedBy"] == session["Username"]
 
        if is_owner or is_creator:
            cur.execute("DELETE FROM Tasks WHERE TaskID = ?", (task_id,))
            con.commit()
 
    con.close()
    return redirect(url_for("tasks"))


# team functionality 

@app.route("/teams")
def teams():
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    # Teams the user owns
    cur.execute("""
        SELECT t.TeamID, t.TeamName,
               (SELECT COUNT(*) FROM TeamMembers WHERE TeamID = t.TeamID) as member_count
        FROM Teams t
        WHERE t.OwnerUsername = ?
    """, (session["Username"],))
    owned_teams = cur.fetchall()
 
    # Teams the user is a member of (but doesn't own)
    cur.execute("""
        SELECT t.TeamID, t.TeamName, t.OwnerUsername,
               (SELECT COUNT(*) FROM TeamMembers WHERE TeamID = t.TeamID) as member_count
        FROM Teams t
        JOIN TeamMembers tm ON t.TeamID = tm.TeamID
        WHERE tm.Username = ? AND t.OwnerUsername != ?
    """, (session["Username"], session["Username"]))
    member_teams = cur.fetchall()
 
    con.close()
    return render_template("teams.html", page="teams",
                           owned_teams=owned_teams,
                           member_teams=member_teams)
@app.route("/teams/create", methods=["POST"])
def create_team():
    if "Username" not in session:
        return redirect(url_for("login"))
 
    team_name = request.form.get("TeamName", "").strip()
    if not team_name:
        return redirect(url_for("teams"))
 
    con = get_db()
    cur = con.cursor()
 
    # Create the team
    cur.execute("INSERT INTO Teams (TeamName, OwnerUsername) VALUES (?, ?)",
                (team_name, session["Username"]))
    team_id = cur.lastrowid
 
    # Add owner as a member with role 'owner'
    cur.execute("INSERT INTO TeamMembers (TeamID, Username, Role) VALUES (?, ?, 'owner')",
                (team_id, session["Username"]))
 
    con.commit()
    con.close()
    return redirect(url_for("team_detail", team_id=team_id))
 
 
@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    # Get team info
    cur.execute("SELECT * FROM Teams WHERE TeamID = ?", (team_id,))
    team = cur.fetchone()
 
    if team is None:
        con.close()
        return redirect(url_for("teams"))
 
    # Check user is a member
    cur.execute("SELECT * FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                (team_id, session["Username"]))
    membership = cur.fetchone()
 
    if membership is None:
        con.close()
        return redirect(url_for("teams"))
 
    # Get all members
    cur.execute("""
        SELECT tm.Username, tm.Role
        FROM TeamMembers tm
        WHERE tm.TeamID = ?
        ORDER BY tm.Role DESC, tm.Username ASC
    """, (team_id,))
    members = cur.fetchall()
 
    con.close()
 
    is_owner = team["OwnerUsername"] == session["Username"]
 
    return render_template("team_detail.html", page="teams",
                           team=team,
                           members=members,
                           is_owner=is_owner,
                           membership=membership)
 
 
@app.route("/teams/<int:team_id>/add", methods=["POST"])
def add_member(team_id):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    # Only owner can add members
    cur.execute("SELECT * FROM Teams WHERE TeamID = ? AND OwnerUsername = ?",
                (team_id, session["Username"]))
    team = cur.fetchone()
 
    if team is None:
        con.close()
        return redirect(url_for("teams"))
 
    username_to_add = request.form.get("Username", "").strip()
    error = None
 
    # Check user exists
    cur.execute("SELECT * FROM User WHERE Username = ?", (username_to_add,))
    user = cur.fetchone()
 
    if user is None:
        error = f"User '{username_to_add}' does not exist."
    else:
        try:
            cur.execute("INSERT INTO TeamMembers (TeamID, Username, Role) VALUES (?, ?, 'member')",
                        (team_id, username_to_add))
            con.commit()
        except sqlite3.IntegrityError:
            error = f"'{username_to_add}' is already in this team."
 
    # Get updated members list for re-render
    cur.execute("SELECT * FROM Teams WHERE TeamID = ?", (team_id,))
    team = cur.fetchone()
    cur.execute("SELECT tm.Username, tm.Role FROM TeamMembers tm WHERE tm.TeamID = ?", (team_id,))
    members = cur.fetchall()
    con.close()
 
    return render_template("team_detail.html", page="teams",
                           team=team,
                           members=members,
                           is_owner=True,
                           membership={"Role": "owner"},
                           error=error)
 
 
@app.route("/teams/<int:team_id>/remove/<username>", methods=["POST"])
def remove_member(team_id, username):
    if "Username" not in session:
        return redirect(url_for("login"))
 
    con = get_db()
    cur = con.cursor()
 
    # Only owner can remove, and can't remove themselves
    cur.execute("SELECT * FROM Teams WHERE TeamID = ? AND OwnerUsername = ?",
                (team_id, session["Username"]))
    team = cur.fetchone()
 
    if team and username != session["Username"]:
        cur.execute("DELETE FROM TeamMembers WHERE TeamID = ? AND Username = ?",
                    (team_id, username))
        con.commit()
 
    con.close()
    return redirect(url_for("team_detail", team_id=team_id))