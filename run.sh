#!/bin/sh
###################

ulimit -n 10000

export COIN=Qtum
export DAEMON_URL=http://user:password@127.0.0.1:3889
export NET=skynet
export DB_DIRECTORY=~/.electrumx/db
export TCP_PORT=52001
export HOST=0.0.0.0
export SSL_PORT=52002
export SSL_KEYFILE=~/.electrumx/keyfile.key
export SSL_CERTFILE=~/.electrumx/certfile.crt
export RPC_PORT=8200
export ALLOW_ROOT=true

python3 electrumx_server.py