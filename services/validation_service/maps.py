"""Folium map HTML for dashboard embed."""

from __future__ import annotations

from typing import Any


def render_track_map(
    vessel_positions: list[dict[str, Any]],
    barge_positions: list[dict[str, Any]] | None,
    port_lat: float | None,
    port_lon: float | None,
) -> str:
    try:
        import folium
    except ImportError:
        return "<p class='map-note'>Install folium for interactive maps.</p>"

    if not vessel_positions:
        return "<p class='map-note'>No AIS positions to display.</p>"

    lat = vessel_positions[0]["lat"]
    lon = vessel_positions[0]["lon"]
    m = folium.Map(location=[lat, lon], zoom_start=12, tiles="CartoDB dark_matter")

    v_coords = [(p["lat"], p["lon"]) for p in vessel_positions]
    folium.PolyLine(v_coords, color="#38bdf8", weight=3, opacity=0.8).add_to(m)
    folium.Marker(v_coords[0], popup="Vessel start", icon=folium.Icon(color="blue")).add_to(m)

    if barge_positions:
        b_coords = [(p["lat"], p["lon"]) for p in barge_positions]
        folium.PolyLine(b_coords, color="#fb923c", weight=3, opacity=0.8).add_to(m)
        folium.Marker(b_coords[0], popup="Barge", icon=folium.Icon(color="orange")).add_to(m)

    if port_lat is not None and port_lon is not None:
        folium.Marker(
            [port_lat, port_lon],
            popup="Declared port",
            icon=folium.Icon(color="green"),
        ).add_to(m)

    return m._repr_html_()
