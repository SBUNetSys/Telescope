# Collecting videos from IPFS-SEARCH

## To start collecting CIDs
1. See detail in `ipfs-search-video-fecthing` 
2. Starting download server, run `docker-compose up` inside `video-measurement` this will start the download server which listening any CIDs sends from the client. The video will be downloaded and all other metric will be collect.
3. To send CID information to the download server, see detail in `ipfs-search-video-fecthing`

### recommend create a shell script which colllecting the CID from IPFS-SEARCH and send them to the download server
