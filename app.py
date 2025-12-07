from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import email_service
from geopy.geocoders import Nominatim
import os

# --- IMPORT CRITIC: Motorul de Rutare ---
# Asigura-te ca ai fisierul routing_engine.py in acelasi folder!
import routing_engine 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cheie_secreta_bucuresti'

# --- CONFIGURARE BAZA DE DATE ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:@localhost/transport_times'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- CONFIGURARE ȘI INIȚIALIZARE MOTOR RUTARE ---
db_params_routing = {
    "dbname": "transport_times",
    "user": "postgres",
    "password": "0799044133", 
    "host": "localhost"
}

# Inițializăm graful global (Se încarcă la pornirea serverului)
try:
    transport_graph = routing_engine.TransportGraph(db_params_routing)
except Exception as e:
    print(f"ATENTIE: Graful nu s-a putut initializa (poate baza de date e goala?): {e}")
    transport_graph = None

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

# ================== MODELE BAZĂ DE DATE ==================

class Users(UserMixin, db.Model):
    __tablename__ = 'users' 
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    email = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)

class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    expire_time = db.Column(db.DateTime, nullable=False)
    user = db.relationship('Users', backref=db.backref('tickets', lazy=True))

class Route(db.Model):
    __tablename__ = 'routes'
    route_id = db.Column(db.String, primary_key=True)
    route_short_name = db.Column(db.String)
    route_long_name = db.Column(db.String)

class SoldTickets(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    ticket_type = db.Column(db.String(50))
    price = db.Column(db.Numeric(10,2))
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)


# ================== RUTE AUTENTIFICARE ==================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if Users.query.filter_by(email=email).first():
            flash('Email deja folosit!', 'danger')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password, method='sha256')
        new_user = Users(username=username, email=email, password_hash=hashed_pw)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Cont creat! Te poti loga.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = Users.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Email sau parola incorecta.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ================== RUTE PRINCIPALE ==================

@app.route('/')
def index():
    return render_template('map.html')

@app.route('/tickets')
@login_required
def tickets():
    now = datetime.now()
    active_tickets = Ticket.query.filter(
        Ticket.user_id == current_user.id, 
        Ticket.expire_time > now
    ).order_by(Ticket.expire_time.desc()).all()
    
    return render_template('tickets.html', active_tickets=active_tickets)

# --- PROCESARE CUMPĂRARE SI EMAIL ---
@app.route('/buy_ticket', methods=['POST'])
@login_required
def buy_ticket():
    ticket_type = request.form.get('ticket_type')
    
    prices = {
        '90min': 3.0, '24h': 8.0, '72h': 20.0, 'airport': 3.0
    }
    durations = {
        '90min': 90, '24h': 1440, '72h': 4320, 'airport': 90
    }
    names = {
        '90min': 'Bilet 90 Minute', '24h': 'Abonament 24h', 
        '72h': 'Abonament 72h', 'airport': 'Bilet Aeroport'
    }

    if ticket_type in prices:
        duration_minutes = durations[ticket_type]
        expire_time = datetime.now() + timedelta(minutes=duration_minutes)
        
        new_ticket = Ticket(
            user_id=current_user.id,
            type=names[ticket_type],
            price=prices[ticket_type],
            expire_time=expire_time
        )
        
        db.session.add(new_ticket)
        db.session.commit()
        
        # --- TRIMITERE EMAIL ---
        try:
            ticket_info = {
                'id': new_ticket.id,
                'type': names[ticket_type],
                'price': f"{prices[ticket_type]:.2f}",
                'expiry': expire_time.strftime('%d.%m.%Y %H:%M')
            }
            
            # Trimitem emailul la adresa utilizatorului logat
            email_sent = email_service.send_ticket_email(current_user.email, ticket_info)
            
            if email_sent:
                flash(f"✅ Bilet cumpărat! Confirmarea a fost trimisă pe {current_user.email}.", "success")
            else:
                flash(f"✅ Bilet cumpărat, dar emailul de confirmare nu a putut fi trimis.", "warning")
                
        except Exception as e:
            print(f"Eroare proces email: {e}")
            flash(f"✅ Bilet cumpărat! (Eroare sistem email)", "warning")

    else:
        flash("❌ Tip bilet invalid!", "danger")
        
    return redirect(url_for('tickets'))

# ================== LOGICA DE RUTARE (Calculate Route) ==================
@app.route('/calculate_route', methods=['POST'])
def calculate_route():
    data = request.json
    start_addr = data.get('start')
    end_addr = data.get('end')
    time_type = data.get('time_type')   
    time_value = data.get('time_value') 
    
    print(f"🔍 Caut ruta: {start_addr} -> {end_addr} @ {time_value}") 

    geolocator = Nominatim(user_agent="app_transport_bucuresti_proiect_v5")
    
    try:
        def smart_query(addr):
            if "," in addr: return addr
            return f"{addr}, Romania"

        loc_start = geolocator.geocode(smart_query(start_addr))
        loc_end = geolocator.geocode(smart_query(end_addr))
        
        if not loc_start:
            return jsonify({'error': f'Nu am putut localiza adresa de plecare: {start_addr}'}), 404
        if not loc_end:
            return jsonify({'error': f'Nu am putut localiza adresa de destinație: {end_addr}'}), 404
            
        if not transport_graph:
             return jsonify({'error': 'Motorul de rutare nu este inițializat corect.'}), 500

        result = transport_graph.find_route(
            (loc_start.latitude, loc_start.longitude),
            (loc_end.latitude, loc_end.longitude),
            time_value=time_value
        )
        
        if "error" in result:
            print(f"❌ Eroare Algoritm: {result['error']}")
            return jsonify({'error': result['error']})
            
        vehicles = [leg for leg in result['details'] if leg['type'] == 'transit']
        nr_schimburi = len(vehicles) - 1 if len(vehicles) > 0 else 0

        # Construire HTML Răspuns
        html_details = f'''
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div>
                <span class="badge bg-success mb-1">Ruta Optimă</span><br>
                <small class="text-muted"><i class="fa-solid fa-clock"></i> Plecare: {time_value.split("T")[1] if time_value else "Acum"}</small>
            </div>
            <div class="text-end">
                <small class="fw-bold text-primary">{len(result['details'])} etape</small><br>
                <small class="text-muted">{nr_schimburi} schimburi</small>
            </div>
        </div>
        
        <div class="route-step mb-2 pb-2 border-bottom">
            <i class="fa-solid fa-location-dot text-success me-2"></i>
            <small>Plecare din:</small> <br><b>{start_addr}</b>
        </div>
        
        <div class="route-step mb-3">
            <i class="fa-solid fa-person-walking text-secondary me-2"></i>
            <small>Mergi la stația:</small> <b>{result["start_stop"]}</b>
        </div>
        '''
        
        for leg in result['details']:
            if leg['line'] == 'Mers pe jos' or leg['type'] == 'transfer':
                html_details += f'''
                <div class="d-flex align-items-center mb-3 ms-2 ps-2 border-start">
                    <div class="text-secondary">
                        <i class="fa-solid fa-person-walking fa-lg me-3"></i>
                    </div>
                    <div>
                        <small class="text-muted d-block">Transfer / Mers pe jos</small>
                        <span class="small">Către: <b>{leg["from"]}</b></span>
                    </div>
                </div>
                '''
            else:
                badge_class = "bg-primary"
                if leg['line'].startswith('M'): badge_class = "bg-danger"
                if leg['line'].startswith('N'): badge_class = "bg-dark"
                
                html_details += f'''
                <div class="card border-0 shadow-sm mb-3">
                    <div class="card-body p-2 d-flex align-items-center">
                        <span class="badge {badge_class} me-3 py-2 px-3 fs-6">{leg["line"]}</span>
                        <div class="border-start ps-3">
                            <small class="text-muted d-block">Ia din stația:</small>
                            <b class="text-dark">{leg["from"]}</b>
                        </div>
                        <div class="ms-auto text-end">
                            <small class="text-muted d-block">{leg.get('duration_fmt', '')}</small>
                            <small class="text-secondary" style="font-size:0.75rem">{leg.get('stops_count', 0)} stații</small>
                        </div>
                    </div>
                </div>
                '''
            
        html_details += f'''
        <div class="route-step mt-3 pt-2 border-top">
            <i class="fa-solid fa-flag-checkered text-danger me-2"></i>
            <small>Coboară la:</small> <b>{result["end_stop"]}</b>
            <div class="mt-2 text-center text-muted small">
                <i class="fa-solid fa-hourglass-half"></i> Durată totală estimată: <b>{result.get('total_duration', 'N/A')}</b>
            </div>
        </div>
        '''

        return jsonify({
            'start_coords': [loc_start.latitude, loc_start.longitude],
            'end_coords': [loc_end.latitude, loc_end.longitude],
            'path_coords': result['path_coords'],
            'html_info': html_details
        })

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Eroare interna server: {str(e)}'}), 500

# ================== RUTE ADMIN ==================

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash("Acces interzis!", "danger")
        return redirect(url_for('index'))

    search_query = request.args.get('search', '')
    query = Route.query
    
    if search_query:
        query = query.filter(Route.route_short_name.ilike(f'%{search_query}%') | 
                             Route.route_long_name.ilike(f'%{search_query}%'))
    
    routes = query.order_by(Route.route_short_name).limit(50).all()

    # Statistici
    try:
        sales = db.session.query(func.sum(Ticket.price)).scalar() or 0
        popular_data = db.session.query(Ticket.type, func.count(Ticket.id)).group_by(Ticket.type).order_by(func.count(Ticket.id).desc()).first()
        popular = popular_data if popular_data else None
    except:
        sales = 0
        popular = None

    return render_template('admin.html', routes=routes, search_query=search_query, sales=sales, popular=popular)


@app.route('/admin/route/edit', methods=['POST'])
@login_required
def edit_route():
    if not current_user.is_admin: return redirect(url_for('index'))
    
    r_id = request.form.get('route_id')
    short_name = request.form.get('short_name')
    long_name = request.form.get('long_name')
    
    route = Route.query.get(r_id)
    if route:
        route.route_short_name = short_name
        route.route_long_name = long_name
        try:
            db.session.commit()
            flash(f"Ruta {short_name} a fost actualizată!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Eroare: {e}", "danger")
    else:
        flash("Ruta nu a fost găsită!", "danger")
        
    return redirect(url_for('admin'))


@app.route('/admin/route/delete', methods=['POST'])
@login_required
def delete_route():
    if not current_user.is_admin: return redirect(url_for('index'))
    
    r_id = request.form.get('route_id')
    route = Route.query.get(r_id)
    if route:
        try:
            db.session.delete(route)
            db.session.commit()
            flash(f"Ruta {route.route_short_name} a fost ștearsă!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Eroare ștergere (dependențe?): {e}", "danger")
    else:
        flash("Ruta inexistentă!", "danger")
        
    return redirect(url_for('admin'))

@app.route('/admin/regenerate_graph', methods=['POST'])
@login_required
def regenerate_graph():
    if not current_user.is_admin: return redirect(url_for('index'))
    
    try:
        cache_file = "transport_graph_layered.pkl"
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"🗑️ [Admin] Cache șters: {cache_file}")
        
        # Forțăm reîncărcarea
        transport_graph.is_loaded = False 
        transport_graph.load_data() 
        flash("Graful a fost regenerat cu succes! Regulile noi sunt active.", "success")
    except Exception as e:
        flash(f"Eroare regenerare: {str(e)}", "danger")
        
    return redirect(url_for('admin'))

# ================== LIVE MAP ROUTES ==================

@app.route('/live')
@login_required
def live_map():
    routes = Route.query.order_by(Route.route_short_name).all()
    return render_template('live.html', routes=routes)

@app.route('/api/live_vehicles')
def api_live_vehicles():
    route_name = request.args.get('route')
    if not route_name:
        return jsonify({'error': 'No route specified'}), 400

    now = datetime.now()
    current_time_str = now.strftime("%H:%M:%S")
    
    # Query SQL Complex: Găsește segmentele active
    query = text("""
        SELECT 
            r.route_short_name,
            t.trip_headsign,
            s1.stop_lat as lat1, s1.stop_lon as lon1, st1.departure_time as t1,
            s2.stop_lat as lat2, s2.stop_lon as lon2, st2.arrival_time as t2
        FROM stop_times st1
        JOIN stop_times st2 ON st1.trip_id = st2.trip_id AND st1.stop_sequence + 1 = st2.stop_sequence
        JOIN trips t ON st1.trip_id = t.trip_id
        JOIN routes r ON t.route_id = r.route_id
        JOIN stops s1 ON st1.stop_id = s1.stop_id
        JOIN stops s2 ON st2.stop_id = s2.stop_id
        WHERE r.route_short_name = :r_name
        AND st1.departure_time <= :now 
        AND st2.arrival_time >= :now
    """)
    
    try:
        results = db.session.execute(query, {'r_name': route_name, 'now': current_time_str}).fetchall()
        
        vehicles = []
        for row in results:
            # Funcție conversie timp
            def to_seconds(t_val):
                if isinstance(t_val, str):
                    h, m, s = map(int, t_val.split(':'))
                    return h * 3600 + m * 60 + s
                # Dacă vine ca obiect timedelta (PostgreSQL uneori face asta)
                if isinstance(t_val, timedelta):
                    return t_val.total_seconds()
                # Dacă vine ca time object
                return t_val.hour * 3600 + t_val.minute * 60 + t_val.second
            
            t1_sec = to_seconds(row.t1)
            t2_sec = to_seconds(row.t2)
            now_sec = to_seconds(current_time_str)
            
            if t2_sec == t1_sec: 
                ratio = 0.5
            else:
                ratio = (now_sec - t1_sec) / (t2_sec - t1_sec)
                # Cap ratio la 0-1
                ratio = max(0.0, min(1.0, ratio))
            
            lat = float(row.lat1) + (float(row.lat2) - float(row.lat1)) * ratio
            lon = float(row.lon1) + (float(row.lon2) - float(row.lon1)) * ratio
            
            vehicles.append({
                'lat': lat,
                'lon': lon,
                'headsign': row.trip_headsign,
                'speed': 25 # km/h estimat
            })
            
        return jsonify({'vehicles': vehicles})
        
    except Exception as e:
        print(f"Eroare Live API: {e}")
        return jsonify({'error': str(e)}), 500

# ================== DB FIX & START ==================
@app.route('/fix_db')
def fix_db():
    try:
        with app.app_context():
            db.create_all() # Doar creeaza daca nu exista, nu sterge
            
            if not Users.query.filter_by(username='admin').first():
                hashed = generate_password_hash('admin123', method='sha256')
                admin = Users(username='admin', email='admin@transport.ro', password_hash=hashed, is_admin=True)
                db.session.add(admin)
                db.session.commit()
            
        return "Baza de date verificata. Userul admin exista."
    except Exception as e:
        return f"Eroare: {str(e)}"

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
