# ADR-0006: The real duck is reached through an SSH tunnel, not a new transport

- Status: accepted
- Date: 2026-09-20

## Context

`CLAUDE.md` §9 left the transport for the real duck open ("SSH-Tunnel (wie `microduck-mcp`)
oder WebRTC-Datachannel – Entscheidung als ADR in M4"), and M4 begins when the hardware
arrives in December. The decision is worth making now, while there is time to be wrong about
it cheaply: everything M2 and M3 built assumes the duck is an `IpcBackend`, and if that
assumption does not survive contact with hardware, it is better to learn it in September.

What we verified in September (`docs/upstream-notes.md`, against microduck@344925c):

- The daemons on a real duck listen on Unix sockets — `/run/robotd.sock`,
  `/run/tofd/tof.sock`, `/run/padd/pad.sock` — and speak the same JSON-RPC/NDJSON our `sim`
  backend already speaks. Same wire format, same methods, same `hello`.
- mediad serves a console and `GET /frame` (PNG) on TCP `:8080`, and WebRTC signalling on
  `:8443`.
- The inbound **WebSocket path for agents that the handover assumed does not exist** — it is
  a design note upstream, not code.
- The WebRTC `control` datachannel does carry `robot.*`, but with its own restrictions
  (it refuses `robot.setMode`), and it needs a signalling and media stack to get there.
- `microduck-mcp` (community, not upstream) reaches a duck with `ssh -N -L` forwards of those
  sockets plus `:8080`.

## Decision

1. **`ssh -L` forwards, and the duck backend is an `IpcBackend`.** `scripts/duck-tunnel.sh
   <host>` forwards the three sockets to local Unix sockets under
   `~/.cache/duckstudio/tunnel` and `:8080` to a local port. `RealDuckBackend` points the
   existing IPC backend at those local ends. No new protocol, no second implementation of
   the wire format, and the whole safety layer (clamps, gate, heartbeat, watchdog) applies
   unchanged.
2. **The runtime never spawns ssh.** The tunnel is a terminal a person opens, like
   `sim/up.sh`. A behavior can therefore never start a process on someone's laptop, and the
   duck's credentials stay in that person's ssh config.
3. **A missing tunnel is a sentence, not an errno.** `connect()` checks for the local socket
   first and says "no tunnel at …: run scripts/duck-tunnel.sh <host>".
4. **It is tested today, minus the ssh hop.** The backend contract suite runs the `duck`
   backend against the protocol double through exactly the socket layout the script creates.
   What hardware will add is latency, a real camera and real failure modes — not a new code
   path.
5. **WebRTC stays open, not chosen.** If the tunnel proves unworkable (a duck on a phone
   hotspot, a laptop that cannot ssh), the `control` datachannel is the fallback, and it
   would be a second transport behind the same `IpcBackend` seam.

## Alternatives considered

- **WebRTC `control` datachannel now.** Rejected for v1: it needs signalling, a peer
  connection and a media stack to carry what a socket carries directly, it refuses some
  methods, and none of it can be tested before the hardware exists.
- **Wait for upstream's agent WebSocket.** Rejected: it is a deferred design item; building
  M4 on something nobody has written is how December gets lost.
- **A small agent on the duck** that bridges to HTTP. Rejected by §3.5: nothing of ours runs
  on the duck in v1.
- **Forward to local TCP ports instead of local Unix sockets.** Rejected as the default: the
  socket-to-socket form keeps `IpcBackend` unchanged, and OpenSSH has forwarded Unix sockets
  since 6.7. TCP forwarding remains available for anything that cannot.

## Consequences

- Using a real duck means one more terminal (`scripts/duck-tunnel.sh duck.local`) and an ssh
  key on it. That is a smaller price than a second transport.
- Latency is whatever the LAN and ssh add. The deadman is 500 ms and our executor resends
  `robot.move` at 10 Hz; if the tunnel adds enough delay to trip it, the duck stops — which
  is the correct failure.
- The December checklist is now concrete: open the tunnel, run the contract suite with
  `DUCKSTUDIO_DUCK_TUNNEL` pointed at it, measure the round trip, then the safety checklist
  from §7 on hardware — and only then let a behavior drive.
- `pad.input` comes through the same tunnel, so gamepad preemption (§4) works on hardware the
  way it works in the simulator.
