# /app/app_main.py
import time

def healthcheck():
    # If you want to force a rollback test, raise an exception here
    # raise RuntimeError("fail healthcheck")
    return True

def main():
    print("Mock App v2 running.")
    i = 0
    while True:
        print("tick", i)
        i += 1
        time.sleep(2)
