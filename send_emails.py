import smtplib
from email.mime.text import MIMEText

# Server details
smtp_server = "smtp.gmail.com" 
port = 587 
sender = "your_email@gmail.com"
password = "your_app_password" # Not your regular login password

# Recipient list
recipients = ["friend1@example.com", "friend2@example.com"]

try:
    # 1. Open connection
    server = smtplib.SMTP(smtp_server, port)
    server.starttls()
    server.login(sender, password)

    # 2. Send emails in a loop
    for receiver in recipients:
        msg = MIMEText("Hello! This is a test email.")
        msg['Subject'] = "Multiple Email Test"
        msg['From'] = sender
        msg['To'] = receiver
        
        server.send_message(msg)
    
    # 3. Close connection
    server.quit()
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
