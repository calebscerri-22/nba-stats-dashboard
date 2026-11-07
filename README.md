# NBA ESPN Analytics Dashboard

Unofficial ESPN API-powered NBA dashboard.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows: activate with `.venv\Scripts\activate`.

Select an NBA season (ending year, e.g. 2026 for 2025-26), load the season's completed games, and explore four tabs. The first load can take several minutes because game box scores are downloaded one at a time to avoid overloading ESPN. Subsequent loads use a local SQLite cache.

**Limitations:** ESPN endpoints are unofficial and may change; positions are roster-listed positions, not tracked defensive assignments; matchup results reflect the selected season, not career history. Stats are box-score-based. Team possessions and efficiency are estimates, not play-by-play tracking metrics. Missing box scores are skipped and shown as coverage warnings.

## Matchup predictions
The app now includes an experimental **Matchup projections** section below the four original tabs. Choose a player and upcoming opponent to estimate PTS, REB, AST, 3PM, STL, BLK, and TOV. It blends season and recent form, lightly incorporates head-to-head games, and applies a sample-size-shrunk opponent-vs-position adjustment. It also offers a simple team scoring projection. These are unvalidated heuristics, not calibrated predictive models. No injury, lineup, odds, or live possession inputs are included.

## Fix: ESPN HTTP 400 on scoreboard date ranges
The season loader now requests one YYYYMMDD per scoreboard call, instead of a YYYYMMDD-YYYYMMDD range. Failed dates are reported clearly rather than silently treated as missing games.

### Season selection
Choose an NBA season by its two calendar years, e.g. **2026–27**. Regular-season collection begins October 1, 2026 and continues into April 2027; playoffs are loaded separately through July 2027. The season ending year (2027) is passed internally to ESPN data loading.


## Player positions CSV integration
`player_positions.csv` is bundled alongside `app.py`. For the 2026–27 season,
positions are matched **by ESPN player ID** and override ESPN generic G/F/C
positions. Other seasons retain ESPN-provided positions. Unknown players fall
back to ESPN positions; they are not automatically assigned from another team.
The dashboard displays unique-player match coverage. Update the CSV in place
when your depth chart changes, then reload the Streamlit app. These are projected
depth-chart positions, not verified game-by-game on-court roles.

## Persistent SQLite season cache (new)
- On first run, choose a season and click **Update latest games**. ESPN scoreboards and completed game summaries are saved to `nba_cache.sqlite` next to `espn.py`.
- On subsequent launches the dashboard **automatically loads cached games offline** without any ESPN season requests. Today's schedule still needs internet.
- **Update latest games** scans only new dates and the last four days, and downloads only game summaries not already saved.
- **Full season refresh** rescans the season and re-downloads box scores.
- The sidebar displays the number of stored game summaries and last scanned date.
- **Back up `nba_cache.sqlite`** if moving machines; don't delete it when installing a new dashboard ZIP. Put the existing database beside `espn.py` in the updated folder.
- An interrupted initial scan resumes from the last successful date. Updates need internet; cached data remains available if ESPN is down.
- The database is a local file, not a cloud sync service.

## Separate dashboard pages
Use the sidebar **Navigation** selector to switch between Today's games, Game matchup, Statistics, Team rankings, and Projections. Selecting **View matchup** on Today's games navigates to the Game matchup view, and **Close game analysis** returns to Today's games. The underlying SQLite season cache and ESPN player position CSV are unchanged. The selected game is held in Streamlit session state; after restarting the app, choose a game again.
