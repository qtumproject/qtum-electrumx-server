# Usage
* `docker build -t qtum-image .`
* `mkdir /root/.qtum`
* `vim /root/.qtum/qtum.conf`
    ```
    rpcuser=xxx
    rpcpassword=xxx
    txindex=1
    logevents=1
    ```
* mainnet: `docker run -itd --privileged=true -v /root/.qtum:/data -p 127.0.0.1:3889:3889 -p 3888:3888 --name qtumd qtum-image`
* testnet: `docker run -itd --privileged=true -v /root/.qtum:/data -p 127.0.0.1:13889:13889 -p 13888:13888 --name qtumd-testnet qtum-image --testnet`
