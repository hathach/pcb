# jlc-cdp — drive JLCPCB ordering via Chrome DevTools Protocol

Minimal CDP driver used to place the pico2_trace_motherboard order
(W2026073018593887, 2026-07-30) when the Claude-in-Chrome extension was
wedged. Works against a dedicated Chrome instance so the main browser is
untouched.

## Setup

```bash
# one-time: clone the main profile so logins (JLCPCB, 1Password) come along
pkill -TERM -f '^/opt/google/chrome/chrome'; sleep 4
cp -a ~/.config/google-chrome ~/.cache/jlc-cdp-profile
rm -f ~/.cache/jlc-cdp-profile/Singleton*
google-chrome &                                     # main browser back
google-chrome --user-data-dir=$HOME/.cache/jlc-cdp-profile \
  --remote-debugging-port=9222 --no-first-run \
  --new-window https://cart.jlcpcb.com/shopcart/cart &

python3 -m venv venv && venv/bin/pip install websocket-client
```

## Usage

```bash
venv/bin/python cdp.py tabs                       # list pages
venv/bin/python cdp.py eval  '<js>'               # run JS in the JLC tab
venv/bin/python cdp.py nav   '<url>'
venv/bin/python cdp.py shot  out.jpg [quality]    # screenshot (viewport)
venv/bin/python cdp.py click <css-x> <css-y>      # trusted click
venv/bin/python cdp.py files '<selector>' /path…  # attach to <input type=file>
```

Targets the first tab whose URL contains `jlcpcb` (else the first page).

## JLC-wizard lessons (hard-won, 2026-07-30 session)

- Re-uploading gerbers inside Edit Order DETACHES the PCBA section —
  re-enable it via the `.switch-box.cursor-pointer` toggle, then re-set
  PCBA qty and Confirm Parts Placement (a Confirm modal follows).
- Saving after a gerber re-upload forks a NEW cart item (Y(n+1)) next to
  the old one — delete the stale group (`i.icon-remove_icon`, then the
  `el-popconfirm` Delete button).
- BOM/CPL re-upload: two `input[type=file]`s (BOM first); the
  "Process BOM & CPL" button needs a real (trusted) click at its rect.
- The Product Description cascader clears on every re-walk: open the
  `input[placeholder=Select]`, dispatch pointer/mouse event sequences on
  the `li` items (plain .click() does not work), category
  "Reserch\Education\DIY\Entertainment" → "Development Board - HS 847330".
- Element-UI chip selection state is unreliable to read from classes —
  verify with a screenshot; state probes can lie while the click landed.
- WebGL pages (placement viewer) stall Page.captureScreenshot; canvas
  toDataURL returns black (no preserveDrawingBuffer). Verify placement in
  the visible window or via JLC's paid Confirm-Parts-Placement service.
- CPL convention JLC ingests: KiCad board frame (y-down, footprint
  anchor, KiCad rotation). Do NOT convert to the gerber/pos.csv frame.
- Deselecting a matched BOM line does NOT remove its Extended loading
  fee; any THT line present brings back the ~$7 hand-solder+manual block.
