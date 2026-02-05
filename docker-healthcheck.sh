#!/bin/sh
# Simple healthcheck script: tries to fetch /login
curl -sfS http://localhost:8080/login >/dev/null 2>&1
