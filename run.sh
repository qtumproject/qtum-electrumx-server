#!/bin/sh
###################

ulimit -n 10000

export COIN=Qtum
export DAEMON_URL=http://user:password@127.0.0.1:3889
export NET=mainnet
export DB_DIRECTORY=~/.electrumx/db
export HOST=0.0.0.0
export TCP_PORT=50001
export SSL_PORT=50002
export SSL_KEYFILE=~/.electrumx/keyfile.key
export SSL_CERTFILE=~/.electrumx/certfile.crt
export RPC_PORT=8200
export ALLOW_ROOT=true

python3 electrumx_server.py