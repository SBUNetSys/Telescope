package main

import (
	"bufio"

	"encoding/json"
	"flag"
	"fmt"
	"github.com/libp2p/go-msgio"
	"io"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
)

type WantedCID struct {
	Cid      string `json:"cid"`
	FileType string `json:"type"`
}

// tcpserver which the client subscribed to
type tcpServer struct {
	// The address of the client.
	remote net.TCPAddr

	// The TCP connection.
	conn net.Conn

	// A 4-byte, big-endian frame-delimited writer.
	writer msgio.WriteCloser

	// A 4-byte, big-endian frame-delimited reader.
	reader msgio.ReadCloser
}

func establishConnection(serverAddr string, serverPort string) (net.Conn, net.TCPAddr) {
	tcpAddr, err := net.ResolveTCPAddr("tcp", fmt.Sprintf("%s:%s", serverAddr, serverPort))
	if err != nil {
		fmt.Printf("Error at resolving tcp address %s:%s", serverAddr, serverPort)
	}
	conn, err := net.DialTCP("tcp", nil, tcpAddr)
	if err != nil {
		fmt.Printf("Error at dialing tcp address %s:%s", serverAddr, serverPort)
		os.Exit(-1)
	}
	return conn, *tcpAddr
}
func main() {
	var inputFile string
	log.SetOutput(os.Stdout)
	flag.StringVar(&inputFile, "i", "", "input files to read")
	flag.Parse()
	serverAddr := "127.0.0.1"
	serverPort := "29998"
	//start connection
	c, tcpAddr := establishConnection(serverAddr, serverPort)
	server := &tcpServer{
		remote: tcpAddr,
		conn:   c,
		writer: msgio.NewWriter(c),
		reader: msgio.NewReader(c),
	}
	// cleaning for connection
	connect := make(chan os.Signal)
	signal.Notify(connect, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-connect
		c.Close()
		os.Exit(1)
	}()

	// open read file
	f, err := os.OpenFile(inputFile, os.O_RDONLY, os.ModePerm)
	if err != nil {
		log.Fatalf("open file error: %v", err)
		return
	}
	defer f.Close()

	rd := bufio.NewReader(f)

	for {
		line, _, err := rd.ReadLine()
		if err == io.EOF {
			break
		}
		//log.Printf("%s", line)

		newData := WantedCID{
			Cid:      string(line),
			FileType: "video",
		}
		buf, err := json.Marshal(newData)
		if err != nil {
			log.Printf("Error %s", err)
		}
		err = server.writer.WriteMsg(buf)
		if err != nil {
			log.Printf("Error %s", err)
		}
	}

}
