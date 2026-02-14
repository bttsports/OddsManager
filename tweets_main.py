from dash import Dash, html, dcc, Input, Output, State, callback_context, callback
import dash_bootstrap_components as dbc
import pandas as pd
import db
from dash import html, dcc, Input, Output, State, register_page

register_page(__name__, path="/nfl-tweets-main", name="NFL Tweets")

### USEFUL KEYWORDS
#risk,moving,weather,windy,prop,odds,miss,serious,will not,at practice,left practice,injury,injured,will play,start,is in,is out,ready,questionable,serious,workload,share,roster,coach


def fetch_tweets(keywords, team):
    # Build SQL query
    query = "SELECT * FROM nfl_tweets WHERE created_at >= NOW() - INTERVAL 14 DAY"
    params = []

    if keywords:
        keyword_conditions = []
        for word in keywords:
            keyword_conditions.append(f"text LIKE '%" + word + "%'")
        query += " AND (" + " OR ".join(keyword_conditions) + ")"

    if team:
        query += " AND LOCATE('" + team + "',team_abbrs) > 0"

    query += " ORDER BY created_at DESC"
    print(query)
    db.DB.reconnect()
    rows = db.execute_any_query(query)
    return pd.DataFrame(rows)


layout = dbc.Container([
    html.H1("NFL Tweet Search"),
    dbc.Row([
        dbc.Col([
            dcc.Input(id='keyword-input', type='text', placeholder='Enter keywords separated by commas', className='mb-2 w-100'),
            dcc.Input(id='team-input', type='text', placeholder='Only 1 Team at Once Supported', className='mb-2 w-100'),
            dbc.Button("Search", id='search-button', color='primary', className='w-100')
        ], width=4),
        dbc.Col([
            html.Div(id='tweet-results')
        ], width=8)
    ])
], fluid=True)

@callback(
    Output('tweet-results', 'children'),
    Input('search-button', 'n_clicks'),
    State('keyword-input', 'value'),
    State('team-input', 'value'),
    prevent_initial_call=True   # <-- stops it from running at page load
)

def update_results(n_clicks, keyword_input, team_input):

    keywords = [k.strip() for k in keyword_input.split(',')] if keyword_input else []
    team = team_input.strip() if team_input else None

    df = fetch_tweets(keywords, team)
    if df.empty:
        return html.Div("No tweets found.")

    return [
        dbc.Card([
            dbc.CardBody([
                html.H6(tweet['author'], className='card-title'),
                html.P(tweet['text'], className='card-text'),
                html.Small(str(tweet['created_at']), className='text-muted')
            ])
        ], className='mb-2')
        for _, tweet in df.iterrows()
    ]


