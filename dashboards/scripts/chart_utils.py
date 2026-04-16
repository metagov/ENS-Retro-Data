"""Shared Plotly chart constants for all dashboard scripts."""

WATERMARK = dict(
    text="ENS Retro Analysis by Metagov 2026",
    xref="paper", yref="paper",
    x=0.5, y=0.5,
    showarrow=False,
    font=dict(size=28, color="rgba(200,200,200,0.35)"),
    textangle=-30,
)

CHART_CONFIG = {
    "displayModeBar": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}
