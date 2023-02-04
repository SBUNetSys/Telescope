FROM golang:1.18-alpine AS build

RUN apk add --no-cache git gcc musl-dev

WORKDIR /src/

# We want to populate the module cache based on the go.{mod,sum} files.
COPY go.mod go.sum /src/

#This is the ‘magic’ step that will download all the dependencies that are specified in
# the go.mod and go.sum file.
# Because of how the layer caching system works in Docker, the  go mod download
# command will _ only_ be re-run when the go.mod or go.sum file change
# (or when we add another docker instruction this line)
RUN go mod download && go mod graph | awk '{if ($1 !~ "@") print $2}' | xargs go get -v

# Here we copy the rest of the source code
COPY . /src/

# Run the build
ENV GORACE="halt_on_error=1"
RUN go install -v -race ./...

# This results in a single layer image
#FROM python:3.8-alpine
#RUN apk add --no-cache git gcc musl-dev tcptraceroute
FROM ubuntu:22.04
# ENV TZ="America/New_York"
WORKDIR /server/
# Install base utilities
RUN apt update && \
    apt-get install -y wget iputils-ping iperf traceroute git psmisc sudo python3 python3-pip musl-dev build-essential libssl-dev libcurl4-openssl-dev wondershaper && \
    apt-get clean
# Install anaconda
#ENV CONDA_DIR /opt/conda
#RUN wget https://repo.anaconda.com/archive/Anaconda3-2021.11-Linux-x86_64.sh -O ~/anaconda.sh && \
#    bash ~/anaconda.sh -b -p /opt/conda
## Put conda in path so we can use conda activate
#ENV PATH=$CONDA_DIR/bin:$PATH
RUN pip3 install --no-cache-dir icmplib lockfile requests pycurl

#COPY --from=build /go/bin/extractServer /usr/local/bin/extractServer
COPY --from=build /go/bin/extractServer /server/extractServer
# setup ipfs binary
COPY ipfs /server/
COPY record.py /server/
COPY init.sh /server/

# ipfs initailization
RUN ./ipfs init && \
        ./ipfs config Addresses.API "/ip4/0.0.0.0/tcp/5001" &&\
        ./ipfs config Addresses.Gateway "/ip4/0.0.0.0/tcp/8080" &&\
        ./ipfs config --json Gateway.PublicGateways '{"localhost": {"Paths": ["/ipfs"],"UseSubdomains": false} }' && \
        ./ipfs config Reprovider.Strategy pinned && \
        ./ipfs config Reprovider.Interval 0 && \
        ./ipfs config show
#CMD ["crawl"]
#ENTRYPOINT ["./extractServer"]
ENTRYPOINT ["bash", "init.sh"]
