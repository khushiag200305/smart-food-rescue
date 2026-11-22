"""Email notifications, using two AWS services for two different jobs.

Amazon SNS (publish/subscribe, one message -> many people):
    Topic "smartfood-food-alerts". Every verified NGO is subscribed to it, so when a donor
    posts food, ONE publish reaches ALL NGOs. AWS emails each NGO a confirmation link the
    first time; they receive alerts after confirming.

Amazon SES (transactional email, one message -> one specific person):
    - donor:  "an NGO requested your food"
    - NGO:    "your request was approved / not approved"
    - NGO:    "your organisation has been verified"
    In the SES sandbox, sender AND recipient addresses must be verified in the SES console.

Both are off unless SNS_TOPIC_ARN / SES_SENDER are set, so local development prints a log
line instead of sending. A failure is logged and never breaks the page the user is using.
"""
from flask import current_app, url_for

from .aws import client
from .utils import fmt_dt


def _log():
    return current_app.logger


# --------------------------------------------------------------------- SES ---
def send_email(to, subject, body):
    sender = current_app.config.get("SES_SENDER")
    if not sender:
        _log().info("email_skipped (SES_SENDER not set) to=%s subject=%r", to, subject)
        return False
    try:
        client("ses").send_email(
            Source=sender,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        _log().info("email_sent to=%s subject=%r", to, subject)
        return True
    except Exception:
        _log().exception("email_failed to=%s subject=%r", to, subject)
        return False


SIGNATURE = "\n\n- Smart Food Rescue"


def request_received(donor, ngo, listing, message):
    body = (f"Hello {donor['name']},\n\n"
            f"{ngo['organization']} has requested your donation \"{listing['food_name']}\" "
            f"({listing['quantity']} meals).\n")
    if message:
        body += f"\nTheir note: \"{message}\"\n"
    body += (f"\nApprove or reject the request here:\n{url_for('donor.dashboard', _external=True)}"
             + SIGNATURE)
    send_email(donor["email"], f"New pickup request: {listing['food_name']}", body)


def request_decided(ngo, listing, donor, approved):
    if approved:
        subject = f"Approved: pick up {listing['food_name']}"
        body = (f"Hello {ngo['name']},\n\n"
                f"{donor['organization']} approved your request for \"{listing['food_name']}\" "
                f"({listing['quantity']} meals).\n\n"
                f"Pickup address: {listing['location']}\n"
                f"Contact: {donor['phone'] or donor['email']}\n\n"
                f"Mark it as picked up once collected:\n{url_for('ngo.my_requests', _external=True)}")
    else:
        subject = f"Request not approved: {listing['food_name']}"
        body = (f"Hello {ngo['name']},\n\n"
                f"Your request for \"{listing['food_name']}\" was not approved this time "
                f"(it may have gone to another NGO).\n\n"
                f"See other available food:\n{url_for('ngo.browse', _external=True)}")
    send_email(ngo["email"], subject, body + SIGNATURE)


def ngo_verified(ngo):
    body = (f"Hello {ngo['name']},\n\n"
            f"{ngo['organization']} has been verified on Smart Food Rescue. "
            f"You can now request surplus food:\n{url_for('ngo.browse', _external=True)}\n\n"
            f"You will also get a separate email from AWS asking you to confirm food alerts. "
            f"Confirm it to be emailed whenever new food is posted.")
    send_email(ngo["email"], "Your NGO is verified", body + SIGNATURE)
    subscribe_to_food_alerts(ngo["email"])


# --------------------------------------------------------------------- SNS ---
def _ascii(text, limit):
    """SNS subjects must be ASCII and under 100 characters."""
    return text.encode("ascii", "ignore").decode()[:limit]


def subscribe_to_food_alerts(email):
    arn = current_app.config.get("SNS_TOPIC_ARN")
    if not arn:
        _log().info("sns_subscribe_skipped (SNS_TOPIC_ARN not set) email=%s", email)
        return
    try:
        client("sns").subscribe(TopicArn=arn, Protocol="email", Endpoint=email)
        _log().info("sns_subscribed email=%s", email)
    except Exception:
        _log().exception("sns_subscribe_failed email=%s", email)


def new_food_alert(listing, donor):
    arn = current_app.config.get("SNS_TOPIC_ARN")
    subject = _ascii(f"Food available: {listing['food_name']} ({listing['quantity']} meals)", 99)
    if not arn:
        _log().info("sns_publish_skipped (SNS_TOPIC_ARN not set) subject=%r", subject)
        return
    message = (f"New surplus food has been posted on Smart Food Rescue.\n\n"
               f"Food:       {listing['food_name']} ({listing['food_type']})\n"
               f"Quantity:   {listing['quantity']} meals\n"
               f"Donor:      {donor['organization']}\n"
               f"Location:   {listing['location']}\n"
               f"Pick up by: {fmt_dt(listing['available_until'])}\n\n"
               f"Request it here (verified NGOs only):\n{url_for('ngo.browse', _external=True)}")
    try:
        client("sns").publish(TopicArn=arn, Subject=subject, Message=message)
        _log().info("sns_published listing_id=%s", listing["id"])
    except Exception:
        _log().exception("sns_publish_failed listing_id=%s", listing["id"])
