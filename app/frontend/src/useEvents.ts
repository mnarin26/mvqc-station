import { useEffect, useRef, useState } from "react";
import type { StationEvent } from "./types";

/** Subscribe to the station event bus over WebSocket with auto-reconnect. */
export function useEvents(onEvent: (e: StationEvent) => void) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let ws: WebSocket;
    let closed = false;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) setTimeout(connect, 2000);
      };
      ws.onmessage = (ev) => handlerRef.current(JSON.parse(ev.data));
    };
    connect();
    return () => { closed = true; ws?.close(); };
  }, []);

  return connected;
}
