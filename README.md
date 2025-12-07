# Public Transportation System for Bucharest-Ilfov
A modern web application for public transport route planning in Bucharest and Ilfov, using a custom routing engine based on GTFS data and graph algorithms.

### Description

This application allows users to find the fastest and most comfortable route between two points in Bucharest, taking into account traffic (simulated via penalties), transport type (Metro vs. Bus), and schedule (Day vs. Night).

In addition to routing, the application includes a Digital Wallet for ticket purchases and an Admin Panel for managing the transport network.
___

## Key Features

### 1. Advanced Routing Engine (Custom Routing Engine)

- We do not use Google Maps API for routing, but our own custom algorithm!
- Layered Graph: Distinguishes between "being at the stop" and "being inside the bus."
- Dynamic Penalties: - High cost for boarding (Boarding Penalty) to discourage unnecessary transfers.
- Favors Metro (low penalty) over Bus (high penalty).
- Smart Hubs: Automatically detects complex connections (e.g., Bus 405 <-> Metro Anghel Saligny) even if names differ slightly in the database.
- Day/Night Mode: Automatically filters night lines (N) based on the selected time.

### 2. Digital Wallet (Ticketing)

- Purchase tickets (90 min, 24h, 72h, Airport).
- Live Timer: Displays remaining time until expiration (e.g., 00:45:12), calculated in real-time via JavaScript.
- Visual validation (pulsing animation) for active tickets.

### 3. User System

- Secure Registration and Authentication (Password hashing).
- Roles: Standard User and Administrator.

### 4. Admin Panel

- Sales statistics and ticket popularity.
- Search, Edit, and Delete routes.
- Regenerate Graph: Button to clear the .pkl cache and rebuild the transport graph in case of database changes.
___

## Technologies Used

### Backend
- Python 3.11
- Flask (Web Framework)
- SQLAlchemy (ORM for database)
- NetworkX (Graph manipulation and Dijkstra algorithm)
- Pandas (GTFS data processing)
- GeoPy (Geographic distance calculations)

### Frontend

- HTML5 / CSS3
- Bootstrap 5 (Responsive design and Modals)
- Leaflet.js (Interactive OpenStreetMap maps)
- FontAwesome (Icons)

### Database

- PostgreSQL (Storage for users, tickets, routes, GTFS schedules)
___

## Installation and Setup

### Requirements

- Python 3.x

- PostgreSQL installed and running

### Step 1: Clone Repo

```bash
git clone [https://github.com/jacraul/transport-bucharest.git](https://github.com/jacraul/transport-bucharest.git)
cd transport-bucharest
```


### Step 2: Database Configuration

- Create a database in pgAdmin named transport_times.

- Import GTFS data (routes, trips, stops, stop_times) into the database.

Configure the connection URL in app.py:
```bash
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:password@localhost/transport_times'
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Initialize and Run
```bash
python app.py
```

On the first run, access http://127.0.0.1:5000/fix_db to create the user and ticket tables.


## Algorithm Logic (Deep Dive)

- The application uses a weighted directed graph (NetworkX). To solve the "zig-zag" problem (frequent bus changes), we implemented a psychological cost logic:
- Virtual Nodes: Every physical stop has virtual nodes for each line passing through it (e.g., Glina|405).
- Boarding Edges: Cost 15 points (Bus) or 5 points (Metro). The algorithm "pays" a high price to board, so it prefers staying in the vehicle as long as possible.
- Travel Edges: Very low cost (real travel time).
- Transfer Edges: Connect nearby physical stops (max 450m).
- This approach guarantees routes with fewer transfers and maximum comfort, not just the shortest geographic distance.

## Credits

Developed by Raul Jac (Frontend + Database) and Tudor Balba (Backend) for the PTS-WEB project (Politehnica).
GTFS Data provided by [TPBI Open Data](https://gtfs.tpbi.ro/regional/).
