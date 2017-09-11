#!/bin/sh
###################

export COIN=Qtum
export DAEMON_URL=http://user:password@127.0.0.1:3889
export NET=skynet
export DB_DIRECTORY=~/.electrumx/db
export TCP_PORT=50001
export SSL_PORT=50002
export SSL_KEYFILE=~/.electrumx/keyfile.key
export SSL_CERTFILE=~/.electrumx/certfile.crt
export RPC_PORT=8000

python3 electrumx_server.py