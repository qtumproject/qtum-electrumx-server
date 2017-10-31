#!/bin/sh
###################

ulimit -n 65535

export COIN=Qtum
export DAEMON_URL=http://user:password@127.0.0.1
export NET=testnet
export DB_DIRECTORY=$HOME/.electrumx/testnet_db
export HOST=0.0.0.0
export SSL_KEYFILE=$HOME/.electrumx/keyfile.key
export SSL_CERTFILE=$HOME/.electrumx/certfile.crt
export ALLOW_ROOT=true

python3.6 electrumx_server.py