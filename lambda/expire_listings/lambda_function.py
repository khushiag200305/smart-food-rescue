"""AWS Lambda: expire overdue food listings.

Trigger:  EventBridge Scheduler, rate(15 minutes)
Runtime:  Python 3.12, handler  lambda_function.lambda_handler
Network:  runs inside the VPC so it can reach the private RDS database
Env vars: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, UTC_OFFSET_MINUTES (330 = IST)

Output goes to CloudWatch Logs automatically. The JSON line in Embedded Metric Format
also becomes the CloudWatch metric SmartFoodRescue / ListingsExpired, without any API call
(the function has no internet access inside the VPC, so it can't call the CloudWatch API).
"""
import json
import os
import time

import pymysql

from expiry import expire_listings, local_now  # expiry.py is copied in by build.py


def lambda_handler(event, context):
    conn = pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ.get("DB_NAME", "smart_food_rescue"),
        connect_timeout=10,
    )
    try:
        now = local_now(int(os.environ.get("UTC_OFFSET_MINUTES", "330")))
        result = expire_listings(conn, now, placeholder="%s")
    finally:
        conn.close()

    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "SmartFoodRescue",
                "Dimensions": [["Function"]],
                "Metrics": [{"Name": "ListingsExpired", "Unit": "Count"}],
            }],
        },
        "Function": "expire-listings",
        "ListingsExpired": result["listings_expired"],
        "RequestsDeclined": result["requests_declined"],
        "CheckedAt": now,
    }))
    return result
