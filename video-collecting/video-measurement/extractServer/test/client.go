package main

import (
	"encoding/json"
	"fmt"
	"github.com/libp2p/go-msgio"
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
	serverAddr := "127.0.0.1"
	serverPort := "29999"
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
	//https://ipfs.io/ipfs/QmRTSA1UFHSx3z7taNRwUVM8AjB2EQwKvyZu3BfJg9QRtZ
	sampleData := WantedCID{
		Cid:      "QmRTSA1UFHSx3z7taNRwUVM8AjB2EQwKvyZu3BfJg9QRtZ",
		FileType: "track",
	}

	buf, err := json.Marshal(sampleData)
	if err != nil {
		panic(err)
	}
	err = server.writer.WriteMsg(buf)
	//for i := 0; i < 10; i++ {
	//	err = server.writer.WriteMsg(buf)
	//	if err != nil {
	//		panic(err)
	//	}
	//}

}
