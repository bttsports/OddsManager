import dash
from dash import html, dcc
from cbb.scrapers.main_cbb import *
import threading, time, multiprocessing
import dash_bootstrap_components as dbc

# Initialize the Dash app
app = dash.Dash(
    __name__,
    use_pages=True,
    suppress_callback_exceptions=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)
server = app.server  # For deployment (e.g., Heroku, Render)

# Layout
app.layout = html.Div([
    dbc.NavbarSimple(
        brand="NFL Dashboard",
        brand_href="/",
        color="dark",
        dark=True,
        children=[
            dbc.NavItem(dbc.NavLink("Home", href="/")),
            dbc.NavItem(dbc.NavLink("Database Search", href="/database-search")),
        ]
    ),
    html.Div(dash.page_container)
])

# Run app
if __name__ == "__main__":
    cbb_scraper_thread = multiprocessing.Process(target=main_cbb_scraper, daemon=True)
    cbb_scraper_thread.start()
    app.run(debug=True, use_reloader=False)