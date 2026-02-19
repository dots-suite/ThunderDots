// thunderdots/native/go/cmd/thunderdots/main.go
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"
	"unsafe"
)

// ---------------- C memory ----------------

//export ThunderDotsFree
func ThunderDotsFree(p *C.char) {
	C.free(unsafe.Pointer(p))
}

// ---------------- Config + stats ----------------

type Config struct {
	EndpointDTS     string  `json:"endpoint_dts"`
	RequestTimeout  float64 `json:"request_timeout"` // seconds
	TotalTimeout    float64 `json:"total_timeout"`   // seconds (0 = no limit)
	MaxInflight     int     `json:"max_inflight"`
	Retries         int     `json:"retries"`
	BackoffMS       int     `json:"backoff_ms"`
}

type Stats struct {
	RequestsTotal int64 `json:"requests_total"`
	HTTPErrors    int64 `json:"http_errors"`
	HTTP500       int64 `json:"http_500"`
	Timeouts      int64 `json:"timeouts"`
}

func errorsIsTimeout(err error) bool {
	if err == nil {
		return false
	}
	var nerr net.Error
	return errors.As(err, &nerr) && nerr.Timeout()
}

func isRetryStatus(code int) bool {
	return code == 429 || (code >= 500 && code <= 599)
}

func sleepBackoff(base time.Duration, attempt int) {
	if attempt <= 0 {
		time.Sleep(base)
		return
	}
	d := base * time.Duration(1<<attempt)
	j := time.Duration(time.Now().UnixNano()%50) * time.Millisecond
	time.Sleep(d + j)
}

type Limiter struct {
	inflight chan struct{}
}

func newLimiter(maxInflight int) *Limiter {
	if maxInflight <= 0 {
		maxInflight = 100
	}
	if maxInflight < 10 {
		maxInflight = 10
	}
	return &Limiter{inflight: make(chan struct{}, maxInflight)}
}

func (l *Limiter) acquire() { l.inflight <- struct{}{} }
func (l *Limiter) release() { <-l.inflight }

func httpClient(maxInflight int) *http.Client {
	if maxInflight <= 0 {
		maxInflight = 200
	}
	dialer := &net.Dialer{
		Timeout:   10 * time.Second,
		KeepAlive: 30 * time.Second,
	}
	tr := &http.Transport{
		Proxy:                 nil,
		MaxIdleConns:          maxInflight,
		MaxIdleConnsPerHost:   maxInflight,
		MaxConnsPerHost:       maxInflight,
		IdleConnTimeout:       60 * time.Second,
		ForceAttemptHTTP2:     true,
		DialContext:           dialer.DialContext,
		ResponseHeaderTimeout: 20 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
	}
	return &http.Client{Transport: tr}
}

func buildURL(endpoint string, path string, params map[string]any) (string, error) {
	endpoint = strings.TrimRight(endpoint, "/")
	path = strings.TrimLeft(path, "/")

	u, err := url.Parse(endpoint + "/" + path)
	if err != nil {
		return "", err
	}
	q := u.Query()
	for k, v := range params {
		// fmt.Sprint = robuste pour numbers/bools
		q.Set(k, fmt.Sprint(v))
	}
	u.RawQuery = q.Encode()
	return u.String(), nil
}

func getRaw(
	parent context.Context,
	client *http.Client,
	lim *Limiter,
	stats *Stats,
	fullURL string,
	reqTimeout time.Duration,
	retries int,
	backoff time.Duration,
) ([]byte, int, error) {

	var lastErr error
	var lastCode int

	for attempt := 0; attempt <= retries; attempt++ {
		atomic.AddInt64(&stats.RequestsTotal, 1)

		lim.acquire()
		ctx, cancel := context.WithTimeout(parent, reqTimeout)

		req, err := http.NewRequestWithContext(ctx, "GET", fullURL, nil)
		if err != nil {
			cancel()
			lim.release()
			return nil, 0, err
		}
		req.Header.Set("User-Agent", "ThunderDots/0.1 (go-fetch)")

		resp, err := client.Do(req)
		if err != nil {
			cancel()
			lim.release()

			lastErr = err
			atomic.AddInt64(&stats.HTTPErrors, 1)
			if errorsIsTimeout(err) || ctx.Err() == context.DeadlineExceeded {
				atomic.AddInt64(&stats.Timeouts, 1)
			}
			if attempt < retries {
				sleepBackoff(backoff, attempt)
				continue
			}
			return nil, 0, err
		}

		b, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		cancel()
		lim.release()

		if readErr != nil {
			lastErr = readErr
			atomic.AddInt64(&stats.HTTPErrors, 1)
			if attempt < retries {
				sleepBackoff(backoff, attempt)
				continue
			}
			return nil, resp.StatusCode, readErr
		}

		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			lastCode = resp.StatusCode
			lastErr = fmt.Errorf("http %d", resp.StatusCode)
			atomic.AddInt64(&stats.HTTPErrors, 1)
			if resp.StatusCode == 500 {
				atomic.AddInt64(&stats.HTTP500, 1)
			}
			if isRetryStatus(resp.StatusCode) && attempt < retries {
				sleepBackoff(backoff, attempt)
				continue
			}
			return nil, resp.StatusCode, fmt.Errorf("http %d: %s", resp.StatusCode, string(b[:min(len(b), 300)]))
		}

		if len(b) == 0 {
			lastErr = fmt.Errorf("empty body")
			atomic.AddInt64(&stats.HTTPErrors, 1)
			if attempt < retries {
				sleepBackoff(backoff, attempt)
				continue
			}
			return nil, resp.StatusCode, lastErr
		}

		return b, resp.StatusCode, nil
	}

	return nil, lastCode, lastErr
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// ---------------- Exported: TDGetJSON ----------------

//export TDGetJSON
func TDGetJSON(cfgC *C.char, pathC *C.char, paramsC *C.char) *C.char {
	cfgJSON := C.GoString(cfgC)
	path := C.GoString(pathC)
	paramsJSON := C.GoString(paramsC)

	var cfg Config
	if err := json.Unmarshal([]byte(cfgJSON), &cfg); err != nil {
		return C.CString(`{"ok":false,"status":0,"error":"bad cfg"}`)
	}
	if cfg.EndpointDTS == "" {
		return C.CString(`{"ok":false,"status":0,"error":"endpoint_dts is required"}`)
	}
	if cfg.RequestTimeout <= 0 {
		cfg.RequestTimeout = 20
	}
	if cfg.MaxInflight <= 0 {
		cfg.MaxInflight = 100
	}
	if cfg.Retries < 0 {
		cfg.Retries = 0
	}
	if cfg.Retries > 5 {
		cfg.Retries = 5
	}
	if cfg.BackoffMS <= 0 {
		cfg.BackoffMS = 200
	}

	params := map[string]any{}
	_ = json.Unmarshal([]byte(paramsJSON), &params)

	full, err := buildURL(cfg.EndpointDTS, path, params)
	if err != nil {
		out := map[string]any{"ok": false, "status": 0, "error": "bad url"}
		b, _ := json.Marshal(out)
		return C.CString(string(b))
	}

	reqTimeout := time.Duration(cfg.RequestTimeout * float64(time.Second))
	backoff := time.Duration(cfg.BackoffMS) * time.Millisecond

	parent := context.Background()
	var cancel context.CancelFunc = func() {}
	if cfg.TotalTimeout > 0 {
		parent, cancel = context.WithTimeout(parent, time.Duration(cfg.TotalTimeout*float64(time.Second)))
	}
	defer cancel()

	client := httpClient(cfg.MaxInflight)
	lim := newLimiter(cfg.MaxInflight)
	stats := &Stats{}

	b, code, e := getRaw(parent, client, lim, stats, full, reqTimeout, cfg.Retries, backoff)
	if e != nil {
		out := map[string]any{"ok": false, "status": code, "error": e.Error()}
		bo, _ := json.Marshal(out)
		return C.CString(string(bo))
	}

	var obj any
	if err := json.Unmarshal(b, &obj); err != nil {
		out := map[string]any{"ok": false, "status": code, "error": "json parse error"}
		bo, _ := json.Marshal(out)
		return C.CString(string(bo))
	}

	out := map[string]any{"ok": true, "status": code, "json": obj}
	bo, _ := json.Marshal(out)
	return C.CString(string(bo))
}

// ---------------- Exported: TDGetText ----------------

//export TDGetText
func TDGetText(cfgC *C.char, pathC *C.char, paramsC *C.char) *C.char {
	cfgJSON := C.GoString(cfgC)
	path := C.GoString(pathC)
	paramsJSON := C.GoString(paramsC)

	var cfg Config
	if err := json.Unmarshal([]byte(cfgJSON), &cfg); err != nil {
		return C.CString(`{"ok":false,"status":0,"error":"bad cfg"}`)
	}
	if cfg.EndpointDTS == "" {
		return C.CString(`{"ok":false,"status":0,"error":"endpoint_dts is required"}`)
	}
	if cfg.RequestTimeout <= 0 {
		cfg.RequestTimeout = 20
	}
	if cfg.MaxInflight <= 0 {
		cfg.MaxInflight = 100
	}
	if cfg.Retries < 0 {
		cfg.Retries = 0
	}
	if cfg.Retries > 5 {
		cfg.Retries = 5
	}
	if cfg.BackoffMS <= 0 {
		cfg.BackoffMS = 200
	}

	params := map[string]any{}
	_ = json.Unmarshal([]byte(paramsJSON), &params)

	full, err := buildURL(cfg.EndpointDTS, path, params)
	if err != nil {
		out := map[string]any{"ok": false, "status": 0, "error": "bad url"}
		b, _ := json.Marshal(out)
		return C.CString(string(b))
	}

	reqTimeout := time.Duration(cfg.RequestTimeout * float64(time.Second))
	backoff := time.Duration(cfg.BackoffMS) * time.Millisecond

	parent := context.Background()
	var cancel context.CancelFunc = func() {}
	if cfg.TotalTimeout > 0 {
		parent, cancel = context.WithTimeout(parent, time.Duration(cfg.TotalTimeout*float64(time.Second)))
	}
	defer cancel()

	client := httpClient(cfg.MaxInflight)
	lim := newLimiter(cfg.MaxInflight)
	stats := &Stats{}

	b, code, e := getRaw(parent, client, lim, stats, full, reqTimeout, cfg.Retries, backoff)
	if e != nil {
		out := map[string]any{"ok": false, "status": code, "error": e.Error()}
		bo, _ := json.Marshal(out)
		return C.CString(string(bo))
	}

	out := map[string]any{"ok": true, "status": code, "text": string(b)}
	bo, _ := json.Marshal(out)
	return C.CString(string(bo))
}

func main() {}