import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import logging
import time
from functools import wraps

# Configuración de email mejorada
SMTP_USER = os.getenv("EMAIL_SENDER")  # Cambio para usar variables coherentes
SMTP_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", 587))
SMTP_RECEIVER = os.getenv("EMAIL_RECEIVER", SMTP_USER)

# Control de reintentos y rate limiting
email_failures = 0
last_email_attempt = 0
EMAIL_COOLDOWN = 60  # 1 minuto entre intentos fallidos
MAX_EMAIL_FAILURES = 5  # Máximo 5 fallos consecutivos

def retry_email(max_retries=3, delay=5):
    """Decorador para reintentar envío de emails"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:  # Último intento
                        raise e
                    logging.warning(f"Intento {attempt + 1} de email falló: {e}. Reintentando en {delay}s...")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

@retry_email(max_retries=2, delay=3)
def send_email(subject, body, html=False):
    global email_failures, last_email_attempt
    
    # Verificar si el email está configurado
    if not SMTP_USER or not SMTP_PASSWORD:
        logging.warning("Email no configurado - saltando envío")
        return True  # No es un error crítico
    
    # Control de rate limiting después de fallos
    current_time = time.time()
    if email_failures >= MAX_EMAIL_FAILURES:
        if current_time - last_email_attempt < EMAIL_COOLDOWN:
            logging.info(f"Email en cooldown por fallos múltiples - esperando {EMAIL_COOLDOWN - (current_time - last_email_attempt):.0f}s")
            return True  # No reintentar todavía
        else:
            # Reset del contador después del cooldown
            email_failures = 0
    
    last_email_attempt = current_time
    
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_USER
        msg["To"] = SMTP_RECEIVER
        msg["Subject"] = subject

        if html:
            part = MIMEText(body, "html", 'utf-8')
        else:
            part = MIMEText(body, "plain", 'utf-8')

        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        # Resetear contador de fallos en éxito
        email_failures = 0
        logging.info(f"Email enviado exitosamente: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        email_failures += 1
        error_msg = f"Error de autenticación SMTP (fallo {email_failures}/{MAX_EMAIL_FAILURES}): {e}"
        logging.error(error_msg)
        
        if email_failures >= MAX_EMAIL_FAILURES:
            logging.error("Máximo de fallos de email alcanzado - deshabilitando envíos temporalmente")
        
        return False
        
    except Exception as e:
        email_failures += 1
        error_msg = f"Error enviando email (fallo {email_failures}/{MAX_EMAIL_FAILURES}): {e}"
        logging.error(error_msg)
        return False
