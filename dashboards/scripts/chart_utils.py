"""Shared Plotly chart helpers for all dashboard scripts."""

import copy

import streamlit as st

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


def render_chart(fig, *, key: str, filename: str = "chart", **kwargs) -> None:
    """Display a Plotly chart with a download button that adds a watermark.

    The live chart is shown clean (no watermark). The download button
    exports a PNG with the watermark baked in.

    Args:
        fig: Plotly figure object.
        key: Unique Streamlit widget key (required to avoid duplicate IDs).
        filename: Base filename for the downloaded PNG (no extension).
        **kwargs: Passed through to st.plotly_chart (e.g. use_container_width).
    """
    kwargs.setdefault("use_container_width", True)
    st.plotly_chart(fig, config=CHART_CONFIG, **kwargs)

    # Build watermarked copy for download
    fig_wm = copy.deepcopy(fig)
    fig_wm.add_annotation(**WATERMARK)

    png_bytes = fig_wm.to_image(format="png", scale=2)
    st.download_button(
        label="\u2B73 Download PNG",
        data=png_bytes,
        file_name=f"{filename}.png",
        mime="image/png",
        key=key,
    )
