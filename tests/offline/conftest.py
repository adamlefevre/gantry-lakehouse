"""Offline fixtures: a local moto S3 server stands in for R2. No credentials are needed.

compact.py reads its env vars at import time, so they are set here, before any test module
imports it. Unconditional assignment means a developer's real .env can never leak in
(load_dotenv does not override existing variables). Run this directory in its own pytest
process, separate from tests/live, which needs the real env.
"""
import os
import socket

import boto3
import pytest
from moto.server import ThreadedMotoServer

BUCKET = "offline-test-bucket"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = _free_port()
ENDPOINT = f"http://127.0.0.1:{PORT}"

os.environ.update({
    "CLOUDFLARE_ACCOUNT_ID": "offline",
    "R2_ACCESS_KEY_ID": "offline",
    "R2_SECRET_ACCESS_KEY": "offline",
    "R2_BUCKET_NAME": BUCKET,
    "R2_ENDPOINT_OVERRIDE": ENDPOINT,
})


@pytest.fixture(scope="session", autouse=True)
def moto_server():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=PORT, verbose=False)
    server.start()
    try:
        # moto rejects region "auto" for CreateBucket, so setup uses a real region name.
        boto3.client(
            "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
            aws_access_key_id="offline", aws_secret_access_key="offline",
        ).create_bucket(Bucket=BUCKET)
        yield server
    finally:
        server.stop()
