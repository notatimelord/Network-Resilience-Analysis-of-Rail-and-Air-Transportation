import pandas as pd
import networkx as nx
import folium
import json

CSV_FILE = "dataUK.csv"
OUTPUT_HTML = "uk_air_failure.html"

CITY_COORDS = {
    "London":       (51.5074, -0.1278),
    "Manchester":   (53.4808, -2.2426),
    "Edinburgh":    (55.9533, -3.1883),
    "Glasgow":      (55.8642, -4.2518),
    "Birmingham":   (52.4862, -1.8904),
    "Bristol":      (51.4545, -2.5879),
    "Leeds":        (53.8008, -1.5491),
    "Liverpool":    (53.4084, -2.9916),
    "Newcastle":    (54.9783, -1.6178),
    "Cardiff":      (51.4816, -3.1791),
    "Belfast":      (54.5973, -5.9301),
    "Aberdeen":     (57.1497, -2.0943),
    "Dundee":       (56.4620, -2.9707),
    "Inverness":    (57.4778, -4.2247),
    "Norwich":      (52.6309,  1.2974),
    "Southampton":  (50.9503, -1.3568),
    "Exeter":       (50.7344, -3.4139),
    "Bournemouth":  (50.7792, -1.8425),
    "Newquay":      (50.4406, -4.9954),
    "Stornoway":    (58.2136, -6.3315),
    "Kirkwall":     (58.9570, -2.9050),
    "Benbecula":    (57.4811, -7.3628),
    "Sumburgh":     (59.8789, -1.2956)
}


df = pd.read_csv(CSV_FILE)

G = nx.Graph()
for _, r in df.iterrows():
    if r["air"] > 0 and r["from"] in CITY_COORDS and r["to"] in CITY_COORDS:
        G.add_edge(r["from"], r["to"], weight=r["air"])

def avg_path_length_lcc(graph):
    if graph.number_of_nodes() < 2:
        return None
    if nx.is_connected(graph):
        return nx.average_shortest_path_length(graph)
    lcc = max(nx.connected_components(graph), key=len)
    return nx.average_shortest_path_length(graph.subgraph(lcc))

def affected_routes(graph, failed):
    if failed not in graph:
        return []

    before_paths = dict(nx.all_pairs_shortest_path(graph))
    G2 = graph.copy()
    G2.remove_node(failed)
    after_paths = dict(nx.all_pairs_shortest_path(G2))

    affected = []

    for src in graph.nodes():
        for dst in graph.nodes():
            if src == dst or failed in (src, dst):
                continue

            path_before = before_paths.get(src, {}).get(dst)
            if not path_before or failed not in path_before:
                continue

            path_after = after_paths.get(src, {}).get(dst)

            if not path_after:
                affected.append({
                    "from": src,
                    "to": dst,
                    "status": "NO_ROUTE",
                    "old_path": path_before
                })
            else:
                old_mid = [n for n in path_before[1:-1] if n == failed]
                new_mid = path_after[1:-1]

                affected.append({
                    "from": src,
                    "to": dst,
                    "status": "REROUTED",
                    "old_len": len(path_before) - 1,
                    "new_len": len(path_after) - 1,
                    "old_path": path_before,
                    "new_path": path_after,
                    "replacement": new_mid
                })

    return affected

BASELINE_AVG_PATH = avg_path_length_lcc(G)

bet = nx.betweenness_centrality(G)
clo = nx.closeness_centrality(G)
deg_cent = nx.degree_centrality(G)
deg = dict(G.degree())
ap = set(nx.articulation_points(G))
ap_percent = 100 * len(ap) / G.number_of_nodes()

def simulate_city_failure(city):
    if city not in G:
        return None

    G2 = G.copy()
    G2.remove_node(city)

    comps = list(nx.connected_components(G2))
    if not comps:
        return None

    avg_path_after = avg_path_length_lcc(G2)

    return {
        "degree": deg.get(city, 0),
        "betweenness": round(bet.get(city, 0), 3),
        "closeness": round(clo.get(city, 0), 3),
        "components": len(comps),
        "largest_cc": len(max(comps, key=len)),
        "articulation": city in ap,
        "avg_path_before": round(BASELINE_AVG_PATH, 3) if BASELINE_AVG_PATH else None,
        "avg_path_after": round(avg_path_after, 3) if avg_path_after else None,
        "avg_path_delta": (
            round(avg_path_after - BASELINE_AVG_PATH, 3)
            if avg_path_after and BASELINE_AVG_PATH
            else None
        ),
        "affected_routes": affected_routes(G, city)
    }

FAILURE_DATA = {
    city: simulate_city_failure(city)
    for city in CITY_COORDS
    if city in G
}

m = folium.Map(location=[54.5, -2.5], zoom_start=6, tiles="cartodbpositron")

for u, v, d in G.edges(data=True):
    folium.PolyLine(
        [CITY_COORDS[u], CITY_COORDS[v]],
        color="blue",
        weight=1 + d["weight"] / 5,
        opacity=0.6,
        dash_array="6,6"
    ).add_to(m)

m.get_root().html.add_child(
    folium.Element(
        f"<script>window.FAILURE_DATA = {json.dumps(FAILURE_DATA)};</script>"
    )
)
modal = """
<style>
#overlay{
  position:fixed;
  display:none;
  top:0; left:0;
  width:100%; height:100%;
  background:rgba(0,0,0,.45);
  z-index:9000;
}

#modal{
  position:fixed;
  display:none;
  top:50%; left:50%;
  transform:translate(-50%,-50%);
  background:white;
  border-radius:12px;
  padding:20px 22px;
  width:420px;
  max-height:80vh;
  overflow-y:auto;
  z-index:9999;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  box-shadow:0 10px 40px rgba(0,0,0,.25);
}

.title{
  font-size:20px;
  font-weight:700;
  margin-bottom:14px;
}

.section{
  margin-bottom:16px;
}

.section-title{
  font-size:12px;
  font-weight:600;
  color:#666;
  text-transform:uppercase;
  margin-bottom:6px;
}

.row{
  display:flex;
  justify-content:space-between;
  margin-bottom:4px;
  font-size:14px;
}

.good{ color:#1a7f37; font-weight:600; }
.bad{ color:#c62828; font-weight:600; }

details summary{
  cursor:pointer;
  font-weight:600;
  margin-top:10px;
}

.route{
  font-size:13px;
  margin-bottom:4px;
}

.close{
  margin-top:16px;
  background:#222;
  color:white;
  padding:8px 14px;
  border:none;
  border-radius:6px;
  cursor:pointer;
}
</style>

<script>
function showCity(city){
  const d = window.FAILURE_DATA[city];
  if(!d) return;

  let routesHtml = "";
  let lost = 0;
  let rerouted = 0;

  d.affected_routes.slice(0,10).forEach(r => {
    if(r.status === "NO_ROUTE"){
      lost++;
      routesHtml += `<div class="route bad">${r.from} → ${r.to}: NO ROUTE</div>`;
    } 
    else if(r.status === "REROUTED"){
      rerouted++;
      const via = r.replacement.length > 0
        ? r.replacement.join(" → ")
        : "direct";

      routesHtml += `
        <div class="route good">
          ${r.from} → ${r.to}: via ${via} (${r.old_len} → ${r.new_len})
        </div>`;
    }
  });

  if(d.affected_routes.length > 10){
    routesHtml += "<i>… more affected routes</i>";
  }

  const html = `
    <div class="title">${city} ✈️</div>

    <div class="section">
      <div class="section-title">Network impact</div>
      <div class="row">
        <span>Δ Avg path length</span>
        <span class="${d.avg_path_delta > 0 ? 'bad' : 'good'}">
          ${d.avg_path_delta}
        </span>
      </div>
      <div class="row"><span>Components</span><span>${d.components}</span></div>
      <div class="row"><span>Largest CC</span><span>${d.largest_cc}</span></div>
    </div>

    <div class="section">
      <div class="section-title">Node importance</div>
      <div class="row"><span>Degree</span><span>${d.degree}</span></div>
      <div class="row"><span>Betweenness</span><span>${d.betweenness}</span></div>
      <div class="row"><span>Closeness</span><span>${d.closeness}</span></div>
      <div class="row"><span>Articulation</span><span>${d.articulation ? "YES" : "NO"}</span></div>
    </div>

    <div class="section">
      <div class="section-title">Disruption summary</div>
      <div class="row bad">• ${lost} routes lost</div>
      <div class="row good">• ${rerouted} routes rerouted</div>
    </div>

    <details>
      <summary>Show affected routes</summary>
      ${routesHtml}
    </details>

    <button class="close" onclick="closeModal()">Close</button>
  `;

  document.getElementById("modal").innerHTML = html;
  document.getElementById("overlay").style.display = "block";
  document.getElementById("modal").style.display = "block";
}

function closeModal(){
  document.getElementById("overlay").style.display = "none";
  document.getElementById("modal").style.display = "none";
}
</script>

<div id="overlay"></div>
<div id="modal"></div>

"""

m.get_root().html.add_child(folium.Element(modal))

for city, (lat, lon) in CITY_COORDS.items():
    if city not in G:
        continue

    popup_html = f"""
        <b>{city}</b><br>
        <span style="font-size:16px;color:#cc0000;cursor:pointer;font-weight:bold;"
              onclick="window.showCity('{city}')">
            🔥 Simulate Failure
        </span>
    """

    folium.CircleMarker(
        location=(lat, lon),
        radius=7,
        color="black",
        fill=True,
        fill_color="white",
        fill_opacity=1,
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(m)

print("\n=========== AIR NETWORK SUMMARY ===========")
print(f"Nodes: {G.number_of_nodes()}")
print(f"Edges: {G.number_of_edges()}")
print(f"Density: {nx.density(G):.4f}")
print(f"Articulation points: {ap_percent:.2f}%")
print(f"Average shortest path (LCC): {BASELINE_AVG_PATH:.3f}")

print("\n=========== TOP 5 BY BETWEENNESS ===========")
for c, v in sorted(bet.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"{c}: {v:.4f}")

print("\n=========== TOP 5 BY CLOSENESS ===========")
for c, v in sorted(clo.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"{c}: {v:.4f}")

print("\n=========== TOP 5 BY DEGREE CENTRALITY ===========")
for c, v in sorted(deg_cent.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"{c}: {v:.4f}")


m.save(OUTPUT_HTML)
print(f"\nSaved {OUTPUT_HTML}")
