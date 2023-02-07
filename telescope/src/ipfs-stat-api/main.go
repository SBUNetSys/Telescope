package main

import (
	"bytes"
	_ "encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"math"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/hare1039/go-mpd"
	"github.com/unki2aut/go-xsd-types"

	"github.com/mikioh/tcp"
	"github.com/mikioh/tcpinfo"
)

func getPathInfo(c *gin.Context) {

}

func main() {
	if len(os.Args) != 3 {
		fmt.Println(os.Args[0] + " listen_address")
	}

	var err error
	remote, err = url.Parse(os.Args[1])
	if err != nil {
		panic(err)
	}

	r := gin.Default()

	//r.GET("/*path", proxyHandle)
	r.GET("/pathInfo", settings)

	s := http.Server{
		Addr:    os.Args[1],
		Handler: r,
	}
	s.SetKeepAlivesEnabled(false)
	s.ListenAndServe()
}
