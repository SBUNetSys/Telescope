package main

import (
	"log"
	"net/http"
	"time"
)

type BufferedWriter struct {
	http.ResponseWriter
	body   []byte
	size   int
	status int
}

//func (r *FakeResponse) Header() http.Header {
//	return r.headers
//}
//
//func (r *FakeResponse) Write(body []byte) (int, error) {
//	r.body = body
//	return len(body), nil
//}
//
//func (r *FakeResponse) WriteHeader(status int) {
//	r.status = status
//}

type RoundTripper struct {
	Bandwidth float64
}

func NewRoundTripper() RoundTripper {
	return RoundTripper{
		Bandwidth: 10 * 1024 * 1024,
	}
}

func (transport RoundTripper) RoundTrip(r *http.Request) (*http.Response, error) {
	start := time.Now()
	resp, err := http.DefaultTransport.RoundTrip(r)
	delta := time.Since(start)
	log.Println("Round trip", delta)

	return resp, err
}
