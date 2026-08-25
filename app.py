from flask import Flask, render_template_string, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TRACKED_TEAMS = [
    "New York Yankees", "Boston Red Sox", "Texas Rangers", 
    "Baltimore Orioles", "Detroit Tigers", "Minnesota Twins", 
    "Cleveland Guardians", "Seattle Mariners", "Toronto Blue Jays", "Houston Astros"
]

OUT_OF_CONTENTION_TEAMS = [
    "Kansas City Royals", "Los Angeles Angels", "Sacramento Athletics"
]

def normalize_team_name(api_name):
    mapping = {
        "Yankees": "New York Yankees", "New York Yankees": "New York Yankees",
        "Red Sox": "Boston Red Sox", "Boston Red Sox": "Boston Red Sox",
        "Rangers": "Texas Rangers", "Texas Rangers": "Texas Rangers",
        "Orioles": "Baltimore Orioles", "Baltimore Orioles": "Baltimore Orioles",
        "Tigers": "Detroit Tigers", "Detroit Tigers": "Detroit Tigers",
        "Twins": "Minnesota Twins", "Minnesota Twins": "Minnesota Twins",
        "Guardians": "Cleveland Guardians", "Cleveland Guardians": "Cleveland Guardians",
        "Mariners": "Seattle Mariners", "Seattle Mariners": "Seattle Mariners",
        "Blue Jays": "Toronto Blue Jays", "Toronto Blue Jays": "Toronto Blue Jays",
        "Royals": "Kansas City Royals", "Kansas City Royals": "Kansas City Royals",
        "Angels": "Los Angeles Angels", "Los Angeles Angels": "Los Angeles Angels",
        "Athletics": "Sacramento Athletics", "Oakland Athletics": "Sacramento Athletics",
        "Sacramento Athletics": "Sacramento Athletics",
        "Astros": "Houston Astros", "Houston Astros": "Houston Astros",
        "Indians": "Cleveland Guardians",
        "Rays": "Tampa Bay Rays", "Tampa Bay Rays": "Tampa Bay Rays",
        "White Sox": "Chicago White Sox", "Chicago White Sox": "Chicago White Sox"
    }
    return mapping.get(api_name, api_name)

def get_nickname(full_name):
    """Extracts just the team nickname (e.g., 'Toronto Blue Jays' -> 'Blue Jays')"""
    parts = full_name.split()
    if len(parts) > 1:
        if parts[-2] in ["Red", "Blue", "White", "Boston", "Kansas", "Los", "New"]:
            if full_name in ["Boston Red Sox", "Toronto Blue Jays", "Chicago White Sox", "Los Angeles Angels", "Kansas City Royals"]:
                return " ".join(parts[-2:])
    return parts[-1]

def get_data_dict():
    current_year = datetime.today().year

    # 4 AM ET Rollover Check (Explicitly bound to Eastern Time)
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.hour < 4:
        target_date = now - timedelta(days=1)
    else:
        target_date = now
    today = target_date.strftime('%Y-%m-%d')
    
    standings = []
    division_leaders = []
    out_of_contention = []
    rankings_map = {}
    leaders_ranking = {}
    
    try:
        # --- 1. Fetch Division Standings ---
        rs_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}"
        res_rs = requests.get(rs_url, headers=HEADERS).json()

        rank_leaders = 0
        
        if 'records' in res_rs:
            for record in res_rs['records']:
                team_records = record.get('teamRecords', [])
                if len(team_records) >= 2:
                    leader_data = team_records[0]
                    raw_leader_name = leader_data.get('team', {}).get('name', '')
                    leader_name = normalize_team_name(raw_leader_name)
                    l_wins = int(leader_data.get('wins', 0))
                    l_losses = int(leader_data.get('losses', 0))
                    
                    second_data = team_records[1]
                    s_wins = int(second_data.get('wins', 0))
                    s_losses = int(second_data.get('losses', 0))
                    
                    ga_val = ((l_wins - s_wins) + (s_losses - l_losses)) / 2.0
                    if ga_val.is_integer():
                        ga_str = f"+{int(ga_val)}"
                    else:
                        ga_str = f"+{ga_val}"
                    if ga_val == 0:
                        ga_str = "-"

                    rank_leaders += 1

                    if not any(d['team'] == leader_name for d in division_leaders):
                        division_leaders.append({
                            "team": leader_name,
                            "rank": rank_leaders,
                            "record": f"{l_wins}-{l_losses}",
                            "ga": ga_str
                        })
                        leaders_ranking[leader_name] = rank_leaders

                for team_data in team_records:
                    raw_name = team_data.get('team', {}).get('name', '')
                    t_name = normalize_team_name(raw_name)
                    wins = int(team_data.get('wins', 0))
                    losses = int(team_data.get('losses', 0))
                    gb = team_data.get('wildCardGamesBack', '-')
                    rank_str = str(team_data.get('wildCardRank', '99'))
                    rank = int(rank_str) if rank_str.isdigit() else 99
                            
                    if t_name in OUT_OF_CONTENTION_TEAMS:
                        if not any(o['team'] == t_name for o in out_of_contention):
                            out_of_contention.append({
                                "team": t_name,
                                "rank": rank,
                                "record": f"{wins}-{losses}",
                                "gb": gb
                            })

        # --- 2. Fetch Wild Card Standings ---
        wc_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}&standingsTypes=wildCard"
        res_wc = requests.get(wc_url, headers=HEADERS).json()
        
        if 'records' in res_wc:
            for record in res_wc['records']:
                for team_data in record.get('teamRecords', []):
                    raw_name = team_data.get('team', {}).get('name', '')
                    t_name = normalize_team_name(raw_name)
                    
                    if t_name in TRACKED_TEAMS:
                        wins = int(team_data.get('wins', 0))
                        losses = int(team_data.get('losses', 0))
                        gb = team_data.get('wildCardGamesBack', '-')
                        rank_str = str(team_data.get('wildCardRank', '99'))
                        rank = int(rank_str) if rank_str.isdigit() else 99
                        
                        standings.append({
                            "team": t_name,
                            "rank": rank,
                            "record": f"{wins}-{losses}",
                            "gb": gb
                        })
                        rankings_map[t_name] = rank
                        
        standings.sort(key=lambda x: x['rank'])
        
    except Exception as e:
        pass

    # --- Fetch Games ---
    sched_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=linescore"
    games_out = []
    try:
        sched_res = requests.get(sched_url, headers=HEADERS).json()
        if sched_res.get('totalGames', 0) > 0:
            for date_data in sched_res.get('dates', []):
                for g in date_data.get('games', []):
                    away_full = g['teams']['away']['team']['name']
                    home_full = g['teams']['home']['team']['name']
                    
                    away_nick = get_nickname(away_full)
                    home_nick = get_nickname(home_full)
                    
                    status_track = g['status']['detailedState']
                    a_score, h_score = g['teams']['away'].get('score', 0), g['teams']['home'].get('score', 0)
                    raw_game_date = g.get('gameDate')

                    status_code = g['status'].get('abstractGameState')
                    if status_code == 'Live' and status_track != 'Warmup':
                        linescore = g.get('linescore', {})
                        current_inning = linescore.get('currentInning', '')
                        inning_half = linescore.get('inningHalf', '')
                        outs = linescore.get('outs', 0)
                        half_symbol = "▲" if inning_half == "Top" else "▼"
                        status = f"{half_symbol}{current_inning}th - {outs} outs"
                    elif raw_game_date and status_track in ['Scheduled', 'Pre-Game', 'Warmup']:
                        utc_dt = datetime.strptime(raw_game_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
                        et_dt = utc_dt.astimezone(ZoneInfo("America/New_York"))
                        status = et_dt.strftime("%H:%M ET")
                    else:
                        status = g['status'].get('detailedState', 'Scheduled')

                    desired_full = None
                    if home_full == "Toronto Blue Jays" or away_full == "Toronto Blue Jays":
                        desired_full = "Toronto Blue Jays"
                    elif home_full in rankings_map and away_full in rankings_map:
                        desired_full = home_full if (rankings_map[home_full] > rankings_map[away_full] and rankings_map[away_full]>= 3) or (rankings_map[home_full] <= 2 and rankings_map[away_full] > 1) else away_full
                    elif home_full in rankings_map:
                        desired_full = away_full
                    elif away_full in rankings_map:
                        desired_full = home_full

elif home_full in leaders_ranking and away_full in leaders_ranking:

#desired_full = home_full if (leaders_ranking[home_full] > leaders_ranking[away_full]) else away_full

desired_full = away_full

elif home_full in leaders_ranking:
desired_full = away_full

elif away_full in leaders_ranking:
desired_full = home_full
                        
                    if desired_full:
                        desired = get_nickname(desired_full)
                        if status_track in ['Final', 'Game Over']:
                            winner = away_full if int(a_score) > int(h_score) else home_full
                            result = "✅ Won (Favorable)" if winner == desired_full else "❌ Lost (Unfavorable)"
                        elif status_track in ['In Progress', 'Live']:
                            winner = away_full if int(a_score) > int(h_score) else home_full if int(h_score) > int(a_score) else None
                            if winner == desired_full:
                                result = "🟢 Leading (Favorable)"
                            elif winner and winner != desired_full:
                                result = "🔴 Trailing (Unfavorable)"
                            else:
                                result = "⏳ Tied / Live"
                        else:
                            result = "🗓️ Upcoming"
                            
                        games_out.append({
                            "matchup": f"{away_nick} {a_score} vs {h_score} {home_nick}",
                            "status": status,
                            "desired": desired,
                            "result": result
                        })
    except:
        pass

    return {
        "standings": standings,
        "division_leaders": division_leaders,
        "out_of_contention": out_of_contention,
        "games": games_out
    }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AL Wild Card Tracker</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#0f172a">
    <style>
        body {
            background-color: rgba(15, 23, 42, 0.95);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 12px;
            margin: 0;
            padding: 16px 20px;
        }
        h1 {
            font-size: 15px;
            font-weight: 700;
            margin: 0 0 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.15);
            padding-bottom: 6px;
            color: #38bdf8;
        }
        h2 {
            font-size: 13px;
            font-weight: 600;
            margin: 0 0 10px 0;
            color: #facc15;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .layout {
            display: flex;
            flex-direction: row;
            gap: 24px;
            align-items: flex-start;
            flex-wrap: wrap;
        }
        .col-extra {
            min-width: 230px;
            border-right: 1px solid rgba(255,255,255,0.1);
            padding-right: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .col-standings {
            min-width: 230px;
            border-right: 1px solid rgba(255,255,255,0.1);
            padding-right: 20px;
        }
        .col-games {
            flex: 1;
            min-width: 250px;
        }
        .games-grid {
            display: grid;
            grid-template-rows: repeat(3, auto);
            grid-auto-flow: column;
            grid-auto-columns: minmax(190px, 1fr);
            gap: 10px;
            overflow-x: auto;
        }
        .row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            color: #cbd5e1;
        }
        .game {
            background: rgba(255, 255, 255, 0.04);
            padding: 10px 12px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.08);
            color: #f1f5f9;
            line-height: 1.4;
        }
        .favorable { color: #4ade80; font-weight: 600; }
        .unfavorable { color: #f87171; font-weight: 600; }
        .upcoming { color: #ffffff; font-weight: 600; }
        .top-three { font-weight: 700; color: #ffffff; }
        .highlight-jays { font-weight: 800; color: #38bdf8; }
        .highlight-leader { font-weight: 700; color: #ffffff; }

        @media (max-width: 768px) {
            .layout { flex-direction: column; gap: 16px; }
            .col-extra, .col-standings { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.1); padding-right: 0; padding-bottom: 16px; width: 100%; }
            .games-grid { grid-template-rows: none; grid-auto-flow: row; }
        }
    </style>
</head>
<body>
    <h1>AL Wild Card Tracker</h1>
    <div class="layout">
        
        <!-- COLUMN 1: Division Leaders + Out of Contention -->
        <div class="col-extra">
            <div>
                <h2>Division Leaders</h2>
                {% if division_leaders %}
                    {% for d in division_leaders %}
                    <div class="row highlight-leader">
                        <span>L{{ d.rank }}. {{ d.team }}</span>
                        <span>{{ d.record }} ({{ d.ga }})</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div>Loading...</div>
                {% endif %}
            </div>

            <div>
                <h2>Out of Contention</h2>
                {% if out_of_contention %}
                    {% for o in out_of_contention %}
                    <div class="row">
                        <span>{{ o.rank }}. {{ o.team }}</span>
                        <span>{{ o.record }} ({{ o.gb }})</span>
                    </div>
                    {% endfor %}
                {% else %}
                    <div>None/Loading...</div>
                {% endif %}
            </div>
        </div>

        <!-- COLUMN 2: Wild Card Standings -->
        <div class="col-standings">
            <h2>Wild Card Standings</h2>
            {% if not standings %}
                <div>Standings offline</div>
            {% else %}
                {% for t in standings %}
                <div class="row {% if t.rank <= 3 %}top-three{% endif %} {% if t.team == 'Toronto Blue Jays' %}highlight-jays{% endif %}">
                    <span>{{ t.rank }}. {{ t.team }}</span>
                    <span>{{ t.record }} ({{ t.gb }})</span>
                </div>
                {% endfor %}
            {% endif %}
        </div>

        <!-- COLUMN 3: Today's Games -->
        <div class="col-games">
            <h2>Today's Games</h2>
            {% if not games %}
                <div>No tracked games today.</div>
            {% else %}
                <div class="games-grid">
                    {% for g in games %}
                    <div class="game">
                        <!-- 'Blue Jays' text replaced dynamically with the highlight CSS class -->
                        <div><strong>{{ g.matchup | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') | safe }}</strong> ({{ g.status }})</div>
                        <div>Root for: <strong>{{ g.desired | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') | safe }}</strong> 
                            <span class="{% if 'Favorable' in g.result %}favorable{% elif 'Unfavorable' in g.result %}unfavorable{% else %}upcoming{% endif %}">— {{ g.result }}</span>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            {% endif %}
        </div>

    </div>
</body>
</html>
"""

@app.route("/")
def index():
    data = get_data_dict()
    return render_template_string(HTML_TEMPLATE, 
                                  division_leaders=data.get('division_leaders', []),
                                  out_of_contention=data.get('out_of_contention', []),
                                  standings=data.get('standings', []),
                                  games=data.get('games', []))

@app.route("/manifest.json")
def manifest():
    return {
        "name": "AL Wild Card Tracker",
        "short_name": "MLB Tracker",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#0f172a",
        "icons": []
    }

@app.route("/api/data")
def api_data():
    return jsonify(get_data_dict())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
