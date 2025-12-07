import smtplib
from email.mime.text import MIMEText

def send_ticket_email(to_email, ticket_details):
    # Configurare SMTP (exemplu Gmail)
    sender = "emailul_tau@gmail.com"
    password = "parola_aplicatiei"
    
    msg = MIMEText(f"Salut! Ai cumparat biletul: {ticket_details['type']}.\nValabil pana la: {ticket_details['expiry']}\nPret: {ticket_details['price']} RON")
    msg['Subject'] = 'Confirmare Bilet Transport Bucuresti'
    msg['From'] = sender
    msg['To'] = to_email

    try:
        # Poti comenta liniile de send real cat timp testezi
        # with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
        #    smtp_server.login(sender, password)
        #    smtp_server.sendmail(sender, to_email, msg.as_string())
        print(f"📧 SIMULARE: Email trimis catre {to_email} cu biletul {ticket_details['type']}")
        return True
    except Exception as e:
        print(f"Eroare email: {e}")
        return False