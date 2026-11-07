"""Season-specific player position overrides, keyed by ESPN player ID."""
from pathlib import Path
import pandas as pd

POSITIONS = {'PG', 'SG', 'SF', 'PF', 'C'}
CSV = Path(__file__).with_name('player_positions.csv')

def apply_player_positions(players, season):
    """Return a copy with CSV positions applied; do not alter other seasons."""
    frame = players.copy()
    if frame.empty or not CSV.exists():
        return frame, {'matched_players': 0, 'total_players': 0, 'unmatched_players': 0, 'conflicts': 0}
    lookup = pd.read_csv(CSV, dtype=str, encoding='utf-8-sig').fillna('')
    required = {'espn_player_id','season','position'}
    if not required.issubset(lookup.columns):
        raise ValueError('player_positions.csv is missing columns: '+', '.join(sorted(required-set(lookup.columns))))
    label = f'{int(season)-1}–{str(int(season))[-2:]}'
    lookup = lookup[lookup['season'].str.strip().eq(label)].copy()
    lookup['espn_player_id'] = lookup['espn_player_id'].str.strip()
    lookup['position'] = lookup['position'].str.upper().str.strip()
    lookup = lookup[lookup['position'].isin(POSITIONS) & lookup['espn_player_id'].ne('')]
    # Conflicting duplicate IDs are deliberately not applied.
    conflicts = lookup.groupby('espn_player_id')['position'].nunique()
    conflicting = set(conflicts[conflicts > 1].index)
    lookup = lookup[~lookup['espn_player_id'].isin(conflicting)]
    mapping = lookup.drop_duplicates('espn_player_id').set_index('espn_player_id')['position']
    ids = frame['player_id'].astype(str).str.strip()
    replacement = ids.map(mapping)
    frame['position_source'] = 'ESPN'
    frame.loc[replacement.notna(), 'position'] = replacement[replacement.notna()]
    frame.loc[replacement.notna(), 'position_source'] = 'CSV depth chart'
    unique = frame[['player_id','position_source']].drop_duplicates('player_id')
    return frame, {'matched_players': int((unique.position_source=='CSV depth chart').sum()),
                   'total_players': len(unique),
                   'unmatched_players': int((unique.position_source!='CSV depth chart').sum()),
                   'conflicts': len(conflicting)}
