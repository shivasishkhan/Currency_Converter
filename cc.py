import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk, ImageDraw
import requests
import threading
import sys
import traceback
import time
from datetime import datetime, timezone, timedelta

API_KEY = "1bcd5bb0563d4e76b6562d54ff6e2b23"

# ---------- helpers ----------
def safe_open_image(path, size, placeholder_text=None, bg="#808080"):
    try:
        img = Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
        return img
    except Exception:
        img = Image.new("RGBA", size, bg)
        if placeholder_text:
            try:
                draw = ImageDraw.Draw(img)
                w, h = draw.textsize(placeholder_text)
                draw.text(((size[0]-w)/2, (size[1]-h)/2), placeholder_text, fill="white")
            except Exception:
                pass
        return img

def make_rounded_rect_image(size, radius=20, fill="#000000", outline="#ffffff", outline_width=2):
    w, h = size
    img = Image.new("RGBA", (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    shape = [(outline_width//2, outline_width//2), (w - outline_width//2 -1, h - outline_width//2 -1)]
    draw.rounded_rectangle(shape, radius=radius, fill=fill, outline=outline, width=outline_width)
    return img

def fetch_rates():
    try:
        r = requests.get(f"https://api.currencyfreaks.com/latest?apikey={API_KEY}", timeout=5)
        r.raise_for_status()
        data = r.json()
        return {k: float(v) for k, v in data.get("rates", {}).items()}
    except Exception as e:
        print("fetch_rates error:", e, file=sys.stderr)
        return None

def fit_text_to_width(widget, text, max_pixels, family="Helvetica", weight="bold", max_size=28, min_size=10):
    size = max_size
    f = tkfont.Font(family=family, size=size, weight=weight)
    widget.config(font=f, fg="#ffffff")
    widget.update_idletasks()
    while f.measure(text) > max_pixels and size > min_size:
        size -= 1
        f = tkfont.Font(family=family, size=size, weight=weight)
        widget.config(font=f, fg="#ffffff")

# ---------- IST helper ----------
def ist_now_str():
    # IST = UTC + 5:30
    utc = datetime.utcnow().replace(tzinfo=timezone.utc)
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime("%d %b %Y, %H:%M:%S IST")

# ---------- constants & layout ----------
WIN_W, WIN_H = 900, 500
BAR_W, BAR_H = 860, 140
PAD = 14
FROM_W = 160
TO_W = 160
EQUAL_W = 64
AMOUNT_W = (BAR_W - (PAD*6 + FROM_W + TO_W + EQUAL_W)) // 2
AMOUNT_H = BAR_H - PAD*2

# ---------- window ----------
root = tk.Tk()
root.title("Shivasish Khan's Currency Converter")
root.geometry(f"{WIN_W}x{WIN_H}")
root.resizable(False, False)

# background safe
bg_img = safe_open_image("1.jpg", (WIN_W, WIN_H), placeholder_text=None, bg="#222222")
bg_photo = ImageTk.PhotoImage(bg_img)
tk.Label(root, image=bg_photo).place(x=0, y=0, relwidth=1, relheight=1)

# load flags safely
FLAG_FILES = {"USD":"usd.png","EUR":"eur.png","INR":"inr.png","JPY":"jpy.png"}
flags_img = {}
FLAG_SIZE = (48, 32)
for code, fn in FLAG_FILES.items():
    im = safe_open_image(fn, FLAG_SIZE, placeholder_text=code, bg="#444444")
    flags_img[code] = ImageTk.PhotoImage(im)

SYMBOLS = {"USD":"$", "EUR":"€", "INR":"₹", "JPY":"¥"}

# state
debounce_job = None
amount_var = tk.StringVar()
result_var = tk.StringVar(value="—")
from_var = tk.StringVar(value="USD")
to_var = tk.StringVar(value="INR")
rates_cache = {}
updating_text = False  # prevent recursive text updates

# ---------- last refreshed state & label (IST) ----------
last_refreshed_var = tk.StringVar(value="Last refreshed: — IST")

# ---------- periodic timestamp job handle ----------
periodic_timestamp_job = None  # holds root.after id when running

def update_timestamp_now():
    """Update the IST timestamp immediately (called via main thread)."""
    last_refreshed_var.set("Last refreshed: " + ist_now_str())

def periodic_timestamp_tick():
    """Tick function scheduled every 60 seconds."""
    global periodic_timestamp_job
    update_timestamp_now()
    periodic_timestamp_job = root.after(60_000, periodic_timestamp_tick)  # schedule next tick

def start_periodic_timestamp():
    """Start (or restart) the periodic 60s timestamp updates and perform an immediate update."""
    global periodic_timestamp_job
    # cancel existing if present
    if periodic_timestamp_job:
        try:
            root.after_cancel(periodic_timestamp_job)
        except Exception:
            pass
        periodic_timestamp_job = None
    # immediate update + schedule next
    update_timestamp_now()
    periodic_timestamp_job = root.after(60_000, periodic_timestamp_tick)

def stop_periodic_timestamp():
    """Stop periodic timestamp updates."""
    global periodic_timestamp_job
    if periodic_timestamp_job:
        try:
            root.after_cancel(periodic_timestamp_job)
        except Exception:
            pass
        periodic_timestamp_job = None

# ---------- rounded background images ----------
rounded_imgs = {}
rounded_imgs['amount_bg'] = ImageTk.PhotoImage(
    make_rounded_rect_image((AMOUNT_W, AMOUNT_H), radius=18, fill="#000000", outline="#ffffff", outline_width=3)
)
rounded_imgs['result_bg'] = ImageTk.PhotoImage(
    make_rounded_rect_image((AMOUNT_W, AMOUNT_H), radius=18, fill="#000000", outline="#ffffff", outline_width=3)
)
rounded_imgs['equals_bg'] = ImageTk.PhotoImage(
    make_rounded_rect_image((EQUAL_W, EQUAL_W), radius=12, fill="#000000", outline="#000000", outline_width=0)
)
rounded_imgs['switch_bg'] = ImageTk.PhotoImage(
    make_rounded_rect_image((FROM_W-12, 72), radius=16, fill="#000000", outline="#ffffff", outline_width=3)
)

# ---------- build UI ----------
bar_x = (WIN_W - BAR_W)//2
bar_y = (WIN_H - BAR_H)//2
bar = tk.Frame(root, bg="#000000", bd=0, relief="flat")
bar.place(x=bar_x, y=bar_y, width=BAR_W, height=BAR_H)

# Amount
amount_bg_label = tk.Label(bar, image=rounded_imgs['amount_bg'], bd=0, bg="#000000")
amount_bg_label.place(x=PAD, y=PAD, width=AMOUNT_W, height=AMOUNT_H)
amount_entry = tk.Entry(bar, textvariable=amount_var, bd=0, justify="left", fg="#ffffff", bg="#000000", insertbackground="#ffffff")
amount_entry.place(x=PAD+12, y=PAD+12, width=AMOUNT_W-24, height=AMOUNT_H-24)

# From switch
x_from = PAD + AMOUNT_W + PAD
switch_w = FROM_W - 12
switch_h = 72
from_bg_label = tk.Label(bar, image=rounded_imgs['switch_bg'], bd=0)
from_bg_label.place(x=x_from+6, y=(BAR_H - switch_h)//2, width=switch_w, height=switch_h)

def make_switch_on_bg(parent, var, initial, x, y, width, height):
    mb = tk.Menubutton(
        parent,
        text=initial,
        image=flags_img.get(initial),
        compound="left",
        relief="flat",
        bd=5,
        padx=8,
        anchor="w",
        bg="#000000",
        fg="#ffffff",
        activebackground="#111",
        activeforeground="#999999"
    )
    mb.config(font=("Arial", 10))
    mb.place(x=x, y=y, width=width, height=height)

    menu = tk.Menu(
        mb,
        tearoff=False,
        bg="#000000",
        fg="#aaaaaa",
        activebackground="#999999",
        activeforeground="#ffffff"
    )
    mb.config(menu=menu)

    def on_select(code):
        var.set(code)
        mb.config(text=code, image=flags_img.get(code))

    for code in flags_img.keys():
        menu.add_command(
            label=code,
            image=flags_img[code],
            compound="left",
            command=lambda c=code: on_select(c)
        )
    mb.config(text=initial, image=flags_img.get(initial))
    return mb

from_mb = make_switch_on_bg(bar, from_var, from_var.get(), x_from+6, (BAR_H - switch_h)//2, switch_w, switch_h)

# Equals
equals_x = x_from + FROM_W + PAD
equals_bg_label = tk.Label(bar, image=rounded_imgs['equals_bg'], bd=0, bg="#000000")
equals_bg_label.place(x=equals_x, y=(BAR_H - EQUAL_W)//2, width=EQUAL_W, height=EQUAL_W)
equals_label = tk.Label(bar, text="=", font=("Helvetica", 28, "bold"), bg="#000000", fg="#ffffff")
equals_label.place(x=equals_x + 2, y=(BAR_H - EQUAL_W)//2 + 2, width=EQUAL_W - 4, height=EQUAL_W - 4)

# Result
result_x = equals_x + EQUAL_W + PAD
result_bg_label = tk.Label(bar, image=rounded_imgs['result_bg'], bd=0, bg="#000000")
result_bg_label.place(x=result_x, y=PAD, width=AMOUNT_W, height=AMOUNT_H)
result_label = tk.Label(bar, textvariable=result_var, bd=0, bg="#000000", fg="#ffffff", anchor="center")
result_label.place(x=result_x + 12, y=PAD + 12, width=AMOUNT_W - 24, height=AMOUNT_H - 24)

# To switch
to_x = result_x + AMOUNT_W + PAD
to_bg_label = tk.Label(bar, image=rounded_imgs['switch_bg'], bd=0)
to_bg_label.place(x=to_x+6, y=(BAR_H - switch_h)//2, width=switch_w, height=switch_h)
to_mb = make_switch_on_bg(bar, to_var, to_var.get(), to_x+6, (BAR_H - switch_h)//2, switch_w, switch_h)

# ---------- last refreshed label (placed below the horizontal bar) ----------
# small margin below the bar
LAST_LABEL_HEIGHT = 20
last_label = tk.Label(
    root,
    textvariable=last_refreshed_var,
    bg="#FFFFFF",       # matches the bar background for visual consistency
    fg="#000000",
    font=("Arial", 9, "italic"),
    anchor="center"
)
last_label.place(x=bar_x, y=bar_y + BAR_H + 6, width=BAR_W, height=LAST_LABEL_HEIGHT)

# Set initial timestamp to the program open/start time
last_refreshed_var.set("Last refreshed: " + ist_now_str())

# Start periodic timestamp updates immediately (every 60 seconds)
start_periodic_timestamp()

# ---------- logic ----------
def schedule_convert(*_):
    global debounce_job
    if debounce_job:
        root.after_cancel(debounce_job)
    debounce_job = root.after(150, do_convert)

def do_convert():
    global rates_cache
    try:
        raw = amount_var.get().replace(SYMBOLS.get(from_var.get(), ""), "").strip()
        if raw == "":
            result_var.set(f"{SYMBOLS.get(to_var.get(), '')} —")
            adjust_fonts()
            return
        try:
            val = float(raw)
        except ValueError:
            result_var.set(f"{SYMBOLS.get(to_var.get(), '')} Invalid")
            adjust_fonts()
            return

        amount_var.set(f"{SYMBOLS.get(from_var.get(), '')} {val:.2f}")

        # conversion using cached rates
        from_rate = rates_cache.get(from_var.get(), 1)
        to_rate = rates_cache.get(to_var.get(), 1)
        conv = val / from_rate * to_rate
        result_var.set(f"{SYMBOLS.get(to_var.get(), '')} {conv:.2f}")
        adjust_fonts()

        # conversions do NOT modify the periodic timestamp (Enter does)

    except Exception as e:
        print("do_convert error:", e, file=sys.stderr)
        traceback.print_exc()
        result_var.set(f"{SYMBOLS.get(to_var.get(), '')} Error")
        adjust_fonts()

def on_enter_pressed(event=None):
    """
    Called when user presses Enter in the amount entry.
    Performs conversion immediately and updates the timestamp.
    """
    try:
        # do immediate conversion
        do_convert()
    finally:
        # update the timestamp immediately (IST)
        update_timestamp_now()
    # prevent default handling propagation
    return "break"

def update_amount_symbol(*_):
    global updating_text
    if updating_text:
        return
    updating_text = True
    cur = amount_var.get()
    sym = SYMBOLS.get(from_var.get(), "")
    for s in SYMBOLS.values():
        if cur.startswith(s):
            cur = cur[len(s):].strip()
    amount_var.set(f"{sym} {cur}")
    updating_text = False
    schedule_convert()

def adjust_fonts():
    pad_inner = 12
    amt_text = amount_var.get() or ""
    res_text = result_var.get() or ""
    amount_entry.update_idletasks()
    result_label.update_idletasks()
    fit_text_to_width(amount_entry, amt_text, AMOUNT_W - pad_inner, family="Helvetica", weight="bold", max_size=28, min_size=10)
    fit_text_to_width(result_label, res_text, AMOUNT_W - pad_inner, family="Helvetica", weight="bold", max_size=28, min_size=10)

# ---------- fetch rates in background (no timestamp changes here) ----------
def fetch_rates_periodically():
    global rates_cache
    while True:
        rates = fetch_rates()
        if rates:
            rates_cache = rates
        time.sleep(300)  # update every 5 minutes

threading.Thread(target=fetch_rates_periodically, daemon=True).start()

# keep original bindings for behavior
amount_var.trace_add("write", update_amount_symbol)
from_var.trace_add("write", update_amount_symbol)
to_var.trace_add("write", schedule_convert)

# bind Enter key(s) on the amount entry to trigger conversion + timestamp update
amount_entry.bind("<Return>", on_enter_pressed)
amount_entry.bind("<KP_Enter>", on_enter_pressed)

# ---------- initial ----------
amount_var.set(f"{SYMBOLS[from_var.get()]} 0")
schedule_convert()

root.mainloop()
