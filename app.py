from flask import Flask, render_template_string, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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
    parts = full_name.split()
    if len(parts) > 1:
        if parts[-2] in ["Red", "Blue", "White", "Boston", "Kansas", "Los", "New"]:
            if full_name in ["Boston Red Sox", "Toronto Blue Jays", "Chicago White Sox", "Los Angeles Angels", "Kansas City Royals"]:
                return " ".join(parts[-2:])
    return parts[-1]

def get_data_dict():
    current_year = datetime.today().year

    # 4 AM ET Rollover Check
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
    al_teams = {}
    
    games_out = {
        "critical": [],
        "important": [],
        "relevant": []
    }
    
    try:
        # --- 1. Fetch Division Standings & Calculate WC3 Gap ---
        rs_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}"
        res_rs = requests.get(rs_url, headers=HEADERS).json()
        
        if 'records' in res_rs:
            for record in res_rs['records']:
                team_records = record.get('teamRecords', [])
                for i, team_data in enumerate(team_records):
                    raw_name = team_data.get('team', {}).get('name', '')
                    name = normalize_team_name(raw_name)
                    w = int(team_data.get('wins', 0))
                    l = int(team_data.get('losses', 0))
                    al_teams[name] = {
                        'wins': w,
                        'losses': l,
                        'is_leader': (i == 0)
                    }
                    
        non_leaders = [ {'name': n, 'wins': s['wins'], 'losses': s['losses']} for n, s in al_teams.items() if not s['is_leader'] ]
        non_leaders.sort(key=lambda x: (x['wins'] - x['losses'], x['wins']), reverse=True)
        
        if len(non_leaders) >= 3:
            wc3_wins, wc3_losses = non_leaders[2]['wins'], non_leaders[2]['losses']
        else:
            wc3_wins, wc3_losses = 0, 0
            
        team_categories = {}
        tracked_teams = set()
        out_of_contention_teams = set()
        
        for name, stats in al_teams.items():
            diff = ((stats['wins'] - wc3_wins) + (wc3_losses - stats['losses'])) / 2.0
            
            if stats['is_leader']:
                if abs(diff) <= 3.0: 
                    team_categories[name] = 'important'
                    tracked_teams.add(name)
            else:
                if abs(diff) <= 3.0: 
                    team_categories[name] = 'critical'
                    tracked_teams.add(name)
                elif diff > 3.0 or (diff < -3.0 and diff >= -6.0): 
                    team_categories[name] = 'relevant'
                    tracked_teams.add(name)
                else: 
                    out_of_contention_teams.add(name)
                    
        if 'records' in res_rs:
            for record in res_rs['records']:
                team_records = record.get('teamRecords', [])
                if len(team_records) >= 2:
                    leader_name = normalize_team_name(team_records[0].get('team', {}).get('name', ''))
                    l_wins = int(team_records[0].get('wins', 0))
                    l_losses = int(team_records[0].get('losses', 0))
                    
                    s_wins = int(team_records[1].get('wins', 0))
                    s_losses = int(team_records[1].get('losses', 0))
                    
                    ga_val = ((l_wins - s_wins) + (s_losses - l_losses)) / 2.0
                    ga_str = f"+{int(ga_val)}" if ga_val.is_integer() else f"+{ga_val}"
                    if ga_val == 0: ga_str = "-"
                        
                    division_leaders.append({
                        "team": leader_name,
                        "wins": l_wins,
                        "losses": l_losses,
                        "ga": ga_str
                    })
                    
        division_leaders.sort(key=lambda x: (x['wins'] - x['losses'], x['wins']), reverse=True)
        for i, dl in enumerate(division_leaders):
            dl['rank'] = i + 1
            dl['record'] = f"{dl['wins']}-{dl['losses']}"
            leaders_ranking[dl['team']] = dl['rank']

        # --- 2. Fetch Wild Card Standings ---
        wc_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}&standingsTypes=wildCard"
        res_wc = requests.get(wc_url, headers=HEADERS).json()
        
        if 'records' in res_wc:
            for record in res_wc['records']:
                for team_data in record.get('teamRecords', []):
                    name = normalize_team_name(team_data.get('team', {}).get('name', ''))
                    w = int(team_data.get('wins', 0))
                    l = int(team_data.get('losses', 0))
                    gb = team_data.get('wildCardGamesBack', '-')
                    rank_str = str(team_data.get('wildCardRank', '99'))
                    rank = int(rank_str) if rank_str.isdigit() else 99
                    
                    if name in tracked_teams and not al_teams.get(name, {}).get('is_leader'):
                        standings.append({
                            "team": name,
                            "rank": rank,
                            "record": f"{w}-{l}",
                            "gb": gb
                        })
                        rankings_map[name] = rank
                        
                    if name in out_of_contention_teams:
                        out_of_contention.append({
                            "team": name,
                            "rank": rank,
                            "record": f"{w}-{l}",
                            "gb": gb
                        })
                        
        standings.sort(key=lambda x: x['rank'])
        out_of_contention.sort(key=lambda x: x['rank'])
        
    except Exception as e:
        pass

    # --- Fetch Games ---
    sched_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=linescore"
    try:
        sched_res = requests.get(sched_url, headers=HEADERS).json()
        if sched_res.get('totalGames', 0) > 0:
            for date_data in sched_res.get('dates', []):
                for g in date_data.get('games', []):
                    away_full = normalize_team_name(g['teams']['away']['team']['name'])
                    home_full = normalize_team_name(g['teams']['home']['team']['name'])
                    
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
                        desired_full = home_full if (leaders_ranking[home_full] < leaders_ranking[away_full]) else away_full
                    elif home_full in leaders_ranking:
                        desired_full = away_full
                    elif away_full in leaders_ranking:
                        desired_full = home_full
                        
                    cat = None
                    if team_categories.get(away_full) == 'critical' or team_categories.get(home_full) == 'critical':
                        cat = 'critical'
                    elif team_categories.get(away_full) == 'important' or team_categories.get(home_full) == 'important':
                        cat = 'important'
                    elif team_categories.get(away_full) == 'relevant' or team_categories.get(home_full) == 'relevant':
                        cat = 'relevant'
                        
                    if cat and desired_full:
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
                            
                        games_out[cat].append({
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
            margin: 0 0 8px 0;
            color: #facc15;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .cat-header {
            font-size: 12px;
            font-weight: 700;
            color: #facc15;
            margin: 0 0 6px 0;
            border-bottom: 1px solid rgba(255,255,255,0.15);
            padding-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .layout {
            display: flex;
            flex-direction: row;
            gap: 20px;
            align-items: flex-start;
            flex-wrap: wrap;
        }
        /* Enforce uniform variable widths between 250px and 300px for all main columns */
        .col-extra {
            flex: 1 1 250px;
            min-width: 250px;
            max-width: 300px;
            border-right: 1px solid rgba(255,255,255,0.1);
            padding-right: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .col-standings {
            flex: 1 1 250px;
            min-width: 250px;
            max-width: 300px;
            border-right: 1px solid rgba(255,255,255,0.1);
            padding-right: 20px;
        }
        .col-games-container {
            display: flex;
            gap: 12px;
            align-items: flex-start;
            flex-wrap: wrap;
            flex: 3 1 750px;
        }
        .game-category-col {
            flex: 1 1 250px;
            min-width: 250px;
            max-width: 300px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
            color: #cbd5e1;
        }
        .game {
            background: rgba(255, 255, 255, 0.04);
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.08);
            color: #f1f5f9;
            line-height: 1.3;
            font-size: 11px;
            margin-bottom: 4px;
        }
        .favorable { color: #4ade80; font-weight: 600; }
        .unfavorable { color: #f87171; font-weight: 600; }
        .upcoming { color: #ffffff; font-weight: 600; }
        .top-three { font-weight: 700; color: #ffffff; }
        .highlight-jays { font-weight: 800; color: #38bdf8; }
        .highlight-leader { font-weight: 700; color: #ffffff; }

        @media (max-width: 1024px) {
            .layout { flex-direction: column; }
            .col-extra, .col-standings { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.1); padding-right: 0; padding-bottom: 12px; max-width: 100%; }
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

        <!-- COLUMN 3: GAMES (Split into Critical, Important, and Other Relevant columns) -->
        <div class="col-games-container">
            {% set cList = games.critical %}
            {% set iList = games.important %}
            {% set rList = games.relevant %}

            <!-- Critical Games Column -->
            <div class="game-category-col">
                <div class="cat-header">Critical Games</div>
                {% if cList|length == 0 %}
                    <div style="color: #64748b; font-size: 11px;">None today</div>
                {% else %}
                    {% for g in cList %}
                        {% set resClass = 'favorable' if 'Favorable' in g.result else ('unfavorable' if 'Unfavorable' in g.result else 'upcoming') %}
                        {% set matchText = g.matchup | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        {% set desiredText = g.desired | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        <div class="game">
                            <div><strong>{{ matchText | safe }}</strong> ({{ g.status }})</div>
                            <div>Root for: <strong>{{ desiredText | safe }}</strong><span class="{{ resClass }}"> — {{ g.result }}</span></div>
                        </div>
                    {% endfor %}
                {% endif %}
            </div>

            <!-- Important Games Column -->
            <div class="game-category-col">
                <div class="cat-header">Important Games</div>
                {% if iList|length == 0 %}
                    <div style="color: #64748b; font-size: 11px;">None today</div>
                {% else %}
                    {% for g in iList %}
                        {% set resClass = 'favorable' if 'Favorable' in g.result else ('unfavorable' if 'Unfavorable' in g.result else 'upcoming') %}
                        {% set matchText = g.matchup | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        {% set desiredText = g.desired | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        <div class="game">
                            <div><strong>{{ matchText | safe }}</strong> ({{ g.status }})</div>
                            <div>Root for: <strong>{{ desiredText | safe }}</strong><span class="{{ resClass }}"> — {{ g.result }}</span></div>
                        </div>
                    {% endfor %}
                {% endif %}
            </div>

            <!-- Other Relevant Games Column -->
            <div class="game-category-col">
                <div class="cat-header">Other Relevant Games</div>
                {% if rList|length == 0 %}
                    <div style="color: #64748b; font-size: 11px;">None today</div>
                {% else %}
                    {% for g in rList %}
                        {% set resClass = 'favorable' if 'Favorable' in g.result else ('unfavorable' if 'Unfavorable' in g.result else 'upcoming') %}
                        {% set matchText = g.matchup | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        {% set desiredText = g.desired | replace('Blue Jays', '<span class="highlight-jays">Blue Jays</span>') %}
                        <div class="game">
                            <div><strong>{{ matchText | safe }}</strong> ({{ g.status }})</div>
                            <div>Root for: <strong>{{ desiredText | safe }}</strong><span class="{{ resClass }}"> — {{ g.result }}</span></div>
                        </div>
                    {% endfor %}
                {% endif %}
            </div>
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
                                  games=data.get('games', {}))

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
