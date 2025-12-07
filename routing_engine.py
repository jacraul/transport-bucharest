import networkx as nx
import pandas as pd
from geopy.distance import geodesic
from sqlalchemy import create_engine, text
import pickle
import os
import re
from datetime import datetime
import math

class TransportGraph:
    def __init__(self, db_params):
        self.db_url = f"postgresql://{db_params['user']}:{db_params['password']}@{db_params['host']}/{db_params['dbname']}"
        self.G = nx.DiGraph()
        self.stops = {} 
        self.is_loaded = False
        self.cache_file = "transport_graph_layered.pkl"

    def _clean_name(self, name):
        name = name.upper()
        name = re.sub(r'\b(METROU|STATIA|PIATA|BULEVARDUL|SOSEAUA|STRADA|BD|SOS|STR|INTRAREA|PERON|SCARI|LIFT|RULANTE|SI|DOAR|URCARE|COBORARE|STAIRS|ESCALATORS|ELEVATOR|ONLY|GOING|UPWARDS|TERMINAL|CAPAT)\b', ' ', name)
        name = re.sub(r'\s+[A-Z]$', '', name)
        name = re.sub(r'[^A-Z0-9 ]', '', name)
        return " ".join(name.split())

    def _format_duration(self, minutes):
        """ Transformă minutele în format lizibil (ex: 1 h 5 min) """
        minutes = int(math.ceil(minutes))
        if minutes < 60:
            return f"{minutes} min"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours} h {mins} min"

    def _create_walking_edges(self):
        print("   -> 🚶 Generare Transferuri cu Timpi...")
        count = 0
        
        # 1. HUB-uri pe bază de nume
        name_clusters = {}
        for stop_id, data in self.stops.items():
            clean = self._clean_name(data['name'])
            if len(clean) > 3:
                if clean not in name_clusters: name_clusters[clean] = []
                name_clusters[clean].append(stop_id)

        for name, ids in name_clusters.items():
            if len(ids) > 1:
                for i in ids:
                    for j in ids:
                        if i == j: continue
                        data1, data2 = self.stops[i], self.stops[j]
                        dist = geodesic((data1['lat'], data1['lon']), (data2['lat'], data2['lon'])).meters
                        
                        if dist < 600:
                            # Transfer rapid în HUB: 2 minute cost algoritmic, 3 minute timp real
                            attr = {
                                'weight': 2.0, 
                                'actual_time': 3.0, # Timp real estimat pentru scări/coridoare
                                'type': 'walking', 
                                'line_name': 'Transfer Rapid'
                            }
                            self.G.add_edge(i, j, **attr)
                            count += 1

        # 2. Conexiuni Geografice
        buckets = {}
        for stop_id, data in self.stops.items():
            key = (round(data['lat'], 2), round(data['lon'], 2))
            if key not in buckets: buckets[key] = []
            buckets[key].append(stop_id)

        for key, stop_ids in buckets.items():
            for i in range(len(stop_ids)):
                for j in range(i + 1, len(stop_ids)):
                    id1, id2 = stop_ids[i], stop_ids[j]
                    if self.G.has_edge(id1, id2): continue 

                    data1, data2 = self.stops[id1], self.stops[id2]
                    dist = geodesic((data1['lat'], data1['lon']), (data2['lat'], data2['lon'])).meters
                    
                    if dist < 450:
                        minutes = (dist / 80) # Viteza medie de mers
                        attr = {
                            'weight': minutes, 
                            'actual_time': minutes, # Aici timpul real = timpul calculat
                            'type': 'walking', 
                            'line_name': 'Transfer'
                        }
                        self.G.add_edge(id1, id2, **attr)
                        self.G.add_edge(id2, id1, **attr)
                        count += 1

        print(f"      ✅ Total legături generate: {count}")

    def load_data(self):
        if os.path.exists(self.cache_file):
            print("⚡ Încărcare Graf din cache...")
            with open(self.cache_file, 'rb') as f:
                data = pickle.load(f)
                self.G = data['G']
                self.stops = data['stops']
            self.is_loaded = True
            return

        print("⏳ Generare Graf Optimizat (Timpi Reali)...")
        engine = create_engine(self.db_url)
        
        with engine.connect() as conn:
            # 1. Stații
            df_stops = pd.read_sql(text("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops"), conn)
            for _, row in df_stops.iterrows():
                s_id = str(row['stop_id'])
                self.stops[s_id] = {
                    'lat': row['stop_lat'], 
                    'lon': row['stop_lon'], 
                    'name': str(row['stop_name']).strip()
                }
                self.G.add_node(s_id, type='physical')

            # 2. Rute
            query = """
                SELECT DISTINCT t1.stop_id as start_node, t2.stop_id as end_node, r.route_short_name
                FROM stop_times t1
                JOIN stop_times t2 ON t1.trip_id = t2.trip_id AND t1.stop_sequence + 1 = t2.stop_sequence
                JOIN trips tr ON t1.trip_id = tr.trip_id
                JOIN routes r ON tr.route_id = r.route_id
            """
            df_edges = pd.read_sql(text(query), conn)

        # --- PARAMETRI ---
        BUS_PENALTY = 15.0 
        METRO_PENALTY = 5.0  
        
        for _, row in df_edges.iterrows():
            u_phys, v_phys = str(row['start_node']), str(row['end_node'])
            route = str(row['route_short_name']).strip().upper()
            
            if u_phys not in self.stops or v_phys not in self.stops: continue

            u_virt = f"{u_phys}|{route}"
            v_virt = f"{v_phys}|{route}"

            is_metro = route.startswith('M') or route in ['M1','M2','M3','M4','M5']
            is_night = route.startswith('N')

            # --- A. TRAVEL (Mersul efectiv cu vehiculul) ---
            # weight: pentru algoritm (Metroul e super ieftin ca să fie ales)
            # actual_time: realitatea (Metroul ia ~2 min, Bus ia ~4 min în trafic)
            algo_cost = 0.5 if is_metro else 2.0
            real_time = 2.5 if is_metro else 4.0 

            self.G.add_edge(u_virt, v_virt, 
                            weight=algo_cost, 
                            actual_time=real_time, # <--- TIMP REAL
                            type='travel', 
                            line_name=route)

            # --- B. BOARDING (Urcarea / Așteptarea) ---
            # weight: penalizarea psihologică pentru schimbare
            # actual_time: timpul mediu de așteptare în stație
            algo_penalty = METRO_PENALTY if is_metro else BUS_PENALTY
            wait_time = 5.0 if is_metro else 10.0 # 5 min metrou, 10 min bus

            self.G.add_edge(u_phys, u_virt, 
                            weight=algo_penalty, 
                            actual_time=wait_time, # <--- TIMP DE AȘTEPTARE
                            type='board', 
                            line_name=route,
                            is_night=is_night)

            # --- C. ALIGHTING (Coborârea) ---
            self.G.add_edge(v_virt, v_phys, weight=0, actual_time=0.5, type='alight', line_name=route)

        self._create_walking_edges()

        with open(self.cache_file, 'wb') as f:
            pickle.dump({'G': self.G, 'stops': self.stops}, f)
        self.is_loaded = True
        print("✅ Graf GATA!")

    def get_nearest_stop(self, lat, lon):
        closest, min_dist = None, float('inf')
        candidates = {s: d for s, d in self.stops.items() if abs(d['lat']-lat)<0.02 and abs(d['lon']-lon)<0.02}
        if not candidates: candidates = self.stops
        for sid, data in candidates.items():
            d = geodesic((lat, lon), (data['lat'], data['lon'])).meters
            if d < min_dist: min_dist, closest = d, sid
        return closest, min_dist

    def find_route(self, start_coords, end_coords, time_value=None):
        if not self.is_loaded: self.load_data()

        is_night_request = False
        if time_value:
            try:
                h = datetime.fromisoformat(time_value).hour
                if h >= 23 or h < 5: is_night_request = True
            except: pass
        
        print(f"🕒 Mod Rutare: {'NOAPTE' if is_night_request else 'ZI'}")

        def layered_weight(u, v, d):
            edge_type = d.get('type')
            
            if edge_type == 'board':
                is_night_line = d.get('is_night', False)
                route_name = d.get('line_name', '')
                if not is_night_request:
                    if is_night_line: return float('inf')
                else:
                    if not (is_night_line or route_name == '783'): return float('inf')
            
            return d.get('weight', 0)

        s_node, _ = self.get_nearest_stop(*start_coords)
        e_node, _ = self.get_nearest_stop(*end_coords)

        try:
            path = nx.dijkstra_path(self.G, s_node, e_node, weight=layered_weight)
            
            route_details = []
            full_coords = []
            
            total_time_min = 0
            
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                edge_data = self.G.get_edge_data(u, v)
                edge_type = edge_data.get('type')
                
                # ADUNĂM TIMPUL REAL (nu weight-ul)
                segment_time = edge_data.get('actual_time', 0)
                total_time_min += segment_time
                
                phys_id = u.split('|')[0]
                if phys_id in self.stops:
                    full_coords.append([self.stops[phys_id]['lat'], self.stops[phys_id]['lon']])

                if edge_type == 'travel':
                    line = edge_data.get('line_name')
                    from_stop = self.stops[phys_id]['name']
                    
                    # Dacă continuăm pe aceeași linie, adunăm timpul la pasul existent
                    if route_details and route_details[-1]['line'] == line and route_details[-1]['type'] == 'transit':
                        route_details[-1]['duration'] += segment_time
                        route_details[-1]['stops_count'] += 1
                    else:
                        route_details.append({
                            'line': line, 
                            'from': from_stop, 
                            'type': 'transit',
                            'duration': segment_time,
                            'stops_count': 1
                        })
                
                elif edge_type == 'walking':
                    display = 'Transfer Metrou' if edge_data.get('line_name') == 'Transfer Rapid' else 'Mers pe jos'
                    if not route_details or route_details[-1]['type'] != 'transfer':
                        route_details.append({
                            'line': display, 
                            'from': self.stops[phys_id]['name'], 
                            'type': 'transfer',
                            'duration': segment_time
                        })
                    else:
                        route_details[-1]['duration'] += segment_time
                
                elif edge_type == 'board':
                    # Adăugăm timpul de așteptare la următorul segment de tranzit sau îl afișăm ca "Așteptare"
                    # Cel mai simplu: îl adăugăm la timpul total, dar nu facem pas separat în UI
                    # (sau putem adăuga un pas mic de "Așteptare")
                    pass

            # Formatăm duratele pentru fiecare pas
            for step in route_details:
                step['duration_fmt'] = self._format_duration(step['duration'])

            last = self.stops[path[-1].split('|')[0]]
            full_coords.append([last['lat'], last['lon']])

            return {
                "path_coords": full_coords,
                "details": route_details,
                "start_stop": self.stops[s_node]['name'],
                "end_stop": self.stops[e_node]['name'],
                "total_duration": self._format_duration(total_time_min),
                "total_minutes": int(total_time_min)
            }

        except nx.NetworkXNoPath:
            return {"error": "Nu există rută validă."}
        except Exception as e:
            return {"error": str(e)}