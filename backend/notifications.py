"""
Notificaciones por Telegram + chequeo diario automatico de una lista de
tickers de seguimiento.

Por que 1 sola revision diaria: la cuota gratuita de la API de datos es de
25 consultas/dia con 13 segundos de espera entre cada una. Revisar el
mercado "en vivo" (cada pocos minutos) requeriria un plan pago de datos.
Con una revision diaria de hasta N tickers (2 consultas c/u) queda margen
de cuota para seguir usando el resto de la app ese mismo dia.

Variables de entorno usadas (configurar en Railway > Variables):
  TELEGRAM_BOT_TOKEN     -> token del bot (via @BotFather)
  TELEGRAM_CHAT_ID       -> tu chat id personal
  ALERT_TICKERS          -> lista separada por comas, ej: "AAPL,MSFT,NVDA"
  ALERT_MIN_SCORE        -> score minimo (LONG o SHORT) para notificar (default 60)
  ALERT_CHECK_HOUR_UTC   -> hora UTC (0-23) a la que correr el chequeo diario (default 14)
"""

import os
import time
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests


def send_email(subject: str, body_html: str) -> bool:
    """Envia un email via SMTP generico. Funciona con Gmail (usando una
    'contraseña de aplicacion', no la contraseña normal de la cuenta),
    Outlook, o cualquier proveedor SMTP. Variables de entorno:
      SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
      ALERT_EMAIL_TO (destinatario)
    """
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    to_addr = os.environ.get("ALERT_EMAIL_TO", "")

    if not (host and user and password and to_addr):
        return False

    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, [to_addr], msg.as_string())
        return True
    except Exception:
        return False


def send_telegram_message(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=15)
        return resp.status_code == 200
    except Exception:
        return False


def _format_alert(ticker: str, data: dict) -> str:
    direction = data["direction"]["direction"]
    score = data["score"]["total"] if direction == "LONG" else data["short_score"]["total"]
    price = data["quote"].get("price")
    currency = data["quote"].get("currency", "USD")
    conclusion = data["conclusion"] if direction == "LONG" else data["short_conclusion"]
    entry = conclusion.get("entry_range", [None, None])
    stop = conclusion.get("stop_loss")
    targets = conclusion.get("targets", [])

    icon = "🟢" if direction == "LONG" else "🔴"
    lines = [
        f"{icon} <b>{ticker}</b> — {direction} (score {score}/100)",
        f"Precio: {price} {currency}",
    ]
    if entry and entry[0] is not None:
        lines.append(f"Entrada sugerida: {entry[0]} - {entry[1]}")
    if stop is not None:
        lines.append(f"Stop loss: {stop}")
    if targets:
        lines.append(f"Objetivos: {', '.join(str(t) for t in targets)}")
    lines.append("\n⚠️ Screener cuantitativo educativo, no es asesoramiento financiero.")
    return "\n".join(lines)


# Registro simple en memoria de que tickers/direccion ya se notificaron hoy,
# para no mandar el mismo mensaje varias veces si el chequeo se re-ejecuta.
_already_sent_today: dict = {}


def _format_alert_html(ticker: str, data: dict) -> str:
    direction = data["direction"]["direction"]
    score = data["score"]["total"] if direction == "LONG" else data["short_score"]["total"]
    price = data["quote"].get("price")
    currency = data["quote"].get("currency", "USD")
    conclusion = data["conclusion"] if direction == "LONG" else data["short_conclusion"]
    entry = conclusion.get("entry_range", [None, None])
    stop = conclusion.get("stop_loss")
    targets = conclusion.get("targets", [])
    color = "#2FD98A" if direction == "LONG" else "#FF5C72"

    rows = f"<p><b>Precio:</b> {price} {currency}</p>"
    if entry and entry[0] is not None:
        rows += f"<p><b>Entrada sugerida:</b> {entry[0]} - {entry[1]}</p>"
    if stop is not None:
        rows += f"<p><b>Stop loss:</b> {stop}</p>"
    if targets:
        rows += f"<p><b>Objetivos:</b> {', '.join(str(t) for t in targets)}</p>"

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;">
      <h2 style="color:{color};">{ticker} — {direction} (score {score}/100)</h2>
      {rows}
      <p style="color:#888;font-size:12px;">⚠️ Screener cuantitativo educativo, no es asesoramiento financiero.</p>
    </div>
    """


def run_daily_alert_check(provider) -> dict:
    """Recorre ALERT_TICKERS, analiza cada uno, y manda un mensaje de
    Telegram para los que muestren LONG o SHORT con score >= ALERT_MIN_SCORE.
    Devuelve un resumen de lo que se envio (para loguear/depurar)."""
    from analysis import analyze_ticker  # import local para evitar ciclos

    tickers_raw = os.environ.get("ALERT_TICKERS", "")
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()][:10]
    min_score = float(os.environ.get("ALERT_MIN_SCORE", "60"))

    today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sent = []
    skipped = []
    errors = []

    for ticker in tickers:
        try:
            data = analyze_ticker(provider, ticker, "6M")
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
            continue
        if "error" in data:
            errors.append(f"{ticker}: {data['error']}")
            continue

        direction = data["direction"]["direction"]
        if direction not in ("LONG", "SHORT"):
            skipped.append(ticker)
            continue

        score = data["score"]["total"] if direction == "LONG" else data["short_score"]["total"]
        if score < min_score:
            skipped.append(ticker)
            continue

        dedup_key = f"{today_key}:{ticker}:{direction}"
        if _already_sent_today.get(dedup_key):
            skipped.append(f"{ticker} (ya enviado hoy)")
            continue

        message = _format_alert(ticker, data)
        sent_ok = False
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            if send_telegram_message(message):
                sent_ok = True
        if os.environ.get("SMTP_HOST"):
            email_body = _format_alert_html(ticker, data)
            if send_email(f"StockLens - Alerta {direction}: {ticker}", email_body):
                sent_ok = True

        if sent_ok:
            _already_sent_today[dedup_key] = True
            sent.append(ticker)
        else:
            errors.append(f"{ticker}: fallo el envio (revisa la configuracion de Telegram y/o Email)")

    return {"sent": sent, "skipped": skipped, "errors": errors, "checked_at": datetime.now(timezone.utc).isoformat()}
