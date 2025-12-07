import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

def send_ticket_email(to_email, ticket_details):
    """
    Trimite un email HTML stilizat (Verde-Albastru) cu detaliile biletului.
    """
    
    # --- CONFIGURARE SMTP ---
    SMTP_SERVER = "mail.euroalfa.eu"
    SMTP_PORT = 465 
    SENDER_EMAIL = "contact@euroalfa.eu"
    # ⚠️ Asigură-te că parola este corectă aici sau în variabile de mediu
    SENDER_PASSWORD = "antenastars25" 

    # Creare container email (Multipart)
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"✅ Biletul tău este activ: {ticket_details['type']}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email

    # --- TEMPLATE HTML (Verde-Albastru) ---
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            .header {{ 
                background: linear-gradient(135deg, #005eb8 0%, #009345 100%); 
                padding: 30px; 
                text-align: center; 
                color: white; 
            }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: bold; letter-spacing: 1px; }}
            .content {{ padding: 30px; color: #333333; }}
            .ticket-card {{
                background-color: #f8fcf9;
                border-left: 5px solid #009345;
                padding: 20px;
                margin: 20px 0;
                border-radius: 4px;
            }}
            .label {{ font-size: 12px; color: #888888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }}
            .value {{ font-size: 18px; font-weight: bold; color: #005eb8; margin-bottom: 15px; }}
            .footer {{ background-color: #f0f0f0; padding: 20px; text-align: center; font-size: 12px; color: #888888; }}
            .btn {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #005eb8;
                color: #ffffff !important;
                text-decoration: none;
                border-radius: 25px;
                font-weight: bold;
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Smart Transport București</h1>
                <p style="margin-top: 10px; opacity: 0.9;">Confirmare Plată</p>
            </div>
            <div class="content">
                <p>Salut,</p>
                <p>Îți mulțumim că folosești serviciile noastre! Biletul tău a fost activat cu succes.</p>
                
                <div class="ticket-card">
                    <div class="label">Tip Bilet</div>
                    <div class="value" style="font-size: 22px;">{ticket_details['type']}</div>
                    
                    <div class="label">Preț</div>
                    <div class="value">{ticket_details['price']} RON</div>
                    
                    <div class="label">Valabil Până La</div>
                    <div class="value" style="color: #d9534f;">{ticket_details['expiry']}</div>
                    
                    <div class="label">ID Tranzacție</div>
                    <div class="value" style="margin-bottom: 0; color: #333;">#{ticket_details.get('id', 'N/A')}</div>
                </div>

                <p style="text-align: center;">
                    <a href="http://localhost:5000/tickets" class="btn">Vezi Biletul în Aplicație</a>
                </p>
            </div>
            <div class="footer">
                &copy; 2025 STB Planner. Toate drepturile rezervate.<br>
                Acesta este un mesaj automat. Te rugăm să nu răspunzi.
            </div>
        </div>
    </body>
    </html>
    """

    # Versiune text simplu (fallback)
    text_content = f"Salut! Ai cumpărat biletul: {ticket_details['type']}. Valabil până la: {ticket_details['expiry']}. Preț: {ticket_details['price']} RON."

    # Atașare părți
    msg.attach(MIMEText(text_content, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    try:
        print(f"🔌 Conectare la {SMTP_SERVER}...")
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
            
        print(f"✅ Email trimis cu succes către {to_email}!")
        return True

    except Exception as e:
        print(f"❌ Eroare la trimiterea emailului: {str(e)}")
        return False