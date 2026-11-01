#!/usr/bin/env python3
"""Stream the large clickstream TSV and build compact InfoVis assets."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from scipy.ndimage import gaussian_filter1d


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "clickstream_data1.tsv"
OUT = ROOT / "data" / "processed"
IMAGES = ROOT / "images"
ASSETS = ROOT / "assets"
SCHEMA = {"src": "VARCHAR", "dst": "VARCHAR", "kind": "VARCHAR", "clicks": "BIGINT"}
TYPE_COLORS = {"link": "#2864a5", "external": "#db7c26", "other": "#5a8f55"}
COMMUNITY_COLORS = ["#2878b5", "#e07a24", "#5b9a62", "#8b69aa", "#bd5367", "#54a6a5", "#9a8143", "#6c7b91"]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def records(df):
    return df.to_dict(orient="records")


def sql_type_totals(con):
    return con.execute("""
        SELECT kind, COUNT(*)::BIGINT AS rows, SUM(clicks)::BIGINT AS clicks,
               MIN(clicks)::BIGINT AS min_clicks, MAX(clicks)::BIGINT AS max_clicks,
               COUNT(DISTINCT src)::BIGINT AS distinct_sources,
               COUNT(DISTINCT dst)::BIGINT AS distinct_destinations
        FROM raw GROUP BY kind ORDER BY kind
    """).fetchdf()


def top_page_candidates(con, limit: int = 300):
    """The global top-N page by in+out traffic must occur in a top-N side list."""
    outgoing = con.execute("""
        SELECT src AS page, SUM(clicks)::BIGINT AS traffic
        FROM raw WHERE kind='link' AND NOT starts_with(src, 'other-')
        GROUP BY src ORDER BY traffic DESC LIMIT ?
    """, [limit]).fetchdf()
    incoming = con.execute("""
        SELECT dst AS page, SUM(clicks)::BIGINT AS traffic
        FROM raw WHERE kind='link' AND NOT starts_with(dst, 'other-')
        GROUP BY dst ORDER BY traffic DESC LIMIT ?
    """, [limit]).fetchdf()
    return sorted(set(outgoing.page.astype(str)) | set(incoming.page.astype(str)))


def make_network(con, total_link_clicks: int, max_nodes: int, max_edges: int):
    candidates = top_page_candidates(con, max(300, max_nodes * 3))
    con.execute("CREATE OR REPLACE TEMP TABLE page_candidates(page VARCHAR)")
    con.executemany("INSERT INTO page_candidates VALUES (?)", [(p,) for p in candidates])
    out_rows = con.execute("""
        SELECT r.src AS page, SUM(r.clicks)::BIGINT AS clicks,
               COUNT(DISTINCT r.dst)::BIGINT AS degree
        FROM raw r JOIN page_candidates c ON c.page=r.src
        WHERE r.kind='link' GROUP BY r.src
    """).fetchdf()
    in_rows = con.execute("""
        SELECT r.dst AS page, SUM(r.clicks)::BIGINT AS clicks,
               COUNT(DISTINCT r.src)::BIGINT AS degree
        FROM raw r JOIN page_candidates c ON c.page=r.dst
        WHERE r.kind='link' GROUP BY r.dst
    """).fetchdf()
    stats = {p: {"page": p, "in_clicks": 0, "out_clicks": 0, "in_degree": 0, "out_degree": 0}
             for p in candidates}
    for row in records(out_rows):
        stats[row["page"]]["out_clicks"] = int(row["clicks"])
        stats[row["page"]]["out_degree"] = int(row["degree"])
    for row in records(in_rows):
        stats[row["page"]]["in_clicks"] = int(row["clicks"])
        stats[row["page"]]["in_degree"] = int(row["degree"])
    ranked = sorted(stats.values(), key=lambda x: x["in_clicks"] + x["out_clicks"], reverse=True)[:max_nodes]
    for node in ranked:
        node["activity"] = node["in_clicks"] + node["out_clicks"]

    con.execute("CREATE OR REPLACE TEMP TABLE network_pages(page VARCHAR)")
    con.executemany("INSERT INTO network_pages VALUES (?)", [(n["page"],) for n in ranked])
    subgraph_rows, subgraph_clicks = con.execute("""
        SELECT COUNT(*)::BIGINT, SUM(r.clicks)::BIGINT
        FROM raw r JOIN network_pages s ON s.page=r.src JOIN network_pages d ON d.page=r.dst
        WHERE r.kind='link'
    """).fetchone()
    edge_df = con.execute("""
        SELECT r.src AS source, r.dst AS target, SUM(r.clicks)::BIGINT AS clicks
        FROM raw r JOIN network_pages s ON s.page=r.src JOIN network_pages d ON d.page=r.dst
        WHERE r.kind='link'
        GROUP BY r.src,r.dst ORDER BY clicks DESC LIMIT ?
    """, [max_edges]).fetchdf()
    edges = [{"source": r["source"], "target": r["target"], "clicks": int(r["clicks"])}
             for r in records(edge_df)]
    displayed_clicks = sum(e["clicks"] for e in edges)

    graph = nx.DiGraph()
    for n in ranked:
        graph.add_node(n["page"])
    for e in edges:
        graph.add_edge(e["source"], e["target"], weight=e["clicks"],
                       layout_weight=math.log1p(e["clicks"]),
                       distance=1.0 / max(math.log1p(e["clicks"]), 1.0))
    undirected = graph.to_undirected()
    communities = nx.community.louvain_communities(undirected, weight="layout_weight", seed=17)
    community_for = {node: cid for cid, group in enumerate(communities) for node in group}
    components = sorted(nx.connected_components(undirected), key=len, reverse=True)
    main_component = undirected.subgraph(components[0]).copy()
    isolates = [node for component in components[1:] for node in component]
    layout_component = main_component.copy()
    layout_component.remove_edges_from(nx.selfloop_edges(layout_component))
    component_layouts = {
        "spring": nx.spring_layout(layout_component, weight="layout_weight", seed=17, iterations=120),
        "kamada_kawai": nx.kamada_kawai_layout(layout_component, weight="distance"),
        "forceatlas2": nx.forceatlas2_layout(layout_component, weight="layout_weight", seed=17,
                                             max_iter=500, scaling_ratio=2.0, gravity=1.2,
                                             linlog=False),
    }
    normalized = {}
    for name, positions in component_layouts.items():
        core_coords = np.asarray([positions[node] for node in main_component.nodes], dtype=float)
        center = core_coords.mean(axis=0)
        radius = np.max(np.linalg.norm(core_coords - center, axis=1)) or 1.0
        packed = {node: 0.82 * (np.asarray(positions[node], dtype=float) - center) / radius
                  for node in main_component.nodes}
        # Layout only the connected core; place disconnected singleton pages around its perimeter.
        for i, node in enumerate(isolates):
            angle = 2 * np.pi * i / max(len(isolates), 1)
            packed[node] = np.asarray([np.cos(angle), np.sin(angle)])
        normalized[name] = {page: [float(v) for v in packed[page]] for page in graph.nodes}
    nodes = []
    for node in ranked:
        page = node["page"]
        nodes.append({**node, "community": community_for.get(page, 0),
                      "layouts": {name: normalized[name][page] for name in normalized}})
    return {
        "nodes": nodes,
        "edges": edges,
        "communities": len(communities),
        "connected_core_nodes": len(main_component),
        "isolated_nodes": len(isolates),
        "layout_names": ["spring", "kamada_kawai", "forceatlas2"],
        "summary": {
            "nodes_available": len(nodes), "displayed_edges": len(edges),
            "induced_edge_rows": int(subgraph_rows or 0), "induced_clicks": int(subgraph_clicks or 0),
            "displayed_clicks": int(displayed_clicks), "all_link_clicks": int(total_link_clicks),
            "displayed_share_of_all_link_clicks": float(displayed_clicks / total_link_clicks) if total_link_clicks else 0,
            "displayed_share_of_induced_clicks": float(displayed_clicks / subgraph_clicks) if subgraph_clicks else 0,
        },
    }, community_for


def make_treemap_by_source(con, type_totals, top_n=15, leaves_n=12):
    type_clicks = {r["kind"]: int(r["clicks"]) for r in records(type_totals)}
    selected = []
    source_rows = {}
    for kind in type_clicks:
        df = con.execute("""
            SELECT src AS page, SUM(clicks)::BIGINT AS clicks
            FROM raw WHERE kind=? GROUP BY src ORDER BY clicks DESC LIMIT ?
        """, [kind, top_n]).fetchdf()
        for r in records(df):
            selected.append((kind, r["page"]))
            source_rows[(kind, r["page"])] = int(r["clicks"])
    con.execute("CREATE OR REPLACE TEMP TABLE selected_sources(kind VARCHAR, src VARCHAR)")
    con.executemany("INSERT INTO selected_sources VALUES (?,?)", selected)
    selected_edges = con.execute("""
        SELECT r.kind,r.src,r.dst,SUM(r.clicks)::BIGINT AS clicks
        FROM raw r JOIN selected_sources s ON s.kind=r.kind AND s.src=r.src
        GROUP BY r.kind,r.src,r.dst
    """).fetchdf()
    by_source = defaultdict(list)
    for row in records(selected_edges):
        by_source[(row["kind"], row["src"])].append((row["dst"], int(row["clicks"])))

    children = []
    for kind, total in type_clicks.items():
        source_nodes = []
        selected_sum = 0
        for _, source in [p for p in selected if p[0] == kind]:
            source_total = source_rows[(kind, source)]
            selected_sum += source_total
            destinations = sorted(by_source[(kind, source)], key=lambda x: x[1], reverse=True)
            leaves = [{"name": dst, "value": clicks} for dst, clicks in destinations[:leaves_n]]
            tail = source_total - sum(x["value"] for x in leaves)
            if tail > 0:
                leaves.append({"name": "Other destinations", "value": tail})
            source_nodes.append({"name": source, "value": source_total, "children": leaves})
        other_sources = total - selected_sum
        if other_sources > 0:
            source_nodes.append({"name": "Other sources", "value": other_sources})
        children.append({"name": kind, "value": total, "children": source_nodes})
    return {"name": "All clickstream activity", "children": children,
            "method": "Relationship type → source page → destination page; residual clicks are rolled into exact Other buckets."}


def make_treemap_by_destination(con, total_clicks, top_n=60, high_n=15, sources_n=8):
    targets_df = con.execute("""
        SELECT dst AS page, SUM(clicks)::BIGINT AS clicks
        FROM raw GROUP BY dst ORDER BY clicks DESC LIMIT ?
    """, [top_n]).fetchdf()
    targets = records(targets_df)
    con.execute("CREATE OR REPLACE TEMP TABLE selected_targets(dst VARCHAR)")
    con.executemany("INSERT INTO selected_targets VALUES (?)", [(r["page"],) for r in targets])
    type_totals_df = con.execute("""
        SELECT r.dst,r.kind,SUM(r.clicks)::BIGINT AS clicks
        FROM raw r JOIN selected_targets t ON t.dst=r.dst
        GROUP BY r.dst,r.kind
    """).fetchdf()
    source_df = con.execute("""
        WITH grouped AS (
            SELECT r.dst,r.kind,r.src,SUM(r.clicks)::BIGINT AS clicks
            FROM raw r JOIN selected_targets t ON t.dst=r.dst
            GROUP BY r.dst,r.kind,r.src
        ), ranked AS (
            SELECT *,ROW_NUMBER() OVER(PARTITION BY dst,kind ORDER BY clicks DESC,src) AS rn
            FROM grouped
        )
        SELECT dst,kind,src,clicks FROM ranked WHERE rn<=?
    """, [sources_n]).fetchdf()
    type_value = {(r["dst"], r["kind"]): int(r["clicks"]) for r in records(type_totals_df)}
    sources = defaultdict(list)
    for r in records(source_df):
        sources[(r["dst"], r["kind"])].append({"name": r["src"], "value": int(r["clicks"])})
    targets_out = []
    for target in targets:
        kind_nodes = []
        for (dst, kind), value in type_value.items():
            if dst != target["page"]:
                continue
            source_nodes = sources[(dst, kind)]
            tail = value - sum(x["value"] for x in source_nodes)
            if tail > 0:
                source_nodes.append({"name": "Other sources", "value": tail})
            kind_nodes.append({"name": kind, "value": value, "children": source_nodes})
        targets_out.append({"name": target["page"], "value": int(target["clicks"]), "children": kind_nodes})
    high = targets_out[:high_n]
    middle = targets_out[high_n:]
    retained = sum(t["value"] for t in targets_out)
    groups = [
        {"name": f"High-volume destinations · top {len(high)}", "children": high,
         "value": sum(t["value"] for t in high)},
        {"name": f"Mid-volume destinations · next {len(middle)}", "children": middle,
         "value": sum(t["value"] for t in middle)},
    ]
    tail = int(total_clicks - retained)
    if tail > 0:
        groups.append({"name": "Long-tail destinations", "value": tail})
    return {"name": "All clickstream activity", "children": groups,
            "method": "Destination activity tier → destination page → relationship type → source page; omitted pages and sources are exactly aggregated."}


def make_parallel_data(con, community_for, per_type=1200, random_per_type=900):
    high = con.execute("""
        SELECT src,dst,kind,clicks,'high-volume' AS sample
        FROM raw
        QUALIFY ROW_NUMBER() OVER(PARTITION BY kind ORDER BY clicks DESC,src,dst)<=?
    """, [per_type]).fetchdf()
    broad = con.execute("""
        SELECT src,dst,kind,clicks,'broad-sample' AS sample
        FROM raw
        WHERE hash(src,dst,kind)%997=0
        QUALIFY ROW_NUMBER() OVER(PARTITION BY kind ORDER BY hash(src,dst,kind))<=?
    """, [random_per_type]).fetchdf()
    seen = set()
    edges = []
    for df in (high, broad):
        for r in records(df):
            identity = (r["src"], r["dst"], r["kind"])
            if identity in seen:
                continue
            seen.add(identity)
            edges.append({"src": r["src"], "dst": r["dst"], "kind": r["kind"],
                          "clicks": int(r["clicks"]), "sample": r["sample"]})
    endpoints = sorted({e["src"] for e in edges} | {e["dst"] for e in edges})
    con.execute("CREATE OR REPLACE TEMP TABLE edge_endpoints(page VARCHAR)")
    con.executemany("INSERT INTO edge_endpoints VALUES (?)", [(p,) for p in endpoints])
    out_df = con.execute("""
        SELECT r.src AS page,SUM(r.clicks)::BIGINT AS clicks,
               COUNT(DISTINCT r.dst)::BIGINT AS degree
        FROM raw r JOIN edge_endpoints p ON p.page=r.src GROUP BY r.src
    """).fetchdf()
    in_df = con.execute("""
        SELECT r.dst AS page,SUM(r.clicks)::BIGINT AS clicks,
               COUNT(DISTINCT r.src)::BIGINT AS degree
        FROM raw r JOIN edge_endpoints p ON p.page=r.dst GROUP BY r.dst
    """).fetchdf()
    outgoing = {r["page"]: {"clicks": int(r["clicks"]), "degree": int(r["degree"])} for r in records(out_df)}
    incoming = {r["page"]: {"clicks": int(r["clicks"]), "degree": int(r["degree"])} for r in records(in_df)}
    for edge in edges:
        out = outgoing.get(edge["src"], {"clicks": 0, "degree": 0})
        inc = incoming.get(edge["dst"], {"clicks": 0, "degree": 0})
        community = community_for.get(edge["src"])
        if community is None:
            community = "Referral buckets" if edge["src"].startswith("other-") else "Long-tail sources"
        edge.update({"source_clicks": out["clicks"], "source_degree": out["degree"],
                     "target_clicks": inc["clicks"], "target_degree": inc["degree"],
                     "bundle": str(community)})
    kind_codes = {kind: i for i, kind in enumerate(sorted({e["kind"] for e in edges}))}
    return {"edges": edges, "kind_codes": kind_codes,
            "axes": [
                {"key": "source_clicks", "label": "Source click volume (log)"},
                {"key": "source_degree", "label": "Source unique destinations"},
                {"key": "target_clicks", "label": "Destination click volume (log)"},
                {"key": "target_degree", "label": "Destination unique sources"},
                {"key": "clicks", "label": "Flow click count (log)"},
                {"key": "kind", "label": "Clickstream relationship type", "categorical": True},
            ],
            "sample_summary": {"records": len(edges), "high_volume_per_type": per_type,
                               "broad_sample_per_type": random_per_type,
                               "note": "High-volume flows plus a deterministic broad sample; click weights and full endpoint activity metrics are retained."}}


def top_target_profiles(con, group_by: str, group_values: list[str], buckets=101):
    profiles = {}
    for group in group_values:
        if group_by == "kind":
            df = con.execute("""
                WITH destination AS (
                    SELECT dst AS page,SUM(clicks)::BIGINT AS clicks
                    FROM raw WHERE kind=? GROUP BY dst
                ), ranked AS (
                    SELECT *,ROW_NUMBER() OVER(ORDER BY clicks DESC,page)-1 AS rank,
                           COUNT(*) OVER() AS n
                    FROM destination
                )
                SELECT FLOOR(rank*100/GREATEST(n-1,1))::INTEGER AS percentile,
                       AVG(LN(1+clicks)) AS mean_log_clicks,COUNT(*)::BIGINT AS pages
                FROM ranked GROUP BY percentile ORDER BY percentile
            """, [group]).fetchdf()
        else:
            role_clause = "starts_with(src,'other-')" if group == "Referral/search buckets" else "NOT starts_with(src,'other-')"
            df = con.execute(f"""
                WITH destination AS (
                    SELECT dst AS page,SUM(clicks)::BIGINT AS clicks
                    FROM raw WHERE {role_clause} GROUP BY dst
                ), ranked AS (
                    SELECT *,ROW_NUMBER() OVER(ORDER BY clicks DESC,page)-1 AS rank,
                           COUNT(*) OVER() AS n
                    FROM destination
                )
                SELECT FLOOR(rank*100/GREATEST(n-1,1))::INTEGER AS percentile,
                       AVG(LN(1+clicks)) AS mean_log_clicks,COUNT(*)::BIGINT AS pages
                FROM ranked GROUP BY percentile ORDER BY percentile
            """).fetchdf()
        if group_by == "kind":
            total, count = con.execute("SELECT SUM(clicks)::BIGINT,COUNT(DISTINCT dst)::BIGINT FROM raw WHERE kind=?", [group]).fetchone()
        else:
            total, count = con.execute(f"SELECT SUM(clicks)::BIGINT,COUNT(DISTINCT dst)::BIGINT FROM raw WHERE {role_clause}").fetchone()
        rows = records(df)
        profiles[group] = {"percentiles": [int(r["percentile"]) for r in rows],
                           "mean_log_clicks": [float(r["mean_log_clicks"]) for r in rows],
                           "pages_per_bin": [int(r["pages"]) for r in rows],
                           "destination_count": int(count), "group_clicks": int(total)}
    return profiles


def horizon_plot(groups, title, path):
    colors_high = ["#f6d365", "#f0a34a", "#d65a3a", "#a52d2d"]
    colors_low = ["#9ecae1", "#5aa0c7", "#346b9a", "#203f75"]
    fig, axes = plt.subplots(len(groups), 1, figsize=(13, max(3.2, 2.8 * len(groups))),
                             constrained_layout=True, squeeze=False)
    for ax, (name, profile) in zip(axes[:, 0], groups.items()):
        values = np.asarray(profile["mean_log_clicks"], dtype=float)
        if len(values) == 0:
            continue
        x = np.asarray(profile["percentiles"], dtype=float)
        centered = values - float(np.median(values))
        fold = 1.0
        for band in range(len(colors_high)):
            upper = np.clip(centered - band * fold, 0, fold)
            lower = np.clip(-centered - band * fold, 0, fold)
            ax.fill_between(x, 0, upper, color=colors_high[band], linewidth=0)
            ax.fill_between(x, 0, -lower, color=colors_low[band], linewidth=0)
        ax.axhline(0, color="#222", linewidth=0.7)
        ax.set_xlim(0, 100)
        ax.set_ylim(-fold, fold)
        ax.set_yticks([])
        ax.set_ylabel(name, rotation=0, ha="right", va="center", fontsize=10)
        ax.grid(axis="x", color="#fff", linewidth=0.7, alpha=0.8)
    axes[-1, 0].set_xticks([0, 20, 40, 60, 80, 100], ["0", "20", "40", "60", "80", "100"])
    axes[-1, 0].set_xlabel("Destination rank percentile (not time)")
    fig.suptitle(title + " · rank-based group profiles · centered log(1 + clicks)", fontsize=15, weight="bold")
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def ridgeline_plot(histograms, title, path):
    all_bins = sorted({float(r["log_bin"]) for rows in histograms.values() for r in rows})
    x = np.arange(min(all_bins), max(all_bins) + 0.101, 0.1)
    fig, ax = plt.subplots(figsize=(12, max(4.5, 1.45 * len(histograms))), constrained_layout=True)
    colors = ["#326a9c", "#d47a2c", "#569b68", "#965e9e", "#c65c68"]
    ordered = list(histograms.items())
    for index, (name, rows) in enumerate(ordered):
        counts = np.zeros(len(x), dtype=float)
        for row in rows:
            pos = int(round((float(row["log_bin"]) - x[0]) / 0.1))
            if 0 <= pos < len(counts):
                counts[pos] += int(row["records"])
        density = gaussian_filter1d(counts, sigma=1.6)
        if density.max() > 0:
            density /= density.max()
        base = len(ordered) - index - 1
        color = colors[index % len(colors)]
        ax.fill_between(x, base, base + density * 0.82, color=color, alpha=0.78)
        ax.plot(x, base + density * 0.82, color=color, linewidth=1.1)
    ax.set_yticks(np.arange(len(ordered)), [name for name, _ in ordered][::-1])
    ax.set_xlabel("log₁₀(clicks per clickstream record); ridge heights normalized within group")
    ax.set_ylabel("Group")
    ax.set_title(title, fontsize=15, weight="bold")
    ax.grid(axis="x", color="#ddd", linewidth=0.7)
    ax.set_xlim(float(x.min()), float(x.max()))
    ax.set_xticks(np.arange(math.floor(x.min()), math.ceil(x.max()) + 1))
    ax.set_xticklabels([f"10^{int(t)}" for t in np.arange(math.floor(x.min()), math.ceil(x.max()) + 1)])
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_distribution_outputs(con, kinds):
    horizon_by_kind = top_target_profiles(con, "kind", kinds)
    horizon_by_role = top_target_profiles(con, "role", ["Article-page sources", "Referral/search buckets"])
    IMAGES.mkdir(parents=True, exist_ok=True)
    horizon_plot(horizon_by_kind, "Horizon view 1 · destination profiles by relationship type", IMAGES / "horizon_by_type.png")
    horizon_plot(horizon_by_role, "Horizon view 2 · destination profiles by source role", IMAGES / "horizon_by_source_role.png")

    hist_type_rows = con.execute("""
        SELECT kind AS grp,FLOOR(LOG10(clicks)*10)/10 AS log_bin,
               COUNT(*)::BIGINT AS records,SUM(clicks)::BIGINT AS clicks
        FROM raw GROUP BY kind,log_bin ORDER BY kind,log_bin
    """).fetchdf()
    hist_role_rows = con.execute("""
        SELECT CASE WHEN starts_with(src,'other-') THEN 'Referral/search buckets'
                    ELSE 'Article-page sources' END AS grp,
               FLOOR(LOG10(clicks)*10)/10 AS log_bin,
               COUNT(*)::BIGINT AS records,SUM(clicks)::BIGINT AS clicks
        FROM raw GROUP BY grp,log_bin ORDER BY grp,log_bin
    """).fetchdf()
    type_hist = defaultdict(list)
    role_hist = defaultdict(list)
    for row in records(hist_type_rows):
        type_hist[row["grp"]].append(row)
    for row in records(hist_role_rows):
        role_hist[row["grp"]].append(row)
    ridgeline_plot(type_hist, "Ridgeline view 1 · click-count distribution by relationship type", IMAGES / "ridgeline_by_type.png")
    ridgeline_plot(role_hist, "Ridgeline view 2 · click-count distribution by source role", IMAGES / "ridgeline_by_source_role.png")
    return {
        "horizon_by_type": horizon_by_kind,
        "horizon_by_source_role": horizon_by_role,
        "ridgeline_histograms": {
            "by_type": {k: v for k, v in type_hist.items()},
            "by_source_role": {k: v for k, v in role_hist.items()},
        },
        "ridgeline_group_counts": {
            "by_type": {k: len(v) for k, v in type_hist.items()},
            "by_source_role": {k: len(v) for k, v in role_hist.items()},
        },
        "note": "No time field is present. Horizon views show mean log clicks in destination-rank percentile bins; ridgelines show exact log-click histograms by group.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--nodes", type=int, default=120)
    parser.add_argument("--edges", type=int, default=1800)
    parser.add_argument("--threads", type=int, default=min(4, os.cpu_count() or 2))
    args = parser.parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Clickstream TSV not found: {args.input}")
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    db_temp = OUT / ".duckdb_temp"
    db_temp.mkdir(exist_ok=True)
    con = duckdb.connect(database=":memory:")
    con.execute(f"SET threads={max(1,args.threads)}")
    con.execute("SET memory_limit='4GB'")
    con.execute(f"SET temp_directory='{db_temp.as_posix()}'")
    con.read_csv(str(args.input), delimiter="\t", header=False, columns=SCHEMA).create_view("raw")
    row = con.execute("SELECT COUNT(*)::BIGINT AS rows,SUM(clicks)::BIGINT AS clicks,MIN(clicks)::BIGINT AS min_clicks,MAX(clicks)::BIGINT AS max_clicks FROM raw").fetchone()
    profile = sql_type_totals(con)
    type_rows = records(profile)
    kinds = [r["kind"] for r in type_rows]
    totals = {r["kind"]: int(r["clicks"]) for r in type_rows}
    total_clicks = int(row[1])
    print(f"Scanned {int(row[0]):,} records; {total_clicks:,} clicks; types: {', '.join(kinds)}", flush=True)

    network, community_for = make_network(con, totals.get("link", 0), args.nodes, args.edges)
    write_json(OUT / "network.json", network)
    print(f"Network: {len(network['nodes'])} nodes, {len(network['edges'])} edges; "
          f"{network['summary']['displayed_share_of_all_link_clicks']:.1%} of link clicks in displayed edges", flush=True)

    tree_a = make_treemap_by_source(con, profile)
    tree_b = make_treemap_by_destination(con, total_clicks)
    write_json(OUT / "treemaps.json", {"models": [tree_a, tree_b]})
    print("Treemap models ready with exact residual click buckets.", flush=True)

    parallel = make_parallel_data(con, community_for)
    write_json(OUT / "parallel.json", parallel)
    print(f"Parallel coordinates: {len(parallel['edges']):,} records retained.", flush=True)

    distributions = make_distribution_outputs(con, kinds)
    write_json(OUT / "distributions.json", distributions)
    type_summary = {r["kind"]: {k: int(r[k]) for k in ("rows", "clicks", "min_clicks", "max_clicks", "distinct_sources", "distinct_destinations")}
                    for r in type_rows}
    summary = {
        "input": args.input.name,
        "input_bytes": args.input.stat().st_size,
        "rows": int(row[0]),
        "total_clicks": total_clicks,
        "min_clicks": int(row[2]),
        "max_clicks": int(row[3]),
        "types": type_summary,
        "has_timestamp": False,
        "source_columns": ["source page", "destination page", "relationship type", "click count"],
        "network": network["summary"],
        "parallel": parallel["sample_summary"],
        "reduction": "The network and browser edge samples retain high-volume flows; both treemaps roll omitted leaves into exact Other buckets. Distribution histograms retain exact record counts per log-click bin.",
    }
    write_json(OUT / "summary.json", summary)
    print(f"Distribution images saved in {IMAGES}; compact data in {OUT}.", flush=True)
    con.close()


if __name__ == "__main__":
    main()
