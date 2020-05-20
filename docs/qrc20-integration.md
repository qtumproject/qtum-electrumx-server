# QRC20 Integration

For QRC20 Tokens, the following apis are needed.

## blockchain.contract.event.subscribe(hash160, contract_addr, topic)
this can be uesd to receive token balance change notifications, similar to `blockchain.scripthash.subscribe`.

* `hash160`: hex format of user address
* `contract_addr`: hex format of QRC20 token contract address
* `topic`: for QRC20, just use `ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` (Keccak-256 hash of `event Transfer(address indexed _from, address indexed _to, uint256 _value)`)

## blockchain.contract.event.get_history(hash160, contract_addr, topic)
this can be used to retrieve QRC20 token transfer history, params are the same as `blockchain.contract.event.subscribe`, and it returns a list of map{tx_hash, height, log_index}.

* `log_index`: the position for this event log in its transaction.

## blochchain.transaction.get_receipt(txid)
this can be used to get eventlogs in the transaction, the returned data is the same as Qtum Core RPC `gettransactionreceipt`. 

from the eventlogs, we can get QRC20 Token transafer informations(from、to、amount).

## blockchain.token.get_info(token_address)
this can be used to get the basic information(name、decimals、total_supply、symbol) of a QRC20 token.
