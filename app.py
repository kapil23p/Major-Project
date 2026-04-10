import os
from dotenv import load_dotenv
load_dotenv()

import requests

def fetch_cf(handle):
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    try:
        res = requests.get(url).json()
        if res["status"] == "OK":
            rating = res["result"][0].get("rating", 0)
            return rating
    except:
        pass
    return 0

def fetch_lc(username):
    url = "https://leetcode.com/graphql"
    query = {
        "query": """
        query getUserProfile($username: String!) {
          matchedUser(username: $username) {
            submitStatsGlobal {
              acSubmissionNum {
                count
              }
            }
          }
        }
        """,
        "variables": {"username": username}
    }
    try:
        res = requests.post(url, json=query).json()
        return res["data"]["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"][0]["count"]
    except:
        return 0

def fetch_cc(handle):
    from bs4 import BeautifulSoup
    url = f"https://www.codechef.com/users/{handle}"
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        rating = soup.find("div", class_="rating-number").text
        return int(rating)
    except:
        return 0


def calculate_score(user):
    print("CALCULATING SCORE...")
    score = 0

    if user.cf_handle:
        cf = fetch_cf(user.cf_handle)
        print("CF FETCH:", cf)
        cf = int(cf or 0)
        user.cf_rating = cf
        if cf > 800:
            score += ((cf - 800) ** 2) // 10

    if user.cc_handle:
        cc = fetch_cc(user.cc_handle)
        print("CC FETCH:", cc)
        cc = int(cc or 0)
        user.cc_rating = cc
        if cc > 1200:
            score += ((cc - 1200) ** 2) // 10

    if user.lc_handle:
        lc = fetch_lc(user.lc_handle)
        print("LC FETCH:", lc)
        lc = int(lc or 0)
        user.lc_solved = lc
        score += lc * 10

    user.total_score = score + (user.problem_score or 0) + (user.crt_score or 0)
    print("FINAL SCORE:", user.total_score)
    db.session.commit()


def platform_score_from_ratings(user):
    """Derive platform score from already-stored ratings (no external API calls)."""
    score = 0
    cf = user.cf_rating or 0
    cc = user.cc_rating or 0
    lc = user.lc_solved or 0
    if cf > 800:
        score += ((cf - 800) ** 2) // 10
    if cc > 1200:
        score += ((cc - 1200) ** 2) // 10
    score += lc * 10
    return score


from flask import Flask, jsonify, render_template, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from authlib.integrations.flask_client import OAuth
from judge import run_code

app = Flask(__name__)

# ================= CONFIG =================
app.config['SECRET_KEY'] = "supersecret"
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///crt.db')
uri = os.getenv('DATABASE_URL', 'sqlite:///crt.db')
if uri.startswith('postgres://'):
    uri = uri.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ================= MODELS =================

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    cf_handle = db.Column(db.String(100))
    cc_handle = db.Column(db.String(100))
    lc_handle = db.Column(db.String(100))
    crt_score = db.Column(db.Integer, default=0)
    problem_score = db.Column(db.Integer, default=0)
    total_score = db.Column(db.Integer, default=0)
    cf_rating = db.Column(db.Integer, default=0)
    cc_rating = db.Column(db.Integer, default=0)
    lc_solved = db.Column(db.Integer, default=0)


class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    input_example = db.Column(db.String(200))
    output_example = db.Column(db.String(200))
    correct_answer = db.Column(db.String(200))
    points = db.Column(db.Integer, default=20)
    hidden_inputs = db.Column(db.Text)
    hidden_outputs = db.Column(db.Text)
    constraints = db.Column(db.Text)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    problem_id = db.Column(db.Integer)
    is_correct = db.Column(db.Boolean)


# ================= LOGIN =================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/authorize")
def authorize():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    email = user_info["email"]
    name = user_info["name"]

    user = User.query.filter_by(email=email).first()

    if not user:
        user = User(name=name, email=email)
        db.session.add(user)
        db.session.commit()

    # Grant admin on login if this is the designated admin email
    if email == "pavankapil177@gmail.com" and not user.is_admin:
        user.is_admin = True
        db.session.commit()

    login_user(user)
    return redirect("/dashboard")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")


# ================= ADMIN =================

@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        return "Access Denied"
    users = User.query.order_by(User.total_score.desc()).all()
    return render_template("admin.html", users=users)


@app.route("/make_admin/<int:user_id>")
@login_required
def make_admin_user(user_id):
    if not current_user.is_admin:
        return "Access Denied"
    user = User.query.get(user_id)
    user.is_admin = True
    db.session.commit()
    return redirect("/admin")


@app.route("/analytics")
@login_required
def analytics():
    if not current_user.is_admin:
        return "Access Denied"

    users = User.query.order_by(User.total_score.desc()).all()
    names = [user.name for user in users]
    scores = [user.total_score for user in users]

    return render_template("analytics.html", names=names, scores=scores)


# ================= PROFILE =================

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        current_user.cf_handle = request.form.get("cf")
        current_user.cc_handle = request.form.get("cc")
        current_user.lc_handle = request.form.get("lc")
        db.session.commit()
        return redirect("/dashboard")
    return render_template("edit_profile.html", user=current_user)


# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    calculate_score(current_user)
    return render_template("dashboard.html", user=current_user)


@app.route("/leaderboard")
@login_required
def leaderboard():
    users = User.query.order_by(User.total_score.desc()).all()
    return render_template("leaderboard.html", users=users)


# ================= PROBLEMS =================

@app.route("/problems")
@login_required
def problems():
    all_problems = Problem.query.all()
    solved = {
        s.problem_id for s in Submission.query.filter_by(
            user_id=current_user.id,
            is_correct=True
        ).all()
    }
    return render_template("internal_problems.html", problems=all_problems, solved=solved)


@app.route("/problem/<int:id>", methods=["GET", "POST"])
@login_required
def solve_problem(id):
    problem = Problem.query.get_or_404(id)

    result = None
    output = None
    success = False
    passed = 0
    total_tests = 0

    if request.method == "POST":
        code = request.form.get("code")
        language = request.form.get("language")

        # Run on sample input for display
        res = run_code(language, code, problem.input_example)
        output = res.get("stdout")
        if not output:
            output = res.get("stderr") or res.get("error") or "No Output"

        # Hidden test cases
        inputs = problem.hidden_inputs.split("|")
        outputs = problem.hidden_outputs.split("|")
        total_tests = len(inputs)
        passed = 0

        for i in range(total_tests):
            res = run_code(language, code, inputs[i])
            out = res.get("stdout", "").strip()
            if out == outputs[i].strip():
                passed += 1

        correct = (passed == total_tests)

        # Prevent double scoring
        already_solved = Submission.query.filter_by(
            user_id=current_user.id,
            problem_id=problem.id,
            is_correct=True
        ).first()

        if correct and not already_solved:
            current_user.problem_score += problem.points
            # BUG FIX #4: include stored platform scores so total stays correct
            current_user.total_score = (
                platform_score_from_ratings(current_user)
                + (current_user.problem_score or 0)
                + (current_user.crt_score or 0)
            )
            db.session.commit()

        result = correct
        success = correct

        submission = Submission(
            user_id=current_user.id,
            problem_id=problem.id,
            is_correct=correct
        )
        db.session.add(submission)
        db.session.commit()

    return render_template(
        "problem_detail.html",
        problem=problem,
        result=result,
        output=output,
        success=success,
        passed=passed,
        total_tests=total_tests
    )


# ================= AI INTERACTION =============

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

@app.route("/ai_help", methods=["POST"])
@login_required
def ai_help():
    data = request.get_json()
    code = data.get("code", "")
    problem = data.get("problemDesc", "")  # key renamed in JS to avoid linter clash

    try:
        user_msg = ""
        if problem:
            user_msg += f"Problem Statement:\n{problem}\n\n"
        if code and code.strip() != "# Write your code here":
            user_msg += f"My Code:\n{code}\n\n"
        user_msg += "Please analyze my code, point out errors, and give hints to solve the problem without revealing the full solution."

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful coding assistant for competitive programming. You receive a problem statement and the user's code. Help them fix bugs and understand the solution approach with hints, not full answers."},
                {"role": "user", "content": user_msg}
            ]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)})


# ================= RUN BUTTON =================

@app.route('/run_code', methods=['POST'])
def run_code_route():
    data = request.get_json()
    language = data['language']
    code = data['code']
    stdin = data.get('stdin')
    problem_id = data.get('problem_id')

    problem = None
    if problem_id:
        problem = Problem.query.get(problem_id)

    if not stdin:
        stdin = problem.input_example if problem else ""

    result = run_code(language, code, stdin)
    return jsonify(result)


# ================= INIT =================
# Runs under both gunicorn and direct python
with app.app_context():
    db.create_all()
    admin_user = User.query.filter_by(email="pavankapil177@gmail.com").first()
    if admin_user and not admin_user.is_admin:
        admin_user.is_admin = True
        db.session.commit()
    if Problem.query.count() == 0:
        db.session.add_all([
            Problem(
                title="Addition of Two Numbers",
                description="Read two integers and print their sum.",
                input_example="2 3",
                output_example="5",
                correct_answer="5",
                constraints="1 ≤ a, b ≤ 10^6",
                hidden_inputs="1 2|3 4|5 6|10 20|100 200|7 8|9 10|50 50|123 456|11 22|13 14|15 16|17 18|19 20|21 22|23 24|25 26|27 28|29 30|31 32",
                hidden_outputs="3|7|11|30|300|15|19|100|579|33|27|31|35|39|43|47|51|55|59|63"
            ),
            Problem(
                title="Multiply Two Numbers",
                description="Read two integers and print their product.",
                input_example="4 5",
                output_example="20",
                constraints="1 ≤ a, b ≤ 10^4",
                hidden_inputs="1 2|3 4|5 6|2 3|10 10|7 8|9 9|12 12|11 11|6 7|8 9|10 11|12 13|14 15|16 17|18 19|20 21|22 23|24 25|26 27",
                hidden_outputs="2|12|30|6|100|56|81|144|121|42|72|110|156|210|272|342|420|506|600|702"
            ),
            Problem(
                title="Square of a Number",
                description="Read an integer and print its square.",
                input_example="6",
                output_example="36",
                constraints="1 ≤ n ≤ 10^5",
                hidden_inputs="1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20",
                hidden_outputs="1|4|9|16|25|36|49|64|81|100|121|144|169|196|225|256|289|324|361|400"
            )
        ])
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
