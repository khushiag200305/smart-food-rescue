"""Build the Lambda upload package:  python lambda/build.py
Produces lambda/expire_listings.zip, ready for "Upload from .zip file" in the Lambda console.

Works on Windows, Mac and Linux: pip downloads Linux builds of the libraries,
because Lambda runs on Amazon Linux (x86_64, Python 3.12).
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
OUT = os.path.join(HERE, "expire_listings")  # make_archive adds .zip

shutil.rmtree(BUILD, ignore_errors=True)
os.makedirs(BUILD)

subprocess.check_call([
    sys.executable, "-m", "pip", "install", "PyMySQL", "cryptography",
    "--target", BUILD,
    "--platform", "manylinux2014_x86_64",
    "--implementation", "cp",
    "--python-version", "3.12",
    "--only-binary=:all:",
    "--upgrade", "--quiet",
])
shutil.copy(os.path.join(HERE, "expire_listings", "lambda_function.py"), BUILD)
shutil.copy(os.path.join(ROOT, "app", "expiry.py"), BUILD)

zip_path = shutil.make_archive(OUT, "zip", BUILD)
shutil.rmtree(BUILD)
print(f"Built {zip_path} ({os.path.getsize(zip_path) // 1024} KB)")
