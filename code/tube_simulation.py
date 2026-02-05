import pandas as pd
import networkx as nx
import folium
import json
import math

OVERLOAD_FACTOR = 1.5

stations_df = pd.read_csv("tfl_stations.csv")
edges_df = pd.read_csv("tfl_edges.csv")
lines_df = pd.read_csv("tfl_lines_stations.csv")

mapping = {
    "bakerloo": "Bakerloo",
    "central": "Central",
    "circle": "Circle",
    "district": "District",
    "hammersmith-city": "Hammersmith & City",
    "jubilee": "Jubilee",
    "metropolitan": "Metropolitan",
    "northern": "Northern",
    "piccadilly": "Piccadilly",
    "victoria": "Victoria",
    "waterloo-city": "Waterloo & City"
}
lines_df["line"] = lines_df["line"].map(mapping)

def clean(name):
    for s in [" Underground Station", " Rail Station", " Railway Station", " DLR Station"]:
        name = name.replace(s, "")
    return name.split(" (")[0].strip()

stations_df["clean"] = stations_df["name"].apply(clean)
edges_df["station_a"] = edges_df["station_a"].apply(clean)
edges_df["station_b"] = edges_df["station_b"].apply(clean)
lines_df["clean_station"] = lines_df["station_name"].apply(clean)


LINE_COLORS = {
    "Bakerloo": "#B36305", "Central": "#E32017", "Circle": "#FFD300",
    "District": "#00782A", "Hammersmith & City": "#F3A9BB",
    "Jubilee": "#A0A5A9", "Metropolitan": "#9B0056",
    "Northern": "#000000", "Piccadilly": "#003688",
    "Victoria": "#0098D4", "Waterloo & City": "#95CDBA"
}

LINE_OFFSETS = {
    "Hammersmith & City": 45, "District": -45, "Circle": 30,
    "Metropolitan": -30, "Central": 0, "Bakerloo": 18,
    "Jubilee": -18, "Northern": 0, "Piccadilly": 22,
    "Victoria": -22, "Waterloo & City": 12
}

R = 6378137

def latlon_to_merc(lat, lon):
    return R * math.radians(lon), R * math.log(math.tan(math.pi/4 + math.radians(lat)/2))

def merc_to_latlon(x, y):
    return math.degrees(2 * math.atan(math.exp(y/R)) - math.pi/2), math.degrees(x/R)

def offset_polyline(coords, offset):
    merc = [latlon_to_merc(lat, lon) for lat, lon in coords]
    out = []
    for i, (x, y) in enumerate(merc):
        x2, y2 = merc[i+1] if i < len(merc)-1 else merc[i-1]
        dx, dy = x2-x, y2-y
        l = math.hypot(dx, dy)
        nx_, ny_ = (-dy/l, dx/l) if l else (0, 0)
        out.append(merc_to_latlon(x + nx_*offset, y + ny_*offset))
    return out

G = nx.Graph()
for _, r in stations_df.iterrows():
    G.add_node(r["clean"], lat=r["lat"], lon=r["lon"])

for _, r in edges_df.iterrows():
    G.add_edge(r["station_a"], r["station_b"])


line_graphs = {}
for line in lines_df["line"].unique():
    df = lines_df[lines_df["line"] == line].sort_values(["branch_id", "order"])
    edges = []
    for bid in df["branch_id"].unique():
        br = df[df["branch_id"] == bid]["clean_station"].tolist()
        for i in range(len(br)-1):
            edges.append((br[i], br[i+1]))
    L = nx.Graph()
    L.add_edges_from(edges)
    line_graphs[line] = L

degree = nx.degree_centrality(G)
betweenness = nx.betweenness_centrality(G)
closeness = nx.closeness_centrality(G)
articulation = set(nx.articulation_points(G))

base_comp = max(nx.connected_components(G), key=len)
BASELINE_AVG_PATH = nx.average_shortest_path_length(G.subgraph(base_comp))

def compute_failure_effect(st):
    G2 = G.copy()
    G2.remove_node(st)

    comps = list(nx.connected_components(G2))
    num_components = len(comps)

    largest = G2.subgraph(max(comps, key=len))
    avg_after = nx.average_shortest_path_length(largest)

    bw_after = nx.betweenness_centrality(G2)

    affected_lines = sorted(
        lines_df[lines_df["clean_station"] == st]["line"].unique()
    )

    disrupted_lines = []
    rerouting = []

    for line in affected_lines:
        L = line_graphs[line].copy()
        if st in L:
            L.remove_node(st)

        parts = list(nx.connected_components(L))
        if len(parts) == 1:
            continue  # line not disrupted

        disrupted_lines.append(line)

        a, b = list(parts[0]), list(parts[1])
        via = None

        for alt in line_graphs:
            if alt == line:
                continue
            La = line_graphs[alt]
            for x in a:
                for y in b:
                    if x in La and y in La and nx.has_path(La, x, y):
                        via = alt
                        break
                if via:
                    break
            if via:
                break

        if not via:
            rerouting.append({
                "text": f"{line}: no rerouting",
                "status": "terminal",
                "overloaded": []
            })
            continue

        overloaded = []
        for n in line_graphs[via].nodes():
            if betweenness.get(n, 0) > 0:
                ratio = bw_after.get(n, 0) / betweenness[n]
                if ratio > OVERLOAD_FACTOR:
                    overloaded.append({
                        "station": n,
                        "ratio": round(ratio, 2)
                    })

        if overloaded:
            rerouting.append({
                "text": f"{line} → {via}",
                "status": "overload",
                "overloaded": overloaded
            })
        else:
            rerouting.append({
                "text": f"{line} → {via}",
                "status": "stable",
                "overloaded": []
            })

    return {
        "components": num_components,
        "avg_before": round(BASELINE_AVG_PATH, 3),
        "avg_after": round(avg_after, 3),
        "avg_delta": round(avg_after - BASELINE_AVG_PATH, 3),
        "degree": round(degree[st], 3),
        "betweenness": round(betweenness[st], 3),
        "closeness": round(closeness[st], 3),
        "articulation": st in articulation,
        "disrupted_lines": disrupted_lines,
        "rerouting": rerouting
    }

DATA = {s: compute_failure_effect(s) for s in G.nodes()}


m = folium.Map(
    location=[stations_df["lat"].mean(), stations_df["lon"].mean()],
    zoom_start=11,
    tiles="cartodbpositron"
)

for line in lines_df["line"].unique():
    df = lines_df[lines_df["line"] == line].sort_values(["branch_id", "order"])
    for bid in df["branch_id"].unique():
        br = df[df["branch_id"] == bid]["clean_station"].tolist()
        coords = [(G.nodes[s]["lat"], G.nodes[s]["lon"]) for s in br]
        folium.PolyLine(
            offset_polyline(coords, LINE_OFFSETS[line]),
            color=LINE_COLORS[line],
            weight=8
        ).add_to(m)
m.get_root().html.add_child(
    folium.Element(f"<script>window.TFL_DATA = {json.dumps(DATA)};</script>")
)

modal = """
<style>
#overlay{position:fixed;display:none;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.6);z-index:9000}
#modal{position:fixed;display:none;top:50%;left:50%;transform:translate(-50%,-50%);
background:white;padding:20px;border-radius:10px;z-index:9999;width:420px}
.overload{color:red;font-weight:bold}
.stable{color:green}
.terminal{color:gray}
</style>

<script>
function showModal(s){
  const d = window.TFL_DATA[s];
  let html = `
    <h3>${s}</h3>
    Components after failure: ${d.components}<br>
    Δ Avg path: <b style="color:${d.avg_delta>0?'red':'green'}">${d.avg_delta}</b><br><br>

    Degree: ${d.degree}<br>
    Betweenness: ${d.betweenness}<br>
    Closeness: ${d.closeness}<br>
    Articulation: ${d.articulation}<br><br>

    <b>Disrupted lines</b><br>
    ${d.disrupted_lines.length ? d.disrupted_lines.join("<br>") : "None"}<br><br>

    <b>Rerouting & Overload</b><br>
  `;

  if(d.rerouting.length){
    d.rerouting.forEach(r=>{
      if(r.status === "overload"){
        const list = r.overloaded
          .map(o => `${o.station} (×${o.ratio})`)
          .join("<br>&nbsp;&nbsp;↳ ");
        html += `
          <span class="overload">${r.text} ⚠ overload</span><br>
          &nbsp;&nbsp;↳ ${list}<br>
        `;
      } else if(r.status === "terminal"){
        html += `<span class="terminal">${r.text}</span><br>`;
      } else {
        html += `<span class="stable">${r.text} ✓ stable</span><br>`;
      }
    });
  } else {
    html += "None<br>";
  }

  html += `<br><button onclick="closeModal()">Close</button>`;
  document.getElementById("modal").innerHTML = html;
  document.getElementById("overlay").style.display="block";
  document.getElementById("modal").style.display="block";
}

function closeModal(){
  document.getElementById("overlay").style.display="none";
  document.getElementById("modal").style.display="none";
}
</script>

<div id="overlay"></div>
<div id="modal"></div>
"""
m.get_root().html.add_child(folium.Element(modal))

for s in G.nodes():
    popup_html = f"""
<b>{s}</b><br>
<a href="#" onclick="event.stopPropagation(); showModal('{s}'); return false;">
🔥 Simulate Failure
</a>
"""
    folium.CircleMarker(
        location=[G.nodes[s]["lat"], G.nodes[s]["lon"]],
        radius=6,
        color="black",
        fill=True,
        fill_color="white",
        fill_opacity=1,
        popup=folium.Popup(folium.Html(popup_html, script=True), max_width=250)
    ).add_to(m)

m.save("uk_tube_failure.html")
print("Saved uk_tube_failure.html")
