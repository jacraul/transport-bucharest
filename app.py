from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import email_service
from geopy.geocoders import Nominatim
from datetime import timedelta


# --- IMPORT CRITIC: Motorul de Rutare ---
import routing_engine 

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cheie_secreta_bucuresti'
# Configurare Bază de date (Useri/Bilete)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:0799044133@localhost/transport_times'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- CONFIGURARE ȘI INIȚIALIZARE MOTOR RUTARE ---

# PASUL 1: DEFINIM PARAMETRII PRIMII (Aici era problema, trebuie să fie SUS)
db_params_routing = {
    "dbname": "transport_times",
    "user": "postgres",
    "password": "0799044133", 
    "host": "localhost"
}

# PASUL 2: CREĂM GRAFUL FOLOSIND PARAMETRII DE MAI SUS
transport_graph = routing_engine.TransportGraph(db_params_routing)

# ... Restul codului (load_user, modelele Users, SoldTickets etc.) continuă mai jos ...
@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

# --- MODELE DB ---
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


# --- RUTA AFIȘARE BILETE ---


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Verificam daca exista deja
        if Users.query.filter_by(email=email).first():
            flash('Email deja folosit!')
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password, method='sha256')
        new_user = Users(username=username, email=email, password_hash=hashed_pw)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Cont creat! Te poti loga.')
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
            flash('Email sau parola incorecta.')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- RUTE PRINCIPALE ---

@app.route('/')
def index():
    return render_template('map.html')

@app.route('/tickets')
@login_required
def tickets():
    # Căutăm biletele active ale utilizatorului curent
    # Un bilet e activ dacă expire_time > acum
    now = datetime.now()
    active_tickets = Ticket.query.filter(
        Ticket.user_id == current_user.id, 
        Ticket.expire_time > now
    ).order_by(Ticket.expire_time.desc()).all()
    
    return render_template('tickets.html', active_tickets=active_tickets)

# --- RUTA PROCESARE CUMPĂRARE ---
@app.route('/buy_ticket', methods=['POST'])
@login_required
def buy_ticket():
    ticket_type = request.form.get('ticket_type')
    
    # Configurare Prețuri și Durate
    prices = {
        '90min': 3.0,
        '24h': 8.0,
        '72h': 20.0,
        'airport': 3.0
    }
    durations = {
        '90min': 90, # minute
        '24h': 1440,
        '72h': 4320,
        'airport': 90
    }
    names = {
        '90min': 'Bilet 90 Minute',
        '24h': 'Abonament 24h',
        '72h': 'Abonament 72h',
        'airport': 'Bilet Aeroport'
    }

    if ticket_type in prices:
        # Creăm biletul
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
        
        flash(f"✅ Ai cumpărat cu succes: {names[ticket_type]}!", "success")
    else:
        flash("❌ Tip bilet invalid!", "danger")
        
    return redirect(url_for('tickets'))
# --- LOGICA DE RUTARE REALA ---
@app.route('/calculate_route', methods=['POST'])
def calculate_route():
    data = request.json
    start_addr = data.get('start')
    end_addr = data.get('end')

    # Preluăm parametrii de timp trimiși de Javascript
    time_type = data.get('time_type')   
    time_value = data.get('time_value') # ex: '2025-12-07T14:30'
    
    print(f"🔍 Caut ruta: {start_addr} -> {end_addr} @ {time_value}") 

    geolocator = Nominatim(user_agent="app_transport_bucuresti_proiect_v5")
    
    try:
        # --- 1. Geocoding ---
        def smart_query(addr):
            if "," in addr: return addr
            return f"{addr}, Romania"

        query_start = smart_query(start_addr)
        query_end = smart_query(end_addr)
        
        loc_start = geolocator.geocode(query_start)
        loc_end = geolocator.geocode(query_end)
        
        if not loc_start:
            return jsonify({'error': f'Nu am putut localiza adresa de plecare: {start_addr}'}), 404
        if not loc_end:
            return jsonify({'error': f'Nu am putut localiza adresa de destinație: {end_addr}'}), 404
            
        # --- 2. Apelare Motor Rutare (CU ORA) ---
        result = transport_graph.find_route(
            (loc_start.latitude, loc_start.longitude),
            (loc_end.latitude, loc_end.longitude),
            time_value=time_value  # <--- AICI ESTE ACTUALIZAREA CRITICĂ
        )
        
        if "error" in result:
            print(f"❌ Eroare Algoritm: {result['error']}")
            return jsonify({'error': result['error']})
            
        # --- 3. Generare HTML Detaliat ---
        # Calculăm numărul de schimburi reale (excludem mersul pe jos)
        vehicles = [leg for leg in result['details'] if leg['type'] == 'transit']
        nr_schimburi = len(vehicles) - 1 if len(vehicles) > 0 else 0

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
            # STILIZARE DIFERITĂ PENTRU MERS PE JOS vs TRANSIT
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
                # Determinăm culoarea badge-ului (Metrou = Roșu/Albastru, Autobuz = Standard)
                badge_class = "bg-primary"
                if leg['line'].startswith('M'): badge_class = "bg-danger" # Metrou
                if leg['line'].startswith('N'): badge_class = "bg-dark"   # Noapte
                
                html_details += f'''
                <div class="card border-0 shadow-sm mb-3">
                    <div class="card-body p-2 d-flex align-items-center">
                        <span class="badge {badge_class} me-3 py-2 px-3 fs-6">{leg["line"]}</span>
                        <div class="border-start ps-3">
                            <small class="text-muted d-block">Ia din stația:</small>
                            <b class="text-dark">{leg["from"]}</b>
                        </div>
                    </div>
                </div>
                '''
            
        html_details += f'''
        <div class="route-step mt-3 pt-2 border-top">
            <i class="fa-solid fa-flag-checkered text-danger me-2"></i>
            <small>Coboară la:</small> <b>{result["end_stop"]}</b>
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
        return jsonify({'error': f'Eroare interna server: {str(e)}'}), 500

# --- ADMIN ---

# --- RUTA PRINCIPALĂ ADMIN (CĂUTARE) ---
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash("Acces interzis!", "danger")
        return redirect(url_for('index'))

    # Logica de Căutare
    search_query = request.args.get('search', '')
    query = Route.query
    
    if search_query:
        # Căutăm parțial în nume scurt sau lung
        query = query.filter(Route.route_short_name.ilike(f'%{search_query}%') | 
                             Route.route_long_name.ilike(f'%{search_query}%'))
    
    # Limităm la 50 de rezultate pentru performanță
    routes = query.order_by(Route.route_short_name).limit(50).all()

    return render_template('admin.html', routes=routes, search_query=search_query)


# --- RUTA PENTRU EDITARE (SALVARE) ---
@app.route('/admin/route/edit', methods=['POST'])
@login_required
def edit_route():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    # Preluăm datele din formularul Modal
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
            flash(f"Eroare la salvare: {e}", "danger")
    else:
        flash("Ruta nu a fost găsită!", "danger")
        
    return redirect(url_for('admin'))


# --- RUTA PENTRU ȘTERGERE (ACȚIUNE) ---
@app.route('/admin/route/delete', methods=['POST'])
@login_required
def delete_route():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    r_id = request.form.get('route_id')
    route = Route.query.get(r_id)
    
    if route:
        try:
            # Atenție: Ștergerea unei rute poate șterge în cascadă trips/stop_times
            # depinde cum ai configurat baza de date (Foreign Keys)
            db.session.delete(route)
            db.session.commit()
            flash(f"Ruta {route.route_short_name} a fost ștearsă!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Nu se poate șterge ruta (probabil are curse active): {e}", "danger")
    else:
        flash("Ruta nu există!", "danger")
        
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Asta creeaza tabelele users/tickets daca nu exista
        
        # Creati un admin default daca nu exista
        if not Users.query.filter_by(username='admin').first():
            hashed = generate_password_hash('admin123', method='sha256')
            admin = Users(username='admin', email='admin@transport.ro', password_hash=hashed, is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print("Admin user creat: admin@transport.ro / admin123")
            
    app.run(debug=True)