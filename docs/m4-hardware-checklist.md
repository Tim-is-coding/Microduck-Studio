# When the duck arrives (M4)

Written 2026-09-20, before the hardware, so the first day with a real duck is a list rather
than an improvisation. Everything here is already possible except the steps marked
**hardware**; the transport is ADR-0006, the safety rules are `CLAUDE.md` §7.

## 1. Before you touch the duck

- [ ] `cd runtime && uv sync && uv run pytest -q` — 200+ tests, no skips you did not expect.
- [ ] Read `docs/upstream-notes.md` again against the duck's firmware version. Ours was
      verified against microduck@344925c (0.14.1, API 31) and re-checked against @ac7531a
      (0.14.4, API 34). A different API version is not a
      reason to panic — upstream logs skew and carries on — but it *is* a reason to re-read
      the method table before driving anything.

## 2. Open the tunnel (**hardware**)

- [ ] `./scripts/duck-tunnel.sh <duck-host>` in its own terminal. It forwards
      `/run/robotd.sock`, `/run/tofd/tof.sock`, `/run/padd/pad.sock` and mediad's `:8080`.
- [ ] `ls ~/.cache/duckstudio/tunnel` shows the three sockets.
- [ ] `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/frame` → 200 (or no
      camera on this duck, which is fine).

## 3. Run the contract against the real thing (**hardware**)

- [ ] `DUCKSTUDIO_DUCK_TUNNEL=~/.cache/duckstudio/tunnel uv run pytest tests/backends -q`
      The same suite that passes against the protocol double. **Every failure here is a
      finding**: it means the duck's wire behaviour differs from what we verified in
      September. Write it into `docs/upstream-notes.md` with the date before fixing code.
- [ ] **IMU mounting**: tilt the standing duck by hand, nose down, then right side down.
      `curl -s localhost:8000/api/state` shows `imu.pitch > 0`, then `imu.roll > 0` (REP-103,
      the signs verified in the sim — `docs/upstream-notes.md`, "Roll and pitch"). A flipped
      sign means the duck's IMU sits differently from the sim's; note it before fixing code.
- [ ] Note the round trip: how long `robot.health` takes through the tunnel. The deadman is
      500 ms and the executor resends `robot.move` at 10 Hz; if a call takes longer than
      ~100 ms, say so in the notes and consider the WebRTC fallback (ADR-0006).

## 4. The safety checklist, on hardware, before any behavior (**hardware**)

Do these with the duck on a table, held, or on a soft floor — one person's hand on it.

- [ ] **Notstopp**: `curl -X POST localhost:8000/api/stop` while it is moving. It stops.
- [ ] **Deadman**: kill the runtime mid-walk. The duck stops by itself within 500 ms
      (`robot.state.move.limited_by == ["deadman"]`).
- [ ] **Watchdog**: pause the executor (breakpoint) while driving; our watchdog calls
      `backend.stop()` after 350 ms and says so in the log.
- [ ] **Clamps**: send a walk step at `tempo: brisk`; `robot.state.move.applied` never
      exceeds the manifest bounds. Upstream clamps nothing — ours are the only limits.
- [ ] **Battery gate**: below 15 % the gate refuses movement intents (§7). Check the log
      says why.
- [ ] **Gamepad**: touch the pad; the executor is preempted within one tick and the log
      names it.

## 5. First behavior (**hardware**)

- [ ] `follow-me` with a person standing 2 m away, in the Studio, with a hand ready and the
      Notstopp on screen. Watch the Live panel: the person chip, the ToF grid, the step bar.
- [ ] Then the one M2 could never show: does it actually walk? (In the simulator it does not
      — upstream `microduck_rl#46`.)

## 6. Afterwards

- [ ] Write what the duck did differently into `docs/upstream-notes.md`, dated.
- [ ] If a Hub policy was loaded (`robot.loadPolicy`), verify `policy.fetch` against
      upstream's code first — it is in our notes as **unverified**, from microduck-mcp.
- [ ] Only then: Hub sharing of behavior packs (M4's last item, `CLAUDE.md` §8).
