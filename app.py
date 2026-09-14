from flask import Flask, render_template_string, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Division Mappings for Intradivisional Tiebreaker Calculations
AL_EAST = ["Toronto Blue Jays", "New York Yankees", "Boston Red Sox", "Baltimore Orioles", "Tampa Bay Rays"]
AL_CENTRAL = ["Chicago White Sox", "Cleveland Guardians", "Detroit Tigers", "Kansas City Royals", "Minnesota Twins"]
AL_WEST = ["Houston Astros", "Texas Rangers", "Seattle Mariners", "Los Angeles Angels", "Sacramento Athletics"]

INITIALS = {
    "Toronto Blue Jays": "TOR",
    "Chicago White Sox": "CWS",
    "Cleveland Guardians": "CLE",
    "Detroit Tigers": "DET",
    "Kansas City Royals": "KC",
    "Minnesota Twins": "MIN",
    "Houston Astros": "HOU",
    "Texas Rangers": "TEX",
    "Seattle Mariners": "SEA",
    "Los Angeles Angels": "LAA",
    "Sacramento Athletics": "SAC",
    "New York Yankees": "NYY",
    "Boston Red Sox": "BOS",
    "Baltimore Orioles": "BAL",
    "Tampa Bay Rays": "TB"
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

def get_initial(team):
    return INITIALS.get(team, team[:3].upper())

def get_division(team):
    if team in AL_EAST: return AL_EAST
    if team in AL_CENTRAL: return AL_CENTRAL
    if team in AL_WEST: return AL_WEST
    return []

def get_intradivision_record(team, h2h_matrix):
    div_teams = get_division(team)
    w, l, rem = 0, 0, 0
    for opp in div_teams:
        if opp != team:
            record = h2h_matrix.get(team, {}).get(opp, {'w':0, 'l':0, 'rem':0})
            w += record['w']
            l += record['l']
            rem += record['rem']
    return w, l, rem

def get_data_dict():
    current_year = datetime.today().year
    now = datetime.now(ZoneInfo("America/New_York"))
    target_date = now - timedelta(days=1) if now.hour < 4 else now
    today = target_date.strftime('%Y-%m-%d')
    
    standings, division_leaders, out_of_contention = [], [], []
    rankings_map, leaders_ranking, al_teams = {}, {}, {}
    games_out = {"critical": [], "important": [], "relevant": []}
    
    try:
        rs_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}"
        res_rs = requests.get(rs_url, headers=HEADERS).json()
        
        if 'records' in res_rs:
            for record in res_rs['records']:
                for i, team_data in enumerate(record.get('teamRecords', [])):
                    name = normalize_team_name(team_data.get('team', {}).get('name', ''))
                    w = int(team_data.get('wins', 0))
                    l = int(team_data.get('losses', 0))
                    al_teams[name] = {'wins': w, 'losses': l, 'is_leader': (i == 0)}
                    
        non_leaders = [{'name': n, 'wins': s['wins'], 'losses': s['losses']} for n, s in al_teams.items() if not s['is_leader']]
        non_leaders.sort(key=lambda x: (x['wins'] - x['losses'], x['wins']), reverse=True)
        wc3_wins, wc3_losses = (non_leaders[2]['wins'], non_leaders[2]['losses']) if len(non_leaders) >= 3 else (0, 0)
            
        team_categories, tracked_teams, wc_ahead_teams, out_of_contention_teams = {}, set(), set(), set()
        for name, stats in al_teams.items():
            diff = ((stats['wins'] - wc3_wins) + (wc3_losses - stats['losses'])) / 2.0
            if stats['is_leader']:
                if abs(diff) <= 3.0: team_categories[name] = 'important'; tracked_teams.add(name)
            else:
                if abs(diff) <= 3.0: team_categories[name] = 'critical'; tracked_teams.add(name)
                elif abs(diff) <= 6.0: team_categories[name] = 'relevant'; tracked_teams.add(name)
                elif diff > 6.0: team_categories[name] = 'ahead'; wc_ahead_teams.add(name)
                else: out_of_contention_teams.add(name)
                    
        if 'records' in res_rs:
            for record in res_rs['records']:
                team_records = record.get('teamRecords', [])
                if len(team_records) >= 2:
                    l_wins = int(team_records[0].get('wins', 0))
                    l_losses = int(team_records[0].get('losses', 0))
                    s_wins = int(team_records[1].get('wins', 0))
                    s_losses = int(team_records[1].get('losses', 0))
                    ga_val = ((l_wins - s_wins) + (s_losses - l_losses)) / 2.0
                    ga_str = f"+{int(ga_val)}" if ga_val.is_integer() else f"+{ga_val}"
                    division_leaders.append({
                        "team": normalize_team_name(team_records[0].get('team', {}).get('name', '')),
                        "wins": l_wins, "losses": l_losses, "ga": "-" if ga_val == 0 else ga_str
                    })
                    
        division_leaders.sort(key=lambda x: (x['wins'] - x['losses'], x['wins']), reverse=True)
        for i, dl in enumerate(division_leaders):
            dl['rank'], dl['record'] = i + 1, f"{dl['wins']}-{dl['losses']}"
            leaders_ranking[dl['team']] = dl['rank']

        wc_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}&standingsTypes=wildCard"
        res_wc = requests.get(wc_url, headers=HEADERS).json()
        if 'records' in res_wc:
            for record in res_wc['records']:
                for team_data in record.get('teamRecords', []):
                    name = normalize_team_name(team_data.get('team', {}).get('name', ''))
                    w, l = int(team_data.get('wins', 0)), int(team_data.get('losses', 0))
                    gb = team_data.get('wildCardGamesBack', '-')
                    rank_str = str(team_data.get('wildCardRank', '99'))
                    rank = int(rank_str) if rank_str.isdigit() else 99
                    
                    if (name in tracked_teams or name in wc_ahead_teams) and not al_teams.get(name, {}).get('is_leader'):
                        standings.append({"team": name, "rank": rank, "record": f"{w}-{l}", "gb": gb})
                        rankings_map[name] = rank
                    if name in out_of_contention_teams:
                        out_of_contention.append({"team": name, "rank": rank, "record": f"{w}-{l}", "gb": gb})
                        
        standings.sort(key=lambda x: x['rank'])
        out_of_contention.sort(key=lambda x: x['rank'])
    except:
        pass

    h2h_matrix = {}
    try:
        full_sched_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&season={current_year}&gameType=R"
        full_sched = requests.get(full_sched_url, headers=HEADERS).json()
        for d in full_sched.get('dates', []):
            for g in d.get('games', []):
                away = normalize_team_name(g['teams']['away']['team']['name'])
                home = normalize_team_name(g['teams']['home']['team']['name'])
                
                if away not in h2h_matrix: h2h_matrix[away] = {}
                if home not in h2h_matrix[away]: h2h_matrix[away][home] = {'w': 0, 'l': 0, 'rem': 0}
                if home not in h2h_matrix: h2h_matrix[home] = {}
                if away not in h2h_matrix[home]: h2h_matrix[home][away] = {'w': 0, 'l': 0, 'rem': 0}
                
                status_track = g['status']['abstractGameState']
                detailed_state = g['status'].get('detailedState', '')
                
                if detailed_state in ['Final', 'Game Over', 'Completed Early']:
                    a_score = g['teams']['away'].get('score', 0)
                    h_score = g['teams']['home'].get('score', 0)
                    if a_score > h_score:
                        h2h_matrix[away][home]['w'] += 1
                        h2h_matrix[home][away]['l'] += 1
                    elif h_score > a_score:
                        h2h_matrix[home][away]['w'] += 1
                        h2h_matrix[away][home]['l'] += 1
                elif detailed_state not in ['Postponed', 'Cancelled'] and status_track in ['Preview', 'Scheduled', 'Live']:
                    h2h_matrix[away][home]['rem'] += 1
                    h2h_matrix[home][away]['rem'] += 1
    except:
        pass

    tiebreakers_2way = []
    tiebreakers_3way = []
    try:
        bj_name = "Toronto Blue Jays"
        target_teams = [t for t, cat in team_categories.items() if cat in ['critical', 'important'] and t != bj_name]
        
        # --- 2-Way Tiebreakers ---
        for team in target_teams:
            h2h = h2h_matrix.get(bj_name, {}).get(team, {'w': 0, 'l': 0, 'rem': 0})
            bj_w, bj_l, rem = h2h['w'], h2h['l'], h2h['rem']
            
            bj_div_w, bj_div_l, bj_div_rem = get_intradivision_record(bj_name, h2h_matrix)
            opp_div_w, opp_div_l, opp_div_rem = get_intradivision_record(team, h2h_matrix)
            
            if rem == 0 and bj_w != bj_l:
                locked = True
                advantage = "Yes" if bj_w > bj_l else "No"
                detail = f"{bj_w}-{bj_l} record"
            elif bj_w > bj_l + rem:
                locked = True
                advantage = "Yes"
                detail = f"{bj_w}-{bj_l} record"
                if rem > 0: detail += f" ({rem} rem)"
            elif bj_l > bj_w + rem:
                locked = True
                advantage = "No"
                detail = f"{bj_w}-{bj_l} record"
                if rem > 0: detail += f" ({rem} rem)"
            elif rem == 0 and bj_w == bj_l:
                if bj_div_w > opp_div_w + opp_div_rem:
                    locked = True
                    advantage = "Yes"
                elif opp_div_w > bj_div_w + bj_div_rem:
                    locked = True
                    advantage = "No"
                else:
                    locked = False
                    advantage = "Yes" if bj_div_w > opp_div_w else "No" if opp_div_w > bj_div_w else "Tied"
                detail = f"{bj_w}-{bj_l}, intradiv. {bj_div_w}-{bj_div_l}"
                if bj_div_rem > 0: detail += f" ({bj_div_rem} rem)"
                detail += f" vs. {opp_div_w}-{opp_div_l}"
                if opp_div_rem > 0: detail += f" ({opp_div_rem} rem)"
            else:
                locked = False
                if bj_w == bj_l and rem > 0: 
                    advantage = "Yes" if bj_div_w > opp_div_w else "No" if opp_div_w > bj_div_w else "Tied"
                detail = f"{bj_w}-{bj_l} ({rem} rem), intradiv. {bj_div_w}-{bj_div_l}"
                if bj_div_rem > 0: detail += f" ({bj_div_rem} rem)"
                detail += f" vs. {opp_div_w}-{opp_div_l}"
                if opp_div_rem > 0: detail += f" ({opp_div_rem} rem)"
                    
            tiebreakers_2way.append({"team": get_initial(team), "locked": locked, "advantage": advantage, "detail": detail})
            
        # --- 3-Way Tiebreakers ---
        cen_tracked = [t for t in target_teams if t in AL_CENTRAL]
        wes_tracked = [t for t in target_teams if t in AL_WEST]
        
        for c_team in cen_tracked:
            for w_team in wes_tracked:
                base_TC_w = h2h_matrix.get(bj_name, {}).get(c_team, {}).get('w', 0)
                base_TC_l = h2h_matrix.get(bj_name, {}).get(c_team, {}).get('l', 0)
                base_TW_w = h2h_matrix.get(bj_name, {}).get(w_team, {}).get('w', 0)
                base_TW_l = h2h_matrix.get(bj_name, {}).get(w_team, {}).get('l', 0)
                base_CW_w = h2h_matrix.get(c_team, {}).get(w_team, {}).get('w', 0)
                base_CW_l = h2h_matrix.get(c_team, {}).get(w_team, {}).get('l', 0)
                
                rem_TC = h2h_matrix.get(bj_name, {}).get(c_team, {}).get('rem', 0)
                rem_TW = h2h_matrix.get(bj_name, {}).get(w_team, {}).get('rem', 0)
                rem_CW = h2h_matrix.get(c_team, {}).get(w_team, {}).get('rem', 0)
                
                can_win, can_lose = False, False
                
                for i in range(rem_TC + 1):
                    for j in range(rem_TW + 1):
                        for k in range(rem_CW + 1):
                            t_w = (base_TC_w + i) + (base_TW_w + j)
                            t_l = (base_TC_l + (rem_TC - i)) + (base_TW_l + (rem_TW - j))
                            c_w = (base_TC_l + (rem_TC - i)) + (base_CW_w + k)
                            c_l = (base_TC_w + i) + (base_CW_l + (rem_CW - k))
                            w_w = (base_TW_l + (rem_TW - j)) + (base_CW_l + (rem_CW - k))
                            w_l = (base_TW_w + j) + (base_CW_w + k)
                            
                            t_pct = t_w / (t_w + t_l) if (t_w+t_l) > 0 else 0
                            c_pct = c_w / (c_w + c_l) if (c_w+c_l) > 0 else 0
                            w_pct = w_w / (w_w + w_l) if (w_w+w_l) > 0 else 0
                            
                            max_pct = max(t_pct, c_pct, w_pct)
                            leaders = []
                            if abs(t_pct - max_pct) < 0.001: leaders.append('T')
                            if abs(c_pct - max_pct) < 0.001: leaders.append('C')
                            if abs(w_pct - max_pct) < 0.001: leaders.append('W')
                            
                            if 'T' not in leaders: can_lose = True
                            elif len(leaders) == 1: can_win = True
                            else: can_win = True; can_lose = True
                
                total_rem = rem_TC + rem_TW + rem_CW
                bj_init, c_init, w_init = get_initial(bj_name), get_initial(c_team), get_initial(w_team)
                t_base_w, t_base_l = base_TC_w + base_TW_w, base_TC_l + base_TW_l
                c_base_w, c_base_l = base_TC_l + base_CW_w, base_TC_w + base_CW_l
                w_base_w, w_base_l = base_TW_l + base_CW_l, base_TW_w + base_CW_w
                
                team_data_list = [
                    {'name': f'<span class="highlight-jays">{bj_init}</span>', 'w': t_base_w, 'l': t_base_l, 'pct': t_base_w / max(1, t_base_w + t_base_l)},
                    {'name': c_init, 'w': c_base_w, 'l': c_base_l, 'pct': c_base_w / max(1, c_base_w + c_base_l)},
                    {'name': w_init, 'w': w_base_w, 'l': w_base_l, 'pct': w_base_w / max(1, w_base_w + w_base_l)}
                ]
                team_data_list.sort(key=lambda x: (x['pct'], x['w']), reverse=True)
                
                detail_parts = [f"{item['name']} {item['w']}-{item['l']}" for item in team_data_list]
                detail = ", ".join(detail_parts)
                if total_rem > 0: detail += f" ({total_rem} rem)"
                
                locked = False
                if can_win and not can_lose:
                    locked, advantage = True, "Yes"
                elif can_lose and not can_win:
                    locked, advantage = True, "No"
                else:
                    advantage = "No" if (t_base_w / max(1, t_base_w + t_base_l)) < (c_base_w / max(1, c_base_w + c_base_l)) else "Yes"

                t_pct = t_base_w / max(1, t_base_w + t_base_l)
                c_pct = c_base_w / max(1, c_base_w + c_base_l)
                w_pct = w_base_w / max(1, w_base_w + w_base_l)
                max_pct = max(t_pct, c_pct, w_pct)
                
                curr_leaders = []
                if abs(t_pct - max_pct) < 0.001: curr_leaders.append('T')
                if abs(c_pct - max_pct) < 0.001: curr_leaders.append('C')
                if abs(w_pct - max_pct) < 0.001: curr_leaders.append('W')

                if len(curr_leaders) == 2 and 'T' in curr_leaders:
                    if 'C' in curr_leaders or 'W' in curr_leaders: 
                        detail += " (See H2H)"
                        
                tiebreakers_3way.append({"teams": f"Vs. {c_init} & {w_init}", "locked": locked, "advantage": advantage, "detail": detail})
    except:
        pass

    try:
        sched_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=linescore"
        sched_res = requests.get(sched_url, headers=HEADERS).json()
        if sched_res.get('totalGames', 0) > 0:
            for date_data in sched_res.get('dates', []):
                for g in date_data.get('games', []):
                    away_full = normalize_team_name(g['teams']['away']['team']['name'])
                    home_full = normalize_team_name(g['teams']['home']['team']['name'])
                    
                    away_nick, home_nick = get_nickname(away_full), get_nickname(home_full)
                    status_track = g['status']['detailedState']
                    a_score, h_score = g['teams']['away'].get('score', 0), g['teams']['home'].get('score', 0)
                    raw_game_date = g.get('gameDate')

                    status_code = g['status'].get('abstractGameState')
                    if status_code == 'Live' and status_track != 'Warmup':
                        linescore = g.get('linescore', {})
                        current_inning = linescore.get('currentInning', '')
                        inning_half = linescore.get('inningHalf', '')
                        outs = linescore.get('outs', 0)
                        status = f"{'▲' if inning_half == 'Top' else '▼'}{current_inning}th - {outs} outs"
                    elif raw_game_date and status_track in ['Scheduled', 'Pre-Game', 'Warmup']:
                        utc_dt = datetime.strptime(raw_game_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=ZoneInfo("UTC"))
                        status = utc_dt.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M ET")
                    else:
                        status = g['status'].get('detailedState', 'Scheduled')

                    desired_full = None
                    if home_full == "Toronto Blue Jays" or away_full == "Toronto Blue Jays":
                        desired_full = "Toronto Blue Jays"
                    elif home_full in rankings_map and away_full in rankings_map:
                        desired_full = home_full if (rankings_map[home_full] > rankings_map[away_full] and rankings_map[away_full]>= 3) or (rankings_map[home_full] <= 2 and rankings_map[away_full] > 1) else away_full
                    elif home_full in rankings_map: desired_full = away_full
                    elif away_full in rankings_map: desired_full = home_full
                    elif home_full in leaders_ranking and away_full in leaders_ranking:
                        desired_full = home_full if (leaders_ranking[home_full] < leaders_ranking[away_full]) else away_full
                    elif home_full in leaders_ranking: desired_full = away_full
                    elif away_full in leaders_ranking: desired_full = home_full
                        
                    cat = None
                    if team_categories.get(away_full) == 'critical' or team_categories.get(home_full) == 'critical': cat = 'critical'
                    elif team_categories.get(away_full) == 'important' or team_categories.get(home_full) == 'important': cat = 'important'
                    elif team_categories.get(away_full) == 'relevant' or team_categories.get(home_full) == 'relevant': cat = 'relevant'
                        
                    if cat and desired_full:
                        desired = get_nickname(desired_full)
                        if status_track in ['Final', 'Game Over']:
                            winner = away_full if int(a_score) > int(h_score) else home_full
                            result = "✅ Won (Favorable)" if winner == desired_full else "❌ Lost (Unfavorable)"
                        elif status_track in ['In Progress', 'Live']:
                            winner = away_full if int(a_score) > int(h_score) else home_full if int(h_score) > int(a_score) else None
                            if winner == desired_full: result = "🟢 Leading (Favorable)"
                            elif winner and winner != desired_full: result = "🔴 Trailing (Unfavorable)"
                            else: result = "⏳ Tied / Live"
                        else:
                            result = "🗓️ Upcoming"
                            
                        games_out[cat].append({
                            "matchup": f"{away_nick} {a_score} vs {h_score} {home_nick}",
                            "status": status, "desired": desired, "result": result
                        })
    except:
        pass

    return {
        "standings": standings,
        "division_leaders": division_leaders,
        "out_of_contention": out_of_contention,
        "games": games_out,
        "tiebreakers_2way": tiebreakers_2way,
        "tiebreakers_3way": tiebreakers_3way
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
            font-size: 12px;
            font-weight: 700;
            margin: 0 0 6px 0;
            color: #facc15;
            padding-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid rgba(255,255,255,0.15);
        }
        .layout {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            align-items: start;
        }
        .col-extra {
            display: flex;
            flex-direction: column;
            gap: 18px;
        }
        .game-category-col, .tiebreaker-col {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .col-standings {
            display: flex;
            flex-direction: column;
            gap: 0px;
        }
        .col-games-container {
            display: contents;
        }
        .tiebreaker-box {
            background: rgba(255, 255, 255, 0.04);
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.08);
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: #cbd5e1;
        }
        .row-tiebreaker {
            color: #cbd5e1;
            line-height 1.4;
        }
        .game {
            background: rgba(255, 255, 255, 0.04);
            padding: 6px 10px;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.08);
            color: #f1f5f9;
            line-height: 1.3;
            margin-bottom: 4px;
        }
        .favorable { color: #4ade80; font-weight: 600; }
        .unfavorable { color: #f87171; font-weight: 600; }
        .upcoming { color: #ffffff; font-weight: 600; }
        .top-three { font-weight: 700; color: #ffffff; }
        .highlight-jays { font-weight: 800; color: #38bdf8; }
        .highlight-leader { font-weight: 700; color: #ffffff; }
        .tiebreaker-detail { font-size: 11px; color: #94a3b8; }
        
        /* Conditional Lock Color Coding */
        .status-green { color: #4ade80; font-weight: 700; }
        .status-red { color: #f87171; font-weight: 700; }
        .status-white { color: #ffffff; font-weight: 600; }
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
                    <div class="row highlight-leader" style="margin-bottom: 4px;">
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
                    <div class="row" style="margin-bottom: 4px;">
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
                <div class="row {% if t.rank <= 3 %}top-three{% endif %} {% if t.team == 'Toronto Blue Jays' %}highlight-jays{% endif %}" style="margin-bottom: 4px;">
                    <span>{{ t.rank }}. {{ t.team }}</span>
                    <span>{{ t.record }} ({{ t.gb }})</span>
                </div>
                {% endfor %}
            {% endif %}
        </div>

        <!-- COLUMNS 3, 4, 5: GAMES -->
        <div class="col-games-container">
            {% set cList = games.critical %}
            {% set iList = games.important %}
            {% set rList = games.relevant %}

            <div class="game-category-col">
                <h2>Critical Games</h2>
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

            <div class="game-category-col">
                <h2>Important Games</h2>
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

            <div class="game-category-col">
                <h2>Other Relevant Games</h2>
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

        <!-- COLUMN 6: 2-WAY TIEBREAKERS -->
        <div class="tiebreaker-col">
            <h2>2-Way Tiebreakers</h2>
            <div class="tiebreaker-box">
                {% if tiebreakers_2way %}
                    {% for tb in tiebreakers_2way %}
                    <div style="display: flex; flex-direction: column; gap: 2px; {% if not loop.last %}border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 6px;{% endif %}">
                        <div class="row-tiebreaker">
                            <strong>Vs. {{ tb.team }}: </strong>
                            {% if tb.locked %}
                                {% if tb.advantage == "Yes" %}
                                    <span class="status-green"> 🔒 Yes </span>
                                {% else %}
                                    <span class="status-red"> 🔒 No </span>
                                {% endif %}
                            {% else %}
                                <span class="status-white"> 🤷 {{ tb.advantage }} </span>
                            {% endif %}
                            <span class="tiebreaker-detail">— {{ tb.detail | safe }}</span>
                        </div>                        
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="color: #64748b; font-size: 11px;">Evaluating active matchups...</div>
                {% endif %}
            </div>
        </div>

        <!-- COLUMN 7: 3-WAY TIEBREAKERS -->
        <div class="tiebreaker-col">
            <h2>3-Way Tiebreakers</h2>
            <div class="tiebreaker-box">
                {% if tiebreakers_3way %}
                    {% for tb in tiebreakers_3way %}
                    <div style="display: flex; flex-direction: column; gap: 2px; {% if not loop.last %}border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 6px;{% endif %}">
                        <div class="row-tiebreaker">
                            <strong>{{ tb.teams }}: </strong>
                            {% if tb.locked %}
                                {% if tb.advantage == "Yes" %}
                                    <span class="status-green"> 🔒 Yes</span>
                                {% else %}
                                    <span class="status-red"> 🔒 No</span>
                                {% endif %}
                            {% else %}
                                <span class="status-white"> 🤷 {{ tb.advantage }}</span>
                            {% endif %}
                            <span class="tiebreaker-detail"> — {{ tb.detail | safe }}</span>
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="color: #64748b; font-size: 11px;">No active 3-way combinations</div>
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
                                  games=data.get('games', {}),
                                  tiebreakers_2way=data.get('tiebreakers_2way', []),
                                  tiebreakers_3way=data.get('tiebreakers_3way', []))

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
