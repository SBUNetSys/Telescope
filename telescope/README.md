[Telescope source code]

In this repo, we provide the Telescope source code. Please put the `./src`
folder into your local `$GOPATH/src/github/hare1039` build path.

We also provide a [VM link] (https://drive.google.com/drive/folders/1jmOjIC1rcC7oT8vTftN8SKAfLBmypXjF?usp=sharing) to show how to run Telescope. This is only an emulation environment for quick testing. For real internet testing, please follow the instruction in the directory in the test dir.

Inside this vm, please go to `$GOPATH/src/github.com/hare1039/Telescope` to see the source code,
and go to `/mnt/ipfs-abr-test/test-dir` to run the experiments.

[VM setup]

Please make sure the client have a display attached, 8 cores and the RAM size > 32G. Or the result maybe unstable due to the insufficient computation power.

This test script demonstrate how to setup the test environment.

File details:
 - `./caddy`: DASH video file
 - `./caddy/second_10min_4k_dash.html`: the main webpage to play the video
 - `./caddy/second.js`: the main JavaScript to load dash.js and the settings
 - `./docker`: (remote) ipfs storage. It stores the DASH video file
 - `./ipfs-mount1`: the pre-added video configs
 - `./ipfs-mount-dummy`: a placeholder for the testing script
 - `./rawdocker`: (local) IPFS gateway. IPFS gateway that loads videos from the network
 - `./rawdocker/ipfs`: Modified IPFS binary.
 - `./record`: (Not used)
 - `/home/hare1039/gopath/src/github.com/hare1039/Telescope`: the Telescope source code; to compile, please use `go build` and copy the binary to `./rawdocker`.
 - `./test-dir`: place to run the experiments
 - `./test-dir/qualist.txt`: list of load quality
 - `./test-dir/run-test-internet-ipfs.sh`: the test script
 - `./test-dir/run-test-old.py`: the test helper and driver

To start, edit the test script with the environments variable, and
start the test by `./test-dir/run-test-internet-ipfs.sh`.

For more detail, please refer to the README inside the VM.