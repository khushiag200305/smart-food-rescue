# Smart Food Rescue

A cloud-based platform connecting food donors (college messes, restaurants, hotels, cafeterias) with NGOs that redistribute surplus food.
Course project for **UCS531 – Cloud Computing**.

## Cloud services used (AWS, region `ap-southeast-2` Sydney)

| Service | What it does in this project |
|---------|------------------------------|
| **EC2** | Hosts the Flask web app (Gunicorn + Nginx) |
| **RDS (MySQL)** | Stores users, food listings and pickup requests |
| **S3** | Stores food photos and NGO certificates (private bucket, presigned URLs) |
| **IAM** | Roles give EC2 and Lambda exactly the permissions they need; no access keys in code |
| **Lambda** | Serverless job that expires listings past their pickup time and declines their pending requests |
| **EventBridge** | Runs the Lambda every 15 minutes |
| **SNS** | Publish/subscribe: one "new food posted" message is delivered to every verified NGO |
| **SES** | Transactional email to one person: new request (to donor), approved / not approved (to NGO), NGO verified |
| **CloudWatch** | App and server logs, business metrics (meals rescued, donations), dashboard, alarms |

## Features

| Role  | Can do |
|-------|--------|
| Donor | Register, list food with a photo, see NGO requests, approve/reject, confirm handover |
| NGO   | Register with certificate, browse/search food, request pickup, track status, mark picked up |
| Admin | Verify NGOs, view certificates, deactivate users, remove listings, view platform stats |

Donation lifecycle: **Available → Requested → Approved → Picked up → Completed**.
Listings still available or requested after their pickup time become **Expired** (set by the Lambda job).
Approving one NGO's request automatically declines the others for that listing.

## Design

Food always has a deadline, so every listing is shown as a **pickup ticket**: the "pick up by" time
leads, with a live countdown that turns yellow in the last hour. Donors and NGOs follow each donation on
a five-step track (Listed, Requested, Approved, Picked up, Done). The stylesheet and script are plain
CSS and JavaScript in `app/static/`, so pages load fast and look the same even without internet access
(only the Archivo web font comes from Google Fonts, with a system-font fallback).

## Project structure

```
smart-food-rescue/
├── run.py                  # entry point (gunicorn run:app)
├── schema.sql              # MySQL schema for AWS RDS
├── schema_sqlite.sql       # same schema for local development
├── requirements.txt
├── .env.example            # copy to .env (never commit .env)
├── app/
│   ├── __init__.py         # app factory, config, logging
│   ├── db.py               # plain-SQL helper (SQLite locally, MySQL on RDS) + CLI commands
│   ├── storage.py          # S3 upload / presigned URLs / delete (local folder fallback)
│   ├── notifications.py    # SNS food alerts + SES emails (logged instead of sent locally)
│   ├── metrics.py          # CloudWatch business metrics
│   ├── expiry.py           # listing-expiry logic, shared by the Lambda and a local command
│   ├── aws.py              # shared boto3 clients
│   ├── security.py         # login sessions, role checks, CSRF protection
│   ├── utils.py            # time helpers, status badges
│   ├── auth.py             # register / login / logout
│   ├── donor.py            # donor dashboard, new listing, approve/reject, complete
│   ├── ngo.py              # browse + filters, request, my requests, picked up
│   ├── admin.py            # verify NGOs, manage users, remove listings, stats
│   ├── demo.py             # seed-demo command for presentation data
│   ├── templates/          # Jinja HTML pages (_ui.html holds the shared ticket, track and icons)
│   └── static/             # css/style.css and js/app.js: the site's own design, no CSS framework
├── lambda/
│   ├── expire_listings/lambda_function.py   # AWS Lambda handler
│   └── build.py            # builds lambda/expire_listings.zip for upload
├── demo_data/              # demo photos + sample certificates (used by seed-demo)
└── deploy/
    ├── iam-policy.json             # least-privilege policy for the EC2 role (S3, SNS, SES)
    ├── cloudwatch-agent-config.json# ships app logs + memory metric to CloudWatch
    ├── cloudwatch-dashboard.json   # dashboard definition
    ├── smartfood.service           # systemd unit for Gunicorn (writes logs to /var/log/smartfood)
    └── nginx.conf                  # reverse proxy on port 80
```

## 1. Run locally (no AWS needed)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install flask python-dotenv   # all the local version needs
cp .env.example .env              # Windows: copy .env.example .env
flask --app run init-db
flask --app run seed-demo --reset
flask --app run run --debug
```
Open http://127.0.0.1:5000. Locally the app uses `local.db` (SQLite) and saves photos to `uploads/`.
Emails, SNS alerts and metrics are **printed in the terminal** instead of sent, so you can see what
would go to AWS.

Run the expiry job locally (the Lambda does this on AWS):
```bash
flask --app run expire-listings
```

> Upgrading from an older copy? Delete `local.db` and run `init-db` + `seed-demo` again, because the
> database now has an `expired` status.

### Demo data (for presentations)
```bash
flask --app run seed-demo --reset  # wipe everything and start fresh before each demo
```
Creates 4 donors, 3 NGOs (one unverified) and an admin, plus 13 listings with photos covering every
status. All demo accounts use the password `Demo@1234` (e.g. `mess@demo.in`, `rotighar@demo.in`,
`admin@demo.in`). One listing ("Jeera rice and dal") is already overdue, so the expiry job has
something to expire. Run it on EC2 and the photos upload to S3.

The food photos in `demo_data/photos/` are drawn illustrations. To use real photos, replace a file with
your own picture under the same name (e.g. `rice_dal.jpg` or `rice_dal.png`) and re-run with `--reset`.
The NGO certificates in `demo_data/certificates/` are watermarked "SAMPLE · DEMO DATA".

## 2. Deploy the core app on AWS (region `ap-southeast-2`, Sydney)

> New AWS accounts on the Free plan are locked to one region. Ours is Sydney (`ap-southeast-2`),
> so every service is created there. Other regions need the paid plan.

### a) S3 bucket
1. S3 → Create bucket, e.g. `smartfood-rescue-<teamname>`. Keep **Block all public access ON** (the app uses presigned URLs).

### b) IAM role for EC2
1. IAM → Policies → Create policy → JSON → paste `deploy/iam-policy.json`. Replace `YOUR-BUCKET-NAME`
   and `YOUR-ACCOUNT-ID` (12 digits, top-right menu of the console). Name it `SmartFoodAppAccess`.
2. IAM → Roles → Create role → *AWS service: EC2* → attach `SmartFoodAppAccess` **and** the AWS managed
   policy `CloudWatchAgentServerPolicy`. Name it `SmartFoodEC2Role`.

### c) RDS MySQL
1. RDS → Create database → MySQL 8 → **Free tier** template → `db.t3.micro` / `db.t4g.micro`.
2. Set master username/password. **Public access: No.**
3. After EC2 exists: edit the RDS security group to allow **port 3306 only from the EC2 instance's security group**.

### d) EC2
1. Launch Ubuntu 24.04, `t2.micro`/`t3.micro` (free tier). Attach IAM role `SmartFoodEC2Role` (Advanced details → IAM instance profile).
2. Security group: allow SSH (22) from *My IP*, HTTP (80) from anywhere.
3. SSH in and run:
```bash
sudo apt update && sudo apt install -y python3-venv nginx git mysql-client
git clone https://github.com/<you>/smart-food-rescue.git && cd smart-food-rescue
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && nano .env     # set SECRET_KEY, DATABASE_URL, S3_BUCKET
mysql -h <rds-endpoint> -u admin -p -e "CREATE DATABASE smart_food_rescue CHARACTER SET utf8mb4;"
flask --app run init-db
flask --app run create-admin admin@yourcollege.edu 'StrongPass123'
sudo cp deploy/smartfood.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now smartfood
sudo cp deploy/nginx.conf /etc/nginx/sites-available/smartfood
sudo ln -s /etc/nginx/sites-available/smartfood /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default && sudo nginx -t && sudo systemctl reload nginx
```
Visit `http://<EC2-public-IP>`. Logs: `tail -f /var/log/smartfood/app.log`.

> Cost safety: set an AWS Budget alarm, and stop the EC2 and RDS instances when not in use.

## 3. Add Lambda, SNS, SES and CloudWatch

Do these after section 2 works.

### a) SNS topics
1. SNS → Topics → Create topic → **Standard** → name `smartfood-food-alerts`. Copy its **ARN**.
2. Create a second topic `smartfood-ops-alerts` (for CloudWatch alarms). Add an **Email** subscription
   for each team member and click the confirmation link each receives.

The app subscribes each NGO to `smartfood-food-alerts` automatically when the admin verifies it.
AWS emails the NGO a confirmation link, and alerts start after they confirm.

### b) SES
1. SES console (make sure the region is **Asia Pacific (Sydney)**) → Identities → Create identity →
   **Email address** → your team's sender address → click the link AWS emails you.
2. The account starts in the **SES sandbox**: emails only reach verified addresses. Verify each team
   member's email the same way, and use those emails when registering the donor and NGO accounts you
   demo with. (The `@demo.in` seed accounts can't receive email; the app logs the failure and carries on.)
3. Check spam folders the first time.

### c) Turn them on in the app (on EC2)
Add to `.env`, then `sudo systemctl restart smartfood`:
```
SNS_TOPIC_ARN=arn:aws:sns:ap-southeast-2:123456789012:smartfood-food-alerts
SES_SENDER=your-verified-sender@gmail.com
CLOUDWATCH_METRICS=1
```

### d) Lambda: expire overdue listings
1. **Build the package** on your laptop (needs internet): `python lambda/build.py` → creates
   `lambda/expire_listings.zip` (handler + shared `expiry.py` + PyMySQL).
2. Lambda → Create function → *Author from scratch* → name `smartfood-expire-listings`,
   runtime **Python 3.12**, architecture **x86_64**. Create.
3. Code → Upload from → .zip file → `expire_listings.zip`. Handler stays `lambda_function.lambda_handler`.
4. Configuration → General → Timeout **30 sec**.
5. Configuration → Environment variables:
   `DB_HOST` = RDS endpoint, `DB_USER`, `DB_PASSWORD`, `DB_NAME` = `smart_food_rescue`, `UTC_OFFSET_MINUTES` = `330`.
6. Configuration → Permissions → click the role name → attach `AWSLambdaVPCAccessExecutionRole`.
7. Configuration → VPC → Edit → the same VPC as RDS, 2+ subnets, and a new security group
   `smartfood-lambda-sg` (no inbound rules needed).
8. RDS security group → add inbound rule **MySQL/Aurora 3306** from `smartfood-lambda-sg`.
9. Test tab → event `{}` → Test. You should see `{"listings_expired": ..., "requests_declined": ...}`.
10. Add trigger → **EventBridge (CloudWatch Events)** → Create a new rule → Schedule expression
    `rate(15 minutes)`.

Each run logs to CloudWatch automatically, and its JSON log line becomes the metric
`SmartFoodRescue / ListingsExpired` (Embedded Metric Format: no extra API calls).

### e) CloudWatch agent on EC2 (logs + memory metric)
```bash
wget https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s \
     -c file:/home/ubuntu/smart-food-rescue/deploy/cloudwatch-agent-config.json
```
Log groups `/smartfood/app`, `/smartfood/access` and `/smartfood/error` appear in CloudWatch → Log groups.

### f) Dashboard
CloudWatch → Dashboards → Create `SmartFoodRescue` → Actions → View/edit source → paste
`deploy/cloudwatch-dashboard.json` after replacing `INSTANCE_ID` (EC2 instance ID, `i-...`) and
`DB_INSTANCE_ID` (your RDS DB identifier).

### g) Alarms (all notify `smartfood-ops-alerts`)
1. **Server down:** EC2 → `StatusCheckFailed` ≥ 1 for 2 consecutive periods.
2. **Lambda failing:** Lambda `smartfood-expire-listings` → `Errors` ≥ 1 in 15 minutes.
3. **Brute-force login attempts:** Log group `/smartfood/app` → Actions → Create metric filter →
   pattern `"event=login_failed"` → namespace `SmartFoodRescue`, metric `FailedLogins`, value `1`.
   Then alarm on `FailedLogins` Sum ≥ 5 in 5 minutes.

### h) Useful Logs Insights queries (log group `/smartfood/app`)
```
fields @timestamp, @message | filter @message like /event=/ | sort @timestamp desc | limit 50
fields @timestamp, @message | filter @message like /email_|sns_/ | sort @timestamp desc
fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc
```

> Cost: these services have free-tier allowances, but AWS's free-tier rules differ by account age.
> Keep custom metrics to about 10 (this setup uses 7) and check Billing → Free tier.

## Security notes
- Passwords hashed with Werkzeug (PBKDF2/scrypt); CSRF tokens on every form; role checks on every route.
- No AWS keys in code or `.env`: EC2 and Lambda get temporary credentials from IAM roles.
- The EC2 role can only touch one S3 bucket and one SNS topic (least privilege).
- S3 bucket is private; images are shown via presigned URLs valid for 1 hour.
- RDS is not publicly accessible; only the EC2 and Lambda security groups can reach port 3306.
- Uploaded files get random names (UUID), are type-checked and limited to 5 MB.
- Failed logins are logged and alarmed on in CloudWatch.

## Demo script
0. Run `flask --app run seed-demo --reset` so the dashboards start full. Register one donor and one NGO
   with real (SES-verified) team emails for the live part.
1. Donor posts "Rice & dal, 40 meals" with a photo → show the object in the S3 console, and the
   SNS food-alert email arriving for subscribed NGOs.
2. Admin verifies the new NGO → NGO receives the SES "verified" email and the SNS confirmation.
3. NGO requests pickup → donor gets an SES email → donor approves → NGO gets the approval email.
4. NGO marks picked up → donor confirms completed.
5. Lambda console → Test (or wait for the schedule) → "Jeera rice and dal" becomes Expired; show the
   Lambda's log in CloudWatch.
6. CloudWatch dashboard: meals rescued, donations, server CPU/memory, Lambda runs, recent app events.
