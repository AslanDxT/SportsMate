from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify
)

from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db


app = Flask(__name__)
app.secret_key = "sportsmate-development-secret-key"


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def current_user():
    if "user_id" not in session:
        return None

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    db.close()

    return user


def login_required():
    return "user_id" in session


def get_unread_notifications():
    if not login_required():
        return 0

    db = get_db()

    result = db.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE user_id = ? AND is_read = 0
    """, (session["user_id"],)).fetchone()

    db.close()

    return result["count"]


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "notification_count": get_unread_notifications()
    }


# --------------------------------------------------
# Public pages
# --------------------------------------------------

@app.route("/")
def index():
    if login_required():
        return redirect(url_for("dashboard"))

    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        db.close()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):
            session.clear()
            session["user_id"] = user["id"]

            flash("Welcome back!", "success")

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    db = get_db()

    sports = db.execute(
        "SELECT * FROM sports ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )
        location = request.form.get("location", "").strip()
        skill_level = request.form.get(
            "skill_level",
            "Beginner"
        )
        sport_id = request.form.get("sport_id")

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            db.close()
            return render_template(
                "register.html",
                sports=sports
            )

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            db.close()
            return render_template(
                "register.html",
                sports=sports
            )

        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error"
            )
            db.close()
            return render_template(
                "register.html",
                sports=sports
            )

        existing = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            flash("This email is already registered.", "error")
            db.close()
            return render_template(
                "register.html",
                sports=sports
            )

        cursor = db.execute("""
            INSERT INTO users
            (name, email, password_hash, location, skill_level)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            email,
            generate_password_hash(password),
            location,
            skill_level
        ))

        user_id = cursor.lastrowid

        if sport_id:
            db.execute("""
                INSERT INTO user_sports(user_id, sport_id)
                VALUES (?, ?)
            """, (user_id, sport_id))

        db.commit()
        db.close()

        session["user_id"] = user_id

        flash(
            "Your SportsMate account has been created!",
            "success"
        )

        return redirect(url_for("dashboard"))

    db.close()

    return render_template(
        "register.html",
        sports=sports
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    activities = db.execute("""
        SELECT
            activities.*,
            sports.name AS sport_name,
            users.name AS creator_name,
            (
                SELECT COUNT(*)
                FROM activity_participants
                WHERE activity_id = activities.id
            ) AS participant_count
        FROM activities
        JOIN sports ON activities.sport_id = sports.id
        JOIN users ON activities.creator_id = users.id
        ORDER BY activities.date, activities.time
        LIMIT 6
    """).fetchall()

    db.close()

    return render_template(
        "dashboard.html",
        activities=activities
    )


# --------------------------------------------------
# Activities
# --------------------------------------------------

@app.route("/activities")
def activities():

    if not login_required():
        return redirect(url_for("login"))

    sport = request.args.get("sport", "")
    location = request.args.get("location", "")
    skill = request.args.get("skill", "")

    db = get_db()

    sports = db.execute(
        "SELECT * FROM sports ORDER BY name"
    ).fetchall()

    query = """
        SELECT
            activities.*,
            sports.name AS sport_name,
            users.name AS creator_name,
            (
                SELECT COUNT(*)
                FROM activity_participants
                WHERE activity_id = activities.id
            ) AS participant_count
        FROM activities
        JOIN sports ON activities.sport_id = sports.id
        JOIN users ON activities.creator_id = users.id
        WHERE 1=1
    """

    params = []

    if sport:
        query += " AND sports.name = ?"
        params.append(sport)

    if location:
        query += " AND activities.location LIKE ?"
        params.append(f"%{location}%")

    if skill:
        query += " AND activities.skill_level = ?"
        params.append(skill)

    query += " ORDER BY activities.date, activities.time"

    activities_list = db.execute(
        query,
        params
    ).fetchall()

    db.close()

    return render_template(
        "activities.html",
        activities=activities_list,
        sports=sports,
        selected_sport=sport,
        selected_location=location,
        selected_skill=skill
    )


@app.route("/activities/create", methods=["GET", "POST"])
def create_activity():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    sports = db.execute(
        "SELECT * FROM sports ORDER BY name"
    ).fetchall()

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        sport_id = request.form.get("sport_id")
        description = request.form.get(
            "description",
            ""
        ).strip()
        date = request.form.get("date")
        time = request.form.get("time")
        location = request.form.get(
            "location",
            ""
        ).strip()
        skill_level = request.form.get(
            "skill_level",
            "Beginner"
        )
        max_participants = request.form.get(
            "max_participants",
            10
        )

        if not title or not sport_id or not date or not time or not location:
            flash(
                "Please fill in all required fields.",
                "error"
            )

            db.close()

            return render_template(
                "create_activity.html",
                sports=sports
            )

        try:
            max_participants = int(max_participants)

            if max_participants < 2:
                raise ValueError

        except ValueError:
            flash(
                "Maximum participants must be at least 2.",
                "error"
            )

            db.close()

            return render_template(
                "create_activity.html",
                sports=sports
            )

        cursor = db.execute("""
            INSERT INTO activities
            (
                creator_id,
                title,
                sport_id,
                description,
                date,
                time,
                location,
                skill_level,
                max_participants
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            title,
            sport_id,
            description,
            date,
            time,
            location,
            skill_level,
            max_participants
        ))

        activity_id = cursor.lastrowid

        db.execute("""
            INSERT INTO activity_participants
            (activity_id, user_id)
            VALUES (?, ?)
        """, (
            activity_id,
            session["user_id"]
        ))

        db.commit()
        db.close()

        flash(
            "Activity created successfully!",
            "success"
        )

        return redirect(
            url_for(
                "activity_detail",
                activity_id=activity_id
            )
        )

    db.close()

    return render_template(
        "create_activity.html",
        sports=sports
    )


@app.route("/activities/<int:activity_id>")
def activity_detail(activity_id):

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    activity = db.execute("""
        SELECT
            activities.*,
            sports.name AS sport_name,
            users.name AS creator_name
        FROM activities
        JOIN sports
            ON activities.sport_id = sports.id
        JOIN users
            ON activities.creator_id = users.id
        WHERE activities.id = ?
    """, (activity_id,)).fetchone()

    if not activity:
        db.close()
        return render_template("404.html"), 404

    participants = db.execute("""
        SELECT users.*
        FROM users
        JOIN activity_participants
            ON users.id = activity_participants.user_id
        WHERE activity_participants.activity_id = ?
    """, (activity_id,)).fetchall()

    joined = db.execute("""
        SELECT 1
        FROM activity_participants
        WHERE activity_id = ?
        AND user_id = ?
    """, (
        activity_id,
        session["user_id"]
    )).fetchone()

    db.close()

    return render_template(
        "activity_detail.html",
        activity=activity,
        participants=participants,
        joined=bool(joined)
    )


@app.route("/activities/<int:activity_id>/join", methods=["POST"])
def join_activity(activity_id):

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    activity = db.execute(
        "SELECT * FROM activities WHERE id = ?",
        (activity_id,)
    ).fetchone()

    if not activity:
        db.close()
        return render_template("404.html"), 404

    existing = db.execute("""
        SELECT 1
        FROM activity_participants
        WHERE activity_id = ? AND user_id = ?
    """, (
        activity_id,
        session["user_id"]
    )).fetchone()

    if existing:
        flash(
            "You already joined this activity.",
            "error"
        )

        db.close()

        return redirect(
            url_for(
                "activity_detail",
                activity_id=activity_id
            )
        )

    count = db.execute("""
        SELECT COUNT(*) AS count
        FROM activity_participants
        WHERE activity_id = ?
    """, (activity_id,)).fetchone()["count"]

    if count >= activity["max_participants"]:
        flash(
            "This activity is already full.",
            "error"
        )

        db.close()

        return redirect(
            url_for(
                "activity_detail",
                activity_id=activity_id
            )
        )

    db.execute("""
        INSERT INTO activity_participants
        (activity_id, user_id)
        VALUES (?, ?)
    """, (
        activity_id,
        session["user_id"]
    ))

    if activity["creator_id"] != session["user_id"]:
        user = db.execute(
            "SELECT name FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        db.execute("""
            INSERT INTO notifications
            (user_id, type, message, related_id)
            VALUES (?, ?, ?, ?)
        """, (
            activity["creator_id"],
            "activity",
            f"{user['name']} joined your activity.",
            activity_id
        ))

    db.commit()
    db.close()

    flash(
        "You joined the activity!",
        "success"
    )

    return redirect(
        url_for(
            "activity_detail",
            activity_id=activity_id
        )
    )


@app.route("/activities/<int:activity_id>/leave", methods=["POST"])
def leave_activity(activity_id):

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    activity = db.execute(
        "SELECT * FROM activities WHERE id = ?",
        (activity_id,)
    ).fetchone()

    if activity and activity["creator_id"] != session["user_id"]:

        db.execute("""
            DELETE FROM activity_participants
            WHERE activity_id = ? AND user_id = ?
        """, (
            activity_id,
            session["user_id"]
        ))

        db.commit()

        flash(
            "You left the activity.",
            "success"
        )

    else:
        flash(
            "The activity creator cannot leave their own activity.",
            "error"
        )

    db.close()

    return redirect(
        url_for(
            "activity_detail",
            activity_id=activity_id
        )
    )


# --------------------------------------------------
# SportsMates
# --------------------------------------------------

@app.route("/mates")
def mates():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    users = db.execute("""
        SELECT *
        FROM users
        WHERE id != ?
        ORDER BY name
    """, (session["user_id"],)).fetchall()

    result = []

    for user in users:

        sports = db.execute("""
            SELECT sports.name
            FROM sports
            JOIN user_sports
                ON sports.id = user_sports.sport_id
            WHERE user_sports.user_id = ?
        """, (user["id"],)).fetchall()

        result.append({
            "user": user,
            "sports": [s["name"] for s in sports]
        })

    db.close()

    return render_template(
        "mates.html",
        mates=result
    )


# --------------------------------------------------
# Profiles
# --------------------------------------------------

@app.route("/profile/<int:user_id>")
def profile(user_id):

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        db.close()
        return render_template("404.html"), 404

    sports = db.execute("""
        SELECT sports.name
        FROM sports
        JOIN user_sports
            ON sports.id = user_sports.sport_id
        WHERE user_sports.user_id = ?
    """, (user_id,)).fetchall()

    created_activities = db.execute("""
        SELECT
            activities.*,
            sports.name AS sport_name
        FROM activities
        JOIN sports
            ON activities.sport_id = sports.id
        WHERE creator_id = ?
        ORDER BY date, time
    """, (user_id,)).fetchall()

    db.close()

    return render_template(
        "profile.html",
        user=user,
        sports=[s["name"] for s in sports],
        created_activities=created_activities
    )


@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    sports = db.execute(
        "SELECT * FROM sports ORDER BY name"
    ).fetchall()

    selected_sports = db.execute("""
        SELECT sport_id
        FROM user_sports
        WHERE user_id = ?
    """, (session["user_id"],)).fetchall()

    selected_ids = [row["sport_id"] for row in selected_sports]

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        location = request.form.get(
            "location",
            ""
        ).strip()
        bio = request.form.get(
            "bio",
            ""
        ).strip()
        skill_level = request.form.get(
            "skill_level",
            "Beginner"
        )
        availability = request.form.get(
            "availability",
            ""
        ).strip()

        sport_ids = request.form.getlist("sports")

        db.execute("""
            UPDATE users
            SET name = ?,
                location = ?,
                bio = ?,
                skill_level = ?,
                availability = ?
            WHERE id = ?
        """, (
            name,
            location,
            bio,
            skill_level,
            availability,
            session["user_id"]
        ))

        db.execute("""
            DELETE FROM user_sports
            WHERE user_id = ?
        """, (session["user_id"],))

        for sport_id in sport_ids:
            db.execute("""
                INSERT INTO user_sports
                (user_id, sport_id)
                VALUES (?, ?)
            """, (
                session["user_id"],
                sport_id
            ))

        db.commit()
        db.close()

        flash(
            "Profile updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "profile",
                user_id=session["user_id"]
            )
        )

    db.close()

    return render_template(
        "edit_profile.html",
        user=user,
        sports=sports,
        selected_ids=selected_ids
    )


# --------------------------------------------------
# Connections
# --------------------------------------------------

@app.route("/connect/<int:user_id>", methods=["POST"])
def connect(user_id):

    if not login_required():
        return redirect(url_for("login"))

    if user_id == session["user_id"]:
        flash(
            "You cannot connect with yourself.",
            "error"
        )
        return redirect(url_for("mates"))

    db = get_db()

    existing = db.execute("""
        SELECT *
        FROM connections
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
    """, (
        session["user_id"],
        user_id,
        user_id,
        session["user_id"]
    )).fetchone()

    if existing:
        flash(
            "A connection already exists.",
            "error"
        )
        db.close()
        return redirect(url_for("mates"))

    db.execute("""
        INSERT INTO connections
        (sender_id, receiver_id, status)
        VALUES (?, ?, 'pending')
    """, (
        session["user_id"],
        user_id
    ))

    sender = db.execute(
        "SELECT name FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    db.execute("""
        INSERT INTO notifications
        (user_id, type, message, related_id)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        "connection",
        f"{sender['name']} wants to connect with you.",
        session["user_id"]
    ))

    db.commit()
    db.close()

    flash(
        "Connection request sent.",
        "success"
    )

    return redirect(url_for("mates"))


@app.route("/connections")
def connections():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    incoming = db.execute("""
        SELECT
            connections.*,
            users.name,
            users.location,
            users.bio
        FROM connections
        JOIN users
            ON users.id = connections.sender_id
        WHERE
            connections.receiver_id = ?
            AND connections.status = 'pending'
    """, (
        session["user_id"],
    )).fetchall()

    accepted = db.execute("""
        SELECT
            connections.id,
            connections.sender_id,
            connections.receiver_id,
            users.name,
            users.location,
            users.bio
        FROM connections
        JOIN users
            ON users.id =
            CASE
                WHEN connections.sender_id = ?
                THEN connections.receiver_id
                ELSE connections.sender_id
            END
        WHERE
            (connections.sender_id = ?
             OR connections.receiver_id = ?)
            AND connections.status = 'accepted'
    """, (
        session["user_id"],
        session["user_id"],
        session["user_id"]
    )).fetchall()

    db.close()

    return render_template(
        "connections.html",
        incoming=incoming,
        accepted=accepted
    )


@app.route(
    "/connections/<int:connection_id>/<action>",
    methods=["POST"]
)
def connection_action(connection_id, action):

    if not login_required():
        return redirect(url_for("connections"))

    db = get_db()

    connection = db.execute("""
        SELECT *
        FROM connections
        WHERE id = ?
    """, (connection_id,)).fetchone()

    if not connection:
        db.close()
        return redirect(url_for("connections"))

    if connection["receiver_id"] != session["user_id"]:
        db.close()
        return render_template("403.html"), 403

    if action == "accept":
        db.execute("""
            UPDATE connections
            SET status = 'accepted'
            WHERE id = ?
        """, (connection_id,))

        db.execute("""
            INSERT INTO notifications
            (user_id, type, message, related_id)
            VALUES (?, ?, ?, ?)
        """, (
            connection["sender_id"],
            "connection",
            "Your connection request was accepted.",
            connection_id
        ))

        flash(
            "Connection accepted.",
            "success"
        )

    elif action == "reject":
        db.execute("""
            DELETE FROM connections
            WHERE id = ?
        """, (connection_id,))

        flash(
            "Connection request rejected.",
            "success"
        )

    db.commit()
    db.close()

    return redirect(url_for("connections"))


# --------------------------------------------------
# Messages
# --------------------------------------------------

@app.route("/messages")
def messages():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    users = db.execute("""
        SELECT DISTINCT
            users.id,
            users.name,
            users.location
        FROM users
        JOIN connections
            ON (
                connections.sender_id = users.id
                OR connections.receiver_id = users.id
            )
        WHERE
            connections.status = 'accepted'
            AND users.id != ?
    """, (
        session["user_id"],
    )).fetchall()

    db.close()

    return render_template(
        "messages.html",
        users=users
    )


@app.route("/messages/<int:user_id>", methods=["GET", "POST"])
def conversation(user_id):

    if not login_required():
        return redirect(url_for("messages"))

    if user_id == session["user_id"]:
        return redirect(url_for("messages"))

    db = get_db()

    connection = db.execute("""
        SELECT *
        FROM connections
        WHERE
            status = 'accepted'
            AND (
                (sender_id = ? AND receiver_id = ?)
                OR
                (sender_id = ? AND receiver_id = ?)
            )
    """, (
        session["user_id"],
        user_id,
        user_id,
        session["user_id"]
    )).fetchone()

    if not connection:
        db.close()
        flash(
            "You can only message your SportsMates.",
            "error"
        )
        return redirect(url_for("messages"))

    if request.method == "POST":

        message = request.form.get(
            "message",
            ""
        ).strip()

        if message:
            db.execute("""
                INSERT INTO messages
                (sender_id, receiver_id, message)
                VALUES (?, ?, ?)
            """, (
                session["user_id"],
                user_id,
                message
            ))

            sender = db.execute(
                "SELECT name FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()

            db.execute("""
                INSERT INTO notifications
                (user_id, type, message, related_id)
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                "message",
                f"{sender['name']} sent you a message.",
                session["user_id"]
            ))

            db.commit()

        db.close()

        return redirect(
            url_for(
                "conversation",
                user_id=user_id
            )
        )

    other_user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    messages_list = db.execute("""
        SELECT *
        FROM messages
        WHERE
            (sender_id = ? AND receiver_id = ?)
            OR
            (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at ASC
    """, (
        session["user_id"],
        user_id,
        user_id,
        session["user_id"]
    )).fetchall()

    db.execute("""
        UPDATE messages
        SET is_read = 1
        WHERE sender_id = ?
        AND receiver_id = ?
    """, (
        user_id,
        session["user_id"]
    ))

    db.commit()
    db.close()

    return render_template(
        "conversation.html",
        other_user=other_user,
        messages=messages_list
    )


# --------------------------------------------------
# Notifications
# --------------------------------------------------

@app.route("/notifications")
def notifications():

    if not login_required():
        return redirect(url_for("login"))

    db = get_db()

    notifications_list = db.execute("""
        SELECT *
        FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (
        session["user_id"],
    )).fetchall()

    db.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE user_id = ?
    """, (
        session["user_id"],
    ))

    db.commit()
    db.close()

    return render_template(
        "notifications.html",
        notifications=notifications_list
    )


# --------------------------------------------------
# PWA
# --------------------------------------------------

@app.route("/service-worker.js")
def service_worker():
    return app.send_static_file("service-worker.js")


# --------------------------------------------------
# Errors
# --------------------------------------------------

@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(error):
    return render_template("500.html"), 500


# --------------------------------------------------
# Start
# --------------------------------------------------

if __name__ == "__main__":
    init_db()

    app.run(
        debug=True,
        host="0.0.0.0",
        port=5000
    )