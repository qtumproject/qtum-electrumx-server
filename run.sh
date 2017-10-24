#!/bin/sh
###################

ulimit -n 10000

export COIN=Qtum
export DAEMON_URL=http://user:password@127.0.0.1
export NET=mainnet
export DB_DIRECTORY=~/.electrumx/db
export HOST=0.0.0.0
export SSL_KEYFILE=~/.electrumx/keyfile.key
export SSL_CERTFILE=~/.electrumx/certfile.crt
export ALLOW_ROOT=true

python3 electrumx_server.py