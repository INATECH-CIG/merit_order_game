from flask import Flask, render_template, request, redirect, url_for, session
import pandas as pd
from bid import Bid
from teacher import Teacher
import os
import yaml

config = yaml.safe_load(open("config.yaml"))

app = Flask(__name__)

if config["randomize_power_plants"]:
    app.secret_key = os.urandom(24)
else:
    app.secret_key = config["secret_key"]


bid = Bid()
teacher = Teacher()

if config["load_storages"]:
    power_plants = pd.read_csv("powerplants_with_storages.csv")
if config["load_demand"]:
    power_plants = pd.read_csv("powerplants_with_demand.csv")
else:
    power_plants = pd.read_csv("powerplants.csv")

# Shuffle the power plants DataFrame
power_plants = power_plants.sample(frac=1).reset_index(drop=True)
# set name as index
power_plants.set_index("name", inplace=True)
assigned_power_plants = []


@app.route("/")
def index():
    if config["clear_sessions"]:
        # Call the function to clear all sessions
        clear_all_sessions()

    return render_template(
        "index.html",
    )


@app.route("/teacher")
def teacher_view():
    if not is_logged_in():
        return redirect(url_for("login"))
    # Teacher's view
    return render_template(
        "teacher.html",
        submitted_bids=bid.bids_to_list(),
        inelastic_demand_level=teacher.demand_level,
        vre_level=teacher.vre_level,
    )


@app.route("/student")
def student_view():
    if "assigned_power_plant" in session:
        assigned_power_plant = session["assigned_power_plant"]
    else:
        if len(assigned_power_plants) == len(power_plants):
            return "All power plants have been assigned."

        available_power_plants = power_plants[
            ~power_plants.index.isin(assigned_power_plants)
        ]
        assigned_power_plant = (
            available_power_plants.sample().reset_index().to_dict(orient="records")[0]
        )
        assigned_power_plants.append(assigned_power_plant["name"])
        session["assigned_power_plant"] = assigned_power_plant

    if "submitted_bid" not in session:
        session["submitted_bid"] = {
            "name": session["assigned_power_plant"]["name"],
            "bid_power": 0,
            "bid_price": 0,
            "bid_type": "sell",
            "profit": 0,
        }

    # Student's bid submission view
    return render_template("student.html", assigned_power_plant=assigned_power_plant)


@app.route("/submit_bid", methods=["POST"])
def submit_bid():
    name = session["assigned_power_plant"]["name"]
    bid_power = abs(float(request.form["bid_power"]))
    bid_price = float(request.form["bid_price"])
    bid_type = request.form["bid_type"]

    # Add the bid to the bid object
    bid.add_bid(name, bid_power, bid_price, bid_type)

    # Store the bid information in a session variable
    session["submitted_bid"] = {
        "name": name,
        "bid_power": bid_power,
        "bid_price": bid_price,
        "bid_type": bid_type,
    }

    return redirect(url_for("student_view"))


@app.route("/set_demand", methods=["POST"])
def set_demand():
    inelastic_demand_level = float(request.form["inelastic_demand_level"])
    bid.add_bid("Inelastic demand", inelastic_demand_level, 500, "buy")

    teacher.demand_level = inelastic_demand_level

    return reload_bids()


@app.route("/set_vre", methods=["POST"])
def set_vre():
    vre_level = float(request.form["vre_level"])
    bid.add_bid("VRE generation", vre_level, 0, "sell")

    teacher.vre_level = vre_level

    return reload_bids()


@app.route("/set_co2_price", methods=["POST"])
def set_co2_price():
    co2_price = float(request.form["co2_price"])
    teacher.co2_price = co2_price

    return reload_bids()


@app.route("/reload_bids", methods=["POST"])
def reload_bids():

    return render_template(
        "teacher.html",
        demand_level=0,
        market_clearing_price=0,
        submitted_bids=bid.bids_to_list(),
        inelastic_demand_level=teacher.demand_level,
        vre_level=teacher.vre_level,
        co2_price=teacher.co2_price,
    )


@app.route("/compute_price", methods=["POST"])
def compute_price():
    bids_as_list = bid.bids_to_list()
    market_clearing_price, accepted_buy, bids_as_list = teacher.compute_price(
        bids_as_list, power_plants
    )

    return render_template(
        "teacher.html",
        demand_level=accepted_buy,
        market_clearing_price=market_clearing_price,
        submitted_bids=bids_as_list,
        inelastic_demand_level=teacher.demand_level,
        vre_level=teacher.vre_level,
    )


@app.route("/clear_bids", methods=["POST"])
def clear_bids():
    bid.clear_bids()
    teacher.reset()
    return redirect(url_for("teacher_view"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Simple check, replace with your actual validation logic
        if username == "teacher" and password == config["teacher_password"]:
            session["user"] = "teacher"
            return redirect(url_for("teacher_view"))
        else:
            return "Invalid username or password"
    return render_template("login.html")


def is_logged_in():
    return "user" in session and session["user"] == "teacher"


def clear_all_sessions():
    session_keys = list(session.keys())  # Get a list of all keys in the session
    for key in session_keys:
        session.pop(key)  # Remove each key from the session


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
