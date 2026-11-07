import datetime as dt
from zoneinfo import ZoneInfo
import json
import sqlite3
import time
from pathlib import Path
import requests
import pandas as pd

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
DB = Path(__file__).with_name('nba_cache.sqlite')
S = requests.Session()
S.headers.update({'User-Agent':'NBA-Stats-Dashboard/1.0 (personal analytics)'})


def fetch(path, params=None):
    for attempt in range(3):
        try:
            r = S.get(BASE + path, params=params, timeout=25)
            if r.status_code in (429,500,502,503,504):
                time.sleep(2 ** attempt + 1)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 2: raise
            time.sleep(2 ** attempt + 1)
    raise RuntimeError('ESPN did not respond after retries')


def connect():
    c = sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS scoreboard_days (day TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS season_scans (season INTEGER NOT NULL, season_type INTEGER NOT NULL, scanned_through TEXT NOT NULL, PRIMARY KEY(season,season_type))')
    c.execute('CREATE TABLE IF NOT EXISTS season_games (season INTEGER NOT NULL, season_type INTEGER NOT NULL, game_id TEXT NOT NULL, PRIMARY KEY(season,season_type,game_id))')
    return c


def sydney_games(day=None):
    """Events whose tipoff occurs on the Sydney calendar day, including US previous day."""
    local = ZoneInfo('Australia/Sydney')
    day = day or dt.datetime.now(local).date()
    events = {}
    for offset in (-1, 0, 1):
        query_day = day + dt.timedelta(days=offset)
        payload = fetch('/scoreboard', {'dates': query_day.strftime('%Y%m%d'), 'limit': 200})
        for event in payload.get('events', []):
            try:
                tip = dt.datetime.fromisoformat(event['date'].replace('Z', '+00:00')).astimezone(local)
            except (KeyError, ValueError, TypeError):
                continue
            if tip.date() != day:
                continue
            comp = (event.get('competitions') or [{}])[0]
            competitors = comp.get('competitors') or []
            home = next((x for x in competitors if x.get('homeAway') == 'home'), {})
            away = next((x for x in competitors if x.get('homeAway') == 'away'), {})
            home_id = str(home.get('team', {}).get('id', '')).strip()
            away_id = str(away.get('team', {}).get('id', '')).strip()
            if home_id not in NBA_TEAM_IDS or away_id not in NBA_TEAM_IDS:
                continue
            events[str(event['id'])] = {
                'Sydney date': tip.date().isoformat(),
                'Sydney time': tip.strftime('%I:%M %p'),
                'Away': away.get('team', {}).get('displayName', '?'),
                'Home': home.get('team', {}).get('displayName', '?'),
                'Status': event.get('status', {}).get('type', {}).get('description', 'Scheduled'),
                'Away score': away.get('score', ''), 'Home score': home.get('score', ''),
                'ESPN game ID': str(event['id'])
            }
    return list(events.values())


def season_bounds(season, season_type):
    start = dt.date(season-1, 10, 1) if season_type == 2 else dt.date(season, 4, 1)
    end = dt.date(season, 4, 20) if season_type == 2 else dt.date(season, 7, 1)
    return start, min(end, dt.date.today())


def cache_status(season, season_type=2):
    """Report durable local cache contents without calling ESPN."""
    with connect() as c:
        scan = c.execute('SELECT scanned_through FROM season_scans WHERE season=? AND season_type=?',
                         (season,season_type)).fetchone()
        count = c.execute('SELECT COUNT(*) FROM season_games WHERE season=? AND season_type=?',
                          (season,season_type)).fetchone()[0]
        saved = c.execute('SELECT COUNT(*) FROM season_games sg JOIN games g ON sg.game_id=g.id WHERE sg.season=? AND sg.season_type=?',
                          (season,season_type)).fetchone()[0]
    return {'scanned_through':scan[0] if scan else None,'games_found':count,'boxscores_saved':saved,'database':str(DB)}


def espn_season_type(payload):
    """Return ESPN season type (1 preseason, 2 regular, 3 playoffs) if present."""
    candidates = [
        payload.get('season'),
        (payload.get('header') or {}).get('season'),
        ((payload.get('header') or {}).get('competitions') or [{}])[0].get('season'),
    ]
    for item in candidates:
        if isinstance(item, dict):
            value = item.get('type')
            if isinstance(value, dict):
                value = value.get('id') or value.get('type')
            try:
                return int(value)
            except (ValueError, TypeError):
                continue
    return None


def game_ids(season, season_type=2, mode='update', progress=None):
    """Scan only unscanned days plus recent days; reuse persistent SQLite index."""
    start,end=season_bounds(season,season_type)
    if end<start: return []
    with connect() as c:
        scan=c.execute('SELECT scanned_through FROM season_scans WHERE season=? AND season_type=?',
                       (season,season_type)).fetchone()
        if mode == 'cached':
            return [r[0] for r in c.execute('SELECT game_id FROM season_games WHERE season=? AND season_type=? ORDER BY game_id',
                                          (season,season_type))]
        if mode == 'full':
            first=start
        elif scan:
            # Revisit the most recent four days for scores corrected or games finalized late.
            first=max(start, min(dt.date.fromisoformat(scan[0])+dt.timedelta(days=1),end-dt.timedelta(days=3)))
        else:
            first=start
        days=[]
        day=first
        while day<=end:
            days.append(day)
            day+=dt.timedelta(days=1)
        failures=[]
        for i,day in enumerate(days):
            key=day.isoformat()
            try:
                # Full refresh forces new network requests. Regular updates recheck recent days.
                payload=fetch('/scoreboard',{'dates':day.strftime('%Y%m%d'),'limit':200})
                c.execute('INSERT OR REPLACE INTO scoreboard_days VALUES (?,?,?)',
                          (key,json.dumps(payload),dt.datetime.now(dt.timezone.utc).isoformat()))
                for event in payload.get('events',[]):
                    if (event.get('status',{}).get('type',{}).get('completed')
                            and espn_season_type(event) == season_type):
                        c.execute('INSERT OR IGNORE INTO season_games VALUES (?,?,?)',
                                  (season,season_type,str(event['id'])))
                c.execute('INSERT INTO season_scans VALUES (?,?,?) ON CONFLICT(season,season_type) DO UPDATE SET scanned_through=excluded.scanned_through',
                          (season,season_type,key))
                c.commit()
            except (requests.RequestException,ValueError,KeyError) as exc:
                failures.append(f'{key}: {exc}')
                # Do not mark failed days as scanned. A future refresh can retry them.
                break
            if progress: progress((i+1)/max(len(days),1)*0.25, f'Checking game dates: {i+1}/{len(days)}')
            time.sleep(0.12)
        if failures:
            raise RuntimeError('ESPN scoreboard refresh failed. Previously saved games are safe. '+ '; '.join(failures[:2]))
        return [r[0] for r in c.execute('SELECT game_id FROM season_games WHERE season=? AND season_type=? ORDER BY game_id',
                                       (season,season_type))]


def parse_game(payload, gid):
    header = payload.get('header',{})
    comp = (header.get('competitions') or [{}])[0]
    teams = comp.get('competitors') or []
    if len(teams) != 2: return [], []
    byid = {str(t.get('team',{}).get('id')): t for t in teams}
    box = payload.get('boxscore') or {}
    # ESPN sends game tipoffs as UTC timestamps. Convert the actual tipoff
    # instant to Sydney before taking the calendar date (handles AEDT/AEST).
    raw_tipoff = comp.get('date') or header.get('date', '')
    try:
        tipoff = dt.datetime.fromisoformat(raw_tipoff.replace('Z', '+00:00'))
        if tipoff.tzinfo is None:
            tipoff = tipoff.replace(tzinfo=dt.timezone.utc)
        date = tipoff.astimezone(ZoneInfo('Australia/Sydney')).date().isoformat()
    except (TypeError, ValueError, AttributeError):
        date = str(raw_tipoff)[:10]

    team_rows=[]
    for t in teams:
        team = t.get('team',{})
        tid = str(team.get('id'))
        opp = next((x for x in teams if str(x.get('team',{}).get('id')) != tid),None)
        if not opp: continue
        team_rows.append({'game_id':gid,'date':date,'team_id':tid,'team':team.get('displayName',''),
                          'opponent_id':str(opp.get('team',{}).get('id')),'opponent':opp.get('team',{}).get('displayName',''),
                          'home':t.get('homeAway')=='home','points':number(t.get('score')),'opp_points':number(opp.get('score'))})
    rows=[]
    for group in box.get('players',[]):
        team = group.get('team') or {}
        tid = str(team.get('id'))
        opp = next((x for x in teams if str(x.get('team',{}).get('id')) != tid),None)
        if not opp: continue
        for stat in group.get('statistics',[]):
            labels = stat.get('names') or stat.get('labels') or []
            labels = [str(x).upper() for x in labels]
            for a in stat.get('athletes',[]):
                athlete = a.get('athlete') or {}
                if a.get('didNotPlay') or not a.get('stats'): continue
                raw = dict(zip(labels,a['stats']))
                if not raw: continue
                pos = athlete.get('position') or {}
                pos = pos.get('abbreviation','') if isinstance(pos,dict) else ''
                if not pos:
                    pos = (a.get('position') or {}).get('abbreviation','') if isinstance(a.get('position'),dict) else ''
                row={'game_id':gid,'date':date,'team_id':tid,'team':team.get('displayName',''),
                     'opponent_id':str(opp.get('team',{}).get('id')),'opponent':opp.get('team',{}).get('displayName',''),
                     'player_id':str(athlete.get('id','')),'player':athlete.get('displayName',''), 'position':pos,
                     'home':byid.get(tid,{}).get('homeAway')=='home'}
                for label,key in [('PTS','pts'),('REB','reb'),('AST','ast'),('STL','stl'),('BLK','blk'),('TO','tov'),('3PT','three'),('FG','fg'),('FT','ft'),('MIN','min')]:
                    v = raw.get(label,'0')
                    if key in ('three','fg','ft'):
                        pair = str(v).split('-')
                        row[key+'m'] = number(pair[0])
                        row[key+'a'] = number(pair[1]) if len(pair)>1 else 0
                    elif key == 'min':
                        try:
                            parts=str(v).split(':')
                            row[key] = float(parts[0]) + (float(parts[1])/60 if len(parts)>1 else 0)
                        except (ValueError,TypeError): row[key]=0
                    else: row[key]=number(v)
                rows.append(row)
    return rows,team_rows


def number(v):
    try: return float(str(v).replace(',',''))
    except (ValueError,TypeError): return 0.0


def roster_positions(team_ids, season):
    """Resolve missing ESPN box-score positions from team rosters, best effort."""
    found = {}
    for tid in sorted(set(team_ids)):
        if not tid or tid == 'None':
            continue
        try:
            data = fetch(f'/teams/{tid}/roster', {'season': season})
            groups = data.get('athletes', [])
            for item in groups:
                athletes = item.get('items', []) if isinstance(item, dict) and 'items' in item else [item]
                for athlete in athletes:
                    if not isinstance(athlete, dict):
                        continue
                    position = athlete.get('position') or {}
                    abbr = position.get('abbreviation', '') if isinstance(position, dict) else str(position)
                    if abbr:
                        found[str(athlete.get('id'))] = abbr.upper()
        except (requests.RequestException, ValueError, KeyError):
            continue
    return found


def normalize_position(pos):
    pos = str(pos or '').upper().strip()
    aliases = {'POINT GUARD':'PG','SHOOTING GUARD':'SG','SMALL FORWARD':'SF',
               'POWER FORWARD':'PF','CENTER':'C'}
    return aliases.get(pos, pos) if pos in ('PG','SG','SF','PF','C') or pos in aliases else ''


# ESPN NBA franchise IDs. International exhibition opponents are not NBA teams.
NBA_TEAM_IDS = frozenset(str(i) for i in range(1, 31))


def nba_only_records(frame):
    """Keep records from games where BOTH teams are NBA franchises."""
    if frame.empty:
        return frame.copy()
    own = frame['team_id'].astype(str).str.strip().str.replace(r'\\.0$', '', regex=True)
    opponent = frame['opponent_id'].astype(str).str.strip().str.replace(r'\\.0$', '', regex=True)
    return frame.loc[own.isin(NBA_TEAM_IDS) & opponent.isin(NBA_TEAM_IDS)].copy()


def load(season, season_type=2, progress=None, mode='update'):
    """mode=cached never contacts ESPN; update fetches recent changes; full refetches all."""
    ids=game_ids(season,season_type,mode,progress)
    players=[]; teams=[]; errors=[]
    with connect() as c:
        scoreboard_types = {}
        for (raw,) in c.execute('SELECT payload FROM scoreboard_days'):
            try:
                for event in json.loads(raw).get('events', []):
                    scoreboard_types[str(event.get('id'))] = espn_season_type(event)
            except (ValueError, TypeError):
                continue
        for i,gid in enumerate(ids):
            found=c.execute('SELECT payload FROM games WHERE id=?',(gid,)).fetchone()
            try:
                if found and mode!='full':
                    data=json.loads(found[0])
                elif mode=='cached':
                    errors.append(gid)
                    continue
                else:
                    data=fetch('/summary',{'event':gid})
                    c.execute('INSERT OR REPLACE INTO games VALUES (?,?)',(gid,json.dumps(data)))
                    c.commit()
                    time.sleep(0.75)
                actual_type = espn_season_type(data)
                if actual_type is None:
                    actual_type = scoreboard_types.get(str(gid))
                if actual_type != season_type:
                    # Do not count preseason, exhibition or unclassified games.
                    continue
                p,t=parse_game(data,gid)
                if not t or not p: errors.append(gid)
                players.extend(p);teams.extend(t)
            except (requests.RequestException,ValueError,KeyError) as exc:
                errors.append(gid)
            if progress: progress(.25+.75*(i+1)/max(len(ids),1),f'Loading saved box scores: {i+1}/{len(ids)}')
    # Avoid roster API calls on every launch: user-provided ID-to-position CSV
    # already supplies 2026-27 positions. Other seasons retain ESPN positions.
    for r in players:
        r['position']=normalize_position(r.get('position'))
    return nba_only_records(pd.DataFrame(players)),nba_only_records(pd.DataFrame(teams)),len(ids),errors


def averages(frame):
    if frame.empty: return pd.DataFrame()
    cols=['pts','reb','ast','stl','blk','tov','threem','threea','fgm','fga','ftm','fta','min']
    out=frame.groupby('player',as_index=False).agg(games=('game_id','nunique'),**{x:(x,'mean') for x in cols})
    out['fg_pct']=100*frame.groupby('player')['fgm'].sum().to_numpy()/frame.groupby('player')['fga'].sum().replace(0,float('nan')).to_numpy()
    out['three_pct']=100*frame.groupby('player')['threem'].sum().to_numpy()/frame.groupby('player')['threea'].sum().replace(0,float('nan')).to_numpy()
    return out.round(2)


def _injury_text(value):
    if isinstance(value, dict):
        return str(value.get('displayName') or value.get('description') or value.get('name') or value.get('detail') or value.get('status') or '')
    return str(value or '')


def nba_injury_reports():
    """Retrieve ESPN injury listings, resolving the team from several ESPN shapes.

    ESPN often puts the franchise ID directly on each team group rather than
    inside group['team']. An empty feed is not proof that players are available.
    """
    payload = fetch('/injuries')
    groups = payload.get('injuries')
    if not isinstance(groups, list):
        raise ValueError('ESPN injury response has no team injury groups')
    reports = {}
    diagnostics = {'groups': len(groups), 'entries': 0, 'matched': 0,
                   'unmatched_groups': [], 'team_ids': []}
    for group in groups:
        if not isinstance(group, dict):
            continue
        team = group.get('team') or {}
        if not isinstance(team, dict):
            team = {}
        # League-wide ESPN feed commonly has {id, displayName, injuries}
        # directly at the group level.
        team_id = str(team.get('id') or group.get('id') or
                      group.get('teamId') or '').strip()
        if team_id.endswith('.0'):
            team_id = team_id[:-2]
        entries = group.get('injuries') or group.get('items') or []
        if not isinstance(entries, list):
            continue
        diagnostics['entries'] += len(entries)
        if not team_id:
            diagnostics['unmatched_groups'].append(str(group.get('displayName') or
                                                     group.get('name') or 'unknown'))
            continue
        diagnostics['team_ids'].append(team_id)
        rows = reports.setdefault(team_id, [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            athlete = entry.get('athlete') or entry.get('player') or {}
            if isinstance(athlete, str):
                athlete = {'displayName': athlete}
            if not isinstance(athlete, dict):
                athlete = {}
            name = (athlete.get('displayName') or athlete.get('fullName') or
                    entry.get('displayName') or entry.get('name'))
            if not name:
                continue
            status = (_injury_text(entry.get('status')) or
                      _injury_text(entry.get('injuryStatus')) or
                      _injury_text((entry.get('fantasy') or {}).get('status')) or
                      'Not specified')
            injury = (_injury_text(entry.get('longComment')) or
                      _injury_text(entry.get('shortComment')) or
                      _injury_text(entry.get('detail')) or
                      _injury_text(entry.get('details')) or
                      _injury_text(entry.get('description')) or
                      _injury_text(entry.get('type')) or
                      'Not specified')
            rows.append({'Player': str(name), 'Status': status,
                         'Injury / notes': injury,
                         'Reported': str(entry.get('date') or '')[:10]})
            diagnostics['matched'] += 1
    if diagnostics['entries'] and not diagnostics['matched']:
        raise ValueError('ESPN returned injury entries, but none could be parsed. '
                         'Team groups: ' + str(diagnostics['unmatched_groups'][:8]))
    if not diagnostics['entries']:
        raise ValueError('ESPN returned zero injury entries across the league. '
                         'This is not confirmation that everyone is available.')
    return reports, str(payload.get('timestamp') or ''), diagnostics


def team_injuries(team_id):
    """Compatibility helper; use nba_injury_reports for two-team matchups."""
    reports, _, _ = nba_injury_reports()
    return reports.get(str(team_id).strip(), [])
