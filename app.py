import streamlit as st
import pandas as pd
import datetime as dt
from espn import load, averages, sydney_games, cache_status, nba_only_records, nba_injury_reports
from positions import apply_player_positions, CSV as POSITIONS_CSV
from zoneinfo import ZoneInfo

st.set_page_config(page_title='NBA Analytics | Sixers Edition',page_icon='🏀',layout='wide', initial_sidebar_state='collapsed')

# Presentation-only redesign: the ESPN data pipeline and analytics remain unchanged.
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp, [data-testid="stAppViewContainer"] {background: #0B1426; color: #F8FAFC;}
[data-testid="stHeader"] {background: rgba(11,20,38,.92);}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none !important;}

.block-container {padding-top: 1.65rem; padding-bottom: 3rem; max-width: 1550px;}
h1,h2,h3 {color:#FFFFFF !important; letter-spacing:-.025em;}
h1 {font-weight:800 !important;}
h2,h3 {border-left: 4px solid #ED174C; padding-left: .65rem;}
p, label, [data-testid="stCaptionContainer"] {color:#C9D6E8;}
[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {background:#14233B; border-radius:14px;}
[data-testid="stMetric"] {background:#14233B; border:1px solid #294160; border-top:3px solid #006BB6; border-radius:12px; padding:14px 18px;}
[data-testid="stMetricValue"] {color:#FFFFFF;}
[data-testid="stMetricLabel"] {color:#B7C9DF;}
.stButton > button[kind="primary"] {background:#006BB6; color:white; border:1px solid #2987D1; font-weight:700;}
.stButton > button[kind="primary"]:hover {background:#087DD0; border-color:#FFFFFF;}
.stButton > button[kind="secondary"] {background:#192C48; color:#FFFFFF; border:1px solid #365273;}
.stButton > button[kind="secondary"]:hover {border-color:#ED174C; color:#FFFFFF;}
[data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid #2B4261; border-radius:12px; overflow:hidden;}
[data-testid="stAlert"] {border-radius:12px;}
[data-baseweb="tab-list"] {gap:10px;}
button[data-baseweb="tab"] {color:#B7C9DF; background:#172841; border-radius:9px 9px 0 0;}
button[data-baseweb="tab"][aria-selected="true"] {color:white; border-bottom:3px solid #ED174C;}
[role="radiogroup"] label:has(input:checked) {background:#006BB6; border-bottom:3px solid #ED174C; border-radius:8px;}
[role="radiogroup"] label {padding:7px 10px;}
.sixers-topbrand {font-size:1.35rem;font-weight:850;color:#FFFFFF;letter-spacing:.03em;margin-bottom:14px;}
.sixers-topbrand span {font-size:.7rem;font-weight:700;color:#ED174C;margin-left:12px;letter-spacing:.12em;}
.sixers-hero {padding:23px 27px; border:1px solid #284362; border-left:5px solid #ED174C; border-radius:16px; background:linear-gradient(115deg,#153C69 0%,#13243E 55%,#25182E 100%); margin-bottom:20px;}
.sixers-eyebrow {font-size:.75rem; font-weight:800; letter-spacing:.19em; color:#F4A2B8; margin-bottom:5px;}
.sixers-title {font-size:clamp(1.55rem,3vw,2.5rem); font-weight:850; color:#FFFFFF; line-height:1.2;}
.sixers-subtitle {color:#D3DFEF; font-size:.94rem; margin-top:6px;}
.sixers-game {background:#14233B; border:1px solid #2B4261; border-left:4px solid #006BB6; border-radius:12px; padding:17px 20px; margin:5px 0; min-height:94px;}
/* The whole matchup card is a native Streamlit button, fully clickable. */
[class*="st-key-matchup_card_"] button {
    width:100%; min-height:94px; padding:18px 22px;
    background:#14233B !important; color:#FFFFFF !important;
    border:1px solid #2B4261 !important; border-left:4px solid #006BB6 !important;
    border-radius:12px !important; text-align:left !important;
    justify-content:flex-start !important; transition:background .15s,border-color .15s,transform .15s;
}
[class*="st-key-matchup_card_"] button:hover,
[class*="st-key-matchup_card_"] button:focus-visible {
    background:#1B3556 !important; border-color:#ED174C !important;
    border-left-color:#ED174C !important; transform:translateY(-1px);
}
[class*="st-key-matchup_card_"] button p {
    color:#FFFFFF !important; text-align:left !important;
    white-space:pre-line !important; line-height:1.75 !important;
    font-size:1rem !important; font-weight:650 !important;
}
.sixers-game-name {color:white; font-size:1.1rem; font-weight:750;}
.sixers-game-meta {color:#B9C9DF; font-size:.84rem; margin-top:7px;}
.matchup-pos-scroll {border-color:#2B4261 !important;}
.matchup-pos th,.matchup-pos td {background:#14233B !important; color:#F8FAFC !important; border-color:#2B4261 !important;}
.matchup-pos th {background:#1C3656 !important;}
.matchup-pos .positive {color:#FF7897 !important;}
.matchup-pos .negative {color:#61D6AA !important;}
@media(max-width:700px){.block-container{padding:1rem .8rem}.sixers-hero{padding:18px}.sixers-game-name{font-size:.96rem}}
</style>
""", unsafe_allow_html=True)

def page_banner(title, subtitle):
    from html import escape
    st.markdown(f'<div class="sixers-hero"><div class="sixers-eyebrow">NBA ANALYTICS • SIXERS EDITION</div><div class="sixers-title">{escape(title)}</div><div class="sixers-subtitle">{escape(subtitle)}</div></div>', unsafe_allow_html=True)


# NBA franchise ESPN team IDs (exclude exhibition opponents such as London Lions).
NBA_TEAM_IDS = {str(i) for i in range(1, 31)}

def nba_only(frame):
    if frame.empty:
        return frame.copy()
    ids = frame['team_id'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    opp_ids = frame['opponent_id'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    return frame.loc[ids.isin(NBA_TEAM_IDS) & opp_ids.isin(NBA_TEAM_IDS)].copy()

# Main navigation and controls are across the top; settings live in a popover.
# Render navigation before the data loading logic so matchup callbacks remain valid.
nav_items = ['Today’s games', 'Game matchup', 'Statistics', 'Team rankings', 'Projections']
if st.session_state.get('page') not in nav_items:
    st.session_state['page'] = nav_items[0]

st.markdown('<div class="sixers-topbrand">🏀 NBA ANALYTICS <span>RED • BLUE • WHITE</span></div>', unsafe_allow_html=True)
nav_col, update_col, settings_col = st.columns([6, 1.6, 1.15], vertical_alignment='bottom')
with nav_col:
    st.radio('Navigation', nav_items, key='page', horizontal=True, label_visibility='collapsed')
with update_col:
    go = st.button('↻ Update latest games', type='primary', use_container_width=True)
with settings_col:
    with st.popover('⚙ Settings', use_container_width=True):
        st.markdown('### Data settings')
        sydney_now = dt.datetime.now(ZoneInfo('Australia/Sydney')).date()
        current_end_year = sydney_now.year + 1 if sydney_now.month >= 10 else sydney_now.year
        season_labels = [f'{year-1}–{str(year)[-2:]}' for year in range(current_end_year, 2014, -1)]
        season_label = st.selectbox('NBA season (October–June)', season_labels, key='selected_season')
        season_type = st.selectbox('Season type', ['Regular season', 'Playoffs'], key='selected_season_type')
        season = int(season_label[:4]) + 1
        season_key = (int(season), 2 if season_type == 'Regular season' else 3)
        status = cache_status(*season_key)
        st.caption(f"Saved: {status['boxscores_saved']}/{status['games_found']} game box scores · scanned through {status['scanned_through'] or 'never'}")
        st.caption('SQLite file: nba_cache.sqlite (kept beside the dashboard).')
        full = st.button('Full season refresh', use_container_width=True)
        st.caption('Saved data opens automatically. Update latest games checks recent/new dates; full refresh re-downloads everything.')

page_banner('NBA Analytics', 'Game-by-game insights • ESPN data • Philadelphia-inspired design')

# On first launch or when changing seasons, read the SQLite cache without network.
if st.session_state.get('loaded_key') != season_key:
    try:
        cached=cache_status(*season_key)
        if cached['games_found']:
            p,t,n,errors=load(*season_key,mode='cached')
            st.session_state['data']=(p,t,n,errors,season,season_type)
        else:
            st.session_state.pop('data',None)
        st.session_state['loaded_key']=season_key
    except Exception as exc:
        st.warning(f'Could not open saved season data: {exc}')
if go or full:
    progress=st.progress(0)
    try:
        p,t,n,errors=load(*season_key,progress=lambda x,msg:progress.progress(x,text=msg),mode='full' if full else 'update')
        st.session_state['data']=(p,t,n,errors,season,season_type)
        st.session_state['loaded_key']=season_key
        st.success(f'Saved {n} completed games locally. Future launches use the saved database.')
    except Exception as e:
        st.error(f'ESPN update failed (saved games are preserved): {e}')
    finally:
        progress.empty()

# Navigation changes must happen in callbacks, before Streamlit creates the radio widget.
def open_matchup(game_id):
    st.session_state['selected_game_id'] = game_id
    st.session_state['page'] = 'Game matchup'

def navigate_to(page, clear_game=False):
    if clear_game:
        st.session_state.pop('selected_game_id', None)
    st.session_state['page'] = page

if st.session_state['page'] == 'Today’s games':
    page_banner('Game Day', 'NBA schedule • Australia/Sydney time')
    sydney_today = dt.datetime.now(ZoneInfo('Australia/Sydney')).date()
    selected_day = st.radio('Show games for', ['Today', 'Tomorrow'], horizontal=True,
                            key='schedule_day_choice')
    schedule_date = sydney_today + dt.timedelta(days=1 if selected_day == 'Tomorrow' else 0)
    st.caption(f'{schedule_date.strftime("%A %d %B %Y")} · Australia/Sydney (AEDT/AEST automatically)')
    # Reuse the same schedule list consumed by the Game matchup page.
    # Refresh when the user switches day, not only when the local date changes.
    if (st.button('Refresh games') or 'today_games' not in st.session_state
            or st.session_state.get('today_date') != str(schedule_date)):
        try:
            st.session_state['today_games'] = sydney_games(schedule_date)
            st.session_state['today_date'] = str(schedule_date)
            st.session_state.pop('today_error', None)
        except Exception as exc:
            st.session_state['today_games'] = []
            st.session_state['today_date'] = str(schedule_date)
            st.session_state['today_error'] = str(exc)
    if st.session_state.get('today_error'):
        st.error('Unable to load the schedule: ' + st.session_state['today_error'])
    elif not st.session_state.get('today_games'):
        st.info('No NBA games scheduled for this Sydney calendar date.')
    else:
        st.caption('Select a matchup to open its dedicated analysis page.')
        for idx, game in enumerate(st.session_state['today_games']):
            # Make the entire matchup card clickable; no separate View matchup button.
            st.button(
                f"{game['Away']}  vs  {game['Home']}\n{game['Sydney time']} · {game['Status']}",
                key=f"matchup_card_{idx}",
                on_click=open_matchup,
                args=(game['ESPN game ID'],),
                use_container_width=True,
            )
    st.stop()

if st.session_state['page'] == 'Game matchup':
    if not st.session_state.get('selected_game_id'):
        st.info('Choose a game on the NBA games page (Today or Tomorrow) to see its matchup analysis.')
        st.button('Go to today’s games', on_click=navigate_to, args=('Today’s games',))
        st.stop()
    selected_game=next((g for g in st.session_state.get('today_games',[]) if g['ESPN game ID']==st.session_state.get('selected_game_id')),None)
    if selected_game:
        st.divider()
        page_banner(f"{selected_game['Away']} vs {selected_game['Home']}", 'Head-to-head matchup intelligence')
        st.caption(f"{selected_game['Sydney time']} Sydney time · {selected_game['Status']} · ESPN game {selected_game['ESPN game ID']}")
        st.button('← Close game analysis', on_click=navigate_to,
                  args=('Today’s games', True))
        if 'data' not in st.session_state:
            st.info('Click **Update latest games** at the top to download this season. Afterwards it loads automatically from SQLite.')
            st.stop()
        gp,gt,gn,ge,gy,gtype=st.session_state['data']
        gp, gt = nba_only_records(gp), nba_only_records(gt)
        try:
            gp,report=apply_player_positions(gp,gy)
        except (ValueError,OSError) as exc:
            st.error(f'Position database error: {exc}')
            st.stop()
        for metric in ['pts','reb','ast','stl','blk','tov','threem','threea','fgm','fga','ftm','fta','min']:
            gp[metric]=pd.to_numeric(gp[metric],errors='coerce').fillna(0)
        away,home=selected_game['Away'],selected_game['Home']
        game_teams=[away,home]
        if gp.empty or gt.empty or not all(team in set(gt.team) for team in game_teams):
            st.warning('The loaded season does not have enough historical data for both teams. Refresh the current season from the sidebar.')
            st.stop()
        # Conference positions estimated from completed NBA-only games.
        # Official NBA standings may differ due to head-to-head tiebreakers.
        east_ids = {'1','2','4','5','8','11','14','15','17','18','19','20','27','28','30'}
        records = gt.copy()
        records['team_id'] = records['team_id'].astype(str).str.strip()
        records['win'] = records['points'] > records['opp_points']
        records['loss'] = records['points'] < records['opp_points']
        records['margin'] = records['points'] - records['opp_points']
        standings = records.groupby('team_id', as_index=False).agg(
            Wins=('win','sum'), Losses=('loss','sum'), Margin=('margin','mean'))
        standings['Played'] = standings['Wins'] + standings['Losses']
        standings['Win pct'] = standings['Wins'] / standings['Played'].replace(0, float('nan'))
        standings['Conference'] = standings['team_id'].map(
            lambda team_id: 'Eastern' if team_id in east_ids else 'Western')
        standings = standings.sort_values(
            ['Conference','Win pct','Wins','Margin'], ascending=[True,False,False,False])
        standings['Conference place'] = standings.groupby('Conference').cumcount() + 1
        standings_by_id = standings.set_index('team_id')

        st.subheader('ESPN injury report')
        st.caption('Current league-wide ESPN injury listings, not a confirmed game-day inactive list. '
                   'Out means reported out; Questionable and Doubtful remain uncertain.')
        if st.button('Refresh injury report', key='refresh_matchup_injuries'):
            st.session_state.pop('matchup_injury_report', None)
        if 'matchup_injury_report' not in st.session_state:
            try:
                reports, updated_at, diagnostics = nba_injury_reports()
                st.session_state['matchup_injury_report'] = {
                    'reports': reports, 'updated_at': updated_at, 'error': None, 'diagnostics': diagnostics}
            except Exception as exc:
                st.session_state['matchup_injury_report'] = {
                    'reports': {}, 'updated_at': '', 'error': str(exc)}
        injury_data = st.session_state['matchup_injury_report']
        if injury_data['error']:
            st.warning('Unable to retrieve ESPN league-wide injuries: ' + injury_data['error'])
        else:
            if injury_data['updated_at']:
                st.caption('ESPN feed updated: ' + injury_data['updated_at'] + ' (UTC)')
            diag = injury_data.get('diagnostics', {})
            with st.expander('Injury feed diagnostics'):
                st.write(f"ESPN team groups: {diag.get('groups', 0)} · "
                         f"Injury entries: {diag.get('entries', 0)} · "
                         f"Parsed players: {diag.get('matched', 0)}")
                st.write('ESPN team IDs in feed:', ', '.join(diag.get('team_ids', [])))
                if diag.get('unmatched_groups'):
                    st.write('Unmatched team groups:', diag['unmatched_groups'])
            injury_cols = st.columns(2)
            for column, team in zip(injury_cols, game_teams):
                with column:
                    st.markdown(f'**{team}**')
                    own_rows = gt.loc[gt['team'].eq(team)]
                    if own_rows.empty:
                        st.warning('Cannot identify this team in the saved season.')
                        continue
                    team_id = str(own_rows.iloc[0]['team_id']).strip()
                    rows = injury_data['reports'].get(team_id, [])
                    if rows:
                        status_order = {'out': 0, 'doubtful': 1, 'questionable': 2, 'day-to-day': 3}
                        rows = sorted(rows, key=lambda r: status_order.get(r['Status'].lower(), 4))
                        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    else:
                        st.warning('No injuries matched to this team in ESPN’s current feed. This does NOT mean everyone is available. '
                                'This does not confirm everyone is available.')
        st.caption('ESPN injury listings may differ from the official game-day injury report. '
                   'Injuries are not yet factored into player projections.')

        st.subheader('Team matchup overview')
        overview=[]
        for team,opp in [(away,home),(home,away)]:
            own=gt[gt.team==team].sort_values('date',ascending=False)
            defend=gt[gt.team==opp].sort_values('date',ascending=False)
            team_id = str(own.iloc[0]['team_id']).strip()
            standing = standings_by_id.loc[team_id] if team_id in standings_by_id.index else None
            overview.append({'Team':team,
                             'W–L': f"{int(standing['Wins'])}–{int(standing['Losses'])}" if standing is not None else '—',
                             'Conference': standing['Conference'] if standing is not None else '—',
                             'Conf. place*': f"#{int(standing['Conference place'])}" if standing is not None else '—',
                             'Win %': round(standing['Win pct']*100,1) if standing is not None else None,
                             'Games':len(own),'Points scored / game':round(own.points.mean(),1),
                             'Points allowed / game':round(own.opp_points.mean(),1),
                             'Opponent allows / game':round(defend.opp_points.mean(),1),
                             'Estimated points*':round((.65*own.points.mean()+.35*own.head(10).points.mean()+.65*defend.opp_points.mean()+.35*defend.head(10).opp_points.mean())/2,1) if len(own)>=3 and len(defend)>=3 else None})
        st.dataframe(pd.DataFrame(overview),hide_index=True,use_container_width=True)
        st.caption('*Experimental estimate based on season and recent scoring plus opponent points allowed. Not a validated forecast.')
        st.caption('*Conference positions are estimated from the completed NBA games in your local database; official NBA tiebreakers may differ.')

        st.subheader('Last 5 games & back-to-back schedule')
        st.caption('Results are shown from each team’s perspective. Consecutive calendar dates indicate a back-to-back.')
        matchup_date = dt.date.fromisoformat(selected_game.get('Sydney date', dt.datetime.now(ZoneInfo('Australia/Sydney')).date().isoformat()))
        for team in game_teams:
            history = gt.loc[gt['team'].eq(team)].copy()
            history['game_date'] = pd.to_datetime(history['date'], errors='coerce').dt.date
            history = history.loc[history['game_date'].notna() & (history['game_date'] < matchup_date)]
            history = history.sort_values(['game_date','game_id'], ascending=False).drop_duplicates('game_id')
            recent = history.head(5)
            st.markdown(f'**{team}**')
            if recent.empty:
                st.info('No earlier completed NBA games in the saved season.')
                continue
            latest_date = recent.iloc[0]['game_date']
            days_between = (matchup_date - latest_date).days
            st.caption(
                f'Last game: {latest_date:%d %b %Y} · '
                + ('Back-to-back today (0 rest days)' if days_between == 1 else
                   f'{max(days_between - 1, 0)} full rest day(s) before this matchup')
            )
            recent_rows = []
            recent_chronological = history.head(6)
            dates = list(recent_chronological['game_date'])
            for index, (_, game) in enumerate(recent.iterrows()):
                day = game['game_date']
                prior_day = dates[index+1] if index+1 < len(dates) else None
                b2b = (day - prior_day).days == 1 if prior_day else False
                recent_rows.append({
                    'Date': day.strftime('%d %b %Y'),
                    'Opponent': ('vs ' if bool(game['home']) else '@ ') + str(game['opponent']),
                    'Score': f"{int(game['points'])}–{int(game['opp_points'])}",
                    'Result': 'W' if game['points'] > game['opp_points'] else 'L' if game['points'] < game['opp_points'] else 'T',
                    'Rest days before': max((day-prior_day).days-1, 0) if prior_day else '—',
                    'Back-to-back': 'Yes' if b2b else 'No' if prior_day else '—',
                })
            st.dataframe(pd.DataFrame(recent_rows), hide_index=True, use_container_width=True)
        st.caption('All displayed game dates and rest-day gaps use Australia/Sydney time (AEDT/AEST automatically). Rest days use calendar dates, not travel or hours between tipoffs.')

        st.subheader('Team rankings across all statistics')
        st.caption('Each statistic shows the team’s average per game and league rank on offence and defence. Offensive rank #1 = most produced; defensive rank #1 = least allowed.')
        matchup_metrics = {
            'Points': 'pts', 'Rebounds': 'reb', 'Assists': 'ast',
            '3-pointers made': 'threem', '3-pointers attempted': 'threea',
            'Steals': 'stl', 'Blocks': 'blk', 'Turnovers': 'tov',
            'Field goals made': 'fgm', 'Field goals attempted': 'fga',
            'Free throws made': 'ftm', 'Free throws attempted': 'fta',
        }
        selected_metric = st.selectbox('Choose team ranking statistic', list(matchup_metrics), key='matchup_team_metric')
        stat_col = matchup_metrics[selected_metric]
        ranking_gt = nba_only(gt)
        ranking_gp = nba_only(gp)
        # ESPN team IDs are stable; display names can vary and must not be used
        # as the grouping key for league-wide rankings.
        # ESPN's 30 NBA franchise IDs are 1–30. Exclude exhibition opponents
        # such as London Lions, even if they appear in the saved season games.
        nba_team_ids = {str(i) for i in range(1, 31)}
        valid_team_ids = set(ranking_gt['team_id'].dropna().astype(str).str.strip()) & nba_team_ids
        # Match the matchup teams using the ESPN IDs from their team-game rows.
        team_ids_by_name = (ranking_gt.dropna(subset=['team_id', 'team'])
                            .drop_duplicates('team')
                            .set_index('team')['team_id'].astype(str).to_dict())
        if stat_col == 'pts':
            # Points come from team scores, not player box-score sums.
            team_stats = ranking_gt.copy()
            team_stats['team_id'] = team_stats['team_id'].astype(str)
            produced = team_stats.groupby('team_id')['points'].mean()
            conceded = team_stats.groupby('team_id')['opp_points'].mean()
        else:
            player_games = ranking_gp.copy()
            player_games['team_id'] = player_games['team_id'].astype(str)
            player_games['opponent_id'] = player_games['opponent_id'].astype(str)
            # One row per team per game, regardless of roster name variations.
            game_totals = (player_games.groupby(['game_id', 'team_id', 'opponent_id'], as_index=False)
                           [stat_col].sum())
            produced = game_totals.groupby('team_id')[stat_col].mean()
            # Opponent conceded stats are keyed by the *defending* ESPN team ID.
            conceded = game_totals.groupby('opponent_id')[stat_col].mean()
        league_metric = pd.DataFrame({'Produced': produced, 'Allowed': conceded})
        league_metric.index = league_metric.index.astype(str).str.strip()
        league_metric = league_metric.loc[league_metric.index.isin(valid_team_ids)]
        # Exclude incomplete entries from ranks rather than assigning fabricated zeros.
        league_metric['Offence rank'] = league_metric['Produced'].rank(ascending=False, method='min')
        league_metric['Defence rank'] = league_metric['Allowed'].rank(ascending=True, method='min')
        league_metric['Allowed rank (most = 1)'] = league_metric['Allowed'].rank(ascending=False, method='min')
        metric_rows = []
        for team_name in game_teams:
            team_id = team_ids_by_name.get(team_name)
            if team_id not in league_metric.index:
                continue
            r = league_metric.loc[team_id]
            metric_rows.append({
                'Team': team_name,
                f'{selected_metric} / game': round(r['Produced'], 1) if pd.notna(r['Produced']) else None,
                'Offence rank': int(r['Offence rank']) if pd.notna(r['Offence rank']) else None,
                f'{selected_metric} allowed / game': round(r['Allowed'], 1) if pd.notna(r['Allowed']) else None,
                'Defence rank': int(r['Defence rank']) if pd.notna(r['Defence rank']) else None,
                'Allowed rank (most = 1)': int(r['Allowed rank (most = 1)']) if pd.notna(r['Allowed rank (most = 1)']) else None,
            })
        st.dataframe(pd.DataFrame(metric_rows), hide_index=True, use_container_width=True)
        if len(league_metric) < 30:
            st.warning(f'Rankings currently include {len(league_metric)} NBA teams with data (out of 30).')
        st.caption('Non-point metrics use available ESPN player box scores. Missing player data can affect averages.')
        st.subheader('Defence against each position')
        pos_stats={'pts':'PTS','reb':'REB','ast':'AST','threem':'3PM','stl':'STL','blk':'BLK'}
        positions=['PG','SG','SF','PF','C']
        allowed_rows=[]
        for defending in [away,home]:
            q=gp[(gp.opponent==defending)&(gp['min']>0)&(gp.position.isin(positions))]
            for position in positions:
                subset=q[q.position==position]
                row={'Defending team':defending,'Position':position,'Games':subset.game_id.nunique()}
                for stat,label in pos_stats.items():
                    row[f'{label} allowed / game']=round(subset.groupby('game_id')[stat].sum().mean(),1) if not subset.empty else None
                allowed_rows.append(row)
        # Compare each opponent player's game production with that same player's
        # season average, summed by position and game (as on the Statistics page).
        baseline = gp[gp['min'] > 0].groupby('player_id')[list(pos_stats)].mean()
        for defending in [away, home]:
            opponents = gp[(gp.opponent == defending) & (gp['min'] > 0) & gp.position.isin(positions)].copy()
            for stat, label in pos_stats.items():
                opponents[f'diff_{stat}'] = opponents[stat] - opponents.player_id.map(baseline[stat])
            for position in positions:
                part = opponents[opponents.position == position]
                row = next(r for r in allowed_rows if r['Defending team'] == defending and r['Position'] == position)
                for stat, label in pos_stats.items():
                    row[f'{label} vs normal'] = (round(part.groupby('game_id')[f'diff_{stat}'].sum().mean(), 2)
                                                   if not part.empty else None)
        # Keep each allowed average immediately beside its comparison to normal.
        position_columns = ['Defending team', 'Position', 'Games']
        for label in pos_stats.values():
            position_columns.extend([f'{label} allowed / game', f'{label} vs normal'])
        # Streamlit's native dataframe does not reliably freeze a non-index column.
        # Use a horizontally scrollable HTML table with sticky Team and Position columns.
        from html import escape as html_escape
        position_table = pd.DataFrame(allowed_rows)[position_columns]
        def display_cell(value, signed=False):
            if pd.isna(value):
                return '—'
            if signed:
                return f'{value:+.2f}'
            return str(value)
        headers = ''.join(f'<th>{html_escape(str(col))}</th>' for col in position_table.columns)
        body_rows = []
        for _, record in position_table.iterrows():
            cells = []
            for col in position_table.columns:
                signed = col.endswith('vs normal')
                value = display_cell(record[col], signed=signed)
                css = ' class="positive"' if signed and pd.notna(record[col]) and record[col] > 0 else (' class="negative"' if signed and pd.notna(record[col]) and record[col] < 0 else '')
                cells.append(f'<td{css}>{html_escape(value)}</td>')
            body_rows.append('<tr>' + ''.join(cells) + '</tr>')
        table_html = '''
<style>
.matchup-pos-scroll {overflow-x:auto;max-width:100%;border:1px solid #2B4261;border-radius:8px;}
.matchup-pos {border-collapse:separate;border-spacing:0;white-space:nowrap;font:14px sans-serif;min-width:1600px;width:100%;}
.matchup-pos th,.matchup-pos td {padding:10px 12px;border-bottom:1px solid #d4d8df;border-right:1px solid #e5e7eb;background:#fff;color:#222;text-align:right;}
.matchup-pos th {background:#f1f3f6;position:sticky;top:0;z-index:2;font-weight:600;}
.matchup-pos th:first-child,.matchup-pos td:first-child {position:sticky;left:0;z-index:4;text-align:left;min-width:170px;}
.matchup-pos th:nth-child(2),.matchup-pos td:nth-child(2) {position:sticky;left:170px;z-index:4;text-align:left;min-width:80px;font-weight:700;box-shadow:3px 0 5px -4px #555;}
.matchup-pos th:first-child,.matchup-pos th:nth-child(2) {z-index:5;background:#e9edf3;}
.matchup-pos tr:nth-child(even) td {background:#f8fafc;}
.matchup-pos tr:nth-child(even) td:first-child,.matchup-pos tr:nth-child(even) td:nth-child(2) {background:#f8fafc;}
.matchup-pos .positive {color:#ad3030;font-weight:600;}
.matchup-pos .negative {color:#16794a;font-weight:600;}
</style>
<div class="matchup-pos-scroll"><table class="matchup-pos"><thead><tr>''' + headers + '''</tr></thead><tbody>''' + ''.join(body_rows) + '''</tbody></table></div>
'''
        st.markdown(table_html, unsafe_allow_html=True)

        st.caption('Allowed = combined opponent production at that position per game. Vs normal = difference from those same players’ season averages; positive means more allowed than normal, negative means less. Positions come from the depth chart, not actual defensive assignments.')
        st.subheader('Player matchup projections')
        window=st.selectbox('Recent games used for projections',[5,10,20],index=1,key='game_recent_window')
        rows=[]
        for team,opponent in [(away,home),(home,away)]:
            candidates=gp[(gp.team==team)&(gp['min']>0)].sort_values('date',ascending=False)
            # Limit to players appearing in the most recent team game to avoid including former teammates.
            team_games=gt[gt.team==team].sort_values('date',ascending=False)
            if team_games.empty:continue
            latest_id=str(team_games.iloc[0].game_id)
            active=candidates[candidates.game_id.astype(str)==latest_id].player_id.dropna().unique()
            for pid in active:
                history=candidates[candidates.player_id==pid].sort_values(['date','game_id'],ascending=False)
                if len(history)<3:continue
                position=str(history.iloc[0].position)
                opponent_pos=gp[(gp.opponent==opponent)&(gp.position==position)&(gp['min']>0)]
                league_pos=gp[(gp.position==position)&(gp['min']>0)]
                h2h=history[history.opponent==opponent]
                row={'Team':team,'Player':history.iloc[0].player,'Pos':position,'Games':len(history)}
                for stat,label in {'pts':'PTS','reb':'REB','ast':'AST','threem':'3PM','stl':'STL','blk':'BLK'}.items():
                    base=.65*history[stat].mean()+.35*history.head(window)[stat].mean()
                    weight=min(.15,len(h2h)/(len(h2h)+15))
                    base=(1-weight)*base+weight*(h2h[stat].mean() if len(h2h) else base)
                    o=opponent_pos[stat].mean()
                    l=league_pos[stat].mean()
                    ratio=o/l if pd.notna(o) and pd.notna(l) and l>0 else 1
                    effect=max(.75,min(1.25,1+len(opponent_pos)/(len(opponent_pos)+20)*(ratio-1)))
                    row[label]=round(max(0,base*effect),1)
                rows.append(row)
        if rows:
            projections=pd.DataFrame(rows)
            team_filter=st.segmented_control('Show players', ['Both',away,home],default='Both',key='game_team_filter')
            if team_filter!='Both':projections=projections[projections.Team==team_filter]
            st.dataframe(projections,hide_index=True,use_container_width=True)
            st.caption('Uses the same historical projection formula as the main dashboard. Players shown are from each team’s most recent recorded box score, not confirmed starters or injury-adjusted lineups.')
        else:
            st.info('Not enough player game history for projections.')
    if not selected_game:
        st.warning('The selected game is no longer in today’s schedule. Return to Today’s games and choose another matchup.')
    st.stop()

if 'data' not in st.session_state:
    st.info('No saved games for this season yet. Click **Update latest games** to download and save them once.')
    st.stop()
p,t,n,errors,loaded_season,loaded_type=st.session_state['data']
p, t = nba_only_records(p), nba_only_records(t)
try:
    p, position_report = apply_player_positions(p, loaded_season)
except (ValueError, OSError) as exc:
    st.error(f'Player positions CSV error: {exc}')
    st.stop()
st.caption(f"Position database: {position_report['matched_players']}/{position_report['total_players']} season players matched by ESPN ID; {position_report['unmatched_players']} use ESPN fallback.")
if position_report['conflicts']:
    st.warning(f"{position_report['conflicts']} conflicting player IDs in the position CSV were ignored.")
st.caption(f'{loaded_type} {loaded_season-1}–{str(loaded_season)[-2:]} • {len(t)//2} NBA games parsed / {n} saved ESPN events scanned • {len(p)} player-game records')
if errors: st.warning(f'{len(errors)} games had unavailable or incomplete player box scores and were excluded. Results may be incomplete.')
if p.empty or t.empty:
    st.warning('No completed games with player stats found for this selection.')
    st.stop()
for col in ['pts','reb','ast','stl','blk','tov','threem','threea','fgm','fga','ftm','fta','min']:
    p[col]=pd.to_numeric(p[col],errors='coerce').fillna(0)

def show(df):
    st.dataframe(df.round(2) if not df.empty else df,use_container_width=True,hide_index=True)

def filters(frame,key):
    options=['All games','Last 5','Last 10','Last 20','Home','Away']
    choice=st.selectbox('Sample',options,key=key)
    frame=frame.sort_values(['date','game_id'],ascending=False)
    if choice.startswith('Last'): frame=frame.head(int(choice.split()[1]))
    if choice=='Home':frame=frame[frame.home]
    if choice=='Away':frame=frame[~frame.home]
    return frame


if st.session_state['page'] == 'Statistics':
    page_banner('Player & Team Statistics', 'Position defence • player averages • opponent analysis')
    tab1,tab2,tab3,tab4=st.tabs(['Defense vs position','Player vs team','Player averages','Team & opponent'])
    with tab1:
        st.subheader('Stats allowed to opposing positions')
        defense=st.selectbox('Defending team',sorted(t.team.unique()),key='defense')
        st.caption('Uses the 2026–27 depth-chart position matched by ESPN player ID when available; otherwise ESPN position. This is not actual on-court defensive assignment.')
        q=p[(p.opponent==defense)&(p['min']>0)].copy()
        positions=['PG','SG','SF','PF','C']
        q['position']=q['position'].fillna('').astype(str).str.upper().str.strip()
        unknown=q[~q.position.isin(positions)]
        q=q[q.position.isin(positions)].copy()
        if q.empty:
            st.warning('No recognised positions were found. Try reloading the season to resolve missing positions from ESPN rosters.')
        else:
            stats={'pts':'PTS','reb':'REB','ast':'AST','threem':'3PM','stl':'STL','blk':'BLK'}
            # Baseline is each individual player's average across ALL games in the loaded season.
            # Comparing to the same players avoids confusing position-wide talent with defense.
            baseline=p[p['min']>0].groupby('player_id')[list(stats)].mean()
            for stat in stats:
                q[f'baseline_{stat}']=q['player_id'].map(baseline[stat])
                q[f'diff_{stat}']=q[stat]-q[f'baseline_{stat}']
            rows=[]
            for pos in positions:
                part=q[q.position==pos]
                row={'Position':pos,'Games':part.game_id.nunique()}
                for stat,label in stats.items():
                    if part.empty:
                        row[f'{label} allowed']=None
                        row[f'{label} vs normal']=None
                    else:
                        # Total positional production per game, including multiple players
                        # at the same listed position. Compare with those SAME players' usual
                        # per-game averages summed within each matchup.
                        per_game=part.groupby('game_id')[[stat,f'diff_{stat}']].sum()
                        row[f'{label} allowed']=round(per_game[stat].mean(),2)
                        row[f'{label} vs normal']=round(per_game[f'diff_{stat}'].mean(),2)
                rows.append(row)
            results=pd.DataFrame(rows)
            st.caption('Allowed = average combined production by players listed at that position per opponent game. Vs normal = average difference from those same players’ season averages. Positive means more allowed than normal; negative means less.')
            show(results)
            stat_choice=st.selectbox('Compare a statistic',list(stats.values()))
            st.bar_chart(results.set_index('Position')[[f'{stat_choice} allowed',f'{stat_choice} vs normal']])
            pos=st.selectbox('Explore individual performances',positions)
            detail=q[q.position==pos].copy()
            if detail.empty:
                st.info('No player records at this position. ESPN may not have supplied a roster position for these athletes.')
            else:
                cols=['date','player','team','pts','diff_pts','reb','diff_reb','ast','diff_ast','threem','diff_threem','min']
                show(detail[cols].rename(columns={'diff_pts':'PTS vs normal','diff_reb':'REB vs normal','diff_ast':'AST vs normal','diff_threem':'3PM vs normal'}).sort_values('date',ascending=False))
        if not unknown.empty:
            st.warning(f'{len(unknown)} player-game records still have unknown positions and were excluded. The position CSV or ESPN roster may be incomplete.')
            with st.expander('See players with missing positions'):
                show(unknown[['player','team','position']].drop_duplicates())
    with tab2:
        st.subheader('Player vs opposing team')
        player=st.selectbox('Player',sorted(p.player.unique()),key='player_match')
        opponent=st.selectbox('Opponent',sorted(t.team.unique()),key='opp_match')
        q=filters(p[(p.player==player)&(p.opponent==opponent)],'match_sample')
        if q.empty:st.info('No games found for this matchup and sample.')
        else:
            a,b,c,d=st.columns(4)
            a.metric('Games',q.game_id.nunique());b.metric('PPG',f'{q.pts.mean():.1f}');c.metric('RPG',f'{q.reb.mean():.1f}');d.metric('APG',f'{q.ast.mean():.1f}')
            show(q[['date','team','opponent','pts','reb','ast','stl','blk','threem','threea','min']])
    with tab3:
        st.subheader('Player season and recent averages')
        player=st.selectbox('Player',sorted(p.player.unique()),key='player_avg')
        q=filters(p[p.player==player],'player_sample')
        if q.empty:st.info('No games found.')
        else:
            a,b,c,d=st.columns(4)
            a.metric('PPG',f'{q.pts.mean():.1f}');b.metric('RPG',f'{q.reb.mean():.1f}');c.metric('APG',f'{q.ast.mean():.1f}');d.metric('3PM',f'{q.threem.mean():.1f}')
            show(averages(q))
            st.line_chart(q.sort_values('date').set_index('date')[['pts','reb','ast']])
            show(q[['date','opponent','pts','reb','ast','threem','min']])
    with tab4:
        st.subheader('Team production and opponent production')
        team=st.selectbox('Team',sorted(t.team.unique()),key='team')
        games=t[t.team==team].sort_values('date',ascending=False)
        sample=st.selectbox('Games',['All games','Last 5','Last 10','Last 20','Home','Away'],key='team_sample')
        if sample.startswith('Last'):games=games.head(int(sample.split()[1]))
        elif sample=='Home':games=games[games.home]
        elif sample=='Away':games=games[~games.home]
        own=p.merge(games[['game_id','team_id']],on=['game_id','team_id'])
        opposing=p.merge(games[['game_id','opponent_id']],left_on=['game_id','team_id'],right_on=['game_id','opponent_id'])
        if games.empty:st.info('No games found.')
        else:
            a,b,c,d=st.columns(4)
            a.metric('Points scored',f'{games.points.mean():.1f}');b.metric('Points allowed',f'{games.opp_points.mean():.1f}')
            c.metric('Point differential',f'{(games.points-games.opp_points).mean():+.1f}');d.metric('Games',len(games))
            records=[]
            for label,df in [('Team',own),('Opponents',opposing)]:
                count=len(games)
                vals={k:df[k].sum()/count for k in ['reb','ast','stl','blk','tov','threem','threea','fgm','fga','fta']}
                possessions=df.fga.sum()-df.reb.sum()*0 # corrected offensive boards unavailable in this version
                # Possession estimate excludes OREB because team rebound split is not reliably exposed in all player boxes.
                poss=(df.fga.sum()+0.44*df.fta.sum()+df.tov.sum())/count
                records.append({'Side':label,'REB':vals['reb'],'AST':vals['ast'],'STL':vals['stl'],'BLK':vals['blk'],'TOV':vals['tov'],'3PM':vals['threem'],'FGA':vals['fga'],'FG%':100*df.fgm.sum()/max(df.fga.sum(),1),'Possessions proxy*':poss})
            show(pd.DataFrame(records))
            st.caption('*Possessions proxy = FGA + 0.44×FTA + TOV; not true possessions or offensive rating because offensive rebounds are not subtracted.')
            show(games[['date','opponent','home','points','opp_points']])

    st.stop()

if st.session_state['page'] == 'Team rankings':
    st.divider()
    page_banner('Team Rankings', 'League-wide offensive and defensive matchup rankings')
    st.caption('Rankings are computed from the loaded season. Offensive rank 1 = most produced; opponent rank 1 = most allowed (easiest matchup). Rankings only cover teams with data; 30-team completeness is shown below.')
    nba_t = nba_only(t)
    nba_p = nba_only(p)
    team_count = nba_t['team_id'].astype(str).nunique()
    if team_count < 30:
        st.warning(f'Only {team_count} of 30 NBA teams have completed game records. Rankings are provisional.')
    rank_stats={'Points':'pts','Rebounds':'reb','Assists':'ast','3-pointers made':'threem','Steals':'stl','Blocks':'blk','Turnovers':'tov'}
    metric=st.selectbox('Statistic to rank',list(rank_stats),key='rank_metric')
    stat=rank_stats[metric]
    if metric=='Points':
        off=nba_t.groupby('team_id')['points'].mean().rename('Scored per game')
        allowed=nba_t.groupby('team_id')['opp_points'].mean().rename('Allowed per game')
    else:
        team_game=nba_p.groupby(['game_id','team_id','opponent_id'],as_index=False)[stat].sum()
        off=team_game.groupby('team_id')[stat].mean().rename('Scored per game')
        allowed=team_game.groupby('opponent_id')[stat].mean().rename('Allowed per game')
    ranking=pd.concat([off,allowed],axis=1)
    ranking.index=ranking.index.astype(str)
    ranking=ranking.loc[ranking.index.isin(NBA_TEAM_IDS)].copy()
    # Map the ID back to one canonical display name per franchise.
    team_names=(nba_t.drop_duplicates('team_id').assign(team_id=lambda d:d['team_id'].astype(str))
                .set_index('team_id')['team'].to_dict())
    ranking['team']=ranking.index.map(team_names)
    ranking=ranking.dropna(subset=['team'])
    ranking['Offense rank']=ranking['Scored per game'].rank(ascending=False,method='min').astype('Int64')
    ranking['Allowed rank (most allowed = 1)']=ranking['Allowed per game'].rank(ascending=False,method='min').astype('Int64')
    ranking=ranking.reset_index(drop=True)
    if ranking.empty:
        st.info('No completed NBA-vs-NBA games are available for this season and statistic.')
    else:
        ra,rb=st.columns(2)
        teams=sorted(ranking.team.unique())
        with ra: rank_team_a=st.selectbox('Team A',teams,key='rank_a')
        with rb: rank_team_b=st.selectbox('Team B',teams,index=min(1,len(teams)-1),key='rank_b')
        for team_name in [rank_team_a,rank_team_b]:
            rr=ranking[ranking.team==team_name].iloc[0]
            st.write(f"**{team_name}** — Offense: #{rr['Offense rank']} ({rr['Scored per game']:.1f}/game); Allowed: #{rr['Allowed rank (most allowed = 1)']} ({rr['Allowed per game']:.1f}/game)")
        show(ranking.sort_values('Offense rank'))

    st.stop()

if st.session_state['page'] == 'Projections':
    st.divider()
    page_banner('Matchup Projections', 'Experimental player and team scoring estimates')
    st.caption('Experimental statistical estimates, not betting advice. Uses historical box scores; no injuries, confirmed lineups, odds, or real-time pace adjustments.')
    left,right,third=st.columns(3)
    with left:
        target_player=st.selectbox('Player to project',sorted(p.player.unique()),key='predict_player')
    with right:
        target_opponent=st.selectbox('Upcoming opponent',sorted(t.team.unique()),key='predict_opponent')
    with third:
        recent_window=st.selectbox('Recent form window',[5,10,20],index=1,key='predict_window')
    player_games=p[p.player==target_player].sort_values(['date','game_id'],ascending=False).copy()
    player_games=player_games[player_games['min']>0]
    if len(player_games)<3:
        st.warning('At least 3 appearances with recorded minutes are required for a projection.')
    else:
        position=player_games.iloc[0]['position']
        season_base=player_games
        recent=player_games.head(recent_window)
        vs_opp=player_games[player_games.opponent==target_opponent]
        opp_pos=p[(p.opponent==target_opponent)&(p.position==position)&(p['min']>0)]
        league_pos=p[(p.position==position)&(p['min']>0)]
        stats={'pts':'Points','reb':'Rebounds','ast':'Assists','threem':'3-pointers made','stl':'Steals','blk':'Blocks','tov':'Turnovers'}
        rows=[]
        for key,label in stats.items():
            season_avg=season_base[key].mean()
            recent_avg=recent[key].mean()
            # Stabilize the opponent-position effect with 20 pseudo-appearances.
            opp_avg=opp_pos[key].mean() if len(opp_pos) else float('nan')
            league_avg=league_pos[key].mean() if len(league_pos) else float('nan')
            ratio=(opp_avg/league_avg) if pd.notna(opp_avg) and pd.notna(league_avg) and league_avg>0 else 1.0
            reliability=len(opp_pos)/(len(opp_pos)+20)
            defense_multiplier=1+reliability*(ratio-1)
            defense_multiplier=max(0.75,min(1.25,defense_multiplier))
            base=.65*season_avg+.35*recent_avg
            # Matchup history gets a modest, sample-size-dependent weight.
            h2h_weight=min(0.15,len(vs_opp)/(len(vs_opp)+15))
            blended=(1-h2h_weight)*base+h2h_weight*(vs_opp[key].mean() if len(vs_opp) else base)
            estimate=max(0,blended*defense_multiplier)
            variability=player_games[key].std(ddof=1)
            low=max(0,estimate-variability) if pd.notna(variability) else estimate
            high=estimate+variability if pd.notna(variability) else estimate
            rows.append({'Stat':label,'Projection':round(estimate,1),'Typical low*':round(low,1),'Typical high*':round(high,1),'Season avg':round(season_avg,1),'Last '+str(recent_window):round(recent_avg,1),'Vs opponent':round(vs_opp[key].mean(),1) if len(vs_opp) else None,'Opponent vs '+str(position):round(opp_avg,1) if pd.notna(opp_avg) else None})
        a,b,c,d=st.columns(4)
        for metric,col in zip(rows[:4],[a,b,c,d]):
            col.metric(metric['Stat'],f"{metric['Projection']:.1f}")
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.caption(f'Based on {len(player_games)} player games, {len(recent)} recent games, {len(vs_opp)} head-to-head games and {len(opp_pos)} opposing {position} player-games. *Typical low/high = projection ± historical single-game standard deviation, NOT a calibrated confidence interval.')
        st.info('Method: 65% season form + 35% recent form; up to 15% weight on head-to-head history; shrink opponent-position effect toward league average (20 pseudo-games), capped at ±25%. No future information is used. These weights are heuristics and have not been backtested.')

    st.subheader('Team scoring matchup estimate')
    team_a,team_b=st.columns(2)
    with team_a:
        offense=st.selectbox('Scoring team',sorted(t.team.unique()),key='predict_team')
    with team_b:
        defense_team=st.selectbox('Defending team',sorted(t.team.unique()),key='predict_team_opp')
    if offense==defense_team:
        st.info('Choose two different teams.')
    else:
        off=t[t.team==offense].sort_values('date',ascending=False)
        deff=t[t.team==defense_team].sort_values('date',ascending=False)
        if len(off)>=3 and len(deff)>=3:
            offensive_score=.65*off.points.mean()+.35*off.head(10).points.mean()
            defensive_allow=.65*deff.opp_points.mean()+.35*deff.head(10).opp_points.mean()
            predicted=(offensive_score+defensive_allow)/2
            st.metric(f'{offense} projected points against {defense_team}',f'{predicted:.1f}')
            st.caption(f'{offense} recent-weighted scoring: {offensive_score:.1f}; {defense_team} recent-weighted points allowed: {defensive_allow:.1f}. Simple unvalidated midpoint; does not account for injuries, pace, rest or home court.')
        else:
            st.warning('Insufficient team games for an estimate.')
