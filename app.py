import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():

    acoes = db.execute("SELECT * FROM shares WHERE user_id = ? AND qtde > 0", session["user_id"])
    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

    if len(acoes) > 0:
        total = db.execute(
            "SELECT sum(price*qtde)+cash AS total FROM shares, users WHERE user_id = ? AND users.id=user_id", session["user_id"])

        for acao in acoes:
            acao["valor"] = usd(acao["price"])
            acao["total"] = usd(acao["price"] * acao["qtde"])
            acao["price"] = usd(acao["price"])

        return render_template("portifolio.html", shares=acoes, cash=usd(user[0]["cash"]), total=usd(total[0]["total"]))

    return render_template("portifolio.html", shares=acoes, cash=usd(user[0]["cash"]), total=usd(user[0]["cash"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            flash("Must provide symbom", "error")

        # Ensure shares was submitted
        elif not request.form.get("shares"):
            flash("Must provide shares", "error")
        else:

            symbol = request.form.get("symbol")
            qtde = request.form.get("shares")
            acao = lookup(symbol)

            if acao and qtde.isdigit() and int(qtde) > 0:
                qtde = int(qtde)

                # Query database for shares
                user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

                if (user[0]["cash"] < acao["price"] * qtde):
                    flash("Insufficient money", "error")
                    return render_template("buy.html")

                acoes = db.execute("SELECT * FROM shares WHERE user_id = ? and symbol = ?", session["user_id"], acao["symbol"])

                cash = user[0]["cash"] - acao["price"] * qtde

                # Ensure shares exists
                if len(acoes) == 0:
                    row = db.execute("INSERT INTO shares (symbol, name, price, qtde, user_id) VALUES(?, ?, ?, ?, ?)",
                                     acao["symbol"], acao["name"], acao["price"], qtde, session["user_id"])

                    db.execute("INSERT INTO history(share_id, price, qtde, date) VALUES(?, ?, ?, datetime())",
                               row, acao["price"], qtde)
                else:
                    db.execute("UPDATE shares SET name = ?, price = ?,  qtde = ? WHERE id = ?",
                               acao["name"], acao["price"], acoes[0]["qtde"] + qtde, acoes[0]["id"])
                    db.execute("INSERT INTO history(share_id, price, qtde, date) VALUES(?, ?, ?, datetime())",
                               acoes[0]["id"], acao["price"], qtde)

                cash = user[0]["cash"] - acao["price"] * qtde

                db.execute("UPDATE users SET cash=? WHERE id=?", cash, session["user_id"])

                flash('Bougth')
                return redirect("/")
            else:
                return apology("Share not found or Invalid share", 400)

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():

    acoes = db.execute(
        "SELECT s.symbol, s.name, h.qtde, h.price, h.date FROM history h LEFT JOIN shares s ON s.id=h.share_id WHERE s.user_id = ? ORDER BY date DESC", session["user_id"])

    for acao in acoes:
        acao["valor"] = usd(acao["price"])

    return render_template("history.html", shares=acoes)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        if symbol:
            quote = lookup(symbol)

            if quote:
                quote["price"] = usd(quote["price"])

                return render_template("quoted.html", quote=quote)
            else:
                return apology("Invalid quote", 400)
        else:
            return apology("Insert a symbol", 400)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)
         # Ensure password was submitted
        elif not confirmation:
            return apology("must provide confirm password", 400)
        elif not password == confirmation:
            return apology("passwords don't match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Ensure username exists
        if len(rows) >= 1:
            return apology("username already exists", 400)

        password = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, password)

        flash('Registred')
        return render_template("login.html")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    acoes = db.execute("SELECT * FROM shares WHERE user_id = ? AND qtde > 0", session["user_id"])

    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            flash("Must provide symbol", "error")

        # Ensure shares was submitted
        elif not request.form.get("shares"):
            flash("Must provide shares", "error")
        else:

            symbol = request.form.get("symbol")
            qtde = request.form.get("shares")

            if symbol and qtde.isdigit() and int(qtde) > 0:
                qtde = int(qtde)

                a = db.execute("SELECT * FROM shares WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)

                if (qtde > a[0]["qtde"]):
                    return apology("Invalid number of shares", 400)
                else:
                    acao = lookup(symbol)
                    user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
                    db.execute("UPDATE shares SET price = ?,  qtde = ? WHERE id = ?",
                               acao["price"], a[0]["qtde"] - qtde, a[0]["id"])
                    db.execute("INSERT INTO history(share_id, price, qtde, date) VALUES(?, ?, ?, datetime())",
                               a[0]["id"], acao["price"], -qtde)
                    db.execute("UPDATE users SET cash = ? WHERE id = ?",
                               (user[0]["cash"] + (qtde * acao["price"])), session["user_id"])
                    flash("Sold")
            else:
                return apology("Invalid input or symbol not found", 400)
            return redirect("/")

    acoes = db.execute("SELECT * FROM shares WHERE user_id = ? AND qtde > 0", session["user_id"])

    return render_template("sell.html", shares=acoes)
