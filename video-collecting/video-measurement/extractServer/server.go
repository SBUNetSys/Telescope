package main

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/ipfs/go-cid"
	"github.com/libp2p/go-msgio"
	"io"
	"log"
	"math/rand"
	"net"
	"os"
	"os/exec"
	"path"
	"sync"
	"time"
)

const (
	HOST    = "0.0.0.0"
	PORT    = "29998"
	TYPE    = "tcp"
	SaveDir = "/out/"
)

type RunningVideo struct {
	mu    sync.Mutex
	count int64
}

func (r *RunningVideo) addRunningVideo() bool {
	r.mu.Lock()
	if r.count < 12 {
		r.count += 1
		r.mu.Unlock()
		return true
	} else {
		r.mu.Unlock()
		return false
	}

}
func (r *RunningVideo) subRunningVideo() {
	r.mu.Lock()
	r.count -= 1
	r.mu.Unlock()
}

type VideoQueue struct {
	mu     sync.Mutex
	videos []*VideoTask
}

func (q *VideoQueue) pushVideo(cid cid.Cid, saveDir string) {
	q.mu.Lock()
	q.videos = append(q.videos, &VideoTask{cid, saveDir})
	q.mu.Unlock()
}
func (q *VideoQueue) popVideo() *VideoTask {
	q.mu.Lock()
	videoTask := q.videos[0]
	q.videos = q.videos[1:]
	q.mu.Unlock()
	return videoTask
}

type VideoTask struct {
	cidStr  cid.Cid
	saveDir string
}

type WantedCID struct {
	Cid      string `json:"cid"`
	FileType string `json:"type"`
}

var runningQueue RunningVideo
var videoQueue VideoQueue

func dequeueVideo() {
	for {
		if len(videoQueue.videos) == 0 {
			time.Sleep(time.Second * 1)
		} else {
			videoTask := videoQueue.popVideo()
			for {
				if runningQueue.addRunningVideo() {
					log.Printf("Added video to Running Video Queue(%d/16) %s",
						runningQueue.count, videoTask.cidStr)
					// create file for video and its provider information
					videoSaveDir := path.Join(videoTask.saveDir, videoTask.cidStr.String())
					err := os.MkdirAll(videoSaveDir, os.ModePerm)
					if err != nil {
						log.Printf("Failed create dir %s", err)
						return
					}
					go collectMetric(videoTask.cidStr, videoSaveDir)
					break
				} else {
					log.Printf("Running Video Queue is full %d/16 sleep for 1min", runningQueue.count)
					// sleep for a random number avoid all wake collusion
					sleepTime := rand.Intn(60) + 60
					time.Sleep(time.Second * time.Duration(sleepTime))
				}
			}
		}
	}
}
func collectMetric(cid cid.Cid, saveDir string) {
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Minute)
	defer cancel()
	if ctx.Err() == context.DeadlineExceeded {
		// Command was killed
		runningQueue.subRunningVideo()
		log.Printf("Collect metric cid %s timeout", cid)
	}
	if err := exec.CommandContext(ctx, "python3", "-u", "record.py",
		"-c", cid.String(),
		"-f", "/log-output/daemon.txt",
		"-d", saveDir).Run(); err != nil {
		log.Printf("Failed excute collect metric cid %s err %s", cid, err)
		if err != nil {
			log.Printf("%s", err)
		}
		runningQueue.subRunningVideo()
		return
	}
	log.Printf("Collect metric cid %s cid success", cid)
	runningQueue.subRunningVideo()
	//cmd := exec.Command("python3", "record.py",
	//	"-c", cid.String(),
	//	"-f", "daemon.txt",
	//	"-d", saveDir)
	//log.Printf("Running cmd %s", cmd.String())
	//err := cmd.Run()
	//if err != nil {
	//	log.Printf("Failed excute collect metric cid %s err %s", cid, err)
	//	out, err := cmd.Output()
	//	if err != nil {
	//		log.Printf("%s", err)
	//	}
	//	log.Printf(string(out))
	//	return
	//}

}
func downloadFile(cid cid.Cid, saveDir string, gatewayUrl string) {
	log.Printf("Processing cid %s", cid)
	// enqueue
	videoQueue.pushVideo(cid, saveDir)
	// TODO start collecting metric about provider
	//for {
	//	if runningQueue.addRunningVideo() {
	//		log.Printf("Added video to Running Video Queue(%d/16) %s", runningQueue.count, cid)
	//		collectMetric(cid, videoSaveDir)
	//		return
	//	} else {
	//		log.Printf("Running Video Queue is full %d/16 sleep for 1min", runningQueue.count)
	//		// sleep for a random number avoid all wake collusion
	//		sleepTime := rand.Intn(60) + 60
	//		time.Sleep(time.Second * time.Duration(sleepTime))
	//	}
	//}

	// now save video
	//saveFile := path.Join(videoSaveDir, cid.String())
	//out, err := os.Create(saveFile)
	//if err != nil {
	//	log.Printf("Failed create cid file %s", cid)
	//	return
	//}

	// Write the body to file
	//_, err = io.Copy(out, fileData.Body)
	//if err != nil {
	//	log.Printf("Failed create cid file %s", cid)
	//	return
	//}

	//out.Close()
}

func main() {
	// get server information from env
	url, ok := os.LookupEnv("SERVER_URL")
	if !ok {
		url = HOST + ":" + PORT
	}

	gatewayUrl, ok := os.LookupEnv("IPFS_GATEWAY_URL")
	if !ok {
		gatewayUrl = "http://127.0.0.1:8080"
	}
	log.Printf("Gateway addrs %s", gatewayUrl)

	listen, err := net.Listen(TYPE, url)
	if err != nil {
		log.Fatal(err)
		os.Exit(1)
	}
	go dequeueVideo()
	// close listener
	defer listen.Close()
	log.Printf("Start listening on URL %s", url)
	for {
		conn, err := listen.Accept()
		if err != nil {
			log.Fatal(err)
			os.Exit(1)
		}
		go handleIncomingRequest(conn, gatewayUrl)
	}
}

func handleIncomingRequest(c net.Conn, gatewayUrl string) {
	fmt.Printf("Serving %s\n", c.RemoteAddr().String())
	reader := msgio.NewReader(c)
	for {
		msg, err := reader.ReadMsg()
		if err != nil {
			if err == io.EOF {
				log.Printf("Recived EOF from connection")
				break
			}
			log.Printf("Error at reading msg %s", err)
			continue
		}
		msgRecvd := &WantedCID{}
		err = json.Unmarshal(msg, msgRecvd)
		if err != nil {
			log.Printf("Failed unmarshal data %s", msg)
			continue
		}
		log.Printf("Processing %s with type of %s", msgRecvd.Cid, msgRecvd.FileType)
		newCid, err := cid.Decode(msgRecvd.Cid)
		if err != nil {
			log.Printf("Invalid cid %s", msgRecvd.Cid)
			continue
		}
		// download cid
		downloadFile(newCid, SaveDir, gatewayUrl)
	}
	c.Close()
}
